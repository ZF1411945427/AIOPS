"""PromQL 子集解析器 — 让 Agent 用 PromQL 风格表达式查询本系统指标。

支持的语法子集:
  1. metric_name                          — 简单指标名
  2. metric_name{label="value"}           — 带标签过滤（label 可为 asset_id / host / unit 等）
  3. topk(N, metric_name)                 — Top N 资产
  4. topk(N, metric_name{label="value"})  — Top N + 标签过滤
  5. bottomk(N, metric_name)              — Bottom N 资产
  6. rate(metric_name[5m])                — 速率（简化：最近值 - 窗口起点值 / 窗口秒数）
  7. avg(metric_name) / max(...) / min(...) / sum(...)  — 聚合（全资产）
  8. avg_over_time(metric_name[5m])       — 时间窗口聚合（每个资产的窗口平均值）
  9. metric_name{asset_id="1"}            — 按 asset_id 过滤
 10. 支持组合：topk(3, rate(metric_name[5m]))

输出结构:
  {
    "metric_name": "cpu_usage",
    "labels": {"asset_id": "1", "host": "web-01"},
    "aggregator": None | "avg" | "max" | "min" | "sum" | "topk" | "bottomk" | "rate" | "avg_over_time",
    "aggregator_arg": None | 3,           # topk/bottomk 的 N
    "range_window": None | "5m",          # rate / avg_over_time 的窗口
    "raw": "原始 PromQL"
  }

不支持（超出子集返回 error）:
  - 二元运算 (a + b)
  - 直方图分位数 histogram_quantile
  - 子查询 Subquery
  - 偏移 offset
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class PromQLQuery:
    metric_name: str = ""
    labels: Dict[str, str] = field(default_factory=dict)
    aggregator: Optional[str] = None        # avg/max/min/sum/topk/bottomk/rate/avg_over_time/max_over_time/min_over_time
    aggregator_arg: Optional[int] = None    # topk/bottomk 的 N
    range_window: Optional[str] = None      # 如 "5m" / "1h"
    inner_aggregator: Optional[str] = None  # topk/bottomk 内层的聚合器（如 rate/avg_over_time）
    raw: str = ""
    error: Optional[str] = None


_WINDOW_RE = re.compile(r'^(\d+)([smhdw])$')
_AGG_FUNCS = {"avg", "max", "min", "sum", "count"}
_RANGE_AGG_FUNCS = {"avg_over_time", "max_over_time", "min_over_time", "sum_over_time", "rate", "irate", "increase"}
_TOPK_FUNCS = {"topk", "bottomk", "quantile"}


def _parse_window(window_str: str) -> Optional[int]:
    """将 '5m' / '1h' 转为秒数。无效返回 None。"""
    m = _WINDOW_RE.match(window_str.strip())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    return n * {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]


def _parse_labels(label_str: str) -> Dict[str, str]:
    """解析 {label="value", label2="value2"} 内部内容（不含大括号）。"""
    labels = {}
    for m in re.finditer(r'(\w+)\s*=\s*"([^"]*)"', label_str):
        labels[m.group(1)] = m.group(2)
    return labels


def _strip_metric_with_labels(s: str):
    """从形如 'metric_name{a="b"}' 的字符串中提取 metric_name 和 labels dict。"""
    s = s.strip()
    brace_idx = s.find('{')
    if brace_idx == -1:
        return s, {}
    metric_name = s[:brace_idx].strip()
    close_idx = s.find('}', brace_idx)
    if close_idx == -1:
        return s, {}
    labels = _parse_labels(s[brace_idx + 1:close_idx])
    return metric_name, labels


def parse_promql(expr: str) -> PromQLQuery:
    """解析 PromQL 子集表达式。失败时返回带 error 字段的 PromQLQuery。"""
    if not expr or not expr.strip():
        return PromQLQuery(error="空表达式", raw=expr or "")

    raw = expr.strip()

    # 去掉最外层多余空格
    s = raw

    # ── 情况 A: 聚合/范围函数 — func(args) ──
    func_match = re.match(r'^(\w+)\s*\((.*)\)\s*$', s, re.DOTALL)
    if func_match:
        func = func_match.group(1).lower()
        inner = func_match.group(2).strip()

        if func in _TOPK_FUNCS:
            # topk(N, metric_name{...}) 或 bottomk(...)
            parts = inner.split(',', 1)
            if len(parts) != 2:
                return PromQLQuery(error=f"{func} 需要 2 个参数 (N, expr)", raw=raw)
            try:
                n = int(parts[0].strip())
            except ValueError:
                return PromQLQuery(error=f"{func} 第一个参数必须是整数", raw=raw)
            inner_expr = parts[1].strip()
            sub = parse_promql(inner_expr)
            if sub.error:
                return PromQLQuery(error=f"{func} 内层解析失败: {sub.error}", raw=raw)
            return PromQLQuery(
                metric_name=sub.metric_name,
                labels=sub.labels,
                aggregator=func,
                aggregator_arg=n,
                range_window=sub.range_window,
                inner_aggregator=sub.aggregator,  # 保存内层聚合器（如 rate/avg_over_time）
                raw=raw,
            )

        if func in _RANGE_AGG_FUNCS:
            # rate(metric_name[5m]) 或 avg_over_time(metric_name[5m])
            inner_stripped = inner.strip()
            win_match = re.search(r'\[([^\]]+)\]\s*$', inner_stripped)
            window_str = None
            if win_match:
                window_str = win_match.group(1).strip()
                inner_stripped = inner_stripped[:win_match.start()].strip()
            metric_name, labels = _strip_metric_with_labels(inner_stripped)
            if not metric_name:
                return PromQLQuery(error=f"{func} 缺少指标名", raw=raw)
            return PromQLQuery(
                metric_name=metric_name,
                labels=labels,
                aggregator=func,
                range_window=window_str,
                raw=raw,
            )

        if func in _AGG_FUNCS:
            # avg(metric_name{...}) — 全资产聚合
            metric_name, labels = _strip_metric_with_labels(inner.strip())
            if not metric_name:
                return PromQLQuery(error=f"{func} 缺少指标名", raw=raw)
            return PromQLQuery(
                metric_name=metric_name,
                labels=labels,
                aggregator=func,
                raw=raw,
            )

        return PromQLQuery(error=f"不支持的函数: {func}", raw=raw)

    # ── 情况 B: 带范围窗口但无函数 — metric_name[5m]（视为最近窗口原始值）──
    range_only = re.match(r'^([^\[\]\{\s]+)\[([^\]]+)\]\s*$', s)
    if range_only:
        return PromQLQuery(
            metric_name=range_only.group(1).strip(),
            range_window=range_only.group(2).strip(),
            raw=raw,
        )

    # ── 情况 C: 简单指标 + 可选标签 ──
    metric_name, labels = _strip_metric_with_labels(s)
    if not metric_name or not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', metric_name):
        return PromQLQuery(error=f"无法解析指标名: {metric_name}", raw=raw)
    return PromQLQuery(
        metric_name=metric_name,
        labels=labels,
        raw=raw,
    )


def promql_to_dict(q: PromQLQuery) -> Dict[str, Any]:
    """转成可 JSON 序列化的 dict。"""
    return {
        "metric_name": q.metric_name,
        "labels": q.labels,
        "aggregator": q.aggregator,
        "aggregator_arg": q.aggregator_arg,
        "range_window": q.range_window,
        "inner_aggregator": q.inner_aggregator,
        "raw": q.raw,
        "error": q.error,
    }


def is_valid(expr: str) -> bool:
    return parse_promql(expr).error is None
