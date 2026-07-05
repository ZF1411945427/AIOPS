import json
from fastapi.templating import Jinja2Templates

_templates = Jinja2Templates(directory="app/templates")
_templates.env.filters["from_json"] = lambda v: json.loads(v) if (isinstance(v, str) and v.strip()) else (v if isinstance(v, dict) else {})

def get_templates():
    return _templates


def parse_json_config(raw):
    """安全解析 JSON 配置字段。空字符串/None/无效 JSON 返回 {}，dict 原样返回。"""
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    if isinstance(raw, dict):
        return raw
    return {}

