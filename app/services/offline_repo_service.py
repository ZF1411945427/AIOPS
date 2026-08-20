"""离线部署服务 - 对标 Pixiu builder serve。

核心能力:
1. 上传/保存离线包(.tar.gz)到 <PROJECT_ROOT>/storage/offline/
2. load_bundle: 解压 → 扫描 images/ 与 packages/ → docker load/tag/push 到私有 Registry → 生成 deb/rpm 包源索引 + 本地 HTTP 静态服务
3. Registry 管理: 通过 Registry HTTP API v2 列镜像 / 测试连接
4. 健康检查: 所有 Registry 与包源可用性
5. 部署计划离线配置: 供 deploy_plans 对接私有 Registry + 包源地址

契约见 CONTRACT.md 第十二章。存储路径必须基于 __file__ 动态计算。
"""
import hashlib
import json
import os
import shutil
import socket
import subprocess
import tarfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from sqlalchemy.orm import Session

from app.models import OfflineRepoBundle, OfflineRegistry, OfflinePackageSource
from app.logger import logger

# 存储根目录: <项目根>/storage/offline（禁止硬编码绝对路径）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = Path(os.environ.get("AIOPS_OFFLINE_DIR", str(_PROJECT_ROOT / "storage" / "offline")))
BUNDLE_DIR = STORAGE_DIR / "bundles"
SOURCE_DIR = STORAGE_DIR / "sources"
SOURCE_PORT = int(os.environ.get("AIOPS_OFFLINE_SOURCE_PORT", "18080"))
BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
SOURCE_DIR.mkdir(parents=True, exist_ok=True)

# 包源 HTTP 静态服务（线程常驻）
_source_server: Optional[ThreadingHTTPServer] = None
_source_server_lock = threading.Lock()
_source_server_thread: Optional[threading.Thread] = None

# 允许的镜像 tar 相关扩展
_BUNDLE_EXT = {".tar.gz", ".tgz"}
_LOAD_TIMEOUT = int(os.environ.get("AIOPS_OFFLINE_LOAD_TIMEOUT", "1800"))


# ─────────────────────────────── 工具函数 ───────────────────────────────

def _now() -> datetime:
    return datetime.now()


def _compute_md5(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _run_cmd(cmd: List[str], timeout: int = _LOAD_TIMEOUT) -> dict:
    """执行本地命令并返回 {ok, stdout, stderr, returncode}。"""
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        return {
            "ok": p.returncode == 0,
            "stdout": p.stdout,
            "stderr": p.stderr,
            "returncode": p.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": f"命令超时(>{timeout}s)", "returncode": -1}
    except FileNotFoundError as e:
        return {"ok": False, "stdout": "", "stderr": f"命令不存在: {e}", "returncode": -2}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e), "returncode": -3}


def _bundle_to_dict(b: OfflineRepoBundle) -> dict:
    return {
        "id": b.id,
        "name": b.name,
        "description": b.description or "",
        "version": b.version or "",
        "os_type": b.os_type or "",
        "os_version": b.os_version or "",
        "bundle_type": b.bundle_type or "images",
        "file_size": b.file_size or 0,
        "file_size_display": _human_size(b.file_size or 0),
        "md5": b.md5 or "",
        "status": b.status or "pending",
        "loaded_images": b.loaded_images or 0,
        "total_images": b.total_images or 0,
        "loaded_packages": b.loaded_packages or 0,
        "load_message": b.load_message or "",
        "loaded_at": b.loaded_at.strftime("%Y-%m-%d %H:%M:%S") if b.loaded_at else None,
        "created_at": b.created_at.strftime("%Y-%m-%d %H:%M:%S") if b.created_at else None,
        "updated_at": b.updated_at.strftime("%Y-%m-%d %H:%M:%S") if b.updated_at else None,
    }


