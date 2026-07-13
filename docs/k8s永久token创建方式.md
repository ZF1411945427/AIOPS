# K8s 永久 Token 创建方式

## 背景

K8s 1.24+ 不再自动为 ServiceAccount 创建 Secret，`kubectl create token` 底层调用 **TokenRequest API**，生成的 JWT 强制带过期时间（`exp`），`--duration 0` 默认只有 **1 小时**。

## 创建永久 Token

```bash
# 1. 创建 ServiceAccount（如已有则跳过）
kubectl create sa admin-user -n kube-system

# 2. 绑定 cluster-admin 权限
kubectl create clusterrolebinding admin-user-binding \
  --clusterrole=cluster-admin \
  --serviceaccount=kube-system:admin-user

# 3. 创建长效 Secret（kubernetes.io/service-account-token 类型）
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: admin-user-token
  namespace: kube-system
  annotations:
    kubernetes.io/service-account.name: admin-user
type: kubernetes.io/service-account-token
EOF

# 4. 获取永久 Token（没有 exp 字段，永不过期）
kubectl get secret admin-user-token -n kube-system \
  -o jsonpath='{.data.token}' | base64 -d
```

## 验证

将输出的 token 粘贴到数据源的 `k8s_token` 字段，保存后测试连接。

## 命令对比

| 命令 | 底层 API | 有效期 | 是否永久 |
|------|---------|--------|---------|
| `kubectl create token ...` | TokenRequest | 默认 1 小时 | ❌ |
| `kubectl create token ... --duration 0` | TokenRequest | 默认 1 小时（0=默认值）| ❌ |
| `Secret type=kubernetes.io/service-account-token` | controller 自动管理 | 无过期时间 | ✅ |
