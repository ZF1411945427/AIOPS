import shlex
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Alert, AlertRule, Asset, ChangeRequest, Report, MetricRecord, K8sEvent
from app.template_utils import get_templates

router = APIRouter(prefix="/chatops", tags=["chatops"])
templates = get_templates()


@router.get("", response_class=HTMLResponse)
def chatops_page(request: Request):
    return templates.TemplateResponse("chatops.html", {"request": request})


def cmd_alerts(args, db: Session, user_id: int):
    q = db.query(Alert).order_by(Alert.created_at.desc())
    limit = 10
    if args and args[0].isdigit():
        limit = int(args[0])
    alerts = q.limit(limit).all()
    lines = [f"**告警列表 (最近{limit}条):**"]
    for a in alerts:
        lines.append(f"  #{a.id} [{a.severity}] {a.metric_name} = {a.actual_value} ({a.status})")
    return "\n".join(lines) if alerts else "暂无告警"


def cmd_alert(args, db: Session, user_id: int):
    if len(args) < 2:
        return "用法: /alert <ack|resolve> <id>"
    action, aid = args[0], args[1]
    a = db.query(Alert).filter(Alert.id == int(aid)).first()
    if not a:
        return f"告警 #{aid} 不存在"
    if action == "ack":
        a.status = "acknowledged"
    elif action == "resolve":
        a.status = "resolved"
    else:
        return f"未知操作: {action}"
    db.commit()
    return f"告警 #{aid} 已{action}"


def cmd_assets(args, db: Session, user_id: int):
    q = db.query(Asset).order_by(Asset.name)
    limit = 10
    if args and args[0].isdigit():
        limit = int(args[0])
    assets = q.limit(limit).all()
    lines = [f"**资产列表 (最近{limit}条):**"]
    for a in assets:
        lines.append(f"  #{a.id} {a.name} ({a.ci_type}) [{a.status}]")
    return "\n".join(lines) if assets else "暂无资产"


def cmd_change(args, db: Session, user_id: int):
    if args and args[0] == "list":
        changes = db.query(ChangeRequest).order_by(ChangeRequest.created_at.desc()).limit(10).all()
        lines = ["**变更列表:**"]
        for c in changes:
            lines.append(f"  #{c.id} {c.title} [{c.status}]")
        return "\n".join(lines) if changes else "暂无变更"
    if args and args[0].isdigit():
        c = db.query(ChangeRequest).filter(ChangeRequest.id == int(args[0])).first()
        if not c:
            return "变更不存在"
        return f"#{c.id} {c.title} [{c.status}] 类型={c.change_type} 优先级={c.priority} 风险={c.risk_level}"
    return "用法: /change <list|id>"


def cmd_report(args, db: Session, user_id: int):
    today = datetime.now().date()
    alerts_today = db.query(Alert).filter(Alert.created_at >= today).count()
    assets_online = db.query(Asset).filter(Asset.status == "online").count()
    assets_total = db.query(Asset).count()
    return (
        f"**日报 ({today.isoformat()}):**\n"
        f"  - 告警数: {alerts_today}\n"
        f"  - 在线资产: {assets_online}/{assets_total}\n"
        f"  - 资产在线率: {(assets_online/assets_total*100) if assets_total else 0:.1f}%"
    )


def cmd_pods(args, db: Session, user_id: int):
    pods = db.query(Asset).filter(Asset.ci_type == "pod").limit(10).all()
    lines = ["**Pod 列表:**"]
    for p in pods:
        lines.append(f"  {p.name} [{p.status}]")
    return "\n".join(lines) if pods else "暂无 Pod"


COMMANDS = {
    "alerts": cmd_alerts,
    "alert": cmd_alert,
    "assets": cmd_assets,
    "change": cmd_change,
    "report": cmd_report,
    "pods": cmd_pods,
    "help": lambda a, db, uid: (
        "**可用命令:**\n"
        "  /alerts [n]     - 最近 n 条告警\n"
        "  /alert ack <id> - 确认告警\n"
        "  /alert resolve <id> - 解决告警\n"
        "  /assets [n]     - 最近 n 条资产\n"
        "  /change list    - 变更列表\n"
        "  /change <id>    - 变更详情\n"
        "  /report         - 今日报告\n"
        "  /pods           - Pod 列表\n"
        "  /help           - 帮助"
    ),
}


@router.post("/command")
def chatops_command(
    request: Request,
    text: str = Form(...),
    db: Session = Depends(get_db),
):
    user_id = request.session.get("user_id")
    text = text.strip()
    if not text.startswith("/"):
        return JSONResponse({"reply": "命令必须以 / 开头。输入 /help 查看帮助"})
    parts = shlex.split(text[1:])
    cmd = parts[0].lower() if parts else ""
    args = parts[1:] if len(parts) > 1 else []
    handler = COMMANDS.get(cmd)
    if not handler:
        return JSONResponse({"reply": f"未知命令: /{cmd}。输入 /help 查看帮助"})
    try:
        reply = handler(args, db, user_id)
        return JSONResponse({"reply": reply})
    except Exception as e:
        return JSONResponse({"reply": f"执行出错: {e}"})
