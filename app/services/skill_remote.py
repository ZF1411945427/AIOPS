"""远程技能源（对接 skills.sh 生态的 GitHub 仓库）。

skilled 市场生态（skills.sh / Anthropic Agent Skills 标准）本质是:
每个技能 = 一个公开 GitHub 仓库 `skills/<name>/SKILL.md`（frontmatter + Markdown）。

本模块把这些社区仓库作为"远程技能源"接入本系统技能库:
  - 目录列表（哪些技能）      -> GitHub Contents API（`/contents/skills`，有限流）
  - 抓取单个 SKILL.md 全文    -> raw.githubusercontent.com（无限流，可靠）
  - 安装                       -> 打包成市场 zip -> import_package(source="remote")

GitHub Token 来源（提升 API 限额 60/时 -> 5000/时，优先级从高到低）:
  1. 入参 token（由路由从 SystemConfig `github_api_token` 解析）
  2. 环境变量 GITHUB_TOKEN

契约见 CONTRACT.md 第十九章 —— `Skill.source` 新增 `remote`。
"""
import io
import json
import os
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import yaml
from sqlalchemy.orm import Session

from app.services import skill_registry
from app.services.config_service import get_config
from app.models import SystemConfig

import logging
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_CACHE_DIR = PROJECT_ROOT / "marketplace" / "remote_cache"

# requests 会话（复用连接，带 UA）
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "AIOps-SkillRemote/1.0"})

# 默认抓取分支
DEFAULT_BRANCH = "main"

# 预设受欢迎仓库（skills.sh 榜单 / 官方生态）
PRESET_REPOS = [
    {"owner": "anthropics", "repo": "skills", "label": "Anthropic 官方技能（docx/pdf/pptx/xlsx 等）"},
    {"owner": "microsoft", "repo": "azure-skills", "label": "Microsoft Azure 技能（rbac/kubernetes/messaging 等）"},
    {"owner": "vercel-labs", "repo": "agent-skills", "label": "Vercel Agent 技能（web-design/react 等）"},
    {"owner": "obra", "repo": "superpowers", "label": "Obra Superpowers（debugging/planning 等）"},
    {"owner": "supabase", "repo": "agent-skills", "label": "Supabase 技能（postgres 等）"},
]

_TIMEOUT = 20


def _ensure_cache():
    RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def list_presets() -> List[Dict[str, str]]:
    return PRESET_REPOS


def resolve_github_token(db: Optional[Session] = None,
                         fallback: Optional[str] = None) -> str:
    """解析 GitHub Token：优先级 入参 fallback > 系统配置 SystemConfig > 环境变量。"""
    if fallback and isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    if db is not None:
        try:
            cfg_val = get_config(db, "github_api_token", "")
            if cfg_val and cfg_val.strip() and cfg_val.strip() != "***":
                return cfg_val.strip()
        except Exception as _exc:
            logger.warning("[except:pass] Exception: %s", _exc, exc_info=True)
    return os.environ.get("GITHUB_TOKEN", "").strip()


def _headers(token: str = "") -> Dict[str, str]:
    h = {"User-Agent": "AIOps-SkillRemote/1.0"}
    if token:
        h["Authorization"] = f"token {token}"
    return h


class _RateLimitError(Exception):
    """GitHub API 限流。"""


def _api_json(url: str, token: str = "") -> Any:
    resp = _SESSION.get(url, headers=_headers(token), timeout=_TIMEOUT)
    if resp.status_code == 403:
        raise _RateLimitError("GitHub API 限流(403)")
    if resp.status_code == 404:
        raise ValueError(f"GitHub 仓库/路径不存在: {url}")
    resp.raise_for_status()
    return resp.json()


# ─── LLM 相关性判断 + 中文化（AIOps 场景收敛）──────────────────────
# 远程市场的技能五花八门(文档/设计/艺术等不相关), 用 LLM 一次调用批量判断
# 每个技能是否与 AIOps 运维相关 + 自动翻译描述/正文; 无 LLM Provider 时全降级为
# 相关=保留(不误杀) + 英文原文, 保证功能可用。

