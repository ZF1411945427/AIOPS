import os
import json
import subprocess
import tempfile

from fastapi import APIRouter, Depends, Body
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.template_utils import parse_json_config
from app.models import DataSource

router = APIRouter(prefix="/helm", tags=["helm"])


def _helm_bin():
    """优先用项目内 bin/helm.exe，回退到系统 PATH 的 helm"""
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    local = os.path.join(here, "bin", "helm.exe") if os.name == "nt" else os.path.join(here, "bin", "helm")
    if os.path.isfile(local):
        return local
    return "helm"


def _run_helm(cmd, env=None, timeout=120):
    try:
        full_cmd = [_helm_bin()] + cmd[1:]
        p = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout, env=env)
        return {"ok": p.returncode == 0, "stdout": p.stdout, "stderr": p.stderr, "returncode": p.returncode}
    except FileNotFoundError:
        return {"ok": False, "stdout": "", "stderr": "未找到 helm 命令，请确认已安装 Helm CLI 并加入 PATH，或在项目 bin/ 目录放置 helm 可执行文件", "returncode": -1, "helm_missing": True}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "Helm 命令执行超时", "returncode": -1, "timeout": True}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e), "returncode": -1}


def _prepare_kubeconfig(db: Session, cluster: str):
    ds = db.query(DataSource).filter(DataSource.type == "kubernetes", DataSource.name == cluster).first()
    if not ds:
        return None, None, "未找到集群数据源: " + cluster
    cfg = parse_json_config(ds.auth_config)
    kubeconfig = cfg.get("kubeconfig")
    if not kubeconfig and cfg.get("api_server") and cfg.get("token"):
        kubeconfig = _build_kubeconfig_from_token(cfg.get("api_server"), cfg.get("token"), cfg.get("verify_ssl", False))
    if not kubeconfig:
        return None, None, "该集群数据源未配置 kubeconfig"
    if isinstance(kubeconfig, dict):
        kubeconfig = json.dumps(kubeconfig, ensure_ascii=False)
    try:
        f = tempfile.NamedTemporaryFile(suffix=".kubeconfig", delete=False, mode="w", encoding="utf-8")
        f.write(kubeconfig)
        f.close()
    except Exception as e:
        return None, None, "写入 kubeconfig 临时文件失败: " + str(e)
    env = dict(os.environ)
    env["KUBECONFIG"] = f.name
    return env, f.name, None


def _build_kubeconfig_from_token(api_server, token, verify_ssl=False):
    import yaml
    cluster_name = "aiops-cluster"
    cfg = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [{
            "name": cluster_name,
            "cluster": {
                "server": api_server,
                "insecure-skip-tls-verify": not verify_ssl,
            },
        }],
        "contexts": [{
            "name": cluster_name,
            "context": {"cluster": cluster_name, "user": "aiops-user"},
        }],
        "current-context": cluster_name,
        "users": [{
            "name": "aiops-user",
            "user": {"token": token},
        }],
    }
    return yaml.safe_dump(cfg, default_flow_style=False)


def _cleanup(*paths):
    for p in paths:
        if not p:
            continue
        try:
            os.unlink(p)
        except Exception:
            pass


@router.get("/api/status")
def helm_status():
    r = _run_helm(["helm", "version", "--short"])
    if r.get("helm_missing"):
        return JSONResponse({"installed": False, "version": None, "error": r["stderr"]})
    if not r["ok"]:
        return JSONResponse({"installed": False, "version": None, "error": (r["stderr"] or "helm version 执行失败").strip()})
    return JSONResponse({"installed": True, "version": r["stdout"].strip()})


@router.get("/api/repos")
def helm_repos():
    r = _run_helm(["helm", "repo", "list", "-o", "json"])
    if r.get("helm_missing"):
        return JSONResponse({"repos": [], "error": r["stderr"]})
    if not r["ok"]:
        msg = (r["stderr"] or "").strip()
        if "no repositories" in msg.lower() or "no repos" in msg.lower():
            return JSONResponse({"repos": []})
        return JSONResponse({"repos": [], "error": msg or "未配置仓库"})
    try:
        repos = json.loads(r["stdout"])
    except Exception:
        repos = []
    return JSONResponse({"repos": repos})


@router.post("/api/repos/add")
def helm_repo_add(body: dict = Body(...)):
    name = (body.get("name") or "").strip()
    url = (body.get("url") or "").strip()
    if not name or not url:
        return JSONResponse({"ok": False, "error": "name 和 url 必填"}, status_code=400)
    r = _run_helm(["helm", "repo", "add", name, url])
    if r.get("helm_missing"):
        return JSONResponse({"ok": False, "error": r["stderr"]})
    if not r["ok"]:
        return JSONResponse({"ok": False, "error": (r["stderr"] or "添加仓库失败").strip()})
    return JSONResponse({"ok": True, "message": "仓库已添加: " + name, "stdout": r["stdout"]})


