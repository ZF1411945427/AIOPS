#!/usr/bin/env python
"""
SQLite → PostgreSQL 数据搬运脚本

从 db/aiops.db(SQLite) 向 PostgreSQL 搬运业务数据。
PG 连接串通过环境变量 AIOPS_DB_URL 读取, 默认 postgresql://aiops:aiops-secret@127.0.0.1:5432/aiops

用法:
    python scripts/migrate_data.py

跳过策略:
    - 超大时序表: spans, metric_records, k8s_events, workflow_audit_logs, agent_workflow_node_runs, agent_workflow_runs
    - 空表: SQLite 中 0 行的表
    - 基础表: tenants, users, roles, role_menus(PG 已初始化,以 PG 为准)
    - 已播种表: 和目标表行数相同且 id 完全重叠的表跳过(即 init_db 数据相同)
    - 其他表: 直接 INSERT ON CONFLICT DO NOTHING

作者: AIOps Team
"""
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

# ── 配置 ─────────────────────────────────────────────
PG_URL = os.environ.get(
    "AIOPS_DB_URL",
    "postgresql://aiops:aiops-secret@127.0.0.1:5432/aiops",
)
SQLITE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "aiops.db"
)

BATCH_SIZE = 500

# 超大表: 跳过搬运(时序数据,生产会重新采集)
SKIP_TABLES = {
    "spans",
    "metric_records",
    "k8s_events",
    "workflow_audit_logs",
    "agent_workflow_node_runs",
    "agent_workflow_runs",
}

# 基础表: 以 PG 已有数据为准,不搬运
BASE_TABLES = {
    "tenants",
    "users",
    "roles",
    "role_menus",
}

# 已知 PG 已播种且与 SQLite 数据相同的表(自动检测后会跳过,此列表仅为加速检测)
PRE_SEEDED_TABLES = {
    "workflow_templates",
    "component_catalog",
    "skills",
    "agent_configs",
    "sub_agents",
    "inspection_templates",
    "anomaly_configs",
    "agent_workflows",
    "chaos_scenarios",
    "chaos_experiments",
}


def get_sqlite_engine() -> Engine:
    return create_engine(f"sqlite:///{SQLITE_PATH}")


def get_pg_engine() -> Engine:
    return create_engine(PG_URL)


def get_sqlite_tables(engine: Engine) -> List[str]:
    insp = inspect(engine)
    return [t for t in insp.get_table_names() if not t.startswith("sqlite_")]


