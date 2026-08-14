"""网络设备管理服务(F6) - CRUD + SNMP 校验/接口轮询/邻居发现/主机链路映射。

契约见 CONTRACT.md 第二十一章。SNMP 走 app/services/snmp_client.py(纯 Python + mock 模式)。
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import Asset, NetworkDevice, NetworkInterface, NetworkNeighbor
from app.services import snmp_client

DEVICE_TYPES = ["switch", "router", "firewall", "ap", "other"]


def _device_dict(d: NetworkDevice) -> Dict[str, Any]:
    return {
        "id": d.id,
        "asset_id": d.asset_id,
        "name": d.name,
        "ip": d.ip,
        "device_type": d.device_type,
        "vendor": d.vendor,
        "model": d.model,
        "snmp_version": d.snmp_version,
        "community": d.community,
        "port": d.port,
        "status": d.status,
        "last_poll_at": d.last_poll_at.isoformat() if d.last_poll_at else None,
        "created_at": d.created_at.isoformat() if d.created_at else "",
    }


def _iface_dict(i: NetworkInterface) -> Dict[str, Any]:
    return {
        "id": i.id,
        "if_index": i.if_index,
        "name": i.name,
        "type": i.type,
        "mac": i.mac,
        "admin_status": i.admin_status,
        "oper_status": i.oper_status,
        "up": i.oper_status == 1,
        "speed": i.speed,
        "in_octets": i.in_octets,
        "out_octets": i.out_octets,
        "in_errors": i.in_errors,
        "out_errors": i.out_errors,
        "last_poll_at": i.last_poll_at.isoformat() if i.last_poll_at else None,
    }


def _neighbor_dict(n: NetworkNeighbor) -> Dict[str, Any]:
    return {
        "id": n.id,
        "local_interface": n.local_interface,
        "neighbor_device": n.neighbor_device,
        "neighbor_port": n.neighbor_port,
        "proto": n.proto,
        "last_seen_at": n.last_seen_at.isoformat() if n.last_seen_at else "",
    }


# ─── CRUD ────────────────────────────────────────────────────────
def list_devices(db: Session, keyword: Optional[str] = None) -> List[Dict[str, Any]]:
    q = db.query(NetworkDevice).order_by(NetworkDevice.ip)
    if keyword:
        k = f"%{keyword}%"
        q = q.filter(NetworkDevice.name.like(k) | NetworkDevice.ip.like(k))
    return [_device_dict(d) for d in q.all()]


def get_device(db: Session, device_id: int) -> Optional[NetworkDevice]:
    return db.query(NetworkDevice).filter(NetworkDevice.id == device_id).first()


def create_device(db: Session, data: Dict[str, Any], created_by: Optional[int] = None) -> NetworkDevice:
    name = str(data.get("name") or "").strip()
    ip = str(data.get("ip") or "").strip()
    if not name or not ip:
        raise ValueError("name 和 ip 不能为空")
    d = NetworkDevice(
        asset_id=data.get("asset_id"),
        name=name,
        ip=ip,
        device_type=str(data.get("device_type") or "switch"),
        vendor=str(data.get("vendor") or ""),
        model=str(data.get("model") or ""),
        snmp_version=str(data.get("snmp_version") or "v2c"),
        community=str(data.get("community") or "public"),
        port=int(data.get("port") or 161),
        status="unreachable",
        created_by=created_by,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def update_device(db: Session, device_id: int, data: Dict[str, Any]) -> NetworkDevice:
    d = get_device(db, device_id)
    if not d:
        raise ValueError("设备不存在")
    for field in ("name", "ip", "device_type", "vendor", "model", "snmp_version", "community", "status"):
        if field in data and data[field] is not None:
            setattr(d, field, str(data[field]))
    if "port" in data and data["port"]:
        d.port = int(data["port"])
    if "asset_id" in data:
        d.asset_id = data["asset_id"]
    d.updated_at = datetime.now()
    db.commit()
    db.refresh(d)
    return d


def delete_device(db: Session, device_id: int) -> None:
    d = get_device(db, device_id)
    if not d:
        raise ValueError("设备不存在")
    db.query(NetworkInterface).filter(NetworkInterface.device_id == device_id).delete()
    db.query(NetworkNeighbor).filter(NetworkNeighbor.device_id == device_id).delete()
    db.delete(d)
    db.commit()


# ─── SNMP 动作 ───────────────────────────────────────────────────
def _backend(device: NetworkDevice):
    if snmp_client.mock_enabled():
        return snmp_client.MockSnmp(device.ip)
    return snmp_client.SnmpSession(device.ip, device.community, device.port, device.snmp_version)


def _real_or_mock(device: NetworkDevice, action, *args):
    """尝试真实 SNMP, 失败时若 mock 开启则回退 mock, 否则抛错。"""
    if snmp_client.mock_enabled():
        return getattr(snmp_client.MockSnmp(device.ip), action)(*args)
    try:
        return getattr(snmp_client, action)(device.ip, device.community, device.port, device.snmp_version, *args)
    except snmp_client.SnmpError:
        if snmp_client.mock_enabled():
            return getattr(snmp_client.MockSnmp(device.ip), action)(*args)
        raise


def validate_device(db: Session, device_id: int) -> Dict[str, Any]:
    d = get_device(db, device_id)
    if not d:
        raise ValueError("设备不存在")
    try:
        info = _real_or_mock(d, "validate")
    except snmp_client.SnmpError as e:
        d.status = "error"
        db.commit()
        return {"ok": False, "error": str(e), "status": "error"}
    d.status = "ok"
    d.vendor = _infer_vendor(info.get("sys_object_id", ""))
    d.model = _infer_model(info.get("sys_descr", ""))
    d.last_poll_at = datetime.now()
    db.commit()
    return {"ok": True, "status": "ok", **info}


def _infer_vendor(object_id: str) -> str:
    oid = str(object_id)
    if "9.1." in oid or "cisco" in oid.lower():
        return "Cisco"
    if "2011" in oid or "huawei" in oid.lower():
        return "Huawei"
    if "2636" in oid or "juniper" in oid.lower():
        return "Juniper"
    if "25506" in oid or "h3c" in oid.lower():
        return "H3C"
    return "Unknown"


def _infer_model(descr: str) -> str:
    words = (descr or "").split()
    return " ".join(words[:3]) if words else ""


def poll_device(db: Session, device_id: int) -> Dict[str, Any]:
    d = get_device(db, device_id)
    if not d:
        raise ValueError("设备不存在")
    try:
        interfaces = _real_or_mock(d, "poll_interfaces")
        d.status = "ok"
    except snmp_client.SnmpError as e:
        d.status = "error"
        db.commit()
        return {"ok": False, "error": str(e), "interfaces": []}
    db.query(NetworkInterface).filter(NetworkInterface.device_id == device_id).delete()
    for i in interfaces:
        db.add(NetworkInterface(
            device_id=device_id,
            if_index=i["if_index"],
            name=i["name"],
            type=i["type"],
            mac=i["mac"],
            admin_status=i["admin_status"],
            oper_status=i["oper_status"],
            speed=i["speed"],
            in_octets=float(i["in_octets"]),
            out_octets=float(i["out_octets"]),
            in_errors=float(i["in_errors"]),
            out_errors=float(i["out_errors"]),
            last_poll_at=datetime.now(),
        ))
    d.last_poll_at = datetime.now()
    db.commit()
    stored = db.query(NetworkInterface).filter(NetworkInterface.device_id == device_id).all()
    up = sum(1 for x in stored if x.oper_status == 1)
    return {"ok": True, "status": "ok", "total_ifaces": len(stored), "up_ifaces": up,
            "interfaces": [_iface_dict(x) for x in stored]}


def discover_device(db: Session, device_id: int) -> Dict[str, Any]:
    d = get_device(db, device_id)
    if not d:
        raise ValueError("设备不存在")
    try:
        neighbors = _real_or_mock(d, "discover_neighbors")
        d.status = "ok"
    except snmp_client.SnmpError as e:
        d.status = "error"
        db.commit()
        return {"ok": False, "error": str(e), "neighbors": []}
    db.query(NetworkNeighbor).filter(NetworkNeighbor.device_id == device_id).delete()
    for n in neighbors:
        db.add(NetworkNeighbor(
            device_id=device_id,
            local_interface=n["local_interface"],
            neighbor_device=n["neighbor_device"],
            neighbor_port=n["neighbor_port"],
            proto=n.get("proto", "lldp"),
            last_seen_at=datetime.now(),
        ))
    d.last_poll_at = datetime.now()
    db.commit()
    stored = db.query(NetworkNeighbor).filter(NetworkNeighbor.device_id == device_id).all()
    return {"ok": True, "neighbors": [_neighbor_dict(x) for x in stored],
            "total": len(stored)}


def device_detail(db: Session, device_id: int) -> Dict[str, Any]:
    d = get_device(db, device_id)
    if not d:
        raise ValueError("设备不存在")
    ifaces = db.query(NetworkInterface).filter(NetworkInterface.device_id == device_id).order_by(
        NetworkInterface.if_index).all()
    neighbors = db.query(NetworkNeighbor).filter(NetworkNeighbor.device_id == device_id).all()
    return {**_device_dict(d),
            "interfaces": [_iface_dict(i) for i in ifaces],
            "neighbors": [_neighbor_dict(n) for n in neighbors],
            "up_ifaces": sum(1 for i in ifaces if i.oper_status == 1)}


def map_host_links(db: Session, host_ip: str) -> Dict[str, Any]:
    """主机 → 交换机端口映射: 用 host 的 MAC(asset) 匹配其它设备的接口 MAC。"""
    asset = db.query(Asset).filter(Asset.ip == host_ip).first() if host_ip else None
    links = []
    devices = db.query(NetworkDevice).all()
    host_mac = ""
    if asset and asset.mac:
        host_mac = asset.mac.lower().replace("-", ":")
    for dev in devices:
        for i in db.query(NetworkInterface).filter(NetworkInterface.device_id == dev.id).all():
            imac = (i.mac or "").lower()
            linked = False
            if host_mac and imac and host_mac in imac:
                linked = True
            if linked:
                links.append({
                    "host_ip": host_ip,
                    "host_name": asset.name if asset else host_ip,
                    "switch": dev.name,
                    "switch_ip": dev.ip,
                    "port": i.name,
                    "port_mac": i.mac,
                    "status": "up" if i.oper_status == 1 else "down",
                })
    return {"host_ip": host_ip, "host_mac": host_mac or "未采集", "links": links,
            "total": len(links)}