def _registry_to_dict(r: OfflineRegistry, include_password: bool = False) -> dict:
    d = {
        "id": r.id,
        "name": r.name,
        "registry_url": r.registry_url,
        "is_internal": bool(r.is_internal),
        "is_secure": bool(r.is_secure),
        "username": r.username or "",
        "has_password": bool(r.has_password),
        "is_default": bool(r.is_default),
        "status": r.status or "active",
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
        "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M:%S") if r.updated_at else None,
    }
    if include_password:
        d["password"] = "***"
    return d


def _source_to_dict(s: OfflinePackageSource) -> dict:
    return {
        "id": s.id,
        "bundle_id": s.bundle_id,
        "os_type": s.os_type or "",
        "os_version": s.os_version or "",
        "source_url": s.source_url or "",
        "source_type": s.source_type or "deb",
        "package_count": s.package_count or 0,
        "is_active": bool(s.is_active),
        "created_at": s.created_at.strftime("%Y-%m-%d %H:%M:%S") if s.created_at else None,
    }


def _human_size(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


# ─────────────────────────────── 离线包管理 ───────────────────────────────

def save_bundle(db: Session, file, name: str, bundle_type: str = "images",
                os_type: str = "", os_version: str = "", version: str = "",
                description: str = "", md5: str = "") -> dict:
    """保存上传的离线包文件到存储目录，返回 bundle 记录。"""
    filename = file.filename or "bundle.tar.gz"
    low = filename.lower()
    if low.endswith(".tgz"):
        file_ext = ".tgz"
    elif low.endswith(".tar.gz"):
        file_ext = ".tar.gz"
    else:
        ext = Path(filename).suffix.lower() or "未知"
        raise ValueError(f"仅支持 .tar.gz / .tgz 离线包，当前: {ext}")
    safe_name = name.strip() or Path(filename).stem
    # 同一名称允许覆盖新版本：文件名加时间戳避免冲突
    store_name = f"{safe_name.replace(os.sep, '_').replace('/', '_')}_{int(time.time())}{file_ext}"
    dest = BUNDLE_DIR / store_name
    file_size = 0
    tmp = dest.with_suffix(dest.suffix + ".uploading")
    with open(tmp, "wb") as f:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            file_size += len(chunk)
    # 计算 MD5（若用户未提供则计算，若提供则校验）
    real_md5 = _compute_md5(tmp)
    if md5 and md5.strip() and md5.strip().lower() != real_md5.lower():
        tmp.unlink(missing_ok=True)
        raise ValueError(f"MD5 校验失败: 期望 {md5.strip()}，实际 {real_md5}")
    os.replace(tmp, dest)
    bundle = OfflineRepoBundle(
        name=safe_name,
        description=description,
        version=version,
        os_type=os_type,
        os_version=os_version,
        bundle_type=bundle_type,
        file_path=str(dest),
        file_size=file_size,
        md5=real_md5,
        status="pending",
    )
    db.add(bundle)
    db.commit()
    db.refresh(bundle)
    logger.info(f"离线包已保存: {bundle.name} -> {dest} ({file_size}B)")
    return _bundle_to_dict(bundle)


def list_bundles(db: Session, search: str = "", status: str = "", page: int = 1, per_page: int = 20) -> dict:
    q = db.query(OfflineRepoBundle)
    if search:
        q = q.filter(OfflineRepoBundle.name.contains(search))
    if status:
        q = q.filter(OfflineRepoBundle.status == status)
    total = q.count()
    items = q.order_by(OfflineRepoBundle.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return {"items": [_bundle_to_dict(b) for b in items], "total": total, "page": page, "per_page": per_page}


def get_bundle(db: Session, bundle_id: int) -> Optional[dict]:
    b = db.query(OfflineRepoBundle).filter(OfflineRepoBundle.id == bundle_id).first()
    if not b:
        return None
    d = _bundle_to_dict(b)
    d["sources"] = [_source_to_dict(s) for s in db.query(OfflinePackageSource)
                    .filter(OfflinePackageSource.bundle_id == bundle_id).all()]
    return d


def delete_bundle(db: Session, bundle_id: int) -> bool:
    b = db.query(OfflineRepoBundle).filter(OfflineRepoBundle.id == bundle_id).first()
    if not b:
        return False
    if b.file_path and os.path.exists(b.file_path):
        try:
            os.remove(b.file_path)
        except Exception as e:
            logger.warning(f"删除离线包文件失败: {e}")
    db.query(OfflinePackageSource).filter(OfflinePackageSource.bundle_id == bundle_id).delete()
    db.delete(b)
    db.commit()
    return True


def _extract_manifest(bundle: OfflineRepoBundle, extract_dir: Path) -> dict:
    """扫描解压后的 images/ 与 packages/ 目录，返回 {images: [names], package_count, os_type}。"""
    result = {"images": [], "package_count": 0}
    images_dir = extract_dir / "images"
    packages_dir = extract_dir / "packages"
    if images_dir.exists() and images_dir.is_dir():
        for f in sorted(images_dir.iterdir()):
            if f.is_file() and f.name.endswith((".tar", ".tar.gz", ".tgz")):
                result["images"].append(f.name)
    if packages_dir.exists() and packages_dir.is_dir():
        result["package_count"] = len([f for f in packages_dir.iterdir() if f.is_file()])
    return result


def _load_image_tar(db: Session, bundle: OfflineRepoBundle, image_file: Path,
                    registry: Optional[OfflineRegistry], loaded: Dict[str, Any]) -> None:
    """加载单个镜像 tar：docker load → tag → push（推送失败不致命，镜像仍入本地 Docker）。"""
    r = _run_cmd(["docker", "load", "-i", str(image_file)])
    if not r["ok"]:
        loaded["errors"].append(f"{image_file.name}: docker load 失败 -> {r['stderr'][:200]}")
        return
    # 解析 load 输出中的镜像名(可多行)
    repotags: List[str] = []
    for line in r["stdout"].splitlines():
        line = line.strip()
        if "Loaded image" in line or "Loaded image ID" in line:
            tag = line.split(":", 1)[1].strip() if ":" in line else ""
            if tag and tag not in repotags:
                repotags.append(tag)
    if not repotags:
        loaded["loaded_images"] += 1
        return
    if not registry:
        loaded["loaded_images"] += len(repotags)
        return
    # 推送到私有 Registry: 重命名 <registry_url>/<name>:<tag>
    for tag in repotags:
        if "/" in tag:
            repo, t = tag.rsplit(":", 1) if ":" in tag else (tag, "latest")
            target = f"{registry.registry_url}/{repo}:{t}"
        else:
            target = f"{registry.registry_url}/{tag}"
        r2 = _run_cmd(["docker", "tag", tag, target])
        if not r2["ok"]:
            loaded["errors"].append(f"{tag}: docker tag 失败 -> {r2['stderr'][:200]}")
            continue
        r3 = _run_cmd(["docker", "push", target])
        if not r3["ok"]:
            loaded["errors"].append(f"{target}: docker push 失败 -> {r3['stderr'][:200]}")
            continue
        loaded["loaded_images"] += 1


def _serve_source_dir() -> ThreadingHTTPServer:
    """启动(或复用)包源 HTTP 静态服务线程。"""
    global _source_server, _source_server_thread
    with _source_server_lock:
        if _source_server is not None:
            return _source_server
        handler = SimpleHTTPRequestHandler
        os.chdir(str(SOURCE_DIR))

        class _SourceHandler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("0.0.0.0", SOURCE_PORT), _SourceHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True, name="offline-source-http")
        thread.start()
        _source_server = server
        _source_server_thread = thread
        logger.info(f"离线包源 HTTP 服务已启动: http://0.0.0.0:{SOURCE_PORT}/ (根目录 {SOURCE_DIR})")
        return server


def _build_package_indexes(extract_dir: Path, bundle: OfflineRepoBundle,
                           source_http_base: str) -> List[OfflinePackageSource]:
    """为 packages/ 目录生成 deb/rpm 索引，并复制到 SOURCE_DIR 供 HTTP 服务。返回包源记录。"""
    packages_dir = extract_dir / "packages"
    if not packages_dir.exists() or not packages_dir.is_dir():
        return []
    # 检测类型：递归扫描 packages 下所有 .deb/.rpm（支持扁平与 deb/rpm 分层两种结构）
    all_files = list(packages_dir.rglob("*"))
    has_deb = any(f.is_file() and f.suffix == ".deb" for f in all_files)
    has_rpm = any(f.is_file() and f.suffix == ".rpm" for f in all_files)
    sources: List[OfflinePackageSource] = []
    for stype, present in (("deb", has_deb), ("rpm", has_rpm)):
        if not present:
            continue
        sub_dir = packages_dir / stype
        if not sub_dir.exists() or not sub_dir.is_dir():
            sub_dir = packages_dir  # 未分层时用根目录
        target_dir = SOURCE_DIR / f"bundle_{bundle.id}_{stype}"
        shutil.rmtree(target_dir, ignore_errors=True)
        shutil.copytree(sub_dir, target_dir)
        # 递归统计包数量
        count = sum(1 for f in target_dir.rglob("*") if f.is_file() and f.suffix in (".deb", ".rpm"))
        # 生成索引
        if stype == "deb":
            _run_cmd(["dpkg-scanpackages", str(target_dir), "/dev/null"], timeout=120)
            index = target_dir / "Packages"
            if index.exists():
                _run_cmd(["gzip", "-9f", str(index)], timeout=120)
        else:
            _run_cmd(["createrepo", str(target_dir)], timeout=300)
        source_url = f"{source_http_base}/bundle_{bundle.id}_{stype}"
        src = OfflinePackageSource(
            bundle_id=bundle.id,
            os_type=bundle.os_type or "generic",
            os_version=bundle.os_version or "",
            source_url=source_url,
            source_type=stype,
            package_count=count,
            is_active=True,
        )
        sources.append(src)
    return sources


def load_bundle(db: Session, bundle_id: int, registry_id: Optional[int] = None,
                auto_start_source: bool = True) -> dict:
    """加载离线包：
    1. 解压 tar.gz 到临时目录
    2. 扫描 images/ 与 packages/
    3. 镜像逐个 docker load → tag → push 到指定(或默认) Registry
    4. 生成 deb/rpm 包源索引 + 启动本地 HTTP 静态服务
    5. 更新 bundle 状态为 loaded/failed
    """
    b = db.query(OfflineRepoBundle).filter(OfflineRepoBundle.id == bundle_id).first()
    if not b:
        raise ValueError("离线包不存在")
    if b.status == "loading":
        raise ValueError("该离线包正在加载中")
    if not b.file_path or not os.path.exists(b.file_path):
        raise ValueError("离线包文件不存在，请重新上传")
    registry = None
    if registry_id:
        registry = db.query(OfflineRegistry).filter(OfflineRegistry.id == registry_id).first()
    if not registry:
        registry = db.query(OfflineRegistry).filter(OfflineRegistry.is_default == True).first()  # noqa: E712

    b.status = "loading"
    b.load_message = "开始解压离线包..."
    b.loaded_images = 0
    b.loaded_packages = 0
    db.commit()

    extract_dir = BUNDLE_DIR / f"extract_{bundle_id}"
    shutil.rmtree(extract_dir, ignore_errors=True)
    extract_dir.mkdir(parents=True, exist_ok=True)
    loaded = {"loaded_images": 0, "loaded_packages": 0, "errors": []}
    try:
        # 解压
        with tarfile.open(b.file_path, "r:gz") as tf:
            tf.extractall(extract_dir)
        b.load_message = "解压完成，扫描镜像与包..."
        db.commit()

        manifest = _extract_manifest(b, extract_dir)
        total_images = len(manifest["images"])
        b.total_images = total_images
        b.load_message = f"扫描到 {total_images} 个镜像文件、{manifest['package_count']} 个软件包"
        db.commit()

        # 镜像加载（并发，限制 2 并发避免 Docker 争抢）
        if manifest["images"]:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(_load_image_tar, db, b, extract_dir / "images" / name, registry, loaded)
                           for name in manifest["images"]]
                for f in futures:
                    f.result()
            b.loaded_images = loaded["loaded_images"]
            b.load_message = f"镜像加载 {b.loaded_images}/{total_images}，处理包源..."
            db.commit()

        # 包源索引
        http_base = f"http://{_local_ip()}:{SOURCE_PORT}"
        if auto_start_source:
            _serve_source_dir()
        new_sources = _build_package_indexes(extract_dir, b, http_base)
        if new_sources:
            db.add_all(new_sources)
            b.loaded_packages = sum(s.package_count for s in new_sources)
        db.commit()

        # 完成
        b.status = "loaded"
        b.loaded_at = _now()
        b.load_message = "加载完成"
        if loaded["errors"]:
            b.load_message = f"加载完成(部分失败 {len(loaded['errors'])} 项)"
        db.commit()
        logger.info(f"离线包加载完成: {b.name} images={b.loaded_images}/{b.total_images} pkgs={b.loaded_packages}")
        result = _bundle_to_dict(b)
        result["warnings"] = loaded["errors"][:20]
        result["sources"] = [_source_to_dict(s) for s in db.query(OfflinePackageSource)
                             .filter(OfflinePackageSource.bundle_id == bundle_id).all()]
        return result
    except Exception as e:
        b.status = "failed"
        b.load_message = f"加载失败: {e}"
        db.commit()
        logger.exception(f"离线包加载失败: {b.name}: {e}")
        return _bundle_to_dict(b)
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)


