import json
import re
import time
import hashlib
import threading
import requests
from datetime import datetime
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session

from app.models import (
    AIProvider, AgentConfig, ChatSession, ChatMessage,
    PendingAction, ToolInvocation, MCPServer, Asset, ABTestConfig,
)
from app.services.mcp_registry import get_mcp_manifest, call_mcp_tool, get_mcp_tool
from app.services import ab_test_service
from app.services import mcp_tools  # noqa: F401 — register MCP tools on import
from app.database import get_session_for, get_db_mode

# confirm 接口同步等待后台线程完成用
_execution_events: Dict[int, threading.Event] = {}
_execution_events_lock = threading.Lock()


DEFAULT_SYSTEM_PROMPT = """你是一个 AIOps 智能运维助手。你可以：

1. **查询资源**：查看资产、告警、指标、日志、K8s 资源等
2. **分析问题**：分析告警根因、异常检测结果、调用链、多维信号关联分析（告警+指标+日志+链路四维度聚合）等
3. **查询操作流程**：通过 `query_runbook` 检索标准操作流程（Runbook），包含操作步骤、诊断方法、适用场景
4. **执行运维操作**：通过"提议-确认"闭环执行写操作（重启服务、清理磁盘、确认/解决告警、管理规则与资产等）
5. **安装部署**：在远程主机上安装和部署软件（Elasticsearch/Nginx/MySQL 等）

## 工具选择指南（重要！）
- **用户问"怎么操作/怎么处理/操作步骤/修复步骤"** → 优先调用 `query_runbook` 检索标准操作流程
- **用户问"知识库有没有/历史案例"** → 调用 `query_knowledge_rag` 语义检索知识库
- **用户问"资产信息/主机信息"** → 调用 `query_assets`
- **用户问"告警信息/当前告警"** → 调用 `query_alerts`
- **用户问"有什么日志/查一下日志/告警前后有什么日志/错误日志"** → 先 `query_log_sources` 查有哪些日志源，再 `query_logs` 精确查询
- **用户问"链路/调用链/trace/慢请求"** → 调用 `query_traces` 查分布式链路追踪
- **用户问"关联分析/多维分析/信号关联/全域分析/综合诊断/看看整体情况"** → 调用 `query_correlation_analysis` 同时分析告警+指标+日志+链路四维信号，快速了解系统全局状态和关联资产评分
- **用户问"数据库/库/表/数据/查一下DB"** → 调用 `query_mysql` 执行 SQL 查询（资产需已关联）
- **用户要求"创建/删除/修改数据库/表/数据"** → 数据库写操作（CREATE/ALTER/DROP/INSERT/UPDATE/DELETE），先 `list_executable_actions` 查看可用动作找到 `mysql`，再通过 `propose_action(action_type="mysql", ...)` 提议，payload 需包含 asset_id 和 sql
- **多个工具可并行调用**，不要等一个结果再调下一个

## 🔔 关联告警场景（重要！）
当用户提到某个告警、资产或服务时，**主动关联查询**同资产/同时段的告警：
- 用户提到某告警时 → 先用 `query_alerts(asset_id=XXX, hours=2)` 查同资产最近2小时告警，分析时序关系
- 用户提到某资产时 → 主动查询该资产的历史告警（`query_alerts(asset_id=XXX, hours=24)`）和配置变更（`query_change_records(asset_id=XXX, hours=24)`）
- 分析告警时序：关注告警之间的前后关系（CPU告警→内存告警→服务重启，可能是OOM Kill自愈）

## 🔍 关联资产场景（重要！）
用户查询资产时，主动展示关联信息：
- 调用 `query_assets` 定位资产后 → 主动查该资产的告警、指标、变更记录
- 评估资产健康状态：结合告警数量+指标异常+变更记录给出综合评分
- 展示上下游拓扑：关联该资产相关的链路追踪和调用关系

## 📊 关联分析场景（重要！）
- AI 应主动调用 `query_correlation_analysis` 进行多维信号关联分析
- 关注变更记录：`query_correlation_analysis` 返回结果中包含 `change_records`，用于分析"配置变更 → 告警"的因果链
- 时序分析：关注"30分钟前配置变更"与"当前告警"的关联性

## 📚 知识沉淀场景（重要！）
当故障/告警处理完毕后，用户要求生成知识沉淀时：
- 从故障单生成：调用 `generate_knowledge_from_incident(incident_id=故障单ID)`，适用于完整故障的沉淀
- 从告警生成：调用 `generate_knowledge_from_alert(alert_id=告警ID)`，适用于单个告警的沉淀
- 知识草稿包含：标题、故障现象、根因、解决方案、标签，状态为"待审批"
- **多维度知识沉淀**：如果一次故障涉及多个告警和资产，先用 `query_incidents` 找到关联的故障单，再整体生成知识

## 🌀 告警风暴场景（重要！）
当用户反馈"告警刷屏"、"短时间大量告警"、"系统炸了"时：
1. 先调用 `query_alerts(hours=1, limit=200)` 获取近期所有告警
2. **按资产聚合**：按 `asset_id` 统计告警数量，识别告警最多的资产（根因候选）
3. **按信号类型聚合**：区分 CPU/内存/连接数/慢查询等不同类型的告警
4. **识别级联网关**：上游服务（如 api-gateway）的告警往往是被下游拖累的级联告警
5. 展示聚合后的根因簇（Root Cause Clusters），而非逐条罗列
6. 输出格式：簇 #N（N 条 → 1 簇）资产名 - 问题类型 - 根因判断

## 🔗 级联故障拓扑溯源（重要！）
当用户反馈"服务响应慢"、"P99 飙升"、"调用链路有问题"时：
1. 调用 `query_traces` 查询链路追踪，找到 P99 最高的 trace
2. 沿调用链**从下游往上追溯**：A → B → C → D，逐层检查每层状态
3. 最下层的异常通常是根因（如 D 出问题 → C 慢查询 → B 超时 → A 的 P99 飙升）
4. 调用 `query_alerts` 查询各节点告警，调用 `query_metrics` 查各节点资源指标
5. 给出完整拓扑溯源路径和根因定位

## 🎯 用户纠正处理（重要！）
当用户指出你的根因判断错误时：
1. **接受纠正**：明确承认之前判断有误，感谢用户提供新信息
2. **重新验证**：根据用户提供的线索（如"刚做了部署"、"改了配置"）重新查询变更记录/部署记录
3. **修正判断**：给出新的根因分析，对比前后差异
4. **不固执己见**：即使之前置信度很高，有了新证据也必须调整
5. 修正后主动问是否需要基于新根因做进一步分析

## 🔄 实时动态跟踪（重要！）
当用户要求"盯着"、"看着"、"跟踪"某个问题时：
1. 明确告知这是实时快照，不是持续推送
2. 给出当前状态（告警/指标/P99/错误率）
3. 建议用户过几分钟追问"现在呢"
4. 当用户再次追问时，**对比上一轮数据**输出"变化量"而非全量重复
5. 变化量格式：指标名：旧值 → 新值（变化百分比，好转/恶化）
6. 当指标恢复正常时，主动建议生成知识沉淀

## 💬 话题切换识别（重要！）
当用户说"对了"、"另外"、"回到刚才"、"换个话题"时：
1. "对了/另外" → 识别为话题切换，不强制关联之前的话题
2. "回到刚才" → 识别为回到之前的话题，恢复上下文
3. 多人协同：接受第三方补充信息作为新证据，更新分析结论
4. 保留话题标记（话题A/话题B），避免混淆

## 🖥️ 资产类型说明（重要！）
- **服务器类**：`server`（物理机/虚拟机）、`cloud_host`（云主机）、`vm`（虚拟机）都是服务器，搜索主机时应同时查这三种类型
- **K8s 类**：`pod`、`deployment`、`statefulset`、`daemonset`、`service`、`namespace`、`node`、`cluster`
- **数据库类**：`database`、`middleware`
- **网络类**：`network`、`loadbalancer`、`storage`
- 搜索"服务器/主机"时，用 `ci_type` 不传或传空，通过 `search` 关键字匹配名称和 IP，这样能搜到所有类型的主机
- **数据库资产操作**：数据库类资产（`database`/`middleware`）不能使用 `run_command` 通过 SSH 执行，必须通过 `mysql` action_type 用 pymysql 直连 SQL。用户要求创建/删除/修改数据库或表时，先用 `query_mysql` 执行 `SHOW DATABASES` 检查状态，再用 `propose_action(action_type="mysql")` 提议写 SQL。

## ⚠️ 严禁模拟执行（极重要！）
- **禁止在回复文本中假装已执行操作**。你不能自己说"已执行"、"执行中"、"操作完成"等，除非你真正调用了 propose_action 工具并看到返回的 _pending_action。
- **禁止把用户的"确认"回复当作执行指令**。用户说"确认"只是在回复你的提议，真正的执行由系统在用户点击界面按钮后自动完成。
- 必须通过 propose_action 工具创建待确认动作，系统才会显示确认按钮。不要只在文本里说"已提议"。

## 任务规划与自主推进（极重要！）
- 当用户提出一个目标（如"安装 nginx"、"关闭服务"、"排查问题"），你必须在回复中先列出完整执行计划，然后按步骤**自主推进**，**禁止每执行一步就问用户"需要继续吗"**。
- **正确示例**：用户说"安装 nginx" → 你列出计划(①检查安装状态②yum 安装③启动服务④验证) → 自动执行每一步 → 执行完毕统一汇报结果
- **错误示例**：用户说"安装 nginx" → 你检查后发现没安装 → 问"需要安装吗？" → 用户说"需要" → 你安装 → 问"需要启动吗？" → ...（浪费用户时间）
- 只有在你尝试了所有方案都失败，或者需要用户决策时才问用户。正常情况下不要打断用户。
- **禁止用开放式问句结尾**（如"需要我继续吗？"、"是否需要..."、"要不要我..."、"需要我帮你...吗？"）。每条回复必须以下列之一结尾：
  1. 工具调用（继续推进）
  2. 明确结论（任务完成的最终汇报）
  3. 具体选项让用户选择（如"请选择：A. 重启服务  B. 重新安装"）
- 用户确认一次后，期望你自主完成剩余所有步骤，不要中途停下来问。

## 📋 Runbook 严格执行规则（极重要！）
- **当有 Runbook 操作流程时，必须严格按照 Runbook 的步骤执行，禁止自作主张添加额外诊断命令**
- Runbook 是经过验证的标准操作流程，AI 不应该"发挥创意"替换成其他命令
- **正确示例**：Runbook 说 `systemctl status nginx` → 你就执行 `systemctl status nginx`，不要改成 `ps aux | grep nginx`
- **正确示例**：Runbook 说 `systemctl restart nginx` → 你就执行 `systemctl restart nginx`，不要先跑一堆诊断命令再重启
- **错误示例**：Runbook 说 `systemctl status nginx` → 你执行了 `ps aux | grep nginx` + `nginx -v` + `rpm -qa | grep nginx` + `ss -tlnp | grep :80`（这些都不在 Runbook 里）
- 如果 Runbook 的命令执行失败，再根据错误信息决定是否需要额外诊断，而不是一开始就自己加命令
- **唯一例外**：Runbook 说"SSH 登录"这一步，你可以跳过（因为系统已经通过 SSH 连接了）

## 诊断命令自动执行（无需用户确认）
- **只读查询工具**（query_* / list_* / get_* / analyze_*）直接调用即可，无需确认。
- **诊断/检查命令**（如 ps/df/free/top/grep/which/echo/curl/date/ls/cat 等只读命令）通过 `execute_run_command` 执行时，调用 `propose_action` 设置 `auto_confirm=true`，系统会自动执行**无需用户点击确认**。
- **写操作**（install/remove/restart/kill/rm/mkdir/shutdown/systemctl 等修改操作）必须设置 `auto_confirm=false`（默认），等待用户点击确认按钮后执行。
- 判断标准：任何不改写磁盘、不修改系统状态、不影响业务运行的命令都是诊断命令。

## 自动验证执行结果（极重要！）
- 每次写操作执行完毕后，必须**自动调用诊断命令验证结果**，禁止问"需要我验证吗？"
- 正确示例：执行 kill -9 → 自动执行 `ps aux | grep nginx` 验证进程是否消失 → 若还在则自动重试 → 若多次失败再问用户
- 正确示例：执行 yum install → 自动执行 `which nginx && nginx -v` 验证安装成功
- 正确示例：执行 systemctl restart → 自动检查进程状态
- 如果验证失败，自动尝试替代方案，只有所有方案都失败才问用户。

## 工具使用规则（必须严格遵守！）
- **只读查询**：直接调用 query_* / list_* / get_* / analyze_* 等查询工具。
- **运维操作**：严禁直接调用 execute_* 工具（它们是内部工具，已被禁用）。必须通过 `propose_action` 提议：
  1. 先调用 `list_executable_actions` 查看可用动作清单。
  2. 再调用 `propose_action` 提议动作（传入合法 action_type、title、payload、reason）。
  3. 系统会根据 `auto_confirm` 决定是自动执行还是等待用户确认。
  4. **禁止臆造 action_type**，必须使用 list_executable_actions 返回的合法值。

## 远程操作安全规则（重要！）
- payload 必须包含 `asset_id`（CMDB 资产 ID），系统会通过该资产的 SSH 连接配置远程登录目标主机执行命令。
- 提议前应先用 query_assets 查询资产，把目标主机的 asset_id 填入 payload。切勿使用 localhost 或本机 IP。
- execute_run_command 会拦截危险命令（rm -rf /、mkfs、dd、shutdown、reboot 等），不要尝试绕过。

## 安装部署任务（重要！必读）
当用户说"安装 XX"、"部署 XX"、"在 XX 上装 YY"时，按以下流程处理：

### 流程一：多步骤复杂部署 → 用 propose_workflow（推荐）
如果安装需要多个步骤（检测OS → 加仓库 → 安装 → 配置 → 启动 → 验证），优先调用 `propose_workflow`。
```
propose_workflow({
  title: "在 {主机名} 上安装 Elasticsearch",
  context: { asset_id: 123 },
  nodes: [
    { name: "检测操作系统", action_type: "run_command", payload_template: { command: "cat /etc/os-release" }, requires_confirm: false },
    { name: "安装依赖", action_type: "run_command", payload_template: { command: "apt-get install -y openjdk-17-jdk" }, requires_confirm: true },
    { name: "下载 ES", action_type: "run_command", payload_template: { command: "wget ..." }, requires_confirm: true },
    ...
  ],
  edges: [...]
})
```

### 流程二：单包安装 → 用 propose_action + execute_install_package（异步任务）
如果只需要安装一个软件包（Elasticsearch/Nginx/MySQL），用 propose_action 提议 `install_package` 动作：
```
propose_action({
  action_type: "install_package",
  title: "在 192.168.1.10 安装 Elasticsearch 8.19.0",
  payload: {
    package_name: "elasticsearch",
    asset_id: 123,        // ← 必须，先用 query_assets 查到
    version: "8.19.0",
    install_type: "binary",
    options: { start_service: true }
  },
  risk_level: "critical",
  auto_confirm: false
})
```
系统会立即返回 `job_id`，**不要等待安装完成**。安装是异步的，用户确认后后台执行。
安装过程中，用 `get_task_status(job_id=...)` **轮询**进度，每轮 LLM 调用可查一次。
当任务状态变为 `success` 或 `failed` 时，安装已完成，可给出最终结果。

### 长耗时任务轮询规范（极重要！）
- propose_action 返回后，立即用 `get_task_status` 查询一次，获取初始状态
- 如果状态是 `running` 或 `pending`，在回复中告知用户"安装进行中，稍等片刻后再次查询"
- **不要反复立即轮询**（每次回复最多查一次），避免浪费 token
- 安装完成后，系统返回 `result` 字段含完整执行步骤和最终状态，据此给用户完整汇报

## 日志查询规范（重要！）

当用户问"日志/错误日志/告警前后有什么日志"时，必须：

1. **先查有哪些日志源**：`query_log_sources` 返回所有已配置的 ES 数据源
2. **再按源查询日志**：`query_logs(source_id=X, query="关键词", time_range="1h", level="error")`
   - `level` 可选：`error` / `warning` / `info`
   - `time_range` 可选：`15m` / `1h` / `6h` / `24h` / `7d`
   - 不带 level 时返回所有级别日志

**典型诊断场景**：
- "告警前后有什么日志" → `query_logs(source_id=3, query="error", time_range="1h")`
- "nginx 有没有错误日志" → `query_logs(source_id=3, query="nginx", level="error")`
- "某主机最近 6h 日志" → `query_logs(source_id=3, host="web-server-01", time_range="6h")`

## 回答格式
1. 先给出结论
2. 列出证据（引用数据来源）
3. 分析风险（如果有操作建议）
4. 给出具体建议或下一步操作"""

