"""子模块(由 component_catalog 拆分生成, 勿手改函数体)"""
import json
import re
import socket
import base64
import time
import threading
from datetime import datetime
from typing import Optional, List

from sqlalchemy.orm import Session

from app.models import Asset, ComponentCatalog, ComponentInstall

import logging
logger = logging.getLogger(__name__)

from app.services.component_catalog_render import build_default_compose, _inject_native_params  # noqa

# ─── 原 L2412-2452 ───
def _ai_decision_options(db, comp_name, asset_name, context, question, deploy_type="docker", system="", opts_hint=2, deploy_path="", port=0) -> list:
    """由 AI 生成部署决策候选方案(默认 2 个, 严格按当前部署方式/系统)。失败/无 provider 时返回规则方案。"""
    provider = _get_deploy_provider(db)
    pm_tip = {"rhel": "dnf/yum", "debian": "apt-get", "alpine": "apk"}.get(system or "", "")
    fallback = [
        {"key": "opt1", "title": "保持默认重试", "detail": "重试当前步骤(clean 后重跑)"},
        {"key": "opt2", "title": "改用降级方案", "detail": "跳过当前步骤, 标记为已处理并继续"},
    ]
    if not provider:
        return fallback
    from app.services.agent_service import call_llm
    _path_hint = (f", 部署路径/数据目录: {deploy_path}" if deploy_path else "") + (f", 端口: {port}" if port else "")
    system_msg = (f"你是资深 SRE。当前正在以【{deploy_type}】方式部署组件 {comp_name}"
                  f"({'目标机系统 ' + system if system else ''}){_path_hint}。请给出 2 个不同的可执行处置方案。\n"
                  f"⚠ 重要: 必须严格围绕【{deploy_type}】方式进行处置, 不要混用其他方式。"
                  f"({deploy_type} 时用 {pm_tip or '系统包管理器'} 安装/管理服务; docker 时才用 docker 命令)。\n"
                  f"⚠ 若已提供部署路径 {deploy_path or '(如 /opt/kafka)'}, 生成的命令必须基于该真实部署路径(用其绝对路径、cd 到该目录、systemd 单元指向它), 禁止臆造不存在的路径/包名。\n"
                  "只输出 JSON: {\"options\":[{\"title\":\"方案名\",\"detail\":\"具体命令/动作\"}, {\"title\":\"...\",\"detail\":\"...\"}]}")
    user = (f"组件: {comp_name}; 目标机: {asset_name}; 部署方式: {deploy_type};"
            f" 部署路径: {deploy_path or '(默认)'}; 端口: {port or '(默认)'};\n"
            f"需要决策的问题: {question}\n当前部署上下文日志:\n{(context or '')[-1200:]}")
    try:
        resp = call_llm(provider, [{"role": "system", "content": system_msg}, {"role": "user", "content": user}])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = safe_json_parse(content)
        opts = parsed.get("options") or []
        result = []
        for i, o in enumerate(opts[:opts_hint]):
            title = str(o.get("title", "")).strip()
            detail = str(o.get("detail", "")).strip()
            if not title and not detail:
                continue
            result.append({"key": f"opt{i+1}", "title": title or f"方案{i+1}", "detail": detail})
        # 不足 opts_hint 个方案时用通用 fallback 补足, 保证用户始终有 ≥2 个可选
        for j in range(len(result), opts_hint):
            fb = fallback[j] if j < len(fallback) else fallback[-1]
            result.append({"key": f"opt{j+1}", "title": fb["title"], "detail": fb["detail"]})
        return result
    except Exception as _exc5:
        logger.warning("[except:pass] Exception: %s", _exc5, exc_info=True)
    return fallback


# ─── 原 L2455-2483 ───
def _ai_intent_to_command(db, comp_name, intent_text, context="") -> str:
    """把用户的自定义处置意图(可能是中文描述)转成可执行 shell 命令。
    返回命令字符串; 无法转换/无 provider 时原样返回(仍尝试执行)。"""
    text = (intent_text or "").strip()
    if not text:
        return text
    # 看起来已经是命令(含 / 空格 且无中文)则直接用
    if not _contains_cn(text):
        return text
    provider = _get_deploy_provider(db)
    if not provider:
        return text
    from app.services.agent_service import call_llm
    system = ("你是资深 SRE。用户用自然语言描述了一个部署处置意图, 请把它转成**一行可直接在目标机 root shell 执行的命令**(可含 ; 或 &&)。"
              "只输出 JSON: {\"command\":\"转换后的命令\"}")
    user = (f"处置意图: {text}\n部署上下文:\n{(context or '')[:1200]}")
    try:
        resp = call_llm(provider, [{"role": "system", "content": system}, {"role": "user", "content": user}])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        cmd = json.loads(content).get("command", "").strip()
        if cmd and not _contains_cn(cmd):
            return cmd
    except Exception as _exc6:
        logger.warning("[except:pass] Exception: %s", _exc6, exc_info=True)
    return text


