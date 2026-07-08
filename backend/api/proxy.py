"""API 代理管理 - 上游Key池、子Key、代理服务启停、统计"""

import logging
import os
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from modules.proxy_server import ProxyDatabase, ProxyServer, SUPPORTED_MODELS, MODEL_CONTEXT_LENGTHS
from utils.crypto import get_data_dir

router = APIRouter()
logger = logging.getLogger(__name__)

# 全局代理服务器实例（在 main.py 中管理生命周期）
_proxy_server: Optional[ProxyServer] = None


def get_proxy_server() -> Optional[ProxyServer]:
    global _proxy_server
    return _proxy_server


def set_proxy_server(s: Optional[ProxyServer]):
    global _proxy_server
    _proxy_server = s


# ─── 请求模型 ───

class AddUpstreamKeyRequest(BaseModel):
    api_key: str
    nickname: str = ""
    key_mode: int = 1  # 1=顺序, 2=随机, 3=负载均衡, 4=粘性会话
    allowed_models: list = []
    weight: int = 1
    max_points: float = 0  # 0=不限


class UpdateUpstreamKeyRequest(BaseModel):
    nickname: Optional[str] = None
    key_mode: Optional[int] = None
    allowed_models: Optional[list] = None
    weight: Optional[int] = None
    max_points: Optional[float] = None
    status: Optional[str] = None


class AddSubKeyRequest(BaseModel):
    name: str = ""
    key: str = ""  # 留空则自动生成随机 key
    key_mode: int = 1
    allowed_key_ids: list = []
    allowed_models: list = []
    daily_limit: int = 0  # 0=不限
    expires_at: str = ""


class UpdateSubKeyRequest(BaseModel):
    name: Optional[str] = None
    key_mode: Optional[int] = None
    allowed_key_ids: Optional[list] = None
    allowed_models: Optional[list] = None
    daily_limit: Optional[int] = None
    is_active: Optional[bool] = None


