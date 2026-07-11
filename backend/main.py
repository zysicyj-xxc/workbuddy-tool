"""Antigravity Tools Web - FastAPI 后端入口"""

import base64
import logging
import os
import secrets as pysecrets
import sys
import threading

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

# 将 backend 目录加入 sys.path，使模块导入正常工作
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from utils.store import init_db, load_all_settings, save_setting, load_setting, load_accounts
from utils.network import get_outbound_proxy
from modules.proxy_server import ProxyServer, ProxyDatabase
from modules.checkin import CheckinManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Antigravity Tools Web", version="1.0.0")

# CORS - 允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── HTTP Basic Auth（BASIC_AUTH_PASSWORD 未设置时关闭，便于本地开发）───
BASIC_AUTH_USER = os.getenv("BASIC_AUTH_USER", "admin")
BASIC_AUTH_PASSWORD = os.getenv("BASIC_AUTH_PASSWORD", "")
# 探针 / 健康检查 / 版本信息免鉴权
_BASIC_AUTH_SKIP_PATHS = frozenset({"/api/health", "/health", "/api/version"})


@app.middleware("http")
async def basic_auth_middleware(request: Request, call_next):
    """全站 Basic Auth；未配置密码时跳过。"""
    if not BASIC_AUTH_PASSWORD:
        return await call_next(request)
    if request.method == "OPTIONS" or request.url.path in _BASIC_AUTH_SKIP_PATHS:
        return await call_next(request)

    auth = request.headers.get("Authorization", "")
    if auth.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth[6:].strip()).decode("utf-8")
            username, _, password = decoded.partition(":")
            user_ok = pysecrets.compare_digest(username, BASIC_AUTH_USER)
            pass_ok = pysecrets.compare_digest(password, BASIC_AUTH_PASSWORD)
            if user_ok and pass_ok:
                return await call_next(request)
        except Exception:
            pass

    return Response(
        content="Unauthorized",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="workbuddy"'},
        media_type="text/plain",
    )


@app.get("/api/health", include_in_schema=False)
def health():
    """K8s 探针用，不受 Basic Auth 保护。"""
    return {"status": "ok"}


@app.get("/api/version", include_in_schema=False)
def version_info():
    """前端左下角版本角标用；构建时注入 APP_VERSION / APP_BUILD_TIME / GIT_SHA。"""
    return {
        "version": os.getenv("APP_VERSION", "1.0.0"),
        "build_time": os.getenv("APP_BUILD_TIME", ""),
        "git_sha": os.getenv("GIT_SHA", ""),
    }

# 注册 API 路由
from api import accounts, checkin, quota, proxy, dashboard, data
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
app.include_router(checkin.router, prefix="/api/checkin", tags=["checkin"])
app.include_router(quota.router, prefix="/api/quota", tags=["quota"])
app.include_router(proxy.router, prefix="/api/proxy", tags=["proxy"])
app.include_router(data.router, prefix="/api/data", tags=["data"])

# ─── 后台调度器：每日定时签到（时间/开关存 MySQL settings，可热更新）───
_checkin_stop = threading.Event()
_checkin_thread = None


def _run_scheduled_checkin():
    """执行一次批量签到（失败自动重试3次），日志输出结果"""
    try:
        proxy = get_outbound_proxy()
        accounts_list = load_accounts()
        if not accounts_list:
            logger.info("[定时签到] 无账号，跳过")
            return
        manager = CheckinManager()
        success = failed = already = 0
        for account in accounts_list:
            if account.checkin.checked_today:
                already += 1
                continue
            result = manager.checkin_account_with_retry(account, proxy=proxy, retries=3)
            if result.get("success"):
                if result.get("already"):
                    already += 1
                else:
                    success += 1
            else:
                failed += 1
                logger.warning(
                    f"[定时签到] 账号 {account.display_name} 签到失败: "
                    f"{result.get('error', '未知错误')}"
                )
        logger.info(
            f"[定时签到] 完成: 成功 {success}, 失败 {failed}, 已签 {already}"
        )
    except Exception as e:
        logger.error(f"[定时签到] 异常: {e}", exc_info=True)


