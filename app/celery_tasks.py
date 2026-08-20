"""Celery 任务（阶段二）.

把数据源采集 / 资产探活封装为 Celery task，由独立 worker 进程消费。
任务内部创建独立 DB session（线程/进程安全），执行后关闭。
"""
from app.celery_app import celery_app


def _make_session():
    """按当前 DB 模式创建一个独立 session."""
    from app.database import get_session_for, get_db_mode
    return get_session_for(get_db_mode())()


@celery_app.task(name="app.celery_tasks.scrape_all_sources_task", bind=True)
def scrape_all_sources_task(self):
    """数据源采集（beat 周期触发）。"""
    from app.services import datasource_service
    _sess = _make_session()
    try:
        results = datasource_service.scrape_all_sources(_sess)
        ok = sum(1 for r in results if r.get("is_success"))
        total = len(results)
        msg = f"采集完成 {ok}/{total}"
        if total == 0:
            msg = "采集完成 0 个到期源"
        return {"ok": ok == total, "total": total, "success": ok, "message": msg}
    except Exception as e:
        self.retry(exc=e, countdown=10, max_retries=2)
    finally:
        _sess.close()


@celery_app.task(name="app.celery_tasks.probe_assets_task", bind=True)
def probe_assets_task(self):
    """资产健康探活（beat 周期触发）。"""
    from app.services import asset_service
    _sess = _make_session()
    try:
        changed = asset_service.probe_assets(_sess)
        return {"ok": True, "changed": len(changed), "message": f"探活完成，状态变化 {len(changed)} 台"}
    except Exception as e:
        self.retry(exc=e, countdown=10, max_retries=2)
    finally:
        _sess.close()
