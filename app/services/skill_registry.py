import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from sqlalchemy.orm import Session

from app.models import Skill, SkillExecution

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SKILL_DIR = PROJECT_ROOT / "skills"              # 内置技能目录(随仓库分发)
MARKETPLACE_DIR = PROJECT_ROOT / "marketplace"   # 私服市场根目录
PACKAGE_DIR = MARKETPLACE_DIR / "packages"       # 市场包存放目录

_FRONTMATTER_RE = re.compile(r"^---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*\r?\n")
MAX_INPUT_SUMMARY = 500
MAX_OUTPUT_SUMMARY = 2000


def _ensure_dirs():
    SKILL_DIR.mkdir(parents=True, exist_ok=True)
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)


# ─── SKILL.md 解析 ───────────────────────────────────────────────

def parse_frontmatter(md: str) -> (Dict[str, Any], str):
    """解析 SKILL.md: 返回 (frontmatter 元数据 dict, 正文 str)。无 frontmatter 返回 ({}, 全文)。"""
    meta: Dict[str, Any] = {}
    m = _FRONTMATTER_RE.match(md or "")
    if m:
        try:
            parsed = yaml.safe_load(m.group(1)) or {}
            if isinstance(parsed, dict):
                meta = parsed
        except yaml.YAMLError:
            meta = {}
    return meta, (md or "")


def build_skill_md(meta: Dict[str, Any], body: str) -> str:
    """把 frontmatter 与正文拼回标准 SKILL.md 文本。"""
    lines = ["---"]
    for k, v in meta.items():
        if isinstance(v, (list, tuple)):
            lines.append(f"{k}: {json.dumps(list(v), ensure_ascii=False)}")
        elif isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append((body or "").strip())
    return "\n".join(lines)


# ─── 内置技能扫描(F1 loader) ─────────────────────────────────────

def scan_builtin_skills(db: Session) -> int:
    """启动时扫描 skills/**/SKILL.md 增量入库。已有 name 不覆盖。返回新增数。"""
    _ensure_dirs()
    added = 0
    for md_path in sorted(SKILL_DIR.rglob("SKILL.md")):
        try:
            text = md_path.read_text(encoding="utf-8")
        except Exception:
            continue
        meta, body = parse_frontmatter(text)
        name = str(meta.get("name") or "").strip()
        if not name:
            continue
        exists = db.query(Skill).filter(Skill.name == name).first()
        if exists:
            continue
        db.add(Skill(
            name=name,
            description=str(meta.get("description") or "").strip()[:512],
            version=str(meta.get("version") or "1.0.0"),
            author=str(meta.get("author") or ""),
            license=str(meta.get("license") or ""),
            category=str(meta.get("category") or ""),
            risk_level=str(meta.get("risk_level") or "read_only"),
            keywords=json.dumps(meta.get("keywords") or [], ensure_ascii=False),
            tools_required=json.dumps(meta.get("tools_required") or [], ensure_ascii=False),
            content=text,
            source="builtin",
            file_path=str(md_path.relative_to(SKILL_DIR)).replace("\\", "/"),
            enabled=True,
        ))
        added += 1
    db.commit()
    return added


# ─── CRUD ────────────────────────────────────────────────────────

def _to_dict(s: Skill) -> Dict[str, Any]:
    return {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "version": s.version,
        "author": s.author,
        "license": s.license,
        "category": s.category,
        "risk_level": s.risk_level,
        "keywords": _load_json(s.keywords),
        "tools_required": _load_json(s.tools_required),
        "source": s.source,
        "file_path": s.file_path,
        "enabled": bool(s.enabled),
        "usage_count": s.usage_count or 0,
        "created_by": s.created_by,
        "created_at": s.created_at.isoformat() if s.created_at else "",
        "updated_at": s.updated_at.isoformat() if s.updated_at else "",
    }


