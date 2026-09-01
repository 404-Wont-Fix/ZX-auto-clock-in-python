"""受控内容源的抓取、健康状态与选择服务。"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import secrets
import socket
import string
from dataclasses import dataclass
from time import perf_counter
from datetime import datetime, timezone
from typing import Awaitable, Callable, Iterable, Optional
from urllib.parse import urljoin, urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import ContentSource


MAX_TEXT_BYTES = 64 * 1024
TEXT_READ_CHUNK_BYTES = 8 * 1024
IMAGE_PREFIX_BYTES = 512
MAX_REDIRECTS = 3
MAX_ADDRESSES_PER_HOST = 4
CONNECT_IP_EXTENSION = "content_source_connect_ip"
TEXT_PARSE_MODES = {"json_text", "plain_text"}
IMAGE_PARSE_MODES = {"json_image", "redirect_image"}


class ContentSourceFetchError(RuntimeError):
    """内容源返回无效内容或请求失败。"""


class ContentSourceSecurityError(ContentSourceFetchError):
    """内容源目标违反公网 HTTPS 限制。"""


class ContentSourceRequestError(ContentSourceFetchError):
    """用户请求参数与来源定义不兼容，不计入来源健康。"""


@dataclass(frozen=True)
class FetchedContent:
    value: str
    final_url: str
    latency_ms: int
    content_type: Optional[str] = None
    attribution: Optional[str] = None


@dataclass(frozen=True)
class ContentResult:
    value: Optional[str]
    source_key: Optional[str]
    fallback: bool
    latency_ms: Optional[int] = None


Resolver = Callable[[str], Awaitable[Iterable[str]]]


async def _resolve_hostname(hostname: str) -> list[str]:
    """在线程中解析域名，避免阻塞事件循环。"""

    def resolve() -> list[str]:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        return sorted({info[4][0] for info in infos})

    return await asyncio.to_thread(resolve)


def _is_public_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False

    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    forbidden = (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )
    return bool(ip.is_global and not forbidden)


def _json_object(raw: Optional[str], *, field_name: str, default):
    try:
        value = json.loads(raw or json.dumps(default))
    except (TypeError, json.JSONDecodeError) as exc:
        raise ContentSourceFetchError(f"{field_name} 不是有效 JSON") from exc
    return value


def _dot_path(data, path: Optional[str]):
    if not path:
        raise ContentSourceFetchError("JSON 解析模式缺少值路径")

    current = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                raise ContentSourceFetchError(f"值路径不存在: {path}")
            current = current[index]
        else:
            raise ContentSourceFetchError(f"值路径不存在: {path}")
    return current


class _PinnedAsyncHTTPTransport(httpx.AsyncBaseTransport):
    """把已校验地址绑定到实际连接，同时保留原始 Host 与 TLS SNI。"""

    def __init__(self, delegate: Optional[httpx.AsyncBaseTransport] = None):
        self._delegate = delegate or httpx.AsyncHTTPTransport(
            trust_env=False,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        connect_ip = request.extensions.get(CONNECT_IP_EXTENSION)
        if not isinstance(connect_ip, str) or not connect_ip:
            raise httpx.ConnectError("内容源请求缺少已校验连接地址", request=request)

        original_hostname = request.url.raw_host.decode("ascii")
        extensions = dict(request.extensions)
        extensions["sni_hostname"] = original_hostname
        pinned_request = httpx.Request(
            method=request.method,
            url=request.url.copy_with(host=connect_ip),
            headers=request.headers,
            stream=request.stream,
            extensions=extensions,
        )
        return await self._delegate.handle_async_request(pinned_request)

    async def aclose(self) -> None:
        await self._delegate.aclose()


class ContentSourceFetcher:
    """只执行公网 HTTPS GET 的受控抓取器。"""

    def __init__(
        self,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        resolver: Optional[Resolver] = None,
    ):
        self.transport = transport
        self.resolver = resolver or _resolve_hostname

    async def _validated_public_addresses(self, url: str) -> list[str]:
        parsed = urlsplit(url)
        if parsed.scheme.lower() != "https":
            raise ContentSourceSecurityError("内容源只允许 HTTPS")
        if not parsed.hostname:
            raise ContentSourceSecurityError("内容源地址缺少主机名")
        if parsed.username is not None or parsed.password is not None:
            raise ContentSourceSecurityError("内容源地址禁止携带凭据")
        try:
            if parsed.port is not None and not 1 <= parsed.port <= 65535:
                raise ContentSourceSecurityError("内容源端口无效")
        except ValueError as exc:
            raise ContentSourceSecurityError("内容源端口无效") from exc

        hostname = parsed.hostname
        try:
            addresses = [str(ipaddress.ip_address(hostname))]
        except ValueError:
            try:
                addresses = list(await self.resolver(hostname))
            except (OSError, socket.gaierror) as exc:
                raise ContentSourceFetchError("内容源域名解析失败") from exc

        if not addresses:
            raise ContentSourceFetchError("内容源域名未解析到地址")
        unsafe = [address for address in addresses if not _is_public_address(address)]
        if unsafe:
            raise ContentSourceSecurityError("内容源解析到了非公网地址")
        return sorted({str(ipaddress.ip_address(address)) for address in addresses})

    async def validate_public_https_url(self, url: str) -> str:
        await self._validated_public_addresses(url)
        return url

    def _materialize_request(self, source: ContentSource, category: Optional[str]) -> str:
        categories = _json_object(
            source.categories_json,
            field_name="允许分类",
            default=[],
        )
        if not isinstance(categories, list) or any(not isinstance(item, str) for item in categories):
            raise ContentSourceFetchError("允许分类必须是字符串数组")

        fields = []
        for _, field_name, _, _ in string.Formatter().parse(source.url_template):
            if field_name:
                fields.append(field_name)

        query_params = _json_object(
            source.query_params_json,
            field_name="查询参数",
            default={},
        )
        if not isinstance(query_params, dict):
            raise ContentSourceFetchError("查询参数必须是对象")
        for key, value in query_params.items():
            if not isinstance(key, str) or not isinstance(value, (str, int, float, bool)):
                raise ContentSourceFetchError("查询参数仅允许标量值")
            if isinstance(value, str):
                for _, field_name, _, _ in string.Formatter().parse(value):
                    if field_name:
                        fields.append(field_name)

        if any(field != "category" for field in fields):
            raise ContentSourceFetchError("地址模板仅允许 {category} 占位符")

        selected_category = category
        if "category" in fields:
            if selected_category in (None, "random"):
                if not categories:
                    raise ContentSourceFetchError("地址模板缺少允许的分类")
                selected_category = secrets.choice(categories)
            if selected_category not in categories:
                raise ContentSourceRequestError("请求分类不在允许列表中")

        replacements = {"category": selected_category or ""}
        try:
            request_url = source.url_template.format(**replacements)
            materialized_params = {
                key: value.format(**replacements) if isinstance(value, str) else value
                for key, value in query_params.items()
            }
        except (KeyError, ValueError) as exc:
            raise ContentSourceFetchError("内容源地址模板无效") from exc

        return str(httpx.URL(request_url).copy_merge_params(materialized_params))

    @staticmethod
    async def _read_limited(response: httpx.Response) -> bytes:
        content_encoding = response.headers.get("content-encoding", "").strip().lower()
        if content_encoding and content_encoding != "identity":
            raise ContentSourceFetchError("文字响应禁止压缩传输")

        content_length = response.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_TEXT_BYTES:
                    raise ContentSourceFetchError("文字响应超过 64 KiB 上限")
            except ValueError:
                pass

        body = bytearray()
        async for chunk in response.aiter_bytes(chunk_size=TEXT_READ_CHUNK_BYTES):
            body.extend(chunk)
            if len(body) > MAX_TEXT_BYTES:
                raise ContentSourceFetchError("文字响应超过 64 KiB 上限")
        return bytes(body)

    @staticmethod
    async def _read_image_prefix(response: httpx.Response) -> bytes:
        content_encoding = response.headers.get("content-encoding", "").strip().lower()
        if content_encoding and content_encoding != "identity":
            raise ContentSourceFetchError("图片响应禁止压缩传输")

        prefix = bytearray()
        async for chunk in response.aiter_bytes(chunk_size=IMAGE_PREFIX_BYTES):
            prefix.extend(chunk)
            break
        if not prefix:
            raise ContentSourceFetchError("图片响应为空")
        return bytes(prefix[:IMAGE_PREFIX_BYTES])

    @staticmethod
    async def _send_with_address_fallback(
        client: httpx.AsyncClient,
        url: str,
        addresses: list[str],
    ) -> httpx.Response:
        last_error: Optional[httpx.RequestError] = None
        for address in addresses:
            request = client.build_request(
                "GET",
                url,
                headers={"Accept-Encoding": "identity"},
                extensions={CONNECT_IP_EXTENSION: address},
            )
            try:
                return await client.send(request, stream=True)
            except httpx.RequestError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise ContentSourceFetchError("内容源域名未解析到地址")

    async def fetch(
        self,
        source: ContentSource,
        category: Optional[str] = None,
    ) -> FetchedContent:
        if source.source_type not in {"text", "image"}:
            raise ContentSourceFetchError("内容源类型无效")
        valid_modes = TEXT_PARSE_MODES if source.source_type == "text" else IMAGE_PARSE_MODES
        if source.parse_mode not in valid_modes:
            raise ContentSourceFetchError("解析模式与内容源类型不匹配")
        if not 2 <= int(source.timeout_seconds) <= 30:
            raise ContentSourceFetchError("内容源超时必须在 2–30 秒之间")

        current_url = self._materialize_request(source, category)
        started = perf_counter()
        timeout_seconds = float(source.timeout_seconds)
        timeout = httpx.Timeout(timeout_seconds)
        transport = self.transport or _PinnedAsyncHTTPTransport()

        try:
            async with asyncio.timeout(timeout_seconds):
                async with httpx.AsyncClient(
                    timeout=timeout,
                    follow_redirects=False,
                    transport=transport,
                    trust_env=False,
                ) as client:
                    for redirect_count in range(MAX_REDIRECTS + 1):
                        addresses = (
                            await self._validated_public_addresses(current_url)
                        )[:MAX_ADDRESSES_PER_HOST]
                        response = await self._send_with_address_fallback(
                            client,
                            current_url,
                            addresses,
                        )
                        try:
                            if response.is_redirect:
                                location = response.headers.get("location")
                                if not location:
                                    raise ContentSourceFetchError("重定向响应缺少 Location")
                                if redirect_count >= MAX_REDIRECTS:
                                    raise ContentSourceFetchError("内容源重定向超过三次")
                                current_url = urljoin(str(response.url), location)
                                continue

                            try:
                                response.raise_for_status()
                            except httpx.HTTPStatusError as exc:
                                raise ContentSourceFetchError(
                                    f"内容源返回 HTTP {response.status_code}"
                                ) from exc

                            content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                            final_url = str(response.url)

                            if source.parse_mode == "redirect_image":
                                if not content_type.startswith("image/"):
                                    raise ContentSourceFetchError("图片源未返回图片内容")
                                await self._read_image_prefix(response)
                                return FetchedContent(
                                    value=final_url,
                                    final_url=final_url,
                                    latency_ms=max(0, round((perf_counter() - started) * 1000)),
                                    content_type=content_type,
                                )

                            body = await self._read_limited(response)
                            if source.parse_mode == "plain_text":
                                encoding = response.encoding or "utf-8"
                                try:
                                    value = body.decode(encoding).strip()
                                except (LookupError, UnicodeDecodeError) as exc:
                                    raise ContentSourceFetchError("文字响应编码无效") from exc
                                if not value:
                                    raise ContentSourceFetchError("文字响应为空")
                                return FetchedContent(
                                    value=value,
                                    final_url=final_url,
                                    latency_ms=max(0, round((perf_counter() - started) * 1000)),
                                    content_type=content_type or None,
                                )

                            try:
                                data = json.loads(body)
                            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                                raise ContentSourceFetchError("内容源返回无效 JSON") from exc

                            raw_value = _dot_path(data, source.value_path)
                            if not isinstance(raw_value, str) or not raw_value.strip():
                                raise ContentSourceFetchError("值路径没有返回非空字符串")
                            value = raw_value.strip()

                            attribution = None
                            if source.attribution_path:
                                raw_attribution = _dot_path(data, source.attribution_path)
                                if isinstance(raw_attribution, str) and raw_attribution.strip():
                                    attribution = raw_attribution.strip()

                            if source.parse_mode == "json_image":
                                value = urljoin(final_url, value)
                                await self.validate_public_https_url(value)
                            elif attribution:
                                value = f"{value} —— {attribution}"

                            return FetchedContent(
                                value=value,
                                final_url=final_url,
                                latency_ms=max(0, round((perf_counter() - started) * 1000)),
                                content_type=content_type or None,
                                attribution=attribution,
                            )
                        finally:
                            await response.aclose()
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise ContentSourceFetchError("内容源请求超时") from exc
        except httpx.RequestError as exc:
            raise ContentSourceFetchError("内容源连接失败") from exc

        raise ContentSourceFetchError("内容源请求未返回结果")


DEFAULT_CONTENT_SOURCES = (
    {
        "key": "poetry_all",
        "name": "今日诗词",
        "source_type": "text",
        "priority": 10,
        "url_template": "https://v1.jinrishici.com/all.json",
        "query_params": {},
        "parse_mode": "json_text",
        "value_path": "content",
        "attribution_path": None,
        "categories": [],
        "timeout_seconds": 10,
    },
    {
        "key": "hitokoto",
        "name": "Hitokoto 一言",
        "source_type": "text",
        "priority": 20,
        "url_template": "https://v1.hitokoto.cn/",
        "query_params": {},
        "parse_mode": "json_text",
        "value_path": "hitokoto",
        "attribution_path": "from",
        "categories": [],
        "timeout_seconds": 10,
    },
    {
        "key": "qzqi_yiyan",
        "name": "QZQI 新一言",
        "source_type": "text",
        "priority": 30,
        "url_template": "https://api.qzqi.com/api/v1/Yiyan",
        "query_params": {"format": "json"},
        "parse_mode": "json_text",
        "value_path": "quote",
        "attribution_path": None,
        "categories": [],
        "timeout_seconds": 10,
    },
    {
        "key": "bing",
        "name": "Bing 每日壁纸",
        "source_type": "image",
        "priority": 10,
        "url_template": "https://www.bing.com/HPImageArchive.aspx",
        "query_params": {"format": "js", "idx": "0", "n": "1", "mkt": "zh-CN"},
        "parse_mode": "json_image",
        "value_path": "images.0.url",
        "attribution_path": None,
        "categories": [],
        "timeout_seconds": 10,
    },
    {
        "key": "bing_uhd",
        "name": "Bing 官方 UHD",
        "source_type": "image",
        "priority": 20,
        "url_template": "https://www.bing.com/HPImageArchive.aspx",
        "query_params": {
            "format": "js",
            "idx": "0",
            "n": "1",
            "mkt": "zh-CN",
            "uhd": "1",
            "uhdwidth": "3840",
            "uhdheight": "2160",
        },
        "parse_mode": "json_image",
        "value_path": "images.0.url",
        "attribution_path": None,
        "categories": [],
        "timeout_seconds": 10,
    },
    {
        "key": "komll",
        "name": "Komll 图片",
        "source_type": "image",
        "priority": 30,
        "url_template": "https://api.komll.com/images",
        "query_params": {},
        "parse_mode": "redirect_image",
        "value_path": None,
        "attribution_path": None,
        "categories": [],
        "timeout_seconds": 10,
    },
    {
        "key": "loliapi",
        "name": "LoliAPI ACG",
        "source_type": "image",
        "priority": 40,
        "url_template": "https://www.loliapi.com/acg/",
        "query_params": {},
        "parse_mode": "redirect_image",
        "value_path": None,
        "attribution_path": None,
        "categories": [],
        "timeout_seconds": 10,
    },
    {
        "key": "cimuapi",
        "name": "次元图源",
        "source_type": "image",
        "priority": 50,
        "url_template": "https://t.alcy.cc/{category}/",
        "query_params": {},
        "parse_mode": "redirect_image",
        "value_path": None,
        "attribution_path": None,
        "categories": [
            "ycy", "moez", "ai", "ysz", "pc", "moe", "fj", "bd",
            "ys", "mp", "moemp", "ysmp", "aimp", "tx", "lai", "xhl",
        ],
        "timeout_seconds": 10,
    },
)


class ContentSourceService:
    """内容源持久化、健康记账与降级选择。"""

    CONFIG_FIELDS = {
        "source_type",
        "url_template",
        "query_params",
        "parse_mode",
        "value_path",
        "attribution_path",
        "categories",
        "timeout_seconds",
    }
    MUTABLE_FIELDS = CONFIG_FIELDS | {"name", "enabled", "priority"}

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def config_fingerprint(source: ContentSource) -> str:
        return source.config_fingerprint

    @staticmethod
    def _validate_definition(data: dict, *, creating: bool = False) -> None:
        key = data.get("key")
        if creating and (not isinstance(key, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", key)):
            raise ValueError("内容源 key 只能包含小写字母、数字、下划线和连字符")
        if creating and data.get("enabled"):
            raise ValueError("新内容源必须测试成功后才能启用")

        source_type = data.get("source_type")
        parse_mode = data.get("parse_mode")
        if source_type not in {"text", "image"}:
            raise ValueError("内容源类型必须是 text 或 image")
        allowed_modes = TEXT_PARSE_MODES if source_type == "text" else IMAGE_PARSE_MODES
        if parse_mode not in allowed_modes:
            raise ValueError("解析模式与内容源类型不匹配")

        url_template = data.get("url_template")
        if not isinstance(url_template, str) or not url_template.startswith("https://"):
            raise ValueError("内容源只允许 HTTPS 地址")

        fields = [
            field_name
            for _, field_name, _, _ in string.Formatter().parse(url_template)
            if field_name
        ]
        query_params = data.get("query_params", {})
        if not isinstance(query_params, dict):
            raise ValueError("查询参数必须是对象")
        for key_name, value in query_params.items():
            if not isinstance(key_name, str) or not isinstance(value, (str, int, float, bool)):
                raise ValueError("查询参数仅允许标量值")
            if isinstance(value, str):
                fields.extend(
                    field_name
                    for _, field_name, _, _ in string.Formatter().parse(value)
                    if field_name
                )
        if any(field != "category" for field in fields):
            raise ValueError("地址模板仅允许 {category} 占位符")

        categories = data.get("categories", [])
        if not isinstance(categories, list) or any(
            not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", item)
            for item in categories
        ):
            raise ValueError("允许分类格式无效")
        if "category" in fields and not categories:
            raise ValueError("使用 {category} 时必须配置允许分类")

        timeout_seconds = data.get("timeout_seconds")
        if not isinstance(timeout_seconds, int) or not 2 <= timeout_seconds <= 30:
            raise ValueError("内容源超时必须在 2–30 秒之间")

        value_path = data.get("value_path")
        if parse_mode in {"json_text", "json_image"} and not value_path:
            raise ValueError("JSON 解析模式必须配置值路径")

    @staticmethod
    def _definition_from_source(source: ContentSource) -> dict:
        return {
            "key": source.key,
            "name": source.name,
            "source_type": source.source_type,
            "enabled": source.enabled,
            "priority": source.priority,
            "url_template": source.url_template,
            "query_params": source.query_params,
            "parse_mode": source.parse_mode,
            "value_path": source.value_path,
            "attribution_path": source.attribution_path,
            "categories": source.categories,
            "timeout_seconds": source.timeout_seconds,
        }

    @staticmethod
    def _make_source(data: dict, *, enabled: bool = False) -> ContentSource:
        return ContentSource(
            key=data["key"],
            name=data["name"],
            source_type=data["source_type"],
            enabled=enabled,
            archived=False,
            priority=data.get("priority", 100),
            url_template=data["url_template"],
            query_params_json=json.dumps(data.get("query_params", {}), ensure_ascii=False, sort_keys=True),
            parse_mode=data["parse_mode"],
            value_path=data.get("value_path"),
            attribution_path=data.get("attribution_path"),
            categories_json=json.dumps(data.get("categories", []), ensure_ascii=False),
            timeout_seconds=data.get("timeout_seconds", 10),
            consecutive_failures=0,
        )

    @classmethod
    async def ensure_default_sources(cls, db: AsyncSession) -> list[ContentSource]:
        existing_result = await db.execute(select(ContentSource))
        existing = {source.key: source for source in existing_result.scalars().all()}
        created = []
        for definition in DEFAULT_CONTENT_SOURCES:
            if definition["key"] in existing:
                continue
            cls._validate_definition({**definition, "enabled": False}, creating=True)
            source = cls._make_source(definition, enabled=True)
            source.verified_config_hash = source.config_fingerprint
            db.add(source)
            created.append(source)
        if created:
            await db.commit()
            for source in created:
                await db.refresh(source)
        return created

    @classmethod
    async def create_source(
        cls,
        db: AsyncSession,
        data: dict,
        *,
        commit: bool = True,
    ) -> ContentSource:
        definition = dict(data)
        definition.setdefault("enabled", False)
        cls._validate_definition(definition, creating=True)
        duplicate = await db.execute(select(ContentSource).where(ContentSource.key == definition["key"]))
        if duplicate.scalar_one_or_none():
            raise ValueError("内容源 key 已存在")
        source = cls._make_source(definition, enabled=False)
        db.add(source)
        if commit:
            await db.commit()
            await db.refresh(source)
        else:
            await db.flush()
        return source

    @staticmethod
    async def get_source(db: AsyncSession, source_id: str) -> Optional[ContentSource]:
        return await db.get(ContentSource, source_id)

    @staticmethod
    async def list_sources(db: AsyncSession, include_archived: bool = False) -> list[ContentSource]:
        statement = select(ContentSource)
        if not include_archived:
            statement = statement.where(ContentSource.archived.is_(False))
        statement = statement.order_by(ContentSource.source_type, ContentSource.priority, ContentSource.name)
        result = await db.execute(statement)
        return list(result.scalars().all())

    @classmethod
    async def update_source(
        cls,
        db: AsyncSession,
        source_id: str,
        updates: dict,
        *,
        commit: bool = True,
    ) -> ContentSource:
        source = await cls.get_source(db, source_id)
        if not source:
            raise LookupError("内容源不存在")
        if source.archived:
            raise ValueError("已归档内容源不能编辑")
        if "key" in updates:
            raise ValueError("内容源 key 不可修改")
        unknown = set(updates) - cls.MUTABLE_FIELDS
        if unknown:
            raise ValueError("包含不支持的内容源字段")

        merged = cls._definition_from_source(source)
        merged.update(updates)
        cls._validate_definition(merged)

        config_changed = any(
            field in updates and updates[field] != cls._definition_from_source(source).get(field)
            for field in cls.CONFIG_FIELDS
        )
        if config_changed and updates.get("enabled") is True:
            raise ValueError("修改后的内容源必须测试成功后才能启用")

        for field, value in updates.items():
            if field == "query_params":
                source.query_params_json = json.dumps(value, ensure_ascii=False, sort_keys=True)
            elif field == "categories":
                source.categories_json = json.dumps(value, ensure_ascii=False)
            else:
                setattr(source, field, value)

        if config_changed:
            source.enabled = False
            source.verified_config_hash = None
        elif updates.get("enabled") is True and not source.config_verified:
            raise ValueError("内容源必须测试成功后才能启用")

        source.updated_at = cls._utc_now()
        if commit:
            await db.commit()
            await db.refresh(source)
        else:
            await db.flush()
        return source

    @staticmethod
    async def mark_failure(
        db: AsyncSession,
        source: ContentSource,
        error: str,
        latency_ms: Optional[int] = None,
    ) -> ContentSource:
        now = ContentSourceService._utc_now()
        source.last_checked_at = now
        source.last_failure_at = now
        source.latency_ms = latency_ms
        source.consecutive_failures = (source.consecutive_failures or 0) + 1
        source.last_error = str(error)[:500]
        source.updated_at = now
        await db.commit()
        return source

    @staticmethod
    async def mark_success(
        db: AsyncSession,
        source: ContentSource,
        latency_ms: Optional[int] = None,
    ) -> ContentSource:
        now = ContentSourceService._utc_now()
        source.last_checked_at = now
        source.last_success_at = now
        source.latency_ms = latency_ms
        source.consecutive_failures = 0
        source.last_error = None
        source.updated_at = now
        await db.commit()
        return source

    @classmethod
    async def test_source(
        cls,
        db: AsyncSession,
        source_id: str,
        *,
        fetcher: Optional[ContentSourceFetcher] = None,
    ) -> dict:
        source = await cls.get_source(db, source_id)
        if not source:
            raise LookupError("内容源不存在")
        fetcher = fetcher or ContentSourceFetcher()
        try:
            result = await fetcher.fetch(source)
        except ContentSourceFetchError as exc:
            await cls.mark_failure(db, source, str(exc))
            return {"success": False, "error": str(exc), "source": source}

        source.verified_config_hash = source.config_fingerprint
        await cls.mark_success(db, source, result.latency_ms)
        return {
            "success": True,
            "value_preview": (result.value or "")[:160],
            "latency_ms": result.latency_ms,
            "source": source,
        }

    @classmethod
    async def test_all(
        cls,
        db: AsyncSession,
        *,
        fetcher: Optional[ContentSourceFetcher] = None,
    ) -> list[dict]:
        sources = await cls.list_sources(db, include_archived=False)
        results = []
        for source in sources:
            results.append(await cls.test_source(db, source.id, fetcher=fetcher))
        return results

    @classmethod
    async def archive_source(cls, db: AsyncSession, source_id: str) -> ContentSource:
        source = await cls.get_source(db, source_id)
        if not source:
            raise LookupError("内容源不存在")
        source.archived = True
        source.enabled = False
        source.updated_at = cls._utc_now()
        await db.commit()
        await db.refresh(source)
        return source

    @classmethod
    async def update_priorities(cls, db: AsyncSession, items: list[dict]) -> list[ContentSource]:
        ids = [item.get("id") for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("优先级更新包含重复内容源")
        if any(not isinstance(item.get("priority"), int) or item["priority"] < 0 for item in items):
            raise ValueError("优先级必须是非负整数")

        sources = []
        try:
            for item in items:
                source = await cls.get_source(db, item["id"])
                if not source or source.archived:
                    raise LookupError("内容源不存在或已归档")
                source.priority = item["priority"]
                source.updated_at = cls._utc_now()
                sources.append(source)
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return sources

    @classmethod
    async def _candidates(
        cls,
        db: AsyncSession,
        source_type: str,
        requested_key: Optional[str],
    ) -> list[ContentSource]:
        result = await db.execute(
            select(ContentSource)
            .where(
                ContentSource.source_type == source_type,
                ContentSource.enabled.is_(True),
                ContentSource.archived.is_(False),
                ContentSource.consecutive_failures < 3,
            )
            .order_by(ContentSource.priority, ContentSource.name)
        )
        eligible = list(result.scalars().all())
        selected: list[ContentSource] = []

        if requested_key:
            requested = next((source for source in eligible if source.key == requested_key), None)
            if requested:
                selected.append(requested)

        healthy = [
            source
            for source in eligible
            if source not in selected
            and (source.consecutive_failures or 0) == 0
            and source.last_success_at is not None
        ]
        degraded_or_unknown = [
            source
            for source in eligible
            if source not in selected and source not in healthy
        ]
        return selected + healthy + degraded_or_unknown

    @classmethod
    async def fetch_content(
        cls,
        db: AsyncSession,
        *,
        source_type: str,
        requested_key: Optional[str] = None,
        category: Optional[str] = None,
        static_fallback: Optional[str] = None,
        fetcher: Optional[ContentSourceFetcher] = None,
    ) -> ContentResult:
        if source_type not in {"text", "image"}:
            raise ValueError("内容源类型必须是 text 或 image")
        fetcher = fetcher or ContentSourceFetcher()
        candidates = await cls._candidates(db, source_type, requested_key)

        for source in candidates:
            try:
                result = await fetcher.fetch(source, category=category)
            except ContentSourceRequestError:
                continue
            except ContentSourceFetchError as exc:
                await cls.mark_failure(db, source, str(exc))
                continue
            await cls.mark_success(db, source, result.latency_ms)
            return ContentResult(
                value=result.value,
                source_key=source.key,
                fallback=False,
                latency_ms=result.latency_ms,
            )

        return ContentResult(
            value=static_fallback,
            source_key=None,
            fallback=True,
            latency_ms=None,
        )
