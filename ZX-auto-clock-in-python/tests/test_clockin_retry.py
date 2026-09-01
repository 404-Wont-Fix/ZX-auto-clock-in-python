"""验证打卡重试：DB 配置读取 + 真正失败时自动重试整次调用。"""

from types import SimpleNamespace

import httpx
import pytest

from app.models.database import User, WorkerApi
from app.services import clockin_service as cs_module
from app.services.clockin_service import ClockinService
from app.services.image_service import ImageService


def _selection(value):
    return SimpleNamespace(value=value, source_key=None)


@pytest.mark.asyncio
async def test_config_int_reads_db_value(db_session):
    from app.models.database import Config

    db_session.add(Config(key="clockin_retry_count", value="5"))
    await db_session.commit()
    got = await ClockinService._config_int(db_session, "clockin_retry_count", 3)
    assert got == 5


@pytest.mark.asyncio
async def test_config_int_falls_back_when_missing(db_session):
    got = await ClockinService._config_int(db_session, "clockin_retry_count", 3)
    assert got == 3


@pytest.mark.asyncio
async def test_config_int_falls_back_on_invalid_value(db_session):
    from app.models.database import Config

    db_session.add(Config(key="clockin_retry_count", value="不是数字"))
    await db_session.commit()
    got = await ClockinService._config_int(db_session, "clockin_retry_count", 3)
    assert got == 3  # 非法值不崩，回退默认


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.is_success = True

    def json(self):
        return self._payload


class _FakeClient:
    """按顺序返回预设响应。注意：call_clockin_api 每次重试都会新建一个 AsyncClient，
    所以调用计数与响应队列必须是跨实例的全局状态。"""

    _queue = []
    _global_calls = 0

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kwargs):
        idx = min(_FakeClient._global_calls, len(_FakeClient._queue) - 1)
        resp = _FakeClient._queue[idx]
        _FakeClient._global_calls += 1
        return _FakeResponse(resp)

    @classmethod
    def reset(cls, responses):
        cls._queue = list(responses)
        cls._global_calls = 0


@pytest.mark.asyncio
async def test_call_clockin_api_retries_on_real_failure_then_succeeds(db_session, monkeypatch):
    """运动图片上传失败（真失败）时应触发重试，第二次成功则整体成功。"""
    user = User(id="u1", username="alice", password="p", enabled=True)
    worker = WorkerApi(
        id="w1", name="wk", url="https://example/clockin", token="t",
        enabled=True, available=True,
    )
    db_session.add_all([user, worker])
    await db_session.commit()

    # PoetryService 的选段方法（不依赖内容源服务的 DB 状态）
    from app.services.poetry_service import PoetryService
    monkeypatch.setattr(PoetryService, "get_daily_comment_selection", lambda *a, **k: _async(_selection("日精进")))
    monkeypatch.setattr(PoetryService, "get_sports_comment_selection", lambda *a, **k: _async(_selection("已运动")))
    monkeypatch.setattr(PoetryService, "get_sports_image_selection", lambda *a, **k: _async(_selection(None)))

    # 第一次：sports 真失败（图片上传失败）；第二次：全部成功
    _FakeClient.reset([
        {"results": {
            "home": {"success": True, "message": "首页签到成功"},
            "sports": {"success": False, "message": "图片上传失败: 校验失败"},
            "daily": {"success": True, "message": "日精进打卡成功"},
        }},
        {"results": {
            "home": {"success": True},
            "sports": {"success": True},
            "daily": {"success": True},
        }},
    ])
    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    result = await ClockinService.call_clockin_api(
        db_session, user, triggered_by="manual", retries=3, worker_api=worker
    )

    assert result["success"] is True
    assert _FakeClient._global_calls == 2  # 第一次失败 -> 重试一次 -> 成功


@pytest.mark.asyncio
async def test_call_clockin_api_no_retry_when_only_already_completed(db_session, monkeypatch):
    """只有“今日已完成”类失败时，归一化后即整体成功，不应重试。"""
    user = User(id="u2", username="bob", password="p", enabled=True)
    worker = WorkerApi(
        id="w2", name="wk", url="https://example/clockin", token="t",
        enabled=True, available=True,
    )
    db_session.add_all([user, worker])
    await db_session.commit()

    from app.services.poetry_service import PoetryService
    monkeypatch.setattr(PoetryService, "get_daily_comment_selection", lambda *a, **k: _async(_selection("日精进")))
    monkeypatch.setattr(PoetryService, "get_sports_comment_selection", lambda *a, **k: _async(_selection("已运动")))
    monkeypatch.setattr(PoetryService, "get_sports_image_selection", lambda *a, **k: _async(_selection(None)))

    _FakeClient.reset([{"results": {
        "home": {"success": True},
        "sports": {"success": False, "message": "今日已完成运动!"},
        "daily": {"success": False, "message": "今日已完成日精进!"},
    }}])
    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    result = await ClockinService.call_clockin_api(
        db_session, user, triggered_by="manual", retries=3, worker_api=worker
    )

    assert result["success"] is True          # 归一化后视为成功
    assert _FakeClient._global_calls == 1  # 没有重试


async def _async(value):
    """把同步值包成 awaitable，模拟 PoetryService 的 async 方法。"""
    return value


@pytest.mark.asyncio
async def test_call_clockin_api_converts_non_jpeg_image_before_send(db_session, monkeypatch):
    """非 JPEG 图片应经 ImageService 转码为 data URI 后再发给 worker（平台不支持 WebP）。"""
    user = User(id="u3", username="carol", password="p", enabled=True)
    worker = WorkerApi(
        id="w3", name="wk", url="https://example/clockin", token="t",
        enabled=True, available=True,
    )
    db_session.add_all([user, worker])
    await db_session.commit()

    from app.services.poetry_service import PoetryService
    monkeypatch.setattr(PoetryService, "get_daily_comment_selection", lambda *a, **k: _async(_selection("日精进")))
    monkeypatch.setattr(PoetryService, "get_sports_comment_selection", lambda *a, **k: _async(_selection("已运动")))
    monkeypatch.setattr(PoetryService, "get_sports_image_selection", lambda *a, **k: _async(_selection("https://img.example/x.webp")))

    converted = {}

    async def fake_process(url, enable_conversion=True):
        converted["called_with"] = url
        return "data:image/jpeg;base64,AAAA"

    monkeypatch.setattr(ImageService, "process_image_url", fake_process)

    captured = {}

    class _CapClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *e):
            return False

        async def post(self, url, **kwargs):
            captured["body"] = kwargs.get("json")
            return _FakeResponse({"results": {
                "home": {"success": True},
                "sports": {"success": True},
                "daily": {"success": True},
            }})

    monkeypatch.setattr(httpx, "AsyncClient", _CapClient)

    await ClockinService.call_clockin_api(
        db_session, user, triggered_by="manual", worker_api=worker
    )

    assert converted["called_with"] == "https://img.example/x.webp"
    # 发给 worker 的是转码后的 data URI，而不是原始 webp URL
    assert captured["body"]["options"]["sports_image_url"] == "data:image/jpeg;base64,AAAA"

