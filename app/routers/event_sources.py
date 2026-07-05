import json
import requests
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import ExtEventSource, Alert
from app.template_utils import get_templates, parse_json_config

router = APIRouter(prefix="/event-sources", tags=["event-sources"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def event_sources_page(request: Request, db: Session = Depends(get_db)):
    sources = db.query(ExtEventSource).all()
    return templates.TemplateResponse("event_sources.html", {
        "request": request, "sources": sources,
    })


@router.post("/create")
def create_source(
    request: Request, name: str = Form(...), source_type: str = Form("zabbix"),
    api_url: str = Form(...), auth_json: str = Form("{}"),
    sync_interval: int = Form(60), db: Session = Depends(get_db),
):
    src = ExtEventSource(name=name, source_type=source_type, api_url=api_url,
                          auth_config=auth_json, sync_interval=sync_interval)
    db.add(src)
    db.commit()
    return RedirectResponse("/event-sources", status_code=303)


@router.post("/toggle/{src_id}")
def toggle_source(src_id: int, db: Session = Depends(get_db)):
    src = db.query(ExtEventSource).filter(ExtEventSource.id == src_id).first()
    if src:
        src.enabled = not src.enabled
        db.commit()
    return RedirectResponse("/event-sources", status_code=303)


@router.post("/sync/{src_id}")
def sync_source(src_id: int, db: Session = Depends(get_db)):
    src = db.query(ExtEventSource).filter(ExtEventSource.id == src_id).first()
    if not src:
        return PlainTextResponse("Source not found", 404)
    try:
        auth = parse_json_config(src.auth_config)
        headers = {}
        token = auth.get("token") or auth.get("password", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        count = 0
        if src.source_type == "zabbix":
            user = auth.get("user", "Admin")
            pw = auth.get("password", "zabbix")
            login = requests.post(
                f"{src.api_url}/api_jsonrpc.php",
                json={"jsonrpc": "2.0", "method": "user.login",
                       "params": {"user": user, "password": pw}, "id": 1},
                timeout=30
            )
            auth_token = login.json().get("result")
            if auth_token:
                resp = requests.post(
                    f"{src.api_url}/api_jsonrpc.php",
                    json={"jsonrpc": "2.0", "method": "trigger.get",
                           "params": {"output": "extend", "filter": {"value": 1},
                                      "selectHosts": "extend", "sortfield": "lastchange",
                                      "sortorder": "DESC", "limit": 50},
                           "id": 2, "auth": auth_token},
                    timeout=30
                )
                triggers = resp.json().get("result", [])
                for t in triggers:
                    hosts = t.get("hosts", [{}])
                    host_name = hosts[0].get("host", "unknown") if hosts else "unknown"
                    existing = db.query(Alert).filter(
                        Alert.name == f"Zabbix-{t.get('triggerid', '')}"
                    ).first()
                    if not existing:
                        db.add(Alert(
                            name=f"Zabbix-{t.get('triggerid', '')}",
                            metric=t.get("description", "zabbix"),
                            message=f"Zabbix: {t.get('description', '')} (host: {host_name}, priority: {t.get('priority', '')})",
                            severity="critical" if int(t.get("priority", 0)) >= 4 else "warning",
                            source="zabbix",
                            status="firing",
                        ))
                        count += 1
        else:
            resp = requests.get(src.api_url, headers=headers, timeout=30)
            if resp.ok:
                events = resp.json() if isinstance(resp.json(), list) else [resp.json()]
                for ev in events:
                    name = ev.get("name") or ev.get("title") or ev.get("id", "event")
                    existing = db.query(Alert).filter(Alert.name == f"Ext-{name}").first()
                    if not existing:
                        db.add(Alert(
                            name=f"Ext-{name}",
                            metric=ev.get("type", "event"),
                            message=ev.get("message") or ev.get("description", ""),
                            severity=ev.get("severity", "warning"),
                            source=src.source_type,
                            status="firing",
                        ))
                        count += 1
        db.commit()
        src.last_sync = datetime.now()
        db.commit()
        return PlainTextResponse(f"Synced {count} new alerts", 200)
    except Exception as e:
        return PlainTextResponse(f"Sync error: {e}", 500)
