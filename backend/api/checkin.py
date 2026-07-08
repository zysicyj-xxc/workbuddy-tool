"""签到 API - 单账号/批量签到、签到状态查询"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from utils.store import load_accounts, save_account, load_setting
from modules.api_client import ApiClient
from modules.checkin import CheckinManager

router = APIRouter()
logger = logging.getLogger(__name__)

_manager = CheckinManager()


@router.get("/status/{uid}")
def get_checkin_status(uid: str):
    """获取指定账号的签到状态"""
    accounts = load_accounts()
    account = next((a for a in accounts if a.uid == uid), None)
    if not account:
        raise HTTPException(404, "账号不存在")

    proxy = load_setting("proxy", "") or None
    client = ApiClient.from_api_key(account.api_key) if account.api_key.startswith("ck_") else ApiClient.from_account(account, proxy=proxy)
    result = client.get_checkin_status()

    if not result.get("success"):
        raise HTTPException(400, result.get("error", "获取签到状态失败"))

    status = result["data"]
    return {
        "active": status.active,
        "today_checked_in": status.today_checked_in,
        "streak_days": status.streak_days,
        "daily_credit": status.daily_credit,
        "today_credit": status.today_credit,
        "is_streak_day": status.is_streak_day,
        "week_checkin_days": status.week_checkin_days,
        "week_progress": status.week_progress,
        "total_credits": status.total_credits,
        "activity_name": status.activity_name,
    }


@router.post("/{uid}")
def checkin_account(uid: str):
    """对指定账号执行签到"""
    accounts = load_accounts()
    account = next((a for a in accounts if a.uid == uid), None)
    if not account:
        raise HTTPException(404, "账号不存在")

    proxy = load_setting("proxy", "") or None
    result = _manager.checkin_account(account, proxy=proxy)
    return result


@router.post("")
def checkin_all():
    """批量签到所有账号"""
    accounts = load_accounts()
    if not accounts:
        return {"success": 0, "failed": 0, "already": 0, "details": []}

    proxy = load_setting("proxy", "") or None
    result = _manager.checkin_all(accounts, proxy=proxy)
    return result
