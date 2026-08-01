"""独立探测默认公网内容源；不访问 Worker 或真实打卡账号。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.content_source_service import (
    DEFAULT_CONTENT_SOURCES,
    ContentSourceFetchError,
    ContentSourceFetcher,
    ContentSourceService,
)


DOH_ENDPOINT = "https://cloudflare-dns.com/dns-query"


async def resolve_via_doh(
    hostname: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[str]:
    """通过固定公网 DoH 端点解析，供透明 DNS 映射环境中的发布探测使用。"""

    addresses: set[str] = set()
    async with httpx.AsyncClient(transport=transport, timeout=10) as client:
        for record_type in ("A", "AAAA"):
            response = await client.get(
                DOH_ENDPOINT,
                params={"name": hostname, "type": record_type},
                headers={"Accept": "application/dns-json"},
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("Status") != 0:
                raise OSError(f"公共 DNS 解析失败: {hostname}")
            addresses.update(
                str(answer["data"])
                for answer in payload.get("Answer", [])
                if answer.get("type") in {1, 28} and answer.get("data")
            )
    return sorted(addresses)


def evaluate_probe_results(results: list[dict[str, Any]], *, strict: bool) -> dict[str, Any]:
    healthy_by_type = {
        source_type: sum(
            1
            for result in results
            if result.get("source_type") == source_type and result.get("success") is True
        )
        for source_type in ("text", "image")
    }
    failed_keys = [
        str(result.get("key"))
        for result in results
        if result.get("success") is not True
    ]
    has_fallback_per_type = all(healthy_by_type[source_type] > 0 for source_type in healthy_by_type)
    return {
        "passed": has_fallback_per_type and (not strict or not failed_keys),
        "strict": strict,
        "healthy_by_type": healthy_by_type,
        "failed_keys": failed_keys,
        "total": len(results),
    }


async def probe_definition(definition: dict[str, Any], *, resolver=None) -> dict[str, Any]:
    source = ContentSourceService._make_source(definition, enabled=True)
    category = source.categories[0] if "{category}" in source.url_template else None
    try:
        fetched = await ContentSourceFetcher(resolver=resolver).fetch(source, category=category)
    except ContentSourceFetchError as exc:
        return {
            "key": source.key,
            "name": source.name,
            "source_type": source.source_type,
            "success": False,
            "error": str(exc),
        }
    except Exception as exc:  # pragma: no cover - 发布环境的未知网络/SSL 异常
        return {
            "key": source.key,
            "name": source.name,
            "source_type": source.source_type,
            "success": False,
            "error": f"unexpected {type(exc).__name__}",
        }
    return {
        "key": source.key,
        "name": source.name,
        "source_type": source.source_type,
        "success": True,
        "latency_ms": fetched.latency_ms,
        "final_url": fetched.final_url,
        "value_preview": (fetched.value or "")[:120],
    }


async def run_probe(*, strict: bool, resolver=None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    results = list(
        await asyncio.gather(
            *(
                probe_definition(dict(definition), resolver=resolver)
                for definition in DEFAULT_CONTENT_SOURCES
            )
        )
    )
    return results, evaluate_probe_results(results, strict=strict)


def main() -> int:
    parser = argparse.ArgumentParser(description="探测 ZX Admin 默认文字/图片内容源")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="任一默认源失败即返回非零；默认只要求文字和图片各有至少一个健康来源",
    )
    parser.add_argument(
        "--doh-resolver",
        action="store_true",
        help="使用固定公网 DoH 解析器；仅用于系统 DNS 被透明映射的发布探测环境",
    )
    args = parser.parse_args()
    resolver = resolve_via_doh if args.doh_resolver else None
    results, summary = asyncio.run(run_probe(strict=args.strict, resolver=resolver))
    print(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
