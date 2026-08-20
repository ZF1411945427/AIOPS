"""log_rca / idice / granger 实装 - 复用现有数据(log_anomaly / MetricRecord / Asset 关系)。

log_rca: 对给定资产/时间窗的日志级证据做根因分析, 产出错误模式 + 假设 + 建议。
idice:  iDICE(incidence-Differential Influence & Conditional Explanation)因果归因的
        真实实现 v1: 按条件影响(协变偏离 × 目标偏离的相关贡献)归因高风险根因指标。
granger: 真实 Granger 因果检验(基于 statsmodels.grangercausalitytests), 双向检验
        A 是否 Granger 引起 B / B 是否 Granger 引起 A。
契约: CONTRACT.md(P3-2)。无真实日志源时基于 asset 关联 + 指标, 仍返回结构化结论。
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List
from app.routers.agent_sse import _clean_key_point


def _build_log_rca_key_points(asset, anomalies, hypotheses, recommendations) -> dict:
    """从日志 RCA 结果组装统一三要素要点(根因/方案/影响)。"""
    if hypotheses:
        root_cause = hypotheses[0]
    else:
        root_cause = "未发现显著指标偏离，需进一步检查日志/进程"
    solution = "；".join([str(r) for r in recommendations[:2]]) if recommendations else "结合日志定位根因并处置"
    if asset:
        impact = f"资产 {asset['name']}（IP {asset['ip']}），检测到 {len(anomalies)} 个异常指标"
    else:
        impact = f"检测到 {len(anomalies)} 个异常指标"
    return {
        "root_cause": _clean_key_point(root_cause, 100),
        "solution": _clean_key_point(solution, 160),
        "impact": _clean_key_point(impact, 100),
    }

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
        "summary_block": _build_log_rca_key_points(
            {"id": asset.id, "name": asset.name, "ip": asset.ip},
            anomalies, hypotheses, [
                "查看最近日志中的 ERROR/WARN 模式(可用知识库 log-troubleshooter 技能)",
                "关联检查邻居资产的同指标是否同步异常(递归定位)",
            ],
        ),
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
        "method": "idice-v1: target-correlated-influence",
        "note": "v1 以协变偏离 × 目标偏离的相关贡献做归因，结果属『伴随/相关』证据而非经过控制的因果结论",
        "attributions": influences[:10],
        "conclusion": (f"最高相关归因指标: {influences[0]['metric']} (相关 {influences[0]['correlation']})"
                       if influences else "未发现显著相关归因指标"),
    }


def _asset_metric_series(db: Session, asset_id: int, metric_name: str,
                         hours: float = 24, limit: int = 5000) -> List[dict]:
    """按时间升序返回指定资产单个指标的时间序列 [{timestamp, value}]。"""
    since = datetime.now() - timedelta(hours=hours)
    rows = (
        db.query(MetricRecord)
        .filter(MetricRecord.asset_id == asset_id,
                MetricRecord.name == metric_name,
                MetricRecord.timestamp >= since)
        .order_by(MetricRecord.timestamp)
        .limit(limit)
        .all()
    )
    out: List[dict] = []
    for r in rows:
        v = float(r.value) if r.value is not None else None
        if v is None:
            continue
        ts = r.timestamp
        if hasattr(ts, "replace"):
            ts = ts.replace(tzinfo=None)
        out.append({"timestamp": ts, "value": v})
    return out


def _align_series(series_a: List[dict], series_b: List[dict]) -> tuple:
    """按时间戳交集对齐两条序列，返回 (x, y) 两个等长 list。"""
    ts_a = {}
    for p in series_a:
        ts_a.setdefault(p["timestamp"], p["value"])  # 同时间戳取首个
    ts_b = {}
    for p in series_b:
        ts_b.setdefault(p["timestamp"], p["value"])
    common = sorted(set(ts_a.keys()) & set(ts_b.keys()))
    if not common:
        return [], []
    x = [ts_a[t] for t in common]
    y = [ts_b[t] for t in common]
    return x, y


def run_granger(db: Session, asset_id: int, metric_a: str, metric_b: str,
                hours: float = 24, maxlag: int = 3) -> Dict[str, Any]:
    """真实 Granger 因果检验（statsmodels）。

    双向检验:
      - a→b: 用 a 的历史是否显著提升对 b 的预测(拒绝 H0 即 a Granger 引起 b)
      - b→a: 反向
    对齐策略: 按时间戳交集对齐两条指标序列。
    """
    import numpy as np

    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return {"ok": False, "error": "资产不存在"}

    series_a = _asset_metric_series(db, asset_id, metric_a, hours=hours)
    series_b = _asset_metric_series(db, asset_id, metric_b, hours=hours)
    if len(series_a) < maxlag * 2 + 2 or len(series_b) < maxlag * 2 + 2:
        return {
            "ok": False,
            "error": f"样本不足: {metric_a}={len(series_a)}点, {metric_b}={len(series_b)}点, "
                     f"需至少 {maxlag * 2 + 2} 点",
            "asset": {"id": asset.id, "name": asset.name, "ip": asset.ip},
            "metric_a": metric_a, "metric_b": metric_b,
            "window_hours": hours,
        }

    try:
        from statsmodels.tsa.stattools import grangercausalitytests as _gct
    except Exception as _e:  # pragma: no cover - 依赖缺失兜底
        return {
            "ok": False, "error": f"statsmodels 不可用: {_e}",
            "asset": {"id": asset.id, "name": asset.name, "ip": asset.ip},
            "metric_a": metric_a, "metric_b": metric_b,
        }

    # 方向 1: metric_a 的历史能否预测 metric_b (a → b)
    x_ab, y_ab = _align_series(series_a, series_b)
    # 方向 2: metric_b 的历史能否预测 metric_a (b → a) —— 同一对齐结果, 两列对调

    directions = []

    def _test(col_resp: List[float], col_cause: List[float], label: str) -> dict:
        # gct 语义: 列0=响应(y), 列1=原因(x), 检验 x 是否 Granger 引起 y
        data = np.column_stack([col_resp, col_cause])
        if len(data) < maxlag * 2 + 2:
            return {"pair": label, "ok": False, "reason": "对齐后样本不足"}
        try:
            # verbose 在未来版本移除, 这里抑制 deprecation 警告
            import warnings as _w
            with _w.catch_warnings():
                _w.simplefilter("ignore")
                res = _gct(data, maxlag=maxlag, verbose=False)
        except Exception as e:
            return {"pair": label, "ok": False, "reason": f"计算失败: {e}"}
        lags = []
        best_lag, best_p = None, None
        for lag, item in res.items():
            # statsmodels≥0.13: res[lag] = (test_dict, supplemental)；兼容旧格式
            d = item[0] if isinstance(item, tuple) else item
            ftest = d.get("ssr_ftest")
            if not ftest or len(ftest) < 2:
                continue
            f_val, p_val = float(ftest[0]), float(ftest[1])
            significant = bool(p_val < 0.05)
            lags.append({
                "lag": int(lag), "f_stat": round(f_val, 4),
                "p_value": round(p_val, 4), "significant_95": significant,
            })
            if best_p is None or p_val < best_p:
                best_p, best_lag = p_val, lag
        return {
            "pair": label,
            "ok": True,
            "lags": lags,
            "best_lag": int(best_lag) if best_lag is not None else None,
            "best_p_value": round(best_p, 4) if best_p is not None else None,
            "significant_95": bool(best_p is not None and best_p < 0.05),
        }

    # gct(data) 检验 data[:,1] 是否 Granger 引起 data[:,0]。
    # 故: a→b ⇒ data=[b(响应), a(原因)]; b→a ⇒ data=[a(响应), b(原因)]。
    directions.append(_test(y_ab, x_ab, f"{metric_a}→{metric_b}"))
    directions.append(_test(x_ab, y_ab, f"{metric_b}→{metric_a}"))

    # 结论: 若有双向显著, 提示可能存在共同驱动或反馈, 需谨慎解释
    dir_a_to_b = next((d for d in directions if d["pair"] == f"{metric_a}→{metric_b}"), {})
    dir_b_to_a = next((d for d in directions if d["pair"] == f"{metric_b}→{metric_a}"), {})
    a2b_sig = dir_a_to_b.get("ok") and dir_a_to_b.get("significant_95")
    b2a_sig = dir_b_to_a.get("ok") and dir_b_to_a.get("significant_95")
    if a2b_sig and b2a_sig:
        conclusion = f"双向 Granger 因果均显著(p<0.05)，可能存在共同驱动因素或反馈环，需结合领域知识判断"
    elif a2b_sig:
        conclusion = f"在 α=0.05 下，{metric_a} 的历史对 {metric_b} 有 Granger 因果预测力"
    elif b2a_sig:
        conclusion = f"在 α=0.05 下，{metric_b} 的历史对 {metric_a} 有 Granger 因果预测力"
    else:
        conclusion = "两方向均未见显著(p<0.05)的 Granger 因果预测力"

    return {
        "ok": True,
        "asset": {"id": asset.id, "name": asset.name, "ip": asset.ip},
        "metric_a": metric_a,
        "metric_b": metric_b,
        "window_hours": hours,
        "maxlag": maxlag,
        "method": "granger-causality (statsmodels ssr_ftest)",
        "aligned_points": len(x_ab),
        "directions": directions,
        "summary_block": {
            "root_cause": _clean_key_point(conclusion, 100),
        },
        "conclusion": conclusion,
    }
