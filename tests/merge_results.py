# -*- coding: utf-8 -*-
"""合并所有测试日志, 生成最终汇总报告 (results_final.json + results_final.txt)"""
import json
import glob
import os

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots", "ai_chat_scenarios")

# 合并: 同 id 取最新
merged = {}
for f in sorted(glob.glob(os.path.join(D, "results_*.json")), key=os.path.getmtime):
    data = json.load(open(f, encoding="utf-8"))
    for sc in data["scenarios"]:
        sid = sc["id"]
        if sid in merged:
            if merged[sid].get("end_at", "") < sc.get("end_at", ""):
                merged[sid] = sc
        else:
            merged[sid] = sc

scenarios = [merged[k] for k in sorted(merged.keys())]

# 统计
total = len(scenarios)
pass_n = sum(1 for s in scenarios if s["status"] == "pass")
fail_n = sum(1 for s in scenarios if s["status"] == "fail")
err_n = sum(1 for s in scenarios if s["status"] == "error")
rounds_ok = sum(1 for s in scenarios for r in s.get("rounds", []) if r.get("error") is None and r.get("status_code") == 200)
rounds_total = sum(len(s.get("rounds", [])) for s in scenarios)
avg_time = sum(r["elapsed_sec"] for s in scenarios for r in s.get("rounds", [])) / rounds_total if rounds_total else 0

# JSON
out_json = os.path.join(D, "results_final.json")
with open(out_json, "w", encoding="utf-8") as f:
    json.dump({
        "total": total, "pass": pass_n, "fail": fail_n, "error": err_n,
        "rounds_ok": rounds_ok, "rounds_total": rounds_total, "avg_resp_sec": round(avg_time, 2),
        "scenarios": scenarios,
    }, f, ensure_ascii=False, indent=2)

# TXT
out_txt = os.path.join(D, "results_final.txt")
with open(out_txt, "w", encoding="utf-8") as f:
    f.write("AI 智能助手多轮对话测试 - 最终汇总报告\n")
    f.write("=" * 80 + "\n")
    f.write(f"场景总数: {total} | 通过 {pass_n} | 失败 {fail_n} | 错误 {err_n}\n")
    f.write(f"轮次级: {rounds_ok}/{rounds_total} 成功 ({rounds_ok*100//rounds_total if rounds_total else 0}%)\n")
    f.write(f"平均响应时间: {avg_time:.2f}s\n")
    f.write("=" * 80 + "\n\n")
    for sc in scenarios:
        icon = "PASS" if sc["status"] == "pass" else ("FAIL" if sc["status"] == "fail" else "ERR")
        f.write(f"[{icon}] 场景 {sc['id']:>2}: {sc['name']}\n")
        if sc.get("error"):
            f.write(f"      错误: {sc['error']}\n")
        for r in sc.get("rounds", []):
            err_tag = "  ❌" if r.get("error") else ""
            f.write(f"      R{r['round']} [{r['status_code']}] {r['elapsed_sec']}s ({r['reply_len']} chars){err_tag}\n")
            if r.get("error"):
                f.write(f"         error: {r['error']}\n")
        f.write("\n")

print(f"已生成: {out_json}")
print(f"已生成: {out_txt}")
print(f"总计: {total} | 通过 {pass_n} | 失败 {fail_n} | 错误 {err_n}")
print(f"轮次级: {rounds_ok}/{rounds_total} ({rounds_ok*100//rounds_total if rounds_total else 0}%)")
print(f"平均响应: {avg_time:.2f}s")
