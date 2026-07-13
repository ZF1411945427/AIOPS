"""从 requirements_lock.txt 生成清洗后的 requirements.txt + requirements-dev.txt"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LOCK = os.path.join(HERE, "..", "requirements_lock.txt")
ROOT = os.path.join(HERE, "..")

# 生产环境排除的包（Windows专属 / 测试工具 / 未使用框架 / 开发工具）
EXCLUDE = {
    # Windows 专属
    "pywin32", "win32_setctime",
    # 测试
    "pytest", "pytest-timeout", "iniconfig", "pluggy", "playwright",
    # 开发工具
    "virtualenv", "distlib", "invoke", "typer", "shellingham",
    # 未使用框架（项目用 FastAPI）
    "django", "sqlparse", "asgiref",
    # 未使用：langchain 全家桶（代码无 import）
    "langchain", "langchain-core", "langgraph", "langgraph-checkpoint",
    "langgraph-prebuilt", "langgraph-sdk", "langsmith",
}

# torch 单独在 Dockerfile 用 --index-url 装 CPU 版，不放进 requirements
TORCH_LINE = "torch"

prod = []
dev_extra = []
removed = []

with open(LOCK, encoding="utf-8") as f:
    for line in f:
        raw = line.rstrip("\n")
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        pkg = stripped.split("==")[0].split(">=")[0].split("<=")[0].split("[")[0].strip().lower()
        if pkg in EXCLUDE:
            removed.append(stripped)
            continue
        if pkg == TORCH_LINE:
            removed.append(stripped + "  # -> Dockerfile单独装CPU版")
            continue
        prod.append(raw)

# 写生产 requirements
out_prod = os.path.join(ROOT, "requirements.txt")
with open(out_prod, "w", encoding="utf-8") as f:
    f.write("# AIOps 生产依赖（从 requirements_lock.txt 清洗）\n")
    f.write("# 排除: Windows专属/测试工具/langchain全家桶/Django/playwright\n")
    f.write("# torch 在 Dockerfile 中单独安装 CPU 版\n")
    f.write("# 可选依赖（try/except 守护）见文件末尾注释\n")
    f.write("\n")
    for line in prod:
        f.write(line + "\n")
    f.write("\n")
    f.write("# ===== 可选依赖（按需启用，代码中 try/except 守护）=====\n")
    f.write("# psycopg2-binary  # PostgreSQL 数据源连接测试\n")
    f.write("# redis            # Redis 数据源连接测试\n")
    f.write("# prophet          # 时间序列预测（需 matplotlib）\n")
    f.write("# croniter         # 告警 cron 表达式解析\n")
    f.write("# python-docx      # Word 文档解析（RAG）\n")
    f.write("# pypdf            # PDF 文档解析（RAG）\n")
    f.write("# docker           # Docker 数据源采集\n")
    f.write("# pysnmp           # SNMP 监控采集\n")

# 写开发 requirements
out_dev = os.path.join(ROOT, "requirements-dev.txt")
with open(out_dev, "w", encoding="utf-8") as f:
    f.write("# 开发/测试依赖\n")
    f.write("-r requirements.txt\n")
    f.write("\n")
    f.write("pytest==9.1.1\n")
    f.write("pytest-timeout==2.4.0\n")
    f.write("playwright==1.60.0\n")
    f.write("virtualenv==20.34.0\n")

print("=== 生产 requirements.txt: {} 个包 ===".format(len(prod)))
print("=== 排除 {} 个包 ===".format(len(removed)))
for r in removed:
    print("  -", r)
print("\n=== requirements-dev.txt 已生成 ===")
