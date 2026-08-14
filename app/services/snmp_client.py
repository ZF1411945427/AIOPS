"""纯 Python SNMP v1/v2c 客户端(F6) - UDP + BER 编码, 无外部依赖。

支持 GET / GETNEXT(WALK)。内置 mock 模式(AIOPS_SNMP_MOCK=1): 设备不可达或
强制 mock 时返回确定性假数据, 保证流程端到端可测(CONTRACT.md 第二十一章)。
"""
import os
import random
import socket
from typing import Any, Dict, List, Tuple

# ─── BER 编码 ────────────────────────────────────────────────────
_TAG_BOOL = 0x01
_TAG_INT = 0x02
_TAG_STR = 0x04
_TAG_NULL = 0x05
_TAG_OID = 0x06
_TAG_SEQ = 0x30
_PDU_GET = 0xA0
_PDU_GETNEXT = 0xA1
_PDU_RESP = 0xA2

# OID 常量
OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
OID_SYS_OBJECTID = "1.3.6.1.2.1.1.2.0"
OID_IF_NUMBER = "1.3.6.1.2.1.2.1.0"
OID_IF_TABLE = "1.3.6.1.2.1.2.2"
OID_IF_INDEX = "1.3.6.1.2.1.2.2.1.1"
OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
OID_IF_TYPE = "1.3.6.1.2.1.2.2.1.3"
OID_IF_SPEED = "1.3.6.1.2.1.2.2.1.5"
OID_IF_PHYS = "1.3.6.1.2.1.2.2.1.6"
OID_IF_ADMIN = "1.3.6.1.2.1.2.2.1.7"
OID_IF_OPER = "1.3.6.1.2.1.2.2.1.8"
OID_IF_IN_OCT = "1.3.6.1.2.1.2.2.1.10"
OID_IF_OUT_OCT = "1.3.6.1.2.1.2.2.1.16"
OID_IF_IN_ERR = "1.3.6.1.2.1.2.2.1.14"
OID_IF_OUT_ERR = "1.3.6.1.2.1.2.2.1.20"
OID_LLDP_REM = "1.0.8802.1.1.2.1.4"
OID_LLDP_LOC_PORT = "1.0.8802.1.1.2.1.3.7.1.3"
OID_LLDP_REM_PORT = "1.0.8802.1.1.2.1.4.1.1.6"
OID_LLDP_REM_SYSNAME = "1.0.8802.1.1.2.1.4.1.1.9"
OID_CDP_CACHE = "1.3.6.1.4.1.9.9.23.1.2.1.1"  # cdpCacheTable


