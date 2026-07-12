"""结构化日志模块：基于 loguru，统一日志格式和级别.

用法:
    from app.logger import logger
    logger.info("消息")
    logger.error("错误", extra={"module": "auth"})
"""
import sys
import os
from loguru import logger as _logger
from app.config import LOG_LEVEL, APP_ENV

# 移除默认 handler
_logger.remove()

# 日志格式
_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
)

# 控制台输出
_logger.add(
    sys.stderr,
    format=_LOG_FORMAT,
    level=LOG_LEVEL,
    colorize=APP_ENV == "dev",
    backtrace=APP_ENV == "dev",
    diagnose=APP_ENV == "dev",
)

# 文件输出（按天轮转，保留 30 天）
_LOG_DIR = os.environ.get("AIOPS_LOG_DIR", "logs")
if not os.path.exists(_LOG_DIR):
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
    except Exception:
        pass

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
