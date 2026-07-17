import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, Integer, Float
from app.models import AnomalyBenchmark, Asset, MetricRecord


_ALGORITHM_META = {
    "sigma":        {"name": "3σ (Z-Score)",  "best_for": "平稳指标，异常点稀疏",   "strength": 0.9},
    "ewma":         {"name": "EWMA",          "best_for": "波动性指标，趋势跟踪",   "strength": 0.85},
    "mad":          {"name": "MAD",           "best_for": "有噪声的指标，抗干扰",   "strength": 0.8},
    "stl":          {"name": "STL 分解",       "best_for": "有周期性/季节性指标",   "strength": 0.88},
    "prophet":      {"name": "Prophet",       "best_for": "业务类时序，有周期和趋势", "strength": 0.9},
    "lstm":         {"name": "LSTM",          "best_for": "复杂非线性时序",         "strength": 0.85},
    "transformer":   {"name": "Transformer",   "best_for": "高维复杂时序，多指标联合", "strength": 0.82},
}


def record_benchmark(
    db: Session,
    asset_id: int = None,
    metric_name: str = "",
    algorithm: str = "",
    window_minutes: int = 60,
    precision: float = 0.0,
    recall: float = 0.0,
    f1_score: float = 0.0,
    threshold: float = 0.0,
) -> int:
    bench = AnomalyBenchmark(
        asset_id=asset_id,
        metric_name=metric_name,
        algorithm=algorithm,
        window_minutes=window_minutes,
        precision=precision,
        recall=recall,
        f1_score=f1_score,
        threshold=threshold,
    )
    db.add(bench)
    db.commit()
    db.refresh(bench)
    return bench.id


def get_benchmarks(db: Session, algorithm: str = "", page: int = 1, per_page: int = 20):
    q = db.query(AnomalyBenchmark)
    if algorithm:
        q = q.filter(AnomalyBenchmark.algorithm == algorithm)
    q = q.order_by(AnomalyBenchmark.created_at.desc())
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return items, total


def get_benchmark_stats(db: Session, days: int = 90) -> dict:
    since = datetime.now() - timedelta(days=days)
    records = db.query(AnomalyBenchmark).filter(AnomalyBenchmark.created_at >= since).all()

    by_algorithm = {}
    for r in records:
        alg = r.algorithm or "unknown"
        if alg not in by_algorithm:
            by_algorithm[alg] = {"count": 0, "precision": 0, "recall": 0, "f1": 0}
        by_algorithm[alg]["count"] += 1
        by_algorithm[alg]["precision"] += r.precision or 0
        by_algorithm[alg]["recall"] += r.recall or 0
        by_algorithm[alg]["f1"] += r.f1_score or 0

    summary = []
    for alg, vals in by_algorithm.items():
        cnt = vals["count"]
        summary.append({
            "algorithm": alg,
            "count": cnt,
            "avg_precision": round(vals["precision"] / cnt, 3) if cnt else 0,
            "avg_recall": round(vals["recall"] / cnt, 3) if cnt else 0,
            "avg_f1": round(vals["f1"] / cnt, 3) if cnt else 0,
        })
    summary.sort(key=lambda x: x["avg_f1"], reverse=True)

    best_algorithm = summary[0]["algorithm"] if summary else ""

    return {
        "total_records": len(records),
        "period_days": days,
        "best_algorithm": best_algorithm,
        "by_algorithm": summary,
    }


def _recommend_by_metric特征(metric_name: str, db: Session) -> dict:
    name_lower = (metric_name or "").lower()

    if any(k in name_lower for k in ["cpu", "mem", "memory", "disk", "io", "load"]):
        if "cpu" in name_lower:
            return {"recommended": "mad", "reason": "CPU 使用率常受噪声干扰，MAD（中位数绝对偏差）抗噪声能力强", "confidence": "high", "method": "特征匹配"}
        if "mem" in name_lower or "memory" in name_lower:
            return {"recommended": "ewma", "reason": "内存使用有连续性，EWMA 指数加权能捕捉渐变趋势", "confidence": "high", "method": "特征匹配"}
        if "disk" in name_lower or "io" in name_lower:
            return {"recommended": "sigma", "reason": "磁盘 I/O 相对平稳，3σ 对稀疏异常敏感", "confidence": "medium", "method": "特征匹配"}
        return {"recommended": "mad", "reason": "系统资源类指标，MAD 最鲁棒", "confidence": "high", "method": "特征匹配"}

    if any(k in name_lower for k in ["latency", "delay", "rt", "response", "p99", "p95"]):
        return {"recommended": "mad", "reason": "延迟类指标分布通常偏态，MAD 对偏态数据更鲁棒", "confidence": "high", "method": "特征匹配"}

    if any(k in name_lower for k in ["error", "fail", "exception", "5xx", "4xx", "reject"]):
        return {"recommended": "isolation_forest", "reason": "错误类指标为稀疏事件，Isolation Forest 对低频异常最敏感", "confidence": "high", "method": "特征匹配"}

    if any(k in name_lower for k in ["qps", "throughput", "tps", "count", "request", "req"]):
        return {"recommended": "stl", "reason": "吞吐类指标常有周期性波动，STL 分解可分离趋势和周期", "confidence": "high", "method": "特征匹配"}

    if any(k in name_lower for k in ["order", "revenue", "sale", "gmv", "user", "在线"]):
        return {"recommended": "prophet", "reason": "业务指标常有日/周周期，Prophet 对业务时序效果最好", "confidence": "high", "method": "特征匹配"}

    if any(k in name_lower for k in ["temp", "温度"]):
        return {"recommended": "sigma", "reason": "温度变化相对连续平稳，3σ 足以捕捉突变", "confidence": "medium", "method": "特征匹配"}

    rec = _analyze_metric_sample(db, metric_name)
    return rec


