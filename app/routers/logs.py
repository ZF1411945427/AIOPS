import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.template_utils import get_templates
from app.models import DataSource

router = APIRouter(prefix="/logs", tags=["logs"])
templates = get_templates()


# ─── JSON API（供 Vue 前端调用，保留 HTML 路由作 fallback）───

@router.get("/api/sources")
def api_log_sources(db: Session = Depends(get_db)):
    """返回日志类数据源列表 (elasticsearch / loki)."""
    sources = db.query(DataSource).filter(
        DataSource.type.in_(["elasticsearch", "loki"])
    ).all()
    return JSONResponse([{
        "id": s.id, "name": s.name, "endpoint": s.endpoint or "",
        "type": s.type, "enabled": bool(s.enabled),
    } for s in sources])


import re

_DEDUP_TS_HEADER = re.compile(
    r'^\[[^\]]*?(?:\d{4}[-/]\d{2}[-/]\d{2}[\sT]\d{2}:\d{2}:\d{2}[^\]]*)\]\s*'
)


def _dedup_logs(logs: list) -> list:
    """降噪: 折叠相邻的相同日志(同服务+同消息),合并为一条并记录重复次数.

    比较前会归一化消息:去掉首段 `[xxx]` 中的时间戳部分,避免嵌入时间使相同日志无法折叠.
    折叠后记录 `time_start`(最新)和 `time_end`(最旧),前端可显示 `T1 ~ T2` 时间范围.
    日志已按时间倒序排列.
    """
    if not logs:
        return logs

    def _norm(msg: str) -> str:
        return _DEDUP_TS_HEADER.sub("", msg, count=1).strip()

    result = []
    prev_key = None
    for lg in logs:
        norm = _norm(lg.get("message", ""))
        key = (lg.get("service", ""), norm)
        ts = lg.get("timestamp", "")
        if key and key == prev_key and result:
            r = result[-1]
            r["repeat"] = r.get("repeat", 1) + 1
            r["time_end"] = ts  # 最早时间(倒序,后出现的更早)
        else:
            item = dict(lg)
            item["repeat"] = 1
            item["time_start"] = ts  # 最晚时间(倒序,先出现的更新)
            item["time_end"] = ""
            result.append(item)
            prev_key = key
    return result


@router.get("/api/search")
def api_log_search(
    source_id: int = 0,
    query: str = "*",
    time_range: str = "1h",
    page: int = 1,
    size: int = 50,
    index: str = "",
    level: str = "",
    host: str = "",
    service: str = "",
    dedup: int = 1,
    db: Session = Depends(get_db)):
    """日志搜索 JSON API，支持高级过滤，按数据源类型分发 (ES / Loki).

    dedup=1 (默认): 折叠相邻相同日志(降噪); dedup=0: 显示原始日志.
    """
    if source_id <= 0:
        return JSONResponse({"logs": [], "total": 0, "page": page, "size": size, "error": None, "total_pages": 1})
    source = db.query(DataSource).filter(DataSource.id == source_id).first()
    if not source:
        return JSONResponse({"logs": [], "total": 0, "page": page, "size": size, "error": "数据源不存在", "total_pages": 1})
    try:
        if source.type == "elasticsearch":
            logs, total, error = _query_elasticsearch(source, query, time_range, page, size, index, level, host, service)
        elif source.type == "loki":
            logs, total, error = _query_loki(source, query, time_range, page, size, level, host, service)
        else:
            return JSONResponse({"logs": [], "total": 0, "page": page, "size": size, "error": f"不支持的数据源类型: {source.type}", "total_pages": 1})
    except Exception as e:
        logs, total, error = [], 0, str(e)
    if dedup:
        logs = _dedup_logs(logs)
    total_pages = (total + size - 1) // size if total > 0 else 1
    return JSONResponse({
        "logs": logs, "total": total, "page": page, "size": size,
        "error": error, "total_pages": total_pages,
    })

@router.get("/api/indices")
def api_log_indices(source_id: int = 0, db: Session = Depends(get_db)):
    """返回 ES 数据源的索引列表."""
    if source_id <= 0:
        return JSONResponse([])
    source = db.query(DataSource).filter(DataSource.id == source_id).first()
    if not source:
        return JSONResponse([])
    try:
        from elasticsearch import Elasticsearch
        raw = source.auth_config
        if isinstance(raw, str) and raw.strip():
            cfg = json.loads(raw)
        elif isinstance(raw, dict):
            cfg = raw
        else:
            cfg = {}
        auth, api_key = (), ""
        if cfg.get("username") and cfg.get("password"):
            auth = (cfg["username"], cfg["password"])
        api_key = cfg.get("api_key", "")
        if api_key:
            es = Elasticsearch(source.endpoint, api_key=api_key, request_timeout=5)
        elif auth:
            es = Elasticsearch(source.endpoint, basic_auth=auth, request_timeout=5)
        else:
            es = Elasticsearch(source.endpoint, request_timeout=5)
        indices = es.cat.indices(format="json", h="index,docs.count")
        es.close()
        return JSONResponse([{"name": i["index"], "docs": int(i.get("docs.count", 0))} for i in indices])
    except Exception as e:
        return JSONResponse({"warning": str(e)}, status_code=200)


