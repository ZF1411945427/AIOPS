"""子模块(由 component_catalog 拆分生成, 勿手改函数体)"""
import json
import re
import socket
import base64
import time
import threading
from datetime import datetime
from typing import Optional, List

from sqlalchemy.orm import Session

from app.models import Asset, ComponentCatalog, ComponentInstall

import logging
logger = logging.getLogger(__name__)

from app.services.component_catalog_data import _OFFLINE_PUBLIC_SOURCES  # noqa
from app.services.component_catalog_data import _BUILTIN_COMPONENTS  # noqa


# ─── 原 L660-674 ───
def build_default_compose(name: str, image: str, port: int) -> str:
    """为组件生成默认单节点 docker compose 内容"""
    return f"""version: '3.8'
services:
  {name}:
    image: {image}
    container_name: aiops-{name}
    ports:
      - "{port}:{port}"
    volumes:
      - {name}_data:/data
    restart: unless-stopped
volumes:
  {name}_data:
"""


# ─── 原 L677-682 ───
def _param_value(schema_item: dict, params: dict):
    """取参数最终值: 用户传参优先, 否则默认值。key 不在 params 时回退 default。"""
    key = schema_item.get("key")
    if params and key in params and params.get(key) is not None and params.get(key) != "":
        return params.get(key)
    return schema_item.get("default")


# ─── 原 L685-752 ───
def render_compose(comp: dict, params: dict, port: int = 0, offline_image: str = "") -> str:
    """按组件 param_schema + 用户定制参数渲染 docker compose。

    参数经 schema 的 env 字段映射到容器环境变量; db_port 覆盖宿主机映射端口;
    组件特殊命令(redis --requirepass / es ES_JAVA_OPTS 等)按 name 分支生成。
    offline_image 非空时用其替换镜像(离线私有仓库地址), 否则用组件默认镜像。
    """
    name = comp["name"]
    image = offline_image or (comp.get("docker_image") or "")
    schema = comp.get("param_schema") or []
    p = params or {}
    service_port = int(p.get("db_port") or port or comp.get("default_port") or 0) or 0

    env_lines = []
    for item in schema:
        env_name = item.get("env")
        if not env_name:
            continue
        val = _param_value(item, p)
        if val is None or val == "":
            continue
        if item.get("type") == "bool":
            _v = "true" if val else "false"
        else:
            _v = str(val)
        env_lines.append(f"      {env_name}: {json.dumps(_v, ensure_ascii=False)}")

    # 组件特殊处理: 容器启动命令 / 额外环境变量
    extra_env = []
    command = None
    if name == "redis":
        pw = _param_value({"key": "redis_password", "default": ""}, p) or ""
        args = ["redis-server"]
        if pw:
            args.append(f"--requirepass {pw}")
        mm = _param_value({"key": "maxmemory", "default": ""}, p) or ""
        if mm:
            args.append(f"--maxmemory {mm}")
        command = " ".join(args)
    elif name == "elasticsearch":
        heap = _param_value({"key": "es_jvm_heap", "default": "512m"}, p) or "512m"
        extra_env.append(f"      ES_JAVA_OPTS: {json.dumps('-Xms%s -Xmx%s' % (heap, heap), ensure_ascii=False)}")

    env_block = "\n".join(env_lines + extra_env)

    # 端口列表: 主端口 + 可选附加端口(如 rabbitmq 管理端口)
    port_lines = [f'      - "{service_port}:{service_port}"']
    if name == "rabbitmq":
        mq = _param_value({"key": "mq_port", "default": "15672"}, p) or "15672"
        port_lines.append(f'      - "{int(mq)}:15672"')

    ports_block = "\n".join(port_lines)
    cmd_block = f"\n    command: {json.dumps(command, ensure_ascii=False)}" if command else ""

    return f"""version: '3.8'
services:
  {name}:
    image: {image}
    container_name: aiops-{name}
    ports:
{ports_block}
{env_block}
    volumes:
      - {name}_data:/data
    restart: unless-stopped{cmd_block}
volumes:
  {name}_data:
"""


# ─── 原 L755-769 ───
def _offline_native_block(script: str) -> str:
    """离线二次强制校验: native 安装脚本若引用公网软件源则返回拦截原因, 否则空串放行。"""
    script = script or ""
    low = script.lower()
    for hint in _OFFLINE_PUBLIC_SOURCES:
        if hint in low:
            return f"离线模式禁止 native 安装使用公网软件源 {hint}(请改用本地/内网包源)"
    return ""


_OFFLINE_PUBLIC_SOURCES = [
    "archive.ubuntu.com", "security.ubuntu.com", "download.fedoraproject.org",
    "mirrors.aliyun.com", "repo.huaweicloud.com", "mirrors.tuna.tsinghua.edu.cn",
    "mirrors.cloud.tencent.com", "dl.fedoraproject.org", "mirrors.ustc.edu.cn",
]


