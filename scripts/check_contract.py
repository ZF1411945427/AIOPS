"""CONTRACT.md 字段漂移检测脚本（P2 任务#8）

解析 CONTRACT.md 提取字段规范 → 解析 models.py / routers/*.py 提取实际字段使用 →
对照输出 diff 报告：违规字段、缺失字段、命名规则违规、长度规范违规。

核心逻辑已封装在 app/services/contract_check_service.py，本脚本通过 sys.path 引入并复用。

用法:
    python scripts/check_contract.py              # 控制台报告
    python scripts/check_contract.py --json        # JSON 输出
    python scripts/check_contract.py --out report.json  # 写入文件

路径规范: 全部基于 __file__ 动态计算，禁止硬编码绝对路径。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# ── 路径计算（基于 __file__，禁止硬编码）──
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
# 加入 sys.path 以便 import app.services.contract_check_service
sys.path.insert(0, str(_PROJECT_ROOT))

from app.services.contract_check_service import check_contract as _check_contract  # noqa: E402


def format_text_report(report: dict) -> str:
    """生成控制台友好文本报告。"""
    lines: list = []
    s = report["summary"]
    lines.append("=" * 72)
    lines.append("CONTRACT.md 字段漂移检测报告")
    lines.append("=" * 72)
    lines.append(f"CONTRACT.md 表数: {s['total_tables_in_contract']}")
    lines.append(f"models.py 表数:   {s['total_tables_in_models']}")
    lines.append(f"违规总数:         {s['total_violations']} (高置信度: {s['high_confidence_count']})")
    lines.append(f"  - CONTRACT 标注违规字段仍使用: {s['contract_violations_count']}")
    lines.append(f"  - 废弃字段仍在使用:           {s['deprecated_usage_count']}")
    lines.append(f"  - 命名规则违规:               {s['naming_violations_count']}")
    lines.append(f"  - 长度规范违规:               {s['length_violations_count']}")
    lines.append(f"结论: {'✅ 全部通过' if s['passed'] else '❌ 存在违规（高置信度）'}")
    lines.append("")

    if report["contract_violations"]:
        lines.append("── CONTRACT.md 标注违规字段仍使用 ──")
        for v in report["contract_violations"]:
            loc = []
            if v["in_models"]:
                loc.append("models")
            if v["in_routers"]:
                loc.append(f"routers:{','.join(v['router_files'][:3])}")
            lines.append(
                f"  [{v['table']}] {v['field']} → {v['should_be']}  "
                f"[{v['confidence']}]  位置: {','.join(loc)}  原因: {v['reason']}"
            )
        lines.append("")

    if report["deprecated_usage"]:
        lines.append("── 废弃字段仍在使用 ──")
        for v in report["deprecated_usage"]:
            loc = []
            if v["in_models"]:
                loc.append("models")
            if v.get("router_files"):
                loc.append(f"routers:{','.join(v['router_files'][:3])}")
            lines.append(
                f"  [{v['table']}] {v['field']} 已废弃，替代: {v['replace_with']}  "
                f"[{v['confidence']}]  位置: {','.join(loc)}"
            )
        lines.append("")

    if report["naming_violations"]:
        lines.append("── 命名规则违规 ──")
        for v in report["naming_violations"]:
            lines.append(f"  [{v['table']}] {v['field']} ({v['type']}) — {v['rule']}")
        lines.append("")

    if report["length_violations"]:
        lines.append("── 长度规范违规 ──")
        for v in report["length_violations"]:
            lines.append(
                f"  [{v['table']}] {v['field']} 实际长度={v['actual']} 期望={v['expected']}"
            )
        lines.append("")

    return "\n".join(lines)


def main():
    # Windows 控制台默认 GBK，强制 UTF-8 输出
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="CONTRACT.md 字段漂移检测")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--out", type=str, default="", help="写入指定文件")
    args = parser.parse_args()

    report = _check_contract()

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = _PROJECT_ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告已写入: {out_path}")
        print(format_text_report(report))
    elif args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(report))

    # 退出码: 0=通过, 1=有违规
    sys.exit(0 if report["summary"]["passed"] else 1)


if __name__ == "__main__":
    main()

