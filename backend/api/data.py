"""数据包导入导出 API"""

import io
import json
import logging
import os
import sqlite3
import tempfile
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse

from models import (
    Account, Platform, AccountStatus, PlanType,
    CheckinInfo, QuotaInfo,
)
from utils.store import (
    load_accounts, save_account, save_setting, load_all_settings,
)
from utils.crypto import get_data_dir, encrypt_json, decrypt_json
from modules.proxy_server import ProxyDatabase

router = APIRouter()
logger = logging.getLogger(__name__)


# ─── 导出数据包 ───

@router.post("/export")
def export_data():
    """导出当前所有数据为加密 JSON 文件

    导出内容包括：
    - accounts: 账号数据（从加密存储读取）
    - settings: 应用设置
    - proxy: 代理服务数据（上游Key、子Key、设置）
    """
    # 读取账号数据
    accounts = load_accounts()

    # 将 Account 对象序列化为字典
    accounts_data = []
    for acc in accounts:
        accounts_data.append({
            "uid": acc.uid,
            "nickname": acc.nickname,
            "platform": acc.platform.value,
            "status": acc.status.value,
            "status_reason": acc.status_reason,
            "plan_type": acc.plan_type.value,
            "domain": acc.domain,
            "enterprise_id": acc.enterprise_id,
            "enterprise_name": acc.enterprise_name,
            "auth_token": acc.auth_token,
            "auth_raw": acc.auth_raw,
            "ck": acc.ck,
            "api_key": acc.api_key,
            "profile_raw": acc.profile_raw,
            "usage_raw": acc.usage_raw,
            "checkin": {
                "last_checkin_time": acc.checkin.last_checkin_time.isoformat() if acc.checkin.last_checkin_time else None,
                "streak_days": acc.checkin.streak_days,
                "rewards": acc.checkin.rewards,
                "daily_credit": acc.checkin.daily_credit,
                "total_credits": acc.checkin.total_credits,
            },
            "quota": {
                "hourly_suggestions": acc.quota.hourly_suggestions,
                "hourly_suggestions_limit": acc.quota.hourly_suggestions_limit,
                "weekly_chat": acc.quota.weekly_chat,
                "weekly_chat_limit": acc.quota.weekly_chat_limit,
                "credits_remaining": acc.quota.credits_remaining,
                "credits_total": acc.quota.credits_total,
                "reset_time": acc.quota.reset_time.isoformat() if acc.quota.reset_time else None,
                "last_updated": acc.quota.last_updated.isoformat() if acc.quota.last_updated else None,
                "last_error": acc.quota.last_error,
                "last_error_at": acc.quota.last_error_at.isoformat() if acc.quota.last_error_at else None,
            },
            "created_at": acc.created_at.isoformat() if acc.created_at else None,
            "last_used": acc.last_used.isoformat() if acc.last_used else None,
            "account_group": getattr(acc, "account_group", ""),
        })

    # 读取设置数据
    settings_data = load_all_settings()

    # 读取代理数据
    db = ProxyDatabase.get_instance()
    proxy_data = {
        "upstream_keys": db.get_upstream_keys(),
        "sub_api_keys": db.get_sub_api_keys(),
        "settings": db.get_settings(),
    }

    # 组装完整数据包
    export_payload = {
        "version": 2,
        "exported_at": datetime.now().isoformat(),
        "accounts": accounts_data,
        "settings": settings_data,
        "proxy": proxy_data,
    }

    # 加密
    encrypted = encrypt_json(export_payload)

    # 生成文件名
    filename = f"antigravity-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}.enc"

    return StreamingResponse(
        io.BytesIO(encrypted),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── 导入旧版数据包（SQLite） ───

@router.post("/import")
async def import_sqlite_data(file: UploadFile = File(...)):
    """导入旧版 SQLite 数据库文件

    解析 .db 文件中的 accounts 表和 settings 表，转换为 Account 对象保存。
    同时读取旧 proxy_db.json（如果存在）中的 upstream_keys 和 sub_api_keys。
    """
    if not file.filename:
        return {"success": False, "message": "未提供文件"}

    # 读取上传文件内容
    content = await file.read()
    if not content:
        return {"success": False, "message": "文件内容为空"}

    # 写入临时文件
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    success_count = 0
    fail_count = 0
    settings_count = 0
    proxy_imported = 0

    try:
        # 解析 SQLite 数据库
        conn = sqlite3.connect(tmp_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 导入 accounts 表
        try:
            rows = cursor.execute("SELECT * FROM accounts").fetchall()
        except sqlite3.OperationalError:
            rows = []

        for row in rows:
            try:
                account = _sqlite_row_to_account(row)
                if account.uid:
                    save_account(account)
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                logger.warning(f"导入账号失败: {e}")
                fail_count += 1

        # 导入 settings 表
        try:
            setting_rows = cursor.execute("SELECT key, value FROM settings").fetchall()
            for srow in setting_rows:
                save_setting(srow["key"], srow["value"])
                settings_count += 1
        except sqlite3.OperationalError:
            pass

        conn.close()

        # 读取旧 proxy_db.json（如果存在）
        proxy_db_path = os.path.join(str(get_data_dir()), "proxy_db.json")
        if os.path.exists(proxy_db_path):
            try:
                with open(proxy_db_path, "r", encoding="utf-8") as pf:
                    proxy_data = json.load(pf)
                db = ProxyDatabase.get_instance()
                # 导入上游 Key
                for uk in proxy_data.get("upstream_keys", []):
                    try:
                        db.add_upstream_key(uk)
                        proxy_imported += 1
                    except Exception as e:
                        logger.warning(f"导入上游Key失败: {e}")
                # 导入子 Key
                for sk in proxy_data.get("sub_api_keys", []):
                    try:
                        db.add_sub_api_key(sk)
                        proxy_imported += 1
                    except Exception as e:
                        logger.warning(f"导入子Key失败: {e}")
            except Exception as e:
                logger.warning(f"读取 proxy_db.json 失败: {e}")

    finally:
        # 清理临时文件
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return {
        "success": True,
        "message": f"导入完成：账号成功 {success_count} 个，失败 {fail_count} 个，设置 {settings_count} 项，代理数据 {proxy_imported} 条",
        "accounts_success": success_count,
        "accounts_failed": fail_count,
        "settings_imported": settings_count,
        "proxy_imported": proxy_imported,
    }


def _sqlite_row_to_account(row: sqlite3.Row) -> Account:
    """SQLite 行转换为 Account 对象（兼容旧版数据库字段）"""
    def _get_col(name: str, default=""):
        try:
            return row[name]
        except (KeyError, IndexError):
            return default

    def _parse_dt(val):
        if val and isinstance(val, str):
            try:
                return datetime.fromisoformat(val)
            except (ValueError, TypeError):
                return None
        return None

    # 解析签到信息
    checkin = CheckinInfo(
        last_checkin_time=_parse_dt(_get_col("last_checkin_time")),
        streak_days=_get_col("streak_days", 0),
        rewards=json.loads(_get_col("checkin_rewards", "[]")),
        daily_credit=_get_col("daily_credit", 0),
        total_credits=_get_col("total_credits", 0),
    )

    # 解析配额信息
    quota = QuotaInfo(
        hourly_suggestions=_get_col("hourly_suggestions", 0),
        hourly_suggestions_limit=_get_col("hourly_suggestions_limit", 0),
        weekly_chat=_get_col("weekly_chat", 0),
        weekly_chat_limit=_get_col("weekly_chat_limit", 0),
        credits_remaining=_get_col("credits_remaining", 0.0),
        credits_total=_get_col("credits_total", 0.0),
        reset_time=_parse_dt(_get_col("reset_time")),
        last_updated=_parse_dt(_get_col("quota_last_updated")),
        last_error=_get_col("quota_last_error"),
        last_error_at=_parse_dt(_get_col("quota_last_error_at")),
    )

    # 解析枚举（容错）
    try:
        platform = Platform(_get_col("platform", "codebuddy"))
    except ValueError:
        platform = Platform.CODEBUDDY

    try:
        status = AccountStatus(_get_col("status", "active"))
    except ValueError:
        status = AccountStatus.ACTIVE

    try:
        plan_type = PlanType(_get_col("plan_type", "free"))
    except ValueError:
        plan_type = PlanType.FREE

    return Account(
        uid=_get_col("uid", ""),
        nickname=_get_col("nickname", ""),
        platform=platform,
        status=status,
        status_reason=_get_col("status_reason", ""),
        plan_type=plan_type,
        domain=_get_col("domain", ""),
        enterprise_id=_get_col("enterprise_id", ""),
        enterprise_name=_get_col("enterprise_name", ""),
        auth_token=_get_col("auth_token", ""),
        auth_raw=_get_col("auth_raw", ""),
        ck=_get_col("ck", ""),
        api_key=_get_col("api_key", ""),
        profile_raw=_get_col("profile_raw", ""),
        usage_raw=_get_col("usage_raw", ""),
        checkin=checkin,
        quota=quota,
        created_at=_parse_dt(_get_col("created_at")),
        last_used=_parse_dt(_get_col("last_used")),
    )


# ─── 导入新版数据包（加密 JSON） ───

@router.post("/import-encrypted")
async def import_encrypted_data(file: UploadFile = File(...)):
    """导入新版加密 JSON 数据包

    解密 .enc 文件后恢复 accounts、settings 和 proxy 数据。
    """
    if not file.filename:
        return {"success": False, "message": "未提供文件"}

    content = await file.read()
    if not content:
        return {"success": False, "message": "文件内容为空"}

    # 解密
    payload = decrypt_json(content)
    if not payload:
        return {"success": False, "message": "解密失败，文件可能损坏或密钥不匹配"}

    accounts_success = 0
    accounts_failed = 0
    settings_imported = 0
    proxy_imported = 0

    # 导入账号
    for acc_dict in payload.get("accounts", []):
        try:
            account = _dict_to_account(acc_dict)
            if account.uid:
                save_account(account)
                accounts_success += 1
            else:
                accounts_failed += 1
        except Exception as e:
            logger.warning(f"导入加密账号失败: {e}")
            accounts_failed += 1

    # 导入设置
    for key, value in payload.get("settings", {}).items():
        try:
            save_setting(key, str(value))
            settings_imported += 1
        except Exception as e:
            logger.warning(f"导入设置失败: {e}")

    # 导入代理数据
    proxy_data = payload.get("proxy", {})
    if proxy_data:
        db = ProxyDatabase.get_instance()
        for uk in proxy_data.get("upstream_keys", []):
            try:
                db.add_upstream_key(uk)
                proxy_imported += 1
            except Exception as e:
                logger.warning(f"导入上游Key失败: {e}")
        for sk in proxy_data.get("sub_api_keys", []):
            try:
                db.add_sub_api_key(sk)
                proxy_imported += 1
            except Exception as e:
                logger.warning(f"导入子Key失败: {e}")
        # 导入代理设置
        proxy_settings = proxy_data.get("settings", {})
        if proxy_settings:
            try:
                db.update_settings(proxy_settings)
            except Exception as e:
                logger.warning(f"导入代理设置失败: {e}")

    return {
        "success": True,
        "message": f"导入完成：账号成功 {accounts_success} 个，失败 {accounts_failed} 个，设置 {settings_imported} 项，代理数据 {proxy_imported} 条",
        "accounts_success": accounts_success,
        "accounts_failed": accounts_failed,
        "settings_imported": settings_imported,
        "proxy_imported": proxy_imported,
    }


def _dict_to_account(d: dict) -> Account:
    """字典转换为 Account 对象（用于导入加密数据包）"""
    checkin_data = d.get("checkin", {}) or {}
    checkin = CheckinInfo(
        last_checkin_time=datetime.fromisoformat(checkin_data["last_checkin_time"]) if checkin_data.get("last_checkin_time") else None,
        streak_days=checkin_data.get("streak_days", 0),
        rewards=checkin_data.get("rewards", []) or [],
        daily_credit=checkin_data.get("daily_credit", 0),
        total_credits=checkin_data.get("total_credits", 0),
    )

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
