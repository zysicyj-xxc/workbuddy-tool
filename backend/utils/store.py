"""本地数据存储 - 加密 JSON 文件持久化

使用 Fernet 对称加密将账号和设置数据存储到 ~/.workbuddy-tool/data.enc。
默认启动时数据为空（不读取旧版 SQLite 数据库）。
"""

import threading
from datetime import datetime
from typing import Optional

from models import (
    Account, Platform, AccountStatus, PlanType,
    CheckinInfo, QuotaInfo,
)
from utils.crypto import get_data_dir, get_or_create_key, encrypt_file, decrypt_file

# 加密数据文件名
_DATA_FILE_NAME = "data.enc"

# 全局锁，保护文件读写避免并发冲突
_lock = threading.Lock()


def _get_data_path() -> str:
    """获取加密数据文件路径"""
    return str(get_data_dir() / _DATA_FILE_NAME)


def _load_data() -> dict:
    """从加密文件加载全部数据

    Returns:
        dict: 包含 accounts 和 settings 的字典。文件不存在或解密失败返回空结构。
    """
    data = decrypt_file(_get_data_path())
    if not data:
        return {"accounts": [], "settings": {}}
    # 确保结构完整
    data.setdefault("accounts", [])
    data.setdefault("settings", {})
    return data


def _save_data(data: dict):
    """加密保存全部数据到文件"""
    encrypt_file(_get_data_path(), data)


def _account_to_dict(account: Account) -> dict:
    """Account 对象序列化为字典"""
    return {
        "uid": account.uid,
        "nickname": account.nickname,
        "platform": account.platform.value,
        "status": account.status.value,
        "status_reason": account.status_reason,
        "plan_type": account.plan_type.value,
        "domain": account.domain,
        "enterprise_id": account.enterprise_id,
        "enterprise_name": account.enterprise_name,
        "auth_token": account.auth_token,
        "auth_raw": account.auth_raw,
        "ck": account.ck,
        "api_key": account.api_key,
        "profile_raw": account.profile_raw,
        "usage_raw": account.usage_raw,
        "checkin": {
            "last_checkin_time": account.checkin.last_checkin_time.isoformat() if account.checkin.last_checkin_time else None,
            "streak_days": account.checkin.streak_days,
            "rewards": account.checkin.rewards,
            "daily_credit": account.checkin.daily_credit,
            "total_credits": account.checkin.total_credits,
        },
        "quota": {
            "hourly_suggestions": account.quota.hourly_suggestions,
            "hourly_suggestions_limit": account.quota.hourly_suggestions_limit,
            "weekly_chat": account.quota.weekly_chat,
            "weekly_chat_limit": account.quota.weekly_chat_limit,
            "credits_remaining": account.quota.credits_remaining,
            "credits_total": account.quota.credits_total,
            "reset_time": account.quota.reset_time.isoformat() if account.quota.reset_time else None,
            "last_updated": account.quota.last_updated.isoformat() if account.quota.last_updated else None,
            "last_error": account.quota.last_error,
            "last_error_at": account.quota.last_error_at.isoformat() if account.quota.last_error_at else None,
        },
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "last_used": account.last_used.isoformat() if account.last_used else None,
        "account_group": getattr(account, "account_group", ""),
    }


