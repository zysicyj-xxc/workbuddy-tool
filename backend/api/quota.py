"""积分/配额 API - 查询积分、刷新配额、资源包汇总"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from fastapi import APIRouter, HTTPException

from utils.store import load_accounts, save_account
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


def _fetch_account_packages(account):
    """查询单个账号的资源包列表（失败返回空列表+错误信息）

    用于 /packages/all 接口并发调用。同时同步更新本地积分缓存。
    """
    try:
        client = (
            ApiClient.from_api_key(account.api_key)
            if account.api_key.startswith("ck_")
            else ApiClient.from_account(account)
        )
        result = client.get_user_resource()
        if not result.get("success"):
            return [], result.get("error", "查询失败")

        # 同步更新本地积分缓存
        try:
            account.quota.credits_remaining = result.get("remaining_credits", 0)
            account.quota.credits_total = result.get("total_credits", 0)
            account.quota.last_updated = datetime.now()
            save_account(account)
        except Exception:
            pass

        pkgs = []
        for pkg in result.get("packages", []):
            pkgs.append({
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
            })
        return pkgs, None
    except Exception as e:
        return [], str(e)


@router.get("/packages/all")
def get_all_packages():
    """获取所有账号的资源包汇总（按到期时间升序）

    与上游 Key 代理池无关，直接遍历账号管理中的所有账号，
    调用每个账号的 get_user_resource() 获取资源包列表并聚合返回。
    """
    accounts = load_accounts()
    now_ts = datetime.now().timestamp()

    if not accounts:
        return []

    results = []
    # 并发查询所有账号（避免串行太慢）
    with ThreadPoolExecutor(max_workers=min(8, len(accounts))) as executor:
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
                # 查询失败的账号跳过（前端可通过账号管理页单独查看错误）
                logger.warning(f"[资源包汇总] 账号 {acc.nickname} 查询失败: {err}")
                continue
            for pkg in pkgs:
                cycle_end = str(pkg.get("cycle_end", "") or "")
                end_ts = _parse_cycle_end_ts(cycle_end)
                cycle_remain = float(pkg.get("cycle_remain", 0) or 0)
                # 状态判定
                if pkg.get("is_exhausted") or cycle_remain <= 0:
                    status = "exhausted"
                elif end_ts is None:
                    status = "unknown"
                elif end_ts < now_ts:
                    status = "expired"
                else:
                    status = "ok"
                results.append({
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
                })

    # 按到期时间升序：有效且最快过期的排最前
    results.sort(key=lambda x: (
        0 if x["status"] == "ok" else 1,
        x["cycle_end_ts"] if x["cycle_end_ts"] is not None else float("inf"),
    ))
    return results


@router.get("/{uid}")
def get_quota(uid: str):
    """查询指定账号的积分/配额"""
    accounts = load_accounts()
    account = next((a for a in accounts if a.uid == uid), None)
    if not account:
        raise HTTPException(404, "账号不存在")

    client = ApiClient.from_api_key(account.api_key) if account.api_key.startswith("ck_") else ApiClient.from_account(account)
    result = client.get_user_resource()

    if not result.get("success"):
        raise HTTPException(400, result.get("error", "查询失败"))

    # 更新本地存储
    account.quota.credits_remaining = result.get("remaining_credits", 0)
    account.quota.credits_total = result.get("total_credits", 0)
    account.quota.last_updated = datetime.now()
    save_account(account)

    # 返回资源包详情
    packages = []
    for pkg in result.get("packages", []):
        packages.append({
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
        })

    return {
        "success": True,
        "total_credits": result.get("total_credits", 0),
        "remaining_credits": result.get("remaining_credits", 0),
        "packages": packages,
    }


@router.post("/refresh")
def refresh_all_quotas():
    """刷新所有账号的积分"""
    accounts = load_accounts()
    results = {"success": 0, "failed": 0, "details": []}

    for account in accounts:
        try:
            client = ApiClient.from_api_key(account.api_key) if account.api_key.startswith("ck_") else ApiClient.from_account(account)
            result = client.get_user_resource()

            if result.get("success"):
                account.quota.credits_remaining = result.get("remaining_credits", 0)
                account.quota.credits_total = result.get("total_credits", 0)
                account.quota.last_updated = datetime.now()
                save_account(account)
                results["success"] += 1
                results["details"].append({
                    "uid": account.uid,
                    "nickname": account.nickname,
                    "remaining": result.get("remaining_credits", 0),
                    "total": result.get("total_credits", 0),
                    "status": "success",
                })
            else:
                results["failed"] += 1
                results["details"].append({
                    "uid": account.uid,
                    "nickname": account.nickname,
                    "error": result.get("error", "未知错误"),
                    "status": "failed",
                })
        except Exception as e:
            results["failed"] += 1
            results["details"].append({
                "uid": account.uid,
                "nickname": account.nickname,
                "error": str(e),
                "status": "failed",
            })

    return results


@router.get("/{uid}/payment")
def get_payment_type(uid: str):
    """获取账号付费类型"""
    accounts = load_accounts()
    account = next((a for a in accounts if a.uid == uid), None)
    if not account:
        raise HTTPException(404, "账号不存在")

    client = ApiClient.from_api_key(account.api_key) if account.api_key.startswith("ck_") else ApiClient.from_account(account)
    result = client.get_payment_type()
    return result
