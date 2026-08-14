#!/bin/sh
# 启动时用 DOMAIN 环境变量替换 nginx.conf 模板, 再启动 nginx
set -e

if [ -z "$DOMAIN" ]; then
  echo "ERROR: DOMAIN env required (e.g. ops.example.com)"; exit 1
fi

cp /etc/nginx/nginx.conf.tpl /etc/nginx/nginx.conf
envsubst '${DOMAIN}' < /etc/nginx/nginx.conf.tpl > /etc/nginx/nginx.conf

exec nginx -g 'daemon off;'