# ─── 原 L772-817 ───
def _inject_native_params(script: str, comp: dict, params: dict, deploy_path: str = "") -> str:
    """把定制参数注入 native 脚本。
    支持:
      1. {{key}} 占位符替换(脚本引用时用);
      2. 关键参数(db_port 等)存在时, 用 native_deploy 生成「真正改写配置文件 + 清理旧进程」的
         部署脚本段叠加在安装脚本之后, 使端口/密码等配置真正落地;
      3. 参数以环境变量前缀注入(保留兼容)。

    deploy_path: 部署/数据目录, 用于 native_deploy 里的 dir/日志路径。
    """
    params = params or {}
    schema = comp.get("param_schema") or []
    name = comp.get("name", "")

    # 1) {{key}} 占位符替换
    out = script or ""
    for item in schema:
        key = item.get("key")
        if not key:
            continue
        val = _param_value(item, params)
        out = out.replace("{{%s}}" % key, str(val) if val is not None else "")

    # 2) 环境变量前缀(保留对旧脚本/纯安装脚本的兼容)
    env_prefix = " ".join(
        f"{item.get('env', item['key'])}={_shell_quote(str(_param_value(item, params)))}"
        for item in schema if item.get("env") and _param_value(item, params) is not None
    )
    base = f"export {env_prefix} && {out}" if env_prefix else out

    # 3) 关键参数非空 → 叠加 native_deploy(清理残留 + 改写真配置 + 启动验证)
    nd = native_deploy(name, params, deploy_path=deploy_path)
    if nd:
        # ▼ 修正: 此前 is_configured 硬编码只认 db_port/redis_password/maxmemory/server_name,
        #   导致 rabbitmq(amqp_port/mq_port)、mongo(pg_*/mongo_*)、postgres 等组件
        #   传了参数也不叠加 native_deploy 配置段 → 服务装了但端口/密码从未生效。
        #   改为: 只要调用方传了非空 params 就叠加(纯安装调用 params 为空时仍走 base)。
        is_configured = any(
            _param_value(item, params) not in (None, "", False)
            for item in schema if item.get("key")
        ) or bool(params)
        if is_configured:
            install = (script or "").strip() or "true"
            chain = "\n".join(x for x in [install, nd] if x)
            return f"export {env_prefix} ; {chain}" if env_prefix else chain
    return base


# ─── 原 L820-821 ───
def _shell_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


# ─── 原 L824-845 ───
def _stop_service(cmds: str) -> str:
    """通用: 优雅停服务 + 杀残留进程(避免旧进程占用端口/数据目录)。
    cmds: 用空格分隔的 systemd 服务名与可执行文件名, 幂等。"""
    svcs = []
    bins = []
    for tok in cmds.split():
        if "." in tok or tok.startswith(("/", "bin", "sbin", "usr")):
            bins.append(tok)
        else:
            svcs.append(tok)
    parts = []
    if svcs:
        # 均加 || true: 服务不存在/未启用时避免返回非零被 set -e 中断
        parts.append(
            "for svc in %s; do systemctl stop $svc 2>/dev/null || true; done; "
            "for svc in %s; do systemctl disable $svc 2>/dev/null || true; done; "
            "systemctl reset-failed %s 2>/dev/null || true" % (" ".join(svcs), " ".join(svcs), " ".join(svcs)))
    if bins:
        parts.append("for bin in %s; do pkill -9 -f $bin 2>/dev/null || true; done" % " ".join(bins))
    parts.append("sleep 2")
    # ▼ 用分号连接, 避免 `...done sleep 2` 缺分号导致的 shell 语法错误(此前用空格连接会吞掉后续命令)
    return "; ".join(parts)


