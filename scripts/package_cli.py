#!/usr/bin/env python3
"""CLI：从 MySQL 导出 / 向 MySQL 导入数据包（不依赖 HTTP）

用法（在 backend 目录或设置 PYTHONPATH）：
  set DB_CONF=...
  set DATA_PACKAGE_PASSWORD=your-secret
  python scripts/package_cli.py export -o ../backup.enc
  python scripts/package_cli.py import -i ../backup.enc [--replace]
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


def cmd_export(args: argparse.Namespace) -> int:
    from utils.store import init_db
    from utils.crypto import encrypt_package
    from api.data import build_export_payload
    from modules.proxy_server import ProxyDatabase

    init_db()
    ProxyDatabase.get_instance()
    payload = build_export_payload()
    blob = encrypt_package(payload, password=args.password)
    out = args.output
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with open(out, "wb") as f:
        f.write(blob)
    print(f"[ok] exported {len(payload.get('accounts') or [])} accounts -> {out}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    from utils.store import init_db
    from utils.crypto import decrypt_package
    from api.data import apply_import_payload
    from modules.proxy_server import ProxyDatabase

    init_db()
    ProxyDatabase.get_instance()
    with open(args.input, "rb") as f:
        blob = f.read()
    payload = decrypt_package(blob, password=args.password)
    if not payload:
        print("[err] decrypt failed: wrong password or invalid package")
        return 1
    result = apply_import_payload(payload, replace=args.replace)
    print(result.get("message", result))
    return 0 if result.get("success") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="workbuddy MySQL 数据包 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_exp = sub.add_parser("export", help="从 MySQL 导出 .enc")
    p_exp.add_argument("-o", "--output", required=True)
    p_exp.add_argument("-p", "--password", default=None)
    p_exp.set_defaults(func=cmd_export)

    p_imp = sub.add_parser("import", help="导入 .enc 到 MySQL")
    p_imp.add_argument("-i", "--input", required=True)
    p_imp.add_argument("-p", "--password", default=None)
    p_imp.add_argument("--replace", action="store_true")
    p_imp.set_defaults(func=cmd_import)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
