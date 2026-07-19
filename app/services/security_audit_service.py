"""安全自查服务：整合 SAST / 依赖 CVE / License 合规 / 安全配置 四类检查。

输出统一聚合报告，供前端「安全自查」仪表盘展示。
- bandit：Python 静态安全扫描（SAST）
- pip-audit：依赖 CVE 扫描（SCA）
- pip-licenses：License 合规清单（SBOM）
- config check：debug / docs / CORS / session / 密码方案等配置基线

扫描结果缓存到 security_reports/ 目录（默认 1 小时 TTL），避免重复慢扫描。
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from app.logger import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
REPORT_DIR = Path(os.environ.get("AIOPS_SECURITY_REPORT_DIR", str(PROJECT_ROOT / "security_reports")))
REPORT_FILE = REPORT_DIR / "latest.json"
CACHE_TTL = int(os.environ.get("AIOPS_SECURITY_CACHE_TTL", "3600"))  # 默认 1 小时


def _run_subprocess(cmd: list, timeout: int = 180) -> tuple[int, str, str]:
    """安全运行子进程，返回 (returncode, stdout, stderr)。超时返回 124。"""
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except FileNotFoundError as e:
        return 127, "", f"command not found: {e}"
    except Exception as e:
        return 1, "", str(e)


def run_bandit() -> dict:
    """运行 bandit SAST 扫描，返回汇总结果。"""
    out_file = REPORT_DIR / "bandit.json"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    # 先清理旧文件
    if out_file.exists():
        try:
            out_file.unlink()
        except Exception:
            pass
    rc, _out, err = _run_subprocess(
        [sys.executable, "-m", "bandit", "-r", "app", "-f", "json", "-o", str(out_file)],
        timeout=180,
    )
    if not out_file.exists():
        return {
            "available": False,
            "error": f"bandit 执行失败 (rc={rc}): {err[:300]}",
            "issues": [],
            "summary": {"high": 0, "medium": 0, "low": 0, "total": 0},
        }
    try:
        data = json.loads(out_file.read_text(encoding="utf-8"))
    except Exception as e:
        return {"available": False, "error": f"bandit 报告解析失败: {e}", "issues": [], "summary": {}}

    results = data.get("results", [])
    issues = []
    sev_count = {"high": 0, "medium": 0, "low": 0}
    for r in results:
        sev = (r.get("issue_severity") or "LOW").lower()
        conf = (r.get("issue_confidence") or "LOW").lower()
        if sev in sev_count:
            sev_count[sev] += 1
        issues.append({
            "severity": sev.upper(),
            "confidence": conf.upper(),
            "test_id": r.get("test_id", ""),
            "cwe": r.get("issue_cwe", {}).get("id") if isinstance(r.get("issue_cwe"), dict) else None,
            "filename": r.get("filename", "").replace("\\", "/").split("/app/")[-1] or r.get("filename", ""),
            "line": r.get("line_number"),
            "text": r.get("issue_text", ""),
            "more_info": r.get("more_info", ""),
        })
    # 按严重度排序
    sev_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    issues.sort(key=lambda x: (sev_order.get(x["severity"], 3), x["filename"], x.get("line") or 0))
    return {
        "available": True,
        "issues": issues,
        "summary": {
            "high": sev_count["high"],
            "medium": sev_count["medium"],
            "low": sev_count["low"],
            "total": len(issues),
        },
    }


def run_pip_audit() -> dict:
    """运行 pip-audit 依赖 CVE 扫描。"""
    out_file = REPORT_DIR / "pip-audit.json"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    if out_file.exists():
        try:
            out_file.unlink()
        except Exception:
            pass
    rc, _out, err = _run_subprocess(
        [sys.executable, "-m", "pip_audit", "-f", "json", "-o", str(out_file)],
        timeout=300,
    )
    if not out_file.exists():
        return {
            "available": False,
            "error": f"pip-audit 执行失败 (rc={rc}): {err[:300]}",
            "vulnerabilities": [],
            "summary": {"vuln_count": 0, "affected_deps": 0},
        }
    try:
        data = json.loads(out_file.read_text(encoding="utf-8"))
    except Exception as e:
        return {"available": False, "error": f"pip-audit 报告解析失败: {e}", "vulnerabilities": [], "summary": {}}

    deps = data.get("dependencies", [])
    vulns = []
    affected = set()
    for dep in deps:
        name = dep.get("name", "")
        version = dep.get("version", "")
        for v in dep.get("vulns", []):
            affected.add(name)
            vulns.append({
                "package": name,
                "version": version,
                "vuln_id": v.get("id", ""),
                "description": (v.get("description") or "")[:300],
                "fix_versions": v.get("fix_versions", []),
            })
    vulns.sort(key=lambda x: x["package"].lower())
    return {
        "available": True,
        "vulnerabilities": vulns,
        "summary": {
            "vuln_count": len(vulns),
            "affected_deps": len(affected),
            "total_deps": len(deps),
        },
    }


def run_license_scan() -> dict:
    """运行 pip-licenses 输出 SBOM + License 合规清单。"""
    try:
        from piplicenses import create_parser, create_licenses_table  # type: ignore
    except Exception as e:
        return {"available": False, "error": f"pip-licenses 未安装: {e}", "licenses": [], "sbom": [], "summary": {}}

    try:
        parser = create_parser()
        args = parser.parse_args([
            "--format=csv", "--with-system", "--with-urls",
            "--with-license-file", "--no-license-path",
            "--with-authors", "--with-description",
        ])
        table = create_licenses_table(args)
        # table 是 prettytable 对象
        rows = table.rows if hasattr(table, "rows") else []
        headers = table.field_names if hasattr(table, "field_names") else []
    except Exception as e:
        return {"available": False, "error": f"pip-licenses 执行失败: {e}", "licenses": [], "sbom": [], "summary": {}}

    licenses = []
    for row in rows:
        rec = dict(zip(headers, row))
        licenses.append({
            "name": rec.get("Name", ""),
            "version": rec.get("Version", ""),
            "license": rec.get("License", ""),
            "url": rec.get("URL", ""),
            "author": rec.get("Author", ""),
            "description": (rec.get("Description") or "")[:200],
        })

    # 高危 License 检测：GPL / AGPL / LGPL / CC-BY-NC / SSPL 等copyleft/传染性协议
    risky_re = re.compile(r"\b(GPL|AGPL|LGPL|CC-BY-NC|SSPL|CC-BY-SA|WTFPL|Ms-RL|EUPL|Sleepycat)\b", re.IGNORECASE)
    risky = []
    for lic in licenses:
        license_text = (lic.get("license") or "") + " " + (lic.get("name") or "")
        if risky_re.search(license_text) and lic.get("license", "").upper() not in ("MIT", "BSD", "APACHE", "APACHE-2.0", "APACHE SOFTWARE LICENSE"):
            # 排除误报（有些包 license 字段写 "GNU" 但实际是 MIT）
            if risky_re.search(lic.get("license") or ""):
                risky.append(lic)
    # 去重
    seen = set()
    risky_dedup = []
    for r in risky:
        key = r["name"] + "@" + r["version"]
        if key not in seen:
            seen.add(key)
            risky_dedup.append(r)

    licenses.sort(key=lambda x: x["name"].lower())
    return {
        "available": True,
        "licenses": licenses,
        "risky_licenses": risky_dedup,
        "summary": {
            "total": len(licenses),
            "risky_count": len(risky_dedup),
        },
    }


def check_security_config() -> dict:
    """检查安全配置基线：debug / docs / CORS / session / 密码方案 / 密钥强度等。"""
    from app import config as _config
    checks = []

    # 1. APP_ENV
    checks.append({
        "key": "app_env",
        "label": "运行环境",
        "value": _config.APP_ENV,
        "status": "pass" if _config.APP_ENV == "prod" else "warn",
        "advice": "生产环境应设置 APP_ENV=prod" if _config.APP_ENV != "prod" else "",
    })

    # 2. /docs /redoc /openapi
    docs_disabled = _config.APP_ENV == "prod"
    checks.append({
        "key": "api_docs_disabled",
        "label": "API 文档关闭 (/docs /redoc /openapi)",
        "value": "已关闭" if docs_disabled else "开发环境开启",
        "status": "pass" if docs_disabled else "warn",
        "advice": "生产环境关闭交互式 API 文档，避免接口裸露" if not docs_disabled else "",
    })

    # 3. CORS
    cors = _config.CORS_ORIGINS
    cors_wildcard = any(o == "*" for o in cors)
    checks.append({
        "key": "cors",
        "label": "CORS 跨域策略",
        "value": ", ".join(cors) if cors else "(空)",
        "status": "fail" if cors_wildcard else ("warn" if not cors else "pass"),
        "advice": "禁止使用 * 全开 CORS" if cors_wildcard else "",
    })

    # 4. Session 密钥强度
    secret = _config.SESSION_SECRET or ""
    weak_secret = secret in ("aiops-dev-secret-change-in-production-please", "") or len(secret) < 16
    checks.append({
        "key": "session_secret",
        "label": "Session 密钥强度",
        "value": "弱密钥/默认值" if weak_secret else "已自定义",
        "status": "fail" if weak_secret else "pass",
        "advice": "生产环境必须通过 AIOPS_SESSION_SECRET 设置 32+ 字符随机密钥" if weak_secret else "",
    })

    # 5. 密码哈希方案
    checks.append({
        "key": "password_hash",
        "label": "密码哈希方案",
        "value": _config.PASSWORD_HASH_SCHEME,
        "status": "pass" if _config.PASSWORD_HASH_SCHEME == "bcrypt" else "warn",
        "advice": "推荐使用 bcrypt 加盐哈希" if _config.PASSWORD_HASH_SCHEME != "bcrypt" else "",
    })

    # 6. 默认管理员密码
    default_pwd = os.environ.get("AIOPS_ADMIN_PASSWORD", "")
    checks.append({
        "key": "admin_password",
        "label": "管理员默认密码",
        "value": "已通过环境变量自定义" if default_pwd else "使用默认 admin123",
        "status": "pass" if default_pwd else "warn",
        "advice": "生产环境应通过 AIOPS_ADMIN_PASSWORD 设置强密码" if not default_pwd else "",
    })

    # 7. 文件上传限制
    checks.append({
        "key": "upload_limit",
        "label": "文件上传大小限制",
        "value": f"{_config.MAX_UPLOAD_SIZE // 1024 // 1024} MB",
        "status": "pass" if _config.MAX_UPLOAD_SIZE <= 20 * 1024 * 1024 else "warn",
        "advice": "建议上传限制 ≤ 20MB" if _config.MAX_UPLOAD_SIZE > 20 * 1024 * 1024 else "",
    })

    # 8. 脚本执行黑名单
    checks.append({
        "key": "script_blacklist",
        "label": "脚本执行危险命令黑名单",
        "value": f"{len(_config.DANGEROUS_PATTERNS)} 条规则",
        "status": "pass" if len(_config.DANGEROUS_PATTERNS) >= 10 else "warn",
        "advice": "建议完善危险命令黑名单" if len(_config.DANGEROUS_PATTERNS) < 10 else "",
    })

    # 9. uvicorn reload（不应在生产开启）
    reload_enabled = os.environ.get("AIOPS_UVICORN_RELOAD", "0") == "1"
    checks.append({
        "key": "uvicorn_reload",
        "label": "uvicorn 热重载",
        "value": "开启" if reload_enabled else "关闭",
        "status": "warn" if (reload_enabled and _config.APP_ENV == "prod") else "pass",
        "advice": "生产环境不应开启 --reload" if reload_enabled and _config.APP_ENV == "prod" else "",
    })

    pass_count = sum(1 for c in checks if c["status"] == "pass")
    warn_count = sum(1 for c in checks if c["status"] == "warn")
    fail_count = sum(1 for c in checks if c["status"] == "fail")
    return {
        "checks": checks,
        "summary": {"pass": pass_count, "warn": warn_count, "fail": fail_count, "total": len(checks)},
    }


def run_full_scan(force: bool = False) -> dict:
    """执行全量安全扫描（带缓存）。force=True 强制刷新。"""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # 缓存判断
    if not force and REPORT_FILE.exists():
        try:
            cached = json.loads(REPORT_FILE.read_text(encoding="utf-8"))
            age = time.time() - cached.get("generated_at_ts", 0)
            if age < CACHE_TTL:
                cached["from_cache"] = True
                cached["cache_age_seconds"] = int(age)
                return cached
        except Exception:
            pass

    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[security_audit] 开始全量安全扫描 @ {generated} (force={force})")

    bandit = run_bandit()
    pip_audit = run_pip_audit()
    licenses = run_license_scan()
    config_check = check_security_config()

    report = {
        "generated_at": generated,
        "generated_at_ts": time.time(),
        "bandit": bandit,
        "dependencies": pip_audit,
        "licenses": licenses,
        "config": config_check,
        "from_cache": False,
    }
    try:
        REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[security_audit] 缓存写入失败: {e}")

    return report


def get_summary() -> dict:
    """轻量摘要（不触发扫描，读缓存）。"""
    if REPORT_FILE.exists():
        try:
            return json.loads(REPORT_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def export_sbom() -> dict:
    """导出 SBOM（软件物料清单）格式。优先读缓存，无缓存才触发扫描。"""
    # 优先读已缓存报告（避免每次导出都重跑 pip-licenses）
    cached = get_summary()
    licenses = cached.get("licenses", {}) if cached else {}
    if not licenses:
        report = run_full_scan(force=False)
        licenses = report.get("licenses", {})
    items = licenses.get("licenses", [])
    return {
        "sbom_version": "1.0",
        "generated_at": cached.get("generated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "components": [
            {
                "name": it.get("name", ""),
                "version": it.get("version", ""),
                "license": it.get("license", ""),
                "supplier": it.get("author", ""),
                "url": it.get("url", ""),
            }
            for it in items
        ],
    }