# ─── 原 L848-1237 ───
def native_deploy(name: str, params: dict, deploy_path: str = "", port: int = 0) -> str:
    """为支持 native 的组件生成「真正落地配置」的原始部署脚本。

    相比传统只 install 的 native_script, 这里额外保证:
      1. 停旧服务 + 杀残留进程(避免旧实例/端口冲突)
      2. 备份旧配置文件
      3. 把 param_schema 的参数(尤其 db_port / 密码 / 内存等)**真正写进目标配置文件**
      4. 启动 + 服务级探测验证
    返回一段可在目标机执行的 shell 脚本(不含命令前缀); params 为空或组件不支持时返回 ""。
    注: 仅在存在有效定制参数时启用, 否则回退组件原生 native_script。
    """
    p = params or {}
    s = deploy_path or ""
    pt = int(p.get("db_port") or port or 0)
    username = ""
    det = _param_value({"key": "REAL_USER", "default": ""}, p) or ""
    if det:
        username = det
    else:
        # 尝试从常见键取用户名(不发明字段, 仅在存在时用)
        for k in ("mysql_user", "rabbitmq_user", "mongo_root_user", "mongo_user",
                  "pg_user", "redis_user", "es_user"):
            if p.get(k):
                username = str(p.get(k))
                break

    def S(run: str) -> str:
        """shell-quote 一个值(用于 sed 替换目标)。"""
        return _shell_quote(str(run))

    if name == "redis" or name == "valkey":
        svc = "redis" if name == "redis" else "valkey"
        # ▼ 修正: Rocky/EL 的 redis RPM 由 systemd 用 /etc/redis/redis.conf 启动
        #   (ExecStart=redis-server /etc/redis/redis.conf)。此前用 /etc/redis.conf 导致
        #   sed 改的端口写进了一个 systemd 不加载的文件, 实际进程仍是 6379。
        cfg = "/etc/redis/redis.conf" if name == "redis" else "/etc/valkey/valkey.conf"
        binname = svc
        pw = _param_value({"key": "redis_password", "default": ""}, p) or ""
        mm = _param_value({"key": "maxmemory", "default": ""}, p) or ""
        port_line = pt or 6379
        _pw_clean = str(pw or "").replace("'", "").replace('"', "")
        # ▼ 监听地址与保护模式改为可配置(默认 0.0.0.0 + no), 不再硬编码
        _bind = str(_param_value({"key": "bind", "default": "0.0.0.0"}, p) or "0.0.0.0").replace("'", "").replace('"', "") or "0.0.0.0"
        _pm = str(_param_value({"key": "redis_protected_mode", "default": "no"}, p) or "no").strip().lower()
        _pm = "yes" if _pm in ("yes", "on", "true", "1") else "no"
        parts = [
            _stop_service(f"{svc}-server {svc}"),
            f"mkdir -p '{s or '/data/'+svc}' && chown {svc}:{svc} '{s or '/data/'+svc}' 2>/dev/null; true",
            # ▼ SELinux 修复(装完即用): 若系统 Enforcing, 给自定义数据目录(如 /data/redis1,
            #   默认 default_t)打上 redis 数据目录类型 redis_var_lib_t, 否则 redis 进程被
            #   SELinux 拒绝写入(SAVE 报 Permission denied → 持久化落盘失败, 目录始终为空)。
            #   幂等: semanage/restorecon 不存在 或 非 Enforcing 时静默跳过。
            (f"if command -v semanage >/dev/null 2>&1 && [ \"$(getenforce 2>/dev/null)\" = \"Enforcing\" ]; then "
             f"semanage fcontext -a -t {svc}_var_lib_t '{s or '/data/'+svc}(/.*)?' 2>/dev/null || true; "
             f"restorecon -Rv '{s or '/data/'+svc}' >/dev/null 2>&1 || true; fi"),
            f"CFG={cfg}",
            "[ -f $CFG ] && cp $CFG $CFG.bak.$(date +%s) || true",
            # ▼ 端口先删后加, 保证唯一(多次部署不会残留多行 port)
            f"sed -i -E '/^[[:space:]]*#?[[:space:]]*port[[:space:]]/d' $CFG || true",
            f"echo 'port {port_line}' >> $CFG",
        ]
        if pw:
            # ▼ requirepass 用 base64 安全注入: 密码含引号/空格/反斜杠等特殊字符也不破坏 shell 与配置。
            #   先还原到临时文件, 再作为配置行追加, 保证 redis.conf 里 password 不含引号字面量。
            _pw_b64 = base64.urlsafe_b64encode(str(pw).encode("utf-8")).decode("ascii")
            # umask 077 使文件权限 600(仅属主可读), 降低泄露风险
            parts.append(f"umask 077; echo '{_pw_b64}' | base64 -d > /tmp/.aiops_{svc}_pw 2>/dev/null || true")
            parts.append(f"sed -i -E '/^[[:space:]]*#?[[:space:]]*requirepass[[:space:]]/d' $CFG || true")
            parts.append("printf 'requirepass ' >> $CFG; cat /tmp/.aiops_%s_pw >> $CFG; echo >> $CFG" % svc)
        if mm:
            parts.append(f"sed -i -E 's/^#?\\s*maxmemory\\s+.*/maxmemory {mm}/' $CFG")
            parts.append(f"grep -q '^maxmemory ' $CFG || echo 'maxmemory {mm}' >> $CFG")
        _dir_clean = str(s or '/data/' + svc).replace("'", "").replace('"', "")
        # ▼ sed 分隔符用 | (不能与路径里的 / 冲突)
        parts.append(f"sed -i -E 's|^#?\\s*dir\\s+.*|dir {_dir_clean}|' $CFG")
        parts.append(f"grep -q '^dir ' $CFG || echo 'dir {_dir_clean}' >> $CFG")
        # bind 先删后加, 保证唯一(原装 conf 常有多处 bind, 仅 sed 第一处会残留旧行)
        parts.append(f"sed -i -E '/^[[:space:]]*#?[[:space:]]*bind[[:space:]]/d' $CFG || true")
        parts.append(f"echo 'bind {_bind}' >> $CFG")
        # protected-mode 先删后加 (配置文件可能多行)
        parts.append(f"sed -i -E '/^[[:space:]]*#?[[:space:]]*protected-mode[[:space:]]/d' $CFG || true")
        parts.append(f"echo 'protected-mode {_pm}' >> $CFG")
        # ▼ 关键修复: redis.service 以 redis 用户运行, 改配置后必须把属主/权限改回 redis,
        #   否则 redis 用户读不了配置 → Fatal: Permission denied → 启动失败(此前各次部署失败根因)
        parts.append(f"chown {svc}:{svc} $CFG; chmod 640 $CFG; chmod 750 /etc/{svc} 2>/dev/null || true")
        # ▼ 启动: daemon-reload + enable + restart, 幂等
        parts.append(f"systemctl daemon-reload 2>/dev/null; systemctl enable --now {svc} 2>/dev/null; systemctl restart {svc} 2>/dev/null || service {svc} restart 2>/dev/null")
        # ▼ 验证(防御性重试): 循环探测最多 10 次(间隔1s), 直到 PONG 或超时,
        #   避免首装/高负载启动慢时误判 DOWN
        if pw:
            parts.append(
                f'_u=0; for _i in $(seq 1 10); do '
                f'{svc}-cli -p {port_line} -a \\"$(cat /tmp/.aiops_{svc}_pw 2>/dev/null)\\" ping 2>/dev/null | grep -q PONG && {{ _u=1; break; }}; sleep 1; done; '
                f'echo "__UP=$_u"')
        else:
            parts.append(
                f'_u=0; for _i in $(seq 1 10); do '
                f'{svc}-cli -p {port_line} ping 2>/dev/null | grep -q PONG && {{ _u=1; break; }}; sleep 1; done; '
                f'echo "__UP=$_u"')
        # ▼ 验证完成后再清理临时密码文件(防长期残留; 体检用 install.deploy_params 里的密码兜底)
        if svc in ("redis", "valkey"):
            parts.append(f"rm -f /tmp/.aiops_{svc}_pw 2>/dev/null || true")
        # ▼ 用「分号+换行」连接各步: 杜绝空格拼接导致的 shell 语法错误(曾出现 `done sleep 2` 缺分号)
        return ";\n".join(parts)

    if name in ("mysql", "mariadb"):
        svc = "mysqld" if name == "mysql" else "mariadb"
        # ▼ 修正: Rocky/EL9 的 MySQL RPM 配置在 /etc/my.cnf.d/mysql-server.cnf, 不是 /etc/my.cnf
        cfg = "/etc/my.cnf.d/mysql-server.cnf"
        port_line = pt or 3306
        _pw = str(_param_value({"key": "mysql_root_password", "default": ""}, p) or "")
        _db = str(_param_value({"key": "mysql_database", "default": ""}, p) or "")
        _user = str(_param_value({"key": "mysql_user", "default": ""}, p) or "")
        _user_pw = str(_param_value({"key": "mysql_password", "default": ""}, p) or "")
        parts = [
            "set +H",  # 禁用 ! 历史展开(密码含 ! 会破坏双引号内的 SQL)
            _stop_service(f"{svc} mysql"),
            # ▼ 初始化: 若数据目录空则 mysqld --initialize-insecure(首次安装必须)
            "[ -d /var/lib/mysql/mysql ] || (mkdir -p /var/lib/mysql; chown mysql:mysql /var/lib/mysql; mysqld --initialize-insecure --user=mysql 2>/dev/null || true)",
            # ▼ 万能重置 root 密码: 无论上次部署设了什么旧密码, 用 skip-grant-tables 临时启动清空,
            #   否则后续 `mysql -u root`(无密码)登录被拒 → ALTER USER 失效 → 密码永远停留在旧值
            "systemctl stop mysqld 2>/dev/null || true; sleep 2; "
            "rm -f /var/run/mysqld/mysqld.pid /var/lib/mysql/mysql.sock 2>/dev/null || true; "
            "mkdir -p /var/run/mysqld; chown mysql:mysql /var/run/mysqld 2>/dev/null || true; "
            f"/usr/sbin/mysqld --skip-grant-tables --skip-networking --user=mysql --socket=/var/lib/mysql/mysql.sock >/tmp/.aiops_{svc}_sgt.log 2>&1 & "
            "MPID=$!; sleep 6; "
            "mysql --socket=/var/lib/mysql/mysql.sock -u root -e \"FLUSH PRIVILEGES; ALTER USER 'root'@'localhost' IDENTIFIED BY ''; FLUSH PRIVILEGES;\" 2>/dev/null || true; "
            "kill $MPID 2>/dev/null || true; sleep 3; "
            "rm -f /var/lib/mysql/mysql.sock /var/run/mysqld/mysqld.pid 2>/dev/null || true",
            f"CFG={cfg}",
            "[ -f $CFG ] && cp $CFG $CFG.bak.$(date +%s) || true",
            # ▼ 端口先删后加, 保证唯一(配置在 /etc/my.cnf.d/mysql-server.cnf)
            f"sed -i -E '/^[[:space:]]*#?[[:space:]]*port[[:space:]=]/d' $CFG || true",
            f"echo 'port={port_line}' >> $CFG",
            # 确保 bind-address 监听所有
            f"grep -q '^bind-address' $CFG || echo 'bind-address=0.0.0.0' >> $CFG",
            # ▼ SELinux 端口上下文: Rocky/EL9 Enforcing 模式下 mysqld 只能 bind 默认端口(3306/1186/63132-63164),
            #   自定义端口(如 3307)会 Bind Permission denied → 必须用 semanage 给端口打上 mysqld_port_t
            (f"if command -v semanage >/dev/null 2>&1 && [ \"$(getenforce 2>/dev/null)\" = \"Enforcing\" ]; then "
             f"semanage port -a -t mysqld_port_t -p tcp {port_line} 2>/dev/null || "
             f"semanage port -m -t mysqld_port_t -p tcp {port_line} 2>/dev/null || true; fi"),
            f"systemctl daemon-reload 2>/dev/null; systemctl reset-failed {svc} 2>/dev/null; systemctl enable {svc} 2>/dev/null; systemctl start {svc} 2>/dev/null; sleep 4",
        ]
        # ▼ 设置 root 密码(密码特殊字符用 base64 注入)
        if _pw:
            _pw_b64 = base64.urlsafe_b64encode(str(_pw).encode("utf-8")).decode("ascii")
            parts.append(
                f"PW=$(echo '{_pw_b64}' | base64 -d); "
                f"mysql -u root -e \"ALTER USER 'root'@'localhost' IDENTIFIED BY '$PW'; FLUSH PRIVILEGES;\" 2>/dev/null || true"
            )
            # ▼ 创建数据库和普通用户
            if _db and _user and _user_pw:
                _upw_b64 = base64.urlsafe_b64encode(str(_user_pw).encode("utf-8")).decode("ascii")
                parts.append(
                    f"UPW=$(echo '{_upw_b64}' | base64 -d); "
                    f"mysql -u root -p\"$PW\" -e "
                    f"\"CREATE DATABASE IF NOT EXISTS {_db}; "
                    f"CREATE USER IF NOT EXISTS '{_user}'@'%' IDENTIFIED BY '$UPW'; "
                    f"GRANT ALL PRIVILEGES ON {_db}.* TO '{_user}'@'%'; "
                    f"FLUSH PRIVILEGES;\" 2>/dev/null || true"
                )
            # ▼ 验证: 用密码探测
            parts.append(
                f"echo \"__UP=$(mysqladmin ping -u root -p\\\"$PW\\\" 2>/dev/null | grep -q alive && echo 1 || echo 0)\""
            )
        else:
            parts.append(
                f"echo \"__UP=$(mysqladmin ping 2>/dev/null | grep -q alive && echo 1 || echo 0)\""
            )
        # ▼ 用「分号+换行」连接各步: 杜绝空格拼接导致的 shell 语法错误(曾出现 `done sleep 2` 缺分号)
        return ";\n".join(parts)

    if name == "nginx":
        cfg = "/etc/nginx/nginx.conf"
        port_line = pt or 80
        server_name = str(_param_value({"key": "server_name", "default": "localhost"}, p) or "localhost")
        parts = [
            _stop_service("nginx"),
            "CFG=/etc/nginx/nginx.conf",
            "[ -f $CFG ] && cp $CFG $CFG.bak.$(date +%s) || true",
            f"sed -i -E 's/^(\\s*)listen\\s+[0-9]+;*/\\1listen {port_line};/' $CFG || true",
            f"sed -i -E 's/^(\\s*)listen\\s+[0-9]+ default_server;*/\\1listen {port_line} default_server;/' $CFG || true",
            f"sed -i -E 's/^\\s*server_name\\s+[^;]+;/server_name {S(server_name)};/' $CFG || true",
            f"systemctl daemon-reload 2>/dev/null || true; systemctl enable nginx 2>/dev/null || true; "
            f"systemctl start --no-block nginx 2>/dev/null || true; sleep 2; "
            f"(nginx -t 2>&1 | grep -q 'syntax is ok' || service nginx restart 2>/dev/null); "
            f'echo "__UP=$((ss -ltn 2>/dev/null | grep -q ":{port_line} " && echo 1) || echo 0)"',
        ]
        # ▼ 用「分号+换行」连接各步: 杜绝空格拼接导致的 shell 语法错误(曾出现 `done sleep 2` 缺分号)
        return ";\n".join(parts)

    if name == "rabbitmq":
        svc = "rabbitmq-server"
        amqp = int(p.get("amqp_port") or pt or 5672) or 5672
        mgmt = int(p.get("mq_port") or 15672) or 15672
        cfg = "/etc/rabbitmq/rabbitmq.conf"
        username = str(_param_value({"key": "rabbitmq_user", "default": "admin"}, p) or "admin")
        password = str(_param_value({"key": "rabbitmq_password", "default": ""}, p) or "")
        parts = [
            _stop_service("rabbitmq-server rabbitmq"),
            "mkdir -p /etc/rabbitmq",
            "CFG=/etc/rabbitmq/rabbitmq.conf",
            "[ -f $CFG ] && cp $CFG $CFG.bak.$(date +%s) || true",
            # ▼ SELinux 放行端口: amqp_port_t 默认只含 5671-5672/15672, 改端口后 Enforcing 下绑定失败
            f"(command -v semanage >/dev/null 2>&1 || yum install -y policycoreutils-python-utils >/dev/null 2>&1 || true); "
            f"semanage port -a -t amqp_port_t -p tcp {amqp} 2>/dev/null || "
            f"semanage port -m -t amqp_port_t -p tcp {amqp} 2>/dev/null || true; "
            f"semanage port -a -t amqp_port_t -p tcp {mgmt} 2>/dev/null || "
            f"semanage port -m -t amqp_port_t -p tcp {mgmt} 2>/dev/null || true",
            # 用 printf 写多行(避免 heredoc 结束符被分号 join 破坏)
            f"printf '%s\\n' 'listeners.tcp.default = {amqp}' 'management.tcp.port = {mgmt}' 'loopback_users.guest = false' > $CFG",
            f"rabbitmq-plugins enable rabbitmq_management 2>/dev/null || true",
            f"systemctl daemon-reload 2>/dev/null || true; systemctl enable {svc} 2>/dev/null || true; "
            f"systemctl start --no-block {svc} 2>/dev/null || true",
            # ▼ 等待 AMQP 端口就绪(rabbitmq 冷启动可能 20-60s, sleep 2/8 都不够)
            #   ss 匹配带冒号+空格, 避免 25672/15672 误命中
            f"_ok=0; for _i in $(seq 1 30); do "
            f"ss -ltn 2>/dev/null | grep -q ':{amqp} ' && {{ _ok=1; break; }}; sleep 3; done",
            # ▼ 等 rabbit 应用真正就绪(rabbitmqctl status 成功才算, 而非 pid 文件)
            "for _i in $(seq 1 40); do rabbitmqctl status >/dev/null 2>&1 && break; sleep 3; done",
        ]
        if username and password:
            parts.append(
                f"timeout 60 rabbitmqctl add_user '{username}' '{password}' 2>/dev/null || true; "
                f"timeout 60 rabbitmqctl set_user_tags '{username}' administrator 2>/dev/null || true; "
                f"timeout 60 rabbitmqctl set_permissions -p / '{username}' '.*' '.*' '.*' 2>/dev/null || true"
            )
            parts.append(f'echo "__UP=$((ss -ltn 2>/dev/null | grep -q ":{amqp} " && echo 1) || echo 0)"')
        else:
            parts.append(f'echo "__UP=$((ss -ltn 2>/dev/null | grep -q ":{amqp} " && echo 1) || echo 0)"')
        # ▼ 用「分号+换行」连接各步: 杜绝空格拼接导致的 shell 语法错误(曾出现 `done sleep 2` 缺分号)
        return ";\n".join(parts)

    if name == "mongodb":
        svc = "mongod"
        cfg = "/etc/mongod.conf"
        port_line = pt or 27017
        m_user = str(_param_value({"key": "mongo_root_user", "default": "admin"}, p) or "admin")
        m_pw = str(_param_value({"key": "mongo_root_password", "default": ""}, p) or "")
        m_db = str(_param_value({"key": "mongo_database", "default": "appdb"}, p) or "appdb")
        parts = [
            _stop_service("mongod mongodb"),
            "CFG=/etc/mongod.conf",
            "[ -f $CFG ] && cp $CFG $CFG.bak.$(date +%s) || true",
            f"sed -i -E 's/^\\s*port\\s*:\\s*[0-9]+/  port: {port_line}/' $CFG || true",
            f"grep -q 'port:' $CFG || sed -i '/net:/a\\  port: {port_line}' $CFG",
            f"systemctl daemon-reload 2>/dev/null || true; systemctl enable {svc} 2>/dev/null || true; "
            f"systemctl start --no-block {svc} 2>/dev/null || true; sleep 2",
            # ▼ 用 mongosh 重试探测(最多 20 次), 必须带 --port(服务可能已改非默认端口)
            f"_ok=0; for _i in $(seq 1 20); do "
            f"mongosh --port {port_line} --quiet --eval 'db.runCommand({{ping:1}})' 2>/dev/null | grep -q 'ok: 1' && {{ _ok=1; break; }}; sleep 2; done",
            # ▼ 创建 root 用户 + 初始化业务库(平台测试需要可认证连接)
            f"mongosh --port {port_line} --quiet --eval 'var u = db.getSiblingDB(\"admin\"); u.createUser({{user:\"{m_user}\", pwd:\"{m_pw}\", roles:[{{role:\"root\", db:\"admin\"}}]}}); u.getSiblingDB(\"{m_db}\").createCollection(\"__init__\");' 2>/dev/null || true",
            f"echo \"__UP=$((ss -ltn 2>/dev/null | grep -q ':{port_line} ' && echo 1) || echo 0)\"",
        ]
        # ▼ 用「分号+换行」连接各步: 杜绝空格拼接导致的 shell 语法错误(曾出现 `done sleep 2` 缺分号)
        return ";\n".join(parts)

    if name == "postgresql":
        svc = "postgresql"
        port_line = pt or 5432
        username = str(_param_value({"key": "pg_user", "default": "postgres"}, p) or "postgres")
        password = str(_param_value({"key": "pg_password", "default": ""}, p) or "")
        m_db = str(_param_value({"key": "pg_database", "default": "appdb"}, p) or "appdb")
        parts = [
            _stop_service("postgresql postgresql-16 postgres"),
            # ▼ initdb: 数据目录未初始化 → ExecStartPre 检查失败 → 服务起不来(必须初始化)
            "[ -s /var/lib/pgsql/data/PG_VERSION ] || /usr/bin/postgresql-setup --initdb 2>/dev/null || true",
            # ▼ SELinux 放行端口: Enforcing 下 postgres 绑定非默认端口会 Permission denied(bind 失败)
            f"(command -v semanage >/dev/null 2>&1 || yum install -y policycoreutils-python-utils >/dev/null 2>&1 || true); "
            f"semanage port -a -t postgresql_port_t -p tcp {port_line} 2>/dev/null || "
            f"semanage port -m -t postgresql_port_t -p tcp {port_line} 2>/dev/null || true",
            "CFG=/var/lib/pgsql/data/postgresql.conf",
            "[ -f $CFG ] && cp $CFG $CFG.bak.$(date +%s) || true",
            f"sed -i -E 's/^#?\\s*port\\s*=\\s*[0-9]+/port = {port_line}/' $CFG || true",
            f"grep -q '^port' $CFG || echo 'port = {port_line}' >> $CFG",
            f"systemctl daemon-reload 2>/dev/null || true; systemctl enable {svc} 2>/dev/null || true; "
            f"systemctl start --no-block {svc} 2>/dev/null || true; sleep 2",
            # ▼ 等待 ready(最多 30s)
            f"_ok=0; for _i in $(seq 1 15); do "
            f"pg_isready -p {port_line} 2>/dev/null | grep -qi accepting && {{ _ok=1; break; }}; sleep 2; done",
            # ▼ 创建业务库 + 设置密码(平台测试/交付需要)
            f"su - postgres -c \"psql -p {port_line} -tAc \\\"SELECT 1 FROM pg_database WHERE datname='{m_db}'\\\" | grep -q 1 || createdb -p {port_line} {m_db}\" 2>/dev/null || true",
            f"su - postgres -c \"psql -c \\\"ALTER USER {username} PASSWORD '{password}'\\\"\" 2>/dev/null || true",
            f"echo \"__UP=$(pg_isready -p {port_line} 2>/dev/null | grep -qi accepting && echo 1 || echo 0)\"",
        ]
        # ▼ 用「分号+换行」连接各步: 杜绝空格拼接导致的 shell 语法错误(曾出现 `done sleep 2` 缺分号)
        return ";\n".join(parts)

    if name == "elasticsearch":
        svc = "elasticsearch"
        cfg = "/etc/elasticsearch/elasticsearch.yml"
        port_line = pt or 9200
        heap = str(_param_value({"key": "es_jvm_heap", "default": "512m"}, p) or "512m")
        parts = [
            _stop_service("elasticsearch"),
            # ▼ SELinux 放行非默认端口(semanage 可能未安装, 用 || true 忽略)
            "if command -v semanage >/dev/null 2>&1; then "
            f"semanage port -a -t http_port_t -p tcp {port_line} 2>/dev/null || "
            f"semanage port -m -t http_port_t -p tcp {port_line} 2>/dev/null || true; fi",
            "mkdir -p /etc/elasticsearch /etc/elasticsearch/jvm.options.d",
            "CFG=/etc/elasticsearch/elasticsearch.yml",
            # 备份旧配置(不删除, 规避高危)
            "[ -f $CFG ] && cp $CFG $CFG.bak.$(date +%s) || true",
            # ▼ 用干净的最小配置整体重写(避免 sed 删父键残留子行破坏 YAML)
            #   ES8 默认开安全+HTTPS, 原生部署关闭以便 HTTP 直连验证 CRUD
            f"printf '%s\\n' "
            "'# AIOps native deploy' "
            "'path.data: /var/lib/elasticsearch' "
            "'path.logs: /var/log/elasticsearch' "
            "'http.host: 0.0.0.0' "
            f"'http.port: {port_line}' "
            "'xpack.security.enabled: false' "
            "'xpack.security.enrollment.enabled: false' "
            "'xpack.security.http.ssl.enabled: false' "
            "'xpack.security.transport.ssl.enabled: false' "
            "'discovery.type: single-node' > $CFG",
            f"printf '%s\\n' '-Xms{heap}' '-Xmx{heap}' > /etc/elasticsearch/jvm.options.d/aiops.heap 2>/dev/null || true",
            # ▼ 清旧数据目录(首次安全初始化会生成; 重部署避免残留冲突), 保证属主
            "rm -rf /var/lib/elasticsearch/* 2>/dev/null || true; "
            "chown -R elasticsearch:elasticsearch /var/lib/elasticsearch /var/log/elasticsearch /etc/elasticsearch 2>/dev/null || true",
            f"systemctl daemon-reload 2>/dev/null || true; systemctl enable {svc} 2>/dev/null || true; "
            f"systemctl start --no-block {svc} 2>/dev/null || true; "
            f"echo ST=$(systemctl is-active {svc} 2>/dev/null || echo UNKNOWN); "
            f"echo PT=$(grep http.port $CFG | head -1 2>/dev/null || echo NOFILE); "
            f"echo LOG=$(journalctl -u {svc} --no-pager -n 3 2>/dev/null | tail -1 | tr -d '\\n' | head -c 60)",
            # ▼ ES 冷启动慢(清库重建), 重试最多 60 次(3s)
            f"_u=0; for _i in $(seq 1 60); do "
            f"curl -s --connect-timeout 3 http://localhost:{port_line} 2>/dev/null | grep -q cluster_name && {{ _u=1; break; }}; sleep 3; done; "
            f'echo "__UP=$_u"',
        ]
        # ▼ 用「分号+换行」连接各步: 杜绝空格拼接导致的 shell 语法错误(曾出现 `done sleep 2` 缺分号)
        return ";\n".join(parts)

    if name == "kafka":
        # ▼ Kafka 的完整安装/配置/启动统一由 native_script(带 {{db_port}}/{{kafka_data_dir}}/
        #   {{kafka_broker_id}} 占位符注入)处理, 这里返回空以避免与 native_script 的
        #   KRaft 配置/启动逻辑冲突(此前 native_deploy 与 native_script 各改一次配置导致端口/数据目录错乱)。
        return ""

    if name == "haproxy":
        cfg = "/etc/haproxy/haproxy.cfg"
        port_line = pt or 8080
        parts = [
            _stop_service("haproxy"),
            "CFG=/etc/haproxy/haproxy.cfg",
            "[ -f $CFG ] && cp $CFG $CFG.bak.$(date +%s) || true",
            f"sed -i -E 's/^\\s*bind\\s+[0-9]+/bind *:{port_line}/' $CFG || true",
            "grep -q '^  bind ' $CFG || sed -i '/^frontend /,/^backend /s/^/  bind *:{port_line}\\n/' $CFG".replace("{port_line}", str(port_line)),
            f"systemctl daemon-reload 2>/dev/null || true; systemctl enable haproxy 2>/dev/null || true; "
            f"systemctl start --no-block haproxy 2>/dev/null || true; sleep 2",
            f"echo \"__UP=$((ss -ltn 2>/dev/null | grep -q ':{port_line} ' && echo 1) || echo 0)\"",
        ]
        # ▼ 用「分号+换行」连接各步: 杜绝空格拼接导致的 shell 语法错误(曾出现 `done sleep 2` 缺分号)
        return ";\n".join(parts)

    if name == "memcached":
        cfg = "/etc/memcached.conf"
        port_line = pt or 11211
        parts = [
            _stop_service("memcached"),
            "CFG=/etc/memcached.conf",
            "[ -f $CFG ] && cp $CFG $CFG.bak.$(date +%s) || true",
            f"sed -i -E 's/^-p\\s+[0-9]+/-p {port_line}/' $CFG || true",
            f"grep -q '^-p' $CFG || sed -i '$a\\-p {port_line}' $CFG",
            f"systemctl daemon-reload 2>/dev/null || true; systemctl enable memcached 2>/dev/null || true; "
            f"systemctl start --no-block memcached 2>/dev/null || true; sleep 2",
            f"echo \"__UP=$(pidof memcached >/dev/null 2>&1 && echo 1 || echo 0)\"",
        ]
        # ▼ 用「分号+换行」连接各步: 杜绝空格拼接导致的 shell 语法错误(曾出现 `done sleep 2` 缺分号)
        return ";\n".join(parts)

    if name == "mosquitto":
        cfg = "/etc/mosquitto/mosquitto.conf"
        port_line = pt or 1883
        parts = [
            _stop_service("mosquitto"),
            "mkdir -p /etc/mosquitto",
            "CFG=/etc/mosquitto/mosquitto.conf",
            "[ -f $CFG ] && cp $CFG $CFG.bak.$(date +%s) || true",
            f"grep -q '^listener ' $CFG || echo 'listener {port_line}' >> $CFG",
            f"sed -i -E 's/^listener\\s+[0-9]+/listener {port_line}/' $CFG || true",
            f"systemctl daemon-reload 2>/dev/null || true; systemctl enable mosquitto 2>/dev/null || true; "
            f"systemctl start --no-block mosquitto 2>/dev/null || true; sleep 2",
            f"echo \"__UP=$((ss -ltn 2>/dev/null | grep -q ':{port_line} ' && echo 1) || echo 0)\"",
        ]
        # ▼ 用「分号+换行」连接各步: 杜绝空格拼接导致的 shell 语法错误(曾出现 `done sleep 2` 缺分号)
        return ";\n".join(parts)

    return ""


