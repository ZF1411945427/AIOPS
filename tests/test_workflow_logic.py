"""工作流纯函数单元测试: 拓扑排序 / 依赖解析 / 条件表达式求值 / 模板渲染 (H3 扩展)。

全部为纯函数, 无需 DB, 对齐 ongrid flow 引擎的 engine_test.go 覆盖度。
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.agent_workflow_service import (
    topological_sort,
    _node_dependencies,
    _eval_condition,
    _render_value,
)


def test_topological_sort_linear():
    nodes = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    edges = [
        {"source": "a", "target": "b"},
        {"source": "b", "target": "c"},
    ]
    order = topological_sort(nodes, edges)
    assert order.index("a") < order.index("b") < order.index("c")


def test_topological_sort_diamond():
    nodes = [{"id": "s"}, {"id": "x"}, {"id": "y"}, {"id": "e"}]
    edges = [
        {"source": "s", "target": "x"},
        {"source": "s", "target": "y"},
        {"source": "x", "target": "e"},
        {"source": "y", "target": "e"},
    ]
    order = topological_sort(nodes, edges)
    assert order.index("s") == 0
    assert order.index("e") == len(order) - 1


def test_topological_sort_supports_from_to_keys():
    nodes = [{"id": "p"}, {"id": "q"}]
    edges = [{"from": "p", "to": "q"}]
    assert topological_sort(nodes, edges) == ["p", "q"]


def test_node_dependencies_multi():
    edges = [
        {"source": "a", "target": "z"},
        {"source": "b", "target": "z"},
        {"source": "c", "target": "b"},
    ]
    assert _node_dependencies("z", edges) == {"a", "b"}
    assert _node_dependencies("b", edges) == {"c"}
    assert _node_dependencies("a", edges) == set()


def test_eval_condition_default_true():
    assert _eval_condition("default", {}) is True
    assert _eval_condition("true", {}) is True


def test_eval_condition_variable_eq():
    # 条件表达式使用裸变量(经 jinja 上下文解析), 操作数可为变量或字面量
    assert _eval_condition("status == error", {"status": "error"}) is True
    assert _eval_condition("status == error", {"status": "ok"}) is False


def test_eval_condition_gt_lt():
    assert _eval_condition("v > 5", {"v": 10}) is True
    assert _eval_condition("v < 5", {"v": 3}) is True
    assert _eval_condition("v < 5", {"v": 10}) is False


def test_eval_condition_ne():
    # 修复: ne/gt/lt 关键字运算符此前因 pyop 带空格后缀比较不匹配而恒失效
    assert _eval_condition("m ne auto", {"m": "manual"}) is True
    assert _eval_condition("m ne manual", {"m": "manual"}) is False


def test_eval_condition_keyword_gt_lt():
    assert _eval_condition("v gt 5", {"v": 10}) is True
    assert _eval_condition("v lt 5", {"v": 3}) is True
    assert _eval_condition("v lt 5", {"v": 10}) is False


def test_eval_condition_contains_startswith():
    ctx = {"s": "nginx-prod"}
    assert _eval_condition("s contains prod", ctx) is True
    assert _eval_condition("s startswith nginx", ctx) is True
    assert _eval_condition("s startswith kong", ctx) is False
    assert _eval_condition("s contains missing", ctx) is False


def test_eval_condition_literal_equality():
    assert _eval_condition("mode == 'auto'", {"mode": "auto"}) is True


def test_render_value_jinja_and_recursive():
    ctx = {"name": "aiops", "n": 3}
    assert _render_value("hello {{name}}", ctx) == "hello aiops"
    assert _render_value({"k": "{{name}}", "m": 1}, ctx) == {"k": "aiops", "m": 1}
    assert _render_value(["{{name}}", "{{n}}"], ctx) == ["aiops", "3"]
    assert _render_value("plain", ctx) == "plain"
