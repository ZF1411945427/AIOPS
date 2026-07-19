"""前端首屏 bundle 体积监控（P1 任务#7）

构建后扫描 `frontend/dist/assets/` 目录，输出：
- 首屏必需 chunk 体积（main + AppLayout + vendor-vue + vendor-element + vendor-element-icons + vendor-axios）
- 全部 chunk 体积排序
- gzip 体积估算
- 体积超阈值告警（首屏 > 500KB gzip 报警）

用法：
    python scripts/check_bundle_size.py
    python scripts/check_bundle_size.py --threshold 600
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Windows 控制台 UTF-8 输出
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 首屏必需 chunk 模式（不包含按需加载的 echarts/xterm/vue-flow/markdown）
# 首屏 = 入口 + AppLayout + vue 核心 + element-plus + element-icons + axios
FIRST_SCREEN_INCLUDE = [
    "main", "index", "AppLayout",
    "vendor-vue", "vendor-element-icons", "vendor-axios",
    "polyfills",
]
# element-plus 单独处理：vendor-element.js 是首屏，但 vendor-element-*.js 子模块也算
FIRST_SCREEN_PREFIX = ["vendor-element"]

# 明确排除（按需加载，不在首屏）
FIRST_SCREEN_EXCLUDE = ["echarts", "xterm", "vue-flow", "markdown"]


def get_chunk_size_kb(path: Path) -> tuple:
    """返回 (原始 KB, gzip KB 估算)"""
    raw = path.stat().st_size
    # gzip 估算：JS 文件 gzip 压缩率约 0.30-0.35
    gzip_est = int(raw * 0.32)
    return raw / 1024, gzip_est / 1024


def is_first_screen(name: str) -> bool:
    """判断是否首屏必需 chunk"""
    # 排除所有 view 组件（按需加载）
    if "View-" in name:
        return False
    # 排除明确按需加载的大块
    for ex in FIRST_SCREEN_EXCLUDE:
        if ex in name:
            return False
    # 精确匹配
    for pat in FIRST_SCREEN_INCLUDE:
        if pat in name:
            return True
    # vendor-element-* 系列算首屏（element-plus 核心）
    for pfx in FIRST_SCREEN_PREFIX:
        if name.startswith(pfx) or f"-{pfx}-" in name or f"{pfx}-" in name:
            return True
    # 默认非首屏
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=int, default=500, help="首屏 gzip 体积阈值 (KB)")
    parser.add_argument("--dist", default="frontend/dist/assets", help="dist 目录")
    args = parser.parse_args()

    dist_dir = Path(args.dist)
    if not dist_dir.exists():
        print(f"ERROR: dist 目录不存在: {dist_dir}")
        print("请先运行: npm run build --prefix frontend")
        sys.exit(1)

    chunks = []
    for f in dist_dir.glob("*.js"):
        raw_kb, gzip_kb = get_chunk_size_kb(f)
        chunks.append({
            "name": f.name,
            "raw_kb": round(raw_kb, 1),
            "gzip_kb": round(gzip_kb, 1),
            "is_first_screen": is_first_screen(f.name),
        })

    # 按原始体积降序
    chunks.sort(key=lambda x: x["raw_kb"], reverse=True)

    first_screen = [c for c in chunks if c["is_first_screen"]]
    lazy_chunks = [c for c in chunks if not c["is_first_screen"]]

    first_screen_raw = sum(c["raw_kb"] for c in first_screen)
    first_screen_gzip = sum(c["gzip_kb"] for c in first_screen)
    total_raw = sum(c["raw_kb"] for c in chunks)
    total_gzip = sum(c["gzip_kb"] for c in chunks)

    print("=" * 70)
    print("前端 Bundle 体积报告")
    print("=" * 70)
    print(f"总 chunk 数: {len(chunks)} (首屏 {len(first_screen)} + 按需 {len(lazy_chunks)})")
    print(f"总体积: {total_raw:.1f} KB (gzip ~{total_gzip:.1f} KB)")
    print(f"首屏体积: {first_screen_raw:.1f} KB (gzip ~{first_screen_gzip:.1f} KB)")
    print(f"首屏阈值: {args.threshold} KB gzip")
    if first_screen_gzip > args.threshold:
        print(f"[WARN] 超阈值: 首屏 gzip {first_screen_gzip:.1f} KB > {args.threshold} KB")
    else:
        print(f"[OK] 符合目标: 首屏 gzip {first_screen_gzip:.1f} KB <= {args.threshold} KB")

    print()
    print("── 首屏必需 chunk ──")
    for c in first_screen:
        print(f"  {c['name']:<50} {c['raw_kb']:>8.1f} KB  gzip {c['gzip_kb']:>6.1f} KB")

    print()
    print("── Top 10 大 chunk（按需加载） ──")
    for c in lazy_chunks[:10]:
        print(f"  {c['name']:<50} {c['raw_kb']:>8.1f} KB  gzip {c['gzip_kb']:>6.1f} KB")

    # 写入 bundle-size.json 作为基线
    report = {
        "total_chunks": len(chunks),
        "total_raw_kb": round(total_raw, 1),
        "total_gzip_kb": round(total_gzip, 1),
        "first_screen_raw_kb": round(first_screen_raw, 1),
        "first_screen_gzip_kb": round(first_screen_gzip, 1),
        "threshold_kb": args.threshold,
        "over_threshold": first_screen_gzip > args.threshold,
        "chunks": chunks,
    }
    report_path = dist_dir.parent / "bundle-size.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print()
    print(f"体积报告已写入: {report_path}")

    if first_screen_gzip > args.threshold:
        sys.exit(2)


if __name__ == "__main__":
    main()