# ── LLM 连接池（复用 TCP+TLS，避免每次三次握手） ──
_LLM_SESSION = None
_LLM_SESSION_LOCK = threading.Lock()

def _get_llm_session() -> requests.Session:
    global _LLM_SESSION
    if _LLM_SESSION is None:
        with _LLM_SESSION_LOCK:
            if _LLM_SESSION is None:
                s = requests.Session()
                adapter = requests.adapters.HTTPAdapter(
                    pool_connections=10, pool_maxsize=20, max_retries=0,
                )
                s.mount("https://", adapter)
                s.mount("http://", adapter)
                _LLM_SESSION = s
    return _LLM_SESSION


def call_llm(provider: AIProvider, messages: List[Dict], tools: Optional[List[Dict]] = None,
             timeout_override: Optional[int] = None, proxies: Optional[Dict] = None,
             max_tokens_override: Optional[int] = None) -> Dict:
    """Call OpenAI-compatible API. timeout_override 可覆盖 provider.timeout_seconds 防卡死.
    max_tokens_override 可覆盖 max_tokens（测试场景建议传小值如 10）。
    proxies 默认 {"http": None, "https": None} 禁用系统代理，避免本地代理对 LLM 长连接读超时."""
    if not provider or not provider.is_enabled:
        return {"error": "Provider not available"}

    api_key = provider.get_api_key()
    base_url = provider.base_url.rstrip("/")
    model = provider.default_model or "gpt-4o"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": provider.temperature,
        "max_tokens": max_tokens_override if max_tokens_override is not None else provider.max_tokens,
    }

    if tools:
        payload["tools"] = tools

    try:
        session = _get_llm_session()
        resp = session.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout_override or provider.timeout_seconds,
            proxies=proxies if proxies is not None else {"http": None, "https": None},
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"error": str(e)}


