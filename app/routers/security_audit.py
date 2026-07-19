"""安全自查路由：暴露 SAST / 依赖 CVE / License 合规 / 配置基线 / SBOM 接口。

仅 admin 角色可访问（写操作需要管理员权限）。扫描结果缓存到 security_reports/。
"""
from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse

from app.security import require_admin
from app.services import security_audit_service

router = APIRouter(prefix="/api/security-audit", tags=["security-audit"])


@router.get("/summary")
def get_summary():
    """读取缓存的安全自查摘要（不触发扫描）。"""
    data = security_audit_service.get_summary()
    if not data:
        return {
            "available": False,
            "message": "尚未生成报告，请先调用 /api/security-audit/scan",
        }
    return data


@router.post("/scan")
def run_scan(request: Request, force: bool = Query(False)):
    """触发全量安全扫描（bandit + pip-audit + pip-licenses + 配置检查）。

    - force=true 强制刷新缓存
    - 首次扫描约 1-3 分钟（pip-audit 联网查 CVE 较慢）
    """
    require_admin(request)
    try:
        report = security_audit_service.run_full_scan(force=force)
        return report
    except Exception as e:
        from app.logger import logger
        logger.error(f"安全自查扫描失败: {e}")
        return JSONResponse(
            {"error": f"扫描失败: {e}", "warning": "请检查 bandit / pip-audit / pip-licenses 是否已安装"},
            status_code=200,
        )


@router.get("/report")
def get_report():
    """获取最近一次扫描报告（读缓存，不触发扫描）。"""
    data = security_audit_service.get_summary()
    if not data:
        return {"available": False, "message": "尚未生成报告"}
    return data


@router.get("/sbom")
def get_sbom():
    """导出 SBOM（软件物料清单）。"""
    try:
        return security_audit_service.export_sbom()
    except Exception as e:
        return JSONResponse({"error": f"SBOM 导出失败: {e}"}, status_code=200)


@router.get("/config-check")
def config_check():
    """仅执行配置基线检查（秒级返回，不依赖外部工具）。"""
    try:
        return security_audit_service.check_security_config()
    except Exception as e:
        return JSONResponse({"error": f"配置检查失败: {e}"}, status_code=200)
