from sqlalchemy.orm import Session

from app.models import Asset
from app.database import get_session_for, get_db_mode
import json
import os


def build_connection_config(payload: dict) -> dict:
    """根据 payload 字段构造 connection_config dict.

    字段名以 CONTRACT.md 为准（Single Source of Truth）。
    """
    ct = payload.get("connection_type", "ssh")
    base = {}
    if payload.get("connection_config"):
        try:
            base = json.loads(payload["connection_config"]) if isinstance(payload["connection_config"], str) else payload["connection_config"]
        except Exception:
            base = {}

    if ct == "ssh":
        return {
            "ssh_user": payload.get("ssh_user", base.get("ssh_user", "root")),
            "ssh_password": payload.get("ssh_password", base.get("ssh_password", "")),
            "ssh_port": int(payload.get("ssh_port", base.get("ssh_port", 22))),
        }
    elif ct == "winrm":
        return {
            "winrm_user": payload.get("winrm_user", base.get("winrm_user", "Administrator")),
            "winrm_password": payload.get("winrm_password", base.get("winrm_password", "")),
            "winrm_port": int(payload.get("winrm_port", base.get("winrm_port", 5985))),
            "winrm_transport": payload.get("winrm_transport", base.get("winrm_transport", "ntlm")),
            "winrm_ssl": payload.get("winrm_ssl", base.get("winrm_ssl", False)),
        }
    elif ct == "kubernetes":
        cfg = dict(base)
        if payload.get("k8s_api_server"):
            cfg["k8s_api_server"] = payload["k8s_api_server"]
        if payload.get("k8s_token"):
            cfg["k8s_token"] = payload["k8s_token"]
        if payload.get("k8s_namespace"):
            cfg["k8s_namespace"] = payload["k8s_namespace"]
        return cfg
    elif ct == "snmp":
        return {
            "snmp_community": payload.get("snmp_community", base.get("snmp_community", "public")),
            "snmp_port": int(payload.get("snmp_port", base.get("snmp_port", 161))),
            "snmp_version": payload.get("snmp_version", base.get("snmp_version", "v2c")),
        }
    elif ct == "http":
        cfg = dict(base)
        if payload.get("http_url"):
            cfg["http_url"] = payload["http_url"]
        if payload.get("http_auth"):
            cfg["http_auth"] = payload["http_auth"]
        if payload.get("http_credential"):
            cfg["http_credential"] = payload["http_credential"]
        if payload.get("mw_subtype"):
            cfg["mw_subtype"] = payload["mw_subtype"]
        if payload.get("mw_port") is not None:
            cfg["mw_port"] = int(payload["mw_port"])
        if payload.get("mw_admin_url"):
            cfg["mw_admin_url"] = payload["mw_admin_url"]
        return cfg
    elif ct == "database":
        return {
            "db_type": payload.get("db_type", base.get("db_type", "mysql")),
            "db_port": int(payload.get("db_port", base.get("db_port", 3306))),
            "db_user": payload.get("db_user", base.get("db_user", "root")),
            "db_password": payload.get("db_password", base.get("db_password", "")),
            "db_name": payload.get("db_name", base.get("db_name", "")),
        }
    return {}


def list_assets(db: Session, search: str = "", type: str = "", ci_type: str = ""):
    q = db.query(Asset)
    if search:
        q = q.filter(Asset.name.ilike(f"%{search}%"))
    if type:
        q = q.filter(Asset.ci_type == type)
    if ci_type:
        types = [t.strip() for t in ci_type.split(",") if t.strip()]
        if len(types) == 1:
            q = q.filter(Asset.ci_type == types[0])
        elif types:
            q = q.filter(Asset.ci_type.in_(types))
    return q.order_by(Asset.id.desc()).all()


