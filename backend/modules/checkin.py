"""签到模块 - 每日签到逻辑"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from models import Account, Platform
from utils.store import save_account
from modules.api_client import ApiClient

logger = logging.getLogger(__name__)

_CHECKIN_PKG_KEYWORD = "运营裂变包"


def _pkg_field(pkg, name: str, default=""):
    if isinstance(pkg, dict):
        return pkg.get(name, default)
    return getattr(pkg, name, default)


def _parse_cycle_start(cycle_start: str) -> datetime:
    """解析资源包 CycleStartTime"""
    s = (cycle_start or "").strip()
    if not s:
        return datetime.now()
    for fmt, n in (
        ("%Y-%m-%d %H:%M:%S", 19),
        ("%Y-%m-%dT%H:%M:%S", 19),
        ("%Y-%m-%d", 10),
    ):
        try:
            return datetime.strptime(s[:n], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return datetime.now()


def _count_streak_from_packages(packages: list) -> int:
    """从「运营裂变包」的 cycle_start 日期，自今天（或昨天）往前数连续天数。"""
    dates = set()
    for pkg in packages or []:
        name = str(_pkg_field(pkg, "package_name", "") or "")
        if _CHECKIN_PKG_KEYWORD not in name:
            continue
        cycle_start = str(_pkg_field(pkg, "cycle_start", "") or "")
        if len(cycle_start) >= 10:
            dates.add(cycle_start[:10])
    if not dates:
        return 0

    today = datetime.now().date()
    cursor = today
    if cursor.strftime("%Y-%m-%d") not in dates:
        cursor = today - timedelta(days=1)
        if cursor.strftime("%Y-%m-%d") not in dates:
            return 0

    streak = 0
    while cursor.strftime("%Y-%m-%d") in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def sync_checkin_from_packages(account: Account, packages: list) -> bool:
    """根据资源包推断今日是否已签到，并更新 account.checkin。

    Returns:
        True 表示检测到今日已签到包。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    month_prefix = datetime.now().strftime("%Y-%m")
    monthly_credits = 0
    today_start = None

    for pkg in packages or []:
        name = str(_pkg_field(pkg, "package_name", "") or "")
        if _CHECKIN_PKG_KEYWORD not in name:
            continue
        cycle_start = str(_pkg_field(pkg, "cycle_start", "") or "")
        capacity = _pkg_field(pkg, "capacity_size", 0) or 0
        if cycle_start.startswith(month_prefix):
            try:
                monthly_credits += int(float(capacity))
            except (TypeError, ValueError):
                pass
        if cycle_start.startswith(today):
            today_start = cycle_start

    account.checkin.total_credits = monthly_credits

    # 用资源包日期推算连续天数（比硬编码 1 更准；上游 checkin-status 仍会覆盖）
    computed_streak = _count_streak_from_packages(packages)
    if computed_streak > 0:
        account.checkin.streak_days = computed_streak
    elif today_start and account.checkin.streak_days == 0:
        account.checkin.streak_days = 1

    if not today_start:
        return False

    parsed = _parse_cycle_start(today_start)
    if not account.checkin.checked_today:
        account.checkin.last_checkin_time = parsed
    return True


def sync_checkin_from_status(account: Account, status) -> bool:
    """用上游 checkin-status 回写本地签到状态（streak 以服务端为准）。"""
    if status is None:
        return False
    today_checked = bool(getattr(status, "today_checked_in", False))
    if not today_checked:
        return False
    credit = int(getattr(status, "today_credit", 0) or getattr(status, "daily_credit", 0) or 0)
    streak = int(getattr(status, "streak_days", 0) or 0)
    if not account.checkin.checked_today:
        account.checkin.mark_checked_today(credit)
    if streak > 0:
        account.checkin.streak_days = streak
    if credit and not account.checkin.daily_credit:
        account.checkin.daily_credit = credit
    return True


