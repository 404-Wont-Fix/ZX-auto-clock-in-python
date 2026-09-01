import asyncio

import httpx
import pytest

from app.models.database import ContentSource
from app.services import content_source_service as content_source_module
from app.services.content_source_service import (
    ContentSourceFetchError,
    ContentSourceFetcher,
    ContentSourceSecurityError,
)


PUBLIC_IP = "93.184.216.34"


async def public_resolver(hostname: str):
    return [PUBLIC_IP]


def make_source(**overrides):
    values = {
        "key": "test-source",
        "name": "测试源",
        "source_type": "text",
        "enabled": False,
        "archived": False,
        "priority": 10,
        "url_template": "https://content.example/api",
        "query_params_json": "{}",
        "parse_mode": "json_text",
        "value_path": "data.quote",
        "attribution_path": None,
        "categories_json": "[]",
        "timeout_seconds": 10,
    }
    values.update(overrides)
    return ContentSource(**values)


@pytest.mark.asyncio
async def test_json_text_uses_dot_path_and_attribution():
    async def handler(request: httpx.Request):
        return httpx.Response(
            200,
            json={"data": {"quote": "山高水长", "from": "无名氏"}},
            request=request,
        )

    source = make_source(attribution_path="data.from")
    fetcher = ContentSourceFetcher(
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )

    result = await fetcher.fetch(source)

    assert result.value == "山高水长 —— 无名氏"
    assert result.attribution == "无名氏"
    assert result.final_url == "https://content.example/api"


@pytest.mark.asyncio
async def test_plain_text_strips_surrounding_whitespace():
    async def handler(request: httpx.Request):
        return httpx.Response(200, text="  今天也要认真生活。\n", request=request)

    source = make_source(parse_mode="plain_text", value_path=None)
    fetcher = ContentSourceFetcher(
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )

    result = await fetcher.fetch(source)

    assert result.value == "今天也要认真生活。"


@pytest.mark.asyncio
async def test_json_image_resolves_relative_https_url():
    async def handler(request: httpx.Request):
        return httpx.Response(
            200,
            json={"images": [{"url": "/wallpaper.jpg"}]},
            request=request,
        )

    source = make_source(
        source_type="image",
        parse_mode="json_image",
        value_path="images.0.url",
    )
    fetcher = ContentSourceFetcher(
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )

    result = await fetcher.fetch(source)

    assert result.value == "https://content.example/wallpaper.jpg"


class BoundedImageStream(httpx.AsyncByteStream):
    def __init__(self):
        self.chunks_requested = 0

    async def __aiter__(self):
        self.chunks_requested += 1
        yield b"\xff\xd8\xff" + (b"x" * 1021)
        self.chunks_requested += 1
        raise AssertionError("redirect_image 只应读取有限图片前缀")


class FailIfImageBodyRead(httpx.AsyncByteStream):
    async def __aiter__(self):
        raise AssertionError("压缩图片响应必须在读取正文前拒绝")
        yield b""


@pytest.mark.asyncio
async def test_redirect_image_checks_headers_and_only_reads_a_bounded_prefix():
    image_stream = BoundedImageStream()

    async def handler(request: httpx.Request):
        if request.url.path == "/start":
            return httpx.Response(
                302,
                headers={"location": "https://cdn.example/photo.webp"},
                request=request,
            )
        return httpx.Response(
            200,
            headers={"content-type": "image/jpeg"},
            stream=image_stream,
            request=request,
        )

    source = make_source(
        source_type="image",
        parse_mode="redirect_image",
        value_path=None,
        url_template="https://content.example/start",
    )
    fetcher = ContentSourceFetcher(
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )

    result = await fetcher.fetch(source)

    assert result.value == "https://cdn.example/photo.webp"
    assert result.content_type == "image/jpeg"
    assert image_stream.chunks_requested == 1


@pytest.mark.asyncio
async def test_redirect_image_rejects_an_empty_image_response():
    async def handler(request: httpx.Request):
        return httpx.Response(
            200,
            headers={"content-type": "image/jpeg"},
            content=b"",
            request=request,
        )

    source = make_source(
        source_type="image",
        parse_mode="redirect_image",
        value_path=None,
    )
    fetcher = ContentSourceFetcher(
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )

    with pytest.raises(ContentSourceFetchError, match="图片响应为空"):
        await fetcher.fetch(source)


@pytest.mark.asyncio
async def test_redirect_image_rejects_compressed_transfer_before_reading_body():
    async def handler(request: httpx.Request):
        return httpx.Response(
            200,
            headers={
                "content-type": "image/jpeg",
                "content-encoding": "gzip",
            },
            stream=FailIfImageBodyRead(),
            request=request,
        )

    source = make_source(
        source_type="image",
        parse_mode="redirect_image",
        value_path=None,
    )
    fetcher = ContentSourceFetcher(
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )

    with pytest.raises(ContentSourceFetchError, match="图片响应禁止压缩传输"):
        await fetcher.fetch(source)


