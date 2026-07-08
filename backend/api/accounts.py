"""账号管理 API - 账号 CRUD、导入"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from models import Account, Platform, AccountStatus, PlanType, CheckinInfo, QuotaInfo
from utils.store import load_accounts, save_account, delete_account, load_setting
from modules.api_client import ApiClient

router = APIRouter()
logger = logging.getLogger(__name__)


class AddAccountRequest(BaseModel):
    """通过 API Key 添加账号"""
    api_key: str
    nickname: str = ""
    platform: str = "codebuddy"


class ImportAccountsRequest(BaseModel):
    """批量导入 API Key"""
    keys: str  # 每行一个 ck_xxx 或 JSON 数组
    platform: str = "codebuddy"


class UpdateAccountRequest(BaseModel):
    nickname: Optional[str] = None
    status: Optional[str] = None
    account_group: Optional[str] = None


def _account_to_dict(account: Account) -> dict:
    """Account 对象转字典（前端友好）"""
    return {
        "uid": account.uid,
        "nickname": account.nickname,
        "platform": account.platform.value,
        "status": account.status.value,
        "status_reason": account.status_reason,
        "plan_type": account.plan_type.value,
        "api_key": account.api_key,
        "ck": account.ck,
        "checkin": {
            "last_checkin_time": account.checkin.last_checkin_time.isoformat() if account.checkin.last_checkin_time else None,
            "streak_days": account.checkin.streak_days,
            "daily_credit": account.checkin.daily_credit,
            "total_credits": account.checkin.total_credits,
        },
        "quota": {
            "credits_remaining": account.quota.credits_remaining,
            "credits_total": account.quota.credits_total,
            "last_updated": account.quota.last_updated.isoformat() if account.quota.last_updated else None,
        },
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "last_used": account.last_used.isoformat() if account.last_used else None,
    }


@router.get("")
def list_accounts(platform: Optional[str] = None):
    """获取账号列表"""
    plat = Platform(platform) if platform else None
    accounts = load_accounts(plat)
    return [_account_to_dict(a) for a in accounts]


@router.post("")
def add_account(req: AddAccountRequest):
    """通过 API Key 添加账号

    使用 API Key 调用上游 API 获取用户信息（昵称、UID 等），
    然后保存到本地数据库。
    """
    api_key = req.api_key.strip()
    if not api_key.startswith("ck_"):
        raise HTTPException(400, "API Key 必须以 ck_ 开头")

    # 用 API Key 调用上游获取账号信息
    client = ApiClient.from_api_key(api_key)
    result = client.get_user_resource()

    if not result.get("success"):
        raise HTTPException(400, f"API Key 验证失败: {result.get('error', '未知错误')}")

    # 用 API Key 验证并获取付费类型
    payment_result = client.get_payment_type()
    payment_type = payment_result.get("payment_type", "free") if payment_result.get("success") else "free"

    # 从 JWT 解码获取 uid（如果 api_key 是 JWT）
    # API Key 模式下 uid 用 api_key 的哈希作为唯一标识
    import hashlib
    uid = hashlib.md5(api_key.encode()).hexdigest()[:16]

    # 检查是否已存在
    existing = load_accounts()
    for a in existing:
        if a.api_key == api_key:
            raise HTTPException(409, "该 API Key 已存在")

    account = Account(
        uid=uid,
        nickname=req.nickname or f"账号_{uid[:8]}",
        platform=Platform(req.platform),
        status=AccountStatus.ACTIVE,
        plan_type=PlanType(payment_type) if payment_type in ["free", "pro", "team", "enterprise"] else PlanType.FREE,
        api_key=api_key,
        auth_token=api_key,
        quota=QuotaInfo(
            credits_remaining=result.get("remaining_credits", 0),
            credits_total=result.get("total_credits", 0),
            last_updated=datetime.now(),
        ),
        created_at=datetime.now(),
        last_used=datetime.now(),
    )

    save_account(account)
    logger.info(f"添加账号成功: {account.nickname}")
    return _account_to_dict(account)


@router.post("/import")
def import_accounts(req: ImportAccountsRequest):
    """批量导入 API Key"""
    import json
    keys = []
    text = req.keys.strip()
    if text.startswith("["):
        keys = json.loads(text)
    else:
        keys = [line.strip() for line in text.splitlines() if line.strip()]

    results = {"success": 0, "failed": 0, "errors": []}
    for key in keys:
        try:
            add_req = AddAccountRequest(api_key=key, platform=req.platform)
            add_account(add_req)
            results["success"] += 1
        except HTTPException as e:
            if e.status_code == 409:
                results["failed"] += 1
            else:
                results["failed"] += 1
                results["errors"].append(f"{key[:12]}...: {e.detail}")
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"{key[:12]}...: {str(e)}")

    return results


@router.delete("/{uid}")
def remove_account(uid: str):
    """删除账号"""
    delete_account(uid)
    return {"success": True}


@router.put("/{uid}")
def update_account(uid: str, req: UpdateAccountRequest):
    """更新账号信息"""
    accounts = load_accounts()
    account = next((a for a in accounts if a.uid == uid), None)
    if not account:
        raise HTTPException(404, "账号不存在")

    if req.nickname is not None:
        account.nickname = req.nickname
    if req.status is not None:
        account.status = AccountStatus(req.status)

    save_account(account)
    return _account_to_dict(account)
