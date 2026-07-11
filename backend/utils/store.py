"""数据存储 - MySQL 持久化

账号与设置数据持久化到 MySQL（antigravity 库）。连接由 utils.db 管理，
凭据通过环境变量 DB_CONF 注入，不在源码中保留明文。

对外接口与原本地加密存储保持一致，便于上层（main.py / router）无缝切换：
  init_db / save_account / load_accounts / delete_account
  save_setting / load_setting / load_all_settings
"""

import json
import threading
from datetime import datetime
from typing import Optional

from models import (
    Account, Platform, AccountStatus, PlanType,
    CheckinInfo, QuotaInfo,
)
from utils import db

# 全局锁，保护内存侧非原子操作（DB 本身有事务保证）
_lock = threading.Lock()


def _row_to_account(row: dict) -> Account:
    """数据库行 -> Account 对象"""
    checkin = CheckinInfo(
        last_checkin_time=_parse_dt(row.get("last_checkin_time")),
        streak_days=row.get("streak_days", 0) or 0,
        rewards=_parse_json(row.get("checkin_rewards"), []),
        daily_credit=row.get("daily_credit", 0) or 0,
        total_credits=row.get("total_credits", 0) or 0,
    )
    quota = QuotaInfo(
        hourly_suggestions=row.get("hourly_suggestions", 0) or 0,
        hourly_suggestions_limit=row.get("hourly_suggestions_limit", 0) or 0,
        weekly_chat=row.get("weekly_chat", 0) or 0,
        weekly_chat_limit=row.get("weekly_chat_limit", 0) or 0,
        credits_remaining=float(row.get("credits_remaining", 0) or 0),
        credits_total=float(row.get("credits_total", 0) or 0),
        reset_time=_parse_dt(row.get("reset_time")),
        last_updated=_parse_dt(row.get("quota_last_updated")),
        last_error=row.get("quota_last_error"),
        last_error_at=_parse_dt(row.get("quota_last_error_at")),
    )
    # 资源包（旧版库无此列时为 []）
    try:
        quota.packages = _parse_json(row.get("quota_packages"), [])
    except Exception:
        quota.packages = []

    try:
        platform = Platform(row.get("platform", "codebuddy"))
    except ValueError:
        platform = Platform.CODEBUDDY

    try:
        status = AccountStatus(row.get("status", "active"))
    except ValueError:
        status = AccountStatus.ACTIVE

    try:
        plan_type = PlanType(row.get("plan_type", "free"))
    except ValueError:
        plan_type = PlanType.FREE

    return Account(
        uid=row.get("uid", ""),
        nickname=row.get("nickname", ""),
        platform=platform,
        status=status,
        status_reason=row.get("status_reason", ""),
        plan_type=plan_type,
        domain=row.get("domain", ""),
        enterprise_id=row.get("enterprise_id", ""),
        enterprise_name=row.get("enterprise_name", ""),
        auth_token=row.get("auth_token", ""),
        auth_raw=row.get("auth_raw", ""),
        ck=row.get("ck", ""),
        api_key=row.get("api_key", ""),
        profile_raw=row.get("profile_raw", ""),
        usage_raw=row.get("usage_raw", ""),
        checkin=checkin,
        quota=quota,
        created_at=_parse_dt(row.get("created_at")),
        last_used=_parse_dt(row.get("last_used")),
        account_group=row.get("account_group", ""),
    )


def _account_to_row(account: Account) -> dict:
    """Account 对象 -> 数据库列字典"""
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
        "account_group": getattr(account, "account_group", ""),
        "created_at": _dt_to_sql(account.created_at),
        "last_used": _dt_to_sql(account.last_used),
        "last_checkin_time": _dt_to_sql(account.checkin.last_checkin_time),
        "streak_days": account.checkin.streak_days,
        "checkin_rewards": json.dumps(account.checkin.rewards, ensure_ascii=False),
        "daily_credit": account.checkin.daily_credit,
        "total_credits": account.checkin.total_credits,
        "hourly_suggestions": account.quota.hourly_suggestions,
        "hourly_suggestions_limit": account.quota.hourly_suggestions_limit,
        "weekly_chat": account.quota.weekly_chat,
        "weekly_chat_limit": account.quota.weekly_chat_limit,
        "credits_remaining": account.quota.credits_remaining,
        "credits_total": account.quota.credits_total,
        "reset_time": _dt_to_sql(account.quota.reset_time),
        "quota_last_updated": _dt_to_sql(account.quota.last_updated),
        "quota_last_error": account.quota.last_error,
        "quota_last_error_at": _dt_to_sql(account.quota.last_error_at),
        "quota_packages": json.dumps(getattr(account.quota, "packages", []), ensure_ascii=False, default=str),
        "quota_payment_type": getattr(account.quota, "payment_type", ""),
    }


def _parse_dt(v):
    """解析多种格式的日期时间为 datetime 或 None"""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        s = v.strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        # 兜底：ISO 含 Z / 偏移
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _dt_to_sql(v):
    """datetime -> MySQL DATETIME 字符串（None 保持 NULL）"""
    dt = _parse_dt(v)
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def _parse_json(v, default):
    if v is None or v == "":
        return default
    if isinstance(v, (list, dict)):
        return v
    try:
        return json.loads(v)
    except (json.JSONDecodeError, TypeError):
        return default


_SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS accounts (
      uid VARCHAR(64) NOT NULL PRIMARY KEY,
      nickname VARCHAR(255) NOT NULL DEFAULT '',
      platform VARCHAR(32) NOT NULL DEFAULT 'codebuddy',
      status VARCHAR(32) NOT NULL DEFAULT 'active',
      status_reason VARCHAR(512) NOT NULL DEFAULT '',
      plan_type VARCHAR(32) NOT NULL DEFAULT 'free',
      domain VARCHAR(255) NOT NULL DEFAULT '',
      enterprise_id VARCHAR(128) NOT NULL DEFAULT '',
      enterprise_name VARCHAR(255) NOT NULL DEFAULT '',
      auth_token TEXT,
      auth_raw MEDIUMTEXT,
      ck TEXT,
      api_key TEXT,
      profile_raw MEDIUMTEXT,
      usage_raw MEDIUMTEXT,
      account_group VARCHAR(128) NOT NULL DEFAULT '',
      created_at DATETIME NULL,
      last_used DATETIME NULL,
      last_checkin_time DATETIME NULL,
      streak_days INT NOT NULL DEFAULT 0,
      checkin_rewards JSON NULL,
      daily_credit INT NOT NULL DEFAULT 0,
      total_credits INT NOT NULL DEFAULT 0,
      hourly_suggestions INT NOT NULL DEFAULT 0,
      hourly_suggestions_limit INT NOT NULL DEFAULT 0,
      weekly_chat INT NOT NULL DEFAULT 0,
      weekly_chat_limit INT NOT NULL DEFAULT 0,
      credits_remaining DOUBLE NOT NULL DEFAULT 0,
      credits_total DOUBLE NOT NULL DEFAULT 0,
      reset_time DATETIME NULL,
      quota_last_updated DATETIME NULL,
      quota_last_error TEXT NULL,
      quota_last_error_at DATETIME NULL,
      quota_packages JSON NULL,
      quota_payment_type VARCHAR(64) NOT NULL DEFAULT ''
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS settings (
      `key` VARCHAR(128) NOT NULL PRIMARY KEY,
      `value` MEDIUMTEXT NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]

# 旧库可能缺列，启动时幂等补齐
_SCHEMA_ALTERS = [
    "ALTER TABLE accounts ADD COLUMN quota_packages JSON NULL",
    "ALTER TABLE accounts ADD COLUMN quota_payment_type VARCHAR(64) NOT NULL DEFAULT ''",
    "ALTER TABLE accounts ADD COLUMN account_group VARCHAR(128) NOT NULL DEFAULT ''",
]


def init_db():
    """连接校验 + 空库建表（幂等）。本地 docker-compose 与生产均可空库启动后再导入数据包。"""
    try:
        db.query_one("SELECT 1")
    except Exception as e:
        raise RuntimeError(f"无法连接数据库，请检查 DB_CONF 环境变量配置: {e}")

    for sql in _SCHEMA_SQL:
        db.execute(sql)
    for sql in _SCHEMA_ALTERS:
        try:
            db.execute(sql)
        except Exception:
            # 列已存在等可忽略
            pass


_COLUMNS = [
    "uid", "nickname", "platform", "status", "status_reason", "plan_type",
    "domain", "enterprise_id", "enterprise_name", "auth_token", "auth_raw",
    "ck", "api_key", "profile_raw", "usage_raw", "account_group",
    "created_at", "last_used", "last_checkin_time", "streak_days",
    "checkin_rewards", "daily_credit", "total_credits", "hourly_suggestions",
    "hourly_suggestions_limit", "weekly_chat", "weekly_chat_limit",
    "credits_remaining", "credits_total", "reset_time", "quota_last_updated",
    "quota_last_error", "quota_last_error_at", "quota_packages", "quota_payment_type",
]


def save_account(account: Account):
    """保存账号（新增或更新，按 uid 主键 upsert）"""
    row = _account_to_row(account)
    cols = _COLUMNS
    placeholders = ", ".join(["%s"] * len(cols))
    update_clause = ", ".join([f"{c}=VALUES({c})" for c in cols if c != "uid"])
    sql = (
        f"INSERT INTO accounts ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {update_clause}"
    )
    args = [row[c] for c in cols]
    with _lock:
        db.execute(sql, args)


def load_accounts(platform: Optional[Platform] = None) -> list[Account]:
    """加载账号列表，按 last_used 倒序"""
    if platform:
        rows = db.query(
            "SELECT * FROM accounts WHERE platform=%s ORDER BY last_used IS NULL, last_used DESC",
            (platform.value,),
        )
    else:
        rows = db.query(
            "SELECT * FROM accounts ORDER BY last_used IS NULL, last_used DESC"
        )
    return [_row_to_account(r) for r in rows]


def delete_account(uid: str):
    """删除账号"""
    with _lock:
        db.execute("DELETE FROM accounts WHERE uid=%s", (uid,))


def save_setting(key: str, value: str):
    """保存设置项（upsert）"""
    db.execute(
        "INSERT INTO settings (`key`, `value`) VALUES (%s, %s) "
        "ON DUPLICATE KEY UPDATE `value`=VALUES(`value`)",
        (key, value),
    )


def load_setting(key: str, default: str = "") -> str:
    """加载设置项"""
    row = db.query_one("SELECT `value` FROM settings WHERE `key`=%s", (key,))
    return row["value"] if row else default


def load_all_settings() -> dict:
    """加载所有设置"""
    rows = db.query("SELECT `key`, `value` FROM settings")
    return {r["key"]: r["value"] for r in rows}
