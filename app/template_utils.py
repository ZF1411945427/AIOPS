import json
from fastapi.templating import Jinja2Templates

_templates = Jinja2Templates(directory="app/templates")
_templates.env.filters["from_json"] = lambda v: json.loads(v) if (isinstance(v, str) and v.strip()) else (v if isinstance(v, dict) else {})

def get_templates():
    return _templates