class ProxySettingsRequest(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8002
    mode: str = "local"  # local or open
    upstream_url: str = ""


class StartProxyRequest(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8002
    mode: str = "local"


# ─── 上游 Key 管理 ───

@router.get("/keys")
def list_upstream_keys():
    """获取上游 Key 列表"""
    db = ProxyDatabase.get_instance()
    return db.get_upstream_keys()


@router.post("/keys")
def add_upstream_key(req: AddUpstreamKeyRequest):
    """添加上游 Key - 生成 key_id、label 等必需字段"""
    db = ProxyDatabase.get_instance()
    key_data = {
        "key_id": f"ck_{secrets.token_hex(4)}",
        "api_key": req.api_key,
        "label": req.nickname or req.api_key[:12],
        "status": "active",
        "key_mode": req.key_mode,
        "allowed_models": req.allowed_models,
        "weight": req.weight,
        "max_points": req.max_points,
        "points": "",
        "points_updated_at": "",
        "packages": [],
        "used_count": 0,
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_tokens": 0,
        "total_cached_tokens": 0,
        "total_credits": 0.0,
        "last_used_at": "",
        "created_at": datetime.now().isoformat(),
        "min_credits_threshold": 50.0,
        "auto_enable_threshold": 100.0,
    }
    db.add_upstream_key(key_data)
    return {"success": True, "key_id": key_data["key_id"]}


@router.put("/keys/{key_id}")
def update_upstream_key(key_id: str, req: UpdateUpstreamKeyRequest):
    """更新上游 Key"""
    db = ProxyDatabase.get_instance()
    updates = {k: v for k, v in req.dict().items() if v is not None}
    db.update_upstream_key(key_id, updates)
    return {"success": True}


@router.delete("/keys/{key_id}")
def delete_upstream_key(key_id: str):
    """删除上游 Key"""
    db = ProxyDatabase.get_instance()
    db.delete_upstream_key(key_id)
    return {"success": True}


# ─── 子 Key 管理 ───

@router.get("/subkeys")
def list_sub_keys():
    """获取子 API Key 列表"""
    db = ProxyDatabase.get_instance()
    return db.get_sub_api_keys()


@router.post("/subkeys")
def add_sub_key(req: AddSubKeyRequest):
    """创建子 API Key - 生成 key_id、key 等必需字段

    若 req.key 非空则使用自定义 key，否则自动生成随机 key。
    """
    db = ProxyDatabase.get_instance()
    # key: 用户自定义优先，否则自动生成
    sub_key = req.key.strip() if req.key and req.key.strip() else f"sk-{secrets.token_urlsafe(32)}"
    key_data = {
        "key_id": f"sk_{secrets.token_hex(4)}",
        "key": sub_key,
        "name": req.name,
        "is_active": True,
        "key_mode": req.key_mode,
        "allowed_key_ids": req.allowed_key_ids,
        "allowed_models": req.allowed_models,
        "daily_limit": req.daily_limit,
        "daily_used": 0,
        "expires_at": req.expires_at,
        "created_at": datetime.now().isoformat(),
    }
    db.add_sub_api_key(key_data)
    return {"success": True, "key_id": key_data["key_id"], "key": key_data["key"]}


@router.put("/subkeys/{key_id}")
def update_sub_key(key_id: str, req: UpdateSubKeyRequest):
    """更新子 API Key"""
    db = ProxyDatabase.get_instance()
    updates = {k: v for k, v in req.dict().items() if v is not None}
    db.update_sub_api_key(key_id, updates)
    return {"success": True}


@router.delete("/subkeys/{key_id}")
def delete_sub_key(key_id: str):
    """删除子 API Key"""
    db = ProxyDatabase.get_instance()
    db.delete_sub_api_key(key_id)
    return {"success": True}


# ─── 代理服务控制 ───

@router.get("/status")
def get_proxy_status():
    """获取代理服务状态"""
    ps = get_proxy_server()
    db = ProxyDatabase.get_instance()
    settings = db.get_settings()
    return {
        "running": ps.is_running if ps else False,
        "base_url": ps.base_url if ps else "",
        "host": settings.get("host", "0.0.0.0"),
        "port": settings.get("port", 8002),
        "mode": settings.get("mode", "local"),
    }


@router.post("/start")
def start_proxy(req: StartProxyRequest):
    """启动代理服务"""
    ps = get_proxy_server()
    if ps and ps.is_running:
        raise HTTPException(400, "代理服务已在运行")

    try:
        server = ProxyServer(host=req.host, port=req.port, mode=req.mode)
        if server.start():
            set_proxy_server(server)
            # 保存设置
            db = ProxyDatabase.get_instance()
            db.update_settings({"host": req.host, "port": req.port, "mode": req.mode})
            return {"success": True, "base_url": server.base_url}
        else:
            raise HTTPException(500, "启动代理服务失败")
    except Exception as e:
        raise HTTPException(500, f"启动失败: {e}")


@router.post("/stop")
def stop_proxy():
    """停止代理服务"""
    ps = get_proxy_server()
    if not ps or not ps.is_running:
        raise HTTPException(400, "代理服务未运行")
    ps.stop()
    set_proxy_server(None)
    return {"success": True}


# ─── 统计与日志 ───

@router.get("/stats")
def get_proxy_stats(days: int = 7):
    """获取代理使用统计

    返回格式与前端字段匹配：
    - total_requests: 请求总数
    - total_prompt_tokens: 上行 Token 总数
    - total_completion_tokens: 下行 Token 总数
    - total_tokens: 总 Token
    - cached_tokens: 缓存命中 Token
    - total_credits: 消耗积分
    - success_count: 成功请求数
    - cache_hit_rate: 缓存命中率
    """
    db = ProxyDatabase.get_instance()
    raw = db.get_usage_summary(days=days)
    # 转换为前端期望的字段名
    return {
        "total_requests": raw.get("count", 0),
        "total_prompt_tokens": raw.get("prompt_tokens", 0),
        "total_completion_tokens": raw.get("completion_tokens", 0),
        "total_tokens": raw.get("total_tokens", 0),
        "cached_tokens": raw.get("cached_tokens", 0),
        "total_credits": raw.get("credits", 0.0),
        "success_count": raw.get("count", 0),
        "cache_hit_rate": raw.get("cache_hit_rate", 0.0),
    }


@router.get("/logs")
def get_proxy_logs(limit: int = 200):
    """获取请求日志"""
    db = ProxyDatabase.get_instance()
    return db.get_request_logs(limit=limit)


@router.get("/stats/by-client")
def get_stats_by_client(days: int = 7, limit: int = 20):
    """按客户端 User-Agent 维度聚合请求统计

    返回：
    [
      {client, requests, prompt_tokens, completion_tokens, total_tokens}, ...
    ]
    按 requests 降序。

    days: 1=今日 / 7=近7天 / 30=近30天 / 0或不传=所有日志聚合
    """
    db = ProxyDatabase.get_instance()
    return db.get_stats_by_client(days=days if days else None, limit=limit)


@router.get("/log-files")
def list_log_files():
    """获取日志文件列表

    读取 ~/.antigravity-tools/logs/ 目录，返回文件列表按修改时间倒序排列。
    """
    logs_dir = os.path.join(str(get_data_dir()), "logs")
    if not os.path.exists(logs_dir):
        return []
    result = []
    try:
        for filename in os.listdir(logs_dir):
            filepath = os.path.join(logs_dir, filename)
            if not os.path.isfile(filepath):
                continue
            stat = os.stat(filepath)
            result.append({
                "filename": filename,
                "size": stat.st_size,
                "modified_time": stat.st_mtime,
            })
    except OSError as e:
        logger.warning(f"读取日志目录失败: {e}")
        return []
    # 按修改时间倒序排列
    result.sort(key=lambda x: x.get("modified_time", 0), reverse=True)
    return result


@router.get("/log-files/{filename}")
def get_log_file_content(filename: str):
    """获取指定日志文件内容

    默认返回最后 500 行，避免响应过大。
    """
    # 防止路径穿越
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "无效的文件名")
    logs_dir = os.path.join(str(get_data_dir()), "logs")
    filepath = os.path.join(logs_dir, filename)
    if not os.path.exists(filepath) or not os.path.isfile(filepath):
        raise HTTPException(404, "日志文件不存在")
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        # 只返回最后 500 行
        tail_lines = all_lines[-500:] if len(all_lines) > 500 else all_lines
        content = "".join(tail_lines)
        return {
            "filename": filename,
            "content": content,
            "size": os.path.getsize(filepath),
            "lines": len(all_lines),
        }
    except OSError as e:
        raise HTTPException(500, f"读取日志文件失败: {e}")


@router.get("/packages")
def list_packages():
    """获取资源包列表（聚合所有上游 Key 的 packages，按到期时间升序排列）

    返回字段：
    - key_id / key_label：所属上游 Key
    - package_name / package_type：资源包名称与类型
    - cycle_remain：剩余积分
    - cycle_end：过期时间（字符串，可能为 ISO8601 或 "YYYY-MM-DD HH:MM:SS"）
    - cycle_end_ts：过期时间戳（解析失败为 None）
    - status：ok / exhausted / expired / unknown
    """
    from datetime import datetime as _dt

    def _parse_cycle_end(cycle_end: str):
        if not cycle_end:
            return None
        try:
            if "T" in cycle_end:
                dt = _dt.fromisoformat(cycle_end.replace("Z", "+00:00"))
                return dt.timestamp()
            try:
                return float(cycle_end)
            except ValueError:
                dt = _dt.strptime(cycle_end, "%Y-%m-%d %H:%M:%S")
                return dt.timestamp()
        except (ValueError, TypeError):
            return None

    db = ProxyDatabase.get_instance()
    keys = db.get_upstream_keys()
    now_ts = _dt.now().timestamp()
    result = []
    for k in keys:
        key_id = k.get("key_id", "")
        key_label = k.get("label", "")
        for pkg in k.get("packages", []) or []:
            if not isinstance(pkg, dict):
                continue
            cycle_remain = float(pkg.get("cycle_remain", 0) or 0)
            cycle_end = str(pkg.get("cycle_end", "") or "")
            end_ts = _parse_cycle_end(cycle_end)
            # 状态判定
            if cycle_remain <= 0:
                status = "exhausted"
            elif end_ts is None:
                status = "unknown"
            elif end_ts < now_ts:
                status = "expired"
            else:
                status = "ok"
            result.append({
                "key_id": key_id,
                "key_label": key_label,
                "package_name": pkg.get("package_name", ""),
                "package_type": pkg.get("package_type", ""),
                "cycle_remain": cycle_remain,
                "cycle_end": cycle_end,
                "cycle_end_ts": end_ts,
                "status": status,
            })
    # 按到期时间升序：有效且最快过期的排最前，无时间/已过期/已耗尽排后
    result.sort(key=lambda x: (
        0 if x["status"] == "ok" else 1,
        x["cycle_end_ts"] if x["cycle_end_ts"] is not None else float("inf"),
    ))
    return result


@router.get("/models")
def get_supported_models():
    """获取支持的模型列表"""
    models = []
    for model_id in SUPPORTED_MODELS:
        models.append({
            "id": model_id,
            "context_length": MODEL_CONTEXT_LENGTHS.get(model_id, 128000),
        })
    return models


# ─── 设置 ───

@router.get("/settings")
def get_proxy_settings():
    """获取代理设置"""
    db = ProxyDatabase.get_instance()
    return db.get_settings()


@router.put("/settings")
def update_proxy_settings(req: ProxySettingsRequest):
    """更新代理设置"""
    db = ProxyDatabase.get_instance()
    db.update_settings(req.dict())
    return {"success": True}