_LLM_PICK_PROMPT = """你是 AIOps 智能运维平台的技术评估者。下面有一批 AI Agent 技能(SKILL.md)。
请逐条判断每个技能是否与本平台相关 —— 相关指: 面向 IT/云/运维/SRE/AIOps 生产场景
(如监控/告警/故障排查/日志/指标/kubernetes/docker/数据库/网络/安全/部署/容灾/性能优化/
troubleshooting/root cause/problem diagnosis 等)。纯办公文档(docx/pdf/ppt)、纯 UI 设计、
纯艺术/动漫/营销/娱乐类技能判为不相关。

同时把 description 翻译成简体中文。

只输出一个 JSON 数组(无其他文字), 数组元素与输入一一对应, 每项:
{"name": "技能名", "relevant": true/false, "reason": "一句话中文原因", "description_zh": "中文描述"}
"""

_LLM_TRANSLATE_PROMPT = """你是专业的技术文档翻译。把下面的英文技术指令/说明完整翻成简体中文。
要求: 保留 Markdown 结构、代码块、命令行、文件名、URL、占位符、frontmatter 原样不变;
只翻译自然语言部分; 专业术语(如 RBAC、SLO、Deployment)可保留英文或加中文括号。只输出翻译结果。"""


def _has_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _pick_llm_provider(db: Session):
    from app.models import AIProvider
    if not db:
        return None
    try:
        return db.query(AIProvider).filter(AIProvider.is_enabled == True).first()
    except Exception:
        return None


def _llm_call(db: Session, messages: List[Dict], max_tokens: int = 1500) -> str:
    """调用 LLM 返回纯文本。任何异常/无 provider → 返回 ''。"""
    from app.services.agent_service import call_llm
    provider = _pick_llm_provider(db)
    if not provider:
        return ""
    try:
        resp = call_llm(provider, messages, timeout_override=45, max_tokens_override=max_tokens)
        if not resp or "error" in resp:
            return ""
        choices = resp.get("choices", [])
        if not choices:
            return ""
        msg = choices[0].get("message", {})
        text = msg.get("content", "") or ""
        if isinstance(text, list):
            text = "".join(t.get("text", "") for t in text if isinstance(t, dict))
        text = (text or "").strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1] if text.count("```") >= 2 else text.replace("```", "").strip()
        return text
    except Exception:
        return ""


def _parse_json_array(text: str) -> Optional[List[Dict]]:
    """从 LLM 输出里尽力抽 JSON 数组。失败返回 None。"""
    if not text:
        return None
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
        return data if isinstance(data, list) else None
    except Exception:
        return None


def evaluate_and_translate_skills(db: Session, skills: List[Dict[str, Any]]) -> None:
    """批量: LLM 判断每个技能是否运维相关 + 翻译描述。就地更新 skills。
    无 LLM/失败 → 全部 relevant=True, description 保留英文原文(不误杀)。"""
    for s in skills:
        s.setdefault("relevant", True)
        s.setdefault("reason", "")
        s.setdefault("description_zh", "")
    if not skills:
        return
    brief = [{"name": s.get("name", ""), "description": (s.get("description") or "")[:280]} for s in skills]
    try:
        text = _llm_call(db, [
            {"role": "system", "content": _LLM_PICK_PROMPT},
            {"role": "user", "content": json.dumps(brief, ensure_ascii=False)},
        ], max_tokens=2048)
    except Exception:
        text = ""
    arr = _parse_json_array(text)
    if not arr:
        return
    by_name = {item.get("name"): item for item in arr if isinstance(item, dict)}
    for s in skills:
        hit = by_name.get(s.get("name"))
        if not hit:
            continue
        s["relevant"] = bool(hit.get("relevant", True))
        s["reason"] = str(hit.get("reason") or "")
        zh = str(hit.get("description_zh") or "").strip()
        if zh:
            s["description_zh"] = zh


def _translate_text(db: Session, text: str, max_tokens: int = 2048) -> str:
    """翻译单段文本为简体中文。无 LLM/失败 → 返回原文。"""
    text = (text or "").strip()
    if not text:
        return ""
    if _has_chinese(text[:200]):
        return text
    out = _llm_call(db, [
        {"role": "system", "content": _LLM_TRANSLATE_PROMPT},
        {"role": "user", "content": text[:8000]},
    ], max_tokens=max_tokens)
    return out or text


