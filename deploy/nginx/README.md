# HTTPS 部署指南

三步让你的 AIOps 平台走 HTTPS(Let's Encrypt 免费证书 + 自动续签)。

## 前提

- 一个域名(国内需备案), 解析到部署服务器公网 IP
- 服务器 80/443 端口对外可访问

## 步骤

1. **配 .env**(复制 .env.example 后再填):
   ```bash
   cp .env.example .env
   ```
   填上:
   ```
   DOMAIN=ops.example.com          # 你的域名
   CERTBOT_EMAIL=admin@example.com # 证书到期通知邮箱
   ```

2. **启动 HTTPS 栈**(会自动申请证书, 首次 1-2 分钟):
   ```bash
   docker compose --profile https up -d
   ```
   如需同时监控栈: `docker compose --profile https --profile monitoring up -d`

3. **验证**:
   ```bash
   curl -I https://ops.example.com/healthz
   ```
   应返回 200, 且响应头含 `Strict-Transport-Security`。

## 说明

| 组件 | 角色 |
|------|------|
| nginx | 反向代理, 80→443 强制跳转, 转发到 aiops:8000, 支持 WebSocket |
| certbot | 首次签发证书, 之后每 12h 检测自动续签 |

- 证书存于 docker volume `certbot-conf`, 容器重建不丢失
- 反向代理已透传 `X-Forwarded-Proto`, 后端可感知 HTTPS 请求
- 放行 443 后原 `AIOPS_PORT`(8000) 端口仍可直连(内网用), 公网请通过 443

## 常见问题

- **证书申请失败**: 确认域名 DNS 已解析到本机公网 IP, 且 80 端口未被占用
- **HSTS 生效后想退回 HTTP**: 清浏览器缓存, 或删除 `Strict-Transport-Security` header