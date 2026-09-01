"""验证“今日已完成”类重复打卡结果被正确视为成功。"""

from app.services.clockin_service import ClockinService


def test_normalize_flips_already_completed_failure_to_success():
    details = {
        "home": {"success": True, "message": "首页签到成功"},
        "sports": {"success": False, "message": "今日已完成运动!"},
        "daily": {"success": False, "message": "今日已完成日精进!"},
    }

    ClockinService._normalize_completed_types(details)

    assert details["home"]["success"] is True
    # “今日已完成” -> 视为成功
    assert details["sports"]["success"] is True
    assert "视为成功" in details["sports"]["message"]
    assert details["daily"]["success"] is True
    assert "视为成功" in details["daily"]["message"]


def test_normalize_leaves_real_failures_alone():
    """真实的失败（如图片上传失败）不应被改成成功。"""
    details = {
        "home": {"success": True, "message": "首页签到成功"},
        "sports": {
            "success": False,
            "message": "图片上传失败: 文件内容与扩展名不匹配（图片验证失败）",
        },
        "daily": {"success": False, "message": "今日已完成日精进!"},
    }

    ClockinService._normalize_completed_types(details)

    assert details["sports"]["success"] is False  # 真失败保留
    assert "视为成功" not in details["sports"]["message"]
    assert details["daily"]["success"] is True  # 重复打卡视为成功


def test_already_completed_only_yields_overall_success():
    """只有“今日已完成”类失败时，整体应判为成功。"""
    details = {
        "home": {"success": True, "message": "首页签到成功"},
        "sports": {"success": False, "message": "今日已完成运动!"},
        "daily": {"success": False, "message": "今日已完成日精进!"},
    }
    ClockinService._normalize_completed_types(details)
    assert ClockinService._calculate_overall_success(details) is True


def test_real_failure_still_yields_overall_failure():
    details = {
        "home": {"success": True, "message": "首页签到成功"},
        "sports": {"success": False, "message": "图片上传失败: 校验失败"},
        "daily": {"success": False, "message": "今日已完成日精进!"},
    }
    ClockinService._normalize_completed_types(details)
    assert ClockinService._calculate_overall_success(details) is False


def test_idempotent_message_not_double_annotated():
    details = {"daily": {"success": False, "message": "今日已完成日精进!"}}
    ClockinService._normalize_completed_types(details)
    once = details["daily"]["message"]
    ClockinService._normalize_completed_types(details)  # 再跑一次不应重复标注
    assert details["daily"]["message"] == once
