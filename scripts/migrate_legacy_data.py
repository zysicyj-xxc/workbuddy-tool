#!/usr/bin/env python3
"""把旧版 ~/.antigravity-tools 数据转为 WBDP 口令包，并可直接导入到当前 MySQL。

旧 data.enc 用本机 secret.key（Fernet）加密，Docker/新环境无法直接解。
本脚本在宿主机用原密钥解密，再打成跨环境口令包。

用法：
  python scripts/migrate_legacy_data.py
  python scripts/migrate_legacy_data.py --dir C:\\Users\\zysic\\.antigravity-tools --import-http
  python scripts/migrate_legacy_data.py --import-db --replace
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))


def load_legacy(data_dir: Path) -> dict:
    from cryptography.fernet import Fernet

    key_path = data_dir / "secret.key"
    enc_path = data_dir / "data.enc"
    proxy_path = data_dir / "proxy_db.json"
    sqlite_path = data_dir / "antigravity.db"

    accounts = []
    settings = {}

    if enc_path.is_file() and key_path.is_file():
        key = key_path.read_bytes()
        blob = enc_path.read_bytes()
        raw = Fernet(key).decrypt(blob)
        data = json.loads(raw.decode("utf-8"))
        accounts = data.get("accounts") or []
        settings = data.get("settings") or {}
        print(f"[ok] data.enc: {len(accounts)} accounts, {len(settings)} settings")
    elif sqlite_path.is_file():
        import sqlite3

        conn = sqlite3.connect(str(sqlite_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM accounts").fetchall()
        # 交给 import 侧 _dict_to_account 不直接兼容 sqlite row；这里走 HTTP/DB 前先转成 dict 包
        # 简化：用 migrate_to_mysql 路径 —— 直接读 row dict 字段打成 export 结构较繁琐
        # 优先建议有 data.enc；若仅有 sqlite，提示用 UI「导入 SQLite」
        print(f"[warn] 仅有 SQLite ({len(rows)} 行)。请用 UI「导入 SQLite .db」或加 --sqlite-http")
        conn.close()
        if not accounts:
            raise SystemExit("没有可从 data.enc 读取的账号；请改用 UI 导入 antigravity.db")
    else:
        raise SystemExit(f"未找到 data.enc+secret.key: {data_dir}")

    proxy = {"upstream_keys": [], "sub_api_keys": [], "settings": {}}
    if proxy_path.is_file():
        pj = json.loads(proxy_path.read_text(encoding="utf-8"))
        proxy = {
            "upstream_keys": pj.get("upstream_keys") or [],
            "sub_api_keys": pj.get("sub_api_keys") or [],
            "settings": pj.get("settings") or {},
        }
        print(
            f"[ok] proxy_db.json: upstream={len(proxy['upstream_keys'])} "
            f"sub={len(proxy['sub_api_keys'])}"
        )

    return {
        "version": 3,
        "format": "mysql+proxy",
        "source": str(data_dir),
        "accounts": accounts,
        "settings": settings,
        "proxy": proxy,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dir",
        default=str(Path.home() / ".antigravity-tools"),
        help="旧数据目录",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(ROOT / "backups" / "legacy-migrated.enc"),
        help="输出 WBDP 口令包路径",
    )
    parser.add_argument("-p", "--password", default=None)
    parser.add_argument(
        "--import-http",
        action="store_true",
        help="通过 http://127.0.0.1:8000 导入（写入 compose 容器）",
    )
    parser.add_argument(
        "--import-db",
        action="store_true",
        help="本机直连 DB_CONF 导入（不写容器内 proxy 卷）",
    )
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--port", default=os.environ.get("APP_PORT", "8000"))
    args = parser.parse_args()

    data_dir = Path(args.dir)
    payload = load_legacy(data_dir)

    from utils.crypto import encrypt_package, get_package_password

    password = get_package_password(args.password)
    blob = encrypt_package(payload, password=password)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    print(f"[ok] wrote WBDP package: {out} ({len(blob)} bytes)")

    if args.import_db:
        if not os.environ.get("DB_CONF"):
            os.environ["DB_CONF"] = json.dumps(
                {
                    "host": "127.0.0.1",
                    "port": 3306,
                    "user": "workbuddy",
                    "passwd": "workbuddy_pass",
                    "database": "antigravity",
                    "charset": "utf8mb4",
                }
            )
        from utils.store import init_db
        from api.data import apply_import_payload
        from modules.proxy_server import ProxyDatabase

        init_db()
        ProxyDatabase.get_instance()
        result = apply_import_payload(payload, replace=args.replace)
        print(result.get("message", result))

    if args.import_http:
        import urllib.request

        boundary = "----workbuddyBoundary7MA4YWxkTrZu0gW"
        body = []
        def add(name, value, filename=None, content_type=None):
            body.append(f"--{boundary}".encode())
            if filename:
                body.append(
                    f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode()
                )
                body.append(f"Content-Type: {content_type or 'application/octet-stream'}".encode())
                body.append(b"")
                body.append(value if isinstance(value, bytes) else value.encode())
            else:
                body.append(f'Content-Disposition: form-data; name="{name}"'.encode())
                body.append(b"")
                body.append(value.encode() if isinstance(value, str) else value)

        add("file", blob, filename=out.name)
        add("password", password)
        add("replace", "true" if args.replace else "false")
        body.append(f"--{boundary}--".encode())
        body.append(b"")
        data = b"\r\n".join(body)
        req = urllib.request.Request(
            f"http://127.0.0.1:{args.port}/api/data/import-encrypted",
            data=data,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            text = resp.read().decode("utf-8")
            print("[http]", text)

    print("[hint] 浏览器导入请选:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