def translate_skill_content(db: Session, content: str) -> str:
    """翻译整份 SKILL.md(frontmatter 描述 + 正文), 保留 name/结构/代码。失败返回原文。"""
    meta, body = skill_registry.parse_frontmatter(content)
    if not meta or not meta.get("name"):
        return content
    translated_desc = ""
    if _meta_value(meta, "description"):
        translated_desc = _translate_text(db, _meta_value(meta, "description"), max_tokens=512)
    translated_body = ""
    if (body or "").strip():
        translated_body = _translate_text(db, body, max_tokens=4096)
    if not translated_desc and not translated_body:
        return content
    new_meta = dict(meta)
    if translated_desc:
        if isinstance(meta.get("metadata"), dict):
            new_meta = dict(meta)
            new_meta["metadata"] = dict(meta["metadata"])
            new_meta["metadata"]["description"] = translated_desc
        else:
            new_meta["description"] = translated_desc
    # 用 yaml 序列化 frontmatter(保留嵌套 metadata), 避免手工拼串破坏结构
    fm = yaml.safe_dump(new_meta, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{fm}\n---\n\n{translated_body or (body or '').strip()}"
# 当 GitHub API 被限流(403) 时,对已知仓库用这份静态目录驱动 raw 抓取(SKILL.md 用 raw 不限流)。
# 仅收录已核实存在的技能名,避免列出 404 假条目。未收录的仓库在 API 限流时给出提 token 的提示。
_CURATED = {
    "anthropics/skills": [
        "docx", "pdf", "pptx", "xlsx", "frontend-design", "webapp-testing",
        "skill-creator", "mcp-builder", "claude-api", "theme-factory",
        "algorithmic-art", "brand-guidelines", "canvas-design", "doc-coauthoring",
        "internal-comms", "slack-gif-creator", "web-artifacts-builder",
    ],
}


def _meta_value(meta: Dict[str, Any], key: str, default: str = "") -> str:
    """读取 frontmatter 字段。部分仓库(如 microsoft/azure-skills)把 author/version 嵌套在 metadata: 下。"""
    v = meta.get(key)
    if v is None:
        md = meta.get("metadata")
        if isinstance(md, dict):
            v = md.get(key)
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v) if v is not None else default


def _fetch_skill_meta(owner: str, repo: str, name: str, branch: str, token: str = "") -> Dict[str, Any]:
    """raw 抓取单个 SKILL.md 并解析元数据（raw 不限流）。"""
    skill = {"name": name, "path": f"skills/{name}", "description": "", "version": "",
             "author": "", "category": "", "license": "", "fetched": False}
    try:
        text = _raw_text(
            f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/skills/{name}/SKILL.md",
            token=token)
        meta, _ = skill_registry.parse_frontmatter(text)
        skill["description"] = _meta_value(meta, "description")[:300]
        skill["version"] = _meta_value(meta, "version")
        skill["author"] = _meta_value(meta, "author")
        skill["category"] = _meta_value(meta, "category")
        skill["license"] = _meta_value(meta, "license")
        skill["fetched"] = True
    except Exception:
        skill["description"] = "（SKILL.md 抓取失败，可尝试预览/安装看详情）"
    return skill


def list_repo_skills(owner: str, repo: str, branch: str = DEFAULT_BRANCH,
                     token: str = "", db: Optional[Session] = None) -> List[Dict[str, Any]]:
    """列出仓库 skills/ 目录下的技能。每个技能元数据来自 raw 抓取的 SKILL.md（raw 不限流）。"""
    owner = (owner or "").strip().strip("/")
    repo = (repo or "").strip().strip("/")
    if not owner or not repo:
        raise ValueError("仓库格式应为 owner/repo")
    token = resolve_github_token(db, token)
    repo_key = f"{owner}/{repo}"
    names: Optional[List[str]] = None
    # 1) 优先 contents API 列目录
    try:
        entries = _api_json(
            f"https://api.github.com/repos/{owner}/{repo}/contents/skills?ref={branch}", token=token)
        names = [e.get("name") for e in entries if e.get("type") == "dir" and e.get("name")]
    except _RateLimitError:
        # API 限流 -> 命中精选目录则用静态清单兜底（raw 仍可用）
        names = _CURATED.get(repo_key)
        if not names:
            raise ValueError(
                f"仓库 {repo_key} 目录拉取失败(GitHub API 限流)。"
                f"请到「技能市场 → 远程技能源 → GitHub Token」填写 token 提升限额后重试；"
                f"或改用内置精选仓库 anthropics/skills。")
    if not names:
        raise ValueError(f"仓库 {owner}/{repo} 的 skills/ 目录下没有技能子目录")
    # 2) raw 抓取每个 SKILL.md 解析元数据（无限流）
    out: List[Dict[str, Any]] = []
    for name in names:
        out.append(_fetch_skill_meta(owner, repo, name, branch, token))
    out.sort(key=lambda s: s["name"])
    # 3) LLM 批量判断运维相关性 + 翻译描述(AIOps 场景收敛; 无 LLM 降级不误杀)
    evaluate_and_translate_skills(db, out)
    # 4) 来自精选目录/API 限流的仓库: 若抓取失败, 全量 fallback 字段
    for s in out:
        s.setdefault("relevant", True)
        s.setdefault("reason", "")
        s.setdefault("description_zh", "")
    return out