@router.post("/api/repos/remove")
def helm_repo_remove(body: dict = Body(...)):
    name = (body.get("name") or "").strip()
    if not name:
        return JSONResponse({"ok": False, "error": "name 必填"}, status_code=400)
    r = _run_helm(["helm", "repo", "remove", name])
    if r.get("helm_missing"):
        return JSONResponse({"ok": False, "error": r["stderr"]})
    if not r["ok"]:
        return JSONResponse({"ok": False, "error": (r["stderr"] or "删除仓库失败").strip()})
    return JSONResponse({"ok": True, "message": "仓库已删除: " + name})


@router.post("/api/repos/update")
def helm_repo_update():
    r = _run_helm(["helm", "repo", "update"], timeout=180)
    if r.get("helm_missing"):
        return JSONResponse({"ok": False, "error": r["stderr"]})
    if not r["ok"]:
        return JSONResponse({"ok": False, "error": (r["stderr"] or "更新仓库失败").strip()})
    return JSONResponse({"ok": True, "message": "仓库索引已更新", "stdout": r["stdout"]})


@router.get("/api/releases")
def helm_releases(cluster: str = "", db: Session = Depends(get_db)):
    if not cluster:
        return JSONResponse({"releases": [], "error": "请提供 cluster 参数"})
    env, tmpf, err = _prepare_kubeconfig(db, cluster)
    if err:
        return JSONResponse({"releases": [], "error": err})
    try:
        r = _run_helm(["helm", "list", "-A", "-o", "json"], env=env)
        if r.get("helm_missing"):
            return JSONResponse({"releases": [], "error": r["stderr"]})
        if not r["ok"]:
            return JSONResponse({"releases": [], "error": (r["stderr"] or "获取 release 列表失败").strip()})
        try:
            releases = json.loads(r["stdout"])
        except Exception:
            releases = []
        return JSONResponse({"releases": releases})
    finally:
        _cleanup(tmpf)


@router.get("/api/charts")
def helm_charts(repo_keyword: str = ""):
    if not repo_keyword:
        return JSONResponse({"charts": []})
    r = _run_helm(["helm", "search", "repo", repo_keyword, "-o", "json"], timeout=60)
    if r.get("helm_missing"):
        return JSONResponse({"charts": [], "error": r["stderr"]})
    if not r["ok"]:
        return JSONResponse({"charts": [], "error": (r["stderr"] or "搜索 chart 失败").strip()})
    try:
        charts = json.loads(r["stdout"])
    except Exception:
        charts = []
    return JSONResponse({"charts": charts})


@router.post("/api/install")
def helm_install(body: dict = Body(...), db: Session = Depends(get_db)):
    cluster = body.get("cluster", "")
    name = (body.get("name") or "").strip()
    chart = (body.get("chart") or "").strip()
    namespace = (body.get("namespace") or "default").strip() or "default"
    version = (body.get("version") or "").strip()
    values = body.get("values") or ""
    if not cluster or not name or not chart:
        return JSONResponse({"ok": False, "error": "cluster/name/chart 必填"}, status_code=400)
    env, tmpf, err = _prepare_kubeconfig(db, cluster)
    if err:
        return JSONResponse({"ok": False, "error": err}, status_code=400)
    values_file = None
    try:
        cmd = ["helm", "install", name, chart, "--namespace", namespace, "--create-namespace"]
        if version:
            cmd += ["--version", version]
        if values and values.strip():
            vf = tempfile.NamedTemporaryFile(suffix=".values.yaml", delete=False, mode="w", encoding="utf-8")
            vf.write(values)
            vf.close()
            values_file = vf.name
            cmd += ["-f", values_file]
        r = _run_helm(cmd, env=env, timeout=300)
        if r.get("helm_missing"):
            return JSONResponse({"ok": False, "error": r["stderr"]})
        if not r["ok"]:
            return JSONResponse({"ok": False, "error": (r["stderr"] or "安装失败").strip(), "stdout": r["stdout"]})
        return JSONResponse({"ok": True, "message": "Release 已安装: " + name, "stdout": r["stdout"]})
    finally:
        _cleanup(tmpf, values_file)