class CheckinManager:
    """签到管理器"""

    def checkin_account(self, account: Account, proxy: Optional[str] = None) -> dict:
        """对单个账号执行签到

        优先使用 API Key (ck_xxx) 签到，更简单可靠；
        如果没有 API Key 则回退到 JWT 模式。

        Returns:
            {"success": True, "already": True} -- 今日已签到
            {"success": True, "credit": int, "streak_days": int} -- 刚签到成功
            {"success": False, "error": str} -- 签到失败
        """
        if account.api_key and account.api_key.startswith("ck_"):
            client = ApiClient.from_api_key(account.api_key, proxy=proxy)
        else:
            client = ApiClient.from_account(account, proxy=proxy)
        result = client.daily_checkin()

        if result["success"]:
            if result.get("already"):
                account.checkin.mark_checked_today()
                logger.info(f"今日已签到: {account.display_name}")
            else:
                credit = int(result.get("credit", 0) or 0)
                streak = int(result.get("streak_days", 0) or 0)
                account.checkin.mark_checked_today(credit)
                if streak > 0:
                    account.checkin.streak_days = streak
                logger.info(
                    f"签到成功: {account.display_name} +{credit}积分 "
                    f"连续{account.checkin.streak_days}天"
                )

            # 资源包：累计签到积分 + 连续天数兜底
            try:
                quota_result = client.get_user_resource()
                if quota_result["success"]:
                    packages = quota_result.get("packages", [])
                    self._update_checkin_stats_from_packages(account, packages)
                    try:
                        from modules.proxy_server import ProxyDatabase
                        db = ProxyDatabase.get_instance()
                        match_key = (
                            account.api_key
                            if (account.api_key and account.api_key.startswith("ck_"))
                            else account.auth_token
                        )
                        db.sync_quota_to_key(
                            api_key_or_token=match_key,
                            remaining_credits=quota_result.get("remaining_credits", 0),
                            total_credits=quota_result.get("total_credits", 0),
                            packages=packages,
                        )
                    except Exception:
                        pass
            except Exception:
                pass

            # checkin-status 为连续天数权威来源（含「今日已签到」无 streak 返回的情况）
            try:
                st = client.get_checkin_status()
                if st.get("success") and st.get("data") is not None:
                    sync_checkin_from_status(account, st["data"])
            except Exception as e:
                logger.debug(f"同步签到状态失败 {account.display_name}: {e}")

            # 把最终 streak 带回给调用方/前端进度
            result["streak_days"] = account.checkin.streak_days
            save_account(account)
        else:
            logger.warning(f"签到失败: {account.display_name} - {result.get('error')}")

        return result

    def _update_checkin_stats_from_packages(self, account: Account, packages: list):
        """从积分包数据推算签到统计并回写今日签到时间。"""
        sync_checkin_from_packages(account, packages)

    def checkin_all(self, accounts: list[Account], proxy: Optional[str] = None) -> dict:
        """批量签到所有账号"""
        results = {"success": 0, "failed": 0, "already": 0, "details": []}
        for account in accounts:
            if account.checkin.checked_today:
                pkgs = getattr(getattr(account, "quota", None), "packages", None) or []
                if pkgs:
                    try:
                        sync_checkin_from_packages(account, pkgs)
                        save_account(account)
                    except Exception:
                        pass
                results["already"] += 1
                results["details"].append({
                    "account": account.display_name,
                    "status": "already",
                    "streak": account.checkin.streak_days,
                    "message": f"今日已签到 (连续{account.checkin.streak_days}天)"
                })
                continue

            result = self.checkin_account(account, proxy=proxy)
            if result["success"]:
                results["success"] += 1
                results["details"].append({
                    "account": account.display_name,
                    "status": "success",
                    "streak": account.checkin.streak_days,
                    "rewards": account.checkin.rewards,
                })
            else:
                results["failed"] += 1
                results["details"].append({
                    "account": account.display_name,
                    "status": "failed",
                    "error": result.get("error", "未知错误")
                })

        logger.info(
            f"批量签到完成: 成功{results['success']}, 失败{results['failed']}, "
            f"已签到{results['already']}"
        )
        return results

    def checkin_platform(self, accounts: list[Account], platform: Platform, proxy: Optional[str] = None) -> dict:
        """对指定平台的所有账号签到"""
        platform_accounts = [a for a in accounts if a.platform == platform]
        return self.checkin_all(platform_accounts, proxy=proxy)

    @staticmethod
    def _sse(event: str, data: dict) -> str:
        """构造一条 SSE 消息"""
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def checkin_account_with_retry(
        self, account: Account, proxy: Optional[str] = None, retries: int = 3, on_event=None
    ) -> dict:
        """带重试的单个账号签到"""
        last_result = None
        for attempt in range(retries + 1):
            result = self.checkin_account(account, proxy=proxy)
            last_result = result
            if result.get("success"):
                result["retries"] = attempt
                return result
            if attempt < retries:
                logger.warning(
                    f"签到失败, 准备第 {attempt + 1} 次重试: "
                    f"{account.display_name} - {result.get('error')}"
                )
                if on_event:
                    on_event("retry", {
                        "account": account.display_name,
                        "uid": account.uid,
                        "attempt": attempt + 1,
                        "error": result.get("error", "未知错误"),
                    })
                time.sleep(1)
        last_result["retries"] = retries
        return last_result

    def checkin_all_stream(self, accounts: list[Account], proxy: Optional[str] = None):
        """批量签到（流式 SSE）"""
        total = len(accounts)
        yield self._sse("start", {"total": total})
        success = failed = already = 0

        for idx, account in enumerate(accounts, start=1):
            if account.checkin.checked_today:
                # 用本地资源包缓存校正连续天数（避免长期停在 1）
                pkgs = getattr(getattr(account, "quota", None), "packages", None) or []
                if pkgs:
                    try:
                        sync_checkin_from_packages(account, pkgs)
                        save_account(account)
                    except Exception:
                        pass
                already += 1
                yield self._sse("progress", {
                    "current": idx,
                    "total": total,
                    "account": account.display_name,
                    "uid": account.uid,
                    "status": "already",
                    "streak": account.checkin.streak_days,
                    "message": f"今日已签到 (连续 {account.checkin.streak_days} 天)",
                })
                continue

            yield self._sse("progress", {
                "current": idx,
                "total": total,
                "account": account.display_name,
                "uid": account.uid,
                "status": "checking",
            })

            retry_events = []
            result = self.checkin_account_with_retry(
                account,
                proxy=proxy,
                retries=3,
                on_event=lambda ev, d: retry_events.append((ev, d)),
            )
            for ev, d in retry_events:
                yield self._sse(ev, d)

            if result.get("success"):
                if result.get("already"):
                    already += 1
                    status = "already"
                else:
                    success += 1
                    status = "success"
                yield self._sse("progress", {
                    "current": idx,
                    "total": total,
                    "account": account.display_name,
                    "uid": account.uid,
                    "status": status,
                    "retries": result.get("retries", 0),
                    "streak": account.checkin.streak_days,
                })
            else:
                failed += 1
                yield self._sse("progress", {
                    "current": idx,
                    "total": total,
                    "account": account.display_name,
                    "uid": account.uid,
                    "status": "failed",
                    "retries": result.get("retries", 0),
                    "error": result.get("error", "未知错误"),
                })

        yield self._sse("done", {"success": success, "failed": failed, "already": already})