# ─── 原 L2486-2487 ───
def _contains_cn(s: str) -> bool:
    return any('\u4e00' <= ch <= '\u9fff' for ch in s)


# ─── 原 L2490-2589 ───
def _ai_generate_plan(db, comp: dict, deploy_type: str, system: str, target: str = "", port=0, deploy_path: str = "", params: dict = None) -> dict:
    """按目标机系统类型 + 组件生成可直接执行的部署方案。
    返回: {ai_generated, kind, system, plan(多行命令/步骤文本), title}。
    无 provider/失败时降级为规则生成的方案。params 为用户填写的组件定制参数({key:value})。"""
    provider = _get_deploy_provider(db)
    name = comp.get("name", "")
    disp = comp.get("display_name", name)
    image = comp.get("docker_image") or ""
    ns = "default"
    release = f"{name}-{datetime.now().strftime('%m%d%H%M')}"
    pm_cmd = {"rhel": "yum install -y", "debian": "apt-get update && apt-get install -y",
              "alpine": "apk add --no-cache", "unknown": "yum install -y"}.get(system, "yum install -y")
    params = params or {}

    def _fallback():
        if deploy_type == "docker":
            compose = comp.get("compose_yaml") or build_default_compose(name, image, port)
            return {"ai_generated": False, "kind": "docker", "system": system,
                    "title": f"{disp} Docker 部署方案",
                    "plan": f"# 目标机: {target} (系统: {system or 'unknown'})\n# 部署路径: {deploy_path or '(默认)'}\n{compose}\n# 执行: docker compose up -d"}
        if deploy_type == "native":
            script = comp.get("native_script") or f"echo '暂未提供 {name} 原生脚本'"
            # 应用用户定制参数: 生成真正改写配置的脚本(端口/密码等落地), 而非裸安装脚本
            script = _inject_native_params(script, comp, params, deploy_path=deploy_path)
            return {"ai_generated": False, "kind": "native", "system": system,
                    "title": f"{disp} 传统部署方案",
                    "plan": f"# 目标机: {target} (系统: {system or 'unknown'}, 包管理器: {pm_cmd[:20]})\n# 部署路径/数据目录: {deploy_path or '(默认)'}\n# (已应用定制参数: 端口/密码/内存等已写入配置)\n{script}\n# 启动: systemctl start {name}"}
        if deploy_type == "helm":
            return {"ai_generated": False, "kind": "helm", "system": system,
                    "title": f"{disp} K8s/Helm 方案",
                    "plan": (f"helm repo add bitnami {comp.get('helm_repo') or 'https://charts.bitnami.com/bitnami'}\n"
                             f"helm install {release} {comp.get('helm_chart') or name} -n {ns} --create-namespace")}
        return {"ai_generated": False, "kind": "ha", "system": system,
                "title": f"{disp} 高可用方案", "plan": f"# 高可用部署由 K8s/helm 引擎编排\n# Chart: {comp.get('helm_chart')}"}

    if not provider:
        return _fallback()
    from app.services.agent_service import call_llm
    system_msg = ("你是资深 SRE。请为目标机指定发行版 + 指定组件并**结合用户填写的部署路径与定制参数**生成一份**可直接在终端执行的部署方案**。"
                  "若部署路径非空, 命令中应包含在该路径下创建目录/落数据/写配置(mkdir -p <path>)。"
                  "**必须把用户填写的定制参数(端口/监听/内存等)写进目标配置文件(如 sed 改 redis.conf 的 port/requirepass、nginx.conf 的 listen/server_name、mysql 的 port 等), 不能用默认值。**"
                  "密码类参数用 <%=KEY%> 占位符代替明文, 不要暴露真实密码。"
                  "**重要 — 下载工具约定**: 任何下载源码/二进制的命令必须使用 **curl 优先 + wget 兜底** 的双降级写法, 严禁假设 wget 可用(minimal 系统通常无 wget):"
                  "`curl -fsSL -o <file> <URL> || wget -q -O <file> <URL>`。"
                  "如需装 wget, 先用 `which curl` 探测, 若 curl 已存在则不需要 wget;若确实需要 wget, 用 `(yum install -y wget || dnf install -y wget || apt-get install -y wget)`, 并在命令前加 `set +e` 防止失败中断。"
                  "**重要 — yum/apt 源约定**: 若需 yum install 装包, 优先用 `yum install -y <pkg>`(默认源即可, 不要盲目换源);若预检已知系统源不可达, 改用 curl 下载 rpm 包本地安装(`curl -fsSL -o /tmp/x.rpm <URL> && yum install -y /tmp/x.rpm`), 或在命令前置 `(curl -s -m 5 -o /dev/null -w '%{http_code}' <mirror> | grep -q 200) || { echo SOURCE_DOWN; exit 1; }` 做源可达性预检。"
                  "只输出 JSON: {\"summary\":\"一句话部署说明\",\"steps\":[\"第1条命令\",\"第2条命令\",...]}")
    # 构造用户定制参数描述(密码脱敏为占位符)
    _schema = comp.get("param_schema") or []
    _param_lines = []
    for item in _schema:
        key = item.get("key")
        if not key or key not in params or params.get(key) in (None, "", False):
            continue
        val = params.get(key)
        label = item.get("label") or key
        if item.get("type") == "password" or "password" in key or "pwd" in key:
            _param_lines.append(f"- {label}({key}): <%= {key.upper()} %> (已填, 部署时用实际值)")
        else:
            _param_lines.append(f"- {label}({key}): {val}")
    params_desc = "\n".join(_param_lines) or "(未填写定制参数, 用默认)"
    user = (f"组件: {name}({disp}); 部署方式: {deploy_type}; "
            f"目标机系统: {system or 'unknown'}(据此选 yum/dnf 或 apt-get/apk); 目标机: {target or '?'}; "
            f"镜像: {image or 'N/A'}; 组件默认端口: {port or ''}; "
            f"用户指定的部署路径: {deploy_path or '(未指定, 用默认)'};\n"
            f"用户填写的定制参数如下, 请将这些参数写进目标配置文件:\n{params_desc}\n"
            f"请给出与该系统类型匹配的、可直接执行的完整命令序列(含安装/配置写入/启动/服务检查)。")
    try:
        resp = call_llm(provider, [{"role": "system", "content": system_msg}, {"role": "user", "content": user}])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = safe_json_parse(content, {})
        steps = parsed.get("steps") or []
        if not steps:
            return _fallback()
        has_pm = any((("yum" in s) or ("apt-get" in s) or ("apk" in s) or ("dnf" in s)) for s in steps)
        if not has_pm:
            # 若系统已知但 AI 没给安装命令, 荣誉补第一步安装
            steps = [f"{pm_cmd} {name}"] + steps
        # ▼ 遵循用户在配置 tab 选择的「安装方式」:
        #   native_source=package(默认) → 强制复用组件内置稳定脚本走系统包管理器(yum/dnf),
        #   避免 redis 这类组件被 AI 带到源码编译而反复失败;
        #   native_source=source → 允许 AI 生成源码编译等方案。
        _nscript = (comp.get("native_script") or "").strip()
        if deploy_type == "native" and _nscript and str((params or {}).get("native_source") or "package") != "source":
            _steps2 = _inject_native_params(_nscript, comp, params, deploy_path=deploy_path)
            steps = _steps2.splitlines()
            header = f"# {disp} {deploy_type} 部署方案(包管理器安装 yum/dnf)"
            header += f" (目标机: {target or '?'} / 系统: {system or 'unknown'})"
            plan = header + "\n" + "\n".join(steps)
            return {"ai_generated": True, "kind": deploy_type, "system": system,
                    "title": f"{disp} {deploy_type} 部署方案(包管理器)",
                    "plan": plan}
        header = f"# {disp} {deploy_type} 部署方案"
        header += f" (目标机: {target or '?'} / 系统: {system or 'unknown'})"
        plan = header + "\n" + "\n".join(steps)
        return {"ai_generated": True, "kind": deploy_type, "system": system,
                "title": parsed.get("summary") or f"{disp} {deploy_type} 部署方案",
                "plan": plan}
    except Exception:
        return _fallback()


