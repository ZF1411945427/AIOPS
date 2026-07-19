import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import ABTestConfig, ABTestRecord, AIProvider

logger = logging.getLogger(__name__)

# 字段白名单：只允许这些字段进入 ABTestConfig 构造/更新
_ALLOWED_FIELDS = {
    "name", "provider_a_id", "provider_b_id",
    "model_a", "model_b", "split_ratio", "metric", "status",
}


def create_test(db: Session, data: dict) -> int:
    """创建 A/B 测试配置。data 必须经过白名单过滤。"""
    clean = {k: v for k, v in data.items() if k in _ALLOWED_FIELDS}
    cfg = ABTestConfig(**clean)
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg.id


def list_tests(db: Session, status: str = "") -> list:
    q = db.query(ABTestConfig)
    if status:
        q = q.filter(ABTestConfig.status == status)
    return q.order_by(ABTestConfig.created_at.desc()).all()


def get_test(test_id: int, db: Session):
    return db.query(ABTestConfig).filter(ABTestConfig.id == test_id).first()


def update_test(test_id: int, data: dict, db: Session):
    cfg = get_test(test_id, db)
    if not cfg:
        return None
    clean = {k: v for k, v in data.items() if k in _ALLOWED_FIELDS}
    # 启动（status=active）时：自动停止其他 active 实验，保证全局只有 1 个 active
    if clean.get("status") == "active":
        _pause_other_active(db, exclude_id=test_id)
        # 启动时刷新 model_a / model_b（provider.default_model 可能已变）
        _sync_models(cfg, clean, db)
    for k, v in clean.items():
        setattr(cfg, k, v)
    cfg.updated_at = datetime.now()
    db.commit()
    return cfg


def _pause_other_active(db: Session, exclude_id: int):
    """启动新实验前，把其他 active 实验置为 stopped，避免多 active 共存导致分流冲突。"""
    others = db.query(ABTestConfig).filter(
        ABTestConfig.status == "active",
        ABTestConfig.id != exclude_id,
    ).all()
    for o in others:
        o.status = "stopped"
        o.updated_at = datetime.now()
    if others:
        db.flush()


def _sync_models(cfg: ABTestConfig, clean: dict, db: Session):
    """启动时根据 provider_a_id / provider_b_id 自动填充 model_a / model_b。"""
    pa_id = clean.get("provider_a_id", cfg.provider_a_id)
    pb_id = clean.get("provider_b_id", cfg.provider_b_id)
    if pa_id:
        pa = db.query(AIProvider).filter(AIProvider.id == pa_id).first()
        if pa:
            clean["model_a"] = pa.default_model or ""
    if pb_id:
        pb = db.query(AIProvider).filter(AIProvider.id == pb_id).first()
        if pb:
            clean["model_b"] = pb.default_model or ""


def get_provider_for_request(test_id: int, session_id: int = None, db: Session = None) -> tuple:
    """根据 A/B 测试配置决定走哪个 provider。返回 (provider_id, group, test_config)

    健壮性：若分流到的 provider_id 为 NULL（用户配错或脏数据），返回 None,
    让上层 agent_service 走默认 provider fallback, 避免查 NULL 永远查不到导致无 provider.
    """
    cfg = db.query(ABTestConfig).filter(
        ABTestConfig.id == test_id,
        ABTestConfig.status == "active"
    ).first()
    if not cfg:
        return None, None, None

    h = _stable_bucket(test_id, session_id)
    try:
        ratio_a = int(cfg.split_ratio.split("/")[0])
    except (ValueError, IndexError, AttributeError):
        ratio_a = 50
    group = "a" if h < ratio_a else "b"

    provider_id = cfg.provider_a_id if group == "a" else cfg.provider_b_id
    if not provider_id:
        return None, None, cfg
    return provider_id, group, cfg


