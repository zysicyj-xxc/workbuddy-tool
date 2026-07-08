"""创建测试用旧版 SQLite 数据库"""
import sqlite3
import os

db_path = "c:/code/antigravity-web/test-old-data.db"
if os.path.exists(db_path):
    os.remove(db_path)

conn = sqlite3.connect(db_path)
c = conn.cursor()

# 创建 accounts 表（和旧版 schema 一致）
c.execute("""CREATE TABLE IF NOT EXISTS accounts (
    uid TEXT PRIMARY KEY, nickname TEXT DEFAULT '', platform TEXT DEFAULT 'codebuddy',
    status TEXT DEFAULT 'active', status_reason TEXT DEFAULT '', plan_type TEXT DEFAULT 'free',
    domain TEXT DEFAULT '', enterprise_id TEXT DEFAULT '', enterprise_name TEXT DEFAULT '',
    auth_token TEXT DEFAULT '', auth_raw TEXT DEFAULT '', ck TEXT DEFAULT '', api_key TEXT DEFAULT '',
    profile_raw TEXT DEFAULT '', usage_raw TEXT DEFAULT '',
    last_checkin_time TEXT, streak_days INTEGER DEFAULT 0, checkin_rewards TEXT DEFAULT '[]',
    daily_credit INTEGER DEFAULT 0, total_credits INTEGER DEFAULT 0,
    hourly_suggestions INTEGER DEFAULT 0, hourly_suggestions_limit INTEGER DEFAULT 0,
    weekly_chat INTEGER DEFAULT 0, weekly_chat_limit INTEGER DEFAULT 0,
    credits_remaining REAL DEFAULT 0, credits_total REAL DEFAULT 0,
    reset_time TEXT, quota_last_updated TEXT, quota_last_error TEXT, quota_last_error_at TEXT,
    created_at TEXT, last_used TEXT, account_group TEXT DEFAULT ''
)""")

# 插入2条测试数据
c.execute("""INSERT INTO accounts (uid, nickname, platform, status, plan_type, auth_token, api_key, ck, streak_days, daily_credit, total_credits, credits_remaining, credits_total, created_at, last_used)
VALUES ('test001', '测试账号1', 'codebuddy', 'active', 'free', 'ck_test001', 'ck_test001_secret', 'test001', 5, 100, 500, 350.5, 500, '2026-07-01T10:00:00', '2026-07-08T10:00:00')""")
c.execute("""INSERT INTO accounts (uid, nickname, platform, status, plan_type, auth_token, api_key, ck, streak_days, daily_credit, total_credits, credits_remaining, credits_total, created_at, last_used)
VALUES ('test002', '测试账号2', 'codebuddy', 'active', 'pro', 'ck_test002', 'ck_test002_secret', 'test002', 3, 100, 300, 280.0, 300, '2026-07-02T10:00:00', '2026-07-08T10:00:00')""")

# 创建 settings 表
c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT DEFAULT '')")
c.execute("INSERT INTO settings (key, value) VALUES ('proxy', 'http://127.0.0.1:7890')")

conn.commit()
conn.close()
print(f"测试数据库已创建: {db_path} ({os.path.getsize(db_path)} bytes)")
