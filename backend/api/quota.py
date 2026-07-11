"""积分/配额 API - 查询积分、刷新配额、资源包汇总"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from utils.store import load_accounts, save_account
from utils.network import get_outbound_proxy
from modules.api_client import ApiClient

router = APIRouter()
logger = logging.getLogger(__name__)


def _parse_cycle_end_ts(cycle_end: str):
    """解析过期时间字符串为时间戳，失败返回 None"""
    if not cycle_end:
        return None
    try:
        if "T" in cycle_end:
            dt = datetime.fromisoformat(cycle_end.replace("Z", "+00:00"))
            return dt.timestamp()
        try:
            return float(cycle_end)
        except ValueError:
            dt = datetime.strptime(cycle_end, "%Y-%m-%d %H:%M:%S")
            return dt.timestamp()
    except (ValueError, TypeError):
        return None


def _pkg_to_dict(pkg) -> dict:
    """ResourcePackage 或 dict -> 可序列化/可返回的统一 dict"""
    if isinstance(pkg, dict):
        package_type = str(pkg.get("package_type", "") or "")
        type_label = pkg.get("type_label")
        if not type_label:
            type_label = {"1": "免费", "2": "付费", "4": "体验"}.get(package_type, package_type)
        usage = pkg.get("usage_percentage")
        remain_pct = pkg.get("remain_percentage")
        cycle_size = float(pkg.get("cycle_size", 0) or 0)
        cycle_remain = float(pkg.get("cycle_remain", 0) or 0)
        if usage is None and cycle_size > 0:
            usage = ((cycle_size - cycle_remain) / cycle_size) * 100
        if remain_pct is None:
            remain_pct = 100.0 - float(usage or 0)
        is_exhausted = pkg.get("is_exhausted")
        if is_exhausted is None:
            is_exhausted = cycle_remain <= 0
        return {
            "package_name": pkg.get("package_name", "") or "",
            "package_type": package_type,
            "type_label": type_label,
            "capacity_size": float(pkg.get("capacity_size", 0) or 0),
            "capacity_remain": float(pkg.get("capacity_remain", 0) or 0),
            "capacity_used": float(pkg.get("capacity_used", 0) or 0),
            "cycle_size": cycle_size,
            "cycle_remain": cycle_remain,
            "usage_percentage": round(float(usage or 0), 1),
            "remain_percentage": round(float(remain_pct or 0), 1),
            "is_exhausted": bool(is_exhausted),
            "cycle_start": str(pkg.get("cycle_start", "") or ""),
            "cycle_end": str(pkg.get("cycle_end", "") or ""),
        }

    # ResourcePackage 对象
    return {
        "package_name": pkg.package_name,
        "package_type": pkg.package_type,
        "type_label": pkg.type_label,
        "capacity_size": pkg.capacity_size,
        "capacity_remain": pkg.capacity_remain,
        "capacity_used": pkg.capacity_used,
        "cycle_size": pkg.cycle_size,
        "cycle_remain": pkg.cycle_remain,
        "usage_percentage": round(pkg.usage_percentage, 1),
        "remain_percentage": round(pkg.remain_percentage, 1),
        "is_exhausted": pkg.is_exhausted,
        "cycle_start": pkg.cycle_start,
        "cycle_end": pkg.cycle_end,
    }


def _row_from_pkg(acc, pkg: dict, now_ts: float) -> dict:
    """账号 + 资源包 dict -> 列表行"""
    cycle_end = str(pkg.get("cycle_end", "") or "")
    end_ts = _parse_cycle_end_ts(cycle_end)
    cycle_remain = float(pkg.get("cycle_remain", 0) or 0)
    if pkg.get("is_exhausted") or cycle_remain <= 0:
        status = "exhausted"
    elif end_ts is None:
        status = "unknown"
    elif end_ts < now_ts:
        status = "expired"
    else:
        status = "ok"
    return {
        "uid": acc.uid,
        "nickname": acc.nickname,
        "platform": acc.platform.value if acc.platform else "",
        "package_name": pkg.get("package_name", ""),
        "package_type": pkg.get("package_type", ""),
        "type_label": pkg.get("type_label", ""),
        "capacity_size": pkg.get("capacity_size", 0),
        "capacity_remain": pkg.get("capacity_remain", 0),
        "capacity_used": pkg.get("capacity_used", 0),
        "cycle_size": pkg.get("cycle_size", 0),
        "cycle_remain": pkg.get("cycle_remain", 0),
        "usage_percentage": pkg.get("usage_percentage", 0),
        "remain_percentage": pkg.get("remain_percentage", 0),
        "is_exhausted": pkg.get("is_exhausted", False),
        "cycle_start": pkg.get("cycle_start", ""),
        "cycle_end": cycle_end,
        "cycle_end_ts": end_ts,
        "status": status,
    }


def _sort_packages(results: list) -> list:
    """按到期时间升序：有效且最快过期的排最前"""
    results.sort(key=lambda x: (
        0 if x["status"] == "ok" else 1,
        x["cycle_end_ts"] if x["cycle_end_ts"] is not None else float("inf"),
    ))
    return results


def _packages_from_mysql_cache(accounts, now_ts: float) -> list:
    """从 MySQL accounts.quota_packages 聚合（不打上游）"""
    results = []
    for acc in accounts:
        for raw in (getattr(acc.quota, "packages", None) or []):
            results.append(_row_from_pkg(acc, _pkg_to_dict(raw), now_ts))
    return _sort_packages(results)


def _apply_quota_result(account, result: dict, *, sync_checkin: bool = True) -> list:
    """把上游 get_user_resource 结果写入账号缓存（含 quota_packages）并落库。

    sync_checkin=True 时根据「运营裂变包」回写今日签到状态，解决上游已签到但本地仍显示未签到。
    """
    pkg_dicts = [_pkg_to_dict(pkg) for pkg in result.get("packages", [])]
    account.quota.packages = pkg_dicts
    account.quota.credits_remaining = result.get("remaining_credits", 0)
    account.quota.credits_total = result.get("total_credits", 0)
    account.quota.last_updated = datetime.now()
    account.quota.last_error = None
    account.quota.last_error_at = None
    if sync_checkin:
        try:
            from modules.checkin import sync_checkin_from_packages
            sync_checkin_from_packages(account, pkg_dicts)
        except Exception as e:
            logger.debug(f"从资源包同步签到状态失败: {e}")
    save_account(account)
    return pkg_dicts


def _fetch_account_packages(account):
    """查询单个账号的资源包列表（失败返回空列表+错误信息）

    用于 /packages/all?refresh=true 并发调用。同时同步更新本地积分与资源包缓存。
    """
    try:
        client = (
            ApiClient.from_api_key(account.api_key, proxy=get_outbound_proxy())
            if account.api_key.startswith("ck_")
            else ApiClient.from_account(account, proxy=get_outbound_proxy())
        )
        result = client.get_user_resource()
        if not result.get("success"):
            return [], result.get("error", "查询失败")

        try:
            pkg_dicts = _apply_quota_result(account, result)
        except Exception:
            # 落库失败仍返回本次查询结果
            pkg_dicts = [_pkg_to_dict(pkg) for pkg in result.get("packages", [])]
        return pkg_dicts, None
    except Exception as e:
        return [], str(e)


@router.get("/packages/all")
def get_all_packages(refresh: bool = Query(False, description="true=强制打上游刷新并写回 MySQL")):
    """获取所有账号的资源包汇总（按到期时间升序）

    默认读 MySQL accounts.quota_packages 缓存（毫秒级）。
    传 refresh=true 时并发打上游 get-user-resource，并写回缓存。
    若缓存全部为空（从未刷新过），自动走一次上游拉取以填充缓存。
    """
    accounts = load_accounts()
    now_ts = datetime.now().timestamp()

    if not accounts:
        return []

    # 快路径：读 MySQL 缓存
    if not refresh:
        has_cache = any(getattr(a.quota, "packages", None) for a in accounts)
        if has_cache:
            return _packages_from_mysql_cache(accounts, now_ts)
        # 全空则自动拉一次上游填充，避免首次永远空白

    results = []
    workers = min(16, max(1, len(accounts)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_account = {
            executor.submit(_fetch_account_packages, acc): acc for acc in accounts
        }
        for future in future_to_account:
            acc = future_to_account[future]
            try:
                pkgs, err = future.result()
            except Exception as e:
                pkgs, err = [], str(e)
            if err:
                logger.warning(f"[资源包汇总] 账号 {acc.nickname} 查询失败: {err}")
                continue
            for pkg in pkgs:
                results.append(_row_from_pkg(acc, pkg, now_ts))

    return _sort_packages(results)


@router.get("/{uid}")
def get_quota(uid: str):
    """查询指定账号的积分/配额"""
    accounts = load_accounts()
    account = next((a for a in accounts if a.uid == uid), None)
    if not account:
        raise HTTPException(404, "账号不存在")

    client = ApiClient.from_api_key(account.api_key, proxy=get_outbound_proxy()) if account.api_key.startswith("ck_") else ApiClient.from_account(account, proxy=get_outbound_proxy())
    result = client.get_user_resource()

    if not result.get("success"):
        raise HTTPException(400, result.get("error", "查询失败"))

    packages = _apply_quota_result(account, result)

    return {
        "success": True,
        "total_credits": result.get("total_credits", 0),
        "remaining_credits": result.get("remaining_credits", 0),
        "packages": packages,
    }


@router.post("/refresh")
def refresh_all_quotas():
    """刷新所有账号的积分（同时写回资源包缓存，并同步今日签到状态）"""
    accounts = load_accounts()
    results = {"success": 0, "failed": 0, "details": []}

    def _refresh_one(account):
        try:
            client = (
                ApiClient.from_api_key(account.api_key, proxy=get_outbound_proxy())
                if account.api_key.startswith("ck_")
                else ApiClient.from_account(account, proxy=get_outbound_proxy())
            )
            result = client.get_user_resource()
            if not result.get("success"):
                return {
                    "uid": account.uid,
                    "nickname": account.nickname,
                    "error": result.get("error", "未知错误"),
                    "status": "failed",
                }

            _apply_quota_result(account, result, sync_checkin=True)

            # 再打 checkin-status，以服务端为准纠正「已签到仍显示未签到」
            checked_today = bool(account.checkin.checked_today)
            try:
                from modules.checkin import sync_checkin_from_status
                st = client.get_checkin_status()
                if st.get("success") and st.get("data") is not None:
                    if sync_checkin_from_status(account, st["data"]):
                        save_account(account)
                        checked_today = True
                    else:
                        checked_today = bool(account.checkin.checked_today)
            except Exception as e:
                logger.debug(f"同步签到状态失败 {account.nickname}: {e}")

            return {
                "uid": account.uid,
                "nickname": account.nickname,
                "remaining": result.get("remaining_credits", 0),
                "total": result.get("total_credits", 0),
                "status": "success",
                "checked_today": checked_today,
                "last_checkin_time": (
                    account.checkin.last_checkin_time.isoformat()
                    if account.checkin.last_checkin_time
                    else None
                ),
                "streak_days": account.checkin.streak_days,
            }
        except Exception as e:
            return {
                "uid": account.uid,
                "nickname": account.nickname,
                "error": str(e),
                "status": "failed",
            }

    with ThreadPoolExecutor(max_workers=min(16, len(accounts) or 1)) as executor:
        for detail in executor.map(_refresh_one, accounts):
            if detail["status"] == "success":
                results["success"] += 1
            else:
                results["failed"] += 1
            results["details"].append(detail)

    return results


@router.get("/{uid}/payment")
def get_payment_type(uid: str):
    """获取账号付费类型"""
    accounts = load_accounts()
    account = next((a for a in accounts if a.uid == uid), None)
    if not account:
        raise HTTPException(404, "账号不存在")

    client = ApiClient.from_api_key(account.api_key, proxy=get_outbound_proxy()) if account.api_key.startswith("ck_") else ApiClient.from_account(account, proxy=get_outbound_proxy())
    result = client.get_payment_type()
    return result
