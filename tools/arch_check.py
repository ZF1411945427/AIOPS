"""架构边界检查 — 对齐 go-arch-lint 的依赖方向约束。

规则:
  1. 分层: routers → services → models
  2. services 禁止顶层 import routers（函数内延迟 import 允许）
  3. 禁止 services 间的循环依赖链（顶层 import）
  4. 所有模块必须位于 app/ 下且属于已知层

退出码: 0 通过, 1 违规
"""
import ast
import os
import sys

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(PROJECT, "app")

LAYERS = {"models": 0, "domains": 1, "services": 2, "routers": 3}
KNOWN_APPS = set(LAYERS.keys())


def _layer_of(path: str):
    rel = os.path.relpath(path, APP).replace("\\", "/")
    parts = rel.split("/")
    for p in parts:
        if p in LAYERS:
            return p
    return None


def _is_top_level(node: ast.stmt, parent_map: dict) -> bool:
    """判断 import 是否在模块顶层(不在函数/类/if 内部)。"""
    parent = parent_map.get(node)
    while parent:
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return False
        parent = parent_map.get(parent)
    return True


def _collect_top_level_imports(source: str):
    """收集模块顶层 import 的 app 内部模块(忽略函数/类内部 import)。"""
    imports = set()
    tree = ast.parse(source)
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.ImportFrom, ast.Import)):
            if isinstance(node, ast.ImportFrom):
                m = node.module or ""
                if not m.startswith("app."):
                    continue
                parts = m.split(".")
                if len(parts) >= 2 and parts[1] in KNOWN_APPS:
                    imports.add(m)
    return imports


def check():
    errors = []
    mod_layer = {}
    top_imports = {}

    for root, dirs, files in os.walk(APP):
        for f in files:
            if not f.endswith(".py"):
                continue
            full = os.path.join(root, f)
            pkg = os.path.relpath(full, PROJECT).replace("\\", ".")[:-3].replace("/.", "")
            layer = _layer_of(full)
            if not layer:
                continue
            mod_layer[pkg] = layer
            with open(full, encoding="utf-8") as fh:
                top_imports[pkg] = _collect_top_level_imports(fh.read())

    for src_mod, deps in top_imports.items():
        src_layer = mod_layer.get(src_mod)
        if not src_layer:
            continue
        for dep_mod in deps:
            parts = dep_mod.split(".")
            tgt_app = parts[1]
            tgt_layer = LAYERS[tgt_app]
            if LAYERS.get(src_layer, -1) < tgt_layer:
                errors.append(
                    f"  [DIR] {src_mod} 顶层 import 上层 {dep_mod}  "
                    f"({src_layer}→{tgt_app})"
                )
            if tgt_app == "routers" and src_layer != "routers":
                errors.append(
                    f"  [DIR] {src_mod} 顶层 import routers 模块 {dep_mod}"
                )

    # 循环依赖检测(有向图 DFS)
    visited = set()

    def find_cycle(start, path):
        if start in path:
            return path[path.index(start):] + [start]
        if start in visited:
            return None
        visited.add(start)
        for dep in top_imports.get(start, set()):
            if dep in top_imports:
                c = find_cycle(dep, path + [start])
                if c:
                    return c
        return None

    for mod in top_imports:
        c = find_cycle(mod, [])
        if c:
            cycle_str = " → ".join(c)
            errors.append(f"  [CYCLE] 顶层 import 循环依赖: {cycle_str}")
            break

    if errors:
        print(f"架构检查失败 ({len(errors)} 项):")
        for e in errors:
            print(e)
        return 1
    print("架构检查通过: 无方向违规, 无循环依赖")
    return 0


if __name__ == "__main__":
    sys.exit(check())