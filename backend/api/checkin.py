"""签到 API - 单账号/批量签到、签到状态查询、定时签到配置"""

import logging
import threading
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from utils.store import load_accounts, save_account, load_setting, save_setting
from utils.network import get_outbound_proxy
from modules.api_client import ApiClient
from modules.checkin import CheckinManager

router = APIRouter()
logger = logging.getLogger(__name__)

_manager = CheckinManager()

# 定时签到配置变更时置位，调度线程据此重新计算下次时间
_schedule_reload = threading.Event()

_DEFAULT_HOUR = 0
_DEFAULT_MINUTE = 30


def get_schedule_config() -> dict:
    """读取定时签到配置（存 MySQL settings）"""
    enabled_raw = load_setting("schedule_checkin_enabled", "true").strip().lower()
    enabled = enabled_raw in ("1", "true", "yes", "on")
    try:
        hour = int(load_setting("schedule_checkin_hour", str(_DEFAULT_HOUR)) or _DEFAULT_HOUR)
    except ValueError:
        hour = _DEFAULT_HOUR
    try:
        minute = int(load_setting("schedule_checkin_minute", str(_DEFAULT_MINUTE)) or _DEFAULT_MINUTE)
    except ValueError:
        minute = _DEFAULT_MINUTE
    hour = max(0, min(23, hour))
    minute = max(0, min(59, minute))
    return {
        "enabled": enabled,
        "hour": hour,
        "minute": minute,
        "time": f"{hour:02d}:{minute:02d}",
    }


def notify_schedule_reload():
    _schedule_reload.set()


def wait_schedule_interrupt(stop_event: threading.Event, timeout: float) -> str:
    """等待：stop / reload / timeout。返回 'stop' | 'reload' | 'timeout'。"""
    import time as _time

    deadline = _time.monotonic() + max(0.0, timeout)
    while True:
        if stop_event.is_set():
            return "stop"
        remain = deadline - _time.monotonic()
        if remain <= 0:
            return "timeout"
        if _schedule_reload.wait(min(1.0, remain)):
            _schedule_reload.clear()
            return "reload"


class ScheduleConfigUpdate(BaseModel):
    enabled: bool = True
    hour: int = Field(_DEFAULT_HOUR, ge=0, le=23)
    minute: int = Field(_DEFAULT_MINUTE, ge=0, le=59)


@router.get("/schedule")
def get_schedule():
    """获取定时签到配置与下次预计执行时间"""
    from datetime import datetime, timedelta

    cfg = get_schedule_config()
    next_run = None
    if cfg["enabled"]:
        now = datetime.now()
        nxt = now.replace(hour=cfg["hour"], minute=cfg["minute"], second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        next_run = nxt.isoformat(timespec="seconds")
    return {**cfg, "next_run": next_run}


@router.put("/schedule")
def update_schedule(body: ScheduleConfigUpdate):
    """更新定时签到配置（立即生效，调度线程重新计算）"""
    save_setting("schedule_checkin_enabled", "true" if body.enabled else "false")
    save_setting("schedule_checkin_hour", str(body.hour))
    save_setting("schedule_checkin_minute", str(body.minute))
    notify_schedule_reload()
    logger.info(
        f"[定时签到] 配置已更新: enabled={body.enabled} "
        f"{body.hour:02d}:{body.minute:02d}"
    )
    return get_schedule()


@router.get("/status/{uid}")
def get_checkin_status(uid: str):
    """获取指定账号的签到状态"""
    accounts = load_accounts()
    account = next((a for a in accounts if a.uid == uid), None)
    if not account:
        raise HTTPException(404, "账号不存在")

    proxy = get_outbound_proxy()
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


@router.post("/stream")
def checkin_all_stream():
    """批量签到（流式实时进度）

    以 SSE（text/event-stream）形式逐个推送签到进度，失败自动重试 3 次。
    前端使用 fetch 读取 ReadableStream，无超时限制。
    """
    proxy = get_outbound_proxy()
    accounts = load_accounts()
    return StreamingResponse(
        _manager.checkin_all_stream(accounts, proxy=proxy),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/{uid}")
def checkin_account(uid: str):
    """对指定账号执行签到"""
    accounts = load_accounts()
    account = next((a for a in accounts if a.uid == uid), None)
    if not account:
        raise HTTPException(404, "账号不存在")

    proxy = get_outbound_proxy()
    result = _manager.checkin_account(account, proxy=proxy)
    return result


@router.post("")
def checkin_all():
    """批量签到所有账号"""
    accounts = load_accounts()
    if not accounts:
        return {"success": 0, "failed": 0, "already": 0, "details": []}

    proxy = get_outbound_proxy()
    result = _manager.checkin_all(accounts, proxy=proxy)
    return result