def get_table_row_count(engine: Engine, table: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()


def get_all_ids(engine: Engine, table: str) -> Set[int]:
    with engine.connect() as conn:
        try:
            rows = conn.execute(text(f'SELECT id FROM "{table}"')).fetchall()
            return {r[0] for r in rows}
        except Exception:
            return set()


def get_pg_columns(engine: Engine, table: str) -> List[Dict[str, Any]]:
    insp = inspect(engine)
    return insp.get_columns(table)


def get_sqlite_column_info(engine: Engine, table: str) -> List[Dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(text(f'PRAGMA table_info("{table}")')).fetchall()
        return [
            {
                "name": r[1],
                "type": r[2].upper(),
                "nullable": not r[3],
            }
            for r in rows
        ]


def is_date_type(col_type: str) -> bool:
    ct = col_type.upper()
    return any(t in ct for t in ("TIMESTAMP", "DATETIME", "DATE"))


def convert_value(
    value: Any, col_name: str, col_type: str, sq_types: Optional[Dict[str, str]] = None
) -> Any:
    if value is None:
        return None
    if col_type and is_date_type(col_type):
        if isinstance(value, str) and value.strip():
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return value
        return value
    if sq_types and col_name in sq_types:
        sq_type = sq_types[col_name].upper()
        if "BOOL" in sq_type:
            if isinstance(value, int):
                return bool(value)
            if isinstance(value, str):
                return value.lower() in ("1", "true", "yes")
    return value


def table_has_column(engine: Engine, table: str, column: str) -> bool:
    cols = get_pg_columns(engine, table)
    return any(c["name"] == column for c in cols)


def migrate_table(
    sq_engine: Engine,
    pg_engine: Engine,
    table: str,
    batch_size: int = BATCH_SIZE,
) -> Tuple[int, int, int]:
    sq_cols = get_sqlite_column_info(sq_engine, table)
    col_names = [c["name"] for c in sq_cols]

    pg_cols = get_pg_columns(pg_engine, table)
    pg_col_names = [c["name"] for c in pg_cols]
    pg_col_types = {c["name"]: c["type"].__class__.__name__ for c in pg_cols}

    common_cols = [c for c in col_names if c in pg_col_names]
    if not common_cols:
        return 0, 0, 0

    common_cols_str = ", ".join(f'"{c}"' for c in common_cols)
    placeholders = ", ".join(f":{c}" for c in common_cols)

    conflict_col = "id" if "id" in common_cols else common_cols[0]
    on_conflict = f'ON CONFLICT ("{conflict_col}") DO NOTHING'

    sq_types = {c["name"]: c["type"] for c in sq_cols}

    total_read = 0
    total_inserted = 0
    total_errors = 0

    with sq_engine.connect() as sq_conn:
        sq_conn.execution_options(stream_results=True)
        result = sq_conn.execute(
            text(f'SELECT {common_cols_str} FROM "{table}"')
        )
        rows = result.fetchall()

    total_read = len(rows)
    if total_read == 0:
        return total_read, 0, 0

    with pg_engine.begin() as pg_conn:
        for i in range(0, total_read, batch_size):
            batch = rows[i : i + batch_size]
            batch_data = []
            for row in batch:
                record = {}
                for j, col in enumerate(common_cols):
                    record[col] = convert_value(
                        row[j], col, pg_col_types.get(col, ""), sq_types
                    )
                batch_data.append(record)

            try:
                stmt = text(
                    f'INSERT INTO "{table}" ({common_cols_str}) '
                    f"VALUES ({placeholders}) {on_conflict}"
                )
                for record in batch_data:
                    pg_conn.execute(stmt, record)
                total_inserted += len(batch_data)
            except Exception as e:
                total_errors += len(batch_data)
                print(f"  [{table}] 批次 {i // batch_size} 错误: {e}")

    return total_read, total_inserted, total_errors


def reset_sequences(pg_engine: Engine, tables: List[str]) -> None:
    with pg_engine.begin() as conn:
        for table in tables:
            if not table_has_column(pg_engine, table, "id"):
                continue
            try:
                max_id = conn.execute(
                    text(f'SELECT COALESCE(MAX(id), 0) FROM "{table}"')
                ).scalar()
                if max_id > 0:
                    conn.execute(
                        text(
                            f"SELECT setval('{table}_id_seq', {max_id}, true)"
                        )
                    )
                    print(f"  [序列] {table}_id_seq -> {max_id}")
            except Exception as e:
                pass


def main():
    sq_engine = get_sqlite_engine()
    pg_engine = get_pg_engine()

    print("=" * 60)
    print("SQLite → PostgreSQL 数据搬运")
    print("=" * 60)
    print(f"SQLite: {SQLITE_PATH}")
    print(f"PG:     {PG_URL}")
    print()

    # 1. 获取 SQLite 全表清单
    all_tables = get_sqlite_tables(sq_engine)
    print(f"SQLite 总表数: {len(all_tables)}")
    print()

    # 2. 过滤表
    empty_tables = set()
    skipped_big = set()
    skipped_base = set()
    skipped_seeded = set()
    to_migrate = []

    for t in sorted(all_tables):
        if t in SKIP_TABLES:
            skipped_big.add(t)
            continue
        if t in BASE_TABLES:
            skipped_base.add(t)
            continue

        sq_count = get_table_row_count(sq_engine, t)
        if sq_count == 0:
            empty_tables.add(t)
            continue

        pg_count = get_table_row_count(pg_engine, t)
        if pg_count > 0:
            sq_ids = get_all_ids(sq_engine, t)
            pg_ids = get_all_ids(pg_engine, t)
            if sq_ids == pg_ids and sq_count == pg_count:
                skipped_seeded.add(t)
                continue

        to_migrate.append(t)

    print(f"跳过(超大表): {len(skipped_big)} — {', '.join(sorted(skipped_big))}")
    print(f"跳过(空表):   {len(empty_tables)}")
    print(f"跳过(基础表): {len(skipped_base)} — {', '.join(sorted(skipped_base))}")
    print(f"跳过(已播种): {len(skipped_seeded)} — {', '.join(sorted(skipped_seeded))}")
    print(f"待搬运:       {len(to_migrate)} 张表")
    print()

    if not to_migrate:
        print("没有需要搬运的表, 退出。")
        sq_engine.dispose()
        pg_engine.dispose()
        return

    # 3. 禁用 FK 约束
    with pg_engine.begin() as conn:
        conn.execute(text("SET session_replication_role = 'replica'"))
    print("[FK] 已临时禁用外键约束")

    # 4. 逐表搬运
    total_rows_read = 0
    total_rows_inserted = 0
    total_rows_error = 0
    table_results = []

    for table in to_migrate:
        sq_count = get_table_row_count(sq_engine, table)
        print(f"[搬运] {table} ({sq_count} 行)...", end="", flush=True)
        read_n, ins_n, err_n = migrate_table(sq_engine, pg_engine, table)
        total_rows_read += read_n
        total_rows_inserted += ins_n
        total_rows_error += err_n
        table_results.append((table, read_n, ins_n, err_n))
        status = "OK" if err_n == 0 else f"ERR({err_n})"
        print(f" 读取 {read_n}, 写入 {ins_n}, {status}")

    # 5. 恢复 FK 约束
    with pg_engine.begin() as conn:
        conn.execute(text("SET session_replication_role = 'origin'"))
    print("[FK] 已恢复外键约束")

    print()

    # 6. 重置序列
    print("[序列] 重置自增序列...")
    reset_sequences(pg_engine, to_migrate)

    print()
    print("=" * 60)
    print("搬运完成!")
    print("=" * 60)
    print(f"总读取:    {total_rows_read} 行")
    print(f"总写入:    {total_rows_inserted} 行")
    print(f"总错误:    {total_rows_error} 行")
    print(f"已跳过:    {len(skipped_big)} 超大 + {len(skipped_seeded)} 已播种 + {len(empty_tables)} 空表 + {len(skipped_base)} 基础表")
    print()

    if total_rows_error > 0:
        print("有错误的表:")
        for t, r, i, e in table_results:
            if e > 0:
                print(f"  {t}: 读取 {r}, 写入 {i}, 错误 {e}")

    sq_engine.dispose()
    pg_engine.dispose()


if __name__ == "__main__":
    main()