# MiniMax 等模型把工具调用编码在 content 文本标签里（非标准 OpenAI tool_calls 结构）：
#   <minimax:tool_call>
#   <invoke name="propose_action">
#   <parameter name="action_type">restart_service</parameter>
#   ...
#   </invoke>
#   </minimax:tool_call>
# 下列正则把上述文本解析为标准 tool_calls，让后续处理流程统一执行。
# 属性值兼容可选引号（双引号/单引号/无引号），防模型偶发输出 name='x' 或 name=x 时不匹配
_INVOKE_RE = re.compile(r'<invoke\s+name=["\']?([^"\'\s>]+)["\']?\s*>(.*?)</invoke>', re.DOTALL)
# 注：非贪婪 .*? 在第一个 </parameter> 处停止。若参数值内含 </parameter> 子串会误截断，
# 实际中 json.dumps 输出几乎不会含此串，按标签深度解析（如 html.parser）收益有限，暂不处理
_PARAM_RE = re.compile(r'<parameter\s+name=["\']?([^"\'\s>]+)["\']?\s*>(.*?)</parameter>', re.DOTALL)
_TOOL_CALL_TAG_RE = re.compile(r'<minimax:tool_call>.*?</minimax:tool_call>', re.DOTALL)
# 与 _INVOKE_RE 保持一致的可选引号模式，用于清理游离 invoke 块（无捕获组，仅用于 sub 清理）
_ORPHAN_INVOKE_RE = re.compile(r'<invoke\s+name=["\']?[^"\'\s>]+["\']?\s*>.*?</invoke>', re.DOTALL)


def _parse_text_tool_calls(content: str) -> List[Dict]:
    """从 content 文本中解析内嵌的工具调用标签，构造标准 OpenAI tool_calls 结构.

    部分模型（如 MiniMax 某些版本）不返回结构化 tool_calls 字段，而是把工具调用
    编码在 content 文本标签中。本函数把这种文本解析为标准 tool_calls 结构。

    参数值会尝试 json.loads：成功用解析值（如 payload 这种 JSON 字符串 → dict），
    失败用原字符串（如 title 这种纯文本）。无 invoke 标签时返回空列表。
    """
    # Early Exit：空内容或不含 invoke 标签，直接返回空列表，不进入正则解析
    if not content or "<invoke" not in content:
        return []

    tool_calls: List[Dict] = []
    for idx, invoke_match in enumerate(_INVOKE_RE.finditer(content)):
        tool_name = invoke_match.group(1)
        body = invoke_match.group(2)

        parsed_args: Dict[str, Any] = {}
        for param_match in _PARAM_RE.finditer(body):
            param_name = param_match.group(1)
            raw_value = param_match.group(2)
            # Parse Don't Validate：边界处尝试 JSON 解析，成功用解析值，
            # 失败保留原字符串（纯文本参数如 title）
            try:
                parsed_args[param_name] = json.loads(raw_value)
            except (json.JSONDecodeError, ValueError):
                parsed_args[param_name] = raw_value

        tool_calls.append({
            "id": f"text_call_{idx}",
            "function": {
                "name": tool_name,
                "arguments": json.dumps(parsed_args, ensure_ascii=False),
            },
        })

    return tool_calls


def _strip_text_tool_call_tags(content: str) -> str:
    """从 content 中剥离工具调用标签文本，保留剩余文字回复.

    先移除 <minimax:tool_call>...</minimax:tool_call> 整块（含外层包装），
    再兜底移除游离的 <invoke>...</invoke> 块，避免标签文本原样显示给用户。
    """
    # Early Exit：空内容无需清理
    if not content:
        return ""
    cleaned = _TOOL_CALL_TAG_RE.sub('', content)
    cleaned = _ORPHAN_INVOKE_RE.sub('', cleaned)
    # 兜底：清理可能游离的 <parameter> 标签（invoke 匹配失败时的残留）
    cleaned = _PARAM_RE.sub('', cleaned)
    return cleaned.strip()


def get_or_create_session(db: Session, user_id: int, session_id: Optional[int] = None) -> ChatSession:
    if session_id:
        session = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        ).first()
        if session:
            return session

    session = ChatSession(user_id=user_id, title="新会话")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_message_history(db: Session, session: ChatSession, config: AgentConfig) -> List[Dict]:
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    max_msgs = config.max_history_messages if config else 12
    if len(messages) > max_msgs:
        messages = messages[-max_msgs:]

    result = []
    for msg in messages:
        result.append({"role": msg.role, "content": msg.message_content or ""})
    return result


def add_message(
    db: Session, session_id: int, role: str, content: str,
    message_type: str = "text", citations: Optional[List] = None,
    tool_calls: Optional[List] = None,
) -> ChatMessage:
    msg = ChatMessage(
        session_id=session_id,
        role=role,
        message_type=message_type,
        message_content=content or "",
        citations=json.dumps(citations or [], ensure_ascii=False),
        tool_calls=json.dumps(tool_calls or [], ensure_ascii=False),
    )
    db.add(msg)
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if session:
        session.last_message_at = datetime.now()
    db.commit()
    db.refresh(msg)
    return msg