@router.post("/api/upgrade")
def helm_upgrade(body: dict = Body(...), db: Session = Depends(get_db)):
    cluster = body.get("cluster", "")
    name = (body.get("name") or "").strip()
    chart = (body.get("chart") or "").strip()
    namespace = (body.get("namespace") or "default").strip() or "default"
    version = (body.get("version") or "").strip()
    values = body.get("values") or ""
    if not cluster or not name or not chart:
        return JSONResponse({"ok": False, "error": "cluster/name/chart 必填"}, status_code=400)
    env, tmpf, err = _prepare_kubeconfig(db, cluster)
    if err:
        return JSONResponse({"ok": False, "error": err}, status_code=400)
    values_file = None
    try:
        cmd = ["helm", "upgrade", name, chart, "--namespace", namespace, "--create-namespace"]
        if version:
            cmd += ["--version", version]
        if values and values.strip():
            vf = tempfile.NamedTemporaryFile(suffix=".values.yaml", delete=False, mode="w", encoding="utf-8")
            vf.write(values)
            vf.close()
            values_file = vf.name
            cmd += ["-f", values_file]
        r = _run_helm(cmd, env=env, timeout=300)
        if r.get("helm_missing"):
            return JSONResponse({"ok": False, "error": r["stderr"]})
        if not r["ok"]:
            return JSONResponse({"ok": False, "error": (r["stderr"] or "升级失败").strip(), "stdout": r["stdout"]})
        return JSONResponse({"ok": True, "message": "Release 已升级: " + name, "stdout": r["stdout"]})
    finally:
        _cleanup(tmpf, values_file)


@router.post("/api/uninstall")
def helm_uninstall(body: dict = Body(...), db: Session = Depends(get_db)):
    cluster = body.get("cluster", "")
    name = (body.get("name") or "").strip()
    namespace = (body.get("namespace") or "default").strip() or "default"
    if not cluster or not name:
        return JSONResponse({"ok": False, "error": "cluster/name 必填"}, status_code=400)
    env, tmpf, err = _prepare_kubeconfig(db, cluster)
    if err:
        return JSONResponse({"ok": False, "error": err}, status_code=400)
    try:
        r = _run_helm(["helm", "uninstall", name, "-n", namespace], env=env)
        if r.get("helm_missing"):
            return JSONResponse({"ok": False, "error": r["stderr"]})
        if not r["ok"]:
            return JSONResponse({"ok": False, "error": (r["stderr"] or "卸载失败").strip()})
        return JSONResponse({"ok": True, "message": "Release 已卸载: " + name, "stdout": r["stdout"]})
    finally:
        _cleanup(tmpf)


@router.post("/api/rollback")
def helm_rollback(body: dict = Body(...), db: Session = Depends(get_db)):
    cluster = body.get("cluster", "")
    name = (body.get("name") or "").strip()
    namespace = (body.get("namespace") or "default").strip() or "default"
    revision = body.get("revision")
    if not cluster or not name or revision is None:
        return JSONResponse({"ok": False, "error": "cluster/name/revision 必填"}, status_code=400)
    env, tmpf, err = _prepare_kubeconfig(db, cluster)
    if err:
        return JSONResponse({"ok": False, "error": err}, status_code=400)
    try:
        r = _run_helm(["helm", "rollback", name, str(revision), "-n", namespace], env=env, timeout=180)
        if r.get("helm_missing"):
            return JSONResponse({"ok": False, "error": r["stderr"]})
        if not r["ok"]:
            return JSONResponse({"ok": False, "error": (r["stderr"] or "回滚失败").strip()})
        return JSONResponse({"ok": True, "message": f"已回滚 {name} 至 revision {revision}", "stdout": r["stdout"]})
    finally:
        _cleanup(tmpf)


@router.get("/api/history")
def helm_history(cluster: str = "", name: str = "", namespace: str = "default", db: Session = Depends(get_db)):
    if not cluster or not name:
        return JSONResponse({"history": [], "error": "cluster/name 必填"})
    env, tmpf, err = _prepare_kubeconfig(db, cluster)
    if err:
        return JSONResponse({"history": [], "error": err})
    try:
        r = _run_helm(["helm", "history", name, "-n", namespace, "-o", "json"], env=env)
        if r.get("helm_missing"):
            return JSONResponse({"history": [], "error": r["stderr"]})
        if not r["ok"]:
            return JSONResponse({"history": [], "error": (r["stderr"] or "获取历史失败").strip()})
        try:
            history = json.loads(r["stdout"])
        except Exception:
            history = []
        return JSONResponse({"history": history})
    finally:
        _cleanup(tmpf)


@router.get("/api/status/{cluster}/{namespace}/{name}")
def helm_status_detail(cluster: str, namespace: str, name: str, db: Session = Depends(get_db)):
    env, tmpf, err = _prepare_kubeconfig(db, cluster)
    if err:
        return JSONResponse({"status": None, "error": err})
    try:
        r = _run_helm(["helm", "status", name, "-n", namespace, "-o", "json"], env=env)
        if r.get("helm_missing"):
            return JSONResponse({"status": None, "error": r["stderr"]})
        if not r["ok"]:
            return JSONResponse({"status": None, "error": (r["stderr"] or "获取状态失败").strip()})
        try:
            status = json.loads(r["stdout"])
        except Exception:
            status = r["stdout"]
        return JSONResponse({"status": status})
    finally:
        _cleanup(tmpf)
