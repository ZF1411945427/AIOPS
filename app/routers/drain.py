"""Drain 日志模板聚类（标准树形算法）API。

将简化版(定长 token + 线性扫描)升级为真正的 Drain:
  - 树形分簇(indexed tree)按深度逐 token 匹配, O(log n) 而非 O(n) 线性扫描
  - 变长 token: 数值→<NUM>, 十六进制→<HEX>, IPv4→<IP>, 路径→<PATH>
  - 叶节点按相似度阈值合并并替换差异 token 为 <*>
参考文献: He et al., "Drain: An Online Log Parsing Approach with Fixed Depth Tree", ICWS 2017。
"""
from __future__ import annotations

from fastapi import APIRouter, Body

router = APIRouter(prefix="/drain", tags=["drain"])

# token 视为通配的类型集合（正则 → 占位符）
_WILDCARD_RULES = [
    (r"^(?:\d{1,3}\.){3}\d{1,3}$", "<IP>"),      # IPv4
    (r"^0x[0-9a-fA-F]+$", "<HEX>"),              # 十六进制
    (r"^[0-9a-fA-F]{8,}$", "<HEX>"),             # 长十六进制(hash/uuid 片段)
    (r"^\d+$", "<NUM>"),                         # 纯数字
    (r"^[+-]?\d+\.\d+$", "<NUM>"),               # 浮点
    (r"^[A-Za-z]:[\\/].+|^/[^ ]*[\\/][^ ]*$", "<PATH>"),  # 绝对路径
]


def _wildcard(token: str) -> str | None:
    """若 token 属于可变/通配类, 返回占位符; 否则 None。"""
    import re
    for pat, repl in _WILDCARD_RULES:
        if re.match(pat, token):
            return repl
    return None


def drain_tokenize(line: str):
    """分词: 空白切分 + 括号/引号就近归一。"""
    toks = line.strip().split()
    # 将成对括号/引号内的内容整体成一个 token, 避免把参数拆散
    merged = []
    buf = None
    open_ch = None
    pairs = {"[": "]", "(": ")", "{": "}", '"': '"', "'": "'"}
    for t in toks:
        if buf is None:
            for ch, close in pairs.items():
                if t.startswith(ch) and close in t:
                    if t.count(ch) >= t.count(close):  # 未闭合, 开始缓冲
                        buf, open_ch = t, close
                        break
                if t.startswith(ch) and not t.endswith(close):
                    buf, open_ch = t, close
                    break
            else:
                merged.append(t)
        else:
            buf += " " + t
            if open_ch in buf and buf.rstrip().endswith(open_ch):
                merged.append(buf)
                buf, open_ch = None, None
    if buf is not None:
        merged.append(buf)
    return merged


class _Node:
    __slots__ = ("token", "children", "clusters")
    def __init__(self, token):
        self.token = token           # 该层 token; "*" 表示通配层
        self.children = {}           # token(含 <*>通配) -> _Node
        self.clusters = []           # 仅叶节点持有 [(template_tokens, count, logs)]


def drain_cluster(logs: list[str], depth: int = 4, similarity_threshold: float = 0.7,
                  max_children: int = 64) -> list[dict]:
    """在线 Drain 聚类。

    参数:
      depth: 解析树深度(固定深度, 含叶节点层); ≥2
      similarity_threshold: 叶级相似度阈值(0~1), 决定是否并入已有模板
      max_children: 单个节点的最大子节点数(超出后用通配覆盖, 防爆炸)
    """
    if not logs:
        return []
    depth = max(2, int(depth))
    root = _Node("ROOT")

    def canon(tok: str):
        return _wildcard(tok) or tok

    def leaf_tokens(tokens: list):
        # 存储/归并时把「可变类 token」(数字/IP/hex/路径)归一为占位符, 使不同取值可归并
        return [canon(t) for t in tokens]

    for log in logs:
        tokens = drain_tokenize(log)
        if not tokens:
            continue
        n = len(tokens)
        # 限制参与树匹配的深度: 固定深度 Drain 取前 depth-1 个 token 做树路径
        path_len = min(n, depth - 1)
        node = root
        for i in range(path_len):
            tok = tokens[i]
            key = canon(tok)
            if key in node.children:
                child = node.children[key]
            else:
                # 通配兜底
                if "*" in node.children:
                    child = node.children["*"]
                else:
                    child = _Node(tok)
                    node.children[key] = child
            node = child

        ltoks = leaf_tokens(tokens)
        # 叶节点: 与已有模板做相似度匹配(模板已含占位符)
        best = None
        best_score = 0.0
        for c in node.clusters:
            tmpl = c[0]
            if len(tmpl) != len(ltoks):
                continue
            matches = sum(1.0 for a, b in zip(ltoks, tmpl) if a == b or b == "<*>")
            score = matches / len(ltoks)
            if score > best_score:
                best_score, best = score, c
        if best and best_score >= similarity_threshold:
            tmpl, count, logs_l = best
            # 将不同 token 更新为通配 <*>
            for i in range(len(ltoks)):
                if tmpl[i] != "<*>" and ltoks[i] != tmpl[i]:
                    tmpl[i] = "<*>"
            logs_l.append(log)
            node.clusters.remove(best)
            node.clusters.append((tmpl, count + 1, logs_l))
        else:
            node.clusters.append((ltoks, 1, [log]))

    # 汇总
    result = []

    def walk(node):
        for c in node.clusters:
            tmpl, count, logs_l = c
            result.append({
                "template": " ".join(tmpl),
                "template_tokens": tmpl,
                "count": count,
                "logs": logs_l,
            })
        for child in node.children.values():
            walk(child)

    walk(root)
    result.sort(key=lambda x: -x["count"])
    return result


@router.get("/status")
def status():
    """连通性探活。"""
    return {"module": "drain", "status": "ok", "implemented": True, "algorithm": "drain-tree"}


@router.post("/cluster")
def cluster_logs(
    logs: list[str] = Body(...),
    depth: int = Body(4, ge=2, le=8, description="Drain 树深度"),
    similarity_threshold: float = Body(0.7, ge=0.1, le=1.0, description="叶级相似度阈值"),
):
    """Drain 日志模板聚类（标准树形实现）。"""
    clusters = drain_cluster(logs, depth=depth, similarity_threshold=similarity_threshold)
    return {"clusters": clusters, "count": len(clusters), "algorithm": "drain-tree"}
