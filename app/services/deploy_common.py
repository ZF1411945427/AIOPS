"""子模块(由 deploy_service 拆分生成, 勿手改函数体)"""

from app.services.deploy_state import *  # noqa: F401,F403

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import DeployPlan, DeployStep, Asset, AIProvider, AgentConfig
from app.services.ssh_helper import connect_ssh
from app.logger import logger
from app.services.deploy_report import (_generate_fallback_report, _report_to_markdown,
                                        _report_to_html, _report_to_docx)

# ─── 原 L26-27 ───
def _release_exec(plan_id: int):
    _EXEC_LOCK.pop(plan_id, None)


# ─── 原 L61-101 ───
def _collect_env_probes(client, plan: DeployPlan) -> dict:
    """执行全套环境探查命令，返回结构化结果。"""
    def _run(cmd, timeout=15):
        try:
            _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
            out = stdout.read().decode("utf-8", errors="replace").strip()
            err = stderr.read().decode("utf-8", errors="replace").strip()
            return out or err or ""
        except Exception as e:
            return f"[probe_error] {e}"
    result = {}
    result["os"] = _run("cat /etc/os-release 2>/dev/null | head -5 || cat /etc/redhat-release 2>/dev/null || uname -a")
    result["kernel"] = _run("uname -a")
    result["disk"] = _run("df -h / 2>/dev/null | tail -1")
    result["ports"] = _run("ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null")
    result["docker"] = _run("docker info --format '{{.ServerVersion}}' 2>/dev/null || echo 'DOCKER_NOT_AVAILABLE'")
    result["images"] = _run("docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null || echo 'NONE'")
    result["containers"] = _run("docker ps --format '{{.Names}}|{{.Image}}|{{.Ports}}' 2>/dev/null || echo 'NONE'")
    # 探查常用目录和 APP_DIR
    _guess_dirs = ["/data/test-project", "/data", "/opt", "/var/www", "/home", "/app", "/srv"]
    dirs_found = {}
    for d in _guess_dirs:
        _ls = _run(f"ls -la {d} 2>/dev/null && echo '---EXISTS---' || echo '---NOT_EXISTS---'")
        if "---EXISTS---" in _ls:
            content = _ls.split("---EXISTS---")[0].strip()
            dirs_found[d] = content[:2000]
            _compose = _run(f"cat {d}/docker-compose.yml 2>/dev/null || cat {d}/compose.yaml 2>/dev/null || cat {d}/docker-compose.yaml 2>/dev/null || echo 'NO_COMPOSE'")
            if _compose and _compose != "NO_COMPOSE":
                dirs_found[f"{d}/docker-compose"] = _compose[:2000]
            _df = _run(f"cat {d}/Dockerfile 2>/dev/null || echo 'NO_DOCKERFILE'")
            if _df and _df != "NO_DOCKERFILE":
                dirs_found[f"{d}/Dockerfile"] = _df[:2000]
    result["dirs"] = dirs_found
    # 常见端口检测
    _common_ports = [80, 443, 3000, 8080, 8443, 5000, 9000, 5432, 3306, 6379, 27017]
    port_status = {}
    for p in _common_ports:
        ps = _run(f"ss -tlnp | grep ':{p} ' || echo 'FREE'")
        port_status[str(p)] = "IN_USE" if ps and "FREE" not in ps else "FREE"
    result["port_scan"] = port_status
    return result


# ─── 原 L325-326 ───
def _now():
    return datetime.now()


# ─── 原 L329-340 ───
def _get_provider(db: Session):
    config = db.query(AgentConfig).filter(AgentConfig.is_enabled == True).order_by(AgentConfig.id.asc()).first()
    provider = None
    if config and config.default_provider_id:
        provider = db.query(AIProvider).filter(
            AIProvider.id == config.default_provider_id, AIProvider.is_enabled == True).first()
    if not provider:
        from app.services.ai_provider_health import select_healthy_provider
        _all = db.query(AIProvider).filter(AIProvider.is_enabled == True).all()
        _sel, _cand, _skip = select_healthy_provider(_all)
        provider = _sel or (_all[0] if _all else None)
    return provider


