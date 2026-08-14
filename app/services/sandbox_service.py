"""AI 运维沙盒策略引擎 — 独立模块，不侵入现有 Agent/Edge 执行链。

核心职责：
1. 读取全局沙盒配置（sandbox_configs）
2. 按作用范围匹配最具体策略（session > user > role > global）
3. 对一次动作请求做决策：allowed / rejected / dry_run
4. 记录执行日志（sandbox_execution_logs）

决策顺序（CONTRACT.md 第九章 9.4）：
  黑名单(blocked) → 白名单(allowed) → 风险等级 → 执行配额
"""
import json
import re
from datetime import datetime

from app.database import get_session_for, get_db_mode
from app.models import SandboxConfig, SandboxPolicy, SandboxExecutionLog

# 风险等级顺序（只升不降）
RISK_ORDER = ["read_only", "advisory", "medium", "high", "critical"]

# 默认全局配置（无配置行时使用）
_DEFAULT_CONFIG = {
    "is_enabled": False,
    "dry_run_mode": False,
    "max_actions_per_session": 10,
    "max_actions_per_day": 50,
    "max_risk_level": "critical",
    "execution_window_start": "",
    "execution_window_end": "",
}


def _ensure_config(db) -> SandboxConfig:
    """确保存在全局配置行（单行）。"""
    cfg = db.query(SandboxConfig).first()
    if not cfg:
        cfg = SandboxConfig()
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def get_config(db=None) -> dict:
    """获取沙盒全局配置（dict）。"""
    own_session = False
    if db is None:
        db = get_session_for(get_db_mode())()
        own_session = True
    try:
        cfg = _ensure_config(db)
        return {
            "id": cfg.id,
            "is_enabled": cfg.is_enabled,
            "dry_run_mode": cfg.dry_run_mode,
            "max_actions_per_session": cfg.max_actions_per_session,
            "max_actions_per_day": cfg.max_actions_per_day,
            "max_risk_level": cfg.max_risk_level,
            "execution_window_start": cfg.execution_window_start,
            "execution_window_end": cfg.execution_window_end,
        }
    except Exception:
        return dict(_DEFAULT_CONFIG)
    finally:
        if own_session:
            db.close()


def update_config(data: dict, db=None) -> dict:
    """更新全局配置，返回最新配置。"""
    own_session = False
    if db is None:
        db = get_session_for(get_db_mode())()
        own_session = True
    try:
        cfg = _ensure_config(db)
        for key in ("name",):
            if key in data:
                setattr(cfg, key, data[key])
        for key in ("is_enabled", "dry_run_mode"):
            if key in data:
                setattr(cfg, key, bool(data[key]))
        for key in ("max_actions_per_session", "max_actions_per_day"):
            if key in data:
                try:
                    setattr(cfg, key, int(data[key]))
                except (TypeError, ValueError):
                    pass
        if "max_risk_level" in data and data["max_risk_level"] in RISK_ORDER:
            cfg.max_risk_level = data["max_risk_level"]
        for key in ("execution_window_start", "execution_window_end"):
            if key in data:
                setattr(cfg, key, str(data[key])[:5])
        db.commit()
        return get_config(db)
    finally:
        if own_session:
            db.close()


def list_policies(db=None) -> list:
    """列出所有策略。"""
    own_session = False
    if db is None:
        db = get_session_for(get_db_mode())()
        own_session = True
    try:
        rows = db.query(SandboxPolicy).order_by(SandboxPolicy.id).all()
        return [_policy_to_dict(p) for p in rows]
    finally:
        if own_session:
            db.close()


def _policy_to_dict(p: SandboxPolicy) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "scope_type": p.scope_type,
        "scope_id": p.scope_id,
        "allowed_asset_ids": p.get_allowed_asset_ids(),
        "blocked_asset_ids": p.get_blocked_asset_ids(),
        "allowed_tools": p.get_allowed_tools(),
        "blocked_tools": p.get_blocked_tools(),
        "allowed_commands": p.get_allowed_commands(),
        "blocked_commands": p.get_blocked_commands(),
        "max_risk_level": p.max_risk_level,
        "max_actions_per_day": p.max_actions_per_day,
        "require_second_approval": p.require_second_approval,
        "is_enabled": p.is_enabled,
        "created_at": p.created_at.isoformat() if p.created_at else "",
        "updated_at": p.updated_at.isoformat() if p.updated_at else "",
    }