def list_assets_paged(db: Session, search: str = "", type: str = "", ci_type: str = "", page: int = 1, page_size: int = 20, exclude_types: set = None):
    q = db.query(Asset)
    if search:
        q = q.filter(Asset.name.ilike(f"%{search}%"))
    if type:
        q = q.filter(Asset.ci_type == type)
    if ci_type:
        types = [t.strip() for t in ci_type.split(",") if t.strip()]
        if len(types) == 1:
            q = q.filter(Asset.ci_type == types[0])
        elif types:
            q = q.filter(Asset.ci_type.in_(types))
    if exclude_types:
        q = q.filter(Asset.ci_type.notin_(exclude_types))
    total = q.count()
    assets = q.order_by(Asset.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return assets, total


def list_by_ci_type(db: Session, ci_type: str):
    return db.query(Asset).filter(Asset.ci_type == ci_type).order_by(Asset.name).all()


def get_asset(db: Session, asset_id: int):
    return db.query(Asset).filter(Asset.id == asset_id).first()


# ─── AI 访问模式（生产只读铁闸）────────────────────────────────────
# 字段契约见 CONTRACT.md:
#   environment   : production / non-production
#   ai_access_mode: read-only / read-write（仅对生产资产生效）
# 有效权限 effective = 非生产→read-write（生产资产才受 ai_access_mode 约束）;
# 生产 + read-only → 只读铁闸（任何写操作一律拒绝）;
# 生产 + read-write → 豁免模式（可写, 但仍走人工确认）。

_SERVER_CI_TYPES = {"server", "virtual_machine", "cloud_host", "vm"}


def _resolve_parent_access(db: Session, asset) -> str:
    """非服务器资产: 沿父链追溯其宿主的服务器(s)环境与 AI 访问模式.

    任一环上的服务器处于生产只读铁闸 → 返回 read-only(最高优先级/安全收敛)。
    仅当整条父链都放行(或无父级→默认非生产)返回 read-write。
    """
    seen = set()
    cur = asset
    while cur is not None:
        if cur.id in seen:
            break
        seen.add(cur.id)
        ci = (cur.ci_type or "").lower()
        if ci in _SERVER_CI_TYPES:
            env = getattr(cur, "environment", None) or "non-production"
            if env == "production":
                mode = getattr(cur, "ai_access_mode", None) or "read-only"
                if mode != "read-write":
                    return "read-only"
                # 生产但已豁免: 继续向上看父链(若该服务器自身也是子)是否还有更严的生产只读
        if cur.parent_id is None:
            break
        cur = db.query(Asset).filter(Asset.id == cur.parent_id).first()
    return "read-write"


def effective_ai_access(db: Session, asset) -> str:
    """返回资产对 AI 的有效访问模式: 'read-only' / 'read-write'.

    服务器资产: 由自身 environment + ai_access_mode 决定(生产默认 read-only, 可豁免 read-write)。
    非服务器资产: 自身不存环境, 沿父链继承宿主的服务器环境(见 _resolve_parent_access)。
    """
    if asset is None:
        return "read-write"
    ci = (asset.ci_type or "").lower()
    if ci in _SERVER_CI_TYPES:
        env = getattr(asset, "environment", None) or "non-production"
        if env == "production":
            mode = getattr(asset, "ai_access_mode", None) or "read-only"
            return "read-only" if mode != "read-write" else "read-write"
        return "read-write"
    return _resolve_parent_access(db, asset)


def effective_environment(db: Session, asset) -> str:
    """返回资产的有效环境: 'production' / 'non-production'.

    服务器资产: 看自身 environment。
    非服务器资产: 沿父链追溯宿主的服务器 environment(父勾生产则也为 production)。
    用于前端「是否生产环境」勾选框的置灰跟随显示。
    """
    if asset is None:
        return "non-production"
    ci = (asset.ci_type or "").lower()
    if ci in _SERVER_CI_TYPES:
        return "production" if (getattr(asset, "environment", None) or "non-production") == "production" else "non-production"
    # 非服务器: 向上找第一个服务器祖先, 取它的 environment
    seen = set()
    cur = asset
    parent_env = None
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        _ci = (cur.ci_type or "").lower()
        if _ci in _SERVER_CI_TYPES:
            parent_env = getattr(cur, "environment", None) or "non-production"
            break
        if cur.parent_id is None:
            break
        cur = db.query(Asset).filter(Asset.id == cur.parent_id).first()
    if parent_env is None:
        return "non-production"
    return "production" if parent_env == "production" else "non-production"


def extract_asset_id_from_payload(payload: dict):
    """从动作 payload / context 中尽力解析目标资产 ID（无则 None）."""
    if not isinstance(payload, dict):
        return None
    for k in ("asset_id", "assetId", "target_asset_id"):
        if payload.get(k) is not None:
            try:
                return int(payload[k])
            except (TypeError, ValueError):
                break
    # 嵌套在 data / context / asset 里
    for nest in ("data", "context", "asset", "target", "params"):
        v = payload.get(nest)
        if isinstance(v, dict):
            for k in ("asset_id", "assetId", "id"):
                if v.get(k) is not None:
                    try:
                        return int(v[k])
                    except (TypeError, ValueError):
                        break
    return None


def assert_ai_writable(db: Session, payload: dict):
    """若目标资产为只读铁闸, 返回拒绝原因字符串; 否则返回 None（放行）."""
    asset_id = extract_asset_id_from_payload(payload)
    if not asset_id:
        return None
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return None
    if effective_ai_access(db, asset) == "read-only":
        return (f"资产「{asset.name}」(id={asset_id}) 为生产环境只读模式，AI 禁止执行任何写操作。"
                f"如需运维操作，请先在资产管理中对该资产临时开启豁免（备注处理原因），操作完成后及时关闭。")
    return None


def create_asset(db: Session, data: dict):
    from sqlalchemy import text
    max_id = db.execute(text("SELECT COALESCE(MAX(id), 0) FROM assets")).scalar() or 0
    data["id"] = max_id + 1
    asset = Asset(**data)
    db.add(asset)
    db.commit()
    return asset


def update_asset(db: Session, asset_id: int, data: dict):
    asset = get_asset(db, asset_id)
    if not asset:
        return None
    try:
        from app.services.asset_change_service import log_change
        for k, v in data.items():
            old = str(getattr(asset, k, ""))
            setattr(asset, k, v)
            if str(v) != old:
                log_change(db, asset_id, k, old, str(v), "user")
    except Exception:
        for k, v in data.items():
            setattr(asset, k, v)
    db.commit()
    db.refresh(asset)
    return asset


def delete_asset(db: Session, asset_id: int):
    asset = get_asset(db, asset_id)
    if not asset:
        return False
    db.query(Asset).filter(Asset.parent_id == asset_id).update({"parent_id": None})
    db.delete(asset)
    db.commit()
    return True




def probe_assets(db: Session):
    """批量探测所有资产的连接状态，更新 status / last_checked_at / latency_ms"""
    from app.services.connection_service import ConnectionTester
    from app.logger import logger
    from datetime import datetime
    import json
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    import socket

    assets = db.query(Asset).all()
    changed = []

    def _probe_db_factory():
        return get_session_for(get_db_mode())()

    _lock = threading.Lock()

    def _probe_middleware_port(ip, port, timeout=5):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            t0 = datetime.now()
            s.connect((ip, int(port)))
            lat = int((datetime.now() - t0).total_seconds() * 1000)
            s.close()
            return {"ok": True, "message": f"端口 {port} 连通", "latency_ms": lat}
        except Exception as e:
            return {"ok": False, "message": f"端口 {port} 不通: {e}"}

    def _probe_ping(ip, timeout=3):
        """ICMP 连通探活（跨平台调用系统 ping）。"""
        import subprocess
        import os as _os
        if not ip:
            return {"ok": False, "message": "无 IP 地址"}
        if _os.name == "nt":
            cmd = ["ping", "-n", "1", "-w", str(int(timeout) * 1000), ip]
        else:
            cmd = ["ping", "-c", "1", "-W", str(int(timeout)), ip]
        try:
            t0 = datetime.now()
            r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout + 3)
            lat = int((datetime.now() - t0).total_seconds() * 1000)
            return {"ok": r.returncode == 0, "message": "ICMP 可达" if r.returncode == 0 else "ICMP 不可达", "latency_ms": lat}
        except Exception as e:
            return {"ok": False, "message": f"ICMP 探测异常: {e}"}

    def _probe_ssh_lowfreq(sess, asset_inst, config, ssh_interval=300):
        """SSH 探活：低频(默认 300s 才真正 SSH 一次) + 失败自动降级为 TCP(22 端口/业务端口)。

        高频 SSH 并发探活会触发目标机 sshd 半开队列（MaxStartups）→ paramiko banner 超时。
        为避免该问题：距上次探活 < ssh_interval 时跳过本轮(Skip，不更新状态，保留上次结果)。
        真正的 SSH 探活失败时降级为 TCP 22 端口连通判定，避免把可达机误判成 offline。
        """
        now = datetime.now()
        last = getattr(asset_inst, "last_checked_at", None)
        if last:
            try:
                if (now - last).total_seconds() < ssh_interval:
                    return None  # 低频窗口内跳过本轮
            except Exception:
                pass
        result = ConnectionTester.test("ssh", asset_inst.ip or "", config)
        if result.get("ok"):
            return result
        # SSH 失败 → 降级 TCP：优先业务端口，否则 22
        tcp_port = config.get("ssh_port", 22)
        return _probe_middleware_port(asset_inst.ip or "", tcp_port, timeout=4)

    def _probe_one(asset):
        if not asset.ip:
            return None
        sess = _probe_db_factory()
        try:
            a = sess.query(Asset).filter(Asset.id == asset.id).first()
            if not a:
                return None
            config = {}
            try:
                raw = a.connection_config
                if isinstance(raw, str):
                    config = json.loads(raw) if raw else {}
                else:
                    config = raw or {}
            except (json.JSONDecodeError, TypeError):
                config = {}

            ci_attrs = {}
            try:
                raw_attrs = a.ci_attributes
                if isinstance(raw_attrs, str):
                    ci_attrs = json.loads(raw_attrs) if raw_attrs else {}
                else:
                    ci_attrs = raw_attrs or {}
            except (json.JSONDecodeError, TypeError):
                ci_attrs = {}

            # 按 CI 类型选择探活方式：有业务端口的探业务端口，否则按 connection_type
            # 演示资产(demo=true)跳过探活，保持在线，避免假 IP 被探活打成 offline
            if ci_attrs.get("demo"):
                return None

            probe_type = (a.probe_type or "tcp").lower()
            probe_port = None
            if a.ci_type == "middleware":
                probe_port = ci_attrs.get("mw_port", "")
            elif a.ci_type == "database":
                probe_port = ci_attrs.get("db_port", "")

            # 按探活方式分发：tcp(默认)/ping/ssh（CONTRACT.md）。ssh 走低频+失败降级 TCP，避免触发 sshd 半开队列
            if probe_type == "ping":
                result = _probe_ping(a.ip)
            elif probe_type == "ssh":
                result = _probe_ssh_lowfreq(sess, a, config)
            elif probe_port:
                result = _probe_middleware_port(a.ip, probe_port)
            else:
                result = ConnectionTester.test(a.connection_type or "ssh", a.ip, config)

            old_status = a.status
            if result is None:
                return None  # ssh 低频窗口内跳过本轮，不更新状态
            new_status = "online" if result.get("ok") else "offline"
            a.status = new_status
            a.last_checked_at = datetime.now()
            a.latency_ms = int(result.get("latency_ms", 0)) if result.get("ok") else None

