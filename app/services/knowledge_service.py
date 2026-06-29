from datetime import datetime

from sqlalchemy.orm import Session

from app.models import KnowledgeBase, AlertKbLink


def list_kb(db: Session, tag: str = ""):
    q = db.query(KnowledgeBase)
    if tag:
        q = q.filter(KnowledgeBase.tags.like(f"%{tag}%"))
    return q.order_by(KnowledgeBase.updated_at.desc()).all()


def get_kb(db: Session, kb_id: int):
    return db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()


def create_kb(db: Session, data: dict):
    kb = KnowledgeBase(**data)
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb


def update_kb(db: Session, kb_id: int, data: dict):
    kb = get_kb(db, kb_id)
    if not kb:
        return None
    for k, v in data.items():
        setattr(kb, k, v)
    kb.updated_at = datetime.now()
    db.commit()
    db.refresh(kb)
    return kb


def delete_kb(db: Session, kb_id: int):
    db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).delete()
    db.query(AlertKbLink).filter(AlertKbLink.kb_id == kb_id).delete()
    db.commit()


def link_alert_to_kb(db: Session, alert_id: int, kb_id: int):
    exists = db.query(AlertKbLink).filter(
        AlertKbLink.alert_id == alert_id, AlertKbLink.kb_id == kb_id,
    ).first()
    if not exists:
        db.add(AlertKbLink(alert_id=alert_id, kb_id=kb_id))
        db.commit()


def get_kb_for_alert(db: Session, alert_id: int):
    links = db.query(AlertKbLink).filter(AlertKbLink.alert_id == alert_id).all()
    if not links:
        return []
    kb_ids = [l.kb_id for l in links]
    return db.query(KnowledgeBase).filter(KnowledgeBase.id.in_(kb_ids)).all()


