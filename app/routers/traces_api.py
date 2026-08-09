import json
import re
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from app.database import get_db
from app.models import Span, Asset
from app.services.health_engine import _extract_domains, _normalize_service_name

router = APIRouter(prefix="/api/traces", tags=["api_traces"])


@router.get("/asset-domains")
def asset_domains(db: Session = Depends(get_db)):
    """返回资产 id → 业务域列表映射(供指标监控/日志页按业务域筛资产)"""
    mapping = {}
    for asset in db.query(Asset).all():
        mapping[asset.id] = _extract_domains(asset)
    return mapping


def _domain_tokens(domain: str) -> list:
    """提取业务域名中的 ASCII 字母数字 token(如 'K8s微商城' → ['k8s'])"""
    return [t.lower() for t in re.findall(r"[a-zA-Z0-9]+", domain or "")]


def _span_service_names(db: Session) -> list:
    return [r[0] for r in db.query(Span.service_name).distinct().order_by(Span.service_name).all() if r[0]]


def _services_by_domain(domain: str, db: Session) -> list:
    """根据业务域查询关联的 span service_name 列表"""
    all_services = _span_service_names(db)
    matched = set()
    for asset in db.query(Asset).all():
        domains = _extract_domains(asset)
        if domain in domains:
            for s in all_services:
                normalized = _normalize_service_name(asset.name)
                if normalized and normalized in s.lower():
                    matched.add(s)
            try:
                attrs = json.loads(asset.ci_attributes or "{}")
                raw = attrs.get("service_names") or attrs.get("service_name") or ""
                if isinstance(raw, str):
                    for svc in [s.strip() for s in raw.split(",") if s.strip()]:
                        matched.add(svc)
                elif isinstance(raw, list):
                    for svc in raw:
                        matched.add(str(svc).strip())
            except (json.JSONDecodeError, TypeError):
                pass
    tokens = _domain_tokens(domain)
    if tokens:
        for s in all_services:
            sl = s.lower()
            if any(t in sl for t in tokens):
                matched.add(s)
    return sorted(matched)


@router.get("/domains")
def list_trace_domains(db: Session = Depends(get_db)):
    """获取有链路数据的业务域列表"""
    all_services = _span_service_names(db)
    domain_set = set()
    for asset in db.query(Asset).all():
        domains = _extract_domains(asset)
        for s in all_services:
            normalized = _normalize_service_name(asset.name)
            if normalized and normalized in s.lower():
                domain_set.update(domains)
                break
        try:
            attrs = json.loads(asset.ci_attributes or "{}")
            raw = attrs.get("service_names") or attrs.get("service_name") or ""
            svcs = []
            if isinstance(raw, str):
                svcs = [s.strip() for s in raw.split(",") if s.strip()]
            elif isinstance(raw, list):
                svcs = [str(s).strip() for s in raw]
            for sn in svcs:
                if sn in all_services:
                    domain_set.update(domains)
                    break
        except (json.JSONDecodeError, TypeError):
            pass
    # 兜底: 服务名包含某域 ASCII token 的域也加入
    for s in all_services:
        sl = s.lower()
        for asset in db.query(Asset).all():
            for d in _extract_domains(asset):
                tokens = _domain_tokens(d)
                if tokens and any(t in sl for t in tokens):
                    domain_set.add(d)
    return sorted(domain_set)


@router.get("/services")
def list_trace_services(domain: str = Query(""), db: Session = Depends(get_db)):
    """获取服务列表，可选按业务域过滤"""
    if domain:
        services = _services_by_domain(domain, db)
        if not services:
            services = [r[0] for r in db.query(Span.service_name).distinct().order_by(Span.service_name).all() if r[0]]
        return services
    services = [r[0] for r in db.query(Span.service_name).distinct().order_by(Span.service_name).all() if r[0]]
    return services