def _analyze_metric_sample(db: Session, metric_name: str) -> dict:
    if not metric_name:
        return {"recommended": "ewma", "reason": "指标名无法识别，基于统计特征默认推荐 EWMA", "confidence": "low", "method": "统计推断"}

    records = (
        db.query(MetricRecord.value, MetricRecord.timestamp)
        .filter(MetricRecord.name == metric_name)
        .order_by(MetricRecord.timestamp.desc())
        .limit(200)
        .all()
    )

    if len(records) < 10:
        return {"recommended": "ewma", "reason": f"数据点不足（{len(records)} 条），默认推荐 EWMA", "confidence": "low", "method": "统计推断"}

    values = [r.value for r in records]
    mean = sum(values) / len(values)
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    median = sorted_vals[n // 2]
    mad = sum(abs(v - median) for v in values) / n
    std = (sum((v - mean) ** 2 for v in values) / n) ** 0.5

    coef_var = std / abs(mean) if mean != 0 else 0
    skewness = (sum((v - mean) ** 3 for v in values) / n) / (std ** 3) if std > 0 else 0

    if coef_var > 1.0:
        return {"recommended": "isolation_forest", "reason": f"变异系数 {coef_var:.2f} > 1.0，数据高度离散", "confidence": "medium", "method": "统计推断"}
    if abs(skewness) > 2:
        return {"recommended": "mad", "reason": f"偏度 {skewness:.2f}，数据严重偏态，MAD 比 σ 更鲁棒", "confidence": "medium", "method": "统计推断"}
    if std > 0 and mad > 0 and (std / mad) > 3:
        return {"recommended": "mad", "reason": f"标准差/MAD 比值 {std/mad:.1f} > 3，数据有较多离群点", "confidence": "medium", "method": "统计推断"}

    return {"recommended": "ewma", "reason": f"数据相对平稳（CV={coef_var:.2f}，偏度={skewness:.1f}），EWMA 最合适", "confidence": "medium", "method": "统计推断"}


def recommend_algorithm(db: Session, asset_id: int = None, metric_name: str = "") -> dict:
    since = datetime.now() - timedelta(days=90)
    q = db.query(AnomalyBenchmark).filter(AnomalyBenchmark.created_at >= since)
    if asset_id:
        q = q.filter(AnomalyBenchmark.asset_id == asset_id)
    if metric_name:
        q = q.filter(AnomalyBenchmark.metric_name == metric_name)

    records = q.all()
    if records:
        by_alg = {}
        for r in records:
            alg = r.algorithm or "unknown"
            if alg not in by_alg:
                by_alg[alg] = {"count": 0, "f1": 0}
            by_alg[alg]["count"] += 1
            by_alg[alg]["f1"] += r.f1_score or 0

        best_alg = max(by_alg.items(), key=lambda x: x[1]["f1"] / max(x[1]["count"], 1))
        confidence = "high" if by_alg[best_alg[0]]["count"] >= 10 else "medium"
        meta = _ALGORITHM_META.get(best_alg[0], {})

        return {
            "recommended": best_alg[0],
            "name": meta.get("name", best_alg[0]),
            "avg_f1": round(best_alg[1]["f1"] / max(best_alg[1]["count"], 1), 3),
            "sample_count": by_alg[best_alg[0]]["count"],
            "confidence": confidence,
            "reason": f"基于 {by_alg[best_alg[0]]['count']} 条标注数据，{best_alg[0]} 算法的 F1 最优",
            "method": "基准标注",
        }

    return _recommend_by_metric特征(metric_name, db)
