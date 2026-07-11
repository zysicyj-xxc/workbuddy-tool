#!/usr/bin/env bash
# 可选：mysqldump 原始备份（含结构+数据）。敏感，勿上传仓库。
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="${1:-./backups/antigravity-$(date +%Y%m%d-%H%M%S).sql}"
mkdir -p "$(dirname "$OUT")"

MYSQL_USER="${MYSQL_USER:-workbuddy}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-workbuddy_pass}"

docker compose exec -T mysql \
  mysqldump -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" \
  --single-transaction --routines --triggers antigravity > "$OUT"

echo "[ok] MySQL dump: $OUT"
