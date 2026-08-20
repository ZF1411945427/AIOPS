import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.database import get_session_for
from app.models.ops import ComponentInstall
from app.models.asset import Asset
from sqlalchemy import select, desc

SessionLocal = get_session_for("real")
db = SessionLocal()
try:
    row = db.execute(select(ComponentInstall).order_by(desc(ComponentInstall.updated_at)).limit(1)).scalar_one_or_none()
    if not row:
        print("NO record")
    else:
        print("id:", row.id, "| component:", row.component_name, "| asset_id:", row.asset_id)
        print("deploy_type:", row.deploy_type, "| path:", row.deploy_path)
        print("port:", row.port)
        print("=== deploy_log (tail) ===")
        print((row.deploy_log or "")[-3000:])
        asset = db.get(Asset, row.asset_id)
        if asset:
            print("=== asset ===")
            print("name:", asset.name, "| ip:", asset.ip, "| host:", getattr(asset, 'host', None))
            print("ci_type:", getattr(asset, 'ci_type', None), "| ci_subtype:", getattr(asset, 'ci_subtype', None))
            print("connection_type:", getattr(asset, 'connection_type', None))
            print("connection_config:", str(getattr(asset, 'connection_config', None)))
finally:
    db.close()