def process_chat_message(
    db: Session, user_id: int, session_id: Optional[int],
    user_message: str, config_name: str = "default",
) -> Dict:
    """Main entry point for chat message processing"""
    session = get_or_create_session(db, user_id, session_id)
    # 查询时不过滤 is_enabled：管理员禁用配置时仍能拿到记录，
    # 用它自身的 require_confirmation/allow_action_execution 值，
    # 避免禁用反而触发纯内存兜底对象误走免确认路径（与 confirm 路径查询保持一致）
    config = db.query(AgentConfig).filter(
        AgentConfig.name == config_name
    ).first()

    if not config:
        # 兜底纯内存对象：显式传入安全默认值，不依赖 SQLAlchemy column default
        # （column default 仅在 INSERT/flush 时生效，纯内存对象访问为 None，
        #  会导致 require_confirmation 为 None → if 判定为 False → 误走免确认路径）
        config = AgentConfig(
            name="default", is_enabled=True,
            require_confirmation=True, allow_action_execution=True,
        )

    provider = None
    ab_test_group = None
    ab_test_cfg = None
    active_ab_test = db.query(ABTestConfig).filter(
        ABTestConfig.status == "active"
    ).first()
    if active_ab_test:
        ab_provider_id, ab_test_group, ab_test_cfg = ab_test_service.get_provider_for_request(
            active_ab_test.id, session.id, db
        )
        if ab_provider_id:
            provider = db.query(AIProvider).filter(
                AIProvider.id == ab_provider_id,
                AIProvider.is_enabled == True,
            ).first()
    if not provider:
        if config.default_provider_id:
            provider = db.query(AIProvider).filter(
                AIProvider.id == config.default_provider_id,
                AIProvider.is_enabled == True,
            ).first()
        if not provider:
            provider = db.query(AIProvider).filter(
                AIProvider.is_enabled == True
            ).first()

    # Save user message
    user_msg = add_message(db, session.id, "user", user_message)

    # Auto-title on first message
    if session.title == "新会话":
        session.title = user_message[:64]
        db.commit()

    if not provider:
        error_text = "未配置可用的 LLM 提供商，请在 AI 设置中配置并启用一个模型提供商。"
        add_message(db, session.id, "assistant", error_text, message_type="error")
        return {"session_id": session.id, "reply": error_text, "error": True}

    # Build messages
    system_prompt = config.system_prompt or DEFAULT_SYSTEM_PROMPT
    
    # 注入会话上下文（告警/资产关联）
    session_ctx = json.loads(session.context or "{}")
    if session_ctx.get("alert_id"):
        alert_id = session_ctx["alert_id"]
        asset_id = session_ctx.get("asset_id") or session_ctx.get("asset", {}).get("id") if isinstance(session_ctx.get("asset"), dict) else None
        asset_name = session_ctx.get("asset_name", "")
        asset_ip = session_ctx.get("asset_ip", "")
        asset_ci_type = session_ctx.get("asset_ci_type", "")
        db_type = session_ctx.get("db_type", "")

        # 尝试从数据库补全资产类型信息
        if not asset_ci_type and asset_id:
            asset_row = db.query(Asset).filter(Asset.id == asset_id).first()
            if asset_row:
                asset_ci_type = asset_row.ci_type or ""
                if not db_type and asset_row.connection_config:
                    try:
                        cfg = json.loads(asset_row.connection_config)
                        db_type = cfg.get("db_type", "")
                    except Exception:
                        pass

        ctx_injection = (
            f"\n\n## ⚠️ 当前告警上下文（系统自动注入，请优先分析此告警）\n"
            f"- 告警 ID: #{alert_id}\n"
            f"- 指标: {session_ctx.get('alert_metric', '')}\n"
            f"- 级别: {session_ctx.get('alert_severity', '')}\n"
            f"- 当前值: {session_ctx.get('alert_value', '')}，阈值: {session_ctx.get('alert_threshold', '')}\n"
            f"- 涉事资产: {asset_name} (IP: {asset_ip})\n"
            f"用户正在处理此告警，你应该优先调用 get_alert_detail(id={alert_id}) 获取详情，并进行根因分析和操作建议。\n"
        )
        if db_type or asset_ci_type == "database":
            ctx_injection += (
                f"- 涉事资产类型: 数据库（{db_type or asset_ci_type}）\n"
                f"⚠️ 该涉事资产是数据库，可使用 `query_mysql` 工具执行 SQL 查询。\n"
                f"示例：query_mysql(asset_id={asset_id}, sql=\"SHOW DATABASES\")\n"
                f"示例：query_mysql(asset_id={asset_id}, sql=\"SHOW TABLES\")\n"
            )
        system_prompt += ctx_injection
    elif session_ctx.get("asset_id"):
        asset_id = session_ctx["asset_id"]
        asset_name = session_ctx.get("asset_name", "")
        asset_ip = session_ctx.get("asset_ip", "")
        asset_ci_type = session_ctx.get("asset_ci_type", "")
        db_type = session_ctx.get("db_type", "")

        if not db_type and asset_ci_type == "database":
            cfg_raw = db.query(Asset).filter(Asset.id == asset_id).first()
            if cfg_raw and cfg_raw.connection_config:
                try:
                    cfg = json.loads(cfg_raw.connection_config)
                    db_type = cfg.get("db_type", "")
                except Exception:
                    pass

        ctx_injection = (
            f"\n\n## 🏢 当前资产上下文（系统自动注入）\n"
            f"- 资产 ID: {asset_id}\n"
            f"- 资产名称: {asset_name}\n"
            f"- IP: {asset_ip}\n"
        )
        if db_type or asset_ci_type == "database":
            ctx_injection += (
                f"- 资产类型: 数据库（{db_type or asset_ci_type}）\n"
                f"⚠️ 该资产是数据库，可使用 `query_mysql` 工具执行 SQL 查询。\n"
                f"示例：query_mysql(asset_id={asset_id}, sql=\"SHOW DATABASES\")  # 查看所有库\n"
                f"示例：query_mysql(asset_id={asset_id}, sql=\"SHOW TABLES\")      # 查看当前库所有表\n"
                f"示例：query_mysql(asset_id={asset_id}, sql=\"DESC table_name\")  # 查看表结构\n"
            )
        system_prompt += ctx_injection

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(get_message_history(db, session, config))
    messages.append({"role": "user", "content": user_message})

    # Build MCP tools manifest for LLM
    mcp_tools = get_mcp_manifest()
    openai_tools = []
    for t in mcp_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        })

    # Call LLM (支持多轮工具调用循环，最多 5 轮防无限循环)
    # MiniMax 等模型可能需要多轮：query_assets 查资产 → propose_action 提议 → 二次总结回复
    # 单轮设计会导致二次 LLM 响应中的工具调用被忽略，标签原样显示给用户
    start = time.time()
    response = call_llm(provider, messages, openai_tools if openai_tools else None)
    latency = int((time.time() - start) * 1000)

    if "error" in response:
        error_text = f"调用 LLM 失败: {response['error']}"
        add_message(db, session.id, "assistant", error_text, message_type="error")
        return {"session_id": session.id, "reply": error_text, "error": True}

    tool_results = []
    pending_actions = []
    content = ""
    max_rounds = 5
    last_round_tool_names: List[str] = []

    for round_idx in range(max_rounds):
        # Parse response
        choice = response.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content", "") or ""
        tool_calls_raw = message.get("tool_calls")

        # 兼容性修复：部分模型（如 MiniMax）将工具调用编码在 content 文本标签中
        # 而非标准 tool_calls 结构化字段，需从 content 解析
        if not tool_calls_raw:
            content_text = message.get("content") or ""
            parsed = _parse_text_tool_calls(content_text)
            if parsed:
                tool_calls_raw = parsed
                # 补全结构化 tool_calls 字段，使后续 LLM 调用遵守 OpenAI 协议：
                # role: tool 消息必须紧跟在带 tool_calls 的 assistant 消息之后，
                # 否则标准端点返回 400。生成的 id 为 text_call_{idx}，
                # 与后续 tool 消息的 tool_call_id（tc.get("id", "")）一致，协议完全合规。
                message["tool_calls"] = parsed

        # 无论是否解析出工具调用，都清理 content 中的标签文本
        # 避免标签经 add_message 落库或显示给用户
        if content and ("<minimax:tool_call" in content or "<invoke" in content or "<parameter" in content):
            cleaned = _strip_text_tool_call_tags(content)
            message["content"] = cleaned
            content = cleaned

        # 无工具调用：当前 content 即最终回复，结束循环
        if not tool_calls_raw:
            break

        # 执行工具调用
        round_tool_results = []
        last_round_tool_names = []
        for tc in tool_calls_raw:
            tool_name = tc["function"]["name"]
            last_round_tool_names.append(tool_name)
            try:
                arguments = json.loads(tc["function"]["arguments"])
            except (json.JSONDecodeError, KeyError):
                arguments = {}

            # Call tool (LLM 路径：禁止调用 internal-only 工具，强制走确认闭环)
            tool_start = time.time()
            tool_result = call_mcp_tool(tool_name, arguments, db=db, user_id=user_id, allow_internal=False)
            tool_latency = int((time.time() - tool_start) * 1000)

            # Record invocation
            invocation = ToolInvocation(
                session_id=session.id,
                message_id=user_msg.id,
                tool_name=tool_name,
                status="success" if tool_result["status"] == "success" else "failed",
                latency_ms=tool_latency,
                request_payload=json.dumps(arguments, ensure_ascii=False),
                response_summary=json.dumps(tool_result, ensure_ascii=False),
            )
            db.add(invocation)
            db.commit()

            round_tool_results.append({
                "tool_name": tool_name,
                "result": tool_result,
                "tool_call_id": tc.get("id", ""),
            })
            tool_results.append({
                "tool_name": tool_name,
                "result": tool_result,
                "tool_call_id": tc.get("id", ""),
            })

            # Check for pending actions
            if tool_result.get("status") == "success":
                result_data = tool_result.get("result", {})
                if isinstance(result_data, dict) and result_data.get("_pending_action"):
                    pa_data = result_data["_pending_action"]
                    action_type = pa_data.get("action_type", "unknown")
                    pa_payload = pa_data.get("payload", {})

                    if config.require_confirmation and not pa_data.get("auto_confirm"):
                        # 默认路径：创建待确认动作，等用户在 UI 确认后由 confirm_pending_action 执行
                        pa = PendingAction(
                            session_id=session.id,
                            message_id=user_msg.id,
                            action_type=action_type,
                            title=pa_data.get("title", ""),
                            risk_level=pa_data.get("risk_level", "low"),
                            reason=pa_data.get("reason", ""),
                            action_payload=json.dumps(pa_payload, ensure_ascii=False),
                        )
                        db.add(pa)
                        db.commit()
                        # 把 PendingAction ID 注入 payload，让 confirm → execute_* 知道关联哪个 PA
                        pa_payload["_pending_action_id"] = pa.id
                        pa.action_payload = json.dumps(pa_payload, ensure_ascii=False)
                        db.commit()
                        pending_actions.append({
                            "id": pa.id,
                            "title": pa.title,
                            "risk_level": pa.risk_level,
                            "action_type": pa.action_type,
                        })
                    else:
                        # 免确认路径：跳过 PendingAction，直接走 execute_* 工具层执行
                        # 仍受 allow_internal=True 防护约束，不绕过工具注册体系
                        exec_tool_name = f"execute_{action_type}"
                        # 与 confirm 路径一致：执行前校验 payload schema，
                        # 防 LLM 在 require_confirmation=False 时构造畸形 payload 直接执行
                        schema_error = _validate_payload_schema(exec_tool_name, pa_payload)
                        if schema_error:
                            # 校验失败：不执行真实动作，回填 error 结果供 LLM 看到
                            exec_result = {"status": "error", "message": f"payload 校验失败：{schema_error}"}
                            round_tool_results[-1]["result"] = exec_result
                            tool_results[-1]["result"] = exec_result
                            db.add(ToolInvocation(
                                session_id=session.id,
                                message_id=user_msg.id,
                                tool_name=exec_tool_name,
                                status="failed",
                                # 未真实调用工具，仅做 schema 校验即被拒绝，故延迟记 0
                                latency_ms=0,
                                request_payload=json.dumps(pa_payload, ensure_ascii=False),
                                response_summary=json.dumps(exec_result, ensure_ascii=False),
                            ))
                            db.commit()
                        else:
                            # 与 LLM 路径 tool_start/tool_latency 计时风格一致，
                            # 记录 execute_* 真实执行延迟，供审计与性能分析
                            exec_start = time.time()
                            exec_result = call_mcp_tool(
                                exec_tool_name, pa_payload, db=db, allow_internal=True
                            )
                            exec_latency = int((time.time() - exec_start) * 1000)
                            # 用真实执行结果替换 propose 占位结果，供 LLM 下一轮调用参考
                            round_tool_results[-1]["result"] = exec_result
                            tool_results[-1]["result"] = exec_result
                            # 追加执行调用的审计记录，保证工具调用可追溯
                            db.add(ToolInvocation(
                                session_id=session.id,
                                message_id=user_msg.id,
                                tool_name=exec_tool_name,
                                status="success" if exec_result.get("status") == "success" else "failed",
                                latency_ms=exec_latency,
                                request_payload=json.dumps(pa_payload, ensure_ascii=False),
                                response_summary=json.dumps(exec_result, ensure_ascii=False),
                            ))
                            db.commit()

        # 准备下一轮 LLM 调用：把 assistant message + tool results 加入 messages
        messages.append(message)
        for tr in round_tool_results:
            messages.append({
                "role": "tool",
                "tool_call_id": tr["tool_call_id"],
                "content": json.dumps(tr["result"], ensure_ascii=False),
            })

        # 下一轮 LLM 调用（带工具结果，让 LLM 决定继续调工具还是给出最终回复）
        response = call_llm(provider, messages, openai_tools if openai_tools else None)
        if "error" in response:
            error_text = f"调用 LLM 失败: {response['error']}"
            add_message(db, session.id, "assistant", error_text, message_type="error")
            return {"session_id": session.id, "reply": error_text, "error": True}

    # 兜底：循环结束（达到 max_rounds 或无工具调用 break）后，
    # 若 content 仍含标签（如最后一轮 LLM 又想调工具但达到上限），清理之
    if content and ("<minimax:tool_call" in content or "<invoke" in content or "<parameter" in content):
        content = _strip_text_tool_call_tags(content)

    # 幻觉执行检测：LLM 回复"已提议/请点击确认"但 propose_action 未成功
    # LLM 多轮对话后容易退化成文本模拟——下面两种情况都触发重试：
    # 1. 没调 propose_action，只在文本说"已提议"
    # 2. 调了 propose_action 但返回错误，文本仍说"已提议成功"（忽略工具错误）
    # 最多重试 3 次，防止单次重试后 LLM 继续幻觉
    _hallucination_keywords = [
        "已提议", "已提交", "已提交安装", "已提交请求",
        "请点击确认", "点击确认", "确认按钮",
        "请确认是否执行", "确认执行",
        "操作已提交", "执行中，请稍候", "待确认",
    ]
    _max_hallucination_retries = 3
    for _hallu_try in range(_max_hallucination_retries):
        _propose_success = any(
            tr.get("result", {}).get("status") == "success"
            for tr in tool_results
            if tr.get("tool_name") == "propose_action"
        )
        if _propose_success or not content:
            break
        if not any(kw in content for kw in _hallucination_keywords):
            break

        # 构造更具体的警告信息：区分"没调用"和"调用失败"
        _last_propose = None
        for tr in tool_results:
            if tr.get("tool_name") == "propose_action":
                _last_propose = tr.get("result", {})
        if _last_propose:
            _err_msg = _last_propose.get("message", "")
            _warning = (
                f"【系统警告】你调用了 propose_action 但返回错误：{_err_msg}。"
                "但你却在回复中说已提议成功，这是错误的！"
                "用户界面不会有确认按钮，操作永远不会执行。"
                "请检查错误信息，修正参数后重新调用 propose_action 工具。"
            )
        else:
            _warning = (
                "【系统警告】你说已提议但你并没有调用 propose_action 工具！"
                "没有调用工具就不会创建待确认动作，用户界面不会显示确认按钮，操作永远不会执行。"
                "请立即调用 propose_action 工具来真正提议操作，不要只在文本里说已提议。"
            )
        messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user", "content": _warning})
        retry_resp = call_llm(provider, messages, openai_tools if openai_tools else None, timeout_override=30)
        if "error" in retry_resp:
            content = retry_resp.get("error", "重试 LLM 调用失败")
            break
        retry_msg = retry_resp.get("choices", [{}])[0].get("message", {})
        content = retry_msg.get("content", "") or ""
        retry_tool_calls = retry_msg.get("tool_calls")
        # 文本标签兼容
        if not retry_tool_calls:
            parsed = _parse_text_tool_calls(content)
            if parsed:
                retry_tool_calls = parsed
                retry_msg["tool_calls"] = parsed
                content = _strip_text_tool_call_tags(content)
        # 如果重试后调了工具，执行之
        if retry_tool_calls:
            for tc in retry_tool_calls:
                t_name = tc["function"]["name"]
                try:
                    t_args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, KeyError):
                    t_args = {}
                t_result = call_mcp_tool(t_name, t_args, db=db, user_id=user_id, allow_internal=False)
                db.add(ToolInvocation(
                    session_id=session.id, message_id=user_msg.id,
                    tool_name=t_name,
                    status="success" if t_result["status"] == "success" else "failed",
                    latency_ms=0,
                    request_payload=json.dumps(t_args, ensure_ascii=False),
                    response_summary=json.dumps(t_result, ensure_ascii=False),
                ))
                db.commit()
                tool_results.append({"tool_name": t_name, "result": t_result, "tool_call_id": tc.get("id", "")})
                # 创建 PendingAction
                if t_name == "propose_action" and t_result.get("status") == "is_success":
                    r_data = t_result.get("result", {})
                    if isinstance(r_data, dict) and r_data.get("_pending_action"):
                        pa_data = r_data["_pending_action"]
                        if config.require_confirmation:
                            pa = PendingAction(
                                session_id=session.id, message_id=user_msg.id,
                                action_type=pa_data.get("action_type", "unknown"),
                                title=pa_data.get("title", ""),
                                risk_level=pa_data.get("risk_level", "low"),
                                reason=pa_data.get("reason", ""),
                                action_payload=json.dumps(pa_data.get("payload", {}), ensure_ascii=False),
                            )
                            db.add(pa)
                            db.commit()
                            pending_actions.append({
                                "id": pa.id, "title": pa.title,
                                "risk_level": pa.risk_level, "action_type": pa.action_type,
                            })
            # 执行了工具后，重新检查幻觉状态（下一轮循环）
            continue
        else:
            # 重试后仍然没调工具，继续循环检查 content 是否仍含幻觉关键词
            continue

    # 兜底：重试循环结束后仍含幻觉关键词且 propose_action 未成功，强制替换
    if (not any(
            tr.get("result", {}).get("status") == "success"
            for tr in tool_results
            if tr.get("tool_name") == "propose_action"
    ) and content and any(kw in content for kw in _hallucination_keywords)):
        _last_propose = None
        for tr in tool_results:
            if tr.get("tool_name") == "propose_action":
                _last_propose = tr.get("result", {})
        if _last_propose:
            _err_msg = _last_propose.get("message", "")
            content = f"❌ 提议操作失败：{_err_msg}\n\n请修正参数后重新发起操作。"
        else:
            content = "❌ 操作提议失败：AI 未正确调用 propose_action 工具。请刷新页面重新发起。"

    # 兜底：LLM 回复太短（<100字）或只说"让我检查"但工具数>=3时，追加数据摘要
    try:
        _exec_msgs = []
        for tr in tool_results:
            r = tr.get("result", {})
            if r.get("status") == "is_success":
                _rr = r.get("result", {}) or {}
                msg = _rr.get("message", "") if isinstance(_rr, dict) else ""
                if not msg:
                    msg = r.get("message", "")
            else:
                msg = r.get("message", "")
            if msg and ("执行" in msg or "远程" in msg):
                _exec_msgs.append(msg[:1500])
        _has_exec_action = bool(_exec_msgs)
        _has_intent = any(kw in content for kw in ["让我确认", "让我检查", "让我验证", "让我看看", "让我查查", "正在确认", "正在检查", "正在验证"])
        _too_short = len(content.strip()) < 100 and len(tool_results) >= 3
        if (_has_exec_action and (len(content.strip()) < 200 or _has_intent)) or _too_short:
            if _exec_msgs:
                content = "✅ 诊断检查执行完成，结果摘要：\n" + "".join(f"  {p}\n" for p in _exec_msgs)
            else:
                _summaries = []
                for tr in tool_results:
                    _r = tr.get("result", {}).get("result", {}) or {}
                    if isinstance(_r, dict):
                        name = tr["tool_name"]
                        if name == "query_alerts":
                            a_list = _r.get("alerts", [])
                            active_n = sum(1 for a in a_list if a.get("status") == "triggered")
                            _summaries.append(f"{name}: {len(a_list)}条({active_n}条待处理)")
                        elif name == "query_assets":
                            _summaries.append(f"{name}: {_r.get('count', 0)}台")
                        elif name == "query_metrics":
                            v_list = _r.get("values", [])
                            if v_list:
                                _summaries.append(f"{name}({_r.get('metric_name','')}): avg={_r.get('avg', 0)}")
                        elif name == "get_alert_detail":
                            _summaries.append(f"{name}: {_r.get('metric_name','')}={_r.get('actual_value','')}")
                        elif name == "query_incidents":
                            _summaries.append(f"{name}: {_r.get('count', 0)}条")
                        elif name == "query_knowledge_rag":
                            _summaries.append(f"{name}: {len(_r.get('documents', []))}条")
                        elif name == "list_k8s_pods":
                            _summaries.append(f"{name}: {len(_r.get('pods', []))}个Pod")
                if _summaries:
                    content = "📊 查询结果摘要：\n" + "\n".join(f"  {s}" for s in _summaries) + "\n"
            for tr in tool_results:
                if tr.get("tool_name") == "query_assets":
                    _ra = tr.get("result", {}).get("result", {})
                    _assets = _ra.get("assets", [])
                    if _assets:
                        content += f"\n📋 资产: {_assets[0].get('name', '')} ({_assets[0].get('ip', '')})\n"
                elif tr.get("tool_name") == "query_alerts":
                    _ra = tr.get("result", {}).get("result", {})
                    _alerts = _ra.get("alerts", [])
                    _active = [a for a in _alerts if a.get("status") == "triggered"]
                    if _active and "告警" not in content:
                        content += f"\n⚠️ 当前告警: {len(_active)} 条待处理\n"
    except Exception:
        pass

    # Save assistant reply
    assistant_msg = add_message(
        db, session.id, "assistant", content,
        tool_calls=tool_results if tool_results else None,
    )

    session.last_message_at = datetime.now()
    db.commit()

    # 记录 A/B 测试结果（如有活跃测试）
    if active_ab_test and ab_test_group:
        try:
            token_usage = response.get("usage", {}) if isinstance(response, dict) else {}
            ab_test_service.record_result(
                db, test_id=active_ab_test.id,
                session_id=session.id, group=ab_test_group,
                provider_id=provider.id if provider else None,
                model_name=provider.model if provider else "",
                latency_ms=latency,
                token_count=token_usage.get("total_tokens", 0),
                success=True,
            )
            db.commit()
        except Exception:
            pass

    result = {
        "session_id": session.id,
        "reply": content,
        "session_title": session.title,
    }

    if pending_actions:
        result["pending_actions"] = pending_actions

    return result


