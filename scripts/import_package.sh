#!/usr/bin/env bash
# 向空库/本地实例导入 .enc 数据包
set -euo pipefail
cd "$(dirname "$0")/.."

ENC_FILE="${1:-}"
if [[ -z "$ENC_FILE" || ! -f "$ENC_FILE" ]]; then
  echo "用法: $0 <workbuddy-data.enc> [--replace]"
  exit 1
fi

REPLACE=false
if [[ "${2:-}" == "--replace" ]]; then
  REPLACE=true
fi

PASSWORD="${DATA_PACKAGE_PASSWORD:-workbuddy-change-me}"
PORT="${APP_PORT:-8000}"
AUTH_USER="${BASIC_AUTH_USER:-admin}"
AUTH_PASS="${BASIC_AUTH_PASSWORD:-}"

AUTH_ARGS=()
if [[ -n "$AUTH_PASS" ]]; then
  AUTH_ARGS=(-u "${AUTH_USER}:${AUTH_PASS}")
fi

curl -fsS "${AUTH_ARGS[@]}" \
  -X POST "http://127.0.0.1:${PORT}/api/data/import-encrypted" \
  -F "file=@${ENC_FILE}" \
  -F "password=${PASSWORD}" \
  -F "replace=${REPLACE}"

echo
echo "[ok] 导入请求已完成"
