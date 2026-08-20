"""临时工具: 通过 registry HTTP API 把 docker save 导出的 OCI 镜像 tar 推送到私有仓库。
绕过 Docker Desktop 对 docker push 的代理拦截(私有仓库 11.0.1.1:5000 走 NO_PROXY 直连)。
用法: python _push_image.py <tar路径> <repo名如 kubernetes/calico/cni> <tag如 v3.29.0>
"""
import io, json, os, sys, hashlib, tarfile, urllib.parse, requests

REG = os.environ.get("REG_URL", "http://11.0.1.1:5000")
USER = os.environ.get("REG_USER", "admin")
PASS = os.environ.get("REG_PASS", "admin123")


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def main(tar_path: str, repo: str, tag: str):
    session = requests.Session()
    session.verify = False
    session.headers["Authorization"] = _basic(USER, PASS)
    urllib3_disable()

    with tarfile.open(tar_path, "r") as t:
        names = t.getnames()
        payloads = {}  # digest -> bytes
        for n in names:
            if n.startswith("blobs/sha256/") and t.getmember(n).isfile():
                data = t.extractfile(n).read()
                payloads["sha256:" + n.split("/")[-1]] = data
        idx = json.loads(t.extractfile("index.json").read())
        # 收集 index/manifest 的 digest 引用
        manifest_digest = None
        if idx.get("manifests"):
            manifest_digest = idx["manifests"][0].get("digest")

        # 从单架构 manifest 解析 layers + config(优先用 manifest.v2+json)
        single = None
        for d in payloads:
            try:
                j = json.loads(payloads[d])
                if j.get("mediaType") in (
                    "application/vnd.docker.distribution.manifest.v2+json",
                    "application/vnd.oci.image.manifest.v1+json",
                ) and "layers" in j:
                    single = (d, j)
                    break
            except Exception:
                continue
        if not single:
            raise SystemExit("未找到单架构 manifest")
        mdigest, manifest = single
        cfg_digest = manifest["config"]["digest"]
        layer_digests = [l["digest"] for l in manifest["layers"]]

        # 上传所有需要的 blob(layers + config)
        needed = set(layer_digests) | {cfg_digest}
        for d in needed:
            data = payloads.get(d)
            if data is None:
                print(f"[skip] 缺 blob {d}") if False else None
                # 尝试从 manifest list 里其他层? 这里应有
                raise SystemExit(f"tar 缺少 blob {d}")
            _put_blob(session, repo, d, data)

        # 上传 manifest 到 <repo>/manifests/<tag>
        _put_manifest(session, repo, tag, mdigest, payloads[mdigest],
                      manifest.get("mediaType", "application/vnd.docker.distribution.manifest.v2+json"))
        print(f"PUSH OK: {repo}:{tag} (manifest {mdigest})")


def _basic(u, p):
    import base64
    return "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()


def urllib3_disable():
    try:
        import urllib3
        urllib3.disable_warnings()
    except Exception:
        pass


def _put_blob(session, repo, digest, data):
    # 先尝试 HEAD 是否存在(幂等)
    h = session.head(f"{REG}/v2/{repo}/blobs/{digest}")
    if h.status_code == 200:
        print(f"  blob 已存在,跳过 {digest[:16]}")
        return
    # 初始化上传
    r = session.post(f"{REG}/v2/{repo}/blobs/uploads/", allow_redirects=True)
    if r.status_code not in (202, 201):
        raise SystemExit(f"init upload 失败 {r.status_code}: {r.text}")
    loc = r.headers.get("Location")
    if not loc:
        raise SystemExit("无 upload Location: " + r.text[:200])
    # PUT 数据(monolithic)。 若 loc 不含 digest, 追加查询参数
    sep = "&" if "?" in loc else "?"
    put_url = f"{loc}{sep}digest={digest}"
    r = session.put(put_url, data=data, headers={"Content-Type": "application/octet-stream"})
    if r.status_code not in (201, 200, 202):
        raise SystemExit(f"PUT blob 失败 {r.status_code}: {r.text[:300]}")
    print(f"  blob 已上传 {digest[:16]} ({len(data)}B)")


def _put_manifest(session, repo, tag, digest, data, content_type):
    # 需要把 data 中的镜像名替换? 不需要, 保留原始 manifest + 添加 platform 不必须。
    # 但 registry 要求 config digest 等已上传。content digest 由 docker 校验需 exact。
    h = session.head(f"{REG}/v2/{repo}/manifests/{tag}")
    if h.status_code == 200:
        print("  manifest 已存在,跳过")
        return
    r = session.put(
        f"{REG}/v2/{repo}/manifests/{tag}", data=data,
        headers={"Content-Type": content_type},
    )
    if r.status_code not in (201, 200, 202):
        raise SystemExit(f"PUT manifest 失败 {r.status_code}: {r.text[:400]}")
    print(f"  manifest 已上传 {tag} ({len(data)}B)")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main(sys.argv[1], sys.argv[2], sys.argv[3])