def _payload_type_matches(value: Any, expected: str) -> bool:
    """JSON Schema 类型与 Python 值的基本匹配（bool 与 int 严格区分）."""
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True  # 未知类型放行，避免误伤


def _validate_payload_schema(tool_name: str, payload: Dict) -> Optional[str]:
    """按 execute_* 工具的 input_schema 校验 payload.

    返回错误描述字符串；None 表示校验通过。宽松校验：只检查 required 必填字段
    是否存在，并对 schema 中声明的字段做基本类型匹配，防 LLM 构造畸形 payload.
    """
    tool = get_mcp_tool(tool_name)
    if not tool:
        return f"工具 '{tool_name}' 不存在"
    schema = tool.input_schema or {}
    properties = schema.get("properties", {}) or {}
    required = schema.get("required", []) or []
    # 必填字段检查
    for field in required:
        if field not in payload:
            return f"缺少必填字段 '{field}'"
    # 已声明字段的类型基本检查
    for field, value in payload.items():
        spec = properties.get(field)
        if not spec:
            continue  # schema 未声明的字段放行（宽松）
        expected_type = spec.get("type")
        if expected_type and not _payload_type_matches(value, expected_type):
            return f"字段 '{field}' 类型应为 {expected_type}，实际为 {type(value).__name__}"
    return None


