"""集中配置管理：所有密钥、路径、运行参数从环境变量读取。

通过 .env 文件或系统环境变量配置，避免硬编码。
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载项目根目录下的 .env 文件（如存在）
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=str(_env_path), override=False)

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── 密钥类（必须配置，有安全默认值仅用于开发）──
SECRET_KEY = os.environ.get("AIOPS_SECRET_KEY", "aiops-dev-secret-change-in-production-please")
SESSION_SECRET = os.environ.get("AIOPS_SESSION_SECRET", SECRET_KEY)

# AI Provider 加密种子（每个部署应不同）
PROVIDER_ENCRYPT_SEED = os.environ.get("AIOPS_PROVIDER_SEED", "aiops-agent-provider-key-seed")

# Secrets Vault 加密种子（集中保险库，每个部署应不同）
VAULT_ENCRYPT_SEED = os.environ.get("AIOPS_VAULT_SEED", "aiops-secret-vault-key-seed")

# 移动端 JWT 密钥
MOBILE_JWT_SECRET = os.environ.get("MOBILE_JWT_SECRET", "aiops-mobile-secret-dev")

# ── 数据库 ──
DB_DIR = os.environ.get("AIOPS_DB_DIR", str(PROJECT_ROOT / "db"))
DEMO_DB_PATH = os.environ.get("AIOPS_DEMO_DB", str(Path(DB_DIR) / "aiops.db"))
REAL_DB_PATH = os.environ.get("AIOPS_REAL_DB", str(Path(DB_DIR) / "aiops_real.db"))

# 数据库连接串（统一在此配置，database.py 从此导入）
# AIOPS_DB_URL 显式指定时优先（兼容测试/CI/多环境），不设则走 AIOPS_PG_URL 生产默认
AIOPS_DB_URL = os.environ.get("AIOPS_DB_URL", "").strip()
AIOPS_PG_URL = os.environ.get(
    "AIOPS_PG_URL",
    "postgresql://aiops:aiops-secret@127.0.0.1:5432/aiops",
)

# ── Milvus ──
MILVUS_DB_PATH = os.environ.get("AIOPS_MILVUS_DB", str(Path(DB_DIR) / "milvus" / "kb_v2.db"))
MILVUS_COLLECTION = os.environ.get("AIOPS_MILVUS_COLLECTION", "kb_chunks_v2")

# ── Redis（阶段二：Celery broker + 分布式冷却/节流缓存）──
REDIS_URL = os.environ.get("AIOPS_REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_COOLDOWN_DB = int(os.environ.get("AIOPS_REDIS_COOLDOWN_DB", "1"))  # 分离冷却缓存与 broker，避免互相干扰

# ── Embedding ──
EMBEDDING_MODE = os.environ.get("EMBEDDING_MODE", "local")
EMBEDDING_MODEL_PATH = os.environ.get("EMBEDDING_MODEL_PATH", str(PROJECT_ROOT / "models" / "bge-small-zh-v1.5"))
EMBEDDING_DIMENSION = int(os.environ.get("EMBEDDING_DIMENSION", "512"))
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
RERANKER_MODEL = os.environ.get("RERANKER_MODEL", "")

# ── CORS ──
CORS_ORIGINS = [
    o.strip() for o in os.environ.get(
        "AIOPS_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000"
    ).split(",") if o.strip()
]

# ── 运行参数 ──
APP_ENV = os.environ.get("APP_ENV", "dev")  # dev / prod
LOG_LEVEL = os.environ.get("AIOPS_LOG_LEVEL", "INFO")

# ── 安全：密码哈希方案 ──
# 使用 bcrypt 加盐哈希，向后兼容 sha256 无盐旧密码
PASSWORD_HASH_SCHEME = os.environ.get("AIOPS_PASSWORD_SCHEME", "bcrypt")

# ── 脚本执行安全：命令黑名单 ──
# 危险命令模式，script_exec 和 remediation_service 共用
DANGEROUS_PATTERNS = [
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "rm -rf ~/*",
    "mkfs",
    "dd if=",
    "dd of=/dev/",
    "shutdown",
    "reboot",
    "halt",
    "init 0",
    "init 6",
    "poweroff",
    ":(){:|:&};:",
    "fork bomb",
    "> /dev/sda",
    "> /dev/nvme",
    "chmod -R 777 /",
    "chmod -R 777 ~",
    "chown -R",
    "iptables -F",
    "iptables -X",
    "iptables -t nat -F",
    "curl.*|.*sh",
    "wget.*|.*sh",
    "curl.*|.*bash",
    "wget.*|.*bash",
    "eval ",
    "exec ",
    "kill -9 -1",
    "killall",
    "pkill -9",
    "find / -delete",
    "find / -exec rm",
    "crontab -r",
    "history -c",
    "shred /",
    "umount /",
    "mount /dev/",
    "fdisk",
    "parted",
    "wipefs",
    "> /etc/passwd",
    "> /etc/shadow",
    "> /etc/sudoers",
    "userdel",
    "usermod -L",
    "passwd -l",
    "--no-preserve-root",
    "systemctl stop",
    "systemctl disable",
    "service.*stop",
]

# ── 脚本执行安全：命令白名单（可选，默认关闭）──
# 启用后，只允许白名单内的命令前缀执行（更严格的安全模式）
# 设置环境变量 AIOPS_COMMAND_WHITELIST=cmd1,cmd2,cmd3 启用
COMMAND_WHITELIST = [
    c.strip() for c in os.environ.get("AIOPS_COMMAND_WHITELIST", "").split(",")
    if c.strip()
]

# 文件上传限制
MAX_UPLOAD_SIZE = int(os.environ.get("AIOPS_MAX_UPLOAD_MB", "10")) * 1024 * 1024  # bytes
UPLOAD_ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf", ".docx"}
