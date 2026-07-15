"""webhook-deployer - 接收 CCR/GitHub webhook，触发 k8s rollout restart

设计原则：
- 单文件，无外部依赖（除 fastapi + kubernetes）
- 通过 in-cluster ServiceAccount 鉴权（最小权限：rollout restart 指定 namespace 的 deployment）
- 鉴权：客户端通过 X-Webhook-Token 头部 token 校验（环境变量 WEBHOOK_TOKEN）
- 健康检查：GET /health 返回 200（参考 hindsight 部署模式）

支持的 webhook 来源：
1. CCR 个人版镜像构建完成通知（POST /webhook/ccr）
2. 通用触发接口（POST /deploy/{namespace}/{deployment}）
3. GitHub Actions 完成通知（POST /webhook/github，解析 workflow run conclusion）
"""

import json
import logging
import os
import hmac
import hashlib
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# === 配置（环境变量） ===
WEBHOOK_TOKEN = os.environ.get("WEBHOOK_TOKEN", "")
# 默认部署到哪个 namespace（环境变量可覆盖）
DEFAULT_NAMESPACE = os.environ.get("DEFAULT_NAMESPACE", "workbuddy")
# 允许触发的 deployment 白名单（逗号分隔，空=不限制但需 token 正确）
ALLOWED_DEPLOYMENTS = [
    x.strip() for x in os.environ.get("ALLOWED_DEPLOYMENTS", "").split(",") if x.strip()
]

app = FastAPI(title="webhook-deployer", version="1.0.0")


# === K8s 客户端（in-cluster 模式） ===
_k8s_apps_api = None


def _get_k8s_apps_api():
    """延迟初始化 k8s 客户端（in-cluster 模式，使用 ServiceAccount token）"""
    global _k8s_apps_api
    if _k8s_apps_api is None:
        try:
            from kubernetes import client, config
            try:
                config.load_incluster_config()
            except Exception:
                # 本地调试 fallback
                config.load_kube_config()
            _k8s_apps_api = client.AppsV1Api()
        except ImportError:
            raise HTTPException(status_code=500, detail="kubernetes python client not installed")
    return _k8s_apps_api


def _verify_token(x_webhook_token: Optional[str]) -> None:
    """校验 webhook token"""
    if not WEBHOOK_TOKEN:
        # 未配置 token = 不鉴权（仅限内网测试，生产环境必须配置）
        logger.warning("WEBHOOK_TOKEN 未配置，跳过鉴权（仅限测试环境！）")
        return
    if not x_webhook_token or x_webhook_token != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="invalid or missing X-Webhook-Token")


def _rollout_restart(namespace: str, deployment: str) -> dict:
    """触发 k8s deployment 滚动重启（等价 kubectl rollout restart）"""
    if ALLOWED_DEPLOYMENTS and deployment not in ALLOWED_DEPLOYMENTS:
        raise HTTPException(
            status_code=403,
            detail=f"deployment {deployment} not in allowed list: {ALLOWED_DEPLOYMENTS}",
        )

    api = _get_k8s_apps_api()
    try:
        # 读取当前 deployment
        dep = api.read_namespaced_deployment(name=deployment, namespace=namespace)
        # 注入 restart 注解触发滚动更新
        annotations = dep.spec.template.metadata.annotations or {}
        annotations["kubectl.kubernetes.io/restartedAt"] = _now_iso()
        if not dep.spec.template.metadata.annotations:
            dep.spec.template.metadata.annotations = {}
        dep.spec.template.metadata.annotations = annotations

        api.patch_namespaced_deployment(name=deployment, namespace=namespace, body=dep)
        logger.info(f"[rollout restart] ns={namespace} deploy={deployment} OK")
        return {"namespace": namespace, "deployment": deployment, "status": "restarted"}
    except Exception as e:
        logger.error(f"[rollout restart] ns={namespace} deploy={deployment} FAILED: {e}")
        raise HTTPException(status_code=500, detail=f"rollout restart failed: {e}")


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# === 健康检查 ===
@app.get("/health")
@app.get("/")
def health():
    """健康检查端点"""
    return {"status": "ok", "service": "webhook-deployer", "version": "1.0.0"}