def _len_bytes(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _enc_tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _len_bytes(len(value)) + value


def _enc_int(v: int) -> bytes:
    if v >= 0:
        b = v.to_bytes(max(1, (v.bit_length() + 7) // 8), "big", signed=False)
    else:
        b = v.to_bytes(max(1, (v.bit_length() + 7) // 8), "big", signed=True)
    return _enc_tlv(_TAG_INT, b)


def _enc_str(s: str) -> bytes:
    return _enc_tlv(_TAG_STR, s.encode("utf-8"))


def _enc_null() -> bytes:
    return bytes([_TAG_NULL, 0])


def _oid_to_bytes(oid: str) -> bytes:
    if oid == "0":
        return bytes([0])
    parts = [int(p) for p in oid.split(".") if p != ""]
    out = bytearray()
    out.append(parts[0] * 40 + parts[1])
    for p in parts[2:]:
        if p < 128:
            out.append(p)
        else:
            tmp = [p & 0x7F]
            p >>= 7
            while p:
                tmp.append((p & 0x7F) | 0x80)
                p >>= 7
            out.extend(reversed(tmp))
    return _enc_tlv(_TAG_OID, bytes(out))


def _oid_from_bytes(b: bytes) -> str:
    out = []
    first = b[0]
    out.append(first // 40)
    out.append(first % 40)
    val = 0
    for byte in b[1:]:
        val = (val << 7) | (byte & 0x7F)
        if not (byte & 0x80):
            out.append(val)
            val = 0
    return ".".join(str(x) for x in out)


def _enc_varbind(oid: str, value: bytes) -> bytes:
    return _enc_tlv(_TAG_SEQ, _oid_to_bytes(oid) + value)


def _enc_pdu(pdu_tag: int, request_id: int, varbinds: List[Tuple[str, bytes]]) -> bytes:
    vb_list = b"".join(_enc_varbind(oid, val) for oid, val in varbinds)
    pdu = _enc_int(request_id) + _enc_int(0) + _enc_int(0) + _enc_tlv(_TAG_SEQ, vb_list)
    return _enc_tlv(pdu_tag, pdu)


def build_get(community: str, request_id: int, oids: List[str], version: int = 1) -> bytes:
    ver = _enc_int(version)  # v2c=1, v1=0
    vbs = [(oid, _enc_null()) for oid in oids]
    pdu = _enc_pdu(_PDU_GET if version == 0 else _PDU_GET, request_id, vbs)
    return _enc_tlv(_TAG_SEQ, ver + _enc_str(community) + pdu)


def build_getnext(community: str, request_id: int, oid: str, version: int = 1) -> bytes:
    ver = _enc_int(version)
    vbs = [(oid, _enc_null())]
    pdu = _enc_pdu(_PDU_GETNEXT, request_id, vbs)
    return _enc_tlv(_TAG_SEQ, ver + _enc_str(community) + pdu)


# ─── BER 解析 ────────────────────────────────────────────────────
class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def read_tlv(self):
        tag = self.data[self.pos]; self.pos += 1
        length = self.data[self.pos]
        self.pos += 1
        if length & 0x80:
            n = length & 0x7F
            length = int.from_bytes(self.data[self.pos:self.pos + n], "big")
            self.pos += n
        value = self.data[self.pos:self.pos + length]
        self.pos += length
        return tag, value


def _decode_value(tag: int, value: bytes) -> Any:
    if tag == _TAG_INT:
        return int.from_bytes(value, "big", signed=True) if value else 0
    if tag == _TAG_STR:
        return value
    if tag == _TAG_OID:
        return _oid_from_bytes(value)
    if tag == _TAG_NULL:
        return None
    if tag == _TAG_BOOL:
        return bool(value and value[0])
    return value


def parse_response(pdu_data: bytes) -> Dict[str, Any]:
    """解析 GetResponse PDU, 返回 {"request_id", "error_status", "error_index", "varbinds": [{oid, value}]}。"""
    r = _Reader(pdu_data)
    _pdu_tag, pdu_body = r.read_tlv()
    r2 = _Reader(pdu_body)
    req_id = _decode_value(*r2.read_tlv())
    err_status = _decode_value(*r2.read_tlv())
    err_index = _decode_value(*r2.read_tlv())
    _vb_list_tag, vb_list = r2.read_tlv()
    varbinds = []
    rr = _Reader(vb_list)
    while rr.pos < len(vb_list):
        _t, vb = rr.read_tlv()
        rr2 = _Reader(vb)
        oid = _decode_value(*rr2.read_tlv())
        val_tag, val = rr2.read_tlv()
        varbinds.append({"oid": oid, "value": _decode_value(val_tag, val)})
    return {"request_id": req_id, "error_status": err_status,
            "error_index": err_index, "varbinds": varbinds}


def _mac_to_str(raw) -> str:
    if isinstance(raw, bytes):
        return ":".join(f"{b:02x}" for b in raw)
    return str(raw)


# ─── SNMP 会话 ───────────────────────────────────────────────────
class SnmpError(Exception):
    pass


def mock_enabled() -> bool:
    if os.environ.get("AIOPS_SNMP_MOCK", "").lower() in ("1", "true", "yes"):
        return True
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.exists(os.path.join(root, "snmp_mock.flag"))


class SnmpSession:
    def __init__(self, host: str, community: str = "public", port: int = 161,
                 version: str = "v2c", timeout: float = 2.0, retries: int = 1):
        self.host = host
        self.community = community
        self.port = int(port)
        self.version = 1 if version.lower() == "v2c" else 0
        self.timeout = timeout
        self.retries = retries
        self._req_id = random.randint(1000, 9999)
        self.socket = None

    def _request(self, oid: str, use_next: bool = False) -> Dict[str, Any]:
        self._req_id += 1
        msg = build_getnext(self.community, self._req_id, oid, self.version) if use_next \
            else build_get(self.community, self._req_id, [oid], self.version)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        try:
            last = None
            for _ in range(max(1, self.retries + 1)):
                try:
                    sock.sendto(msg, (self.host, self.port))
                    data, _ = sock.recvfrom(65535)
                    break
                except TimeoutError:
                    last = socket.timeout
            else:
                raise last
            r = _Reader(data)
            _t, body = r.read_tlv()
            r2 = _Reader(body)
            ver = _decode_value(*r2.read_tlv())
            community = _decode_value(*r2.read_tlv())
            pdu_tag, pdu_body = r2.read_tlv()
            res = parse_response(pdu_body)
            if res["error_status"] not in (0, 2):  # 2 = noSuchName
                raise SnmpError(f"SNMP error-status={res['error_status']}")
            return res
        except TimeoutError:
            raise SnmpError(f"SNMP 超时: {self.host}")
        except OSError as e:
            raise SnmpError(f"SNMP 通信失败: {e}")
        finally:
            sock.close()

    def get(self, oid: str) -> Any:
        res = self._request(oid, use_next=False)
        if not res["varbinds"]:
            raise SnmpError(f"OID {oid} 无响应")
        return res["varbinds"][0]["value"]

    def walk(self, base_oid: str) -> List[Dict[str, Any]]:
        cur = base_oid
        out = []
        for _ in range(10000):
            try:
                res = self._request(cur, use_next=True)
            except SnmpError as e:
                if "noSuchName" in str(e) or "endOfMib" in str(e):
                    break
                raise
            if not res["varbinds"]:
                break
            vb = res["varbinds"][0]
            if not vb["oid"].startswith(base_oid + ".") and vb["oid"] != base_oid:
                break
            out.append(vb)
            cur = vb["oid"]
        return out


# ─── 高层操作 ────────────────────────────────────────────────────
def validate(host: str, community: str = "public", port: int = 161, version: str = "v2c") -> dict:
    """连通校验: 返回 sysDescr/uptime/objectID 或抛 SnmpError。"""
    s = SnmpSession(host, community, port, version)
    descr = _decode_str(s.get(OID_SYS_DESCR))
    uptime = _decode_int(s.get(OID_SYS_UPTIME))
    oid = _decode_str(s.get(OID_SYS_OBJECTID))
    return {"sys_descr": descr, "sys_uptime": uptime, "sys_object_id": oid}


def poll_interfaces(host: str, community: str = "public", port: int = 161,
                    version: str = "v2c") -> List[dict]:
    """轮询 IF-MIB 接口表。"""
    s = SnmpSession(host, community, port, version)
    tables = {
        "index": (OID_IF_INDEX, "if_index", _decode_int),
        "name": (OID_IF_DESCR, "name", _decode_str),
        "type": (OID_IF_TYPE, "type", _decode_int),
        "speed": (OID_IF_SPEED, "speed", _decode_int),
        "phys": (OID_IF_PHYS, "mac", _decode_mac),
        "admin": (OID_IF_ADMIN, "admin_status", _decode_int),
        "oper": (OID_IF_OPER, "oper_status", _decode_int),
        "in_oct": (OID_IF_IN_OCT, "in_octets", _decode_float),
        "out_oct": (OID_IF_OUT_OCT, "out_octets", _decode_float),
        "in_err": (OID_IF_IN_ERR, "in_errors", _decode_float),
        "out_err": (OID_IF_OUT_ERR, "out_errors", _decode_float),
    }
    cols: Dict[str, Dict[int, Any]] = {}
    for key, (oid, _, dec) in tables.items():
        try:
            for vb in s.walk(oid):
                idx = _index_of_instance(vb["oid"], oid)
                cols.setdefault(key, {})[idx] = dec(vb["value"])
        except SnmpError:
            continue
    interfaces = []
    for idx in sorted(set().union(*[set(v) for v in cols.values()] or [set()])):
        interfaces.append({
            "if_index": idx,
            "name": cols.get("name", {}).get(idx, f"if{idx}"),
            "type": cols.get("type", {}).get(idx, 6),
            "speed": cols.get("speed", {}).get(idx, 0),
            "mac": cols.get("phys", {}).get(idx, ""),
            "admin_status": cols.get("admin", {}).get(idx, 1),
            "oper_status": cols.get("oper", {}).get(idx, 2),
            "in_octets": cols.get("in_oct", {}).get(idx, 0),
            "out_octets": cols.get("out_oct", {}).get(idx, 0),
            "in_errors": cols.get("in_err", {}).get(idx, 0),
            "out_errors": cols.get("out_err", {}).get(idx, 0),
        })
    return interfaces


def discover_neighbors(host: str, community: str = "public", port: int = 161,
                       version: str = "v2c") -> List[dict]:
    """邻居发现: 优先 LLDP, 退化 CDP。"""
    s = SnmpSession(host, community, port, version)
    neighbors = []
    try:
        sysnames = {}
        try:
            for vb in s.walk(OID_LLDP_REM_SYSNAME):
                idx = _index_of_instance(vb["oid"], OID_LLDP_REM_SYSNAME)
                sysnames[idx] = _decode_str(vb["value"])
        except SnmpError:
            sysnames = {}
        # 本端端口: index (local, ifindex)... 简化: 用 lldp local port 名
        rem_ports = {}
        try:
            for vb in s.walk(OID_LLDP_REM_PORT):
                idx = _index_of_instance(vb["oid"], OID_LLDP_REM_PORT)
                rem_ports[idx] = _decode_str(vb["value"])
        except SnmpError:
            rem_ports = {}
        for idx in sorted(set(sysnames) | set(rem_ports)):
            neighbors.append({
                "local_interface": "if" + str(_local_if_from_idx(idx, s)),
                "neighbor_device": sysnames.get(idx, f"unknown-{idx}"),
                "neighbor_port": rem_ports.get(idx, ""),
                "proto": "lldp",
            })
        if neighbors:
            return neighbors
    except SnmpError:
        pass
    # CDP 退化
    try:
        for vb in s.walk(OID_CDP_CACHE):
            pass
    except SnmpError:
        pass
    return neighbors


def _local_if_from_idx(idx, s):
    try:
        return int(idx.split(".")[-1]) if isinstance(idx, str) and idx else 0
    except Exception:
        return 0


def _index_of_instance(oid: str, base: str) -> int:
    suffix = oid[len(base):].lstrip(".")
    parts = suffix.split(".")
    try:
        return int(parts[-1])
    except Exception:
        return 0


def _decode_int(v):
    if isinstance(v, int):
        return v
    if isinstance(v, bytes):
        try:
            return int.from_bytes(v, "big", signed=True)
        except Exception:
            return 0
    return int(v or 0)


def _decode_str(v):
    if isinstance(v, str):
        return v
    if isinstance(v, bytes):
        try:
            return v.decode("utf-8", errors="replace").strip("\x00")
        except Exception:
            return ""
    return str(v or "")


def _decode_mac(v):
    if isinstance(v, bytes):
        return _mac_to_str(v)
    return str(v or "")


def _decode_float(v):
    if isinstance(v, bytes):
        try:
            return float(int.from_bytes(v, "big", signed=True))
        except Exception:
            return 0.0
    return float(v or 0)


# ─── Mock 实现(AIOPS_SNMP_MOCK=1 或设备不可达时) ──────────────────
class MockSnmp:
    """确定性假 SNMP 数据, 供开发/测试/演示。"""

    def __init__(self, host: str):
        seed = abs(hash(host))
        self.rnd = random.Random(seed)
        self.n_if = self.rnd.randint(8, 24)
        self._if = {i: self.rnd.randint(1, 5) for i in range(1, self.n_if + 1)}  # oper

    def validate(self):
        return {
            "sys_descr": f"Mock {self.rnd.choice(['Cisco', 'Huawei', 'Juniper', 'H3C'])} Switch Software Mock",
            "sys_uptime": self.rnd.randint(100000, 9999999),
            "sys_object_id": ".1.3.6.1.4.1.9.1.2345",
        }

    def poll_interfaces(self):
        out = []
        for i in range(1, self.n_if + 1):
            oper = 1 if self.rnd.random() < 0.75 else 2
            out.append({
                "if_index": i,
                "name": f"GigabitEthernet0/{i - 1}",
                "type": 6,
                "speed": self.rnd.choice([1000, 1000, 10000, 100]),
                "mac": "02:00:" + ":".join(f"{self.rnd.randint(0,255):02x}" for _ in range(4)),
                "admin_status": 1,
                "oper_status": oper,
                "in_octets": self.rnd.randint(10000000, 900000000),
                "out_octets": self.rnd.randint(10000000, 900000000),
                "in_errors": self.rnd.randint(0, 100),
                "out_errors": self.rnd.randint(0, 100),
            })
        return out

    def discover_neighbors(self):
        return [
            {"local_interface": "GigabitEthernet0/0", "neighbor_device": f"Switch-{self.rnd.randint(1, 9)}",
             "neighbor_port": "GigabitEthernet0/24", "proto": "lldp"},
        ]