def _dict_to_account(d: dict) -> Account:
    """字典反序列化为 Account 对象"""
    # 解析签到信息
    checkin_data = d.get("checkin", {}) or {}
    checkin = CheckinInfo(
        last_checkin_time=datetime.fromisoformat(checkin_data["last_checkin_time"]) if checkin_data.get("last_checkin_time") else None,
        streak_days=checkin_data.get("streak_days", 0),
        rewards=checkin_data.get("rewards", []) or [],
        daily_credit=checkin_data.get("daily_credit", 0),
        total_credits=checkin_data.get("total_credits", 0),
    )

    # 解析配额信息
    quota_data = d.get("quota", {}) or {}
    quota = QuotaInfo(
        hourly_suggestions=quota_data.get("hourly_suggestions", 0),
        hourly_suggestions_limit=quota_data.get("hourly_suggestions_limit", 0),
        weekly_chat=quota_data.get("weekly_chat", 0),
        weekly_chat_limit=quota_data.get("weekly_chat_limit", 0),
        credits_remaining=quota_data.get("credits_remaining", 0.0),
        credits_total=quota_data.get("credits_total", 0.0),
        reset_time=datetime.fromisoformat(quota_data["reset_time"]) if quota_data.get("reset_time") else None,
        last_updated=datetime.fromisoformat(quota_data["last_updated"]) if quota_data.get("last_updated") else None,
        last_error=quota_data.get("last_error"),
        last_error_at=datetime.fromisoformat(quota_data["last_error_at"]) if quota_data.get("last_error_at") else None,
    )

    # 解析平台和状态枚举（容错处理）
    try:
        platform = Platform(d.get("platform", "codebuddy"))
    except ValueError:
        platform = Platform.CODEBUDDY

    try:
        status = AccountStatus(d.get("status", "active"))
    except ValueError:
        status = AccountStatus.ACTIVE

    try:
        plan_type = PlanType(d.get("plan_type", "free"))
    except ValueError:
        plan_type = PlanType.FREE

    return Account(
        uid=d.get("uid", ""),
        nickname=d.get("nickname", ""),
        platform=platform,
        status=status,
        status_reason=d.get("status_reason", ""),
        plan_type=plan_type,
        domain=d.get("domain", ""),
        enterprise_id=d.get("enterprise_id", ""),
        enterprise_name=d.get("enterprise_name", ""),
        auth_token=d.get("auth_token", ""),
        auth_raw=d.get("auth_raw", ""),
        ck=d.get("ck", ""),
        api_key=d.get("api_key", ""),
        profile_raw=d.get("profile_raw", ""),
        usage_raw=d.get("usage_raw", ""),
        checkin=checkin,
        quota=quota,
        created_at=datetime.fromisoformat(d["created_at"]) if d.get("created_at") else None,
        last_used=datetime.fromisoformat(d["last_used"]) if d.get("last_used") else None,
    )


def init_db():
    """初始化加密存储

    确保密钥存在，如果 data.enc 不存在则创建空结构。
    不读取旧版 SQLite 数据库。
    """
    # 确保密钥存在
    get_or_create_key()
    # 确保数据文件存在（空结构）
    with _lock:
        data = _load_data()
        _save_data(data)


def save_account(account: Account):
    """保存账号（新增或更新）"""
    with _lock:
        data = _load_data()
        accounts = data.get("accounts", [])
        account_dict = _account_to_dict(account)
        # 按 uid 查找并替换，不存在则追加
        found = False
        for i, a in enumerate(accounts):
            if a.get("uid") == account.uid:
                accounts[i] = account_dict
                found = True
                break
        if not found:
            accounts.append(account_dict)
        data["accounts"] = accounts
        _save_data(data)


def load_accounts(platform: Optional[Platform] = None) -> list[Account]:
    """加载账号列表

    Args:
        platform: 可选，按平台过滤

    Returns:
        list[Account]: 账号列表，按 last_used 倒序排列
    """
    with _lock:
        data = _load_data()
        accounts = data.get("accounts", [])
        if platform:
            accounts = [a for a in accounts if a.get("platform") == platform.value]
        # 按 last_used 倒序排列（None 排最后）
        accounts.sort(
            key=lambda a: a.get("last_used") or "",
            reverse=True,
        )
        return [_dict_to_account(a) for a in accounts]


def delete_account(uid: str):
    """删除账号"""
    with _lock:
        data = _load_data()
        accounts = data.get("accounts", [])
        data["accounts"] = [a for a in accounts if a.get("uid") != uid]
        _save_data(data)


def save_setting(key: str, value: str):
    """保存设置项"""
    with _lock:
        data = _load_data()
        data.setdefault("settings", {})[key] = value
        _save_data(data)


def load_setting(key: str, default: str = "") -> str:
    """加载设置项"""
    with _lock:
        data = _load_data()
        return data.get("settings", {}).get(key, default)


def load_all_settings() -> dict[str, str]:
    """加载所有设置"""
    with _lock:
        data = _load_data()
        return dict(data.get("settings", {}))
