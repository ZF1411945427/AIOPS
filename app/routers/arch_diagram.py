"""架构图自动生成路由 (ArchDiagram): 按业务域生成 draw.io 架构图。"""

from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Dict, Optional

from app.database import get_session_for, get_db_mode
from app.models import AssetRelation
from app.services import drawio_generator as dg
from app.services.drawio_ai_planner import ai_layout_plan, apply_ai_scores

router = APIRouter(prefix="/api/arch-diagram", tags=["ArchDiagram"])


class GenerateRequest(BaseModel):
    domain: str
    drawio_path: Optional[str] = None
    format: Optional[str] = "drawio"  # drawio / png / svg / pdf
    ai_layout: bool = True  # 是否启用 AI 智能布局
    live_draw: bool = False  # 是否通过 CDP 实时绘制到 draw.io 桌面版


def _load(domain: str):
    db = get_session_for(get_db_mode())()
    assets = dg.collect_domain_assets(db, domain)
    relations = db.query(AssetRelation).all()
    return db, assets, relations


@router.get("/meta")
def meta(domain: str = Query(..., description="业务域")):
    db, assets, relations = _load(domain)
    if not assets:
        return {"ok": False, "message": f"业务域 '{domain}' 下没有资产", "domain": domain}
    m = dg.render_meta(domain, assets, relations)
    m["ok"] = True
    m["message"] = f"共 {len(assets)} 个资产, {len(relations)} 条关系"
    return m


@router.get("/list")
def list_generated():
    d = dg.ensure_export_dir()
    files = []
    if d.exists():
        for f in sorted(d.iterdir(), key=lambda x: x.name):
            files.append({"name": f.name, "size": f.stat().st_size if f.is_file() else 0})
    return {"ok": True, "dir": str(d), "files": files}


@router.post("/generate")
def generate(req: GenerateRequest):
    domain = (req.domain or "").strip()
    if not domain:
        return {"ok": False, "message": "缺少业务域", "error": "domain required"}

    db, assets, relations = _load(domain)
    if not assets:
        return {"ok": False, "message": f"业务域 '{domain}' 下没有资产", "error": "no assets"}

    # 实时绘制模式: 通过 draw.io MCP server 生成并打开 draw.io 桌面版
    if req.live_draw and req.drawio_path:
        from app.services.drawio_live_drawer import generate_and_open
        result = generate_and_open(req.drawio_path, domain, db)
        db.close()
        return result

    # 原有的文件生成模式
    ai_scores: Optional[Dict[str, float]] = None
    ai_result = None
    if req.ai_layout:
        db2 = get_session_for(get_db_mode())()
        try:
            ai_result = ai_layout_plan(domain, assets, relations)
            if ai_result.get("ok"):
                ai_scores = apply_ai_scores(assets, ai_result.get("node_order", {}))
        finally:
            db2.close()

    # 1) 生成 .drawio XML 并落盘
    xml = dg.build_drawio_xml(domain, assets, relations,
                              diagram_title=f"{domain} - 系统架构图",
                              ai_scores=ai_scores)
    safe = "".join(c if c.isalnum() or c in "_-." else "_" for c in domain) or "domain"
    drawio_file = dg.write_drawio_file(xml, f"arch-{safe}.drawio")

    result = {
        "ok": True,
        "message": f"已生成架构图: {len(assets)} 个资产, {len(relations)} 条关系",
        "domain": domain,
        "asset_count": len(assets),
        "relation_count": len(relations),
        "drawio_file": str(drawio_file),
        "drawio_download": f"/api/arch-diagram/file/{drawio_file.name}",
    }

    if ai_result:
        result["ai_analysis"] = ai_result.get("analysis", "")
        result["ai_suggestions"] = ai_result.get("suggestions", "")
        result["ai_ok"] = ai_result.get("ok", False)
        if not ai_result.get("ok"):
            result["ai_error"] = ai_result.get("error", "AI 布局分析失败，已使用默认布局")

    # 2) 若提供了 drawio 路径且 format != drawio, 调用本地 drawio 无头导出
    fmt = (req.format or "drawio").lower()
    if fmt != "drawio" and req.drawio_path:
        ok, msg, out_f = dg.export_via_drawio(req.drawio_path, drawio_file, fmt)
        result["export_ok"] = ok
        result["export_message"] = msg
        if ok and out_f:
            result["export_file"] = str(out_f)
            result["export_download"] = f"/api/arch-diagram/file/{out_f.name}"
    elif fmt != "drawio":
        result["export_ok"] = False
        result["export_message"] = "未提供 draw.io 本地路径, 仅生成 .drawio 文件"

    return result


@router.get("/file/{filename}")
def download_file(filename: str):
    """下载已生成的架构图文件(.drawio / png / svg ...)。"""
    from fastapi.responses import FileResponse
    d = dg.ensure_export_dir()
    # 防目录穿越
    safe_name = filename.replace("/", "").replace("\\", "")
    p = d / safe_name
    if not p.exists() or not p.is_file():
        return {"ok": False, "error": "file not found"}
    media = {
        ".drawio": "application/xml",
        ".png": "image/png",
        ".svg": "image/svg+xml",
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    ext = p.suffix.lower()
    return FileResponse(str(p), media_type=media.get(ext, "application/octet-stream"),
                        filename=p.name)
