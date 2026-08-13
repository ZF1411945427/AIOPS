"""log_rca / idice 实装(P3-2) - 复用现有数据(log_anomaly / MetricRecord / Asset 关系)。

log_rca: 对给定资产/时间窗的日志级证据做根因分析, 产出错误模式 + 假设 + 建议。
idice:  简化 iDICE(incidence-Differential Influence & Conditional Explanation)
        因果归因: 用相关指标相对基线的偏离 + 与"结果指标"的相关性, 归因高风险根因指标。
契约: CONTRACT.md(P3-2)。无真实日志源时基于 asset 关联 + 指标, 仍返回结构化结论。
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models import Asset, AssetRelation, MetricRecord


def _asset_metrics(db: Session, asset_id: int, hours: float = 24, limit: int = 2000) -> Dict[str, List[float]]:
    since = datetime.now() - timedelta(hours=hours)
    rows = db.query(MetricRecord).filter(
        MetricRecord.asset_id == asset_id,
        MetricRecord.timestamp >= since,
    ).order_by(MetricRecord.timestamp).limit(limit).all()
    out: Dict[str, List[float]] = {}
    for r in rows:
        out.setdefault(r.name, []).append(float(r.value) if r.value is not None else 0.0)
    return out


def _baseline(values: List[float]):
    if not values:
        return 0.0, 0.0, 0.0
    n = len(values)
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n if n > 1 else 0.0
    return mean, var ** 0.5, n


def run_log_rca(db: Session, asset_id: int, hours: float = 24, keyword: str = "") -> Dict[str, Any]:
    """日志根因分析: 基于指标异常 + 资产关系推断可能根因(日志源不足时给出指标证据链)。"""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return {"ok": False, "error": "资产不存在"}
    metrics = _asset_metrics(db, asset_id, hours)
    anomalies = []
    for name, vals in metrics.items():
        if len(vals) < 5:
            continue
        mean, std, n = _baseline(vals)
        last = vals[-1]
        if std == 0:
            continue
        z = abs(last - mean) / std
        if z >= 2.0:
            anomalies.append({"metric": name, "latest": round(last, 2),
                              "baseline": round(mean, 2), "z_score": round(z, 2),
                              "lift": round((last - mean) / (std + 1e-9), 2)})
    anomalies.sort(key=lambda x: x["z_score"], reverse=True)
    related = db.query(AssetRelation).filter(
        (AssetRelation.parent_id == asset_id) | (AssetRelation.child_id == asset_id)).all()
    neighbors = []
    for rel in related:
        other_id = rel.child_id if rel.parent_id == asset_id else rel.parent_id
        n_asset = db.query(Asset).filter(Asset.id == other_id).first()
        if n_asset:
            neighbors.append({"asset_id": n_asset.id, "name": n_asset.name,
                              "relation": getattr(rel, "relation_type", "") or ""})
    # 假设
    hypotheses = []
    for a in anomalies[:3]:
        hypotheses.append(
            f"{a['metric']} 偏离基线 {a['lift']}σ(z={a['z_score']}),可能为根因指标"
        )
    if not hypotheses:
        hypotheses.append("未发现显著指标偏离, 需进一步检查日志/进程")
    return {
        "ok": True,
        "asset": {"id": asset.id, "name": asset.name, "ip": asset.ip},
        "window_hours": hours,
        "keyword": keyword,
        "anomaly_metrics": anomalies,
        "related_assets": neighbors,
        "root_cause_hypotheses": hypotheses,
        "recommendations": [
            "查看最近日志中的 ERROR/WARN 模式(可用知识库 log-troubleshooter 技能)",
            "关联检查邻居资产的同指标是否同步异常(递归定位)",
        ],
        "generated_at": datetime.now().isoformat(),
    }


def run_idice(db: Session, asset_id: int, target_metric: str, hours: float = 24) -> Dict[str, Any]:
    """iDICE 因果归因: 对目标指标, 计算各候选指标的相关性(相对基线的共同偏离)排序归因。"""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return {"ok": False, "error": "资产不存在"}
    metrics = _asset_metrics(db, asset_id, hours)
    if target_metric not in metrics:
        # 默认取最后一个指标当目标
        target_metric = next(iter(metrics), "")
    if not target_metric:
        return {"ok": False, "error": "无指标数据"}
    target = metrics[target_metric]
    if len(target) < 5:
        return {"ok": True, "asset": {"id": asset.id, "name": asset.name},
                "target_metric": target_metric, "message": "目标指标样本不足, 无法归因",
                "attributions": []}
    t_mean = sum(target) / len(target)
    t_dev = [(v - t_mean) for v in target]
    influences = []
    for name, vals in metrics.items():
        if name == target_metric or len(vals) != len(target):
            continue
        m = sum(vals) / len(vals)
        # 皮尔逊相关 vs 目标偏离
        dev = [v - m for v in vals]
        num = sum(a * b for a, b in zip(t_dev, dev))
        den = (sum(a * a for a in t_dev) ** 0.5) * (sum(b * b for b in dev) ** 0.5) + 1e-9
        corr = num / den
        if abs(corr) < 0.3:
            continue
        last = vals[-1]
        influence = corr * (last - m)
        influences.append({"metric": name, "correlation": round(corr, 3),
                           "influence_score": round(influence, 3),
                           "latest": round(last, 2), "baseline": round(m, 2)})
    influences.sort(key=lambda x: abs(x["influence_score"]), reverse=True)
    return {
        "ok": True,
        "asset": {"id": asset.id, "name": asset.name, "ip": asset.ip},
        "target_metric": target_metric,
        "window_hours": hours,
        "attributions": influences[:10],
        "conclusion": (f"最高相关因果指标: {influences[0]['metric']} (相关 {influences[0]['correlation']})"
                       if influences else "未发现显著相关因果指标"),
    }
