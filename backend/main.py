"""Antigravity Tools Web - FastAPI 后端入口"""

import logging
import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 将 backend 目录加入 sys.path，使模块导入正常工作
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from utils.store import init_db, load_all_settings, save_setting, load_setting
from modules.proxy_server import ProxyServer, ProxyDatabase

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

# 注册 API 路由
from api import accounts, checkin, quota, proxy, dashboard, data
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
app.include_router(checkin.router, prefix="/api/checkin", tags=["checkin"])
app.include_router(quota.router, prefix="/api/quota", tags=["quota"])
app.include_router(proxy.router, prefix="/api/proxy", tags=["proxy"])
app.include_router(data.router, prefix="/api/data", tags=["data"])

@app.on_event("startup")
def on_startup():
    """启动时初始化数据库"""
    init_db()
    # 初始化 ProxyDatabase 单例
    ProxyDatabase.get_instance()
    logger.info("数据库已初始化")


@app.on_event("shutdown")
def on_shutdown():
    """关闭时停止代理服务"""
    from api.proxy import get_proxy_server
    ps = get_proxy_server()
    if ps and ps.is_running:
        ps.stop()
        logger.info("代理服务已停止")


# 前端静态文件（构建后）
_frontend_dist = os.path.join(backend_dir, "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
