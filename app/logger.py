"""结构化日志模块：基于 loguru，统一日志格式和级别，支持 trace_id 全链路串联。

用法:
    from app.logger import logger
    logger.info("消息")
    logger.error("错误", extra={"module": "auth"})
    # 请求级 trace_id:
    logger.bind(trace_id="xxx").info("...")   # 或经中间件自动注入

trace_id: 每个 HTTP 请求在中间件里生成/透传，写进日志 extra[trace_id]，
可把一次请求跨服务的所有日志串起来（D3）。
JSON 模式: 设环境变量 AIOPS_LOG_JSON=1 输出 JSON 行(便于采集到 ELK/日志系统)。
"""
import sys
import os
import json
from pathlib import Path
from loguru import logger as _logger
from app.config import LOG_LEVEL, APP_ENV

# 移除默认 handler
_logger.remove()

# 默认 extra: trace_id 缺省为 "-"，保证 {extra[trace_id]} 不报错
_logger.configure(extra={"trace_id": "-"})

_JSON = os.environ.get("AIOPS_LOG_JSON", "").lower() in ("1", "true", "yes")

# 文本日志格式
_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "trace_id=<cyan>{extra[trace_id]}</cyan> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
)


def _json_serializer(record):
    sub = record["extra"]
    payload = {
        "time": record["time"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        "level": record["level"].name,
        "trace_id": sub.get("trace_id", "-"),
        "logger": record["name"],
        "function": record["function"],
        "line": record["line"],
        "message": record["message"],
    }
    for k, v in sub.items():
        if k != "trace_id":
            payload[k] = str(v)
    rec = {"text": record["message"], **payload}
    return json.dumps(rec, ensure_ascii=False, default=str) + "\n"


# 控制台输出
if _JSON:
    _logger.add(sys.stderr, format=_json_serializer, level=LOG_LEVEL)
else:
    _logger.add(
        sys.stderr,
        format=_LOG_FORMAT,
        level=LOG_LEVEL,
        colorize=APP_ENV == "dev",
        backtrace=APP_ENV == "dev",
        diagnose=APP_ENV == "dev",
    )

# 文件输出（按天轮转，保留 30 天）
_LOG_DIR = os.environ.get("AIOPS_LOG_DIR", str(Path(__file__).resolve().parent.parent / "logs"))
if not os.path.exists(_LOG_DIR):
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
    except Exception:
        pass

if _JSON:
    _logger.add(
        os.path.join(_LOG_DIR, "aiops_{time:YYYY-MM-DD}.log"),
        format=_json_serializer,
        level=LOG_LEVEL,
        rotation="00:00",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
    )
else:
    _logger.add(
        os.path.join(_LOG_DIR, "aiops_{time:YYYY-MM-DD}.log"),
        format=_LOG_FORMAT,
        level=LOG_LEVEL,
        rotation="00:00",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        backtrace=True,
        diagnose=APP_ENV == "dev",
    )

logger = _logger
