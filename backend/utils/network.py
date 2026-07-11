"""出站网络配置"""

import os
from typing import Optional, Union

import certifi
import urllib3

from utils.store import load_setting


def get_outbound_proxy() -> Optional[str]:
    """获取出站 HTTP 代理：优先数据库 settings，其次环境变量 OUTBOUND_PROXY"""
    proxy = (load_setting("proxy", "") or "").strip()
    if proxy:
        return proxy
    env_proxy = (os.environ.get("OUTBOUND_PROXY") or "").strip()
    return env_proxy or None


def get_ssl_verify() -> Union[bool, str]:
    """集群节点若存在 HTTPS 中间人（自签证书），可设 HTTP_SSL_VERIFY=false"""
    val = os.environ.get("HTTP_SSL_VERIFY", "true").strip().lower()
    if val in ("0", "false", "no", "off"):
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        return False
    return certifi.where()


def get_outbound_proxies() -> dict:
    """供 requests 使用的 proxies 字典；无代理时显式禁用系统代理"""
    proxy = get_outbound_proxy()
    if proxy:
        return {"http": proxy, "https": proxy}
    return {"http": None, "https": None}