# === 通用部署接口 ===
@app.post("/deploy/{namespace}/{deployment}")
def deploy(namespace: str, deployment: str, x_webhook_token: Optional[str] = Header(None)):
    """通用部署接口：触发指定 namespace 的 deployment 滚动重启

    使用方式：
        curl -X POST https://webhook.zysicyj.top/deploy/workbuddy/workbuddy-tool \
             -H "X-Webhook-Token: <your-token>"
    """
    _verify_token(x_webhook_token)
    return _rollout_restart(namespace, deployment)


@app.post("/deploy/{deployment}")
def deploy_default(deployment: str, x_webhook_token: Optional[str] = Header(None)):
    """部署到默认 namespace（DEFAULT_NAMESPACE）"""
    _verify_token(x_webhook_token)
    return _rollout_restart(DEFAULT_NAMESPACE, deployment)


# === CCR webhook 接口 ===
@app.post("/webhook/ccr")
async def webhook_ccr(request: Request, x_webhook_token: Optional[str] = Header(None)):
    """腾讯云 CCR 个人版镜像构建完成通知

    CCR 控制台配置 webhook URL：https://webhook.zysicyj.top/webhook/ccr
    触发条件：镜像 push 完成

    通过查询参数 ?ns=xxx&deploy=yyy 指定要重启的 deployment
    例：https://webhook.zysicyj.top/webhook/ccr?ns=workbuddy&deploy=workbuddy-tool
    """
    _verify_token(x_webhook_token)
    ns = request.query_params.get("ns", DEFAULT_NAMESPACE)
    deploy_name = request.query_params.get("deploy", "")
    if not deploy_name:
        # 尝试从 body 解析镜像名推断（image 字段格式：ccr.ccs.tencentyun.com/zysicyj/<repo>:<tag>）
        try:
            body = await request.json()
            image = body.get("image") or body.get("push_data", {}).get("repository") or ""
            logger.info(f"[CCR webhook] 收到通知 image={image} body={json.dumps(body, ensure_ascii=False)[:300]}")
            # 推断 deployment：repo 名 == deployment 名时直接用
            # ccr.ccs.tencentyun.com/zysicyj/workbuddy-tool:xxx → workbuddy-tool
            if "/" in image:
                repo_tag = image.split("/")[-1]
                repo_name = repo_tag.split(":")[0]
                deploy_name = repo_name
        except Exception as e:
            logger.warning(f"[CCR webhook] 解析 body 失败: {e}")
    if not deploy_name:
        raise HTTPException(status_code=400, detail="missing ?deploy=xxx query param")
    return _rollout_restart(ns, deploy_name)


# === GitHub Actions webhook ===
@app.post("/webhook/github")
async def webhook_github(request: Request, x_webhook_token: Optional[str] = Header(None),
                          x_hub_signature_256: Optional[str] = Header(None)):
    """GitHub Actions / GitHub webhook 通知

    可选：通过 GITHUB_WEBHOOK_SECRET 校验 X-Hub-Signature-256
    解析 workflow_run conclusion == success 时触发部署
    """
    body_bytes = await request.body()

    # 校验 GitHub 签名（可选）
    github_secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    if github_secret and x_hub_signature_256:
        expected = "sha256=" + hmac.new(
            github_secret.encode(), body_bytes, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="invalid github signature")
    else:
        _verify_token(x_webhook_token)

    try:
        body = json.loads(body_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    event = request.headers.get("X-GitHub-Event", "")
    logger.info(f"[GitHub webhook] event={event} body_keys={list(body.keys())[:10]}")

    # workflow_run 事件：CI 跑完后触发部署
    if event == "workflow_run":
        conclusion = body.get("workflow_run", {}).get("conclusion")
        if conclusion != "success":
            return {"status": "skipped", "reason": f"conclusion={conclusion}"}
        ns = request.query_params.get("ns", DEFAULT_NAMESPACE)
        deploy_name = request.query_params.get("deploy", "")
        if not deploy_name:
            raise HTTPException(status_code=400, detail="missing ?deploy=xxx query param")
        return _rollout_restart(ns, deploy_name)

    # push 事件：直接部署
    if event == "push":
        ns = request.query_params.get("ns", DEFAULT_NAMESPACE)
        deploy_name = request.query_params.get("deploy", "")
        if not deploy_name:
            raise HTTPException(status_code=400, detail="missing ?deploy=xxx query param")
        return _rollout_restart(ns, deploy_name)

    return {"status": "ignored", "event": event}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