def list_bundle_images(db: Session, bundle_id: int) -> dict:
    """列出离线包内镜像文件清单（未加载时扫描 tar，已加载返回记录）。"""
    b = db.query(OfflineRepoBundle).filter(OfflineRepoBundle.id == bundle_id).first()
    if not b:
        raise ValueError("离线包不存在")
    extract_dir = BUNDLE_DIR / f"extract_{bundle_id}"
    if b.file_path and b.status != "loading" and extract_dir.exists():
        manifest = _extract_manifest(b, extract_dir)
        return {"images": [{"name": n} for n in manifest["images"]],
                "loaded": b.loaded_images, "total": b.total_images}
    # 未解压：直接读 tar 内部索引（快速）
    names = []
    try:
        with tarfile.open(b.file_path, "r:gz") as tf:
            for m in tf.getmembers():
                if m.name.startswith("images/") and m.isfile():
                    names.append(m.name.split("images/", 1)[1])
    except Exception as _exc:
        logger.warning("[except:pass] Exception: %s", _exc, exc_info=True)
    return {"images": [{"name": n} for n in names], "loaded": b.loaded_images, "total": b.total_images}


def list_bundle_packages(db: Session, bundle_id: int) -> dict:
    sources = db.query(OfflinePackageSource).filter(OfflinePackageSource.bundle_id == bundle_id).all()
    items = []
    for s in sources:
        base_dir = SOURCE_DIR / f"bundle_{bundle_id}_{s.source_type}"
        names = []
        if base_dir.exists():
            names = [f.name for f in sorted(base_dir.iterdir())[:200]]
        items.append({**_source_to_dict(s), "packages": names})
    return {"sources": items}


