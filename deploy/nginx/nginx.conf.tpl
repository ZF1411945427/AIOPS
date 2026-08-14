# AIOps HTTPS 反向代理 + Let's Encrypt 自动续签
# 用法: DOMAIN=ops.example.com docker compose --profile https up -d
# ${DOMAIN} 由 docker-entrypoint.sh 的 envsubst 替换

events {
    worker_connections 1024;
}

http {
    include       mime.types;
    default_type  application/octet-stream;
    sendfile      on;
    keepalive_timeout 65;

    # HTTP → HTTPS 强制跳转
    server {
        listen 80;
        server_name ${DOMAIN};
        return 301 https://$host$request_uri;
    }

    # HTTPS 服务
    server {
        listen 443 ssl http2;
        server_name ${DOMAIN};

        ssl_certificate     /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
        ssl_protocols       TLSv1.2 TLSv1.3;
        ssl_ciphers         HIGH:!aNULL:!MD5;

        # HSTS
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

        # 后端代理
        location / {
            proxy_pass http://aiops:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 300s;
            proxy_send_timeout 300s;
        }

        # WebSocket 代理（容器日志/终端）
        location /containers/ {
            proxy_pass http://aiops:8000;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
        location /k8s-offline/ {
            proxy_pass http://aiops:8000;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }

        # 大文件上传
        client_max_body_size 100m;
    }
}