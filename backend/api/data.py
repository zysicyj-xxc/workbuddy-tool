"""数据包导入导出 API

数据源：MySQL（accounts / settings）+ 代理 JSON（proxy_db，仍落本地卷）。
导出为跨环境口令包（WBDP v3），空库/新机器可用同一口令导入。
兼容：旧版本机 .enc、旧版 SQLite .db。
"""

import io
import json
import logging
import os
import sqlite3
import tempfile
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from models import (
    Account, Platform, AccountStatus, PlanType,
    CheckinInfo, QuotaInfo,
)
from utils.store import (
    load_accounts, save_account, save_setting, load_all_settings,
)
from utils.crypto import encrypt_package, decrypt_package, get_data_dir
from utils import db as mysql_db
from modules.proxy_server import ProxyDatabase

router = APIRouter()
logger = logging.getLogger(__name__)


class ClearDataRequest(BaseModel):
    confirm: str = Field("", description="必须为 CLEAR")
    clear_proxy: bool = True
    clear_settings: bool = True


def _account_to_export_dict(acc: Account) -> dict:
    return {
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
            "packages": getattr(acc.quota, "packages", []) or [],
            "payment_type": getattr(acc.quota, "payment_type", "") or "",
        },
        "created_at": acc.created_at.isoformat() if acc.created_at else None,
        "last_used": acc.last_used.isoformat() if acc.last_used else None,
        "account_group": getattr(acc, "account_group", "") or "",
    }


def build_export_payload() -> dict:
    """从 MySQL + 代理存储组装导出载荷"""
    accounts = load_accounts()
    accounts_data = [_account_to_export_dict(acc) for acc in accounts]
    settings_data = load_all_settings()

    proxy_db = ProxyDatabase.get_instance()
    # 导出前尽量刷盘，保证与内存一致
    try:
        proxy_db.flush_now()
    except Exception:
        pass
    proxy_data = {
        "upstream_keys": proxy_db.get_upstream_keys(),
        "sub_api_keys": proxy_db.get_sub_api_keys(),
        "settings": proxy_db.get_settings(),
    }

    return {
        "version": 3,
        "format": "mysql+proxy",
        "exported_at": datetime.now().isoformat(),
        "accounts": accounts_data,
        "settings": settings_data,
        "proxy": proxy_data,
    }


