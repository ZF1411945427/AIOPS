"""子模块: 组件目录 CRUD/安装/部署/SSH/健康检查(由拆分生成)"""

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

from app.services.component_catalog_data import (    _BUILTIN_COMPONENTS, _OFFLINE_PUBLIC_SOURCES, _MIN_CVE_RULES,
    _HEALTH_CMDS, _CONFIG_FILES, _NATIVE_VERIFY,
)
from app.services.component_catalog_render import (    build_default_compose, render_compose, _inject_native_params,
    _offline_native_block, native_deploy, _shell_quote, _param_value,
)
from app.services.component_catalog_ai import _plan_to_visual_steps  # noqa: F401

# ─── 原 L1274-1281 ───
def list_components(db: Session, category: str = "", keyword: str = "") -> List[dict]:
    q = db.query(ComponentCatalog).filter(ComponentCatalog.enabled == True)  # noqa: E712
    if category:
        q = q.filter(ComponentCatalog.category == category)
    if keyword:
        q = q.filter(ComponentCatalog.name.like(f"%{keyword}%") | ComponentCatalog.display_name.like(f"%{keyword}%"))
    rows = q.order_by(ComponentCatalog.sort_order, ComponentCatalog.id).all()
    return [_comp_to_dict(c) for c in rows]


# ─── 原 L1284-1286 ───
def get_component(db: Session, component_id: int) -> Optional[dict]:
    c = db.query(ComponentCatalog).filter(ComponentCatalog.id == component_id).first()
    return _comp_to_dict(c) if c else None


# ─── 原 L1289-1316 ───
def _comp_to_dict(c: ComponentCatalog) -> dict:
    try:
        deploy_types = json.loads(c.deploy_types) if c.deploy_types else []
    except Exception:
        deploy_types = []
    try:
        ha_config = json.loads(c.ha_config) if c.ha_config else {}
    except Exception:
        ha_config = {}
    try:
        param_schema = json.loads(c.param_schema) if c.param_schema else []
    except Exception:
        param_schema = []
    install_count = 0
    return {
        "id": c.id, "name": c.name, "display_name": c.display_name,
        "category": c.category, "version": c.version, "source": c.source or "", "description": c.description,
        "icon": c.icon, "docker_image": c.docker_image, "helm_chart": c.helm_chart,
        "helm_repo": c.helm_repo, "default_port": c.default_port,
        "deploy_types": deploy_types, "native_script": c.native_script,
        "compose_yaml": c.compose_yaml, "ha_config": ha_config,
        "param_schema": param_schema,
        "config_keys": c.config_keys, "complexity": c.complexity,
        "sort_order": c.sort_order, "install_count": install_count,
    }


# ───────────── 部署 ─────────────


# ─── 原 L1318-1369 ───
def get_deploy_render(comp: dict, deploy_type: str, params: dict, db: Session = None) -> dict:
    """渲染部署配方内容(不执行): 返回 compose/native 脚本/helm 命令, 供前端确认。
    comp 为 get_component 的 dict。db 用于可选离线镜像解析(get_deploy_render 无 db 时跳过离线)。"""
    allowed = comp.get("deploy_types") or []
    if deploy_type not in allowed:
        return {"ok": False, "error": f"组件不支持部署方式 {deploy_type}(支持: {allowed})"}

    host = params.get("host") or ""
    ns = params.get("namespace") or "default"
    release = params.get("release") or f"{comp['name']}-{datetime.now().strftime('%m%d%H%M')}"
    port = comp.get("default_port") or 0
    image = comp.get("docker_image") or ""

    if deploy_type == "docker":
        schema_keys = {item.get("key") for item in (comp.get("param_schema") or [])}
        custom_params = {k: v for k, v in params.items() if k in schema_keys}
        offline_image = ""
        if params.get("use_offline") and db:
            from app.services.offline_repo_service import resolve_offline_image as _roi
            offline_image = _roi(db, image, True)["image"] if image else ""
        if custom_params:
            compose = render_compose(comp, custom_params, port, offline_image=offline_image)
        else:
            compose = comp.get("compose_yaml") or build_default_compose(comp["name"], offline_image or image, port)
        content = f"# {comp.get('display_name')} Docker 部署 (docker compose)\n# 目标机: {host}\n{compose}\n# 命令: docker compose up -d\n"
        meta = {"kind": "docker", "release": release}
    elif deploy_type == "native":
        script = comp.get("native_script") or f"echo '暂未提供 {comp['name']} 原生安装脚本'"
        schema_keys = {item.get("key") for item in (comp.get("param_schema") or [])}
        custom_params = {k: v for k, v in params.items() if k in schema_keys}
        if custom_params:
            script = _inject_native_params(script, comp, custom_params, deploy_path=params.get("deploy_path") or "")
        content = f"# {comp.get('display_name')} 传统部署\n# 目标机: {host}\n{script}\n# 启动: systemctl start {comp['name']}\n"
        meta = {"kind": "native"}
    elif deploy_type == "helm":
        content = (f"# {comp.get('display_name')} K8S/Helm 部署\n"
                   f"# Chart: {comp.get('helm_chart')} (repo: {comp.get('helm_repo')})\n"
                   f"# 命名空间: {ns} | Release: {release}\n"
                   f"# 命令: helm repo add bitnami {comp.get('helm_repo')} && "
                   f"helm install {release} {comp.get('helm_chart')} -n {ns} --create-namespace\n")
        meta = {"kind": "helm", "namespace": ns, "release": release}
    else:  # ha
        ha = comp.get("ha_config") or {}
        nodes = ha.get("replicas") or ha.get("brokers") or ha.get("nodes") or ha.get("members") or "1"
        content = (f"# {comp.get('display_name')} 高可用部署\n"
                   f"# 模式: {ha.get('mode', 'cluster')} | 节点/副本: {nodes}\n"
                   f"# 提示: 高可用建议通过 helm/K8s 多副本或 docker 多实例 + 负载均衡实现。\n")
        meta = {"kind": "ha", "mode": ha.get("mode", "cluster")}
    return {"ok": True, "content": content, "meta": meta}


# ───────────── 安装记录 ─────────────


# ─── 原 L1371-1376 ───
def list_installs(db: Session, asset_id: Optional[int] = None) -> List[dict]:
    q = db.query(ComponentInstall)
    if asset_id:
        q = q.filter(ComponentInstall.asset_id == asset_id)
    rows = q.order_by(ComponentInstall.created_at.desc()).limit(200).all()
    return [_install_to_dict(r, db) for r in rows]


# ─── 原 L1379-1387 ───
def _resolve_pending_decision(raw: Optional[str]):
    """解析持久化的待决策卡片: 'null'/'空' → None; 否则返回 dict。"""
    if not raw or raw == "null":
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


