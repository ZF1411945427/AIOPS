"""治理 except: pass —— 把裸 Exception 静默吞异常改为 logger.warning 记录。

安全策略:
  1. 只处理 except 后直接跟 pass(无任何语句)且该 except 是预期之外裸捕获的情况
  2. 保留 WebSocketDisconnect / asyncio.CancelledError / KeyboardInterrupt 等正常控制流
  3. 若 except 子句带注释或 pass 后注释含"预期"关键词, 保留 pass
  4. 每文件若无 logger 定义, 自动注入 `import logging` + `logger = logging.getLogger(__name__)`
  5. 错误变量统一用 `_exc`(下划线前缀几乎从不与业务代码冲突), 若原 except 已有 `as xx` 则复用 xx
  6. --dry-run 预览(默认) / --apply 真正写入
  7. --skip 可指定文件名(逗号分隔)跳过(如启动容错类文件)
"""
import re
import os
import argparse

APP_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

KEEP_EXC = ("WebSocketDisconnect", "asyncio.CancelledError", "CancelledError",
            "KeyboardInterrupt", "SystemExit", "ConnectionResetError",
            "TimeoutError", "asyncio.TimeoutError")

EXPECTED_KEYWORDS = ("预期", "正常", "忽略", "不处理", "已存在", "无需", "暂无",
                     "跳过", "可忽略", "无需处理", "不用", "already", "expected",
                     "ignore", "不存在时", "没有", "无此", "或缺", "初始化前",
                     "告警", "静默", "ORM", "optional", "可选", "找不到", "可能不存在",
                     "为空", "空时", "兜底", "降级", "回退")


def has_logger(src: str) -> bool:
    return bool(re.search(r"\blogger\b\s*=\s*", src)) or bool(
        re.search(r"\blog\s*=\s*logging\.getLogger", src)) or bool(
        re.search(r"(?:from\s+\S+\s+import|\bimport)\s+.*\blogger\b", src))


def find_import_block_end(lines):
    """返回 import 连续块的末尾索引(含空行前的最后一行 index+1)。正确处理多行括号 import。"""
    # 逐行扫描, 维护括号深度, 找到最后一个 import 语句完整结束的行
    end = None
    depth = 0
    i = 0
    # 先跳过文件头 docstring/注释
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.lstrip()
        # 统计括号深度变化
        depth += line.count("(") - line.count(")")
        is_import = stripped.startswith("import ") or stripped.startswith("from ")
        if is_import:
            # 记录这段 import 的起始(可能跨多行)
            seg_start = i
            while i < n:
                depth += lines[i].count("(") - lines[i].count(")")
                i += 1
                if depth <= 0 and not lines[i-1].rstrip().endswith("\\") and not lines[i-1].rstrip().endswith(","):
                    # 保守: 若括号已闭合且不是逗号续行, 视为段落结束
                    break
                if i >= n:
                    break
            end = i
            continue
        # 非 import 行
        if stripped and not stripped.startswith("#") and depth == 0:
            # 遇到第一个非 import/注释/空行的顶层语句, 停止
            if is_import is False:
                break
        i += 1
    return end


def inject_logger(src: str):
    if has_logger(src):
        return src, False
    lines = src.split("\n")
    anchor = find_import_block_end(lines)
    if anchor is not None:
        # 在 import 块末尾后插入
        snippet = "import logging\nlogger = logging.getLogger(__name__)"
        new_lines = lines[:anchor] + [snippet, ""] + lines[anchor:]
        return "\n".join(new_lines), True
    # 兜底: 文件末尾
    snippet = "\n\nimport logging\nlogger = logging.getLogger(__name__)\n"
    return src + snippet, True


def process_file(filepath: str, apply: bool, skip: set, summary: dict):
    name = os.path.basename(filepath)
    if name in skip:
        summary["skipped"] += 1
        return
    with open(filepath, encoding="utf-8") as f:
        lines = f.readlines()
    changed = []
    need_logger = False

    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)except\b(.*?):(.*)$", lines[i])
        if not m:
            i += 1
            continue
        indent, exc_clause, trailing = m.groups()
        clause_l = exc_clause.lower()
        if any(k in clause_l for k in ("websocketdisconnect", "cancellederror",
                                       "keyboardinterrupt", "systemexit",
                                       "connectionreseterror", "timeouterror")):
            i += 1
            continue
        if i + 1 >= len(lines):
            i += 1
            continue
        nm = re.match(r"^(\s*)pass\b(.*)$", lines[i + 1])
        if not nm:
            i += 1
            continue
        pass_comment = nm.group(2)
        if any(k in trailing for k in EXPECTED_KEYWORDS) or \
           any(k in pass_comment for k in EXPECTED_KEYWORDS):
            i += 2
            continue
        # 复用已有的异常变量名, 否则用 _exc
        em = re.search(r"\bas\s+(\w+)", exc_clause)
        if em:
            var = em.group(1)
        else:
            var = "_exc"
            # 若已存在同名(理论上 _exc 极少), 加序号
            n = 0
            base = "_exc"
            while re.search(rf"\b{base if n==0 else base+str(n)}\b", "".join(lines)):
                n += 1
                if n == 0:
                    continue
            var = base if n == 0 else base + str(n)
        exc_stripped = exc_clause.strip() or "Exception"
        lines[i] = f"{indent}except {exc_stripped} as {var}:{trailing}\n"
        lines[i + 1] = (f"{indent}    logger.warning(\"[except:pass] {exc_stripped}: %s\", "
                        f"{var}, exc_info=True)\n")
        need_logger = True
        changed.append(i + 1)
        i += 2

    if changed:
        summary["spots"] += len(changed)
        summary["files_changed"] += 1
        if apply:
            content = "".join(lines)
            content, injected = inject_logger(content)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)


def main():
    ap = argparse.ArgumentParser(description="except: pass 治理")
    ap.add_argument("--apply", action="store_true", help="真正写入(默认预览)")
    ap.add_argument("--path", default=APP_DIR)
    ap.add_argument("--skip", default="", help="逗号分隔跳过文件名, 如 main.py,startup.py")
    args = ap.parse_args()

    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    summary = {"files_changed": 0, "spots": 0, "skipped": 0}
    if os.path.isfile(args.path):
        process_file(args.path, args.apply, skip, summary)
    else:
        for root, _, files in os.walk(args.path):
            for f in files:
                if f.endswith(".py"):
                    process_file(os.path.join(root, f), args.apply, skip, summary)

    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"{mode} files_changed={summary['files_changed']} spots={summary['spots']} "
          f"skipped={summary['skipped']}")


if __name__ == "__main__":
    main()
