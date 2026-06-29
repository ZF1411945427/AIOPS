from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from app.database import get_db
from app.models import NetFlowRecord, NetFlowCollector
from app.template_utils import get_templates

router = APIRouter(prefix="/netflow", tags=["netflow"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def netflow_page(request: Request, db: Session = Depends(get_db)):
    collectors = db.query(NetFlowCollector).all()
    protocols = [r[0] for r in db.query(NetFlowRecord.protocol).distinct().all()]
    top_src = (
        db.query(NetFlowRecord.src_ip, NetFlowRecord.protocol,
                 func.sum(NetFlowRecord.bytes_sent + NetFlowRecord.bytes_rcvd).label("total"))
        .group_by(NetFlowRecord.src_ip, NetFlowRecord.protocol)
        .order_by(desc("total")).limit(20).all()
    )
    return templates.TemplateResponse("netflow.html", {
        "request": request, "collectors": collectors, "protocols": protocols,
        "top_src": top_src, "records": None,
    })


@router.post("/collectors/create")
def create_collector(
    request: Request, name: str = Form(...), collector_type: str = Form("sflow"),
    listen_host: str = Form("0.0.0.0"), listen_port: int = Form(6343),
    db: Session = Depends(get_db),
):
    c = NetFlowCollector(name=name, collector_type=collector_type,
                          listen_host=listen_host, listen_port=listen_port)
    db.add(c)
    db.commit()
    return RedirectResponse("/netflow", status_code=303)


@router.post("/collectors/toggle/{cid}")
def toggle_collector(cid: int, db: Session = Depends(get_db)):
    c = db.query(NetFlowCollector).filter(NetFlowCollector.id == cid).first()
    if c:
        c.enabled = not c.enabled
        db.commit()
    return RedirectResponse("/netflow", status_code=303)


@router.post("/ingest")
def ingest_flow(
    src_ip: str = Form(...), dst_ip: str = Form(...),
    src_port: int = Form(0), dst_port: int = Form(0),
    protocol: str = Form("TCP"), bytes_sent: int = Form(0),
    bytes_rcvd: int = Form(0),
    db: Session = Depends(get_db),
):
    r = NetFlowRecord(
        src_ip=src_ip, dst_ip=dst_ip, src_port=src_port, dst_port=dst_port,
        protocol=protocol, bytes_sent=bytes_sent, bytes_rcvd=bytes_rcvd,
        start_time=datetime.now(), end_time=datetime.now(),
    )
    db.add(r)
    db.commit()
    return {"ok": True}


@router.post("/query", response_class=HTMLResponse)
def query_flow(
    request: Request, protocol: str = Form(""), src_ip: str = Form(""),
    dst_ip: str = Form(""), hours: int = Form(6), limit: int = Form(100),
    db: Session = Depends(get_db),
):
    since = datetime.now() - timedelta(hours=hours)
    q = db.query(NetFlowRecord).filter(NetFlowRecord.created_at >= since)
    if protocol:
        q = q.filter(NetFlowRecord.protocol == protocol)
    if src_ip:
        q = q.filter(NetFlowRecord.src_ip.like(f"%{src_ip}%"))
    if dst_ip:
        q = q.filter(NetFlowRecord.dst_ip.like(f"%{dst_ip}%"))
    records = q.order_by(desc(NetFlowRecord.created_at)).limit(limit).all()
    collectors = db.query(NetFlowCollector).all()
    protocols = [r[0] for r in db.query(NetFlowRecord.protocol).distinct().all()]
    top_src = (
        db.query(NetFlowRecord.src_ip, NetFlowRecord.protocol,
                 func.sum(NetFlowRecord.bytes_sent + NetFlowRecord.bytes_rcvd).label("total"))
        .group_by(NetFlowRecord.src_ip, NetFlowRecord.protocol)
        .order_by(desc("total")).limit(20).all()
    )
    return templates.TemplateResponse("netflow.html", {
        "request": request, "collectors": collectors, "protocols": protocols,
        "top_src": top_src, "records": records,
    })
