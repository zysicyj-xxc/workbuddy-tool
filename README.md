# workbuddy-tool

腾讯 CodeBuddy / WorkBuddy 账号管理、签到、资源包与本地 API 代理。账号与设置持久化在 **MySQL**；代理 Key 落在本地数据卷。

## 快速开始（空库 + 导入数据包）

```bash
cp .env.example .env
# Windows PowerShell:
Copy-Item .env.example .env

docker compose up -d --build
```

打开 http://localhost:8000 → **数据管理** → 导入 `.enc` 数据包。

或用脚本：

```bash
# Git Bash / WSL
./scripts/local_up.sh
./scripts/import_package.sh ./your-backup.enc

# 或直接 CLI（需已配置 DB_CONF）
python scripts/package_cli.py import -i ./your-backup.enc
```

默认开发口令见 `.env.example` 中 `DATA_PACKAGE_PASSWORD`，**开源/部署前务必改掉**。

## 配置（敏感信息勿入库）

| 变量 | 说明 |
|------|------|
| `DB_CONF` | MySQL JSON：`host/port/user/passwd/database/charset` |
| `DB_CONF_FILE` / `backend/.db_conf.json` | 本地文件方式（已 gitignore） |
| `DATA_PACKAGE_PASSWORD` | 跨环境导出/导入口令 |
| `BASIC_AUTH_PASSWORD` | 管理端 Basic Auth；空则关闭 |
| `OUTBOUND_PROXY` | 可选出站代理 |
| `HTTP_SSL_VERIFY` | `false` 时跳过 TLS 校验（仅特殊网络） |

生产凭据用 Secret / `.env` 注入，**不要**提交：

- `.env`、`backend/.db_conf.json`、`backend/.docker.env`
- `*.enc`、`*.db`、`proxy_db.json`、`secret.key`
- `backups/`、mysqldump 产物

## 数据包格式

- **v3（推荐）**：口令派生 Fernet（包头 `WBDP`），可跨机器、空库导入
- **旧版**：本机 `secret.key` 加密的 `.enc`，仅同机可解
- **遗留**：SQLite `.db` 可通过「导入 SQLite」写入 MySQL

导出内容：MySQL `accounts` + `settings` + 代理 upstream/sub keys。

## 常用脚本

| 脚本 | 作用 |
|------|------|
| `scripts/local_up.sh` | 生成 `.env` 并 `compose up` |
| `scripts/export_package.sh` | HTTP 导出 `.enc` |
| `scripts/import_package.sh` | HTTP 导入 `.enc` |
| `scripts/package_cli.py` | 不经 HTTP，直连 MySQL 导出/导入 |
| `scripts/mysql_dump.sh` / `mysql_restore.sh` | 可选原生 SQL 备份 |

## 开发（不用 Docker 跑前端）

```bash
# MySQL 可用 compose 只起库：
docker compose up -d mysql

# backend/.db_conf.json 示例（勿提交）：
# {"host":"127.0.0.1","port":3306,"user":"workbuddy","passwd":"workbuddy_pass","database":"antigravity","charset":"utf8mb4"}

cd backend && pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000

cd frontend && npm ci && npm run dev
```

## K8s

见 `deploy/k8s.yaml`。`workbuddy-db-conf` / `workbuddy-basic-auth` 需集群内单独创建 Secret，清单内不含明文密码。

## License

按仓库 LICENSE 为准；开源前请自查无账号 Token、API Key、数据库地址进入 Git 历史。
