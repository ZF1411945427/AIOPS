"""Check OpenAPI schema validity."""
import os, sys
os.environ['AIOPS_DB_URL'] = 'sqlite:///:memory:'
from app.main import app
schema = app.openapi()
paths = schema.get("paths", {})
print(f"OpenAPI paths: {len(paths)}")
print(f"OpenAPI schemas: {len(schema.get('components', {}).get('schemas', {}))}")
assert len(paths) > 50, f"Routes too few: {len(paths)}"
print("OpenAPI schema valid")