def confirm_pending_action(db: Session, action_id: int, user_name: str) -> Dict:
    # 行锁防 TOCTOU：并发确认同一动作时，后到事务等待先到事务提交后再读，
    # 此时 status 已非 pending，直接走早退分支。SQLite 下 with_for_update 静默
    # 退化为普通查询（开发环境单进程可接受），MySQL/PostgreSQL 上真正生效。
    action = db.query(PendingAction).filter(
        PendingAction.id == action_id
    ).with_for_update().first()
    if not action or action.status != PendingAction.STATUS_PENDING:
        return {"is_success": False, "status": "not_found", "message": "待确认动作不存在或已被处理"}

    # 读取配置开关（查不到配置则按默认值 True 处理）
    config = db.query(AgentConfig).filter(AgentConfig.name == "default").first()
    allow_exec = config.allow_action_execution if config else True

    # 统一的失败收尾：标记 STATUS_FAILED 并记录原因
    def _fail(message: str) -> Dict:
        action.status = PendingAction.STATUS_FAILED
        action.confirmed_by = user_name
        action.confirmed_at = datetime.now()
        fail_result = {"status": "error", "message": message}
        action.result_payload = json.dumps(fail_result, ensure_ascii=False)
        db.commit()
        return {"is_success": False, "status": PendingAction.STATUS_FAILED, "result": fail_result}

    # 早退出：管理员已全局禁止动作执行
    if not allow_exec:
        return _fail("管理员已禁止动作执行（allow_action_execution=False）")

    # payload schema 重新校验（防 LLM 在 propose 阶段构造畸形 payload，confirm 时原样执行造成危害）
    payload = json.loads(action.action_payload) if action.action_payload else {}
    tool_name = f"execute_{action.action_type}"
    schema_error = _validate_payload_schema(tool_name, payload)
    if schema_error:
        return _fail(f"payload 校验失败：{schema_error}")

    action.status = PendingAction.STATUS_CONFIRMED
    action.confirmed_by = user_name
    action.confirmed_at = datetime.now()

    # 置 STATUS_EXECUTING，准备执行
    action.status = PendingAction.STATUS_EXECUTING
    action.result_payload = ""
    db.commit()

    # 创建同步事件
    event = threading.Event()
    with _execution_events_lock:
        _execution_events[action.id] = event

    # 后台线程执行（独立 db session，避免与请求 session 冲突）
    _async_execute_action(action.id, action.session_id, action.message_id,
                          tool_name, payload, action.title, action.action_type)

    # 等后台线程完成（最多 180s），消除前端轮询竞态条件
    # 链式推进最多 8 轮 agentic loop + 最终总结, 每轮 LLM 30s, 需要更长超时
    completed = event.wait(timeout=180)

    with _execution_events_lock:
        _execution_events.pop(action.id, None)

    if completed:
        return {"is_success": True, "status": "completed",
                "result": {"status": "completed", "message": "执行完成"}}
    else:
        return {"is_success": True, "status": PendingAction.STATUS_EXECUTING,
                "result": {"status": "executing", "message": "命令正在远程执行中，请稍候..."}}