@router.get("")
def list_traces(
    service: str = Query(""), operation: str = Query(""),
    keyword: str = Query(""), status: str = Query(""),
    min_dur: float = Query(0), max_dur: float = Query(0),
    limit: int = Query(50), offset: int = Query(0),
    domain: str = Query(""),
    db: Session = Depends(get_db)):
    """查询调用链列表"""
    subq = db.query(
        Span.trace_id,
        func.count(Span.id).label("span_count"),
        func.sum(Span.duration_ms).label("total_dur"),
        func.min(Span.started_at).label("root_time"),
        func.max(Span.status).label("worst_status")).group_by(Span.trace_id)

    domain_services = None
    if domain:
        domain_services = _services_by_domain(domain, db)
        if domain_services:
            subq = subq.having(Span.service_name.in_(domain_services))

    if service:
        subq = subq.having(Span.service_name == service)
    if min_dur > 0:
        subq = subq.having(func.avg(Span.duration_ms) >= min_dur)
    if max_dur > 0:
        subq = subq.having(func.avg(Span.duration_ms) <= max_dur)
    if status:
        subq = subq.having(Span.status == status)
    if keyword:
        subq = subq.having(
            Span.service_name.ilike(f"%{keyword}%")
            | Span.operation_name.ilike(f"%{keyword}%")
            | Span.trace_id.ilike(f"%{keyword}%")
        )

    subq = subq.order_by(desc(func.min(Span.started_at))).limit(limit).offset(offset)
    rows = subq.all()

    # 获取服务列表
    if domain_services:
        services = domain_services
    else:
        services = [r[0] for r in db.query(Span.service_name).distinct().order_by(Span.service_name).all() if r[0]]

    results = []
    for r in rows:
        root = db.query(Span).filter(
            Span.trace_id == r.trace_id,
            Span.parent_span_id == ""
        ).first()
        if not root:
            root = db.query(Span).filter(Span.trace_id == r.trace_id).order_by(Span.started_at).first()

        results.append({
            "trace_id": r.trace_id,
            "span_count": r.span_count,
            "total_duration_ms": round(r.total_dur or 0, 1),
            "root_service": root.service_name if root else "",
            "root_operation": root.operation_name if root else "",
            "started_at": r.root_time.strftime("%Y-%m-%d %H:%M:%S") if r.root_time else "",
            "worst_status": r.worst_status or "OK",
        })

    total = db.query(Span.trace_id).distinct().count()
    return JSONResponse({"traces": results, "services": services, "total": total})


@router.get("/{trace_id}")
def get_trace(trace_id: str, db: Session = Depends(get_db)):
    """获取单个调用链的完整 Span 详情"""
    spans = db.query(Span).filter(Span.trace_id == trace_id).order_by(Span.started_at).all()
    if not spans:
        return JSONResponse({"spans": []})

    root_span = None
    for s in spans:
        if not s.parent_span_id:
            root_span = s
            break
    if not root_span:
        root_span = spans[0]

    root_start = root_span.started_at
    root_end = root_span.ended_at
    root_dur = (root_end - root_start).total_seconds() * 1000 if root_end and root_start else 0
    if root_dur <= 0:
        root_dur = 1

    span_list = []
    for s in spans:
        tags = s.tags
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = {}
        span_list.append({
            "span_id": s.span_id,
            "parent_span_id": s.parent_span_id or "",
            "service_name": s.service_name,
            "operation_name": s.operation_name,
            "started_at": s.started_at.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if s.started_at else "",
            "duration_ms": s.duration_ms,
            "status": s.status,
            "tags": tags,
        })

    services = list(set(s["service_name"] for s in span_list if s["service_name"]))

    # 构建拓扑边
    edges = []
    span_id_to_service = {s["span_id"]: s["service_name"] for s in span_list}
    for s in span_list:
        if s["parent_span_id"]:
            parent_svc = span_id_to_service.get(s["parent_span_id"])
            if parent_svc and parent_svc != s["service_name"]:
                edge_key = f"{parent_svc}->{s['service_name']}"
                if edge_key not in [f"{e['source']}->{e['target']}" for e in edges]:
                    edges.append({"source": parent_svc, "target": s["service_name"]})

    return JSONResponse({
        "trace_id": trace_id,
        "total_spans": len(spans),
        "root_duration_ms": round(root_dur, 1),
        "root_start": root_start.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if root_start else "",
        "services": services,
        "spans": span_list,
        "topology": {"services": services, "edges": edges},
    })
