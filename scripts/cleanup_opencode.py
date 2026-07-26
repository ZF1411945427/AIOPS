"""opencode 历史数据清理脚本

定期清理 opencode 累积的 SQLite 数据与文件缓存，保持窗口流畅。

用法:
    python cleanup_opencode.py              # 默认保留最近 10 个 session
    python cleanup_opencode.py --keep 5     # 保留最近 5 个 session
    python cleanup_opencode.py --keep 0     # 清空所有历史 session（仅保留运行中）
    python cleanup_opencode.py --keep-ids ses_xxx,ses_yyy   # 指定保留的 session id

注意:
    - VACUUM 需要数据库无其他连接占用，建议先退出 opencode 再运行；
      若运行时报 "database is locked"，关闭 opencode 后重试即可。
    - 仅使用标准库，无外部依赖。
"""
import argparse
import os
import shutil
import sqlite3
import sys
import time

DATA_DIR = os.path.join(os.environ["USERPROFILE"], ".local", "share", "opencode")
DB_PATH = os.path.join(DATA_DIR, "opencode.db")


def human(n: int) -> str:
    return f"{n / 1024 / 1024:.1f}MB" if n is not None and n >= 0 else "gone"


def fsize(p: str) -> int:
    return os.path.getsize(p) if os.path.exists(p) else -1


def clean_files():
    """清理文件缓存：snapshot / session_diff / tool-output / 旧 log"""
    targets = [
        os.path.join(DATA_DIR, "snapshot"),
        os.path.join(DATA_DIR, "storage", "session_diff"),
        os.path.join(DATA_DIR, "tool-output"),
    ]
    freed = 0
    for d in targets:
        if os.path.isdir(d):
            before = sum(
                os.path.getsize(os.path.join(r, f))
                for r, _, fs in os.walk(d) for f in fs
            )
            shutil.rmtree(d, ignore_errors=True)
            os.makedirs(d, exist_ok=True)
            freed += before
    # 旧日志
    log_dir = os.path.join(DATA_DIR, "log")
    if os.path.isdir(log_dir):
        for f in os.listdir(log_dir):
            if f.endswith(".log"):
                try:
                    os.remove(os.path.join(log_dir, f))
                except OSError:
                    pass
    return freed


def main():
    ap = argparse.ArgumentParser(description="opencode 历史数据清理")
    ap.add_argument("--keep", type=int, default=10, help="保留最近 N 个 session（默认 10）")
    ap.add_argument("--keep-ids", default="", help="额外保留的 session id（逗号分隔）")
    args = ap.parse_args()

    if not os.path.exists(DB_PATH):
        print(f"数据库不存在: {DB_PATH}")
        sys.exit(1)

    keep_ids = {s.strip() for s in args.keep_ids.split(",") if s.strip()}

    db_before = fsize(DB_PATH)
    wal_before = fsize(DB_PATH + "-wal")
    print(f"清理前: opencode.db={human(db_before)}  wal={human(wal_before)}")

    con = sqlite3.connect(f"file:{DB_PATH}?mode=rwc", uri=True, timeout=60)
    con.execute("PRAGMA busy_timeout=60000")
    cur = con.cursor()

    # 选保留集：最近 N 个 + 指定 id
    cur.execute("SELECT id FROM session ORDER BY time_created DESC")
    all_ids = [r[0] for r in cur.fetchall()]
    n = args.keep if args.keep > 0 else 0
    keep_set = set(all_ids[:n]) | keep_ids
    drop_ids = [s for s in all_ids if s not in keep_set]
    print(f"session: 共 {len(all_ids)}，保留 {len(keep_set)}，删除 {len(drop_ids)}")

    if drop_ids:
        ph = ",".join("?" for _ in drop_ids)
        t0 = time.time()
        cur.execute("BEGIN")
        try:
            cur.execute(f"DELETE FROM part WHERE session_id IN ({ph})", drop_ids)
            p = cur.rowcount
            cur.execute(f"DELETE FROM todo WHERE session_id IN ({ph})", drop_ids)
            td = cur.rowcount
            cur.execute(f"DELETE FROM message WHERE session_id IN ({ph})", drop_ids)
            m = cur.rowcount
            cur.execute(f"DELETE FROM session WHERE id IN ({ph})", drop_ids)
            s = cur.rowcount
            con.commit()
            print(f"已删: part={p} todo={td} message={m} session={s}（{time.time()-t0:.1f}s）")
        except Exception as e:
            con.rollback()
            print(f"删除失败，已回滚: {e}")
            sys.exit(1)

    # 合并 WAL 并截断
    cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    print(f"wal_checkpoint(TRUNCATE): {cur.fetchall()}")

    con.close()

    # VACUUM 压缩（需无其他连接）
    try:
        con2 = sqlite3.connect(f"file:{DB_PATH}?mode=rwc", uri=True, timeout=30)
        con2.execute("PRAGMA busy_timeout=30000")
        con2.execute("VACUUM")
        con2.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con2.close()
        print("VACUUM: 成功")
    except Exception as e:
        print(f"VACUUM 失败（请退出 opencode 后重试）: {e}")

    # 文件缓存
    freed_files = clean_files()
    print(f"文件缓存清理: {human(freed_files)}")

    db_after = fsize(DB_PATH)
    wal_after = fsize(DB_PATH + "-wal")
    print(f"清理后: opencode.db={human(db_after)}  wal={human(wal_after)}")
    print(f"数据库释放: {human(max(db_before,0)-max(db_after,0))}  WAL释放: {human(max(wal_before,0)-max(wal_after,0))}")


if __name__ == "__main__":
    main()