def _stable_bucket(test_id: int, session_id: int = None) -> int:
    """稳定的 0-99 分流桶：同一 (test_id, session_id) 永远命中同一组。

    注：此处 md5 仅用于确定性分桶（非安全场景），显式声明 usedforsecurity=False
    以通过 SAST 扫描（bandit B324）。
    """
    import hashlib
    h = hashlib.md5(f"{test_id}:{session_id or ''}".encode(), usedforsecurity=False).hexdigest()
    return int(h[:8], 16) % 100


def record_result(
    db: Session,
    test_id: int,
    session_id: int = None,
    group: str = "a",
    provider_id: int = None,
    model_name: str = "",
    latency_ms: int = 0,
    token_count: int = 0,
    success: bool = True,
    user_feedback: str = "",
) -> int:
    rec = ABTestRecord(
        test_id=test_id,
        session_id=session_id,
        group=group,
        provider_id=provider_id,
        model_name=model_name,
        latency_ms=latency_ms,
        token_count=token_count,
        is_success=success,
        user_feedback=user_feedback,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec.id


def get_test_results(test_id: int, db: Session) -> dict:
    records = db.query(ABTestRecord).filter(ABTestRecord.test_id == test_id).all()
    if not records:
        return {"total": 0, "group_a": {}, "group_b": {}, "winner": "insufficient_data", "metric": None}

    a_records = [r for r in records if r.group == "a"]
    b_records = [r for r in records if r.group == "b"]

    cfg = db.query(ABTestConfig).filter(ABTestConfig.id == test_id).first()
    metric = cfg.metric if cfg else "latency"

    def summarize(recs):
        if not recs:
            return {}
        total = len(recs)
        successes = sum(1 for r in recs if r.is_success)
        latencies = [r.latency_ms for r in recs if r.latency_ms]
        tokens = [r.token_count for r in recs if r.token_count]
        return {
            "total": total,
            "is_success": successes,
            "success_rate": round(successes / max(total, 1) * 100, 1),
            "avg_latency_ms": round(sum(latencies) / max(len(latencies), 1), 1) if latencies else 0,
            "avg_tokens": round(sum(tokens) / max(len(tokens), 1), 1) if tokens else 0,
        }

    a_sum = summarize(a_records)
    b_sum = summarize(b_records)
    return {
        "total": len(records),
        "group_a": a_sum,
        "group_b": b_sum,
        "winner": _compare(a_sum, b_sum, metric),
        "metric": metric,
    }


def _compare(a: dict, b: dict, metric: str = "latency") -> str:
    """根据评估指标判定胜出组。

    metric 取值：
    - latency:  延迟优先（avg_latency_ms 越低越好）
    - accuracy: 仅看 success_rate
    - success:  success_rate 优先，延迟做次要参考
    """
    if not a or not b:
        return "insufficient_data"
    sr_a = a.get("success_rate", 0)
    sr_b = b.get("success_rate", 0)
    lat_a = a.get("avg_latency_ms", 0) or 0
    lat_b = b.get("avg_latency_ms", 0) or 0

    if metric == "latency":
        # 延迟差异 > 100ms 才认为有显著差异，否则看成功率
        if abs(lat_a - lat_b) > 100:
            return "a" if lat_a < lat_b else "b"
        if abs(sr_a - sr_b) > 5:
            return "a" if sr_a > sr_b else "b"
        return "inconclusive"

    if metric == "accuracy":
        if abs(sr_a - sr_b) > 5:
            return "a" if sr_a > sr_b else "b"
        return "inconclusive"

    # success: 综合分 = success_rate - latency/1000
    a_score = sr_a - lat_a / 1000
    b_score = sr_b - lat_b / 1000
    if a_score > b_score + 5:
        return "a"
    if b_score > a_score + 5:
        return "b"
    return "inconclusive"


def delete_test(test_id: int, db: Session) -> bool:
    """删除实验配置及关联记录。"""
    cfg = get_test(test_id, db)
    if not cfg:
        return False
    db.query(ABTestRecord).filter(ABTestRecord.test_id == test_id).delete()
    db.query(ABTestConfig).filter(ABTestConfig.id == test_id).delete()
    db.commit()
    return True