# ─── 原 L343-356 ───
def _build_offline_hint(db: Session) -> str:
    """生成离线部署提示: 默认私有 Registry 地址 + 活跃本地包源(供 AI SOP 生成命令时遵守)。"""
    lines = []
    try:
        from app.models import OfflineRegistry, OfflinePackageSource
        reg = db.query(OfflineRegistry).filter(OfflineRegistry.is_default == True).first()  # noqa: E712
        if reg and reg.registry_url:
            lines.append(f"- 镜像私有仓库: {reg.registry_url} (insecure={not reg.is_secure})")
        for s in db.query(OfflinePackageSource).filter(OfflinePackageSource.is_active == True).all():  # noqa: E712
            if getattr(s, "source_url", ""):
                lines.append(f"- 包源({getattr(s, 'os_type', '')}): {s.source_url}")
    except Exception as _exc3:
        logger.warning("[except:pass] Exception: %s", _exc3, exc_info=True)
    return "\n".join(lines)


# ─── 原 L359-364 ───
def _get_asset_ids(plan) -> List[int]:
    try:
        ids = json.loads(plan.asset_ids) if isinstance(plan.asset_ids, str) else (plan.asset_ids or [])
        return ids if isinstance(ids, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


# ─── 原 L367-371 ───
def _get_assets(db: Session, plan) -> List[Asset]:
    ids = _get_asset_ids(plan)
    if not ids:
        return []
    return db.query(Asset).filter(Asset.id.in_(ids)).all()


# ─── 原 L765-776 ───
def _extract_json(text: str) -> Optional[dict]:
    text = text.strip()
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError as _exc4:
            logger.warning("[except:pass] json.JSONDecodeError: %s", _exc4, exc_info=True)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# ─── 原 L820-823 ───
def _sanitize_dirname(name: str) -> str:
    """把计划名转成安全目录名（去空白与路径分隔符）。"""
    safe = re.sub(r"[\s/\\:*?\"<>|]+", "-", (name or "plan").strip())
    return safe or "plan"


# ─── 原 L826-831 ───
def resolve_download_path(plan: DeployPlan) -> str:
    """解析源码自动下载目标路径：
    用户填了 artifact_download_path 则用它；否则返回 '/data/aiops-deploy/<计划名>'。"""
    if plan.artifact_download_path and plan.artifact_download_path.strip():
        return plan.artifact_download_path.strip()
    return f"/data/aiops-deploy/{_sanitize_dirname(plan.name or 'plan')}"


# ─── 原 L834-855 ───
def detect_artifact_source(url: str) -> str:
    """识别源码来源类型：
    - 'git':  Git 仓库地址（github/gitee/gitlab 等）
    - 'http': HTTP(S) 下载地址（tar.gz/zip 等压缩包）
    - 'offline': 离线仓库获取（offline:// 前缀或离线包引用）
    - 'local': 资产本地路径（/opt/app 等，无需下载）
    - '': 无法识别
    """
    if not url:
        return ""
    u = url.strip()
    if u.startswith("offline://") or u.startswith("offline:"):
        return "offline"
    if u.startswith("http://") or u.startswith("https://"):
        if any(h in u.lower() for h in _GIT_HOST_HINTS):
            return "git"
        return "http"
    if any(h in u.lower() for h in _GIT_HOST_HINTS):
        return "git"
    if u.startswith("/") or ":" in u.split("/")[0]:
        return "local"
    return ""


# ─── 原 L858-873 ───
def _run_ssh(asset, cmd: str, timeout: int = 300):
    """在目标机上执行命令，返回 (exit_status, stdout_text)。"""
    client = None
    try:
        client, host = _ssh_connect(asset)
        stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        code = stdout.channel.recv_exit_status()
        return code, (out + err).strip()
    finally:
        if client:
            try:
                client.close()
            except Exception as _exc5:
                logger.warning("[except:pass] Exception: %s", _exc5, exc_info=True)


# ─── 原 L876-887 ───
def _fetch_offline_bundle_path(plan) -> str:
    """离线模式：返回离线包在资产侧可供下载的相对信息。
    这里返回离线包文件路径；实际部署时由用户已加载的离线包承载。"""
    try:
        bundles = None
        from app.models import OfflineRepoBundle
        from app.database import get_db_session
        with get_db_session() as db:
            bundle = db.query(OfflineRepoBundle).filter(OfflineRepoBundle.status == "loaded").first()
            return bundle.file_path if bundle else ""
    except Exception:
        return ""


# ─── 原 L890-999 ───
def auto_download_artifact(db: Session, plan_id: int, force: bool = False) -> dict:
    """探查前自动下载源码到目标机（在线 git/HTTP + 离线仓库两套都支持）。

    根据 artifact_path 识别来源：
      - git: 优先 git clone（目标机有 git 时）；无 git 则 curl 下载 codeload/仓库 zip 并解压
      - http: curl 下载压缩包并解压
      - offline: 离线包方式（复用离线仓库，由手册步骤落地，此处探查离线包存在性）
      - local: 资产本地路径，无需下载
    幂等：目标路径已存在且含 compose/docker-compose 文件时跳过。”
    """
    plan = db.query(DeployPlan).filter(DeployPlan.id == plan_id).first()
    if not plan:
        return {"ok": False, "error": "计划不存在"}
    if not plan.artifact_auto_download:
        return {"ok": True, "skipped": True, "reason": "已关闭自动下载(artifact_auto_download=False)"}

    url = (plan.artifact_path or "").strip()
    source_type = detect_artifact_source(url)
    if source_type == "local" or source_type == "":
        return {"ok": True, "skipped": True, "source": source_type or "unknown", "reason": "本地路径或未填源码地址，无需自动下载"}

    assets = _get_assets(db, plan)
    if not assets:
        return {"ok": False, "error": "计划未关联目标资产"}
    if len(assets) > 1:
        return {"ok": False, "error": "自动下载仅支持单资产计划，多资产请用本地路径或手册自行处理"}

    asset = assets[0]
    dest = resolve_download_path(plan)
    log_lines = []

    # 幂等检查：目标路径已有 compose 则跳过
    code, out = _run_ssh(asset, f"ls {dest}/docker-compose.yml {dest}/docker-compose.yaml {dest}/compose.yaml 2>/dev/null | head -1")
    if code == 0 and out.strip() and not force:
        return {"ok": True, "skipped": True, "source": source_type, "dest": dest,
                "reason": f"源码已存在于 {dest}(含 compose)，跳过下载(force=False 幂等)"}

    try:
        _run_ssh(asset, f"mkdir -p {dest}")
    except Exception as e:
        return {"ok": False, "error": f"创建目录失败: {e}"}

    if source_type == "offline":
        bundle_path = _fetch_offline_bundle_path(plan)
        if not bundle_path:
            return {"ok": False, "error": "离线模式下未找到已加载(loaded)的离线包，请先在离线仓库功能页加载离线包"}
        code, out = _run_ssh(asset, f"ls {dest}", timeout=60)
        log_lines.append(f"[offline] 目标目录: {dest}")
        log_lines.append(f"[offline] 已检测到已加载离线包: {bundle_path} (镜像/包源由手册步骤对接私有 Registry)")
        return {"ok": True, "source": "offline", "dest": dest, "log": log_lines,
                "note": "离线模式：离线包已在仓库侧加载，请确保部署手册步骤通过私有 Registry/包源拉取镜像与软件包"}

    # --- 在线: git / http ---
    if source_type == "git":
        # 目标机有 git → git clone，否则 curl 下载 zip
        _, _has_git = _run_ssh(asset, "command -v git >/dev/null 2>&1 && echo YES || echo NO", timeout=30)
        if _has_git.strip() == "YES":
            code, out = _run_ssh(
                asset,
                f"if [ -d {dest} ] && [ -n \"$(ls -A {dest})\" ]; then echo EXISTS; fi",
                timeout=60,
            )
            if "EXISTS" in out:
                log_lines.append(f"[git] 目录 {dest} 非空，执行 git pull 增量更新")
                pull_cmd = f"cd {dest} && (git pull --ff-only 2>/dev/null || echo PULL_FAILED)"
                _run_ssh(asset, pull_cmd, timeout=300)
                log_lines.append(f"[git] git pull 完成: {dest}")
                return {"ok": True, "source": "git", "dest": dest, "method": "git-clone", "log": log_lines}
            clone_cmd = f"cd {dest} && git clone --depth 1 {url} . 2>&1"
            code, out = _run_ssh(asset, clone_cmd, timeout=600)
            log_lines.append(f"[git] git clone --depth 1: exit={code}")
            log_lines.append((out or "")[-1200:])
            if code != 0:
                return {"ok": False, "error": f"git clone 失败: {(out or '')[-500:]}", "log": log_lines}
            _set_compose_perms(asset, dest, log_lines)
            return {"ok": True, "source": "git", "dest": dest, "method": "git-clone", "log": log_lines}
        # 无 git → curl 下载仓库 zip 并解压
        zip_url = _git_zip_url(url)
        code, out = _run_ssh(
            asset,
            f"curl -fsSL --max-time 300 -o /tmp/_aiops_src.zip \"{zip_url}\" && "
            f"rm -rf {dest}/* && unzip -o -q /tmp/_aiops_src.zip -d /tmp/_aiops_src_x && "
            f"mv /tmp/_aiops_src_x/*/* {dest}/ 2>/dev/null || mv /tmp/_aiops_src_x/* {dest}/ 2>/dev/null; "
            f"rm -rf /tmp/_aiops_src.zip /tmp/_aiops_src_x",
            timeout=400,
        )
        log_lines.append(f"[git->zip] 下载 {zip_url}")
        log_lines.append(f"[git->zip] exit={code}")
        log_lines.append((out or "")[-1200:])
        if code != 0:
            return {"ok": False, "error": f"curl 下载/解压失败: {(out or '')[-500:]}", "log": log_lines}
        _set_compose_perms(asset, dest, log_lines)
        return {"ok": True, "source": "git", "dest": dest, "method": "git-zip", "log": log_lines}

    # http 下载压缩包
    code, out = _run_ssh(
        asset,
        f"curl -fsSL --max-time 300 -o /tmp/_aiops_src.bin \"{url}\" && "
        f"mkdir -p {dest} && rm -rf {dest}/* && "
        f"(file /tmp/_aiops_src.bin | grep -qi zip && unzip -o -q /tmp/_aiops_src.bin -d /tmp/_aiops_src_x || tar -xzf /tmp/_aiops_src.bin -C /tmp/_aiops_src_x) && "
        f"mv /tmp/_aiops_src_x/*/* {dest}/ 2>/dev/null || mv /tmp/_aiops_src_x/* {dest}/ 2>/dev/null; "
        f"rm -rf /tmp/_aiops_src.bin /tmp/_aiops_src_x",
        timeout=400,
    )
    log_lines.append(f"[http] 下载 {url}: exit={code}")
    log_lines.append((out or "")[-1200:])
    if code != 0:
        return {"ok": False, "error": f"HTTP 下载/解压失败: {(out or '')[-500:]}", "log": log_lines}
    _set_compose_perms(asset, dest, log_lines)
    return {"ok": True, "source": "http", "dest": dest, "method": "http-download", "log": log_lines}


# ─── 原 L1002-1015 ───
def _git_zip_url(url: str) -> str:
    """把 Git 仓库主页/zip 地址归一为可直接 curl 下载的 zip 地址（github/gitee 均支持 codeload/archive）。"""
    u = url.rstrip("/")
    if u.endswith(".zip"):
        return u
    if "github.com" in u:
        m = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", u)
        if m:
            return f"https://codeload.github.com/{m.group(1)}/{m.group(2)}/zip/refs/heads/master"
    if "gitee.com" in u:
        m = re.match(r"https?://gitee\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", u)
        if m:
            return f"https://gitee.com/{m.group(1)}/{m.group(2)}/repository/archive/master.zip"
    return u


# ─── 原 L1018-1021 ───
def _set_compose_perms(asset, dest: str, log_lines: list) -> None:
    """下载后确保 compose 文件存在并赋可执行权限（幂等友好）。"""
    code, out = _run_ssh(asset, f"chmod -R +x {dest} 2>/dev/null; ls {dest}/docker-compose.yml {dest}/compose.yaml {dest}/docker-compose.yaml 2>/dev/null | head -1", timeout=60)
    log_lines.append(f"[perm] {out.strip() or '(未找到 compose 文件)'}")


# ─── 原 L1024-1035 ───
def _resolve_command(cmd: str, mapping: dict) -> str:
    def replace(match):
        key = match.group(1)
        val = mapping.get(key, "")
        if val:
            return val
        if key.startswith("ENV_") and key[4:] in mapping:
            val = mapping[key[4:]]
            if val:
                return val
        return f"__UNSET__{key}__"
    return re.sub(r'\$\{(\w+)\}', replace, cmd)


# ─── 原 L1038-1043 ───
def _check_unresolved(cmd: str) -> Optional[str]:
    """检查命令中是否有未解析的 ${ENV_xxx} 占位符，返回第一个未解析的 key。"""
    m = re.search(r'__UNSET__(\w+)__', cmd)
    if m:
        return m.group(1)
    return None


# ─── 原 L1046-1063 ───
def _is_valid_shell_command(cmd: str) -> bool:
    """防御校验：verify/rollback 字段必须是可执行的 shell 命令，而不是 AI 输出的自然语言描述。
    规则：非空、不含中文/日韩文、不含自然语言连接词标记、以命令动作开头。"""
    if not cmd or not cmd.strip():
        return False
    cmd = cmd.strip()
    # 含 CJK 字符 → 判定为自然语言
    if re.search(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]', cmd):
        return False
    # 含"检查是否""预期""状态""成功"等中文词汇特征（已含中文必然命中上一条，冗余防护）
    # 必须看起来像一个命令：不能以中文标点或描述性单词开头
    if re.match(r'^(执行后|检查|确认|验证|显示|确保|等待)[：:\s，,，]', cmd):
        return False
    return True


_OFFLINE_PUBLIC_IMAGES = ["docker.io", "registry.hub.docker.com", "index.docker.io", "hub.docker.com", "ghcr.io", "quay.io", "gcr.io", "docker.easypack.io", "registry.cn-hangzhou.aliyuncs.com", "mirror.ccs.tencentyun.com"]
_PUBLIC_REPO_HINTS = ["archive.ubuntu.com", "security.ubuntu.com", "download.fedoraproject.org", "mirrors.aliyun.com", "repo.huaweicloud.com", "mirrors.tuna.tsinghua.edu.cn", "mirrors.cloud.tencent.com"]


# ─── 原 L1066-1093 ───
def _offline_blocked_reason(plan, cmd: str) -> str:
    """离线模式二次强制校验: 命令含公网 docker 镜像拉取或公网软件源时, 返回拦截原因; 否则返回空串放行。
    仅当 plan.use_offline=True 时启用。识别 docker pull/run/compose 的镜像引用、yum/apt 针对公网源的操作。"""
    if not plan or not getattr(plan, "use_offline", False):
        return ""
    cmd = cmd or ""
    low = cmd.lower()
    # 明确公网镜像仓库引用
    for img in _OFFLINE_PUBLIC_IMAGES:
        if img in low:
            return f"离线模式禁止拉取公网镜像仓库 {img} 的镜像(请改用离线私有 Registry)"
    # docker pull / docker run 引用公网镜像: 仅当是"裸镜像名"(无仓库主机)或显式 docker.io 时拦截
    # 带仓库主机(如 internal.registry/app/x)视为私有/内网仓库, 放行
    if re.search(r'\bdocker\s+(pull|run|create)\b', low):
        _rest = re.split(r'\bdocker\s+(?:pull|run|create)\b', cmd)[-1]
        _cand = ""
        for _t in _rest.split():
            if _t.startswith('-') or _t in ('--','/dev/null'):
                continue
            _cand = _t
            break
        if _cand and ('/' not in _cand or _cand.startswith(('docker.io/', 'registry.hub.docker.com/', 'library/'))):
            return f"离线模式禁止直接 docker pull/run 公网镜像 {_cand}(请改用离线私有 Registry 地址)"
    # 公网软件源
    for hint in _PUBLIC_REPO_HINTS:
        if hint in low:
            return f"离线模式禁止使用公网软件源 {hint}(请改用本地/内网包源)"
    return ""


# ─── 原 L1096-1100 ───
def _assert_online_allowed(plan, cmd: str) -> str:
    """通用: 在线/离线统一入口。离线时返回拦截原因, 在线返回空串。供执行前调用。"""
    if not plan or not getattr(plan, "use_offline", False):
        return ""
    return _offline_blocked_reason(plan, cmd)


# ─── 原 L1103-1114 ───
def _proxy_env_prefix(plan) -> str:
    """为计划生成代理环境变量导出前缀(供执行步骤注入 HTTP_PROXY/HTTPS_PROXY/NO_PROXY)。"""
    if not plan:
        return ""
    parts = []
    if getattr(plan, "http_proxy", ""):
        parts.append("export HTTP_PROXY='%s' http_proxy='%s'" % (plan.http_proxy, plan.http_proxy))
    if getattr(plan, "https_proxy", ""):
        parts.append("export HTTPS_PROXY='%s' https_proxy='%s'" % (plan.https_proxy, plan.https_proxy))
    if getattr(plan, "no_proxy", ""):
        parts.append("export NO_PROXY='%s' no_proxy='%s'" % (plan.no_proxy, plan.no_proxy))
    return " && ".join(parts)


# ─── 原 L1117-1145 ───
def _sync_env_mapping_from_sop(db: Session, plan: DeployPlan) -> None:
    """预检/执行前把 SOP 命令与 doc_raw 中的 ${ENV_xxx} 占位符同步到 env_mapping。
    防止旧版解析产生的计划缺键（旧代码只信 AI 的 env_vars 列表，可能漏掉占位符）。
    只补缺失的键（空值待填），不覆盖用户已填的值。"""
    try:
        current_mapping = json.loads(plan.env_mapping or "{}") if isinstance(plan.env_mapping, str) and plan.env_mapping not in ("{}", "[]") else {}
    except Exception:
        current_mapping = {}
    _placeholder_re = re.compile(r'\$\{(\w+)\}')
    _found_keys = set()
    sop = json.loads(plan.sop_json or "{}")
    if isinstance(sop, dict):
        for _pf in sop.get("preflight", []):
            _found_keys.update(_m.group(1) for _m in _placeholder_re.finditer(_pf.get("command", "")))
    steps = db.query(DeployStep).filter(DeployStep.plan_id == plan.id).all()
    for _s in steps:
        for _field in (_s.command, _s.verify_command, _s.rollback_command):
            if _field:
                _found_keys.update(_m.group(1) for _m in _placeholder_re.finditer(_field))
    if plan.doc_raw:
        _found_keys.update(_m.group(1) for _m in _placeholder_re.finditer(plan.doc_raw))
    changed = False
    for _k in sorted(_found_keys):
        if _k not in current_mapping:
            current_mapping[_k] = ""
            changed = True
    if changed:
        plan.env_mapping = json.dumps(current_mapping, ensure_ascii=False)
        db.commit()


# ─── 原 L1148-1158 ───
def _ssh_connect(asset: Asset) -> tuple:
    try:
        conn_config = json.loads(asset.connection_config or "{}")
    except Exception:
        conn_config = {}
    host = asset.ip or conn_config.get("ssh_host", "")
    port = int(conn_config.get("ssh_port", 22))
    username = conn_config.get("ssh_user", "root")
    password = conn_config.get("ssh_password", "")
    client = connect_ssh(host, port=port, username=username, password=password)
    return client, host


# ─── 原 L3556-3593 ───
def _plan_to_dict(p: DeployPlan) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description or "",
        "artifact_path": p.artifact_path or "",
        "artifact_download_path": p.artifact_download_path or "",
        "artifact_auto_download": bool(p.artifact_auto_download),
        "use_offline": bool(p.use_offline),
        "http_proxy": p.http_proxy or "",
        "https_proxy": p.https_proxy or "",
        "no_proxy": p.no_proxy or "",
        "doc_raw": p.doc_raw or "",
        "doc_file_name": p.doc_file_name or "",
        "asset_ids": _safe_json(p.asset_ids) if p.asset_ids else [],
        "env_mapping": _safe_json(p.env_mapping),
        "environment_probe_json": _safe_json(p.environment_probe_json),
        "env_analysis_json": _safe_json(p.env_analysis_json),
        "sop_json": _safe_json(p.sop_json),
        "status": p.status,
        "preflight_json": _safe_json(p.preflight_json),
        "deploy_report_json": _safe_json(p.deploy_report_json),
        "test_results_json": _safe_json(p.test_results_json),
        "execution_history_json": _safe_json(p.execution_history_json),
        "cleanup_history_json": _safe_json(p.cleanup_history_json),
        "dag_json": _safe_json(p.dag_json),
        "ai_decision_log_json": _safe_json(p.ai_decision_log_json),
        "strategy": p.strategy or "auto",
        "risk_score": p.risk_score or 0,
        "deployment_feature_json": _safe_json(p.deployment_feature_json),
        "health_gate_json": _safe_json(p.health_gate_json),
        "pending_decision": _safe_json(p.pending_decision_json, default=None),
        "last_deployed_at": p.last_deployed_at.isoformat() if p.last_deployed_at else "",
        "deploy_count": p.deploy_count or 0,
        "created_by": p.created_by,
        "created_at": p.created_at.isoformat() if p.created_at else "",
        "updated_at": p.updated_at.isoformat() if p.updated_at else "",
    }


