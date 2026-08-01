from sqlalchemy import inspect

from app.models import database


def test_content_source_model_declares_managed_provider_fields():
    assert hasattr(database, "ContentSource"), "缺少 ContentSource 持久化模型"

    columns = {column.name for column in inspect(database.ContentSource).columns}

    assert {
        "id",
        "key",
        "name",
        "source_type",
        "enabled",
        "archived",
        "priority",
        "url_template",
        "query_params_json",
        "parse_mode",
        "value_path",
        "attribution_path",
        "categories_json",
        "timeout_seconds",
        "verified_config_hash",
        "last_checked_at",
        "last_success_at",
        "last_failure_at",
        "latency_ms",
        "consecutive_failures",
        "last_error",
    }.issubset(columns)