@router.get("/api/jobs")
def api_log_jobs(source_id: int = 0, db: Session = Depends(get_db)):
    """返回 Loki 数据源的 job 标签值列表（供前端服务过滤下拉使用）."""
    if source_id <= 0:
        return JSONResponse([])
    source = db.query(DataSource).filter(DataSource.id == source_id).first()
    if not source or source.type != "loki" or not source.endpoint:
        return JSONResponse([])
    try:
        import requests
        base = source.endpoint.rstrip("/")
        auth_config = {}
        if source.auth_config:
            try:
                auth_config = json.loads(source.auth_config) if isinstance(source.auth_config, str) else (source.auth_config or {})
            except Exception:
                pass
        auth = None
        if auth_config.get("username") and auth_config.get("password"):
            auth = (auth_config["username"], auth_config["password"])
        headers = {}
        if auth_config.get("org_id"):
            headers["X-Scope-OrgID"] = str(auth_config["org_id"])
        resp = requests.get(f"{base}/loki/api/v1/label/job/values", headers=headers, auth=auth, timeout=8)
        if resp.status_code != 200:
            return JSONResponse([])
        return JSONResponse(resp.json().get("data", []))
    except Exception:
        return JSONResponse([])


@router.get("/api/services")
def api_log_services(source_id: int = 0, db: Session = Depends(get_db)):
    """返回 Loki 数据源的真实服务名列表.

    服务名从 filename 标签解析:k8s pod 路径→deployment 名、
    docker 容器路径→容器名(经 132 docker ps 映射)、裸机日志文件→文件名。
    """
    if source_id <= 0:
        return JSONResponse([])
    source = db.query(DataSource).filter(DataSource.id == source_id).first()
    if not source or source.type != "loki" or not source.endpoint:
        return JSONResponse([])
    try:
        import requests
        from app.services.log_query_service import parse_loki_service_name
        base = source.endpoint.rstrip("/")
        auth_config = {}
        if source.auth_config:
            try:
                auth_config = json.loads(source.auth_config) if isinstance(source.auth_config, str) else (source.auth_config or {})
            except Exception:
                pass
        auth = None
        if auth_config.get("username") and auth_config.get("password"):
            auth = (auth_config["username"], auth_config["password"])
        headers = {}
        if auth_config.get("org_id"):
            headers["X-Scope-OrgID"] = str(auth_config["org_id"])
        resp = requests.get(f"{base}/loki/api/v1/label/filename/values", headers=headers, auth=auth, timeout=8)
        if resp.status_code != 200:
            return JSONResponse([])
        services = set()
        for f in resp.json().get("data", []):
            svc = parse_loki_service_name(f)
            if svc:
                services.add(svc)
        return JSONResponse(sorted(services))
    except Exception:
        return JSONResponse([])


