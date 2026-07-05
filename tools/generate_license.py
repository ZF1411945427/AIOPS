import argparse
import base64
import json
import os
import sys
from datetime import datetime, date

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

HERE = os.path.dirname(os.path.abspath(__file__))
PRIVATE_KEY_PATH = os.path.join(HERE, "private_key.pem")
DEFAULT_OUTPUT = os.path.join(HERE, "license.lic")

VALID_EDITIONS = ["标准版", "企业版", "旗舰版"]


def build_payload(customer, edition, expire, fingerprint, max_nodes, features):
    today = date.today()
    try:
        expire_date = datetime.strptime(expire, "%Y-%m-%d").date()
    except Exception:
        print(f"错误: --expire 格式应为 YYYY-MM-DD，收到 {expire}")
        sys.exit(1)
    if expire_date < today:
        print(f"警告: 到期日期 {expire} 早于今天 {today.isoformat()}，许可证将立即过期")
    if edition not in VALID_EDITIONS:
        print(f"警告: 版本 {edition} 不在标准列表 {VALID_EDITIONS} 中（仍会签发）")
    feat_list = [f.strip() for f in (features or "").split(",") if f.strip()]
    return {
        "customer": customer,
        "edition": edition,
        "issued_at": datetime.now().isoformat(),
        "expire_at": expire,
        "fingerprint": fingerprint,
        "max_nodes": int(max_nodes),
        "features": feat_list,
    }


def sign_payload(payload: dict, private_key) -> str:
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    payload_bytes = payload_json.encode("utf-8")
    signature = private_key.sign(payload_bytes, padding.PKCS1v15(), hashes.SHA256())
    payload_b64 = base64.b64encode(payload_bytes).decode("ascii")
    sig_b64 = base64.b64encode(signature).decode("ascii")
    return f"{payload_b64}.{sig_b64}"


def main():
    parser = argparse.ArgumentParser(description="离线签发 AIOps 平台许可证")
    parser.add_argument("--customer", required=True, help="客户名称")
    parser.add_argument("--edition", required=True, help="版本（标准版/企业版/旗舰版）")
    parser.add_argument("--expire", required=True, help="到期日期 YYYY-MM-DD")
    parser.add_argument("--fingerprint", required=True, help="目标机器指纹（32位）")
    parser.add_argument("--max-nodes", default="100", help="最大节点数")
    parser.add_argument("--features", default="", help="功能模块，逗号分隔")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="输出文件路径")
    args = parser.parse_args()

    if not os.path.exists(PRIVATE_KEY_PATH):
        print(f"错误: 未找到私钥文件 {PRIVATE_KEY_PATH}")
        sys.exit(1)

    with open(PRIVATE_KEY_PATH, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)

    payload = build_payload(
        args.customer, args.edition, args.expire, args.fingerprint, args.max_nodes, args.features
    )
    license_text = sign_payload(payload, private_key)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(license_text)

    print("=" * 60)
    print("许可证签发成功")
    print("=" * 60)
    print(f"客户名称   : {payload['customer']}")
    print(f"版本       : {payload['edition']}")
    print(f"签发时间   : {payload['issued_at']}")
    print(f"到期时间   : {payload['expire_at']}")
    print(f"机器指纹   : {payload['fingerprint']}")
    print(f"最大节点数 : {payload['max_nodes']}")
    print(f"功能模块   : {', '.join(payload['features']) if payload['features'] else '无'}")
    print(f"输出文件   : {args.output}")
    print("=" * 60)
    print("请将此文件安全交付给客户，上传到平台「授权管理」页即可激活。")


if __name__ == "__main__":
    main()