# ─── 原 L1390-1392 ───
def get_install(db: Session, install_id: int) -> Optional[dict]:
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    return _install_to_dict(r, db) if r else None


# ─── 原 L1395-1428 ───
def _install_to_dict(r: ComponentInstall, db: Session) -> dict:
    asset_name = db.query(Asset.name).filter(Asset.id == r.asset_id).scalar() or f"资产#{r.asset_id}"
    # 从 events_json 提取落盘的部署方案(plan 事件), 供详情直接展示(不再依赖运行时重建)
    plan_text = ""
    plan_system = ""
    plan_ai = False
    try:
        evs = json.loads(r.events_json) if r.events_json else []
        if isinstance(evs, list):
            plan_ev = next((e for e in evs if isinstance(e, dict) and e.get("type") == "plan"), None)
            if plan_ev:
                plan_text = plan_ev.get("plan") or ""
                plan_system = plan_ev.get("system") or ""
                plan_ai = bool(plan_ev.get("ai_generated"))
    except Exception:
        pass
    plan_steps = _plan_to_visual_steps(plan_text, r.deploy_type) if plan_text else []
    return {
        "id": r.id, "component_id": r.component_id, "component_name": r.component_name,
        "asset_id": r.asset_id, "asset_name": asset_name, "deploy_type": r.deploy_type,
        "name_space": r.name_space, "release_name": r.release_name, "deploy_path": r.deploy_path,
        "port": r.port, "status": r.status, "config_check_status": r.config_check_status,
        "health_status": r.health_status, "config_result": r.config_result,
        "health_result": r.health_result, "vuln_result": r.vuln_result,
        "ai_analysis": r.ai_analysis, "report_json": r.report_json or "",
        "deploy_params": r.deploy_params or "{}",
        "deploy_log": (r.deploy_log or "")[-2000:],
        "deploy_plan_id": r.deploy_plan_id,
        "plan": plan_text, "plan_steps": plan_steps, "plan_system": plan_system,
        "plan_ai": plan_ai,
        "pending_decision": _resolve_pending_decision(r.pending_decision_json),
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


# ─── 原 L1431-1443 ───
def record_install(db: Session, component_id: int, component_name: str, asset_id: int,
                   deploy_type: str, deploy_path: str = "", release_name: str = "",
                   name_space: str = "", port: int = 0, deploy_params: dict = None) -> dict:
    inst = ComponentInstall(
        component_id=component_id, component_name=component_name, asset_id=asset_id,
        deploy_type=deploy_type, deploy_path=deploy_path, release_name=release_name,
        name_space=name_space, port=port, status="running",
        deploy_params=json.dumps(deploy_params or {}, ensure_ascii=False),
    )
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return _install_to_dict(inst, db)


# ─── 原 L1446-1454 ───
def update_install_status(db: Session, install_id: int, status: str, log: str = "") -> None:
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r:
        return
    r.status = status
    if log:
        r.deploy_log = (r.deploy_log or "") + "\n" + log
    r.updated_at = datetime.now()
    db.commit()


# ─── 原 L1457-1469 ───
def _append_install_event(db: Session, install_id: int, event: dict) -> None:
    """把单个结构化部署事件追加到安装记录 events_json(供历史回放/续 AI 对话)。"""
    try:
        r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
        if not r:
            return
        existing = json.loads(r.events_json) if r.events_json else []
        existing.append(event)
        r.events_json = json.dumps(existing, ensure_ascii=False)
        r.updated_at = datetime.now()
        db.commit()
    except Exception as _exc:
        logger.warning("[except:pass] Exception: %s", _exc, exc_info=True)


# ─── 原 L1472-1482 ───
def _set_pending_decision_install(db: Session, install_id: int, decision: Optional[dict] = None):
    """持久化/清空当前安装记录待决策卡片(按 install_id 独立, 互不干扰)。"""
    try:
        r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
        if not r:
            return
        r.pending_decision_json = "null" if decision is None else json.dumps(decision, ensure_ascii=False)
        r.updated_at = datetime.now()
        db.commit()
    except Exception as _exc:
        logger.warning("[except:pass] Exception: %s", _exc, exc_info=True)


# ─── 原 L1485-1493 ───
def get_install_events(db: Session, install_id: int) -> list:
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r or not r.events_json:
        return []
    try:
        evs = json.loads(r.events_json)
        return evs if isinstance(evs, list) else []
    except Exception:
        return []


# ─── 原 L1496-1505 ───
def delete_install(db: Session, install_id: int) -> bool:
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r:
        return False
    db.delete(r)
    db.commit()
    return True


# ───────────── 真实部署(代理注入 + docker compose) ─────────────


# ─── 原 L1507-1531 ───
def _apply_docker_proxy(asset: Asset, http_proxy: str, https_proxy: str, no_proxy: str) -> str:
    """把代理写入目标机 docker daemon 的 systemd drop-in, 使 docker pull 走代理。
    返回执行日志; 若三个代理都为空则跳过。"""
    logs = []
    http_p = (http_proxy or "").strip()
    https_p = (https_proxy or http_p or "").strip()
    no_proxy_p = (no_proxy or "127.0.0.1,localhost,.local").strip()
    if not http_p and not https_p:
        return ""
    unit = (
        "mkdir -p /etc/systemd/system/docker.service.d && "
        "cat > /etc/systemd/system/docker.service.d/http-proxy.conf <<'AIOPS_PROXY'\n"
        "[Service]\n"
        f"Environment=\"HTTP_PROXY={http_p}\"\n"
        f"Environment=\"HTTPS_PROXY={https_p}\"\n"
        f"Environment=\"NO_PROXY={no_proxy_p}\"\n"
        f"Environment=\"no_proxy={no_proxy_p}\"\n"
        "AIOPS_PROXY\n"
        "systemctl daemon-reload && systemctl restart docker && sleep 3 && systemctl is-active docker"
    )
    ok, out = _exec_ssh(asset, unit)
    logs.append(f"[proxy] 写入 docker 代理 {http_p or https_p} (no_proxy={no_proxy_p}): {out}")
    if not ok:
        logs.append("[proxy] docker 重启后未 active, 请检查代理")
    return "\n".join(logs)


# ─── 原 L1534-1556 ───
def _apply_native_proxy(asset: Asset, http_proxy: str, https_proxy: str, no_proxy: str) -> str:
    """把用户已配置的网络代理写入目标机 dnf/yum 配置, 使 native 的 yum/dnf 走代理。
    返回执行日志; 若三个代理都为空则跳过。
    与 _apply_docker_proxy 并列: docker 注入 docker daemon, native 注入 dnf/yum。
    """
    logs = []
    http_p = (http_proxy or "").strip()
    https_p = (https_proxy or http_p or "").strip()
    if not http_p and not https_p:
        return ""
    no_proxy_p = (no_proxy or "127.0.0.1,localhost,.local").strip()
    # 写入 dnf/yum 代理(覆盖重启后永久生效), 同时备份原文件
    unit = (
        "for _cf in /etc/dnf/dnf.conf /etc/yum.conf; do "
        "[ -f $_cf ] && grep -q '^proxy' $_cf || (echo 'proxy=" + http_p + "' >> $_cf); "
        "done; "
        "echo NATIVE_PROXY_OK"
    )
    ok, out = _exec_ssh(asset, unit)
    logs.append(f"[proxy] 写入 native(yum/dnf) 代理 {http_p} (no_proxy={no_proxy_p}): {out}")
    if not ok:
        logs.append("[proxy] native 代理写入失败, 请检查目标机权限")
    return "\n".join(logs)


# ─── 原 L1559-1570 ───
def _native_proxy_prefix(http_proxy: str, https_proxy: str, no_proxy: str) -> str:
    """返回一段在 native 执行脚本开头 export 代理环境变量的 shell 前缀。
    使 curl/wget/pip 等命令也都走代理(不只 yum)。"""
    http_p = (http_proxy or "").strip()
    https_p = (https_proxy or http_p or "").strip()
    if not http_p and not https_p:
        return ""
    no_proxy_p = (no_proxy or "127.0.0.1,localhost,.local").strip()
    return (
        f"export http_proxy='{http_p}' https_proxy='{https_p}' HTTP_PROXY='{http_p}' "
        f"HTTPS_PROXY='{https_p}' no_proxy='{no_proxy_p}' NO_PROXY='{no_proxy_p}'"
    )


# ─── 原 L1574-1605 ───
def deploy_docker(asset: Asset, comp: dict, port: int, deploy_path: str,
                  http_proxy: str = "", https_proxy: str = "", no_proxy: str = "",
                  compose: str = "") -> tuple:
    """在目标机真实部署 docker 组件: 写代理 → 写 compose → docker compose up -d。
    可用 compose 传入完整覆盖配置(含必要环境变量/启动参数), 否则用组件默认配方。
    返回 (ok: bool, log: str)。"""
    logs = []
    name = comp["name"]
    image = comp.get("docker_image") or ""
    if http_proxy or https_proxy:
        logs.append(_apply_docker_proxy(asset, http_proxy, https_proxy, no_proxy))
    # 生成 compose(优先显式传入覆盖)
    compose = (compose or comp.get("compose_yaml") or build_default_compose(name, image, port))
    cn = f"aiops-{name}"
    # 组合远程执行命令
    remote = (
        f"mkdir -p '{deploy_path}'; "
        f"cat > '{deploy_path}/docker-compose.yml' <<'AIOPS_COMPOSE'\n{compose}\nAIOPS_COMPOSE\n"
        f"cd '{deploy_path}'; docker compose down >/dev/null 2>&1; "
        f"OUT=$(docker compose up -d 2>&1); RC=$?; "
        f"echo \"$OUT\" | tail -20; echo __RC__=$RC"
    )
    ok, out = _exec_ssh(asset, remote, timeout=300)
    logs.append(f"[deploy] 写入 compose 并 docker compose up -d:\n{out}")
    # 判断是否起来
    ok2, ps = _exec_ssh(asset, f"docker ps --filter name={cn} --format '{{{{.Names}}}} {{{{.Status}}}}' 2>&1 | head -5")
    running = "Up" in ps
    if ok and running:
        logs.append(f"[deploy] 容器 {cn} 已启动: {ps}")
        return True, "\n".join(logs) + f"\n[result] {cn} Up"
    logs.append("[deploy] 容器未启动, 部署失败")
    return False, "\n".join(logs) + f"\n[result] 容器状态: {ps}"


# ─── 原 L1608-1675 ───
def component_to_asset(db: Session, install_id: int) -> dict:
    """把部署成功的组件实例自动登记为一条子资产(挂在目标机下)。

    复用目标机 SSH 连接 + 记住容器名(aiops-<name>)与端口; 去重(同组件同名资产已存在则不重复建)。
    返回: {ok, asset} 或 {ok, already}。
    """
    from app.services.asset_service import create_asset
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r:
        raise ValueError("安装记录不存在")
    if r.status != "running":
        raise ValueError("仅运行中的组件实例可登记为资产")
    parent = db.query(Asset).filter(Asset.id == r.asset_id).first()
    if not parent:
        raise ValueError("目标机资产不存在")

    comp = db.query(ComponentCatalog).filter(ComponentCatalog.id == r.component_id).first()
    name = r.component_name
    # 组件→CI 类型映射
    db_cats = {"mysql", "redis", "mongodb", "postgresql", "elasticsearch", "mariadb", "tidb",
               "clickhouse", "influxdb", "cassandra", "neo4j", "hbase", "tdengine", "dameng",
               "kingbase", "opengauss", "oceanbase", "doris", "starrocks", "memcached", "valkey"}
    ci_type = "database" if name in db_cats else "middleware"
    cname = f"aiops-{name}"

    # 去重: 同组件名且同父(目标机)已有的不重复建
    dup = db.query(Asset).filter(
        Asset.name == name, Asset.parent_id == parent.id,
        Asset.ci_type.in_(("database", "middleware")),
    ).first()
    if dup:
        return {"ok": True, "already": True, "asset_id": dup.id, "asset": _asset_brief(db, dup)}

    # 复用目标机 SSH + 记住容器名与端口
    parent_cfg = {}
    try:
        parent_cfg = json.loads(parent.connection_config) if parent.connection_config else {}
    except Exception as _exc1:
        logger.warning("[except:pass] Exception: %s", _exc1, exc_info=True)
    cfg = {
        "ssh_user": parent_cfg.get("ssh_user", "root"),
        "ssh_password": parent_cfg.get("ssh_password", ""),
        "ssh_port": int(parent_cfg.get("ssh_port", 22)),
        "container_name": cname,
        "component": name,
        "deploy_type": r.deploy_type,
        "app_port": r.port,
    }
    attrs = {
        "source": "component-store",
        "component": name,
        "install_id": r.id,
        "deploy_type": r.deploy_type,
        "container": cname,
    }
    data = {
        "name": name,
        "ci_type": ci_type,
        "ip": parent.ip,
        "status": "online",
        "tags": f"component:{name}",
        "parent_id": parent.id,
        "connection_type": parent.connection_type or "ssh",
        "connection_config": json.dumps(cfg, ensure_ascii=False),
        "ci_attributes": json.dumps(attrs, ensure_ascii=False),
    }
    asset = create_asset(db, data)
    return {"ok": True, "asset_id": asset.id, "asset": _asset_brief(db, asset)}


# ─── 原 L1678-1683 ───
def _asset_brief(db: Session, a) -> dict:
    return {"id": a.id, "name": a.name, "ci_type": a.ci_type, "ip": a.ip,
            "status": a.status, "parent_id": a.parent_id, "connection_type": a.connection_type}


# ───────────── SSH 执行与探测(复用底座) ─────────────


# ─── 原 L1685-1759 ───
def _exec_ssh(asset: Asset, command: str, timeout: int = 30) -> tuple:
    try:
        from app.services.remediation_service import _ssh_connect
        ssh = _ssh_connect(asset, timeout=15)
    except Exception as e:
        return (False, f"SSH 连接失败: {e}")
    try:
        # ▼ 非阻塞循环读 + 硬超时: 防止后台进程继承 stdout 导致管道不 EOF
        #   (曾出现 `| tail -20` 等管道 EOF 而无限挂起, stdout.read() 永不返回)
        transport = ssh.get_transport()
        if transport is None:
            return (False, "SSH transport 不可用")
        ch = transport.open_session()
        ch.settimeout(10)
        ch.exec_command(command)
        deadline = time.time() + timeout
        out = bytearray()
        err = bytearray()
        while time.time() < deadline:
            try:
                buf = ch.recv(65536)
                if not buf:
                    break
                out += buf
            except socket.timeout:
                # 10s 无数据: 检查是否已退出且无缓冲
                if ch.exit_status_ready() and not ch.recv_ready() and not ch.recv_stderr_ready():
                    break
                continue
            except Exception:
                break
        # 命令退出后, 再读一次剩余缓冲(确保 tail 等管道输出不会因时序丢失)
        while ch.recv_ready():
            out += ch.recv(65536)
        while ch.recv_stderr_ready():
            err += ch.recv_stderr(65536)
        # 若超时, 强制关闭
        if time.time() >= deadline:
            try:
                ch.close()
            except Exception as _exc3:
                logger.warning("[except:pass] Exception: %s", _exc3, exc_info=True)
            txt_out = bytes(out).decode(errors="ignore").strip()
            txt_err = bytes(err).decode(errors="ignore").strip()
            text = (txt_out or txt_err) + "\n[SSH_TIMEOUT] 命令执行超过 %ds 已强制终止" % timeout
            return (False, text.strip())
        ssh.close()
        txt_out = bytes(out).decode(errors="ignore").strip()
        txt_err = bytes(err).decode(errors="ignore").strip()
        text = (txt_out or txt_err)
        # 若命令含 __RC__=N 标记, 以其为真实退出码判断成功; 否则退回"有输出即 ok"旧逻辑
        import re as _re
        m = _re.search(r"__RC__\s*=\s*(\d+)", text)
        if m:
            ok = (m.group(1) == "0")
        else:
            ok = (out != b"" or err == b"")
        return (ok, text)
    except Exception as e:
        try:
            ssh.close()
        except Exception as _exc2:
            logger.warning("[except:pass] Exception: %s", _exc2, exc_info=True)
        import traceback as _tb
        _err_msg = f"命令执行失败: {e} | {type(e).__name__} | {_tb.format_exc()[:200]}"
        logger.error("[_exec_ssh] %s", _err_msg)
        return (False, _err_msg)


# 简化版 CVE 库(仅作演示/基础检查; 生产应接 Trivy/Clair/Grype)
_MIN_CVE_RULES = [
    {"component": "redis", "max_safe": "7.0.0", "cve": "CVE-2021-32761", "severity": "critical", "desc": "Redis 命令注入(旧版)"},
    {"component": "nginx", "max_safe": "1.20.0", "cve": "CVE-2021-23017", "severity": "high", "desc": "Nginx DNS 解析器堆溢出"},
    {"component": "mysql", "max_safe": "5.7.10", "cve": "CVE-2016-6662", "severity": "critical", "desc": "MySQL 提权(旧版)"},
]


# ─── 原 L1768-1814 ───
def check_vuln(db: Session, install_id: int) -> Optional[dict]:
    """检查组件实例漏洞.

    优先使用 **Trivy 镜像级扫描**(生产级, SBOM + CVE 全网数据库);
    若目标机无 Trivy 或无 SSH, 回退到内置版对比 CVE 库(基础版)。
    """
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r:
        return None
    component_name = r.component_name

    asset = db.query(Asset).filter(Asset.id == r.asset_id).first()
    # 该组件对应的 docker 镜像(catalog 里取, 用于 trivy image 扫描)
    image = ""
    try:
        comp = db.query(ComponentCatalog).filter(ComponentCatalog.id == r.component_id).first()
        image = comp.docker_image or "" if comp else ""
    except Exception:
        image = ""

    result = None
    if asset and asset.connection_type == "ssh":
        result = _trivy_scan(asset, image)

    if result is None:
        # 回退: 版对比 CVE 库
        version = _probe_version(db, r)
        findings = []
        for rule in _MIN_CVE_RULES:
            if rule["component"] == component_name:
                if _version_less(version, rule["max_safe"]) if version else True:
                    findings.append({
                        "cve": rule["cve"], "severity": rule["severity"], "desc": rule["desc"],
                        "found_version": version or "unknown",
                    })
        result = {
            "component": component_name, "version": version or "未知",
            "scan_type": "version-based (基础版, 生产建议接 Trivy)",
            "findings": findings, "safe": len(findings) == 0,
            "scanned_at": datetime.now().isoformat(),
        }
    else:
        result["component"] = component_name

    r.vuln_result = json.dumps(result, ensure_ascii=False, default=str)
    db.commit()
    return result


# ─── 原 L1817-1868 ───
def _trivy_scan(asset: Asset, image: str) -> Optional[dict]:
    """在目标机上用 Trivy 扫描镜像漏洞(生产级 SBOM+CVE)。返回 None 表示无法使用 Trivy。"""
    if not image:
        return None
    # 1. 检测目标机是否有 trivy
    ok, out = _exec_ssh(asset, "command -v trivy 2>/dev/null && trivy --version 2>/dev/null | head -1 || echo NO_TRIVY")
    if not ok or "NO_TRIVY" in out or "trivy" not in out.lower():
        return None
    # 2. 用 trivy image 扫描(只输出 JSON 摘要, 限制时间避免卡死)
    cmd = f"trivy image --severity CRITICAL,HIGH,MEDIUM --no-progress --exit-code 0 --timeout 180s -f json {image} 2>/dev/null"
    ok2, raw = _exec_ssh(asset, cmd, timeout=200)
    if not ok2 or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except Exception:
        try:
            # 截取第一个 { 到最后一个 } 
            start = raw.find("{")
            end = raw.rfind("}") + 1
            data = json.loads(raw[start:end])
        except Exception:
            return None
    # 聚合处理结果
    vulns = data.get("Results", []) if isinstance(data, dict) else []
    total = {"critical": 0, "high": 0, "medium": 0}
    findings = []
    for res in vulns:
        for v in (res.get("Vulnerabilities") or []):
            sev = (v.get("Severity") or "").lower()
            if sev in ("critical", "high", "medium"):
                total[sev] = total.get(sev, 0) + 1
            findings.append({
                "cve": v.get("VulnerabilityID", ""),
                "severity": v.get("Severity", ""),
                "desc": (v.get("Title") or "")[:120],
                "pkg": v.get("PkgName", ""),
                "installed": v.get("InstalledVersion", ""),
                "fixed": v.get("FixedVersion", "") or None,
            })
    target = data.get("ArtifactName", image) if isinstance(data, dict) else image
    safe = total["critical"] == 0 and total["high"] == 0
    return {
        "image": target,
        "scan_type": "trivy-image (生产级 SBOM+CVE)",
        "summary": total,
        "findings": findings[:50],
        "safe": safe,
        "count_critical": total["critical"],
        "count_high": total["high"],
        "scanned_at": datetime.now().isoformat(),
    }


# ─── 原 L1871-1885 ───
def _probe_version(db: Session, r: ComponentInstall) -> str:
    asset = db.query(Asset).filter(Asset.id == r.asset_id).first()
    if not asset or asset.connection_type != "ssh":
        return ""
    cmds = {
        "redis": "redis-cli --version 2>/dev/null | head -1",
        "nginx": "nginx -v 2>&1 | head -1",
        "mysql": "mysql --version 2>/dev/null | head -1",
    }
    cmd = cmds.get(r.component_name, f"{r.component_name} --version 2>/dev/null | head -1")
    ok, out = _exec_ssh(asset, cmd)
    return (out or "").strip()[:60]


# ───────────── AI 综合分析 ─────────────


# ─── 原 L1887-1953 ───
def ai_analyze(db: Session, install_id: int) -> dict:
    """对组件实例做 AI 综合健康分析: 配置/高可用/漏洞 => 健康结论与建议"""
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r:
        raise ValueError("安装记录不存在")
    asset = db.query(Asset).filter(Asset.id == r.asset_id).first()
    asset_name = asset.name if asset else f"资产#{r.asset_id}"

    config = {}
    try:
        config = json.loads(r.config_result) if r.config_result else {}
    except Exception:
        config = {}
    health = {}
    try:
        health = json.loads(r.health_result) if r.health_result else {}
    except Exception:
        health = {}
    vuln = {}
    try:
        vuln = json.loads(r.vuln_result) if r.vuln_result else {}
    except Exception:
        vuln = {}

    from app.services.agent_service import call_llm
    from app.models import AIProvider
    provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()  # noqa: E712
    if not provider:
        return {
            "ai_generated": False,
            "summary": f"{r.component_name} 实例健康分析(无 AI provider, 基于探测) 状态={r.status} 配置={r.config_check_status} 健康={r.health_status}",
            "severity": "medium", "health_status": r.health_status,
        }

    system = """你是 SRE 组件健康专家。根据组件实例的配置/高可用/漏洞检查结果, 输出综合健康分析。只输出 JSON:
{"summary":"总体结论","health_score":0-100,"issues":[{"item":"...","level":"info|warning|critical","advice":"..."}],
 "recommendations":["建议1","建议2"],"severity":"low|medium|high"}"""
    user = f"""组件: {r.component_name} (资产: {asset_name}, 部署: {r.deploy_type})
运行状态: {r.status}
配置检查: {json.dumps(config, ensure_ascii=False, default=str)[:1200]}
高可用/健康: {json.dumps(health, ensure_ascii=False, default=str)[:1200]}
漏洞检查: {json.dumps(vuln, ensure_ascii=False, default=str)[:1200]}
请输出综合健康分析 JSON。"""
    try:
        resp = call_llm(provider, [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        parsed = json.loads(content)
        parsed["ai_generated"] = True
        parsed["health_status"] = r.health_status
    except Exception:
        parsed = {
            "ai_generated": False,
            "summary": f"{r.component_name} 综合分析完成(规则模式) 状态={r.status}",
            "severity": "medium", "health_status": r.health_status,
            "recommendations": [],
        }
    r.ai_analysis = json.dumps(parsed, ensure_ascii=False)
    db.commit()
    parsed["summary_block"] = _build_component_key_points(parsed)
    return parsed


# ─── 原 L1956-1968 ───
def _build_component_key_points(parsed: dict) -> dict:
    """从组件 AI 健康分析结果组装统一三要素要点(根因/方案/影响)。"""
    from app.routers.agent_sse import _clean_key_point  # 延迟导入, 避免启动时序循环导入
    issues = parsed.get("issues") or []
    criticals = [i for i in issues if str(i.get("level", "")).lower() in ("critical", "warning")]
    root_cause = parsed.get("summary", "") or f"{'发现 ' + str(len(criticals)) + ' 项风险' if criticals else '组件健康检查通过'}"
    recs = parsed.get("recommendations") or []
    solution = "；".join([str(r) for r in recs[:3]]) if recs else "按风险项逐项修复，复检确认健康"
    impact = f"健康评分 {parsed.get('health_score', '-')}，风险项 {len(criticals)} / {len(issues)}"
    return {
        "root_cause": _clean_key_point(root_cause, 100),
        "solution": _clean_key_point(solution, 160),
        "impact": _clean_key_point(impact, 100),
    }


# ─── 原 L1971-2016 ───
def get_stats(db: Session) -> dict:
    total = db.query(ComponentCatalog).count()
    by_cat = {}
    for c in db.query(ComponentCatalog).all():
        by_cat[c.category] = by_cat.get(c.category, 0) + 1
    installs = db.query(ComponentInstall).count()
    running = db.query(ComponentInstall).filter(ComponentInstall.status == "running").count()
    return {
        "total_components": total,
        "by_category": by_cat,
        "total_installs": installs,
        "running_installs": running,
    }


# ───────────── 配置优化 & 高可用 检查 ─────────────

# 各组件的健康探测命令(SSH)
_HEALTH_CMDS = {
    "redis": "redis-cli ping 2>/dev/null || docker exec aiops-redis redis-cli ping 2>/dev/null",
    "nginx": "nginx -t 2>&1 >/dev/null; curl -s -o /dev/null -w '%{http_code}' http://localhost/ 2>/dev/null",
    "mysql": "mysqladmin ping 2>/dev/null || docker exec aiops-mysql mysqladmin ping 2>/dev/null",
    "kafka": "ss -ltn 2>/dev/null | grep 9092 >/dev/null && echo LISTEN || echo DOWN",
    "rabbitmq": "rabbitmqctl status 2>/dev/null | head -1 || curl -s -o /dev/null -w '%{http_code}' http://localhost:15672/",
    "elasticsearch": "curl -s http://localhost:9200/_cluster/health 2>/dev/null | head -1",
    "mongodb": "mongosh --eval 'db.runCommand({ping:1})' 2>/dev/null | grep -q ok && echo OK || echo DOWN",
    "postgresql": "pg_isready 2>/dev/null || docker exec aiops-postgresql pg_isready 2>/dev/null",
}
_CONFIG_FILES = {
    "redis": "redis.conf", "nginx": "nginx.conf", "mysql": "my.cnf",
    "postgresql": "postgresql.conf", "elasticsearch": "elasticsearch.yml",
    "rabbitmq": "rabbitmq.conf", "mongodb": "mongod.conf",
}

# native 安装后验证: name -> (探测命令, 判定为成功的关键字)
_NATIVE_VERIFY = {
    "redis": ("redis-cli ping 2>/dev/null | grep -q PONG && echo UP || systemctl is-active redis 2>/dev/null | grep -xq 'active' && echo UP || echo DOWN", ["UP"]),
    "mysql": ("mysqladmin ping 2>/dev/null | grep -q alive && echo UP || systemctl is-active mysqld 2>/dev/null | grep -xq 'active' && echo UP || echo DOWN", ["UP"]),
    "nginx": ("(nginx -t 2>&1 | grep -q 'syntax is ok') && echo UP || echo DOWN", ["UP"]),
    "rabbitmq": ("rabbitmqctl status 2>/dev/null | grep -q RabbitMQ && echo UP || echo DOWN", ["UP"]),
    "kafka": ("ss -ltn 2>/dev/null | grep -q 9092 && echo UP || echo DOWN", ["UP"]),
    "elasticsearch": ("curl -s http://localhost:9200 2>/dev/null | grep -q cluster_name && echo UP || echo DOWN", ["UP"]),
    "mongodb": ("ss -ltn 2>/dev/null | grep ':27017 ' >/dev/null && echo UP || echo DOWN", ["UP"]),
    "postgresql": ("pg_isready 2>/dev/null | grep -qi accepting && echo UP || systemctl is-active postgresql 2>/dev/null | grep -xq 'active' && echo UP || echo DOWN", ["UP"]),
    "memcached": ("pidof memcached >/dev/null 2>&1 && echo UP || echo DOWN", ["UP"]),
}


# ─── 原 L2019-2068 ───
def check_config(db: Session, install_id: int) -> dict:
    """配置优化检查: 复用 config_drift_service(基线+漂移+AI推荐)"""
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r:
        raise ValueError("安装记录不存在")
    component_name = r.component_name
    cfg_key = _CONFIG_FILES.get(component_name, f"{component_name}.conf")

    from app.services import config_drift_service as cds
    result = {"component": component_name, "config_key": cfg_key, "checks": [], "ai": None}

    # 1. 基线采集(capture) 若已有基线则检测漂移
    asset = db.query(Asset).filter(Asset.id == r.asset_id).first()
    if not asset:
        result["error"] = "目标机资产不存在"
        return result
    try:
        # 尝试建立/检测基线
        baseline = cds.capture_baseline(db, r.asset_id, cfg_key, config_name=f"{component_name} 配置", category=component_name)
        result["baseline_version"] = baseline.get("version")
        drift = cds.detect_drift(db, r.asset_id, cfg_key)
        if drift.get("drifted"):
            result["checks"].append({"item": cfg_key, "status": "drift", "detail": drift.get("diff_text")})
            record_id = drift.get("record_id")
            if record_id:
                try:
                    result["ai"] = cds.ai_assess(db, record_id)
                except Exception as _exc3:
                    logger.warning("[except:pass] Exception: %s", _exc3, exc_info=True)
        else:
            result["checks"].append({"item": cfg_key, "status": "pass", "detail": "配置与基线一致, 无漂移"})
    except Exception as e:
        result["checks"].append({"item": cfg_key, "status": "error", "detail": f"配置检查失败: {e}"})

    if result["checks"]:
        sts = [c["status"] for c in result["checks"]]
        if all(s == "pass" for s in sts):
            cfg_status = "pass"
        elif any(s == "error" for s in sts):
            cfg_status = "error"
        elif any(s in ("drift", "warn") for s in sts):
            cfg_status = "drift"
        else:
            cfg_status = "drift"
    else:
        cfg_status = "pending"
    r.config_check_status = cfg_status
    r.config_result = json.dumps(result, ensure_ascii=False, default=str)
    db.commit()
    return result


# ─── 原 L2071-2137 ───
def check_health(db: Session, install_id: int) -> dict:
    """高可用/健康检查: SSH 探测组件运行状态 + 版本"""
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r:
        raise ValueError("安装记录不存在")
    asset = db.query(Asset).filter(Asset.id == r.asset_id).first()
    results = []
    healthy = True
    deploy_type = r.deploy_type or ""
    if asset and asset.connection_type == "ssh":
        if deploy_type == "docker":
            # docker 部署: 直接探测容器运行状态(权威), 再叠加组件专属命令
            cn = f"aiops-{r.component_name}"
            cok, cout = _exec_ssh(asset, f"docker ps --filter name={cn} --filter status=running --format '{{{{.Names}}}}' | grep -q '{cn}' && echo OK || echo DOWN")
            c_up = "ok" in cout.lower()
            results.append({"check": "容器运行状态", "command": f"docker ps --filter name={cn}", "output": (cout or "")[:150], "healthy": c_up})
            spec_cmd = _HEALTH_CMDS.get(r.component_name)
            if spec_cmd:
                sok, sout = _exec_ssh(asset, spec_cmd)
                s_up = any(k in sout.lower() for k in ("ok", "pong", "alive", "listen", "ready", "200", "green", "yellow", "running", "up"))
                results.append({"check": "组件探测", "command": spec_cmd, "output": (sout or "")[:150], "healthy": s_up})
                healthy = c_up and s_up
            else:
                healthy = c_up
        else:
            # redis/valkey: 用真实 PONG 探测(不看 systemd 状态, 因 --supervised systemd 常显示 deactivating 而非 active, 会误判 unhealthy)
            if r.component_name in ("redis", "valkey"):
                _rc_port = r.port or 6379
                _rc_pwd = ""
                try:
                    _rc_pwd = str((json.loads(r.deploy_params or "{}") or {}).get("redis_password") or "")
                except Exception:
                    _rc_pwd = ""
                _rc_cmd = (f"grep -q PONG <<< \"$(timeout 6 redis-cli -p {_rc_port} -a '{_rc_pwd}' ping 2>/dev/null)\" && echo UP "
                           f"|| grep -q PONG <<< \"$(timeout 6 redis-cli -p {_rc_port} -a \"$(cat /tmp/.aiops_{r.component_name}_pw 2>/dev/null)\" ping 2>/dev/null)\" && echo UP "
                           f"|| grep -q PONG <<< \"$(timeout 6 redis-cli -p {_rc_port} ping 2>/dev/null)\" && echo UP "
                           f"|| echo DOWN")
                _ok, _out = _exec_ssh(asset, _rc_cmd)
                _up = "DOWN" not in _out and "UP" in _out
                healthy = bool(_up)
                results.append({"check": "组件运行状态", "command": f"redis-cli -p {_rc_port} ping", "output": ("PONG" if _up else (_out or "")[:200]), "healthy": healthy})
            else:
                cmd = _HEALTH_CMDS.get(r.component_name, f"systemctl is-active {r.component_name} 2>/dev/null || echo DOWN")
                ok, out = _exec_ssh(asset, cmd)
                up = "ok" in out.lower() or "pong" in out.lower() or "alive" in out.lower() or "listen" in out.lower() or "ready" in out.lower() or "200" in out or "green" in out.lower() or "yellow" in out.lower()
                healthy = ok and up
                results.append({"check": "组件运行状态", "command": cmd, "output": (out or "")[:200], "healthy": healthy})
    else:
        results.append({"check": "目标机连通", "healthy": False, "output": "资产非 SSH 或不存在"})
        healthy = False
    # 高可用模式检查
    ha = {}
    try:
        comp = db.query(ComponentCatalog).filter(ComponentCatalog.id == r.component_id).first()
        ha = json.loads(comp.ha_config) if comp and comp.ha_config else {}
    except Exception as _exc4:
        logger.warning("[except:pass] Exception: %s", _exc4, exc_info=True)
    status = "healthy" if healthy else "unhealthy"
    result = {
        "component": r.component_name, "deploy_type": r.deploy_type,
        "ha_mode": ha.get("mode", "single"), "health_status": status,
        "checks": results, "checked_at": datetime.now().isoformat(),
    }
    r.health_status = status
    r.health_result = json.dumps(result, ensure_ascii=False, default=str)
    db.commit()
    return result


# ─── 原 L2140-2187 ───
def full_health_check(db: Session, install_id: int) -> dict:
    """四合一体检闭环: 一键同时执行 健康→配置→漏洞→AI综合分析, 返回整合报告。
    对应组件商店「一句话/一键全面体检」。"""
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r:
        raise ValueError("安装记录不存在")
    component_name = r.component_name
    result = {
        "component": component_name,
        "asset_id": r.asset_id,
        "deploy_type": r.deploy_type,
        "checked_at": datetime.now().isoformat(),
        "health": None, "config": None, "vuln": None, "ai": None,
        "overall_status": "pending",
    }
    # 1. 高可用/健康
    try:
        result["health"] = check_health(db, install_id)
        result["health_status"] = result["health"].get("health_status")
    except Exception as e:
        result["health"] = {"error": str(e)}
    # 2. 配置优化
    try:
        result["config"] = check_config(db, install_id)
        result["config_check_status"] = result["config"]["checks"][0]["status"] if result["config"].get("checks") else "pending"
    except Exception as e:
        result["config"] = {"error": str(e)}
    # 3. 漏洞
    try:
        result["vuln"] = check_vuln(db, install_id)
    except Exception as e:
        result["vuln"] = {"error": str(e)}
    # 4. AI 综合分析
    try:
        result["ai"] = ai_analyze(db, install_id)
    except Exception as e:
        result["ai"] = {"error": str(e), "ai_generated": False}
    # overall 判定
    health_ok = result["health"] and result["health"].get("health_status") == "healthy"
    config_ok = result.get("config_check_status") in ("pass", None)
    vuln_ok = result["vuln"] and result["vuln"].get("safe") is True
    if health_ok and config_ok and vuln_ok:
        result["overall_status"] = "healthy"
    elif health_ok or config_ok is None:
        result["overall_status"] = "degraded"
    else:
        result["overall_status"] = "unhealthy"
    return result


# ─── 原 L2190-2221 ───
def batch_full_check(db: Session, limit: int = 50) -> dict:
    """批量四合一体检: 对所有 running 组件实例执行 健康+配置+漏洞+AI 分析。
    用于组件商店「一键体检全部实例」/ 定时巡检任务。"""
    installs = db.query(ComponentInstall).filter(
        ComponentInstall.status == "running",
    ).order_by(ComponentInstall.updated_at.desc()).limit(limit).all()

    results = []
    for r in installs:
        try:
            res = full_health_check(db, r.id)
            results.append({
                "install_id": r.id, "component": r.component_name,
                "asset_id": r.asset_id, "overall_status": res.get("overall_status"),
                "health_status": res.get("health_status"),
                "config_check_status": res.get("config_check_status"),
                "vuln_safe": (res.get("vuln") or {}).get("safe"),
                "ai_generated": (res.get("ai") or {}).get("ai_generated", False),
            })
        except Exception as e:
            results.append({"install_id": r.id, "component": r.component_name, "error": str(e)})

    healthy = sum(1 for x in results if x.get("overall_status") == "healthy")
    degraded = sum(1 for x in results if x.get("overall_status") == "degraded")
    unhealthy = sum(1 for x in results if x.get("overall_status") == "unhealthy")
    return {
        "total": len(results),
        "healthy": healthy, "degraded": degraded, "unhealthy": unhealthy,
        "results": results,
        "scanned_at": datetime.now().isoformat(),
        "summary_block": _build_full_health_key_points(len(results), healthy, degraded, unhealthy),
    }


# ─── 原 L2224-2237 ───
def _build_full_health_key_points(total, healthy, degraded, unhealthy) -> dict:
    """从四合一体检结果组装统一三要素要点(根因/方案/影响)。"""
    from app.routers.agent_sse import _clean_key_point  # 延迟导入
    if unhealthy or degraded:
        root_cause = f"体检发现 {unhealthy} 项不健康、{degraded} 项降级"
        solution = "优先处理不健康项，排查降级原因并修复"
    else:
        root_cause = f"体检全部通过（{healthy}/{total} 项健康）"
        solution = "保持当前配置与运行状态，定期复检"
    impact = f"共 {total} 项检查：健康 {healthy}、降级 {degraded}、不健康 {unhealthy}"
    return {
        "root_cause": _clean_key_point(root_cause, 100),
        "solution": _clean_key_point(solution, 160),
        "impact": _clean_key_point(impact, 100),
    }


# ─── 原 L2240-2341 ───
def generate_ai_health_report(db: Session, install_id: int) -> dict:
    """为安装记录生成**可读的 AI 全面体检报告**(对标 AI 部署报告版式)。

    运行四合一体检(健康/配置/漏洞/AI)后, 把原始 JSON 组织成结构化、可直接阅读的
    报告字段: title/status/executive_summary/kpi/各维度小节/issues/recommendations/risk_assessment。
    AI provider 可用时用 AI 润色总体结论, 否则基于检查结果规则兜底。
    """
    r = db.query(ComponentInstall).filter(ComponentInstall.id == install_id).first()
    if not r:
        raise ValueError("安装记录不存在")
    asset = db.query(Asset).filter(Asset.id == r.asset_id).first()
    asset_name = asset.name if asset else f"资产#{r.asset_id}"
    res = full_health_check(db, install_id)
    overall = res.get("overall_status") or "unknown"

    health = res.get("health") or {}
    config = res.get("config") or {}
    vuln = res.get("vuln") or {}
    ai = res.get("ai") or {}

    # KPI 卡片
    health_checks = health.get("checks") or []
    ok_count = sum(1 for c in health_checks if c.get("healthy"))
    bad_count = sum(1 for c in health_checks if not c.get("healthy"))
    vuln_findings = (vuln.get("findings") or [])
    vuln_crit = vuln.get("count_critical") or 0
    vuln_high = vuln.get("count_high") or 0
    config_checks = (config.get("checks") or [])
    config_pass = sum(1 for c in config_checks if str(c.get("status")) in ("pass", "ok", "healthy", "通过"))
    config_bad = len(config_checks) - config_pass
    ai_issues = (ai.get("issues") or [])
    ai_recs = (ai.get("recommendations") or [])

    # 汇总各维度中文描述
    health_desc = []
    for c in health_checks:
        health_desc.append(f"{'✅' if c.get('healthy') else '❌'} {c.get('check') or ''}: {(c.get('output') or '').strip()[:80]}")
    config_desc = []
    for c in config_checks:
        st = c.get("status") or ""
        config_desc.append(f"[{st}] {c.get('name') or c.get('key') or ''} {c.get('recommendation') or ''}".strip())
    vuln_desc = []
    for f in vuln_findings:
        vuln_desc.append(f"[{f.get('severity') or ''}] {f.get('cve') or f.get('desc') or ''} ({f.get('pkg') or ''})")
    if not vuln_findings:
        vuln_desc.append("未发现中高危漏洞" if vuln.get("safe") else "存在中高危漏洞, 详见漏洞明细")

    status_map = {"healthy": "健康", "degraded": "亚健康", "unhealthy": "不健康", "pending": "待评估"}
    ai_summary = (ai.get("summary") or "") if isinstance(ai, dict) else ""
    overall_text = {
        "healthy": "整体健康", "degraded": "部分健康(亚健康)", "unhealthy": "存在风险", "pending": "待评估",
    }.get(overall, overall)

    # 汇总 issues(健康异常 + 漏洞 + AI issues)
    issues = []
    for c in health_checks:
        if not c.get("healthy"):
            issues.append({"severity": "high", "description": f"健康检查未通过: {c.get('check') or ''} - {(c.get('output') or '').strip()[:80]}", "resolution": ""})
    for f in vuln_findings:
        sev = (f.get("severity") or "").lower()
        if sev in ("critical", "high"):
            issues.append({"severity": "high", "description": f"镜像漏洞 {f.get('cve') or f.get('desc') or ''} ({f.get('pkg') or ''})", "resolution": f"升级至 {f.get('fixed') or '最新版'}" if f.get("fixed") else ""})
    for it in ai_issues:
        issues.append({"severity": (it.get("level") or "info"), "description": (it.get("item") or "")[:160], "resolution": (it.get("advice") or "")})

    recommendations = list(ai_recs)
    if not recommendations:
        health_ok = bool(health_checks) and all(c.get("healthy") for c in health_checks)
        if not health_ok:
            recommendations.append("请检查目标机组件进程/容器运行状态并恢复正常")
        if vuln_crit or vuln_high:
            recommendations.append("请优先修复镜像高危/严重漏洞(升级或加固)")
        if config_bad:
            recommendations.append("请按配置优化建议调整组件配置")
        if not recommendations:
            recommendations.append("检查结果正常, 建议定期巡检保持健康")

    report = {
        "type": "ai_health",
        "title": f"{r.component_name} AI 全面体检报告",
        "status": overall,
        "overall_assessment": f"{overall_text}({asset_name} · {r.deploy_type} 部署 · 端口 {r.port or '-'})",
        "executive_summary": (ai_summary or f"{r.component_name} 体检完成, 总体状态 {overall_text}。健康检查 {ok_count}/{len(health_checks) or 1} 项通过, 配置 {config_pass}/{len(config_checks) or 1} 项通过, 漏洞 {len(vuln_findings)} 项。")[:500],
        "kpi": {
            "overall_status": overall,
            "health_passed": ok_count, "health_total": len(health_checks),
            "config_passed": config_pass, "config_total": len(config_checks),
            "vuln_count": len(vuln_findings),
            "vuln_critical": vuln_crit, "vuln_high": vuln_high,
            "ai_issues": len(ai_issues), "ai_recs": len(ai_recs),
            "ai_generated": bool((ai or {}).get("ai_generated")),
            "checked_at": (res.get("checked_at") or "")[:16].replace("T", " "),
        },
        "health_section": {"title": "高可用/健康检查", "status": (health.get("health_status") or "unknown"), "rows": health_desc},
        "config_section": {"title": "配置优化检查", "status": (res.get("config_check_status") or "pending"), "rows": config_desc},
        "vuln_section": {"title": "漏洞检查", "status": ("安全" if vuln.get("safe") else "存在风险"), "rows": vuln_desc, "safe": vuln.get("safe") is True},
        "issues": issues,
        "recommendations": recommendations,
        "risk_assessment": ("存在中高危漏洞或健康异常, 建议尽快处理" if issues else "当前未发现明显风险, 状态良好")[:200],
    }
    report["summary_block"] = _build_component_report_key_points(report)
    return report


# ─── 原 L2344-2363 ───
def _build_component_report_key_points(report: dict) -> dict:
    """从组件体检报告组装统一三要素要点(根因/方案/影响)。"""
    from app.routers.agent_sse import _clean_key_point  # 延迟导入
    kpi = report.get("kpi") or {}
    root_cause = report.get("executive_summary", "") or "组件健康体检完成"
    recs = report.get("recommendations") or []
    solution = "；".join([str(r) for r in recs[:3]]) if recs else (
        "按风险项优先处理，复检确认健康恢复"
    )
    impact = f"健康 {kpi.get('health_passed', 0)}/{kpi.get('health_total', 0)} 项通过，漏洞 {kpi.get('vuln_count', 0)} 项（高危 {kpi.get('vuln_high', 0)}）"
    return {
        "root_cause": _clean_key_point(root_cause, 100),
        "solution": _clean_key_point(solution, 160),
        "impact": _clean_key_point(impact, 100),
    }