# ─── 原 L1240-1272 ───
def seed_builtin_components(db: Session) -> int:
    """启动时播种内置组件目录(upsert: 存在则刷新字段, 不存在则新增)"""
    added = 0
    for item in _BUILTIN_COMPONENTS:
        comp = db.query(ComponentCatalog).filter(ComponentCatalog.name == item["name"]).first()
        if not comp:
            comp = ComponentCatalog(name=item["name"])
            db.add(comp)
            added += 1
        comp.display_name = item["display_name"]
        comp.category = item["category"]
        comp.version = item["version"]
        comp.source = item.get("source", "")
        comp.description = item["description"]
        comp.icon = item["icon"]
        comp.docker_image = item["docker_image"]
        comp.helm_chart = item["helm_chart"]
        comp.helm_repo = item["helm_repo"]
        comp.default_port = item["default_port"]
        comp.deploy_types = json.dumps(item["deploy_types"], ensure_ascii=False)
        comp.native_script = item["native_script"]
        comp.compose_yaml = item["compose_yaml"] or build_default_compose(item["name"], item["docker_image"], item["default_port"])
        comp.ha_config = item["ha_config"]
        comp.config_keys = item["config_keys"]
        comp.complexity = item["complexity"]
        comp.sort_order = item["sort_order"]
        comp.enabled = True
        comp.param_schema = json.dumps(item.get("param_schema") or [], ensure_ascii=False)
    db.commit()
    return added


# ───────────── CRUD ─────────────


