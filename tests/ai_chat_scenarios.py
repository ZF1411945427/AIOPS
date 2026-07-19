# -*- coding: utf-8 -*-
"""
AI 智能助手多轮对话测试脚本

依据 docs/AI智能助手多轮对话测试场景.md 自动化执行 32 个测试场景。
- 场景 1-4:  关联告警 / 关联资产 / 关联分析 / 知识自动沉淀 (核心 happy path)
- 场景 5-7:  模糊指代 / 闲聊 / 空结果 (简单边界)
- 场景 8-17: 多轮澄清 / 告警风暴 / 级联溯源 / 实时跟踪 / 工具降级 /
             用户纠正 / 权限脱敏 / 对比预测 / 上下文跳跃 / 知识冲突 (复杂)
- 场景 18-22: 夜间无人值守 / 知识遗忘 / 自愈闭环 / 跨多云 / 安全事件 (复杂)
- 场景 23-32: 三按钮 (关联告警 / 关联资产 / 关联分析) 交互场景

用法:
    python tests/ai_chat_scenarios.py                 # 跑全部 32 个场景
    python tests/ai_chat_scenarios.py 1 2 3           # 只跑指定场景
    python tests/ai_chat_scenarios.py --range 1-4     # 跑范围
    python tests/ai_chat_scenarios.py --no-llm        # 仅校验接口连通性, 不等 LLM 响应
"""
import os
import sys
import json
import time
import sqlite3
import argparse
import traceback
from datetime import datetime
from typing import Optional, Dict, List, Any

import requests

# ---------- 路径基于 __file__ 动态计算 (遵循 AGENTS.md 路径契约) ----------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "db", "aiops.db")
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots", "ai_chat_scenarios")

BASE_URL = os.environ.get("AIOPS_BASE_URL", "http://127.0.0.1:8000")
USERNAME = os.environ.get("AIOPS_USER", "admin")
PASSWORD = os.environ.get("AIOPS_PWD", "admin123")

# LLM 单轮最大等待秒数
LLM_TIMEOUT = 180
# 单场景失败时是否继续后续场景
CONTINUE_ON_FAIL = True


# ---------- 测试数据准备: 从数据库挑可用的告警/资产 ----------
def fetch_test_data() -> Dict[str, Any]:
    """从 sqlite 挑选可用告警和资产 ID 供按钮场景使用"""
    if not os.path.exists(DB_PATH):
        print(f"[WARN] 数据库不存在: {DB_PATH}")
        return {"alerts": [], "assets": []}
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # 优先挑有 asset_id 的告警, 各级别都来一些
    cur.execute(
        "SELECT id, asset_id, severity, metric_name, message FROM alerts "
        "WHERE asset_id IS NOT NULL ORDER BY id DESC LIMIT 20"
    )
    alerts = [
        {"id": r[0], "asset_id": r[1], "severity": r[2],
         "metric": r[3], "message": r[4]}
        for r in cur.fetchall()
    ]
    cur.execute("SELECT id, name, ip, ci_type FROM assets ORDER BY id LIMIT 30")
    assets = [
        {"id": r[0], "name": r[1], "ip": r[2], "ci_type": r[3]}
        for r in cur.fetchall()
    ]
    conn.close()
    return {"alerts": alerts, "assets": assets}