# ─── 原 L2592-2632 ───
def _plan_to_visual_steps(plan: str, deploy_type: str = "native") -> list:
    """把部署方案文本解析成「可展示」的分步结构, 供前端渲染步骤卡片。

    与 `_plan_to_steps`(执行用)不同, 这里**保留 # 注释作为每步说明**, 并做美化分类:
    返回 [{no, desc, cmd, kind}], 其中:
      - desc: 该命令紧邻上方 # 注释(去 # 后), 无注释则为 ''(可用于步骤说明/折叠标题);
      - cmd : 该步命令(多行命令合并为一行展示);
      - kind: 按命令特征归类(install/config/pull/start/verify/other), 用于前端打标签。
    """
    steps = []
    if not plan:
        return steps
    pending_desc = []
    no = 0
    for ln in plan.splitlines():
        line = (ln or "").strip()
        if not line:
            continue
        if line.startswith(("#!", "```", "~~~")):
            continue
        if line.startswith("#"):
            # 注释: 首行若为「xxx 部署方案」标题则跳过, 其余作为 pending 说明
            txt = line.lstrip("#").strip()
            if not txt or ("部署方案" in txt and re.match(r".{0,20}(部署方案|方案|deploy|Deploy)", txt)):
                pass
            else:
                pending_desc.append(txt)
            continue
        # 跳过 YAML/compose 键值行 与 纯提示行(与 _plan_to_steps 一致)
        if re.match(r"^[\w.-]+\s*:", line) and not re.search(r"[$()|&;<>`]", line):
            continue
        if re.match(r"^\s*-\s+", line) and not re.search(r"[$()|&;<>`]", line):
            continue
        if re.match(r"^(执行|运行|启动|步骤|部署|安装|配置|验证)\s*[:：]\s*", line):
            continue
        no += 1
        desc = " ".join(pending_desc).strip()
        pending_desc = []
        kind = _plan_step_kind(line)
        steps.append({"no": no, "desc": desc, "cmd": line, "kind": kind})
    return steps


