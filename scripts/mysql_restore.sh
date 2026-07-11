#!/usr/bin/env bash
# 可选：把 mysqldump 灌进当前 compose MySQL（空库验证用）
set -euo pipefail
cd "$(dirname "$0")/.."

SQL_FILE="${1:-}"
if [[ -z "$SQL_FILE" || ! -f "$SQL_FILE" ]]; then
  echo "用法: $0 <dump.sql>"
  exit 1
fi

MYSQL_USER="${MYSQL_USER:-workbuddy}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-workbuddy_pass}"

docker compose exec -T mysql \
  mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" antigravity < "$SQL_FILE"

echo "[ok] 已导入 SQL: $SQL_FILE"
