#!/usr/bin/env bash
# 从运行中的 app 导出 MySQL 数据包到本地文件
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="${1:-./workbuddy-export-$(date +%Y%m%d-%H%M%S).enc}"
PASSWORD="${DATA_PACKAGE_PASSWORD:-workbuddy-change-me}"
PORT="${APP_PORT:-8000}"
AUTH_USER="${BASIC_AUTH_USER:-admin}"
AUTH_PASS="${BASIC_AUTH_PASSWORD:-}"

AUTH_ARGS=()
if [[ -n "$AUTH_PASS" ]]; then
  AUTH_ARGS=(-u "${AUTH_USER}:${AUTH_PASS}")
fi

curl -fsS "${AUTH_ARGS[@]}" \
  -X POST "http://127.0.0.1:${PORT}/api/data/export?password=$(python -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$PASSWORD")" \
  -o "$OUT"

echo "[ok] 已导出: $OUT"