def _checkin_scheduler_loop():
    """定时签到调度循环：读 settings，支持开关与时间热更新。"""
    from datetime import datetime, timedelta
    from api.checkin import get_schedule_config, wait_schedule_interrupt

    logger.info("[定时签到] 调度器已启动")
    while not _checkin_stop.is_set():
        cfg = get_schedule_config()
        if not cfg["enabled"]:
            logger.info("[定时签到] 已关闭，60 秒后复查配置")
            reason = wait_schedule_interrupt(_checkin_stop, 60)
            if reason == "stop":
                return
            continue

        hour, minute = cfg["hour"], cfg["minute"]
        now = datetime.now()
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        logger.info(
            f"[定时签到] 下次签到: {next_run.strftime('%Y-%m-%d %H:%M:%S')} "
            f"（每日 {hour:02d}:{minute:02d}）"
        )

        interrupted = False
        while not _checkin_stop.is_set():
            now = datetime.now()
            remain = (next_run - now).total_seconds()
            if remain <= 0:
                break
            reason = wait_schedule_interrupt(_checkin_stop, min(remain, 60))
            if reason == "stop":
                return
            if reason == "reload":
                interrupted = True
                break
            cfg2 = get_schedule_config()
            if (
                not cfg2["enabled"]
                or cfg2["hour"] != hour
                or cfg2["minute"] != minute
            ):
                interrupted = True
                break

        if _checkin_stop.is_set():
            return
        if interrupted:
            continue

        cfg3 = get_schedule_config()
        if not cfg3["enabled"]:
            continue
        logger.info("[定时签到] 触发签到")
        _run_scheduled_checkin()


@app.on_event("startup")
def on_startup():
    """启动时初始化数据库、自动启动代理、启动定时签到"""
    if BASIC_AUTH_PASSWORD:
        logger.info(f"Basic Auth 已启用（用户: {BASIC_AUTH_USER}）")
    else:
        logger.warning("Basic Auth 未启用（未设置 BASIC_AUTH_PASSWORD）")
    init_db()
    # 初始化 ProxyDatabase 单例
    ProxyDatabase.get_instance()
    logger.info("数据库已初始化")

    # 自动启动代理：读取上次保存的设置，若有上游 Key 则自动启动
    try:
        db = ProxyDatabase.get_instance()
        settings = db.get_settings()
        host = settings.get("host", "0.0.0.0")
        port = int(settings.get("port", 8002))
        mode = settings.get("mode", "local")
        upstream_keys = db.get_upstream_keys()
        if upstream_keys:
            server = ProxyServer(host=host, port=port, mode=mode)
            if server.start():
                from api.proxy import set_proxy_server
                set_proxy_server(server)
                logger.info(f"代理服务自动启动: http://{host}:{port}（{mode}）")
            else:
                logger.warning("代理服务自动启动失败")
        else:
            logger.info("无上游 Key，跳过代理自动启动")
    except Exception as e:
        logger.error(f"代理自动启动异常: {e}", exc_info=True)

    # 启动定时签到守护线程
    global _checkin_thread
    _checkin_thread = threading.Thread(
        target=_checkin_scheduler_loop, name="checkin-scheduler", daemon=True
    )
    _checkin_thread.start()


@app.on_event("shutdown")
def on_shutdown():
    """关闭时停止代理服务和定时签到线程"""
    # 停止定时签到
    _checkin_stop.set()
    if _checkin_thread and _checkin_thread.is_alive():
        _checkin_thread.join(timeout=3)
    # 停止代理服务
    from api.proxy import get_proxy_server
    ps = get_proxy_server()
    if ps and ps.is_running:
        ps.stop()
        logger.info("代理服务已停止")


# 前端静态文件（构建后）
_frontend_dist = os.path.join(backend_dir, "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    # /assets 由 StaticFiles 直接提供（JS/CSS 带 hash，可长期缓存）
    _assets_dir = os.path.join(_frontend_dist, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="frontend-assets")

    # SPA fallback：所有未匹配 API 路由的 GET 请求都返回前端页面
    # - 优先尝试返回 dist 根目录的实际文件（如 favicon.ico、vite.svg）
    # - 否则返回 index.html，交给 vue-router 处理前端路由（如 /checkin）
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # API 404 不走 SPA fallback，返回 JSON 错误
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        # 尝试返回 dist 根目录中的实际文件
        candidate = os.path.normpath(os.path.join(_frontend_dist, full_path))
        if (
            full_path
            and candidate.startswith(_frontend_dist)
            and os.path.isfile(candidate)
        ):
            return FileResponse(candidate)
        # 其余路径返回 index.html，由 vue-router 接管
        return FileResponse(os.path.join(_frontend_dist, "index.html"))