# 每次探测都写入 svc_up 指标（不限于状态变化），确保告警系统总能拿到最新值；
# 与资产状态合并为一次 commit，减少上千台时 DB 往返压力。
            try:
                from app.models import MetricRecord, AssetLifecycle
                lifecycle = sess.query(AssetLifecycle).filter(
                    AssetLifecycle.asset_id == a.id,
                    AssetLifecycle.status.in_(["maintenance", "decommissioned", "retired"])
                ).first()
                if not (lifecycle and new_status == "offline"):
                    svc_up = 1.0 if new_status == "online" else 0.0
                    sess.add(MetricRecord(
                        asset_id=a.id, name="svc_up", value=svc_up,
                        unit="", timestamp=datetime.now()
                    ))
                sess.commit()
            except Exception:
                sess.rollback()

            if old_status != new_status:
                return {"id": a.id, "name": a.name,
                        "old": old_status, "new": new_status,
                        "message": result.get("message", "")}
            return None
        except Exception as e:
            sess.rollback()
            from app.logger import logger
            logger.warning(f"probe {asset.name}({asset.ip}) 探测异常: {e}")
            return None
        finally:
            sess.close()

    _PROBE_WORKERS = int(os.environ.get("AIOPS_PROBE_WORKERS", "50"))
    with ThreadPoolExecutor(max_workers=_PROBE_WORKERS) as executor:
        futures = {executor.submit(_probe_one, a): a for a in assets}
        for future in as_completed(futures):
            c = future.result()
            if c:
                changed.append(c)
                with _lock:
                    logger.info(f"probe {c['name']}({futures[future].ip}): {c['old']} -> {c['new']} ({c['message']})")

    return changed