def _local_ip() -> str:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


# ─────────────────────────────── Registry 管理 ───────────────────────────────

def create_registry(db: Session, payload: dict) -> OfflineRegistry:
    password = payload.get("password") or ""
    r = OfflineRegistry(
        name=payload.get("name", "").strip(),
        registry_url=payload.get("registry_url", "").strip(),
        is_internal=bool(payload.get("is_internal")),
        storage_path=payload.get("storage_path", "").strip(),
        is_secure=bool(payload.get("is_secure")),
        username=payload.get("username", "").strip(),
        password=password,
        has_password=bool(password),
        is_default=bool(payload.get("is_default")),
        status="active",
    )
    if not r.name or not r.registry_url:
        raise ValueError("仓库名称与地址必填")
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def update_registry(db: Session, registry_id: int, payload: dict) -> Optional[OfflineRegistry]:
    r = db.query(OfflineRegistry).filter(OfflineRegistry.id == registry_id).first()
    if not r:
        return None
    if "name" in payload:
        r.name = payload["name"].strip() or r.name
    if "registry_url" in payload:
        r.registry_url = payload["registry_url"].strip() or r.registry_url
    if "is_internal" in payload:
        r.is_internal = bool(payload["is_internal"])
    if "storage_path" in payload and payload["storage_path"]:
        r.storage_path = payload["storage_path"].strip()
    if "is_secure" in payload:
        r.is_secure = bool(payload["is_secure"])
    if "username" in payload:
        r.username = payload["username"].strip() or ""
    # 敏感字段: 空值=不更新
    if "password" in payload and payload["password"]:
        r.password = payload["password"]
        r.has_password = True
    if "is_default" in payload:
        r.is_default = bool(payload["is_default"])
        if r.is_default:
            db.query(OfflineRegistry).filter(OfflineRegistry.is_default == True,  # noqa: E712
                                             OfflineRegistry.id != registry_id).update({"is_default": False})
    if "status" in payload:
        r.status = payload["status"]
    db.commit()
    db.refresh(r)
    return r


