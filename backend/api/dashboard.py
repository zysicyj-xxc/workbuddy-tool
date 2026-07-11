"""仪表盘 API - 汇总统计数据"""

import logging
from fastapi import APIRouter

from utils.store import load_accounts
from modules.proxy_server import ProxyDatabase

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/dashboard")
def get_dashboard():
    """获取仪表盘统计数据"""
    accounts = load_accounts()
    active_count = sum(1 for a in accounts if a.status.value == "active")
    exhausted_count = sum(1 for a in accounts if a.status.value == "quota_exhausted")
    error_count = sum(1 for a in accounts if a.status.value == "error")

    # 签到统计（与 Account.checkin.checked_today 同一套本地日逻辑）
    checked_today = sum(1 for a in accounts if a.checkin.checked_today)

    # 代理统计
    db = ProxyDatabase.get_instance()
    upstream_keys = db.get_upstream_keys()
    sub_keys = db.get_sub_api_keys()
    active_upstream = sum(1 for k in upstream_keys if k.get("status") == "active")
    usage = db.get_usage_summary()

    return {
        "accounts": {
            "total": len(accounts),
            "active": active_count,
            "exhausted": exhausted_count,
            "error": error_count,
        },
        "checkin": {
            "checked_today": checked_today,
            "total": len(accounts),
        },
        "proxy": {
            "upstream_keys": len(upstream_keys),
            "active_upstream": active_upstream,
            "sub_keys": len(sub_keys),
            "total_requests": usage.get("total_requests", 0),
            "total_prompt_tokens": usage.get("total_prompt_tokens", 0),
            "total_completion_tokens": usage.get("total_completion_tokens", 0),
        },
    }
