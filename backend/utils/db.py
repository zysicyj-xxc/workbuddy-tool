"""MySQL 数据库连接管理

使用 pymysql + DBUtils 连接池。连接配置整体通过环境变量 DB_CONF
（JSON 字符串）注入，例如：
  DB_CONF='{"host":"127.0.0.1","port":3306,"user":"workbuddy","passwd":"...","database":"antigravity","charset":"utf8mb4"}'

也支持 DB_CONF_FILE 指向 JSON 文件（便于本地开发，文件勿提交）。
源码中不包含任何连接主机/账号/凭据字面量。
"""

import os
import json
import threading
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor
from dbutils.pooled_db import PooledDB

_pool = None
_pool_lock = threading.Lock()


def _load_conf() -> dict:
    raw = os.environ.get("DB_CONF", "").strip()
    if not raw:
        conf_file = os.environ.get("DB_CONF_FILE", "").strip()
        if not conf_file:
            # 本地约定：backend/.db_conf.json（已 gitignore）
            default = os.path.join(os.path.dirname(__file__), "..", ".db_conf.json")
            if os.path.isfile(default):
                conf_file = default
        if conf_file and os.path.isfile(conf_file):
            with open(conf_file, "r", encoding="utf-8") as f:
                raw = f.read()
    if not raw:
        raise RuntimeError(
            "未配置数据库：请设置环境变量 DB_CONF（JSON）或 DB_CONF_FILE，"
            "或在 backend/.db_conf.json 放置本地配置（勿提交仓库）"
        )
    conf = json.loads(raw)
    if not isinstance(conf, dict) or not conf.get("host"):
        raise RuntimeError("DB_CONF JSON 无效：至少需要 host/user/passwd/database")
    # 兼容 password 字段名
    if "passwd" not in conf and "password" in conf:
        conf["passwd"] = conf.pop("password")
    conf.setdefault("charset", "utf8mb4")
    conf.setdefault("port", 3306)
    return conf


_conf = None


def get_conf() -> dict:
    global _conf
    if _conf is None:
        _conf = _load_conf()
    return _conf


def _create_pool() -> PooledDB:
    """创建（或返回已存在的）连接池"""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = PooledDB(
                    creator=pymysql,
                    maxconnections=10,
                    mincached=1,
                    maxcached=5,
                    maxshared=3,
                    blocking=True,
                    maxusage=None,
                    setsession=[],
                    ping=1,
                    cursorclass=DictCursor,
                    **get_conf(),
                )
    return _pool


def get_conn():
    """从连接池获取一个连接"""
    return _create_pool().connection()


@contextmanager
def get_cursor(commit: bool = False):
    """上下文管理器：自动获取连接/游标，退出时提交或回滚并归还连接"""
    conn = get_conn()
    cursor = conn.cursor()
    try:
        yield cursor
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def execute(sql: str, args=None, commit: bool = True):
    """执行写操作（INSERT/UPDATE/DELETE），返回受影响行数"""
    with get_cursor(commit=commit) as cursor:
        return cursor.execute(sql, args)


def query(sql: str, args=None):
    """执行查询，返回全部行（dict 列表）"""
    with get_cursor() as cursor:
        cursor.execute(sql, args)
        return cursor.fetchall()


def query_one(sql: str, args=None):
    """执行查询，返回第一行或 None"""
    with get_cursor() as cursor:
        cursor.execute(sql, args)
        return cursor.fetchone()
