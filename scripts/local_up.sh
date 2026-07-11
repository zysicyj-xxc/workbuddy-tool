#!/usr/bin/env bash
# 本地：构建并启动空库环境
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "[ok] 已生成 .env（请按需修改口令）"
fi

docker compose up -d --build
echo
echo "服务已启动："
echo "  管理端: http://localhost:${APP_PORT:-8000}"
echo "  代理端: http://localhost:${PROXY_PORT:-8002}"
echo "空库状态：请到「数据管理」导入 .enc 数据包，或运行："
echo "  ./scripts/import_package.sh /path/to/workbuddy-data.enc"