def _query_elasticsearch(source, query_str, time_range, page, size, index="", level="", host="", service=""):
    try:
        from elasticsearch import Elasticsearch
    except ImportError:
        return [], 0, "elasticsearch Python 库未安装，请运行: pip install elasticsearch"

    import socket
    from urllib.parse import urlparse
    try:
        parsed = urlparse(source.endpoint)
        hostname = parsed.hostname or "127.0.0.1"
        port = parsed.port or 9200
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((hostname, port))
        sock.close()
        if result != 0:
            return [], 0, f"无法连接到 Elasticsearch {hostname}:{port}（连接超时或被拒绝），请检查数据源地址和网络连通性。"
    except Exception as e:
        return [], 0, f"ES 地址解析失败: {e}"

    raw = source.auth_config
    if isinstance(raw, str) and raw.strip():
        try:
            cfg = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            cfg = {}
    elif isinstance(raw, dict):
        cfg = raw
    else:
        cfg = {}
    auth = ()
    if cfg.get("username") and cfg.get("password"):
        auth = (cfg["username"], cfg["password"])
    api_key = cfg.get("api_key", "")

    try:
        if api_key:
            es = Elasticsearch(source.endpoint, api_key=api_key, request_timeout=8)
        elif auth:
            es = Elasticsearch(source.endpoint, basic_auth=auth, request_timeout=8)
        else:
            es = Elasticsearch(source.endpoint, request_timeout=8)
    except Exception as e:
        return [], 0, f"ES 连接失败: {e}"

    now = datetime.now()
    if time_range == "15m":
        since = now - timedelta(minutes=15)
    elif time_range == "30m":
        since = now - timedelta(minutes=30)
    elif time_range == "6h":
        since = now - timedelta(hours=6)
    elif time_range == "24h":
        since = now - timedelta(hours=24)
    elif time_range == "7d":
        since = now - timedelta(days=7)
    else:
        since = now - timedelta(hours=1)

    filters = [{"range": {"@timestamp": {"gte": since.isoformat(), "lte": now.isoformat()}}}]
    if level:
        levels = [l.strip() for l in level.split(",") if l.strip()]
        if len(levels) == 1:
            filters.append({"term": {"level.keyword": levels[0]}})
        elif len(levels) > 1:
            filters.append({"terms": {"level.keyword": levels}})
    if host:
        filters.append({"wildcard": {"host": {"value": f"*{host}*"}}})
    if service:
        filters.append({"wildcard": {"service": {"value": f"*{service}*"}}})

    must_clause = [{"query_string": {"query": query_str}}] if query_str and query_str != "*" else [{"match_all": {}}]
    es_query = {"bool": {"must": must_clause, "filter": filters}}

    try:
        es_index = index if index else "_all"
        count_resp = es.count(index=es_index, body={"query": es_query})
        total = count_resp.get("count", 0)

        from_idx = (page - 1) * size
        resp = es.search(
            index=es_index,
            body={
                "query": es_query,
                "sort": [{"@timestamp": {"order": "desc"}}],
                "from": from_idx,
                "size": size,
            }
        )
        hits = resp.get("hits", {}).get("hits", [])
        logs = []
        for hit in hits:
            src = hit.get("_source", {})
            logs.append({
                "id": hit.get("_id", ""),
                "index": hit.get("_index", ""),
                "timestamp": src.get("@timestamp", src.get("timestamp", "")),
                "message": src.get("message", src.get("log", json.dumps(src, ensure_ascii=False))),
                "level": src.get("level", src.get("severity", src.get("log_level", "info"))),
                "host": (src.get("host", {}).get("name", "") if isinstance(src.get("host"), dict) else src.get("host", src.get("hostname", ""))),
                "service": (src.get("service", {}).get("name", "") if isinstance(src.get("service"), dict) else src.get("service", src.get("service_name", ""))),
                "source": src,
            })
        es.close()
        return logs, total, None
    except Exception as e:
        try:
            es.close()
        except Exception:
            pass
        return [], 0, f"ES 查询失败: {e}"


_LEVEL_RE = re.compile(
    r'(?im)^\s*'
    r'(?:\[[^\]]*\])?\s*'
    r'(?:level[=:]\s*)?'
    r'(?P<level>fatal|error|warn|warning|info|debug|trace)\b'
)
_LEVEL_INLINE_RE = re.compile(
    r'(?i)\blevel[=:]\s*(?P<level>fatal|error|warn|warning|info|debug|trace)\b'
)
_LEVEL_BRACKET_RE = re.compile(
    r'(?i)\[(?P<level>fatal|error|warn|warning|info|debug|trace)\]'
)

_LEVEL_NORMALIZE = {
    "fatal": "error",
    "warn": "warning",
    "trace": "debug",
}


def _infer_log_level(message: str) -> str:
    """从日志 message 内容推断真实级别.

    依次尝试:
    1. 行首级别(如 "2026-... ERROR xxx" / "level=info ts=...") — 首选
    2. 行内 level=xxx(如 caller=... level=error ...)
    3. 方括号级别(如 "[ERROR]" / "[WARN]")
    返回标准级别(error/warning/info/debug)或空串。
    """
    if not message:
        return ""
    for pat in (_LEVEL_RE, _LEVEL_INLINE_RE, _LEVEL_BRACKET_RE):
        m = pat.search(message)
        if m:
            lv = m.group("level").lower()
            return _LEVEL_NORMALIZE.get(lv, lv)
    return ""


