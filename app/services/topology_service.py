import json
from sqlalchemy.orm import Session

from app.models import Asset, AssetRelation


def get_relations(db: Session):
    return db.query(AssetRelation).all()


def create_relation(db: Session, parent_id: int, child_id: int, relation_type: str = "depends_on"):
    if parent_id == child_id:
        return None
    exists = db.query(AssetRelation).filter(
        AssetRelation.parent_id == parent_id,
        AssetRelation.child_id == child_id,
    ).first()
    if exists:
        return exists
    r = AssetRelation(parent_id=parent_id, child_id=child_id, relation_type=relation_type)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def delete_relation(db: Session, relation_id: int):
    db.query(AssetRelation).filter(AssetRelation.id == relation_id).delete()
    db.commit()


def build_topo(db: Session):
    assets = db.query(Asset).order_by(Asset.type, Asset.name).all()
    relations = db.query(AssetRelation).all()
    asset_map = {a.id: {"id": a.id, "name": a.name, "type": a.type, "ci_type": a.ci_type, "status": a.status} for a in assets}
    children_map = {}
    for r in relations:
        children_map.setdefault(r.parent_id, []).append({
            "child_id": r.child_id, "type": r.relation_type,
        })
    trees = []
    linked = set()
    for r in relations:
        linked.add(r.child_id)
    roots = [a for a in assets if a.id not in linked]

    def build_node(aid):
        node = dict(asset_map.get(aid, {}))
        children = children_map.get(aid, [])
        if children:
            node["children"] = [build_node(c["child_id"]) for c in children]
        return node

    for root in roots:
        trees.append(build_node(root.id))
    orphans = [a for a in assets if a.id not in linked and a.id not in {r.parent_id for r in relations}]
    for o in orphans:
        if o.id not in linked:
            trees.append(build_node(o.id))
    return trees


def build_container_topo(db: Session):
    container_types = ["cluster", "namespace", "node", "deployment", "statefulset", "daemonset", "pod", "service", "ingress", "pvc", "container"]
    assets = db.query(Asset).filter(Asset.ci_type.in_(container_types)).order_by(Asset.ci_type, Asset.name).all()
    asset_map = {}
    for a in assets:
        try:
            attrs = json.loads(a.ci_attributes) if isinstance(a.ci_attributes, str) else a.ci_attributes or {}
        except Exception:
            attrs = {}
        asset_map[a.id] = {
            "id": a.id,
            "name": a.name.split("/")[-1],
            "full_name": a.name,
            "ci_type": a.ci_type,
            "status": a.status,
            "k8s_cluster": a.k8s_cluster,
            "attrs": attrs,
            "parent_id": a.parent_id,
        }

    children_map = {}
    for aid, a in asset_map.items():
        pid = a.get("parent_id")
        if pid and pid in asset_map:
            children_map.setdefault(pid, []).append(aid)

    roots = [aid for aid, a in asset_map.items() if a.get("parent_id") not in asset_map]

    def build_node(aid):
        a = asset_map.get(aid, {})
        node = {
            "id": a["id"],
            "name": a["name"],
            "full_name": a["full_name"],
            "ci_type": a["ci_type"],
            "status": a["status"],
            "k8s_cluster": a["k8s_cluster"],
            "attrs": a["attrs"],
        }
        kids = children_map.get(aid, [])
        if kids:
            node["children"] = [build_node(kid) for kid in kids]
        return node

    return [build_node(root) for root in roots if root in asset_map]

