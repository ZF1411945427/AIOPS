import json
import os
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SystemConfig

router = APIRouter(prefix="/api/menu", tags=["menu"])

# 从 JSON 文件加载
_config_path = os.path.join(os.path.dirname(__file__), "menu_config.json")
if os.path.exists(_config_path):
    with open(_config_path, "r", encoding="utf-8") as f:
        DEFAULT_MENU = json.load(f)
else:
    DEFAULT_MENU = []

@router.get("")
def get_menu(db: Session = Depends(get_db)):
    """获取菜单配置"""
    # 尝试从数据库读取
    config = db.query(SystemConfig).filter(SystemConfig.key == "menu_config").first()
    if config and config.value:
        return json.loads(config.value)
    
    # 使用默认配置
    return DEFAULT_MENU