@pytest.mark.asyncio
async def test_category_template_accepts_only_configured_values():
    requests = []

    async def handler(request: httpx.Request):
        requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "image/jpeg"},
            content=b"\xff\xd8\xff",
            request=request,
        )

    source = make_source(
        source_type="image",
        parse_mode="redirect_image",
        value_path=None,
        url_template="https://content.example/{category}/",
        categories_json='["pc", "mobile"]',
    )
    fetcher = ContentSourceFetcher(
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )

    result = await fetcher.fetch(source, category="pc")

    assert result.value == "https://content.example/pc/"
    assert requests[0].url.path == "/pc/"

    with pytest.raises(ContentSourceFetchError, match="分类"):
        await fetcher.fetch(source, category="private")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.8",
        "169.254.169.254",
        "192.0.2.1",
        "224.0.0.1",
        "239.255.255.250",
        "::1",
        "fc00::1",
        "ff02::1",
        "ff0e::1",
    ],
)
async def test_ssrf_blocks_non_public_resolved_addresses(address):
    async def resolver(_hostname: str):
        return [address]

    called = False

    async def handler(request: httpx.Request):
        nonlocal called
        called = True
        return httpx.Response(200, json={"data": {"quote": "不应请求"}}, request=request)

    fetcher = ContentSourceFetcher(
        transport=httpx.MockTransport(handler),
        resolver=resolver,
    )

    with pytest.raises(ContentSourceSecurityError):
        await fetcher.fetch(make_source())

    assert called is False


@pytest.mark.asyncio
async def test_ssrf_revalidates_every_redirect_before_requesting_target():
    requested_hosts = []

    async def resolver(hostname: str):
        if hostname == "private.example":
            return ["127.0.0.1"]
        return [PUBLIC_IP]

    async def handler(request: httpx.Request):
        requested_hosts.append(request.url.host)
        return httpx.Response(
            302,
            headers={"location": "https://private.example/secrets"},
            request=request,
        )

    fetcher = ContentSourceFetcher(
        transport=httpx.MockTransport(handler),
        resolver=resolver,
    )

    with pytest.raises(ContentSourceSecurityError):
        await fetcher.fetch(make_source())

    assert requested_hosts == ["content.example"]


@pytest.mark.asyncio
async def test_fetch_binds_the_validated_address_to_the_transport_request():
    captured = []

    async def handler(request: httpx.Request):
        captured.append(request)
        return httpx.Response(200, text="已绑定", request=request)

    source = make_source(parse_mode="plain_text", value_path=None)
    fetcher = ContentSourceFetcher(
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )

    result = await fetcher.fetch(source)

    assert result.value == "已绑定"
    assert captured[0].extensions["content_source_connect_ip"] == PUBLIC_IP
    assert captured[0].headers["accept-encoding"] == "identity"


@pytest.mark.asyncio
async def test_fetch_retries_the_next_validated_address_after_connect_failure():
    ipv6_address = "2606:2800:220:1:248:1893:25c8:1946"
    attempts = []

    async def resolver(_hostname: str):
        return [ipv6_address, PUBLIC_IP]

    async def handler(request: httpx.Request):
        address = request.extensions["content_source_connect_ip"]
        attempts.append(address)
        if address == ipv6_address:
            raise httpx.ConnectError("IPv6 endpoint unavailable", request=request)
        return httpx.Response(200, text="地址回退成功", request=request)

    source = make_source(parse_mode="plain_text", value_path=None)
    fetcher = ContentSourceFetcher(
        transport=httpx.MockTransport(handler),
        resolver=resolver,
    )

    result = await fetcher.fetch(source)

    assert result.value == "地址回退成功"
    assert attempts == [ipv6_address, PUBLIC_IP]


@pytest.mark.asyncio
async def test_pinned_transport_connects_to_validated_ip_with_original_host_and_sni():
    transport_type = getattr(content_source_module, "_PinnedAsyncHTTPTransport", None)
    assert transport_type is not None, "内容源默认传输层必须绑定已校验 IP"

    class CapturingTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.request = None

        async def handle_async_request(self, request: httpx.Request):
            self.request = request
            return httpx.Response(200, request=request)

    delegate = CapturingTransport()
    transport = transport_type(delegate=delegate)
    request = httpx.Request(
        "GET",
        "https://content.example:8443/quote",
        extensions={"content_source_connect_ip": PUBLIC_IP},
    )

    await transport.handle_async_request(request)

    assert delegate.request.url.host == PUBLIC_IP
    assert delegate.request.url.port == 8443
    assert delegate.request.headers["host"] == "content.example:8443"
    assert delegate.request.extensions["sni_hostname"] == "content.example"
    assert isinstance(delegate.request.stream, httpx.AsyncByteStream)


