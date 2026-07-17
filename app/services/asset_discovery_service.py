import json
import socket
import concurrent.futures
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import DiscoverySchedule, DiscoveryResult


def create_schedule(db: Session, data: dict) -> int:
    sch = DiscoverySchedule(**data)
    db.add(sch)
    db.commit()
    db.refresh(sch)
    return sch.id


def list_schedules(db: Session, enabled: bool = None) -> list:
    q = db.query(DiscoverySchedule)
    if enabled is not None:
        q = q.filter(DiscoverySchedule.enabled == enabled)
    return q.order_by(DiscoverySchedule.created_at.desc()).all()


def update_schedule(schedule_id: int, data: dict, db: Session):
    sch = db.query(DiscoverySchedule).filter(DiscoverySchedule.id == schedule_id).first()
    if not sch:
        return None
    for k, v in data.items():
        setattr(sch, k, v)
    db.commit()
    return sch


def delete_schedule(schedule_id: int, db: Session):
    db.query(DiscoverySchedule).filter(DiscoverySchedule.id == schedule_id).delete()
    db.commit()


def run_discovery(schedule_id: int, db: Session) -> dict:
    schedule = db.query(DiscoverySchedule).filter(DiscoverySchedule.id == schedule_id).first()
    if not schedule:
        return {"ok": False, "error": "Schedule not found"}

    target_range = schedule.target_range
    protocol = schedule.protocol
    port = schedule.port

    hosts = _parse_target_range(target_range)
    results = []

    for ip in hosts:
        try:
            if protocol == "ssh":
                status = _check_ssh(ip, port)
            elif protocol == "tcp":
                status = _check_tcp(ip, port)
            elif protocol == "icmp":
                status = _check_icmp(ip)
            else:
                status = "unknown"

            dr = DiscoveryResult(
                schedule_id=schedule_id,
                ip=ip,
                port=port if port else 0,
                status=status,
                hostname="",
                os_type="",
                services="",
            )
            db.add(dr)
            results.append({"ip": ip, "status": status})
        except Exception as e:
            results.append({"ip": ip, "status": f"error: {e}"})

    db.commit()
    return {"ok": True, "schedule_id": schedule_id, "scanned": len(hosts), "results": results}


def _parse_target_range(target_range: str) -> list:
    hosts = []
    if not target_range:
        return hosts

    parts = target_range.split(",")
    for part in parts:
        part = part.strip()
        if "/" in part:
            pass
        elif "-" in part:
            start, end = part.split("-", 1)
            start_ip = start.strip()
            try:
                if "." in start_ip:
                    s1, s2, s3, s4 = start_ip.rsplit(".", 3)
                    for i in range(int(s4), int(end.split(".")[-1]) + 1):
                        hosts.append(f"{s1}.{s2}.{s3}.{i}")
            except:
                hosts.append(start_ip)
        else:
            hosts.append(part)
    return hosts[:256]


def _check_tcp(host: str, port: int, timeout: int = 3) -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return "open" if result == 0 else "closed"
    except Exception as e:
        return f"error:{e}"


def _check_ssh(host: str, port: int = 22, timeout: int = 3) -> str:
    return _check_tcp(host, port, timeout)


def _check_icmp(host: str, timeout: int = 3) -> str:
    try:
        ping = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        ping.settimeout(timeout)
        ping.sendto(b"", (host, 0))
        ping.recvfrom(256)
        ping.close()
        return "reachable"
    except Exception:
        return "unreachable"


def get_discovery_results(db: Session, schedule_id: int = None, page: int = 1, per_page: int = 50):
    q = db.query(DiscoveryResult)
    if schedule_id:
        q = q.filter(DiscoveryResult.schedule_id == schedule_id)
    q = q.order_by(DiscoveryResult.discovered_at.desc())
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return items, total
