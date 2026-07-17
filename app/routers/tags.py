from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Asset, TagCategory, Tag

router = APIRouter(prefix="/tags", tags=["tags"])


# -------- 旧数据迁移（从 Asset.tags 字符串迁移到 Tag 表） --------
@router.post("/api/migrate")
def migrate_old_tags(db: Session = Depends(get_db)):
    all_assets = db.query(Asset).all()
    migrated = 0
    for a in all_assets:
        if not a.tags:
            continue
        for t in [t.strip() for t in a.tags.split(",") if t.strip()]:
            existing = db.query(Tag).filter(Tag.name == t).first()
            if not existing:
                db.add(Tag(name=t, color="#6366f1"))
                migrated += 1
    db.commit()
    return {"status": "ok", "migrated": migrated}


# -------- 分类管理 --------

@router.get("/api/categories")
def list_categories(db: Session = Depends(get_db)):
    cats = db.query(TagCategory).order_by(TagCategory.sort_order, TagCategory.id).all()
    return {"categories": [{"id": c.id, "name": c.name, "label": c.label, "color": c.color, "icon": c.icon} for c in cats]}


@router.post("/api/categories")
def create_category(payload: dict = Body(...), db: Session = Depends(get_db)):
    name = payload.get("name", "").strip()
    label = payload.get("label", name)
    color = payload.get("color", "#6366f1")
    icon = payload.get("icon", "🏷️")
    sort_order = int(payload.get("sort_order", 0))
    if not name:
        return {"status": "error", "message": "分类名称不能为空"}
    existing = db.query(TagCategory).filter(TagCategory.name == name).first()
    if existing:
        return {"status": "error", "message": "分类已存在"}
    cat = TagCategory(name=name, label=label, color=color, icon=icon, sort_order=sort_order)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return {"status": "ok", "category": {"id": cat.id, "name": cat.name, "label": cat.label, "color": cat.color, "icon": cat.icon}}