# ─── 原 L2635-2648 ───
def _plan_step_kind(cmd: str) -> str:
    """按命令特征粗略归类, 用于前端步骤卡片打标签(视觉分类, 不影响执行)。"""
    c = cmd.lower()
    if re.search(r"\b(docker pull|docker run|docker compose up|docker build)\b", c) or "pull " in c:
        return "pull"
    if re.search(r"\b(sed |tee |cat >|echo .*[>]|\bchmod|\bchown|\bmkdir|touch |\bapply -f\b|kubectl apply)", c):
        return "config"
    if re.search(r"\b(systemctl (start|enable|restart)|nohup |redis-server|& )", c):
        return "start"
    if re.search(r"\b(install|yum |dnf |apt-get|apk |make |go build|curl .*\.(gz|tgz|rpm|deb)|\btar)", c):
        return "install"
    if re.search(r"\b(verify|check|ping|is-active|status|ps |ss |test |curl .*ping|redis-cli|mysqladmin|pg_isready)", c):
        return "verify"
    return "other"


# ─── 原 L2651-2683 ───
def _plan_to_steps(plan: str, deploy_type: str = "native") -> list:
    """从部署方案文本中提取「可执行的 shell 命令步骤」。

    - 跳过注释(#)、空行、YAML/compose 键值行(如 services:/image:/ports:)以及纯提示行;
    - 验证/清理/占位类命令(docker compose ps|down、systemctl is-active、pgrep 等)不作为部署步骤执行;
    - 返回的命令即为「AI 生成方案」中被确认要执行的步骤, 供部署流逐步执行(对标 SOP)。"""
    steps = []
    if not plan:
        return steps
    for ln in plan.splitlines():
        line = (ln or "").strip()
        if not line or line.startswith("#"):
            continue
        # 跳过 markdown 代码围栏
        if line.startswith(("```", "~~~")):
            continue
        # 跳过 YAML/compose 键值行: 形如 "services:" / "  image: xxx"(无 shell 元字符)
        if re.match(r"^[\w.-]+\s*:", line) and not re.search(r"[$()|&;<>`]", line):
            continue
        # 跳过 YAML 列表项(如 "- 6379:6379" 是 compose 端口映射, 非命令)
        if re.match(r"^\s*-\s+", line) and not re.search(r"[$()|&;<>`]", line):
            continue
        # 跳过纯提示行(如 "执行: docker compose up -d" 之前无注释头的残留)
        if re.match(r"^(执行|运行|启动|步骤|部署|安装|配置|验证)\s*[:：]\s*", line):
            continue
        # 跳过验证/信息类命令(由"执行部署"内部的验证逻辑完成, 不重复执行)
        if re.match(r"^(systemctl is-active|pgrep|pidof|docker compose ps|docker compose down|ss -tln|curl -s |echo (UP|DOWN)\b)", line):
            continue
        # 跳过 helm/ha 配方提示(不可直接在本机执行)
        if deploy_type in ("helm", "ha") and line.startswith("helm "):
            continue
        steps.append(line)
    return steps