def apply_import_payload(payload: dict, *, replace: bool = False) -> dict:
    """将数据包写入 MySQL（accounts/settings）与代理 JSON。

    replace=True 时先清空 accounts/settings（空库场景通常 False 即可 upsert）。
    """
    if not isinstance(payload, dict):
        return {
            "success": False,
            "message": "数据包格式无效",
            "accounts_success": 0,
            "accounts_failed": 0,
            "settings_imported": 0,
            "proxy_imported": 0,
        }

    if replace:
        try:
            mysql_db.execute("DELETE FROM accounts")
            mysql_db.execute("DELETE FROM settings")
        except Exception as e:
            logger.warning(f"清空表失败（可忽略）: {e}")

    accounts_success = 0
    accounts_failed = 0
    settings_imported = 0
    proxy_imported = 0

    for acc_dict in payload.get("accounts", []) or []:
        try:
            account = _dict_to_account(acc_dict)
            if account.uid:
                save_account(account)
                accounts_success += 1
            else:
                accounts_failed += 1
        except Exception as e:
            logger.warning(f"导入账号失败: {e}")
            accounts_failed += 1

    for key, value in (payload.get("settings") or {}).items():
        try:
            save_setting(key, value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))
            settings_imported += 1
        except Exception as e:
            logger.warning(f"导入设置失败: {e}")

    proxy_data = payload.get("proxy") or {}
    if proxy_data:
        pdb = ProxyDatabase.get_instance()
        # 替换模式：覆盖代理内存数据
        if replace:
            try:
                with pdb._lock:
                    pdb._data["upstream_keys"] = list(proxy_data.get("upstream_keys") or [])
                    pdb._data["sub_api_keys"] = list(proxy_data.get("sub_api_keys") or [])
                    if proxy_data.get("settings"):
                        pdb._data["settings"] = dict(proxy_data.get("settings") or {})
                    pdb._dirty = True
                pdb.flush_now()
                proxy_imported = len(pdb.get_upstream_keys()) + len(pdb.get_sub_api_keys())
            except Exception as e:
                logger.warning(f"替换导入代理数据失败，回退增量: {e}")
                replace = False

        if not replace:
            for uk in proxy_data.get("upstream_keys") or []:
                try:
                    # 按 key_id / api_key 去重
                    existing = {k.get("key_id") or k.get("api_key") for k in pdb.get_upstream_keys()}
                    ident = uk.get("key_id") or uk.get("api_key")
                    if ident and ident in existing:
                        continue
                    pdb.add_upstream_key(uk)
                    proxy_imported += 1
                except Exception as e:
                    logger.warning(f"导入上游Key失败: {e}")
            for sk in proxy_data.get("sub_api_keys") or []:
                try:
                    existing = {k.get("key") or k.get("api_key") for k in pdb.get_sub_api_keys()}
                    ident = sk.get("key") or sk.get("api_key")
                    if ident and ident in existing:
                        continue
                    pdb.add_sub_api_key(sk)
                    proxy_imported += 1
                except Exception as e:
                    logger.warning(f"导入子Key失败: {e}")
            proxy_settings = proxy_data.get("settings") or {}
            if proxy_settings:
                try:
                    pdb.update_settings(proxy_settings)
                except Exception as e:
                    logger.warning(f"导入代理设置失败: {e}")

    return {
        "success": True,
        "message": (
            f"导入完成：账号成功 {accounts_success} 个，失败 {accounts_failed} 个，"
            f"设置 {settings_imported} 项，代理数据 {proxy_imported} 条"
        ),
        "accounts_success": accounts_success,
        "accounts_failed": accounts_failed,
        "settings_imported": settings_imported,
        "proxy_imported": proxy_imported,
        # 前端兼容字段
        "imported": accounts_success,
        "success_count": accounts_success,
        "failed": accounts_failed,
        "failed_count": accounts_failed,
    }


def clear_all_data(*, clear_proxy: bool = True, clear_settings: bool = True) -> dict:
    """清空 MySQL 账号/设置，以及可选的代理 JSON 数据。"""
    accounts_deleted = 0
    settings_deleted = 0
    try:
        row = mysql_db.query_one("SELECT COUNT(*) AS c FROM accounts")
        accounts_deleted = int((row or {}).get("c") or 0)
        mysql_db.execute("DELETE FROM accounts")
    except Exception as e:
        logger.error(f"清空 accounts 失败: {e}")
        raise

    if clear_settings:
        try:
            row = mysql_db.query_one("SELECT COUNT(*) AS c FROM settings")
            settings_deleted = int((row or {}).get("c") or 0)
            mysql_db.execute("DELETE FROM settings")
        except Exception as e:
            logger.warning(f"清空 settings 失败: {e}")

    proxy_cleared = False
    if clear_proxy:
        try:
            pdb = ProxyDatabase.get_instance()
            pdb.clear_all(keep_settings=False)
            proxy_cleared = True
        except Exception as e:
            logger.warning(f"清空代理数据失败: {e}")

    # 清空后尝试停止正在运行的代理
    if clear_proxy:
        try:
            from api.proxy import get_proxy_server, set_proxy_server
            ps = get_proxy_server()
            if ps and getattr(ps, "is_running", False):
                ps.stop()
                set_proxy_server(None)
                logger.info("清空数据后已停止代理服务")
        except Exception as e:
            logger.warning(f"停止代理失败: {e}")

    return {
        "success": True,
        "message": (
            f"已清空：账号 {accounts_deleted} 个，"
            f"设置 {settings_deleted} 项"
            + ("，代理数据已清空" if proxy_cleared else "")
        ),
        "accounts_deleted": accounts_deleted,
        "settings_deleted": settings_deleted,
        "proxy_cleared": proxy_cleared,
    }