@router.put("/api/categories/{cat_id}")
def update_category(cat_id: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    cat = db.query(TagCategory).filter(TagCategory.id == cat_id).first()
    if not cat:
        return {"status": "error", "message": "分类不存在"}
    if "label" in payload:
        cat.label = payload["label"]
    if "color" in payload:
        cat.color = payload["color"]
    if "icon" in payload:
        cat.icon = payload["icon"]
    if "sort_order" in payload:
        cat.sort_order = int(payload["sort_order"])
    db.commit()
    return {"status": "ok"}


@router.delete("/api/categories/{cat_id}")
def delete_category(cat_id: int, db: Session = Depends(get_db)):
    cat = db.query(TagCategory).filter(TagCategory.id == cat_id).first()
    if not cat:
        return {"status": "error", "message": "分类不存在"}
    db.query(Tag).filter(Tag.category_id == cat_id).update({"category_id": None})
    db.delete(cat)
    db.commit()
    return {"status": "ok"}


# -------- 标签管理 --------

@router.get("/api/list")
def list_tags(
    page: int = 1,
    per_page: int = 24,
    category_id: int = None,
    search: str = "",
    sort_by: str = "name",
    db: Session = Depends(get_db),
):
    q = db.query(Tag)
    if category_id:
        q = q.filter(Tag.category_id == category_id)
    if search:
        q = q.filter(Tag.name.ilike(f"%{search}%"))
    total = q.count()
    if sort_by == "count":
        q = q.order_by(Tag.id)  # 实际按使用量排序在 Python 层做
    elif sort_by == "recent":
        q = q.order_by(Tag.id.desc())
    else:
        q = q.order_by(Tag.name)
    tags = q.offset((page - 1) * per_page).limit(per_page).all()
    result = []
    for t in tags:
        count = _tag_usage_count(db, t.name)
        result.append({
            "id": t.id,
            "name": t.name,
            "category_id": t.category_id,
            "color": t.color,
            "description": t.description,
            "usage_count": count,
        })
    if sort_by == "count":
        result.sort(key=lambda x: -x["usage_count"])
    category_counts = {}
    for c in db.query(TagCategory).all():
        cnt = db.query(Tag).filter(Tag.category_id == c.id).count()
        category_counts[c.id] = cnt
    return {
        "tags": result,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page if total > 0 else 1,
        "category_counts": category_counts,
        "all_tags_count": db.query(Tag).count(),
    }


@router.post("/api")
def create_tag(payload: dict = Body(...), db: Session = Depends(get_db)):
    name = payload.get("name", "").strip()
    if not name:
        return {"status": "error", "message": "标签名称不能为空"}
    existing = db.query(Tag).filter(Tag.name == name).first()
    if existing:
        return {"status": "error", "message": "标签已存在"}
    tag = Tag(
        name=name,
        category_id=payload.get("category_id") or None,
        color=payload.get("color", "#6366f1"),
        description=payload.get("description", ""),
    )
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return {"status": "ok", "tag": {"id": tag.id, "name": tag.name, "category_id": tag.category_id, "color": tag.color}}


@router.put("/api/{tag_id}")
def update_tag(tag_id: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        return {"status": "error", "message": "标签不存在"}
    if "name" in payload:
        tag.name = payload["name"].strip()
    if "category_id" in payload:
        tag.category_id = payload["category_id"] or None
    if "color" in payload:
        tag.color = payload["color"]
    if "description" in payload:
        tag.description = payload["description"]
    db.commit()
    return {"status": "ok"}


@router.delete("/api/{tag_id}")
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        return {"status": "error", "message": "标签不存在"}
    _remove_tag_from_all_assets(db, tag.name)
    db.delete(tag)
    db.commit()
    return {"status": "ok"}


# -------- 标签分配 --------

@router.post("/api/assign")
def assign_tag(payload: dict = Body(...), db: Session = Depends(get_db)):
    asset_id = int(payload.get("asset_id", 0) or 0)
    tag_name = payload.get("tag", "").strip()
    if not tag_name or asset_id <= 0:
        return {"status": "error", "message": "参数错误"}
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return {"status": "error", "message": "资产不存在"}
    existing = [t.strip() for t in (asset.tags or "").split(",") if t.strip()]
    if tag_name not in existing:
        existing.append(tag_name)
        asset.tags = ",".join(existing)
        db.commit()
    return {"status": "ok"}


@router.post("/api/remove")
def remove_tag(payload: dict = Body(...), db: Session = Depends(get_db)):
    asset_id = int(payload.get("asset_id", 0) or 0)
    tag_name = payload.get("tag", "").strip()
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if asset:
        existing = [t.strip() for t in (asset.tags or "").split(",") if t.strip()]
        existing = [t for t in existing if t != tag_name]
        asset.tags = ",".join(existing)
        db.commit()
    return {"status": "ok"}


# -------- 标签云（兼容旧前端） --------

@router.get("/api/cloud")
def tag_cloud(db: Session = Depends(get_db)):
    all_assets = db.query(Asset).all()
    tag_map = {}
    for a in all_assets:
        for t in [t.strip() for t in (a.tags or "").split(",") if t.strip()]:
            tag_map[t] = tag_map.get(t, 0) + 1
    return {"tags": [{"name": k, "count": v} for k, v in sorted(tag_map.items(), key=lambda x: -x[1])]}


# -------- 标签关联资产列表 --------

@router.get("/api/assets")
def tagged_assets(tag: str = "", db: Session = Depends(get_db)):
    all_assets = db.query(Asset).all()
    result = []
    for a in all_assets:
        tags = [t.strip() for t in (a.tags or "").split(",") if t.strip()]
        if tag and tag not in tags:
            continue
        result.append({"id": a.id, "name": a.name, "ip": a.ip, "ci_type": a.ci_type, "tags": tags})
    return {"assets": result, "count": len(result)}


@router.get("/api/all-assets")
def all_assets_for_tag(db: Session = Depends(get_db)):
    assets = db.query(Asset).order_by(Asset.name).all()
    return {"assets": [{"id": a.id, "name": a.name, "ip": a.ip, "tags": a.tags or ""} for a in assets]}


# -------- 辅助函数 --------

def _tag_usage_count(db: Session, tag_name: str) -> int:
    return db.query(Asset).filter(Asset.tags.contains(tag_name)).count()


def _remove_tag_from_all_assets(db: Session, tag_name: str):
    assets = db.query(Asset).filter(Asset.tags.contains(tag_name)).all()
    for a in assets:
        existing = [t.strip() for t in (a.tags or "").split(",") if t.strip()]
        existing = [t for t in existing if t != tag_name]
        a.tags = ",".join(existing)
    db.commit()
