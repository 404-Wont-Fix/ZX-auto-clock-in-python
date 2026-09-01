import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from scripts.probe_content_sources import evaluate_probe_results, resolve_via_doh


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_live_probe_passes_when_each_content_type_has_a_healthy_fallback():
    results = [
        {"key": "text-ok", "source_type": "text", "success": True},
        {"key": "text-down", "source_type": "text", "success": False},
        {"key": "image-ok", "source_type": "image", "success": True},
    ]

    summary = evaluate_probe_results(results, strict=False)

    assert summary["passed"] is True
    assert summary["healthy_by_type"] == {"text": 1, "image": 1}
    assert summary["failed_keys"] == ["text-down"]


def test_live_probe_fails_without_a_healthy_type_or_when_strict():
    results = [
        {"key": "text-ok", "source_type": "text", "success": True},
        {"key": "image-down", "source_type": "image", "success": False},
    ]

    assert evaluate_probe_results(results, strict=False)["passed"] is False

    redundant_results = results + [
        {"key": "image-ok", "source_type": "image", "success": True},
    ]
    assert evaluate_probe_results(redundant_results, strict=False)["passed"] is True
    assert evaluate_probe_results(redundant_results, strict=True)["passed"] is False


def test_live_probe_supports_direct_script_entrypoint_without_pythonpath():
    result = subprocess.run(
        [sys.executable, "scripts/probe_content_sources.py", "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--strict" in result.stdout
    assert "--doh-resolver" in result.stdout


@pytest.mark.asyncio
async def test_doh_resolver_returns_only_a_and_aaaa_answers():
    def handler(request: httpx.Request) -> httpx.Response:
        record_type = request.url.params["type"]
        answers = {
            "A": [
                {"type": 5, "data": "edge.example.com."},
                {"type": 1, "data": "93.184.216.34"},
            ],
            "AAAA": [{"type": 28, "data": "2606:2800:220:1:248:1893:25c8:1946"}],
        }
        return httpx.Response(200, json={"Status": 0, "Answer": answers[record_type]})

    addresses = await resolve_via_doh(
        "example.com",
        transport=httpx.MockTransport(handler),
    )

    assert addresses == ["2606:2800:220:1:248:1893:25c8:1946", "93.184.216.34"]
