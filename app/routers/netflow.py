from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, Form
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from app.database import get_db
from app.models import NetFlowRecord, NetFlowCollector
from app.template_utils import get_templates

router = APIRouter(prefix="/netflow", tags=["netflow"])
templates = get_templates()


@router.post("/ingest")
def ingest_flow(
    src_ip: str = Form(...), dst_ip: str = Form(...),
    src_port: int = Form(0), dst_port: int = Form(0),
    protocol: str = Form("TCP"), bytes_sent: int = Form(0),
    bytes_rcvd: int = Form(0),
    db: Session = Depends(get_db)):
    r = NetFlowRecord(
        src_ip=src_ip, dst_ip=dst_ip, src_port=src_port, dst_port=dst_port,
        protocol=protocol, bytes_sent=bytes_sent, bytes_rcvd=bytes_rcvd,
        started_at=datetime.now(), ended_at=datetime.now())
    db.add(r)
    db.commit()
    return {"ok": True}