def _query_loki(source, query_str, time_range, page, size, level="", host="", service=""):
    """调用 Loki 适配器查询日志，支持分页切片."""
    from app.services.log_query_service import query_logs as _service_query_logs

    # Loki query_range 的 limit 是"每个 stream"条数。为保证翻页切片数据充足
    # (尤其单 stream 场景),limit 取当前页所需条数,并预留下一页余量。
    limit = min(max(page * size, 200), 500)
    raw_logs, total, error = _service_query_logs(
        source_id=source.id,
        query=query_str,
        time_range=time_range,
        level=level,
        host=host,
        limit=limit,
        service=service,
    )
    if error:
        return [], 0, error

    # 部分 Loki 数据源(如 129 promtail)的 level 标签不可靠:被提成内容里的随机单词
    # (processing/offset/Aug...),LogQL 的 level 过滤对它们无效。
    # 这里对返回的日志做内容级二次推断: 从 message 里的 level=xx / [xx] / 行首 xx
    # 识别真实级别, 覆盖不可靠标签, 并按用户选择做最终过滤。
    # total 也改为"本次取回范围内的实际匹配数"——因为标签 count_over_time 不可靠。
    if level:
        want = level.strip().lower()
        filtered = []
        for lg in raw_logs:
            real = _infer_log_level(lg.get("message", ""))
            if real and (real == want or (want == "error" and real == "fatal")):
                lg["level"] = real
                filtered.append(lg)
        raw_logs = filtered
        total = len(raw_logs)

    start_idx = (page - 1) * size
    page_logs = raw_logs[start_idx:start_idx + size]
    for lg in page_logs:
        lg["id"] = ""
        lg["index"] = "loki"
        lg["source"] = lg.get("source", "loki")
    return page_logs, total, None


@router.post("/api/analyze")
async def api_log_analyze(request: Request, db: Session = Depends(get_db)):
    """AI 分析选中的日志：把勾选日志交给 LLM 做异常根因/关联分析。

    body: {
      "source_id": 1,
      "logs": [{"timestamp": "...", "level": "error", "host": "...", "service": "...", "message": "..."}],
      "question": "可选，自定义分析诉求"
    }
    返回: {ok, analysis, error}
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"error": "未登录"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "请求体格式错误"}, status_code=400)

    logs = body.get("logs") or []
    question = (body.get("question") or "").strip()
    if not logs:
        return JSONResponse({"error": "请先勾选至少一条日志"}, status_code=400)
    if len(logs) > 100:
        return JSONResponse({"error": "单次最多分析 100 条日志"}, status_code=400)

    source = db.query(DataSource).filter(DataSource.id == int(body.get("source_id", 0) or 0)).first()
    source_name = source.name if source else f"数据源#{body.get('source_id')}"

    # 取默认 AI Provider
    from app.models import AgentConfig, AIProvider
    from app.services.agent_service import call_llm
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
    if not provider:
        return JSONResponse({"ok": False, "error": "未配置可用的 AI 模型提供商，请在 AI 设置中配置并启用一个"})

    # 组装日志文本（按时间倒序已由前端保证）
    lines = []
    for i, lg in enumerate(logs[:100], 1):
        ts = (lg.get("timestamp") or "").replace("T", " ")[:19]
        lvl = lg.get("level") or "info"
        host = lg.get("host") or "-"
        svc = lg.get("service") or "-"
        msg = (lg.get("message") or "").strip()
        lines.append(f"{i}. [{ts}] [{lvl}] host={host} service={svc} | {msg}")

    sys_prompt = (
        "你是一名资深 SRE 运维专家，精通日志分析与故障根因定位。"
        f"用户从日志中心（数据源: {source_name}）勾选了 {len(lines)} 条日志请求分析。"
        "请输出结构化分析：\n"
        "1. **异常模式**：识别日志中的错误/告警规律（报错组件、重复频率、关联线索）\n"
        "2. **根因推断**：最可能的故障根因，按可能性排序并说明依据\n"
        "3. **影响评估**：受影响的服务/主机范围与严重程度\n"
        "4. **处置建议**：给出可执行的具体命令或操作步骤（P0/P1/P2 优先级）\n"
        "如果日志无明显异常，请如实说明，并给出排查建议。"
    )
    user_prompt = "以下是被勾选的日志（已按时间倒序）：\n\n" + "\n".join(lines)
    if question:
        user_prompt += f"\n\n用户附加诉求：{question}"

    resp = call_llm(provider, [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ], timeout_override=max(provider.timeout_seconds, 90))
    if resp.get("error"):
        return JSONResponse({"ok": False, "error": f"AI 分析失败: {resp['error']}"})
    try:
        content = resp["choices"][0]["message"]["content"]
    except Exception:
        return JSONResponse({"ok": False, "error": "AI 返回格式异常"})

    return JSONResponse({"ok": True, "analysis": content or "", "provider": provider.default_model, "log_count": len(logs)})

