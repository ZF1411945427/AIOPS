"""CONTRACT.md 字段漂移检测服务（P2 任务#8）

封装字段漂移检测逻辑，供 API 和脚本调用。
将"文档约定"变成"工具强制"，杜绝字段漂移导致的静默数据丢失。

设计原则:
- 高置信度违规: CONTRACT 标注违规字段在 models.py 中使用 / 命名规则违规 / 长度规范违规
- 低置信度违规: CONTRACT 标注违规字段在 routers 中作为 dict key 出现（可能误报）
- 自动过滤明显误报（通用字段名 in 与表无关的 router 文件）
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# 路径基于包位置动态计算（遵循路径规范契约）
_APP_DIR = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _APP_DIR.parent
_CONTRACT_PATH = _PROJECT_ROOT / "CONTRACT.md"
_MODELS_PATH = _APP_DIR / "models.py"
_ROUTERS_DIR = _APP_DIR / "routers"


# ── 全局命名规则（CONTRACT.md 第一章）──
FORBIDDEN_DESC_FIELDS = {"notes", "note", "comment", "remarks", "remark", "memo", "detail"}
FORBIDDEN_GENERIC_CONFIG = {"config", "params", "data"}
FORBIDDEN_BOOL_NAMES = {"success", "active", "visible", "auto_rotate", "auto_recovered",
                        "asset_recovered", "alert_resolved", "hallucination_flag",
                        "published", "resolved", "ai_analysis", "schedule_enabled",
                        "require_confirmation", "requires_confirm", "allow_action_execution"}

# DateTime 字段应后缀 _at 的例外（含 created_at 等合规字段）
TIME_FIELD_EXCEPTIONS = {
    "timestamp", "created_at", "updated_at", "resolved_at", "acknowledged_at",
    "started_at", "finished_at", "expires_at", "executed_at", "planned_started_at",
    "planned_ended_at", "period_started_at", "period_ended_at", "last_checked_at",
    "last_scraped_at", "current_period_started_at", "current_period_ended_at",
    "check_at", "last_success_at", "last_failure_at", "last_run_at", "next_run_at",
    "last_message_at", "last_status_at", "last_heartbeat_at",
}

# 跨表统一长度（CONTRACT.md 第三章）
LENGTH_SPEC = {
    "name": 128, "title": 256, "status": 32, "severity": 32,
    "metric_name": 64, "category": 32, "ci_type": 32, "risk_level": 16,
    "source": 32, "reason": 256, "tags": 256, "cron_expr": 128,
    "service_name": 128,
}

# 第四章废弃字段
DEPRECATED_FIELDS = {
    "assets": {"type": "ci_type"},
}

# 同名 router 文件优先匹配（高置信度）
# 比如 assets 表的违规字段如果出现在 assets.py 里就是高置信度
_TABLE_TO_ROUTER_HINTS = {
    "assets": "assets.py",
    "alerts": "alerts.py",
    "alert_silences": "alert_silence.py",
    "notification_channels": "notifications.py",
    "notification_logs": "notifications.py",
    "remediation_logs": "remediation.py",
    "remediation_effects": "remediation_effect.py",
    "auto_remediations": "remediation.py",
    "reports": "reports.py",
    "dashboard_card_configs": "dashboard_config.py",
    "prediction_models": "prediction_models.py",
    "data_sources": "datasources.py",
    "change_requests": "change_workflow.py",
    "spans": "trace_ingest.py",
    "netflow_records": "netflow.py",
    "asset_lifecycles": "lifecycle.py",
    "change_tasks": "change_workflow.py",
    "error_budgets": "sre.py",
    "sla_records": "sre.py",
    "availability_reports": "sre.py",
    "ci_attributes": "ci_models.py",
    "cluster_anomaly_events": "cluster_anomaly.py",
    "api_tokens": "tokens.py",
    "k8s_events": "k8s_monitor.py",
    "discovery_schedules": "asset_discovery.py",
    "discovery_jobs": "asset_discovery.py",
    "report_schedules": "report_schedules.py",
    "ext_cmdb_configs": "ext_cmdb.py",
    "ext_event_sources": "event_sources.py",
    "system_configs": "settings.py",
    "incident_approvals": "incidents.py",
    "blue_green_switch_records": "blue_green.py",
    "remediation_effect_records": "remediation_effect.py",
    "agent_evaluations": "agent_eval.py",
    "ab_test_records": "ab_test.py",
    "oncall_schedules": "OnCallView.vue",
    "agent_ground_truths": "agent_ground_truth.py",
    "agent_ground_truth_runs": "agent_ground_truth.py",
    "ab_test_configs": "ab_test.py",
    "knowledge_drafts": "knowledge_autogen.py",
    "knowledge_base": "knowledge.py",
    "alert_kb_links": "alerts.py",
    "chaos_experiments": "chaos.py",
    "chaos_runs": "chaos.py",
}


def parse_contract() -> Dict[str, Any]:
    """解析 CONTRACT.md 提取规范信息。

    返回: {"tables": {table_name: {"violations": [...], "expected_fields": [...]}}, "deprecated": {...}}
    """
    if not _CONTRACT_PATH.exists():
        return {"tables": {}, "deprecated": DEPRECATED_FIELDS}

    content = _CONTRACT_PATH.read_text(encoding="utf-8")
    tables: Dict[str, Any] = {}

    table_header_re = re.compile(r"^### `([a-z_][a-z0-9_]*)`", re.MULTILINE)
    for m in table_header_re.finditer(content):
        table_name = m.group(1)
        start = m.end()
        next_section = re.search(r"^### |^---", content[start:], re.MULTILINE)
        block = content[start:start + next_section.start()] if next_section else content[start:]

        violations: List[Dict[str, str]] = []
        expected_fields: List[str] = []
        row_re = re.compile(
            r"^\|\s*(?:\*\*)?`?([a-z_][a-z0-9_]*)`?(?:\*\*)?\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|$",
            re.MULTILINE,
        )
        for rm in row_re.finditer(block):
            field = rm.group(1)
            current = rm.group(2).strip()
            fix = rm.group(3).strip()
            note = rm.group(4).strip()
            if field in ("字段名", "field") or current.startswith("当前") or current == "类型":
                continue
            if field in ("(已有字段)",):
                continue
            expected_fields.append(field)
            fix_match = re.search(r"\*\*`([a-z_][a-z0-9_]*)`\*\*", fix)
            is_violation = fix_match is not None or "❌" in note or "删除" in fix
            if is_violation:
                new_name = fix_match.group(1) if fix_match else ""
                if "删除" in fix and not new_name:
                    new_name = "(删除)"
                violations.append({
                    "field": field, "old": field, "new": new_name,
                    "current": current, "reason": note or fix,
                })
        if violations or expected_fields:
            tables[table_name] = {"violations": violations, "expected_fields": expected_fields}

    return {"tables": tables, "deprecated": DEPRECATED_FIELDS}


def parse_models() -> Dict[str, List[Dict[str, Any]]]:
    """AST 解析 models.py，提取每个表的字段定义。"""
    if not _MODELS_PATH.exists():
        return {}
    source = _MODELS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    tables: Dict[str, List[Dict[str, Any]]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = [getattr(b, "id", "") for b in node.bases]
        if "Base" not in bases:
            continue
        table_name: Optional[str] = None
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for tgt in stmt.targets:
                    if isinstance(tgt, ast.Name) and tgt.id == "__tablename__":
                        if isinstance(stmt.value, ast.Constant):
                            table_name = stmt.value.value
        if not table_name:
            table_name = re.sub(r"(?<!^)(?=[A-Z])", "_", node.name).lower()

        fields: List[Dict[str, Any]] = []
        for stmt in node.body:
            target = None
            value = None
            if isinstance(stmt, ast.AnnAssign):
                target = stmt.target
                value = stmt.value
            elif isinstance(stmt, ast.Assign) and stmt.targets:
                target = stmt.targets[0]
                value = stmt.value
            if not isinstance(target, ast.Name) or not isinstance(value, ast.Call):
                continue
            field_name = target.id
            if field_name.startswith("_") or field_name == "__tablename__":
                continue
            func_name = ""
            if isinstance(value.func, ast.Name):
                func_name = value.func.id
            elif isinstance(value.func, ast.Attribute):
                func_name = value.func.attr
            if func_name != "Column":
                continue
            type_name = ""
            length: Optional[int] = None
            nullable = True
            is_pk = False
            if value.args:
                first_arg = value.args[0]
                if isinstance(first_arg, ast.Call):
                    if isinstance(first_arg.func, ast.Name):
                        type_name = first_arg.func.id
                    elif isinstance(first_arg.func, ast.Attribute):
                        type_name = first_arg.func.attr
                    if first_arg.args:
                        la = first_arg.args[0]
                        if isinstance(la, ast.Constant) and isinstance(la.value, int):
                            length = la.value
                elif isinstance(first_arg, ast.Name):
                    type_name = first_arg.id
            for kw in value.keywords:
                if kw.arg == "primary_key" and isinstance(kw.value, ast.Constant):
                    is_pk = bool(kw.value.value)
                elif kw.arg == "nullable" and isinstance(kw.value, ast.Constant):
                    nullable = bool(kw.value.value)
            fields.append({
                "name": field_name, "type": type_name, "length": length,
                "nullable": nullable, "is_pk": is_pk,
            })
        tables[table_name] = fields
    return tables


def parse_routers() -> Dict[str, Set[str]]:
    """扫描 routers/*.py，提取每个文件中出现的 dict 字面量 key。"""
    if not _ROUTERS_DIR.exists():
        return {}
    result: Dict[str, Set[str]] = {}
    for py_file in _ROUTERS_DIR.glob("*.py"):
        if py_file.name.startswith("__"):
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception:
            continue
        keys: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for k in node.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        if re.match(r"^[a-z][a-z0-9_]*$", k.value):
                            keys.add(k.value)
        result[py_file.name] = keys
    return result


def _confidence_for_router_use(table: str, field: str, router_files: List[str]) -> str:
    """判断 router 中字段使用的置信度。

    Returns: "high" | "medium" | "low"
    - high: 与该表同名的 router 文件中使用了该字段（强信号）
    - medium: 任意 router 中使用了该字段
    - low: 通用字段名（success/content/data 等在多个无关文件中出现）
    """
    generic_fields = {"success", "content", "data", "type", "config", "params",
                      "notes", "note", "comment", "value", "result", "status",
                      "name", "title", "description", "id", "created_at"}
    hint_router = _TABLE_TO_ROUTER_HINTS.get(table, "")
    if hint_router and hint_router in router_files:
        return "high"
    if field in generic_fields:
        return "low"
    return "medium"


def check_contract() -> Dict[str, Any]:
    """主检测函数: 返回完整 diff 报告。"""
    contract = parse_contract()
    models_fields = parse_models()
    router_keys = parse_routers()

    # 1. CONTRACT.md 标注违规字段仍使用
    contract_violations: List[Dict[str, Any]] = []
    for table_name, info in contract["tables"].items():
        for v in info["violations"]:
            old_field = v["field"]
            new_field = v["new"]
            in_models = False
            if table_name in models_fields:
                in_models = any(f["name"] == old_field for f in models_fields[table_name])
            router_files_with: List[str] = []
            for fname, keys in router_keys.items():
                if old_field in keys:
                    router_files_with.append(fname)
            in_routers = bool(router_files_with)
            if in_models or in_routers:
                confidence = "high" if in_models else _confidence_for_router_use(
                    table_name, old_field, router_files_with
                )
                contract_violations.append({
                    "table": table_name,
                    "field": old_field,
                    "should_be": new_field or "(删除)",
                    "in_models": in_models,
                    "in_routers": in_routers,
                    "router_files": router_files_with[:5],
                    "reason": v["reason"],
                    "confidence": confidence,
                })

    # 2. 废弃字段检测
    deprecated_usage: List[Dict[str, Any]] = []
    for table, fields in contract["deprecated"].items():
        for old_field in fields:
            in_models = False
            if table in models_fields:
                in_models = any(f["name"] == old_field for f in models_fields[table])
            router_files_with: List[str] = []
            for fname, keys in router_keys.items():
                if old_field in keys:
                    router_files_with.append(fname)
            if in_models or router_files_with:
                deprecated_usage.append({
                    "table": table,
                    "field": old_field,
                    "replace_with": fields[old_field],
                    "in_models": in_models,
                    "router_files": router_files_with[:5],
                    "confidence": "high" if in_models else _confidence_for_router_use(
                        table, old_field, router_files_with
                    ),
                })

    # 3. 命名规则违规
    naming_violations: List[Dict[str, Any]] = []
    for table, fields in models_fields.items():
        for f in fields:
            name = f["name"]
            ftype = f["type"]
            if name == "id" or f["is_pk"]:
                continue
            if ftype == "Boolean":
                if name in FORBIDDEN_BOOL_NAMES or (
                    not name.startswith("is_") and not name.startswith("has_")
                    and name not in ("enabled",)
                ):
                    naming_violations.append({
                        "table": table, "field": name, "type": ftype,
                        "rule": "Boolean 字段需前缀 is_/has_ 或为 enabled",
                        "confidence": "high",
                    })
            if ftype == "DateTime":
                if not name.endswith("_at") and name not in TIME_FIELD_EXCEPTIONS:
                    naming_violations.append({
                        "table": table, "field": name, "type": ftype,
                        "rule": "DateTime 字段需后缀 _at",
                        "confidence": "high",
                    })
            if name in FORBIDDEN_DESC_FIELDS:
                naming_violations.append({
                    "table": table, "field": name, "type": ftype,
                    "rule": f"描述字段禁止用 {name}，应为 description",
                    "confidence": "high",
                })
            if name in FORBIDDEN_GENERIC_CONFIG:
                naming_violations.append({
                    "table": table, "field": name, "type": ftype,
                    "rule": f"JSON/配置字段禁止泛型名 {name}，需带业务前缀",
                    "confidence": "high",
                })

    # 4. 长度规范违规
    length_violations: List[Dict[str, Any]] = []
    for table, fields in models_fields.items():
        for f in fields:
            name = f["name"]
            if name in LENGTH_SPEC and f["length"] is not None:
                expected = LENGTH_SPEC[name]
                if f["length"] != expected:
                    length_violations.append({
                        "table": table, "field": name,
                        "actual": f["length"], "expected": expected,
                        "confidence": "high",
                    })

    # 5. 汇总
    high_count = (
        sum(1 for v in contract_violations if v["confidence"] == "high")
        + sum(1 for v in deprecated_usage if v["confidence"] == "high")
        + len(naming_violations) + len(length_violations)
    )
    summary = {
        "total_tables_in_contract": len(contract["tables"]),
        "total_tables_in_models": len(models_fields),
        "contract_violations_count": len(contract_violations),
        "deprecated_usage_count": len(deprecated_usage),
        "naming_violations_count": len(naming_violations),
        "length_violations_count": len(length_violations),
        "high_confidence_count": high_count,
        "total_violations": (
            len(contract_violations) + len(deprecated_usage)
            + len(naming_violations) + len(length_violations)
        ),
        "passed": high_count == 0,
    }

    return {
        "summary": summary,
        "contract_violations": contract_violations,
        "deprecated_usage": deprecated_usage,
        "naming_violations": naming_violations,
        "length_violations": length_violations,
        "tables_in_models": sorted(models_fields.keys()),
        "contract_tables": sorted(contract["tables"].keys()),
    }