# ─── 原 L2686-2703 ───
def _apply_plan_params(cmd: str, params: dict) -> str:
    """把用户填写的定制参数替换进方案命令。

    - <%=KEY%> 占位符(AI 生成方案中密码类参数用此占位, 避免明文泄漏) → 实际参数值;
    - {{key}} 占位符(与 _inject_native_params 兼容) → 实际参数值。"""
    if not params:
        return cmd
    for key, val in (params or {}).items():
        if val is None:
            val = ""
        # <%=KEY%> 形式(大小写不敏感): 如 <%=REDIS_PASSWORD%>、<%=redis_password%>
        cmd = re.sub(r"<%==?\s*" + re.escape(str(key).upper()) + r"\s*[%=]>", str(val), cmd)
        cmd = re.sub(r"<%==?\s*" + re.escape(str(key).lower()) + r"\s*[%=]>", str(val), cmd)
        # {{key}} 形式(大小写都尝试)
        cmd = cmd.replace("{{%s}}" % key, str(val))
        cmd = cmd.replace("{{%s}}" % key.upper(), str(val))
        cmd = cmd.replace("{{%s}}" % key.lower(), str(val))
    return cmd


# ─── 原 L2706-2716 ───
def _get_deploy_provider(db):
    from app.models import AIProvider
    return db.query(AIProvider).filter(AIProvider.is_enabled == True).first()  # noqa: E712


# bash 内部瞬态变量(随每次 shell 变化/无跨步骤意义), 变量持久化时跳过
_SHELL_TRANSIENT_VARS = {
    "SHLVL", "RANDOM", "LINENO", "SECONDS", "PPID", "EUID", "UID",
    "GROUPS", "BASHOPTS", "SHELLOPTS", "BASH_ALIASES", "BASH_CMDS",
    "PWD", "OLDPWD", "IFS", "OPTIND", "OPTERR", "BASH_REMATCH",
}


# ─── 原 L2719-2742 ───
def _extract_assignments(cmd: str) -> list:
    """提取命令文本中的纯赋值行(export X=value / X=value), 供跨步骤变量持久化。

    仅提取「单 token 值、无命令连接符」的赋值(可带结尾分号), 例如:
      CFG=/etc/redis/redis.conf;                → export CFG=/etc/redis/redis.conf
      export DEPLOY_DIR='/data/redis1'          → export DEPLOY_DIR='/data/redis1'
    不提取复合命令行(含 ; && || 再接后续命令)、X=$(cmd) 动态赋值与瞬态内部变量。
    返回可直接 source 的 export 语句列表。
    """
    result = []
    for line in (cmd or "").splitlines():
        stripped = line.strip().rstrip(";").strip()
        # 逐条: export X=value 或 X=value, 值必须是单个 token(不含空格/命令符)
        m = re.match(r"^(export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(\S+)$", stripped)
        if not m:
            continue
        var_name, var_value = m.group(2), m.group(3)
        if var_name in _SHELL_TRANSIENT_VARS:
            continue
        # 排除 X=$(cmd) / X=`cmd` 动态赋值(source 时重复求值可能有副作用)
        if var_value.startswith("$(") or var_value.startswith("`"):
            continue
        result.append(f"export {var_name}={var_value}")
    return result


# ─── 原 L2745-2765 ───
def _native_step_wrapper(step: str, install_id: int) -> str:
    """构造「单步独立执行 + 跨步变量持久化」的远程命令包装。

    - 步骤内容 base64 编码落 tmp 脚本, 规避引号/特殊字符转义问题;
    - 执行前 source vars 文件恢复之前步骤 export 的变量(跨步骤 shell 变量上下文);
    - 以 bash 子进程执行步骤(防止步骤内 exit 杀死 SSH 会话), 输出存 tmp 后 tail 回显;
    - 末尾回显 __RC__=N 供 _exec_ssh 判定步骤成败。
    """
    iid = int(install_id or 0)
    vars_f = f"/tmp/.aiops_vars_{iid}"
    step_f = f"/tmp/._aiops_step_{iid}.sh"
    out_f = f"/tmp/._aiops_out_{iid}"
    b64 = base64.b64encode((step or "").encode("utf-8")).decode("ascii")
    return (
        "set +e; "
        f"_vf={vars_f}; [ -f \"$_vf\" ] && . \"$_vf\" 2>/dev/null || true; "
        f"echo '{b64}' | base64 -d > {step_f} 2>/dev/null; "
        f"bash {step_f} > {out_f} 2>&1; RC=$?; "
        f"cat {out_f} 2>/dev/null | tail -60; "
        f"echo __RC__=$RC"
    )