def create_policy(data: dict, db=None) -> dict:
    own_session = False
    if db is None:
        db = get_session_for(get_db_mode())()
        own_session = True
    try:
        p = SandboxPolicy(
            name=str(data.get("name", "")).strip() or "未命名策略",
            description=str(data.get("description", "")),
            scope_type=str(data.get("scope_type", "global")),
            scope_id=int(data.get("scope_id", 0) or 0),
            allowed_asset_ids=json.dumps(data.get("allowed_asset_ids", []), ensure_ascii=False),
            blocked_asset_ids=json.dumps(data.get("blocked_asset_ids", []), ensure_ascii=False),
            allowed_tools=json.dumps(data.get("allowed_tools", []), ensure_ascii=False),
            blocked_tools=json.dumps(data.get("blocked_tools", []), ensure_ascii=False),
            allowed_commands=json.dumps(data.get("allowed_commands", []), ensure_ascii=False),
            blocked_commands=json.dumps(data.get("blocked_commands", []), ensure_ascii=False),
            max_risk_level=str(data.get("max_risk_level", "critical")),
            max_actions_per_day=int(data.get("max_actions_per_day", 0) or 0),
            require_second_approval=bool(data.get("require_second_approval", False)),
            is_enabled=bool(data.get("is_enabled", True)),
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        return _policy_to_dict(p)
    finally:
        if own_session:
            db.close()


def update_policy(policy_id: int, data: dict, db=None) -> dict:
    own_session = False
    if db is None:
        db = get_session_for(get_db_mode())()
        own_session = True
    try:
        p = db.query(SandboxPolicy).filter(SandboxPolicy.id == policy_id).first()
        if not p:
            return None
        if "name" in data:
            p.name = str(data["name"]).strip() or p.name
        if "description" in data:
            p.description = str(data["description"])
        if "scope_type" in data:
            p.scope_type = str(data["scope_type"])
        if "scope_id" in data:
            p.scope_id = int(data["scope_id"] or 0)
        _set_json_field(p, "allowed_asset_ids", data)
        _set_json_field(p, "blocked_asset_ids", data)
        _set_json_field(p, "allowed_tools", data)
        _set_json_field(p, "blocked_tools", data)
        _set_json_field(p, "allowed_commands", data)
        _set_json_field(p, "blocked_commands", data)
        if "max_risk_level" in data and data["max_risk_level"] in RISK_ORDER:
            p.max_risk_level = data["max_risk_level"]
        if "max_actions_per_day" in data:
            p.max_actions_per_day = int(data["max_actions_per_day"] or 0)
        if "require_second_approval" in data:
            p.require_second_approval = bool(data["require_second_approval"])
        if "is_enabled" in data:
            p.is_enabled = bool(data["is_enabled"])
        db.commit()
        db.refresh(p)
        return _policy_to_dict(p)
    finally:
        if own_session:
            db.close()


def _set_json_field(policy, field, data):
    if field in data:
        try:
            val = json.dumps(data[field] if data[field] else [], ensure_ascii=False)
        except Exception:
            val = "[]"
        setattr(policy, field, val)


def delete_policy(policy_id: int, db=None) -> bool:
    own_session = False
    if db is None:
        db = get_session_for(get_db_mode())()
        own_session = True
    try:
        p = db.query(SandboxPolicy).filter(SandboxPolicy.id == policy_id).first()
        if not p:
            return False
        db.delete(p)
        db.commit()
        return True
    finally:
        if own_session:
            db.close()


def evaluate_request(
    action_type: str,
    tool_name: str,
    asset_id: int,
    command: str,
    risk_level: str,
    session_id: int = 0,
    user_id: int = 0,
    role_id: int = 0,
    db=None,
) -> dict:
    """对一个动作请求做沙盒决策。

    返回：
      {"decision": "allowed"/"rejected"/"dry_run", "reason": "...", "mode": "live"/"dry_run",
       "policy_id": int, "second_approval": bool}
    """
    own_session = False
    if db is None:
        db = get_session_for(get_db_mode())()
        own_session = True
    try:
        cfg = _ensure_config(db)
        result = {
            "decision": "allowed",
            "reason": "ok",
            "mode": "live",
            "policy_id": 0,
            "second_approval": False,
        }

        # 1. 全局开关关闭 → 直接放行（沙盒不影响现有功能）
        if not cfg.is_enabled:
            return result

        # 2. 干运行模式
        if cfg.dry_run_mode:
            result["decision"] = "dry_run"
            result["mode"] = "dry_run"
            result["reason"] = "全局干运行模式：仅记录不执行"

        # 3. 匹配策略（session > user > role > global）
        policy = _match_policy(db, session_id, user_id, role_id)

        # 4. 黑名单检查（优先级最高）
        if policy:
            blocked_assets = policy.get_blocked_asset_ids()
            if blocked_assets and asset_id in blocked_assets:
                return _reject(result, "资产在策略黑名单中", policy.id)
            blocked_tools = policy.get_blocked_tools()
            if blocked_tools and tool_name in blocked_tools:
                return _reject(result, f"工具 {tool_name} 在策略黑名单中", policy.id)
            blocked_cmds = policy.get_blocked_commands()
            if command and blocked_cmds:
                for pat in blocked_cmds:
                    try:
                        if re.search(pat, command):
                            return _reject(result, f"命令命中黑名单规则: {pat}", policy.id)
                    except re.error:
                        if pat in command:
                            return _reject(result, f"命令命中黑名单规则: {pat}", policy.id)

        # 5. 白名单检查
        if policy:
            allowed_assets = policy.get_allowed_asset_ids()
            if allowed_assets and asset_id and asset_id not in allowed_assets:
                return _reject(result, "资产不在策略白名单中", policy.id)
            allowed_tools = policy.get_allowed_tools()
            if allowed_tools and tool_name and tool_name not in allowed_tools:
                return _reject(result, f"工具 {tool_name} 不在策略白名单中", policy.id)
            allowed_cmds = policy.get_allowed_commands()
            if allowed_cmds and command:
                ok = any(command.strip().startswith(c) for c in allowed_cmds)
                if not ok:
                    return _reject(result, "命令不在策略白名单中", policy.id)

        # 6. 风险等级检查（取全局与策略中更严格者）
        effective_max = cfg.max_risk_level
        if policy and policy.max_risk_level:
            effective_max = _stricter(effective_max, policy.max_risk_level)
        if risk_level and _risk_gt(risk_level, effective_max):
            return _reject(result, f"风险等级 {risk_level} 超过允许上限 {effective_max}", policy.id if policy else 0)

        # 7. 二级审批标记
        if policy and policy.require_second_approval and risk_level in ("high", "critical"):
            result["second_approval"] = True

        # 8. 执行窗口检查（写操作）
        if risk_level in ("medium", "high", "critical"):
            win_ok = _window_allowed(cfg.execution_window_start, cfg.execution_window_end)
            if not win_ok:
                return _reject(
                    result,
                    f"当前不在执行窗口内（{cfg.execution_window_start}-{cfg.execution_window_end}）",
                    policy.id if policy else 0,
                )

        if policy:
            result["policy_id"] = policy.id
        return result
    finally:
        if own_session:
            db.close()


def _match_policy(db, session_id, user_id, role_id):
    """按作用范围匹配最具体策略。"""
    enabled = db.query(SandboxPolicy).filter(SandboxPolicy.is_enabled == True)
    if session_id:
        p = enabled.filter(SandboxPolicy.scope_type == "session", SandboxPolicy.scope_id == session_id).first()
        if p:
            return p
    if user_id:
        p = enabled.filter(SandboxPolicy.scope_type == "user", SandboxPolicy.scope_id == user_id).first()
        if p:
            return p
    if role_id:
        p = enabled.filter(SandboxPolicy.scope_type == "role", SandboxPolicy.scope_id == role_id).first()
        if p:
            return p
    return enabled.filter(SandboxPolicy.scope_type == "global").first()


def _reject(result, reason, policy_id):
    result["decision"] = "rejected"
    result["reason"] = reason
    result["policy_id"] = policy_id
    return result


def _risk_gt(a, b):
    """判断风险 a 是否高于 b。"""
    na = RISK_ORDER.index(a) if a in RISK_ORDER else -1
    nb = RISK_ORDER.index(b) if b in RISK_ORDER else -1
    return na > nb


def _stricter(a, b):
    """返回更严格（更高）的风险等级。"""
    if _risk_gt(a, b):
        return a
    return b


def _window_allowed(start, end):
    """执行窗口检查。start/end 为空则不限。"""
    if not start or not end:
        return True
    try:
        now = datetime.now().time()
        s = datetime.strptime(start, "%H:%M").time()
        e = datetime.strptime(end, "%H:%M").time()
        if s <= e:
            return s <= now <= e
        # 跨天窗口（如 22:00 - 06:00）
        return now >= s or now <= e
    except Exception:
        return True


def log_execution(
    action_type, tool_name, asset_id, risk_level, mode, payload,
    decision, reject_reason="", approved_by=0, session_id=0, db=None,
):
    """记录沙盒执行日志。"""
    own_session = False
    if db is None:
        db = get_session_for(get_db_mode())()
        own_session = True
    try:
        log = SandboxExecutionLog(
            session_id=int(session_id or 0),
            action_type=str(action_type or ""),
            tool_name=str(tool_name or ""),
            asset_id=int(asset_id or 0),
            risk_level=str(risk_level or "medium"),
            mode=str(mode or "live"),
            payload=json.dumps(payload, ensure_ascii=False) if payload else "{}",
            decision=str(decision or "allowed"),
            reject_reason=str(reject_reason or ""),
            approved_by=int(approved_by or 0),
        )
        db.add(log)
        db.commit()
        return log.id
    finally:
        if own_session:
            db.close()


def list_execution_logs(limit=100, db=None) -> list:
    own_session = False
    if db is None:
        db = get_session_for(get_db_mode())()
        own_session = True
    try:
        rows = (
            db.query(SandboxExecutionLog)
            .order_by(SandboxExecutionLog.created_at.desc())
            .limit(min(int(limit), 500))
            .all()
        )
        return [_log_to_dict(l) for l in rows]
    finally:
        if own_session:
            db.close()


def _log_to_dict(l: SandboxExecutionLog) -> dict:
    return {
        "id": l.id,
        "session_id": l.session_id,
        "action_type": l.action_type,
        "tool_name": l.tool_name,
        "asset_id": l.asset_id,
        "risk_level": l.risk_level,
        "mode": l.mode,
        "payload": l.payload,
        "decision": l.decision,
        "reject_reason": l.reject_reason,
        "approved_by": l.approved_by,
        "created_at": l.created_at.isoformat() if l.created_at else "",
    }