# ─── 原 L3596-3614 ───
def _step_to_dict(s: DeployStep) -> dict:
    return {
        "id": s.id,
        "plan_id": s.plan_id,
        "step_order": s.step_order,
        "description": s.description or "",
        "command": s.command or "",
        "verify_command": s.verify_command or "",
        "rollback_command": s.rollback_command or "",
        "risk_level": s.risk_level,
        "status": s.status,
        "output": s.output or "",
        "diagnosis": s.diagnosis or "",
        "fix_command": s.fix_command or "",
        "retry_count": s.retry_count or 0,
        "precheck_result": s.precheck_result or "",
        "started_at": s.started_at.isoformat() if s.started_at else "",
        "finished_at": s.finished_at.isoformat() if s.finished_at else "",
    }


# ─── 原 L3617-3625 ───
def _safe_json(val, default=None) -> Any:
    if not val:
        return default if default is not None else ({} if val is None else val)
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else val

# ─── 原 L817-817 ───
_GIT_HOST_HINTS = ("github.com", "gitee.com", "gitlab.com", "gitcode.com", "jihulab.com", ".git")


# ─── 原 L1062-1063 ───
_OFFLINE_PUBLIC_IMAGES = ["docker.io", "registry.hub.docker.com", "index.docker.io", "hub.docker.com", "ghcr.io", "quay.io", "gcr.io", "docker.easypack.io", "registry.cn-hangzhou.aliyuncs.com", "mirror.ccs.tencentyun.com"]
_PUBLIC_REPO_HINTS = ["archive.ubuntu.com", "security.ubuntu.com", "download.fedoraproject.org", "mirrors.aliyun.com", "repo.huaweicloud.com", "mirrors.tuna.tsinghua.edu.cn", "mirrors.cloud.tencent.com"]