@pytest.mark.asyncio
async def test_rejects_http_and_credentials_in_url():
    fetcher = ContentSourceFetcher(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)),
        resolver=public_resolver,
    )

    with pytest.raises(ContentSourceSecurityError):
        await fetcher.fetch(make_source(url_template="http://content.example/api"))

    with pytest.raises(ContentSourceSecurityError):
        await fetcher.fetch(make_source(url_template="https://user:pass@content.example/api"))


@pytest.mark.asyncio
async def test_text_response_is_limited_to_64_kib():
    async def handler(request: httpx.Request):
        return httpx.Response(200, content=b"x" * (64 * 1024 + 1), request=request)

    source = make_source(parse_mode="plain_text", value_path=None)
    fetcher = ContentSourceFetcher(
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )

    with pytest.raises(ContentSourceFetchError, match="64 KiB"):
        await fetcher.fetch(source)


class FailIfOversizedBodyIsRead(httpx.AsyncByteStream):
    async def __aiter__(self):
        raise AssertionError("声明超限的正文不应进入读取循环")
        yield b""


@pytest.mark.asyncio
async def test_declared_oversized_text_response_is_rejected_before_body_read():
    async def handler(request: httpx.Request):
        return httpx.Response(
            200,
            headers={"content-length": str(64 * 1024 + 1)},
            stream=FailIfOversizedBodyIsRead(),
            request=request,
        )

    source = make_source(parse_mode="plain_text", value_path=None)
    fetcher = ContentSourceFetcher(
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )

    with pytest.raises(ContentSourceFetchError, match="64 KiB"):
        await fetcher.fetch(source)


@pytest.mark.asyncio
async def test_text_response_rejects_unrequested_content_encoding():
    async def handler(request: httpx.Request):
        return httpx.Response(
            200,
            headers={"content-encoding": "gzip"},
            stream=FailIfOversizedBodyIsRead(),
            request=request,
        )

    source = make_source(parse_mode="plain_text", value_path=None)
    fetcher = ContentSourceFetcher(
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )

    with pytest.raises(ContentSourceFetchError, match="压缩"):
        await fetcher.fetch(source)


@pytest.mark.asyncio
async def test_timeout_is_reported_as_fetch_error():
    async def handler(request: httpx.Request):
        raise httpx.ReadTimeout("too slow", request=request)

    fetcher = ContentSourceFetcher(
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )

    with pytest.raises(ContentSourceFetchError, match="超时"):
        await fetcher.fetch(make_source(timeout_seconds=2))


@pytest.mark.asyncio
async def test_source_timeout_is_one_budget_for_dns_and_all_address_attempts():
    alternate_public_ip = "1.1.1.1"

    async def slow_resolver(_hostname: str):
        await asyncio.sleep(0.75)
        return [PUBLIC_IP, alternate_public_ip]

    async def slow_failure(request: httpx.Request):
        await asyncio.sleep(0.75)
        raise httpx.ConnectError("endpoint unavailable", request=request)

    fetcher = ContentSourceFetcher(
        transport=httpx.MockTransport(slow_failure),
        resolver=slow_resolver,
    )

    with pytest.raises(ContentSourceFetchError, match="超时"):
        await fetcher.fetch(make_source(parse_mode="plain_text", value_path=None, timeout_seconds=2))


@pytest.mark.asyncio
async def test_address_fallback_attempts_are_bounded_per_hostname():
    attempted_addresses = []
    addresses = [
        "1.0.0.1",
        "1.1.1.1",
        "8.8.4.4",
        "8.8.8.8",
        "9.9.9.9",
        "208.67.222.222",
    ]

    async def many_public_addresses(_hostname: str):
        return addresses

    async def unavailable(request: httpx.Request):
        attempted_addresses.append(request.extensions["content_source_connect_ip"])
        raise httpx.ConnectError("endpoint unavailable", request=request)

    fetcher = ContentSourceFetcher(
        transport=httpx.MockTransport(unavailable),
        resolver=many_public_addresses,
    )

    with pytest.raises(ContentSourceFetchError, match="连接失败"):
        await fetcher.fetch(make_source(parse_mode="plain_text", value_path=None))

    assert len(attempted_addresses) == 4


@pytest.mark.asyncio
async def test_redirect_limit_is_three():
    calls = 0

    async def handler(request: httpx.Request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            302,
            headers={"location": f"https://content.example/redirect/{calls}"},
            request=request,
        )

    fetcher = ContentSourceFetcher(
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )

    with pytest.raises(ContentSourceFetchError, match="重定向"):
        await fetcher.fetch(make_source())

    assert calls == 4