# ---------- 32 个场景定义 ----------
def build_scenarios(test_data: Dict) -> List[Dict]:
    """构建 32 个测试场景。按钮场景的 alert_id/asset_id 从测试数据中取。"""
    alerts = test_data["alerts"]
    assets = test_data["assets"]

    # 取一些可用的 ID (带兜底)
    alert_ids = [a["id"] for a in alerts] or [1, 2, 3]
    asset_ids = [a["id"] for a in assets] or [1, 2, 3]
    alert_assets = {a["id"]: a.get("asset_id") for a in alerts}

    # 挑 3 条不同资产的告警用于场景 23 (多告警注入)
    multi_alerts = alert_ids[:3]
    # 挑 3 个不同资产用于场景 25
    multi_assets = asset_ids[:3]
    # 挑 1 个资产用于场景 26 单资产巡检
    single_asset = asset_ids[0] if asset_ids else 1
    # 挑 5 条告警用于场景 29 / 31
    five_alerts = alert_ids[:5]
    # 25 条告警用于场景 31 (告警风暴); 若不够则循环填充
    storm_alerts = (alert_ids * ((25 // len(alert_ids)) + 1))[:25] if alert_ids else list(range(1, 26))

    # 被攻击资产 (场景 32): 用现有资产 ID, AI 应识别为安全事件
    attacked_asset = asset_ids[-1] if asset_ids else 1

    scenarios = [
        # ==================== 场景 1-4: 核心 happy path ====================
        {
            "id": 1, "name": "关联告警多轮对话",
            "rounds": [
                {"user": "我刚才收到了一个 CPU 告警，发生在 server-001 这台服务器上，级别是 critical，这是什么情况？"},
                {"user": "能帮我分析一下这个告警的根因吗？可能是什么原因导致的？"},
                {"user": "这个问题解决了，帮我生成一个故障记录存到知识库，方便以后参考"},
            ],
        },
        {
            "id": 2, "name": "关联资产多轮对话",
            "rounds": [
                {"user": "server-001 这台服务器现在什么情况？帮我做个全面检查"},
                {"user": "database-01 错误率偏高是怎么回事？跟 server-001 有关吗？"},
                {"user": "帮我搜一下知识库里有没有类似的案例，数据库连接超时的问题以前怎么处理的？"},
            ],
        },
        {
            "id": 3, "name": "关联分析多轮对话",
            "rounds": [
                {"user": "帮我分析一下 payment 服务最近 2 小时的情况，看看有没有什么问题"},
                {"user": "能具体说说是哪次配置变更导致的问题吗？是什么时候改的？"},
            ],
        },
        {
            "id": 4, "name": "知识自动沉淀多轮对话",
            "rounds": [
                {"user": "故障单 #10 已经解决了，这个故障之前是因为数据库连接池耗尽导致的，处理方法是扩大了 max_connections。帮我把这个处理过程沉淀到知识库。"},
                {"user": "确认，提交审批"},
                {"user": "帮我看看知识库里有哪些跟数据库故障相关的知识"},
            ],
        },
        # ==================== 场景 5-7: 简单边界 ====================
        {
            "id": 5, "name": "模糊指代与输入纠错",
            "rounds": [
                {"user": "刚才那个 CPU 高的告警，啥情况？"},
                {"user": "帮我看看 server001 的情况"},
                {"user": "昨天那会儿 payment 服务有什么告警吗？"},
            ],
        },
        {
            "id": 6, "name": "纯闲聊与单点事实查询",
            "rounds": [
                {"user": "你好"},
                {"user": "database-01 现在连接数多少？"},
                {"user": "这个数算高吗？"},
            ],
        },
        {
            "id": 7, "name": "空结果与异常输入处理",
            "rounds": [
                {"user": "帮我查一下 nonexistent-server-999 的告警"},
                {"user": "搜一下知识库里有没有\"量子计算机故障\"相关案例"},
                {"user": "查一下 payment 服务 9999 小时前的告警"},
            ],
        },
        # ==================== 场景 8-17: 复杂运维 ====================
        {
            "id": 8, "name": "多轮澄清(AI 主动反问)",
            "rounds": [
                {"user": "出问题了，帮我看看"},
                {"user": "payment 服务，刚才"},
                {"user": "最近 30 分钟，做个整体关联分析吧"},
            ],
        },
        {
            "id": 9, "name": "告警风暴降噪",
            "rounds": [
                {"user": "payment 服务刚才炸了，告警刷屏，帮我理一下"},
                {"user": "被合并的告警具体有哪些？"},
            ],
        },
        {
            "id": 10, "name": "跨服务级联故障拓扑溯源",
            "rounds": [
                {"user": "payment 服务响应很慢，P99 飙到 2 秒了，什么情况？"},
                {"user": "redis-01 怎么了？详细说说"},
            ],
        },
        {
            "id": 11, "name": "实时诊断与动态跟踪",
            "rounds": [
                {"user": "payment 现在还在报错，帮我盯着"},
                {"user": "现在呢？还在报错吗？"},
                {"user": "好像好了"},
            ],
        },
        {
            "id": 12, "name": "工具调用失败降级",
            "rounds": [
                {"user": "帮我分析 payment 服务最近 2 小时"},
                {"user": "那查一下 server-001 的告警"},
            ],
        },
        {
            "id": 13, "name": "用户纠正 AI 错误根因",
            "rounds": [
                {"user": "server-001 CPU 飙高是什么原因？"},
                {"user": "不对，我刚做了部署，应该是部署引起的"},
                {"user": "那这个部署有问题的话，怎么回滚？"},
            ],
        },
        {
            "id": 14, "name": "权限边界与敏感数据脱敏",
            "rounds": [
                {"user": "帮我查一下 finance-db 这个核心数据库的告警"},
                {"user": "看一下 server-001 的应用配置文件内容"},
                {"user": "查一下 server-001 最近的 ERROR 日志"},
            ],
        },
        {
            "id": 15, "name": "对比分析与趋势预测",
            "rounds": [
                {"user": "对比一下 payment 和 order 两个服务今天的健康度"},
                {"user": "payment 服务本周和上周比，P99 延迟有变化吗？"},
                {"user": "按这个趋势，database-01 连接数什么时候会到上限？"},
            ],
        },
        {
            "id": 16, "name": "上下文跳跃与多人协同",
            "rounds": [
                {"user": "帮我看看 server-001 的 CPU"},
                {"user": "对了，知识库里有没有 redis 持久化的最佳实践？"},
                {"user": "回到刚才 server-001 的问题，它的内存怎么样？"},
                {"user": "补充一下，server-001 半小时前有人手动重启过"},
            ],
        },
        {
            "id": 17, "name": "知识冲突与误报识别",
            "rounds": [
                {"user": "数据库连接池到底设多大合适？查一下知识库"},
                {"user": "server-001 一直报 CPU 100%，但我看监控明明是 20%"},
            ],
        },
        # ==================== 场景 18-22: 真实复杂运维 ====================
        {
            "id": 18, "name": "夜间无人值守告警与冷静判断",
            "rounds": [
                {"user": "刚收到告警，server-001 半夜 CPU 飙到 92% 了，这个严重吗？需要现在处理吗？"},
                {"user": "被你猜中了，确实是 cron 定时任务，凌晨跑日志压缩的。那这个告警还要留着吗？要不要做点什么优化？"},
                {"user": "我已经改了告警规则，加了持续 3 分钟才触发。也改了定时任务加了 nice 19。帮我验证一下效果。"},
            ],
        },
        {
            "id": 19, "name": "知识遗忘与重新发现",
            "rounds": [
                {"user": "database-01 的连接池应该设多大？帮我查查知识库"},
                {"user": "确实忘了已经升级到 8.0 了。那 128 是推荐值的话，改成 128 安全吗？改之前要不要先验证一下峰值连接数？"},
            ],
        },
        {
            "id": 20, "name": "自愈闭环验证",
            "rounds": [
                {"user": "刚收到通知，server-001 的 CPU 告警已经自动恢复了。但我看到这个告警这周已经出现了好几次，是不是自愈只是临时解决了？"},
                {"user": "分析得很清楚。那就按你说的，把 nginx worker_connections 改到 2048，同时把自愈流程也优化一下。"},
            ],
        },
        {
            "id": 21, "name": "跨多云环境排障",
            "rounds": [
                {"user": "杭州用户说支付很慢，但新加坡用户说正常。payment 服务部署在新加坡 AWS，杭州的 api-gateway 调新加坡的 payment。帮我看看是不是跨云网络有问题？"},
                {"user": "联系云厂商了，他们说今天亚太区域有光缆故障，正在修复中。那我能不能临时把新加坡的流量切到杭州来？"},
            ],
        },
        {
            "id": 22, "name": "安全事件应急响应",
            "rounds": [
                {"user": "收到一个安全告警，server-003 有异常外连流量，目标 IP 45.33.32.156 已知是恶意 IP。现在该怎么办？要不要直接隔离这台服务器？"},
                {"user": "server-003 已经隔离了，网络已切断，保留 SSH 可以访问。现在帮我分析一下那个可疑文件和登录记录。"},
                {"user": "清除完毕，server-003 已恢复。这次入侵的根本原因是什么？要怎么防止以后再发生？"},
            ],
        },
        # ==================== 场景 23-32: 三按钮交互 ====================
        {
            "id": 23, "name": "关联告警按钮-多告警注入主从识别",
            "pre_action": {"type": "link_alert", "alert_ids": multi_alerts},
            "rounds": [
                {"user": "这 3 条告警是什么关系？哪个是根因？"},
                {"user": "帮我深入看一下 #103 database-01 那条"},
                {"user": "我又加了 #102 和 #104，重新分析一下", "extra_action": {"type": "link_alert", "alert_ids": alert_ids[3:5]}},
            ],
        },
        {
            "id": 24, "name": "关联告警按钮-跨资产告警链推理",
            "pre_action": {"type": "link_alert", "alert_ids": multi_alerts},
            "rounds": [
                {"user": "这 3 条告警来自不同资产，有联系吗？"},
                {"user": "下钻到 redis-01 看看"},
            ],
        },
        {
            "id": 25, "name": "关联资产按钮-多资产注入联合诊断",
            "pre_action": {"type": "link_asset", "asset_ids": multi_assets},
            "rounds": [
                {"user": "这 3 个资产现在联合状态怎么样？有相互影响吗？"},
                {"user": "如果 redis-01 修好了，server-001 的 P99 能恢复正常吗？"},
            ],
        },
        {
            "id": 26, "name": "关联资产按钮-单资产端到端巡检",
            "pre_action": {"type": "link_asset", "asset_ids": [single_asset]},
            "rounds": [
                {"user": "帮我给 payment-service 做个全面巡检"},
                {"user": "对比一下 v2.3.0 和 v2.3.1 的指标差异"},
            ],
        },
        {
            "id": 27, "name": "关联分析按钮-深度根因下钻与反驳",
            "pre_action": {"type": "correlation_analyze", "hours": 2, "service": "payment"},
            "rounds": [
                {"user": "请基于注入的关联分析数据开始深度下钻分析"},
                {"user": "不对，连接池变更前已经有 connection timeout 了，我自己看了日志"},
                {"user": "对，深挖一下 database-01 慢查询"},
            ],
        },
        {
            "id": 28, "name": "关联分析按钮-时间窗多轮收敛",
            "pre_action": {"type": "correlation_analyze", "hours": 2, "service": "payment"},
            "rounds": [
                {"user": "先看 payment 服务最近 2 小时整体情况"},
                {"user": "收敛到 1 小时，再看一下", "extra_action": {"type": "correlation_analyze", "hours": 1, "service": "payment"}},
                {"user": "再聚焦到 payment-api 资产", "extra_action": {"type": "correlation_analyze", "hours": 1, "service": "payment", "asset_id": single_asset}},
            ],
        },
        {
            "id": 29, "name": "三按钮端到端联动排障",
            "pre_action": {"type": "link_alert", "alert_ids": five_alerts},
            "rounds": [
                {"user": "先看看这 5 条告警的关系"},
                {"user": "注入这 3 个资产，看看联合状态", "extra_action": {"type": "link_asset", "asset_ids": multi_assets}},
                {"user": "做一次完整关联分析验证一下", "extra_action": {"type": "correlation_analyze", "hours": 1, "service": "payment"}},
            ],
        },
        {
            "id": 30, "name": "三按钮边界-注入失败与空结果降级",
            "rounds": [
                {"user": "帮我分析 nonexistent-999 这个资产", "extra_action": {"type": "link_asset", "asset_ids": [99999]}},
                {"user": "搜一下知识库里有没有\"量子计算机故障\"相关案例"},
            ],
        },
        {
            "id": 31, "name": "关联告警按钮-告警风暴批量注入降噪",
            "pre_action": {"type": "link_alert", "alert_ids": storm_alerts},
            "rounds": [
                {"user": "25 条告警太多了，帮我理一下"},
                {"user": "展开簇 #1 看看 15 条都是啥"},
            ],
        },
        {
            "id": 32, "name": "关联资产按钮-注入被攻击资产触发安全应急",
            "pre_action": {"type": "link_asset", "asset_ids": [attacked_asset]},
            "rounds": [
                {"user": "server-003 收到安全告警，帮我看看"},
                {"user": "已隔离，网络切断了。现在分析一下那个可疑文件"},
            ],
        },
    ]
    return scenarios


# ---------- 测试执行器 ----------
class ScenarioRunner:
    def __init__(self):
        self.session = requests.Session()
        self.token: Optional[str] = None
        self.results: List[Dict] = []
        self.log_dir = LOG_DIR

    def login(self) -> bool:
        try:
            r = self.session.post(
                f"{BASE_URL}/login",
                json={"username": USERNAME, "password": PASSWORD},
                timeout=15,
            )
            data = r.json()
            if data.get("ok"):
                self.token = data.get("token")
                print(f"[LOGIN] OK user={USERNAME} token={self.token[:20]}...")
                return True
            print(f"[LOGIN] FAIL: {data}")
            return False
        except Exception as e:
            print(f"[LOGIN] ERROR: {e}")
            return False

    def create_session(self, title: str = "测试会话") -> Optional[int]:
        try:
            r = self.session.post(f"{BASE_URL}/agent/session/new", timeout=15)
            if r.status_code == 200:
                sid = r.json().get("session_id")
                # 重命名
                if sid:
                    try:
                        self.session.post(
                            f"{BASE_URL}/agent/session/{sid}/rename",
                            json={"title": title}, timeout=10
                        )
                    except Exception:
                        pass
                return sid
            print(f"[NEW SESSION] status={r.status_code} body={r.text[:200]}")
            return None
        except Exception as e:
            print(f"[NEW SESSION] ERROR: {e}")
            return None

    def link_alert(self, sid: int, alert_id: int) -> Dict:
        try:
            r = self.session.post(
                f"{BASE_URL}/agent/session/{sid}/link-alert",
                json={"alert_id": alert_id}, timeout=15
            )
            return {"status_code": r.status_code, "body": self._safe_json(r)}
        except Exception as e:
            return {"status_code": -1, "body": {}, "error": str(e)}

    def link_asset(self, sid: int, asset_id: int) -> Dict:
        try:
            r = self.session.post(
                f"{BASE_URL}/agent/session/{sid}/link-asset",
                json={"asset_id": asset_id}, timeout=15
            )
            return {"status_code": r.status_code, "body": self._safe_json(r)}
        except Exception as e:
            return {"status_code": -1, "body": {}, "error": str(e)}

    def correlation_analyze(self, hours: int, service: str, asset_id: int = 0) -> Dict:
        """注意: correlation-analyze 会创建新会话并返回 session_id"""
        try:
            payload = {"hours": hours, "service": service}
            if asset_id:
                payload["asset_id"] = asset_id
            r = self.session.post(
                f"{BASE_URL}/agent/correlation-analyze",
                json=payload, timeout=60
            )
            return {"status_code": r.status_code, "body": self._safe_json(r)}
        except Exception as e:
            return {"status_code": -1, "body": {}, "error": str(e)}

    def send_message(self, sid: int, message: str) -> Dict:
        try:
            r = self.session.post(
                f"{BASE_URL}/agent/chat/send",
                json={"session_id": sid, "message": message},
                timeout=LLM_TIMEOUT,
            )
            return {"status_code": r.status_code, "body": self._safe_json(r)}
        except requests.exceptions.Timeout:
            return {"status_code": -1, "body": {}, "error": "timeout"}
        except Exception as e:
            return {"status_code": -1, "body": {}, "error": str(e)}

    def get_history(self, sid: int) -> Dict:
        try:
            r = self.session.get(f"{BASE_URL}/agent/history/{sid}", timeout=15)
            return {"status_code": r.status_code, "body": self._safe_json(r)}
        except Exception as e:
            return {"status_code": -1, "body": {}, "error": str(e)}

    def _safe_json(self, r):
        try:
            return r.json()
        except Exception:
            return {"_raw": r.text[:500]}

    # ---------- 单场景执行 ----------
    def run_scenario(self, scenario: Dict) -> Dict:
        sid: Optional[int] = None
        sc_id = scenario["id"]
        sc_name = scenario["name"]
        rounds = scenario.get("rounds", [])
        pre_action = scenario.get("pre_action")

        print(f"\n{'='*70}")
        print(f"[SCENARIO {sc_id}] {sc_name}")
        print(f"{'='*70}")

        sc_result = {
            "id": sc_id, "name": sc_name,
            "start_at": datetime.now().isoformat(),
            "rounds": [], "status": "pending", "error": None,
        }

        try:
            # 1. 创建会话 (correlation_analyze 预操作会自建会话, 跳过)
            if not pre_action or pre_action.get("type") != "correlation_analyze":
                sid = self.create_session(f"[场景{sc_id}] {sc_name}")
                if not sid:
                    sc_result["status"] = "fail"
                    sc_result["error"] = "创建会话失败"
                    print(f"  [FAIL] 创建会话失败")
                    return sc_result

            # 2. 预操作 (按钮注入)
            if pre_action:
                pa_type = pre_action.get("type")
                if pa_type == "link_alert":
                    for aid in pre_action.get("alert_ids", []):
                        res = self.link_alert(sid, aid)
                        print(f"  [PRE link-alert] alert_id={aid} -> {res['status_code']}")
                        if res["status_code"] != 200:
                            print(f"    body: {res['body']}")
                elif pa_type == "link_asset":
                    for aid in pre_action.get("asset_ids", []):
                        res = self.link_asset(sid, aid)
                        print(f"  [PRE link-asset] asset_id={aid} -> {res['status_code']}")
                        if res["status_code"] != 200:
                            print(f"    body: {res['body']}")
                elif pa_type == "correlation_analyze":
                    res = self.correlation_analyze(
                        hours=pre_action.get("hours", 1),
                        service=pre_action.get("service", ""),
                        asset_id=pre_action.get("asset_id", 0),
                    )
                    print(f"  [PRE correlation-analyze] -> {res['status_code']}")
                    new_sid = res.get("body", {}).get("session_id")
                    if new_sid:
                        sid = new_sid
                        print(f"  [PRE] 切换到关联分析会话 sid={sid}")
                    else:
                        print(f"    body: {res['body']}")
                        # 降级: 自建会话
                        sid = self.create_session(f"[场景{sc_id}] {sc_name}")

            # 3. 多轮对话
            for idx, rnd in enumerate(rounds, 1):
                user_msg = rnd["user"]
                extra = rnd.get("extra_action")

                # 轮次内的额外按钮注入 (如场景 23 第3轮 / 28 第2-3轮 / 29 第2-3轮 / 30 第1轮)
                if extra:
                    et = extra.get("type")
                    if et == "link_alert":
                        for aid in extra.get("alert_ids", []):
                            res = self.link_alert(sid, aid)
                            print(f"  [R{idx} link-alert] alert_id={aid} -> {res['status_code']}")
                    elif et == "link_asset":
                        for aid in extra.get("asset_ids", []):
                            res = self.link_asset(sid, aid)
                            print(f"  [R{idx} link-asset] asset_id={aid} -> {res['status_code']}")
                    elif et == "correlation_analyze":
                        # 收敛场景: 创建新会话并切换
                        res = self.correlation_analyze(
                            hours=extra.get("hours", 1),
                            service=extra.get("service", ""),
                            asset_id=extra.get("asset_id", 0),
                        )
                        print(f"  [R{idx} correlation-analyze] -> {res['status_code']}")
                        new_sid = res.get("body", {}).get("session_id")
                        if new_sid:
                            sid = new_sid

                print(f"\n  [R{idx}] USER> {user_msg}")
                t0 = time.time()
                res = self.send_message(sid, user_msg)
                elapsed = time.time() - t0
                reply = ""
                err = None
                body = res.get("body", {})
                if res["status_code"] == 200:
                    reply = body.get("reply", "") or body.get("_raw", "")
                    if body.get("error"):
                        err = body.get("reply") or "error"
                else:
                    err = body.get("error") or body.get("message") or f"HTTP {res['status_code']}"

                # 截断打印
                preview = (reply[:300] + "...") if len(reply) > 300 else reply
                print(f"  [R{idx}] AI> ({elapsed:.1f}s, {len(reply)} chars)")
                if preview:
                    print(f"    {preview}")
                if err:
                    print(f"  [R{idx}] ERROR: {err}")

                sc_result["rounds"].append({
                    "round": idx,
                    "user": user_msg,
                    "reply": reply,
                    "reply_len": len(reply),
                    "elapsed_sec": round(elapsed, 2),
                    "status_code": res["status_code"],
                    "error": err,
                    "extra_action": extra,
                })

                # 轮次间隔, 避免 LLM 限流
                if idx < len(rounds):
                    time.sleep(1)

            # 判定场景结果
            failed_rounds = [r for r in sc_result["rounds"] if r["error"] or r["status_code"] != 200]
            sc_result["status"] = "fail" if failed_rounds else "pass"
            if failed_rounds:
                sc_result["error"] = f"{len(failed_rounds)}/{len(rounds)} 轮失败"

        except Exception as e:
            sc_result["status"] = "error"
            sc_result["error"] = f"{type(e).__name__}: {e}"
            traceback.print_exc()

        sc_result["end_at"] = datetime.now().isoformat()
        sc_result["session_id"] = sid
        status_icon = "PASS" if sc_result["status"] == "pass" else "FAIL"
        print(f"\n  [{status_icon}] 场景 {sc_id} 结束: {sc_result.get('error') or '全部轮次成功'}")
        return sc_result

    # ---------- 保存日志 ----------
    def save_logs(self):
        os.makedirs(self.log_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 完整 JSON
        full_path = os.path.join(self.log_dir, f"results_{ts}.json")
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump({
                "run_at": ts,
                "base_url": BASE_URL,
                "username": USERNAME,
                "scenarios": self.results,
            }, f, ensure_ascii=False, indent=2)
        # 可读文本
        txt_path = os.path.join(self.log_dir, f"results_{ts}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"AI 智能助手多轮对话测试报告\n")
            f.write(f"运行时间: {ts}\n")
            f.write(f"基础URL: {BASE_URL}\n")
            f.write(f"用户: {USERNAME}\n")
            f.write(f"{'='*70}\n\n")
            for sc in self.results:
                f.write(f"场景 {sc['id']}: {sc['name']} [{sc['status'].upper()}]\n")
                if sc.get("error"):
                    f.write(f"  错误: {sc['error']}\n")
                f.write(f"  会话ID: {sc.get('session_id')}\n")
                f.write(f"  开始: {sc['start_at']}\n")
                f.write(f"  结束: {sc['end_at']}\n")
                for rnd in sc.get("rounds", []):
                    f.write(f"\n  --- 第 {rnd['round']} 轮 ---\n")
                    f.write(f"  用户: {rnd['user']}\n")
                    if rnd.get("extra_action"):
                        f.write(f"  [按钮注入: {rnd['extra_action']}]\n")
                    f.write(f"  状态码: {rnd['status_code']}, 耗时: {rnd['elapsed_sec']}s\n")
                    if rnd["error"]:
                        f.write(f"  错误: {rnd['error']}\n")
                    f.write(f"  AI回复 ({rnd['reply_len']} chars):\n")
                    f.write(f"  {rnd['reply']}\n")
                f.write(f"\n{'='*70}\n\n")
        return full_path, txt_path

    def print_summary(self):
        total = len(self.results)
        passed = sum(1 for r in self.results if r["status"] == "pass")
        failed = sum(1 for r in self.results if r["status"] == "fail")
        errored = sum(1 for r in self.results if r["status"] == "error")
        print(f"\n{'='*70}")
        print(f"测试摘要: 总计 {total} | 通过 {passed} | 失败 {failed} | 错误 {errored}")
        print(f"{'='*70}")
        for sc in self.results:
            icon = "OK" if sc["status"] == "pass" else "XX"
            err = f" - {sc['error']}" if sc.get("error") else ""
            print(f"  [{icon}] 场景 {sc['id']:>2}: {sc['name']}{err}")
        # 轮次级统计
        all_rounds = [r for sc in self.results for r in sc.get("rounds", [])]
        ok_rounds = sum(1 for r in all_rounds if r["error"] is None and r["status_code"] == 200)
        print(f"\n  轮次级: {ok_rounds}/{len(all_rounds)} 成功")
        if all_rounds:
            avg_time = sum(r["elapsed_sec"] for r in all_rounds) / len(all_rounds)
            print(f"  平均响应时间: {avg_time:.2f}s")


# ---------- 主入口 ----------
def parse_args():
    p = argparse.ArgumentParser(description="AI 智能助手多轮对话测试")
    p.add_argument("ids", nargs="*", type=int, help="指定场景 ID (空=全部)")
    p.add_argument("--range", dest="range_str", help="场景范围, 如 1-4")
    return p.parse_args()


def main():
    args = parse_args()
    test_data = fetch_test_data()
    print(f"[DATA] alerts={len(test_data['alerts'])} assets={len(test_data['assets'])}")
    if not test_data["alerts"]:
        print("[WARN] 数据库无告警数据, 按钮场景将使用兜底 ID")

    all_scenarios = build_scenarios(test_data)

    # 选择要跑的场景
    if args.ids:
        selected = [s for s in all_scenarios if s["id"] in args.ids]
    elif args.range_str:
        try:
            lo, hi = args.range_str.split("-")
            selected = [s for s in all_scenarios if int(lo) <= s["id"] <= int(hi)]
        except Exception:
            print(f"[ERR] 无效范围: {args.range_str}")
            return
    else:
        selected = all_scenarios

    print(f"[PLAN] 共 {len(selected)} 个场景待测试")
    print(f"[URL]  {BASE_URL}")
    print(f"[LOG]  {LOG_DIR}")

    runner = ScenarioRunner()
    if not runner.login():
        print("[FATAL] 登录失败, 终止")
        return

    full_path, txt_path = "", ""
    for idx, sc in enumerate(selected, 1):
        print(f"\n[PROGRESS] {idx}/{len(selected)} 场景 {sc['id']}")
        result = runner.run_scenario(sc)
        runner.results.append(result)
        # 增量保存: 每跑完一个场景就写日志, 避免超时丢失
        full_path, txt_path = runner.save_logs()
        if not CONTINUE_ON_FAIL and result["status"] in ("fail", "error"):
            print("[STOP] 首个失败场景出现, 终止 (设置 CONTINUE_ON_FAIL=True 可继续)")
            break

    runner.print_summary()
    if full_path:
        print(f"\n[LOG] 完整 JSON: {full_path}")
        print(f"[LOG] 文本报告: {txt_path}")


if __name__ == "__main__":
    main()
