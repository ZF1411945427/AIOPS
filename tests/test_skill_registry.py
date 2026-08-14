"""技能注册表 frontmatter 解析单元测试(H3)。纯函数, 无需 DB。"""
import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.skill_registry import parse_frontmatter, build_skill_md


def test_parse_frontmatter_meta():
    md = """---
name: demo
description: demo skill
version: 2.0.0
tools_required: ["query_logs", "query_alerts"]
---
# 正文
## 步骤
1. a
"""
    meta, body = parse_frontmatter(md)
    assert meta["name"] == "demo"
    assert meta["tools_required"] == ["query_logs", "query_alerts"]
    assert "步骤" in body


def test_parse_no_frontmatter():
    meta, body = parse_frontmatter("just text")
    assert meta == {}
    assert body == "just text"


def test_build_roundtrip():
    md = """---
name: demo
description: d
version: 1.0.0
keywords: ["a", "b"]
---
body here
"""
    meta, body = parse_frontmatter(md)
    rebuilt = build_skill_md(meta, body)
    meta2, body2 = parse_frontmatter(rebuilt)
    assert meta2["name"] == "demo"
    assert meta2["keywords"] == ["a", "b"]
    assert "body here" in body2 or "body here" == body2.strip()


def test_parse_malformed_yaml_returns_empty_meta():
    # 损坏的 yaml 不应抛异常
    md = "---\nname: [unclosed\n---\ncontent"
    meta, _ = parse_frontmatter(md)
    assert isinstance(meta, dict)
