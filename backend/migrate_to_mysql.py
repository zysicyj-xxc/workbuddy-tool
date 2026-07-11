"""数据迁移脚本 - 将本地数据迁移到 MySQL

数据源（按优先级）：
  1. SQLite 文件（默认 ~/.antigravity-tools/antigravity.db，可用 --sqlite 指定）
  2. 本地加密文件 ~/.workbuddy-tool/data.enc（由 --enc 指定）

目标：MySQL（antigravity 库），连接配置通过环境变量 DB_CONF（JSON）注入。

用法：
  set DB_CONF={"host":"...","port":3306,"user":"...","passwd":"...","database":"antigravity","charset":"utf8mb4"}
  python migrate_to_mysql.py [--sqlite PATH] [--enc PATH] [--dry-run]
"""

import argparse
import json
import os
import sqlite3
import sys

# 将 backend 目录加入 sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from utils.store import save_account, save_setting, _row_to_account  # noqa: E402


def migrate_from_sqlite(path: str, dry_run: bool = False):
    """从 SQLite 迁移 accounts + settings 到 MySQL"""
    print(f"[迁移] 读取 SQLite: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM accounts")
        rows = cur.fetchall()
        accounts = [dict(r) for r in rows]
        cur.execute("SELECT `key`, `value` FROM settings")
        settings = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    print(f"[迁移] 找到 {len(accounts)} 个账号, {len(settings)} 条设置")

    if dry_run:
        print("[迁移] dry-run 模式，不写入数据库")
        return

    for row in accounts:
        acc = _row_to_account(row)
        save_account(acc)
    print(f"[迁移] 已写入 {len(accounts)} 个账号")

    for s in settings:
        save_setting(s["key"], s["value"])
    print(f"[迁移] 已写入 {len(settings)} 条设置")


def migrate_from_enc(path: str, dry_run: bool = False):
    """从本地加密文件（data.enc）迁移到 MySQL"""
    from utils.store import _load_data  # 复用旧解密逻辑
    print(f"[迁移] 读取加密文件: {path}")
    data = _load_data() if path is None else _load_data_from_path(path)
    accounts = data.get("accounts", [])
    settings = data.get("settings", {})
    print(f"[迁移] 找到 {len(accounts)} 个账号, {len(settings)} 条设置")

    if dry_run:
        print("[迁移] dry-run 模式，不写入数据库")
        return

    from models import Account, Platform, AccountStatus, PlanType, CheckinInfo, QuotaInfo
    from datetime import datetime
    for d in accounts:
        # 用 store 内部的 _dict_to_account 等价逻辑：这里复用 models 反序列化
        acc = _dict_to_account_legacy(d)
        save_account(acc)
    for k, v in settings.items():
        save_setting(k, v if isinstance(v, str) else json.dumps(v))
    print(f"[迁移] 已写入 {len(accounts)} 个账号, {len(settings)} 条设置")


def _load_data_from_path(path: str) -> dict:
    """从指定路径的加密文件加载（复刻 store.decrypt_file）"""
    from utils.crypto import decrypt_file
    return decrypt_file(path)


def _dict_to_account_legacy(d: dict):
    """本地加密数据 dict -> Account（与 store._dict_to_account 一致）"""
    from models import Account, Platform, AccountStatus, PlanType, CheckinInfo, QuotaInfo
    from datetime import datetime
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
        account_group=getattr(d, "account_group", ""),
    )


def main():
    parser = argparse.ArgumentParser(description="迁移本地数据到 MySQL")
    parser.add_argument("--sqlite", default=os.path.expanduser("~/.antigravity-tools/antigravity.db"),
                        help="SQLite 数据文件路径")
    parser.add_argument("--enc", default=None, help="本地加密数据文件路径 (data.enc)")
    parser.add_argument("--dry-run", action="store_true", help="只读取不写入")
    args = parser.parse_args()

    if not os.environ.get("DB_CONF"):
        print("错误: 未设置环境变量 DB_CONF，请先设置 MySQL 连接配置（JSON）。")
        sys.exit(1)

    if args.enc:
        migrate_from_enc(args.enc, dry_run=args.dry_run)
    elif os.path.exists(args.sqlite):
        migrate_from_sqlite(args.sqlite, dry_run=args.dry_run)
    else:
        print(f"错误: 未找到数据源（sqlite={args.sqlite}）")
        sys.exit(1)


if __name__ == "__main__":
    main()