def _raw_text(url: str, token: str = "") -> str:
    resp = _SESSION.get(url, headers=_headers(token), timeout=_TIMEOUT)
    if resp.status_code == 404:
        raise ValueError(f"未找到 SKILL.md: {url}")
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def preview_remote_skill(owner: str, repo: str, skill: str, branch: str = DEFAULT_BRANCH,
                         token: str = "", db: Optional[Session] = None) -> Dict[str, Any]:
    """预览单个远程技能: 返回元数据 + SKILL.md 正文（供前端展示指令）。"""
    owner = owner.strip().strip("/")
    repo = repo.strip().strip("/")
    skill = skill.strip().strip("/")
    token = resolve_github_token(db, token)
    text = _raw_text(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/skills/{skill}/SKILL.md",
                     token=token)
    meta, body = skill_registry.parse_frontmatter(text)
    # 翻译/相关性任何一步失败都降级到原文, 不应阻塞预览
    body_zh = ""
    desc_zh = ""
    relevance = {"relevant": True, "reason": ""}
    try:
        body_zh = _translate_text(db, (body or "").strip(), max_tokens=4096)
    except Exception:
        body_zh = ""
    try:
        if _meta_value(meta, "description"):
            desc_zh = _translate_text(db, _meta_value(meta, "description"), max_tokens=512)
    except Exception:
        desc_zh = ""
    try:
        rel = _llm_call(db, [
            {"role": "system", "content": _LLM_PICK_PROMPT},
            {"role": "user", "content": json.dumps(
                [{"name": skill, "description": (_meta_value(meta, "description"))[:280]}], ensure_ascii=False)},
        ], max_tokens=512)
        arr = _parse_json_array(rel)
        if arr and isinstance(arr[0], dict):
            relevance = {"relevant": bool(arr[0].get("relevant", True)),
                         "reason": str(arr[0].get("reason") or "")}
    except Exception as _exc1:
        logger.warning("[except:pass] Exception: %s", _exc1, exc_info=True)
    return {
        "name": _meta_value(meta, "name", default=skill) or skill,
        "version": _meta_value(meta, "version", "1.0.0"),
        "author": _meta_value(meta, "author"),
        "license": _meta_value(meta, "license"),
        "category": _meta_value(meta, "category"),
        "risk_level": _meta_value(meta, "risk_level", "read_only"),
        "description": _meta_value(meta, "description"),
        "description_zh": desc_zh,
        "keywords": meta.get("keywords") or [],
        "tools_required": meta.get("tools_required") or [],
        "frontmatter": {k: v for k, v in meta.items()},
        "body": (body or "").strip(),
        "body_zh": body_zh,
        "content": text,
        "relevant": relevance["relevant"],
        "reason": relevance["reason"],
        "installed": False,
    }


def install_remote_skill(db: Session, owner: str, repo: str, skill: str,
                         created_by: Optional[int] = None, branch: str = DEFAULT_BRANCH,
                         token: str = ""):
    """从远程仓库安装单个技能到技能库（source=remote）。重名直接报 ValueError。"""
    owner = owner.strip().strip("/")
    repo = repo.strip().strip("/")
    skill = skill.strip().strip("/")
    token = resolve_github_token(db, token)
    text = _raw_text(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/skills/{skill}/SKILL.md",
                     token=token)
    # 全文翻译为中文(保留 name/frontmatter/代码/命令/URL), 存储为 source=remote
    text_zh = translate_skill_content(db, text)
    # 复用 zip 导入逻辑（单 SKILL.md 即 manifest）
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SKILL.md", text_zh)
    return skill_registry.import_package(db, buf.getvalue(), created_by=created_by, source="remote")