# ─── 原 L2768-2791 ───
def safe_json_parse(content: str, fallback=None):
    """统一的 LLM 返回 JSON 解析: 剥 markdown 代码围栏 + 容错 json.loads。
    三处旧代码手写剥壳, 收敛到此处复用(见 CONTRACT 规范评论)。"""
    if fallback is None:
        fallback = {}
    if not content:
        return fallback
    text = (content or "").strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else fallback
    except Exception:
        # 尝试截取第一个 { 到最后一个 } 的裸 JSON
        try:
            s, e = text.find("{"), text.rfind("}")
            if s >= 0 and e > s:
                return json.loads(text[s:e + 1])
        except Exception as _exc7:
            logger.warning("[except:pass] Exception: %s", _exc7, exc_info=True)
    return fallback


# ─── 原 L2794-2835 ───
def _ai_autonomous_decision(db, comp_name, asset_name, deploy_type, system, question,
                            output="", history=None, risk_level="medium", deploy_path="", port=0) -> dict:
    """AI 自主处置决策(对标 AI 自动部署闭环): 步骤失败时在 fix/retry/skip/rollback 中自选并给修复命令。

    返回: {decision, reason, fix_commands, needs_confirm}
    - needs_confirm=True 当: decision==rollback 或 risk_level==high(需人工兜底确认, 高危操作铁律)
    - 无 provider / AI 异常: 回退 needs_confirm=True 走人工确认。
    """
    history = history or []
    provider = _get_deploy_provider(db)
    fallback = {"decision": "", "reason": "AI 不可用, 需人工确认", "fix_commands": [], "needs_confirm": True}
    if not provider:
        return fallback
    from app.services.agent_service import call_llm
    htxt = "; ".join([f"第{h.get('attempt', 1)}次: {h.get('decision', '')}({h.get('result', '')})" for h in history[-3:]]) or "无"
    sys = ("你是资深 SRE 运维专家, 负责组件部署失败后的自主处置。基于失败输出, 在 fix/retry/skip/rollback 中选择一个并给出修复命令。\n"
           "只输出 JSON: {\"decision\":\"fix|retry|skip|rollback\",\"reason\":\"一句话理由(中文)\",\"fix_commands\":[\"命令1\",\"命令2\"]}\n"
           "- fix: 有明确修复手段且修复成功率高(>70%)时选\n- retry: 偶发/瞬时问题(端口占用、资源竞态)时选\n"
           "- skip: 该异常不影响整体可用时选\n- rollback: 无法修复、风险高或反复失败时选\n"
           "fix_commands 最多 3 条, 必须是可执行 shell 命令, 且必须基于真实部署路径, 禁止臆造路径/包名/密码。")
    user = (f"组件: {comp_name}; 目标机: {asset_name}; 部署方式: {deploy_type}; 系统: {system or 'unknown'}; "
            f"部署路径: {deploy_path or '(默认)'}; 端口: {port or '(默认)'};\n"
            f"需决策问题: {question}\n风险等级(前端标注): {risk_level}\n"
            f"历史处置: {htxt}\n失败输出:\n{(output or '')[-1800:]}")
    try:
        resp = call_llm(provider, [{"role": "system", "content": sys}, {"role": "user", "content": user}], timeout_override=60)
        if resp.get("error"):
            return fallback
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = safe_json_parse(content)
        decision = str(parsed.get("decision", "")).strip().lower()
        if decision not in ("fix", "retry", "skip", "rollback"):
            return fallback
        fm = parsed.get("fix_commands") or []
        fm = [str(x) for x in (fm if isinstance(fm, list) else [])][:3]
        needs_confirm = (decision == "rollback") or (risk_level == "high")
        return {
            "decision": decision, "reason": str(parsed.get("reason", "")).strip(),
            "fix_commands": fm, "needs_confirm": needs_confirm,
        }
    except Exception:
        return fallback


