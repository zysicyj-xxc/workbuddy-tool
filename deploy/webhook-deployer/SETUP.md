# CCR 自动构建配置说明

## 目标
push 代码到 GitHub main 分支 → CCR 自动构建 docker 镜像 → 推送到 ccr.ccs.tencentyun.com/zysicyj → webhook 触发 k8s 滚动更新

## 一、腾讯云控制台配置（2 个镜像仓库）

### 1. 主应用镜像：workbuddy-tool
1. 登录腾讯云控制台 → 容器镜像服务 → 个人版 → 镜像仓库
2. 命名空间：`zysicyj`（已有则跳过）
3. 新建仓库：`workbuddy-tool`（如果已有跳过）
   - 类型：私有
4. 进入仓库 → **构建配置** → 新增配置
   - 代码源：GitHub
   - 授权：授权腾讯云访问 GitHub `zysicyj-xxc/workbuddy-tool` 仓库（首次需 OAuth 授权）
   - 分支：`main`
   - Dockerfile 路径：`Dockerfile`（仓库根目录）
   - 构建触发：**Push 到分支自动构建**（勾选）
   - 镜像标签规则：
     - `latest`（固定标签，每次构建覆盖）
     - `{sha-prefix}`（commit 前 7 位，便于回滚，可选加）
     - `{version}`（如 1.0.4，从 package.json 读，可选）

### 2. webhook-deployer 镜像
- 仓库：`webhook-deployer`
- Dockerfile 路径：`deploy/webhook-deployer/Dockerfile`
- 分支：`main`
- 标签：`latest`
- 其余配置同上

## 二、CCR Webhook 通知配置

CCR 个人版镜像仓库构建完成后，需要触发 webhook-deployer 调 k8s rollout restart。

### CCR 控制台 → 镜像仓库 → workbuddy-tool → Webhook
- 新增 webhook：
  - URL：`https://webhook.zysicyj.top/webhook/ccr?ns=workbuddy&deploy=workbuddy-tool`
  - 触发动作：镜像 push 完成
  - 自定义 Header：`X-Webhook-Token: <你的 token>`（与 k8s secret `webhook-deployer-token` 中的 WEBHOOK_TOKEN 一致）

## 三、k8s 部署 webhook-deployer（一次性）

```bash
# 1. 生成 token 并创建 secret
TOKEN=$(openssl rand -hex 16)
echo "保存此 token 用于 CCR webhook Header: $TOKEN"
kubectl create ns webhook
kubectl create secret generic webhook-deployer-token \
  -n webhook --from-literal=WEBHOOK_TOKEN=$TOKEN

# 2. 确认 ccr-registry secret 在 webhook namespace
#    （如果只在 default/workbuddy ns 有，需复制过来）
kubectl get secret ccr-registry -n default -o yaml \
  | sed 's/namespace: default/namespace: webhook/' \
  | kubectl apply -f -
# 或从 workbuddy 复制
kubectl get secret ccr-registry -n workbuddy -o yaml \
  | sed 's/namespace: workbuddy/namespace: webhook/' \
  | kubectl apply -f -

# 3. 确认 TLS 证书 secret
kubectl get secret zysicyj-tls -n default -o yaml \
  | sed 's/namespace: default/namespace: webhook/' \
  | kubectl apply -f -

# 4. 删除旧 webhook ingress（如果存在）
kubectl delete ingress -A -l app=webhook-deployer --ignore-not-found
# 或手动查：kubectl get ingress -A | grep webhook

# 5. 部署 webhook-deployer
kubectl apply -f deploy/webhook-deployer/k8s.yaml

# 6. 等待镜像构建（首次需在 CCR 控制台手动触发构建一次）
kubectl rollout status deploy/webhook-deployer -n webhook

# 7. 验证健康检查
curl https://webhook.zysicyj.top/health
# 应返回：{"status":"ok","service":"webhook-deployer","version":"1.0.0"}

# 8. 测试触发部署（手动调一次）
curl -X POST https://webhook.zysicyj.top/deploy/workbuddy/workbuddy-tool \
  -H "X-Webhook-Token: $TOKEN"
# 应返回：{"namespace":"workbuddy","deployment":"workbuddy-tool","status":"restarted"}
```

## 四、完整触发链路验证

1. 本地改代码 → `git push origin main`
2. CCR 自动检测 push → 构建 workbuddy-tool 镜像 → push 到 ccr.ccs.tencentyun.com/zysicyj/workbuddy-tool:latest
3. CCR 构建完成 → POST `https://webhook.zysicyj.top/webhook/ccr?ns=workbuddy&deploy=workbuddy-tool`
4. webhook-deployer 校验 token → k8s API patch deployment/workbuddy-tool 注入 restartedAt 注解
5. k8s 自动滚动更新 → 新 Pod 拉取 `:latest` 镜像（注意：原 workbuddy-tool deployment 的 imagePullPolicy 已是 Always）
6. 验证：`kubectl rollout status deploy/workbuddy-tool -n workbuddy`

## 注意

- **镜像 tag**：k8s.yaml 中 workbuddy-tool 的 image 用的是 `ccr.ccs.tencentyun.com/zysicyj/workbuddy-tool:<sha>` 形式（原 GitHub Actions 用 sha tag）。改用 CCR 自动构建后，imagePullPolicy=Always，image 应改为 `:latest`（每次 push 自动覆盖），否则 sha tag 不会更新。
  **需要改 deploy/k8s.yaml 中 workbuddy-tool deployment 的 image tag**。

- **webhook-deployer 自身更新**：webhook-deployer 的镜像变更需要手动 `kubectl rollout restart deploy/webhook-deployer -n webhook`（或配置一个自触发，但容易死循环，不推荐）。

- **token 保存**：webhook-deployer-token secret 的 WEBHOOK_TOKEN 务必保存好，需要在 CCR webhook Header 中使用同一值。
