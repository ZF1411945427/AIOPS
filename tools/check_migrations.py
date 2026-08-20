"""Check alembic migration tree + 与 runtime _MIGRATIONS 同步校验.

用法:
  python tools/check_migrations.py --full    # 完整校验(迁移树 + 同步性)
  python tools/check_migrations.py           # 仅迁移树
"""
import ast
import glob
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MAIN_PY = _PROJECT_ROOT / "app" / "main.py"
_ALEMBIC_VERSIONS = _PROJECT_ROOT / "alembic" / "versions"


def list_versions() -> list[str]:
    versions = sorted(glob.glob(str(_ALEMBIC_VERSIONS / "*.py")))
    return [os.path.basename(v) for v in versions if not v.endswith("__init__.py")]


def check_tree() -> bool:
    versions = list_versions()
    print(f"[check_migrations] Alembic migrations: {len(versions)}")
    for v in versions:
        print(f"  - {v}")
    ok = len(versions) >= 1
    print(f"[check_migrations] migration tree {'OK' if ok else 'FAILED'} (>=1 revisions expected)")
    return ok


def _literal_dict(node) -> dict[str, list[str]]:
    result = {}
    if isinstance(node, ast.Dict):
        for k, v in zip(node.keys, node.values):
            try:
                key = ast.literal_eval(k) if isinstance(k, ast.Constant) else str(k)
            except Exception:
                key = str(k)
            if isinstance(v, ast.List):
                result[key] = [ast.literal_eval(e) for e in v.elts if isinstance(e, ast.Constant)]
    return result


def _find_named_dict(tree, var_name: str) -> dict[str, list[str]]:
    for node in ast.walk(tree):
        target = None
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == var_name:
                    target = t
                    break
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.target.id == var_name:
            target = node.target
        if target is not None and isinstance(node, (ast.Assign, ast.AnnAssign)) \
                and isinstance(node.value, ast.Dict):
            return _literal_dict(node.value)
    return {}


def extract_migrations_from_main() -> dict[str, list[str]]:
    """静态解析 app/main.py 中 _MIGRATIONS 字典(不 import, 避免副作用)。"""
    src = _MAIN_PY.read_text(encoding="utf-8")
    return _find_named_dict(ast.parse(src), "_MIGRATIONS")


def extract_columns_from_alembic() -> dict[str, list[str]]:
    """解析 alembic 迁移脚本中的 _MIGRATION_COLUMNS 字典。"""
    result = {}
    for version_file in glob.glob(str(_ALEMBIC_VERSIONS / "*.py")):
        src = Path(version_file).read_text(encoding="utf-8")
        result.update(_find_named_dict(ast.parse(src), "_MIGRATION_COLUMNS"))
    return result


def check_sync() -> bool:
    """校验 main._MIGRATIONS 与 alembic 迁移脚本补列集合一致(仅校验列名)。"""
    main_migrations = extract_migrations_from_main()
    alembic_migrations = extract_columns_from_alembic()

    def col_names(col_defs: list[str]) -> set[str]:
        return {(cd.split(maxsplit=1)[0] if cd.split() else cd) for cd in col_defs}

    mismatches = []
    all_tables = set(main_migrations) | set(alembic_migrations)
    for table in sorted(all_tables):
        main_cols = col_names(main_migrations.get(table, []))
        alembic_cols = col_names(alembic_migrations.get(table, []))
        only_main = main_cols - alembic_cols
        only_alembic = alembic_cols - main_cols
        if only_main:
            mismatches.append(f"  table[{table}] 只在 main._MIGRATIONS: {sorted(only_main)}")
        if only_alembic:
            mismatches.append(f"  table[{table}] 只在 alembic 迁移: {sorted(only_alembic)}")

    if mismatches:
        print("[check_migrations] SYNC FAILED - main._MIGRATIONS 与 alembic 迁移不一致:")
        for m in mismatches:
            print(m)
        print("  修复: 两边同步追加补充列(main.py + alembic/versions/*.py 的 _MIGRATION_COLUMNS)")
        return False
    print("[check_migrations] main._MIGRATIONS 与 alembic 迁移列同步 OK")
    return True


if __name__ == "__main__":
    full_check = "--full" in sys.argv
    ok = check_tree()
    if full_check:
        ok = check_sync() and ok
    sys.exit(0 if ok else 1)