# ─── 原 L2838-2849 ───
def _rule_deploy_tip(stage: str, comp_name: str) -> str:
    rules = {
        "preflight": f"{comp_name} 部署前预检完成。建议确认目标机内存/磁盘充足且已具备 Docker 环境。",
        "proxy": "已注入 docker 代理。建议确认代理可达, 否则镜像拉取会超时。",
        "pull": f"正在拉取 {comp_name} 镜像。若失败请检查网络、代理及镜像 tag 是否存在。",
        "deploy": f"{comp_name} 容器启动中。建议观察容器状态是否为 Up。",
        "verify": f"{comp_name} 部署完成校验中。建议执行健康探测确认服务可用。",
        "done": f"{comp_name} 部署成功。建议接着做四合一体检(高可用/配置/漏洞/AI 分析)。",
        "fail": f"{comp_name} 部署失败。建议查看上方错误日志, 定位问题后重试。",
        "helm": f"{comp_name} 采用 K8s/Helm 方式。当前为记录+配方, 需通过 K8s/Helm 引擎执行。",
    }
    return rules.get(stage, f"{comp_name} 部署阶段 {stage} 处理中。")


# ─── 原 L2852-2877 ───
def _ai_deploy_tip(db, stage: str, comp_name: str, asset_name: str, context: str) -> dict:
    """在部署某阶段后调用 AI 生成实时建议; 无 provider / 解析失败时降级规则提示。"""
    rule = _rule_deploy_tip(stage, comp_name)
    provider = _get_deploy_provider(db)
    if not provider:
        return {"ai_generated": False, "stage": stage, "summary": rule}
    from app.services.agent_service import call_llm
    system = ("你是资深 SRE 部署专家。根据组件部署过程中某个阶段的实时日志/上下文, 输出简洁专业的部署建议。"
              "只输出 JSON: {\"summary\":\"一句话结论(≤30字)\",\"advice\":\"可操作的下一步建议,1-3条用;分隔\",\"risk\":\"low|medium|high\"}")
    user = f"组件: {comp_name}; 目标机: {asset_name}; 阶段: {stage};\n上下文日志:\n{(context or '')[:1500]}"
    try:
        resp = call_llm(provider, [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        parsed = json.loads(content)
        parsed["ai_generated"] = True
        parsed["stage"] = stage
        return parsed
    except Exception:
        return {"ai_generated": False, "stage": stage, "summary": rule}


# ─── 原 L2880-2918 ───
def _ai_deploy_diagnosis(db, comp_name, asset_name, deploy_type, full_log, error_hint="") -> dict:
    """部署失败时用 AI 深度诊断根因 + 给修复步骤(自我察觉)。
    返回: {ai_generated, stage='diagnosis', summary, root_cause, steps[], risk}"""
    provider = _get_deploy_provider(db)
    default = {
        "ai_generated": False, "stage": "diagnosis", "root_cause": "",
        "steps": [], "risk": "medium", "summary": "部署失败, 请检查上方日志",
    }
    if not provider:
        return default
    from app.services.agent_service import call_llm
    system = ("你是资深 SRE 部署专家。一次组件部署失败了, 请根据完整部署日志自我察觉并定位根因。"
              "**重要决策原则**(避免无意义重试浪费资源):"
              "1) 看到 'wget: command not found' / 'curl: command not found' / 'tar: command not found' 等命令缺失类错误 →"
              "   **绝不要建议 retry**, 直接给替代方案: 改用 curl(wget 缺失时)/ 安装缺失命令(包管理器可达时)/ 改用已存在的工具;"
              "2) 看到 'Connection timed out' / 'Could not resolve host' / 'Failed to connect' / 'No route to host' 等网络类错误 →"
              "   **不要盲目 retry**(非瞬时问题), 给具体修复: 切国内源(阿里云 mirrors.aliyun.com / 清华 mirrors.tuna.tsinghua.edu.cn)/ 检查代理(NO_PROXY 含内网)/ 配置 DNS(/etc/hosts 硬编码);"
              "3) 看到 'No space left on device' / 'disk full' → 不要 retry, 给清磁盘建议(rm -rf 缓存/日志轮转);"
              "4) 看到 'Permission denied' / 'readonly' → 不要 retry, 给权限修复(chmod/chown/sudo);"
              "5) 看到 'Address already in use' / 'port already' → 不要 retry, 给杀进程/换端口方案;"
              "6) 其它瞬时性错误(网络抖动/race condition)才适合 retry。"
              "只输出 JSON: {\"root_cause\":\"一句话根因(≤40字)\",\"steps\":[\"修复步骤1\",\"修复步骤2\",...],\"summary\":\"结论(≤30字)\",\"risk\":\"low|medium|high\"}")
    user = (f"组件: {comp_name}; 目标机: {asset_name}; 部署方式: {deploy_type};\n"
            f"错误线索: {error_hint[:300]}\n完整部署日志:\n{(full_log or '')[-2500:]}")
    try:
        resp = call_llm(provider, [{"role": "system", "content": system}, {"role": "user", "content": user}])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        parsed = json.loads(content)
        parsed.setdefault("stage", "diagnosis")
        parsed["ai_generated"] = True
        if not isinstance(parsed.get("steps"), list):
            parsed["steps"] = []
        return parsed
    except Exception:
        return default


# ─── 原 L2921-2961 ───
def _ai_final_report(db, comp, asset, install_id, deploy_type, status, log_summary, health=None) -> dict:
    """生成可直接交付的 AI 部署报告(结论/根因/已执行/影响/下一步/风险)。
    返回 report 事件 payload: {ai_generated, title, conclusion, root_cause, executed, impact, next_steps, risks, overview}"""
    provider = _get_deploy_provider(db)
    base = {
        "ai_generated": False, "title": f"{comp['name']} 部署{'成功' if status == 'succeeded' else '失败'}报告",
        "conclusion": f"组件 {comp['name']} 部署{'成功' if status == 'succeeded' else '失败'}",
        "root_cause": "", "executed": "", "impact": "", "next_steps": [], "risks": [],
        "overview": status,
    }
    if not provider:
        return base
    from app.services.agent_service import call_llm
    system = ("你是资深 SRE 部署专家。请基于以下组件部署信息生成一份**可直接交付给客户/团队的正式部署报告**, "
              "语言专业、结论清晰、可行动。只输出 JSON, 字段: "
              "{\"conclusion\":\"总体结论\",\"root_cause\":\"成功则留空, 失败则根因\","
              "\"executed\":\"已执行的部署动作摘要\",\"impact\":\"对业务/系统的影响\","
              "\"next_steps\":[\"后续动作\"],\"risks\":[\"风险项\"]}")
    user = (f"组件: {comp['name']}({comp.get('display_name','')}); 目标机: {asset.name if asset else ''}; "
            f"部署方式: {deploy_type}; 结果: {status}; 安装ID: {install_id};\n"
            f"部署要点摘录:\n{(log_summary or '')[-2000:]}\n"
            f"体检状态: {((health or {}).get('overall_status')) if isinstance(health, dict) else 'N/A'}")
    try:
        resp = call_llm(provider, [{"role": "system", "content": system}, {"role": "user", "content": user}])
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        parsed = json.loads(content)
        parsed["ai_generated"] = True
        parsed["title"] = f"{comp['name']} 部署{'成功' if status == 'succeeded' else '失败'}报告"
        parsed["overview"] = status
        parsed.setdefault("next_steps", [])
        parsed.setdefault("risks", [])
        parsed.setdefault("root_cause", "")
        parsed.setdefault("executed", "")
        parsed.setdefault("impact", "")
        return parsed
    except Exception:
        return base


# ─── 原 L3151-3166 ───
def _build_install_report_key_points(report: dict) -> dict:
    """从组件部署报告组装统一三要素要点(根因/方案/影响)。"""
    from app.routers.agent_sse import _clean_key_point  # 延迟导入
    kpi = report.get("kpi") or {}
    root_cause = report.get("executive_summary", "") or "组件部署报告"
    recs = report.get("recommendations") or []
    solution = "；".join([str(x) for x in recs[:3]]) if recs else (
        "按报告中的改进建议跟进，确认服务稳定运行"
    )
    impact = "部署成功" if report.get("status") in ("success", "running", "deployed") else f"部署状态：{report.get('status')}"
    if kpi:
        impact += f"（步骤 {kpi.get('succeeded_steps', 0)} 成功/{kpi.get('failed_steps', 0)} 失败，验证 {kpi.get('verification_passed')}）"
    return {
        "root_cause": _clean_key_point(root_cause, 100),
        "solution": _clean_key_point(solution, 160),
        "impact": _clean_key_point(impact, 100),
    }