@router.post("/export")
def export_data(password: Optional[str] = None):
    """从 MySQL 导出加密数据包（跨环境可导入）"""
    payload = build_export_payload()
    encrypted = encrypt_package(payload, password=password)
    filename = f"workbuddy-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}.enc"
    return StreamingResponse(
        io.BytesIO(encrypted),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/clear")
def clear_data(body: ClearDataRequest = Body(...)):
    """清空全部业务数据（账号/设置/代理）。

    请求体需包含 confirm=CLEAR 以防误触。
    """
    if str(body.confirm or "").strip().upper() != "CLEAR":
        return {
            "success": False,
            "message": "请在请求体中设置 confirm=CLEAR 以确认清空",
        }
    try:
        return clear_all_data(
            clear_proxy=bool(body.clear_proxy),
            clear_settings=bool(body.clear_settings),
        )
    except Exception as e:
        logger.error(f"清空数据失败: {e}", exc_info=True)
        return {"success": False, "message": f"清空失败: {e}"}


@router.post("/import")
async def import_sqlite_data(file: UploadFile = File(...), replace: bool = Form(False)):
    """导入旧版 SQLite .db → 写入 MySQL（兼容迁移）"""
    if not file.filename:
        return {"success": False, "message": "未提供文件"}

    content = await file.read()
    if not content:
        return {"success": False, "message": "文件内容为空"}

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    accounts = []
    settings = {}
    try:
        conn = sqlite3.connect(tmp_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            rows = cursor.execute("SELECT * FROM accounts").fetchall()
        except sqlite3.OperationalError:
            rows = []
        for row in rows:
            try:
                accounts.append(_account_to_export_dict(_sqlite_row_to_account(row)))
            except Exception as e:
                logger.warning(f"解析 SQLite 账号失败: {e}")
        try:
            for srow in cursor.execute("SELECT key, value FROM settings").fetchall():
                settings[srow["key"]] = srow["value"]
        except sqlite3.OperationalError:
            pass
        conn.close()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    # 旧 proxy_db.json（同机迁移场景）
    proxy_data = {}
    proxy_db_path = os.path.join(str(get_data_dir()), "proxy_db.json")
    if os.path.exists(proxy_db_path):
        try:
            with open(proxy_db_path, "r", encoding="utf-8") as pf:
                proxy_data = json.load(pf)
        except Exception as e:
            logger.warning(f"读取 proxy_db.json 失败: {e}")

    payload = {
        "version": 1,
        "format": "sqlite-legacy",
        "accounts": accounts,
        "settings": settings,
        "proxy": {
            "upstream_keys": proxy_data.get("upstream_keys", []),
            "sub_api_keys": proxy_data.get("sub_api_keys", []),
            "settings": proxy_data.get("settings", {}),
        },
    }
    return apply_import_payload(payload, replace=bool(replace))


@router.post("/import-encrypted")
async def import_encrypted_data(
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    replace: bool = Form(False),
):
    """导入加密数据包 → MySQL + 代理存储。空库直接导入即可。"""
    if not file.filename:
        return {"success": False, "message": "未提供文件"}

    content = await file.read()
    if not content:
        return {"success": False, "message": "文件内容为空"}

    payload = decrypt_package(content, password=password)
    if not payload:
        # 旧版本机 Fernet 包（无 WBDP 头）在跨环境无法解密
        is_legacy = not content.startswith(b"WBDP")
        hint = (
            "解密失败：这是旧版本机 data.enc（依赖原 secret.key），"
            "请在宿主机运行: python scripts/migrate_legacy_data.py --import-http --replace"
            if is_legacy
            else "解密失败：口令不正确，或文件损坏/不是 workbuddy 数据包"
        )
        return {
            "success": False,
            "message": hint,
            "accounts_success": 0,
            "accounts_failed": 0,
            "settings_imported": 0,
            "proxy_imported": 0,
        }

    return apply_import_payload(payload, replace=bool(replace))


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

    checkin = CheckinInfo(
        last_checkin_time=_parse_dt(_get_col("last_checkin_time")),
        streak_days=_get_col("streak_days", 0) or 0,
        rewards=json.loads(_get_col("checkin_rewards", "[]") or "[]"),
        daily_credit=_get_col("daily_credit", 0) or 0,
        total_credits=_get_col("total_credits", 0) or 0,
    )

    packages_raw = _get_col("quota_packages", "[]") or "[]"
    try:
        packages = json.loads(packages_raw) if isinstance(packages_raw, str) else (packages_raw or [])
    except (json.JSONDecodeError, TypeError):
        packages = []

    quota = QuotaInfo(
        hourly_suggestions=_get_col("hourly_suggestions", 0) or 0,
        hourly_suggestions_limit=_get_col("hourly_suggestions_limit", 0) or 0,
        weekly_chat=_get_col("weekly_chat", 0) or 0,
        weekly_chat_limit=_get_col("weekly_chat_limit", 0) or 0,
        credits_remaining=_get_col("credits_remaining", 0.0) or 0.0,
        credits_total=_get_col("credits_total", 0.0) or 0.0,
        reset_time=_parse_dt(_get_col("reset_time")),
        last_updated=_parse_dt(_get_col("quota_last_updated")),
        last_error=_get_col("quota_last_error"),
        last_error_at=_parse_dt(_get_col("quota_last_error_at")),
        packages=packages if isinstance(packages, list) else [],
        payment_type=_get_col("quota_payment_type", "") or "",
    )

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
        account_group=_get_col("account_group", "") or "",
    )


def _dict_to_account(d: dict) -> Account:
    """字典转换为 Account（加密包 / 中间格式）"""
    checkin_data = d.get("checkin", {}) or {}
    checkin = CheckinInfo(
        last_checkin_time=datetime.fromisoformat(checkin_data["last_checkin_time"]) if checkin_data.get("last_checkin_time") else None,
        streak_days=checkin_data.get("streak_days", 0) or 0,
        rewards=checkin_data.get("rewards", []) or [],
        daily_credit=checkin_data.get("daily_credit", 0) or 0,
        total_credits=checkin_data.get("total_credits", 0) or 0,
    )

    quota_data = d.get("quota", {}) or {}
    packages = quota_data.get("packages") or d.get("quota_packages") or []
    if isinstance(packages, str):
        try:
            packages = json.loads(packages)
        except (json.JSONDecodeError, TypeError):
            packages = []

    quota = QuotaInfo(
        hourly_suggestions=quota_data.get("hourly_suggestions", 0) or 0,
        hourly_suggestions_limit=quota_data.get("hourly_suggestions_limit", 0) or 0,
        weekly_chat=quota_data.get("weekly_chat", 0) or 0,
        weekly_chat_limit=quota_data.get("weekly_chat_limit", 0) or 0,
        credits_remaining=quota_data.get("credits_remaining", 0.0) or 0.0,
        credits_total=quota_data.get("credits_total", 0.0) or 0.0,
        reset_time=datetime.fromisoformat(quota_data["reset_time"]) if quota_data.get("reset_time") else None,
        last_updated=datetime.fromisoformat(quota_data["last_updated"]) if quota_data.get("last_updated") else None,
        last_error=quota_data.get("last_error"),
        last_error_at=datetime.fromisoformat(quota_data["last_error_at"]) if quota_data.get("last_error_at") else None,
        packages=packages if isinstance(packages, list) else [],
        payment_type=quota_data.get("payment_type") or d.get("quota_payment_type") or "",
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
        account_group=d.get("account_group", "") or "",
    )