def _async_execute_action(action_id: int, session_id: int, message_id: Optional[int],
                          tool_name: str, payload: Dict, title: str, action_type: str):
    """后台线程执行待确认动作 + LLM 总结，独立 db session.

    执行完成后：更新 PendingAction.status + result_payload + ToolInvocation 审计 +
    调 LLM 总结存为 assistant 消息（失败/超时用 result message 兜底，不依赖 LLM）。
    """
    def _run():
        SessionLocal = get_session_for(get_db_mode())
        db = SessionLocal()
        try:
            action = db.query(PendingAction).filter(PendingAction.id == action_id).first()
            if not action:
                return

            # 执行命令
            exec_start = time.time()
            result: Dict
            try:
                result = call_mcp_tool(tool_name, payload, db=db, allow_internal=True)
            except Exception as e:
                result = {"status": "error", "message": str(e)}
            exec_latency = int((time.time() - exec_start) * 1000)

            # 审计
            db.add(ToolInvocation(
                session_id=session_id,
                message_id=message_id,
                tool_name=tool_name,
                status="success" if result.get("status") == "success" else "failed",
                latency_ms=exec_latency,
                request_payload=json.dumps(payload, ensure_ascii=False),
                response_summary=json.dumps(result, ensure_ascii=False),
            ))

            is_success = result.get("status") == "success"
            action.result_payload = json.dumps(result, ensure_ascii=False)
            # 注意：status 暂不更新为 executed/failed，先保持 executing，
            # 等 LLM 总结/兜底消息落库后再更新——否则前端轮询到 is_terminal
            # 时 assistant 消息还没存进去，loadMessages 拿不到 AI 回复

            # 方案A: 链式推进——执行成功后进入 agentic loop, 让 LLM 自主决定下一步
            # (提议启动/验证/最终总结), 形成"确认→自动推进→确认"链
            config = db.query(AgentConfig).filter(AgentConfig.name == "default").first()
            reply = _continue_after_execution(db, action, result, config, user_id=None)
            # 链式推进失败/超时：用 result 里的 message 兜底，确保用户有反馈
            if not reply:
                status_text = "执行成功" if is_success else "执行失败"
                # 从嵌套结构提取 message
                fallback_msg = result.get("message", "")
                if not fallback_msg:
                    inner = result.get("result", {})
                    if isinstance(inner, dict):
                        fallback_msg = inner.get("message", "")
                reply = f"**{title}** — {status_text}\n\n{fallback_msg}"
                add_message(db, session_id, "assistant", reply)

            # LLM 总结/兜底消息已落库，现在更新 status 为终态
            # 前端轮询到 is_terminal 时 assistant 消息已存在，loadMessages 能拿到
            action.status = PendingAction.STATUS_EXECUTED if is_success else PendingAction.STATUS_FAILED
            db.commit()
        except Exception:
            # 兜底：标记 failed，不崩溃
            try:
                action = db.query(PendingAction).filter(PendingAction.id == action_id).first()
                if action and action.status == PendingAction.STATUS_EXECUTING:
                    action.status = PendingAction.STATUS_FAILED
                    action.result_payload = json.dumps(
                        {"status": "error", "message": "后台执行异常"}, ensure_ascii=False)
                    db.commit()
            except Exception:
                pass
        finally:
            db.close()
            # 通知 confirm 接口线程已完成
            with _execution_events_lock:
                event = _execution_events.get(action_id)
                if event:
                    event.set()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


def _summarize_execution_result(db: Session, action: PendingAction, result: Dict, config: Optional[AgentConfig]) -> str:
    """确认执行后调 LLM 把执行结果总结成自然语言回复，存为 assistant 消息.

    LLM 总结失败不影响 confirm 结果（命令已执行），仅 try/except 静默降级返回空串。
    """
    try:
        session_obj = db.query(ChatSession).filter(ChatSession.id == action.session_id).first()
        if not session_obj:
            return ""
        provider = None
        if config and config.default_provider_id:
            provider = db.query(AIProvider).filter(
                AIProvider.id == config.default_provider_id, AIProvider.is_enabled == True,
            ).first()
        if not provider:
            provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
        if not provider:
            return ""

        system_prompt = (config.system_prompt if config else None) or DEFAULT_SYSTEM_PROMPT
        msgs: List[Dict] = [{"role": "system", "content": system_prompt}]
        msgs.extend(get_message_history(db, session_obj, config))
        # 把执行结果作为上下文让 LLM 总结（不暴露原始 JSON，用结构化描述）
        result_json = json.dumps(result, ensure_ascii=False)
        status_text = "成功" if result.get("status") == "success" else "失败"
        msgs.append({"role": "user", "content": (
            f"[系统通知] 待确认动作已执行完成。\n"
            f"动作标题: {action.title}\n"
            f"动作类型: {action.action_type}\n"
            f"执行状态: {status_text}\n"
            f"执行结果: {result_json}\n\n"
            f"请用简洁的自然语言向用户总结执行结果，如果失败请说明原因并给出建议。"
            f"重要：这是执行结果总结，不是新操作提议，不要写'请点击确认'、'请在界面点击确认'或类似内容。"
        )})

        resp = call_llm(provider, msgs, timeout_override=20)
        if "error" not in resp:
            reply = resp.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
            if reply:
                add_message(db, session_obj.id, "assistant", reply)
                return reply
    except Exception:
        pass
    return ""


# ─── 方案A: 链式推进 (Chained Proactive Continuation) ───
# 写操作 confirm 执行成功后, 不再只做文字总结, 而是把执行结果作为新输入重新进入 agentic loop,
# 让 LLM 自己决定下一步 (提议启动/验证/或给最终总结). 形成"确认→自动推进→确认"链.
# 与 _summarize_execution_result 的区别: 后者只调一次 LLM 生成总结, 不进入工具调用循环;
# 本函数进入最多 8 轮 agentic loop, LLM 可继续调 propose_action/query_*/execute_* (免确认).
_CONTINUE_SYSTEM_SUFFIX = """

## 当前任务上下文：链式推进模式
你刚才提议的一个写操作已被用户确认并执行完成，执行结果已在上一条消息中给出。
现在请你根据执行结果决定下一步：
1. **继续推进计划下一步**：如果原计划还有后续步骤（如安装后启动、启动后验证），立即调用 propose_action 提议下一个动作。诊断命令会自动执行无需确认，写操作会等待用户确认。
2. **给出最终总结**：如果原计划已全部完成，或执行失败且无替代方案，用简洁自然语言向用户汇报最终结果。
3. **禁止问"需要我继续吗？"、"是否需要..."等开放式问句**。要么直接调工具推进，要么给结论。用户确认了一次就期望你自主完成剩余步骤。
4. **禁止只说不做**：不要写"让我进一步检查"、"我来排查一下"等话语后不调用工具。如果你说要检查，就必须立即调用 propose_action 工具执行检查命令。
"""

# 意图词检测: LLM 说"让我检查/我来排查"但没调工具的幻觉模式
# 用于 _continue_after_execution 的幻觉检测, 命中后追加 warning 强制 LLM 调工具
_CONTINUE_INTENT_RE = re.compile(
    r'(让我|我来|我将|我会|接下来|下一步).{0,6}(检查|查看|执行|排查|分析|看看|继续|确认|验证|查找|试试|尝试|排查一下|看一下)',
    re.DOTALL,
)


def _has_continue_intent(content: str) -> bool:
    """检测 content 是否含'说要继续检查但没调工具'的意图词模式."""
    if not content:
        return False
    # 末尾是冒号（"让我进一步检查："这种半截句子）也算意图
    if content.rstrip().endswith(("：", ":")):
        return True
    return bool(_CONTINUE_INTENT_RE.search(content))


