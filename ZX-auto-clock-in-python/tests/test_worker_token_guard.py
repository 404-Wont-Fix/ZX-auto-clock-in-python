"""验证脱敏占位符 token 不会被当作真实 token 落库。"""

import pytest

from app.models.database import WorkerApi
from app.models.schemas import WorkerApiUpdate
from app.services.worker_api_service import WorkerApiService


def _worker(wid, url):
    return WorkerApi(
        id=wid, name=wid, url=url, token="real-uuid-token",
        enabled=True, available=True,
    )


@pytest.mark.asyncio
async def test_update_api_rejects_masked_placeholder_token(db_session):
    db_session.add(_worker("w1", "https://x.example"))
    await db_session.commit()

    # 前端占位符 "••••e681" 绝不能被落库，否则 worker 鉴权会坏
    with pytest.raises(ValueError):
        await WorkerApiService.update_api(
            db_session, "w1", WorkerApiUpdate(token="••••e681")
        )

    refreshed = await WorkerApiService.get_api_by_id(db_session, "w1")
    assert refreshed.token == "real-uuid-token"  # 原 token 保持不变


@pytest.mark.asyncio
async def test_update_api_accepts_real_token(db_session):
    db_session.add(_worker("w2", "https://y.example"))
    await db_session.commit()

    await WorkerApiService.update_api(
        db_session, "w2", WorkerApiUpdate(token="new-real-token-123")
    )

    refreshed = await WorkerApiService.get_api_by_id(db_session, "w2")
    assert refreshed.token == "new-real-token-123"