def delete_registry(db: Session, registry_id: int) -> bool:
    r = db.query(OfflineRegistry).filter(OfflineRegistry.id == registry_id).first()
    if not r:
        return False
    db.delete(r)
    db.commit()
    return True


def list_registries(db: Session) -> list:
    regs = db.query(OfflineRegistry).order_by(OfflineRegistry.id.desc()).all()
    return [_registry_to_dict(r) for r in regs]


def _registry_headers(r: OfflineRegistry) -> Dict[str, str]:
    headers = {"Accept": "application/vnd.docker.distribution.api.v2+json"}
    if r.username:
        import base64
        token = base64.b64encode(f"{r.username}:{r.password}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    return headers


def _local_host_ips() -> set:
    """返回本机所有网卡 IP, 用于判断 registry_url 是否指向宿主机自身。"""
    ips = {"127.0.0.1", "localhost", "::1"}
    try:
        _, _, addrs = socket.gethostbyname_ex(socket.gethostname())
        ips.update(a for a in addrs if a)
    except Exception:
        pass
    return ips


def _registry_probe_base(r: OfflineRegistry) -> str:
    """构造用于本机探测的 base URL。

    仓库地址若指向宿主机自身网卡(Vmnet8 NAT 等 11.0.1.1), 后端在本机用该地址
    访问会因回环路由问题超时。探测端统一回退到 127.0.0.1(同一仓库), 只影响测试/
    健康检查/列镜像, 不改变 部署 时虚机上使用的 registry_url。
    """
    scheme = "https" if r.is_secure else "http"
    host = r.registry_url
    port = ""
    if "://" in host:  # 防御: 万一存了完整 url
        host = host.split("://", 1)[1]
    if ":" in host:
        host, _, port = host.rpartition(":")
    host = host.strip("/")
    if host in _local_host_ips():
        host = "127.0.0.1"
    return f"{scheme}://{host}" + (f":{port}" if port else "")


def test_registry(r: OfflineRegistry) -> dict:
    """通过 Registry HTTP API v2 测试连接与认证。"""
    base = _registry_probe_base(r)
    url = f"{base}/v2/"
    try:
        req = Request(url, headers=_registry_headers(r))
        resp = urlopen(req, timeout=10)
        if resp.status == 200:
            return {"ok": True, "message": "连接成功", "status_code": resp.status}
        return {"ok": False, "message": f"Registry 返回 {resp.status}", "status_code": resp.status}
    except HTTPError as e:
        if e.code == 401:
            return {"ok": False, "message": "认证失败(401)，请检查用户名/密码", "status_code": 401}
        return {"ok": False, "message": f"连接失败: HTTP {e.code}", "status_code": e.code}
    except URLError as e:
        return {"ok": False, "message": f"连接失败: {e.reason}", "status_code": 0}
    except Exception as e:
        return {"ok": False, "message": f"连接异常: {e}", "status_code": 0}


def list_registry_images(r: OfflineRegistry, max_items: int = 200) -> dict:
    """通过 Registry Catalog API 列出镜像列表。"""
    base = _registry_probe_base(r)
    try:
        req = Request(f"{base}/v2/_catalog?n={max_items}", headers=_registry_headers(r))
        resp = urlopen(req, timeout=15)
        data = json.loads(resp.read().decode("utf-8"))
        repos = data.get("repositories", [])
        images = [{"name": repo} for repo in repos]
        return {"ok": True, "images": images, "count": len(images)}
    except HTTPError as e:
        return {"ok": False, "message": f"列出镜像失败: HTTP {e.code}", "images": []}
    except URLError as e:
        return {"ok": False, "message": f"列出镜像失败: {e.reason}", "images": []}
    except Exception as e:
        return {"ok": False, "message": f"列出镜像异常: {e}", "images": []}


# ─────────────────────────────── 包源 / 健康检查 ───────────────────────────────

def list_sources(db: Session, bundle_id: Optional[int] = None) -> dict:
    q = db.query(OfflinePackageSource)
    if bundle_id:
        q = q.filter(OfflinePackageSource.bundle_id == bundle_id)
    items = q.order_by(OfflinePackageSource.id.desc()).all()
    return {"items": [_source_to_dict(s) for s in items], "total": len(items)}


def delete_source(db: Session, source_id: int) -> bool:
    s = db.query(OfflinePackageSource).filter(OfflinePackageSource.id == source_id).first()
    if not s:
        return False
    db.delete(s)
    db.commit()
    return True


def get_health_status(db: Session) -> dict:
    registries = db.query(OfflineRegistry).all()
    sources = db.query(OfflinePackageSource).filter(OfflinePackageSource.is_active == True).all()  # noqa: E712
    reg_items = []
    for r in registries:
        t = test_registry(r)
        reg_items.append({**_registry_to_dict(r), "reachable": t.get("ok"), "message": t.get("message")})
    src_items = []
    for s in sources:
        ok = False
        try:
            req = Request(s.source_url, method="HEAD")
            resp = urlopen(req, timeout=5)
            ok = resp.status < 400
        except Exception:
            ok = False
        src_items.append({**_source_to_dict(s), "reachable": ok})
    bundles = db.query(OfflineRepoBundle).all()
    return {
        "registry_count": len(registries),
        "source_count": len(sources),
        "bundle_count": len(bundles),
        "loaded_bundle_count": len([b for b in bundles if b.status == "loaded"]),
        "registries": reg_items,
        "sources": src_items,
        "source_http_base": f"http://{_local_ip()}:{SOURCE_PORT}",
    }


def get_repo_config_for_plan(db: Session, plan_id: int) -> dict:
    """获取部署计划所需的离线配置（镜像仓库地址 / 包源地址），供 deploy_plans 对接。"""
    from app.models import DeployPlan
    plan = db.query(DeployPlan).filter(DeployPlan.id == plan_id).first()
    default_registry = db.query(OfflineRegistry).filter(OfflineRegistry.is_default == True).first()  # noqa: E712
    sources = db.query(OfflinePackageSource).filter(OfflinePackageSource.is_active == True).all()  # noqa: E712
    return {
        "plan_id": plan_id,
        "plan_name": plan.name if plan else "",
        "registry_url": default_registry.registry_url if default_registry else "",
        "registry_is_insecure": not (default_registry.is_secure if default_registry else False),
        "package_sources": [_source_to_dict(s) for s in sources],
    }


def list_proxies(db: Session) -> list:
    from app.models import DeployProxy
    rows = db.query(DeployProxy).order_by(DeployProxy.is_default.desc(), DeployProxy.id.asc()).all()
    return [_proxy_to_dict(p) for p in rows]


def _proxy_to_dict(p) -> dict:
    return {
        "id": p.id, "name": p.name,
        "http_proxy": p.http_proxy or "", "https_proxy": p.https_proxy or "",
        "no_proxy": p.no_proxy or "", "is_default": bool(p.is_default),
    }


def create_proxy(db: Session, payload: dict) -> dict:
    from app.models import DeployProxy
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("代理名称不能为空")
    if payload.get("is_default"):
        db.query(DeployProxy).update({DeployProxy.is_default: False})
    p = DeployProxy(
        name=name,
        http_proxy=(payload.get("http_proxy") or "").strip(),
        https_proxy=(payload.get("https_proxy") or "").strip(),
        no_proxy=(payload.get("no_proxy") or "").strip(),
        is_default=bool(payload.get("is_default")),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _proxy_to_dict(p)


def update_proxy(db: Session, proxy_id: int, payload: dict) -> Optional[dict]:
    from app.models import DeployProxy
    p = db.query(DeployProxy).filter(DeployProxy.id == proxy_id).first()
    if not p:
        return None
    if payload.get("is_default"):
        db.query(DeployProxy).update({DeployProxy.is_default: False})
    for f in ("name", "http_proxy", "https_proxy", "no_proxy"):
        if f in payload:
            setattr(p, f, (payload.get(f) or "").strip())
    if "is_default" in payload:
        p.is_default = bool(payload.get("is_default"))
    db.commit()
    db.refresh(p)
    return _proxy_to_dict(p)


def delete_proxy(db: Session, proxy_id: int) -> bool:
    from app.models import DeployProxy
    p = db.query(DeployProxy).filter(DeployProxy.id == proxy_id).first()
    if not p:
        return False
    db.delete(p)
    db.commit()
    return True


def set_default_proxy(db: Session, proxy_id: int) -> Optional[dict]:
    from app.models import DeployProxy
    p = db.query(DeployProxy).filter(DeployProxy.id == proxy_id).first()
    if not p:
        return None
    db.query(DeployProxy).update({DeployProxy.is_default: False})
    p.is_default = True
    db.commit()
    return _proxy_to_dict(p)


def resolve_offline_image(db: Session, image: str, use_offline: bool = False) -> dict:
    """离线镜像解析(三部署页共用, 可选开关)。
    当 use_offline=True 且有默认私有 Registry 时:
      - docker hub 简写(无 `/`)→ {registry}/library/{image}(对标 _load_image_tar 的推送格式)
      - 已有仓库路径 → {registry}/{image}
      - 返回 is_secure/insecure 供 docker daemon --insecure-registry 使用
    否则原样返回 + 不 insecure。供组件商店/AI 部署在离线时自动改走私有仓库。
    """
    image = (image or "").strip()
    if not image:
        return {"image": image, "registry_url": "", "is_insecure": False, "offline": False}
    if not use_offline:
        return {"image": image, "registry_url": "", "is_insecure": False, "offline": False}
    registry = db.query(OfflineRegistry).filter(OfflineRegistry.is_default == True).first()  # noqa: E712
    if not registry or not registry.registry_url:
        return {"image": image, "registry_url": "", "is_insecure": not bool(getattr(registry, "is_secure", False) if registry else False), "offline": False}
    url = registry.registry_url.rstrip("/")
    # docker hub 简写: redis:7 / nginx:latest → library/xxx
    if "/" not in image:
        target = f"{url}/library/{image}"
    else:
        target = f"{url}/{image}"
    return {
        "image": target,
        "registry_url": url,
        "is_insecure": not (registry.is_secure if registry else False),
        "offline": True,
    }