def _continue_after_execution(db: Session, action: PendingAction, result: Dict, config: Optional[AgentConfig], user_id: Optional[int]) -> str:
    """执行成功后进入 agentic loop, 让 LLM 自主决定下一步 (提议新动作/验证/最终总结).

    返回最终 assistant 回复内容 (已存入数据库). 失败/超时返回空串, 由调用方兜底.
    与 _summarize_execution_result 的区别: 后者只生成文字总结不调工具; 本函数进入
    最多 8 轮工具调用循环, LLM 可继续 propose_action 形成链式推进.
    """
    try:
        session_obj = db.query(ChatSession).filter(ChatSession.id == action.session_id).first()
        if not session_obj:
            return ""
        provider = None
        if config and config.default_provider_id:
            provider = db.query(AIProvider).filter(
                AIProvider.id == config.default_provider_id, AIProvider.is_enabled == True,
            ).first()
        if not provider:
            provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
        if not provider:
            return ""

        # 构造 system prompt: 原始 prompt + 链式推进指令
        base_prompt = (config.system_prompt if config else None) or DEFAULT_SYSTEM_PROMPT
        system_prompt = base_prompt + _CONTINUE_SYSTEM_SUFFIX

        msgs: List[Dict] = [{"role": "system", "content": system_prompt}]
        msgs.extend(get_message_history(db, session_obj, config))
        # 执行结果作为系统通知 (不存为 user 消息, 避免污染对话历史)
        result_json = json.dumps(result, ensure_ascii=False)
        status_text = "成功" if result.get("status") == "success" else "失败"
        msgs.append({"role": "user", "content": (
            f"[系统通知] 待确认动作已执行完成。\n"
            f"动作标题: {action.title}\n"
            f"动作类型: {action.action_type}\n"
            f"执行状态: {status_text}\n"
            f"执行结果: {result_json}\n\n"
            f"请根据执行结果继续推进计划下一步，或给出最终总结。"
        )})

        # Build MCP tools manifest
        mcp_tools = get_mcp_manifest()
        openai_tools = []
        for t in mcp_tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            })

        content = ""
        max_rounds = 8
        last_had_tool_calls = False
        intent_retry_count = 0  # 意图词幻觉重试次数
        _MAX_INTENT_RETRIES = 2
        for round_idx in range(max_rounds):
            resp = call_llm(provider, msgs, openai_tools if openai_tools else None, timeout_override=30)
            if "error" in resp:
                # LLM 调用失败: 用 result message 兜底, 不继续 loop
                return ""
            choice = resp.get("choices", [{}])[0]
            message = choice.get("message", {})
            content = message.get("content", "") or ""
            tool_calls_raw = message.get("tool_calls")

            # 文本标签兼容 (MiniMax 等)
            if not tool_calls_raw:
                parsed = _parse_text_tool_calls(content)
                if parsed:
                    tool_calls_raw = parsed
                    message["tool_calls"] = parsed
            if content and ("<minimax:tool_call" in content or "<invoke" in content or "<parameter" in content):
                cleaned = _strip_text_tool_call_tags(content)
                message["content"] = cleaned
                content = cleaned

            # 无工具调用: 检查是否含意图词 (说"让我检查"但没调工具)
            if not tool_calls_raw:
                if content and intent_retry_count < _MAX_INTENT_RETRIES and _has_continue_intent(content):
                    # 意图词幻觉: LLM 说要检查但没调工具, 追加 warning 强制调工具
                    intent_retry_count += 1
                    msgs.append({"role": "assistant", "content": content})
                    msgs.append({"role": "user", "content": (
                        "【系统警告】你说了'让我进一步检查'或类似话语，但没有调用任何工具。"
                        "请立即调用 propose_action 工具来执行检查命令（诊断命令会自动执行无需确认），"
                        "或者给出最终总结。不要只说不做。"
                    )})
                    continue
                # 真的没工具调用也没意图词 (或重试上限): 存 content 结束
                if content:
                    add_message(db, session_obj.id, "assistant", content)
                return content

            last_had_tool_calls = True
            round_tool_results = []
            has_new_pending = False  # 本轮是否创建了需用户确认的 PendingAction
            for tc in tool_calls_raw:
                tool_name = tc["function"]["name"]
                try:
                    arguments = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, KeyError):
                    arguments = {}

                tool_start = time.time()
                tool_result = call_mcp_tool(tool_name, arguments, db=db, user_id=user_id, allow_internal=False)
                tool_latency = int((time.time() - tool_start) * 1000)

                db.add(ToolInvocation(
                    session_id=session_obj.id,
                    message_id=action.message_id,
                    tool_name=tool_name,
                    status="success" if tool_result.get("status") == "success" else "failed",
                    latency_ms=tool_latency,
                    request_payload=json.dumps(arguments, ensure_ascii=False),
                    response_summary=json.dumps(tool_result, ensure_ascii=False),
                ))
                db.commit()

                round_tool_results.append({
                    "tool_name": tool_name,
                    "result": tool_result,
                    "tool_call_id": tc.get("id", ""),
                })

                # propose_action 成功 → 创建 PendingAction 或 auto_confirm 执行
                if tool_result.get("status") == "is_success":
                    result_data = tool_result.get("result", {})
                    if isinstance(result_data, dict) and result_data.get("_pending_action"):
                        pa_data = result_data["_pending_action"]
                        pa_action_type = pa_data.get("action_type", "unknown")
                        pa_payload = pa_data.get("payload", {})

                        if config.require_confirmation and not pa_data.get("auto_confirm"):
                            # 需用户确认: 创建 PendingAction, 标记 has_new_pending, loop 结束后等用户确认
                            pa = PendingAction(
                                session_id=session_obj.id,
                                message_id=action.message_id,
                                action_type=pa_action_type,
                                title=pa_data.get("title", ""),
                                risk_level=pa_data.get("risk_level", "low"),
                                reason=pa_data.get("reason", ""),
                                action_payload=json.dumps(pa_payload, ensure_ascii=False),
                            )
                            db.add(pa)
                            db.commit()
                            has_new_pending = True
                        else:
                            # 免确认路径 (诊断命令): 直接执行, 继续 loop 让 LLM 看结果
                            exec_tool_name = f"execute_{pa_action_type}"
                            schema_error = _validate_payload_schema(exec_tool_name, pa_payload)
                            if schema_error:
                                exec_result = {"status": "error", "message": f"payload 校验失败：{schema_error}"}
                                round_tool_results[-1]["result"] = exec_result
                            else:
                                exec_start = time.time()
                                exec_result = call_mcp_tool(exec_tool_name, pa_payload, db=db, allow_internal=True)
                                exec_latency = int((time.time() - exec_start) * 1000)
                                round_tool_results[-1]["result"] = exec_result
                                db.add(ToolInvocation(
                                    session_id=session_obj.id,
                                    message_id=action.message_id,
                                    tool_name=exec_tool_name,
                                    status="success" if exec_result.get("status") == "success" else "failed",
                                    latency_ms=exec_latency,
                                    request_payload=json.dumps(pa_payload, ensure_ascii=False),
                                    response_summary=json.dumps(exec_result, ensure_ascii=False),
                                ))
                                db.commit()

            # 把 assistant message + tool results 加入 msgs, 准备下一轮
            msgs.append(message)
            for tr in round_tool_results:
                msgs.append({
                    "role": "tool",
                    "tool_call_id": tr["tool_call_id"],
                    "content": json.dumps(tr["result"], ensure_ascii=False),
                })

            # 如果本轮创建了需用户确认的 PendingAction, loop 结束 (等用户确认后链式继续)
            if has_new_pending:
                # 给用户一个文字提示, 说明已提议下一步 (content 可能已含 LLM 的说明)
                if content:
                    add_message(db, session_obj.id, "assistant", content)
                return content

        # 达到 max_rounds: 如果最后一轮 LLM 仍调了工具 (说明还想继续但被截断),
        # 再调一次 LLM 不带 tools, 强制它给出最终总结 (否则用户只看到半截句子)
        if last_had_tool_calls:
            final_msgs = msgs + [{"role": "user", "content": (
                "【系统通知】已达到最大自动执行轮次。请根据以上所有执行结果，"
                "用简洁的自然语言向用户汇报最终结果（包括已执行的诊断命令和发现的问题）。"
                "不要再调用工具，只给出总结。"
            )}]
            final_resp = call_llm(provider, final_msgs, None, timeout_override=30)
            if "error" not in final_resp:
                final_content = final_resp.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
                if final_content:
                    content = final_content
        # 清理可能的标签, 存最终 content
        if content and ("<minimax:tool_call" in content or "<invoke" in content or "<parameter" in content):
            content = _strip_text_tool_call_tags(content)
        if content:
            add_message(db, session_obj.id, "assistant", content)
        return content
    except Exception:
        return ""


def cancel_pending_action(db: Session, action_id: int) -> bool:
    # 行锁防 TOCTOU：与 confirm_pending_action 保持对称，并发 confirm+cancel
    # 时后到事务等待先到事务提交后再读，此时 status 已非 pending，走早退分支。
    # SQLite 下 with_for_update 静默退化为普通查询（开发环境单进程可接受），
    # MySQL/PostgreSQL 上真正生效。
    action = db.query(PendingAction).filter(
        PendingAction.id == action_id
    ).with_for_update().first()
    if not action or action.status != PendingAction.STATUS_PENDING:
        return False

    action.status = PendingAction.STATUS_CANCELED
    db.commit()
    return True