def _load_json(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else []
    except Exception:
        return []


def list_skills(db: Session, keyword: Optional[str] = None) -> List[Dict[str, Any]]:
    q = db.query(Skill).order_by(Skill.name)
    if keyword:
        kw = f"%{keyword.strip()}%"
        q = q.filter(Skill.name.like(kw) | Skill.description.like(kw) | Skill.category.like(kw))
    return [_to_dict(s) for s in q.all()]


def get_skill(db: Session, skill_id: int) -> Optional[Skill]:
    return db.query(Skill).filter(Skill.id == skill_id).first()


def get_skill_by_name(db: Session, name: str) -> Optional[Skill]:
    return db.query(Skill).filter(Skill.name == name.strip()).first()


def create_skill(db: Session, data: Dict[str, Any], created_by: Optional[int] = None,
                 source: str = "upload", content: Optional[str] = None) -> Skill:
    """从 JSON/zip 安装技能。name 唯一;重名报 ValueError。"""
    name = str(data.get("name") or "").strip()
    if not name:
        raise ValueError("技能 name 不能为空")
    if get_skill_by_name(db, name):
        raise ValueError(f"技能 {name} 已存在")
    body = str(data.get("body") or data.get("content") or "").strip()
    if not content:
        content = build_skill_md({k: v for k, v in data.items() if k not in ("body", "content")}, body)
    skill = Skill(
        name=name,
        description=str(data.get("description") or "")[:512],
        version=str(data.get("version") or "1.0.0"),
        author=str(data.get("author") or ""),
        license=str(data.get("license") or ""),
        category=str(data.get("category") or ""),
        risk_level=str(data.get("risk_level") or "read_only"),
        keywords=json.dumps(data.get("keywords") or [], ensure_ascii=False),
        tools_required=json.dumps(data.get("tools_required") or [], ensure_ascii=False),
        content=content,
        source=source,
        enabled=True,
        created_by=created_by,
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


def update_skill(db: Session, skill_id: int, data: Dict[str, Any]) -> Skill:
    skill = get_skill(db, skill_id)
    if not skill:
        raise ValueError("技能不存在")
    if "enabled" in data:
        skill.enabled = bool(data["enabled"])
    for field in ("description", "version", "author", "license", "category", "risk_level"):
        if field in data and data[field] is not None:
            setattr(skill, field, str(data[field])[: (512 if field == "description" else 128)])
    if "keywords" in data and isinstance(data["keywords"], list):
        skill.keywords = json.dumps(data["keywords"], ensure_ascii=False)
    if "tools_required" in data and isinstance(data["tools_required"], list):
        skill.tools_required = json.dumps(data["tools_required"], ensure_ascii=False)
    skill.updated_at = datetime.now()
    db.commit()
    db.refresh(skill)
    return skill


def delete_skill(db: Session, skill_id: int) -> Dict[str, Any]:
    """卸载。内置技能只置 enabled=False(删除后重启 scan 会重建);其余删行。"""
    skill = get_skill(db, skill_id)
    if not skill:
        raise ValueError("技能不存在")
    if skill.source == "builtin":
        skill.enabled = False
        skill.updated_at = datetime.now()
        db.commit()
        return {"message": f"内置技能 {skill.name} 已禁用(卸载)", "disabled": True}
    db.delete(skill)
    db.commit()
    return {"message": f"技能 {skill.name} 已删除", "disabled": False}


# ─── 执行审计(F1 可审计) ─────────────────────────────────────────

def record_execution(db: Session, skill_id: int, skill_name: str, tool: str,
                     status: str, input_summary: str = "", output_summary: str = "",
                     duration_ms: int = 0, executed_by: Optional[int] = None) -> SkillExecution:
    if skill_id:
        db.query(Skill).filter(Skill.id == skill_id).update(
            {"usage_count": Skill.usage_count + 1}, synchronize_session=False)
    rec = SkillExecution(
        skill_id=skill_id,
        skill_name=skill_name,
        tool=tool,
        status=status,
        input_summary=(input_summary or "")[:MAX_INPUT_SUMMARY],
        output_summary=(output_summary or "")[:MAX_OUTPUT_SUMMARY],
        duration_ms=int(duration_ms),
        executed_by=executed_by,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def list_executions(db: Session, limit: int = 100) -> List[Dict[str, Any]]:
    rows = db.query(SkillExecution).order_by(SkillExecution.id.desc()).limit(limit).all()
    return [{
        "id": r.id,
        "skill_id": r.skill_id,
        "skill_name": r.skill_name,
        "tool": r.tool,
        "status": r.status,
        "input_summary": r.input_summary,
        "output_summary": r.output_summary,
        "duration_ms": r.duration_ms,
        "executed_by": r.executed_by,
        "created_at": r.created_at.isoformat() if r.created_at else "",
    } for r in rows]


# ─── 打包 / 市场(F2 私服分发) ────────────────────────────────────

def export_package(db: Session, skill_id: int) -> bytes:
    """导出技能为 zip(SKILL.md 单文件即 manifest)。"""
    skill = get_skill(db, skill_id)
    if not skill:
        raise ValueError("技能不存在")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SKILL.md", skill.content)
    return buf.getvalue()


def import_package(db: Session, data_bytes: bytes, created_by: Optional[int] = None,
                   source: str = "marketplace") -> Skill:
    """导入技能 zip: 读取 SKILL.md, 按 frontmatter 建库。"""
    try:
        with zipfile.ZipFile(io.BytesIO(data_bytes)) as zf:
            names = [n for n in zf.namelist() if n.endswith("SKILL.md")]
            if not names:
                raise ValueError("技能包缺少 SKILL.md")
            text = zf.read(names[0]).decode("utf-8")
    except zipfile.BadZipFile:
        raise ValueError("不是有效的 zip 技能包")
    meta, body = parse_frontmatter(text)
    name = str(meta.get("name") or "").strip()
    if not name:
        raise ValueError("SKILL.md 缺少 name 字段")
    return create_skill(db, {**meta, "body": body}, created_by=created_by,
                        source=source, content=text)


def scan_marketplace_packages() -> List[Dict[str, Any]]:
    """扫描市场 packages 目录, 解析每个 zip 的 manifest(frontmatter)。"""
    _ensure_dirs()
    out: List[Dict[str, Any]] = []
    for p in sorted(PACKAGE_DIR.glob("*.zip")):
        try:
            with zipfile.ZipFile(p) as zf:
                names = [n for n in zf.namelist() if n.endswith("SKILL.md")]
                if not names:
                    continue
                text = zf.read(names[0]).decode("utf-8")
            meta, _ = parse_frontmatter(text)
            out.append({
                "package": p.name,
                "name": str(meta.get("name") or p.stem),
                "version": str(meta.get("version") or "?"),
                "author": str(meta.get("author") or ""),
                "description": str(meta.get("description") or "")[:300],
                "category": str(meta.get("category") or ""),
                "size_bytes": p.stat().st_size,
            })
        except Exception:
            continue
    return out


def publish_to_marketplace(db: Session, skill_id: int) -> str:
    """发布技能到私服市场: 导出 zip 落到 marketplace/packages/<name>-<version>.zip。"""
    skill = get_skill(db, skill_id)
    if not skill:
        raise ValueError("技能不存在")
    pkg_name = f"{skill.name}-{skill.version}.zip"
    target = PACKAGE_DIR / pkg_name
    target.write_bytes(export_package(db, skill_id))
    return pkg_name


def install_from_marketplace(db: Session, package: str, created_by: Optional[int] = None) -> Skill:
    """从市场包安装到技能库。"""
    _ensure_dirs()
    p = PACKAGE_DIR / package
    if not p.exists():
        raise ValueError("市场包不存在")
    return import_package(db, p.read_bytes(), created_by=created_by, source="marketplace")


def delete_marketplace_package(package: str) -> None:
    _ensure_dirs()
    p = PACKAGE_DIR / package
    if p.exists():
        p.unlink()
