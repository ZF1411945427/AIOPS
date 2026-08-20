"""逐步骤 native 部署回归测试(_extract_assignments / _native_step_wrapper / deploy_stream native 分支).

背景: 原生部署曾把 AI 方案的所有步骤合并成一段 set -e 大脚本一次性执行,
失败后才由 AI 事后修正, 无法在步骤之间即时决策。本次改造为:
  逐步骤独立 SSH 执行 → 每步检查 __RC__ → 失败立即 AI 自主决策(fix/retry/skip), 修复后重跑该步。
本测试不发包不上真实目标机: 纯校验包装命令结构与 mock _exec_ssh 的部署流行为。
"""
import base64
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["AIOPS_DB_URL"] = "sqlite:///:memory:"

from app.services.component_catalog_service import (
    _extract_assignments,
    _native_step_wrapper,
    _SHELL_TRANSIENT_VARS,  # noqa: F401
    deploy_stream,
)


# ───────────────────────── _extract_assignments ─────────────────────────
class TestExtractAssignments:
    def test_pure_assignment_trailing_semicolon(self):
        assert _extract_assignments("CFG=/etc/redis/redis.conf;") == ["export CFG=/etc/redis/redis.conf"]

    def test_export_assignment(self):
        assert _extract_assignments("export DEPLOY_DIR='/data/redis1'") == ["export DEPLOY_DIR='/data/redis1'"]

    def test_quoted_value(self):
        assert _extract_assignments("VERSION='7.3.2'") == ["export VERSION='7.3.2'"]

    def test_compound_command_skipped(self):
        # export + ; 接后续命令 → 不作为纯赋值持久化(复合命令行)
        assert _extract_assignments("export REDIS_PASSWORD='redis123' ; (command -v dnf >/dev/null && dnf install -y redis)") == []

    def test_pipe_skipped(self):
        assert _extract_assignments("redis-cli -p 6379 ping | grep PONG") == []

    def test_dynamic_assign_skipped(self):
        assert _extract_assignments("CFG=$(find /etc -name 'redis*.conf')") == []

    def test_transient_var_skipped(self):
        assert _extract_assignments("PWD=/some/path") == []

    def test_multiline_only_extracts_assignment(self):
        r = _extract_assignments("export REDIS_PORT=6379\nfor svc in redis-server; do systemctl stop $svc; done")
        assert r == ["export REDIS_PORT=6379"]

    def test_empty_and_none(self):
        assert _extract_assignments("") == []
        assert _extract_assignments(None) == []

    def test_command_prefix_skipped(self):
        # CC=gcc make 是命令前缀(值含空格), 不是纯赋值
        assert _extract_assignments("CC=gcc make") == []

    def test_comment_blank_skipped(self):
        assert _extract_assignments("  # comment\n\n") == []


# ───────────────────────── _native_step_wrapper ─────────────────────────
class TestNativeStepWrapper:
    def test_wrapper_structure(self):
        w = _native_step_wrapper("echo hello", 42)
        assert "/tmp/.aiops_vars_42" in w
        assert "/tmp/._aiops_step_42.sh" in w
        assert "/tmp/._aiops_out_42" in w
        assert "__RC__=$RC" in w
        assert "base64 -d" in w
        assert "set +e" in w
        assert "tail -60" in w
        assert ". \"$_vf\" 2>/dev/null" in w  # source vars 文件恢复跨步骤变量

    def test_base64_roundtrip(self):
        special = """export A='it's tricky' ; echo "hello $HOME" \\`cmd\\`"""
        w = _native_step_wrapper(special, 7)
        m = re.search(r"echo '([A-Za-z0-9+/=]+)' \| base64 -d", w)
        assert m is not None
        assert base64.b64decode(m.group(1)).decode("utf-8") == special

    def test_real_redis_plan_steps(self):
        # 复现用户日志里 Redis native 部署的 22 步 AI 方案, 每步都要能包装且含 __RC__
        steps = [
            "export REDIS_PASSWORD='redis123' ; (command -v dnf >/dev/null 2>&1 && (dnf install -y redis || dnf install -y epel-release -y && dnf install -y redis) || yum install -y redis) || (apt-get update && apt-get install -y redis-server); (systemctl enable --now redis 2>/dev/null || systemctl enable --now redis-server 2>/dev/null || true)",
            "for svc in redis-server redis; do systemctl stop $svc 2>/dev/null || true; done; for svc in redis-server redis; do systemctl disable $svc 2>/dev/null || true; done; systemctl reset-failed redis-server redis 2>/dev/null || true; sleep 2;",
            "mkdir -p '/data/redis' && chown redis:redis '/data/redis' 2>/dev/null; true;",
            "CFG=/etc/redis/redis.conf;",
            "[ -f $CFG ] && cp $CFG $CFG.bak.$(date +%s) || true;",
            "sed -i -E '/^[[:space:]]*#?[[:space:]]*port[[:space:]]/d' $CFG || true;",
            "echo 'port 3379' >> $CFG;",
            "umask 077; echo 'cmVkaXMxMjM=' | base64 -d > /tmp/.aiops_redis_pw 2>/dev/null || true;",
            "sed -i -E '/^[[:space:]]*#?[[:space:]]*requirepass[[:space:]]/d' $CFG || true;",
            "printf 'requirepass ' >> $CFG; cat /tmp/.aiops_redis_pw >> $CFG; echo >> $CFG;",
            "sed -i -E 's/^#?\\s*maxmemory\\s+.*/maxmemory 456mb/' $CFG;",
            "grep -q '^maxmemory ' $CFG || echo 'maxmemory 456mb' >> $CFG;",
            "sed -i -E 's|^#?\\s*dir\\s+.*|dir /data/redis|' $CFG;",
            "grep -q '^dir ' $CFG || echo 'dir /data/redis' >> $CFG;",
            "sed -i -E '/^[[:space:]]*#?[[:space:]]*bind[[:space:]]/d' $CFG || true;",
            "echo 'bind 0.0.0.0' >> $CFG;",
            "sed -i -E '/^[[:space:]]*#?[[:space:]]*protected-mode[[:space:]]/d' $CFG || true;",
            "echo 'protected-mode no' >> $CFG;",
            "chown redis:redis $CFG; chmod 640 $CFG; chmod 750 /etc/redis 2>/dev/null || true;",
            "systemctl daemon-reload 2>/dev/null; systemctl enable --now redis 2>/dev/null; systemctl restart redis 2>/dev/null || service redis restart 2>/dev/null;",
            '_u=0; for _i in $(seq 1 10); do redis-cli -p 3379 -a "$(cat /tmp/.aiops_redis_pw 2>/dev/null)" ping 2>/dev/null | grep -q PONG && { _u=1; break; }; sleep 1; done; echo "__UP=$_u"',
            "rm -f /tmp/.aiops_redis_pw 2>/dev/null || true",
        ]
        for s in steps:
            w = _native_step_wrapper(s, 999)
            assert "__RC__" in w
        # 22 步里只有 CFG= 是纯赋值 → 提取到 CFG(跨步骤变量持久化生效)
        assigns = []
        for s in steps:
            assigns.extend(_extract_assignments(s))
        assert any("export CFG" in a for a in assigns), "CFG 赋值应被提取"
        assert all("export REDIS_PASSWORD" not in a for a in assigns), "复合行 REDIS_PASSWORD 应跳过"


# ───────────────────────── deploy_stream native 分支 ─────────────────────────
class _FakeAsset:
    name = "vm-test"
    ip = "10.0.0.1"
    connection_type = "ssh"
    id = 1


def _make_comp():
    return {
        "name": "redis", "display_name": "Redis", "version": "7",
        "deploy_types": ["native", "docker", "helm", "ha"],
        "default_port": 6379, "docker_image": "redis:7",
        "param_schema": [],
    }


class _StatefulFakeSsh:
    """有状态的 _exec_ssh mock: 按步骤内容模拟结果, AI 修复后该步骤可通过。"""

    def __init__(self):
        self.exec_calls = []
        self.step_exec_counts = {}
        self.mkdir_fixed = False
        self.restart_fixed = False
        self.ai_fix_cmds_ran = []

    def _decode_step(self, command):
        m = re.search(r"echo '([A-Za-z0-9+/=]+)' \| base64 -d > /tmp/\._aiops_step_\d+\.sh", command)
        if not m:
            return ""
        try:
            return base64.b64decode(m.group(1)).decode("utf-8")
        except Exception:
            return ""

    def __call__(self, asset, command, timeout=30):
        self.exec_calls.append((command, timeout))
        step = self._decode_step(command)
        if step:
            if "mkdir -p '/data/redis'" in step:
                self.step_exec_counts["mkdir"] = self.step_exec_counts.get("mkdir", 0) + 1
                return (True, "dir exists\n__RC__=0") if self.mkdir_fixed else (False, "mkdir: Permission denied\n__RC__=1")
            if "systemctl daemon-reload" in step and "restart redis" in step:
                self.step_exec_counts["restart"] = self.step_exec_counts.get("restart", 0) + 1
                return (True, "service restarted\n__RC__=0") if self.restart_fixed else (False, "Job failed\n__RC__=1")
            return (True, "step OK\n__RC__=0")
        if "mkdir -p /data/redis && chown" in command or "mkdir -p /data/redis" in command:
            self.mkdir_fixed = True
            self.ai_fix_cmds_ran.append(command)
            return (True, "fix applied\n__RC__=0")
        if "systemctl restart redis" in command:
            self.restart_fixed = True
            self.ai_fix_cmds_ran.append(command)
            return (True, "fix applied\n__RC__=0")
        return (True, "UP\n__RC__=0")


class TestDeployStreamNative:
    @pytest.fixture(autouse=True)
    def _patch(self, monkeypatch):
        import app.services.component_catalog_service as ccs
        self.ssh = _StatefulFakeSsh()
        monkeypatch.setattr(ccs, "_exec_ssh", self.ssh)

        decisions = iter([
            {"decision": "fix", "reason": "auto create dir", "fix_commands": ["mkdir -p /data/redis && chown redis:redis /data/redis"], "needs_confirm": False},
            {"decision": "fix", "reason": "auto restart svc", "fix_commands": ["systemctl restart redis"], "needs_confirm": False},
        ])
        def _dec(*a, **k):
            try:
                return next(decisions)
            except StopIteration:
                return {"decision": "", "reason": "AI 不可用", "fix_commands": [], "needs_confirm": True}

        monkeypatch.setattr(ccs, "_ai_autonomous_decision", _dec)
        monkeypatch.setattr(ccs, "_ai_decision_options",
                            lambda *a, **k: [{"title": "重试", "desc": "瞬态"}, {"title": "跳过", "desc": "继续"}])

        class _Provider:
            is_enabled = True
            provider_type = "openai"
            api_key = "sk-test"
            api_base = "http://localhost:1"
            model = "test"
        monkeypatch.setattr(ccs, "_get_deploy_provider", lambda db: _Provider())
        monkeypatch.setattr(ccs, "_ai_deploy_tip",
                            lambda *a, **k: {"summary": "tip", "advice": "ok"})
        monkeypatch.setattr(ccs, "_ai_deploy_diagnosis",
                            lambda *a, **k: {"root_cause": "模拟失败", "advice": "改", "steps": ["s"], "risk": "low"})
        monkeypatch.setattr(ccs, "_ai_final_report",
                            lambda *a, **k: {"overview": "succeeded", "conclusion": "ok", "status": "succeeded"})
        monkeypatch.setattr(ccs, "precheck_deploy",
                            lambda *a, **k: {"ok": True, "issues": [], "system": "rhel",
                                              "checks": [{"name": "ssh", "ok": True, "message": "ok"}]})
        monkeypatch.setattr(ccs, "_plan_to_steps",
                            lambda plan, deploy_type="native": [
                                "export REDIS_PASSWORD='redis123' ; (command -v dnf >/dev/null 2>&1 && dnf install -y redis || yum install -y redis)",
                                "mkdir -p '/data/redis' && chown redis:redis '/data/redis' 2>/dev/null; true;",
                                "CFG=/etc/redis/redis.conf;",
                                "systemctl daemon-reload 2>/dev/null; systemctl restart redis 2>/dev/null",
                            ])
        self.ccs = ccs

    def _run(self):
        self.events = list(self.ccs.deploy_stream(
            db=None, asset=_FakeAsset(), comp=_make_comp(), port=6379, deploy_path="/data/redis",
            deploy_type="native", http_proxy="http://11.0.1.1:7897", https_proxy="",
            no_proxy="127.0.0.1,localhost,.local", install_id=123, params={"db_port": 3379},
            use_offline=False, plan="# Redis plan\n...",
        ))
        return self.events

    def test_step_by_step_execution(self):
        evs = self._run()
        step_logs = [e for e in evs if e.get("type") == "log" and "▶ 步骤 " in e.get("message", "")]
        assert len(step_logs) == 4, f"期望 4 条步骤日志, 实得 {len(step_logs)}"
        wraps = [c for c, _ in self.ssh.exec_calls if "._aiops_step_123.sh" in c]
        assert len(wraps) >= 5, f"每步骤应独立包装执行(含修复后重跑), 实得 {len(wraps)}"

    def test_failure_triggers_ai_decision_and_fix(self):
        evs = self._run()
        ai_decisions = [e for e in evs if e.get("type") == "ai" and e.get("stage") == "decision"]
        assert len(ai_decisions) == 2, f"mkdir/restart 各触发 1 次 AI 决策, 实得 {len(ai_decisions)}"
        diag = [e for e in evs if e.get("type") == "ai" and e.get("stage") == "diagnosis"]
        assert len(diag) == 2
        assert len(self.ssh.ai_fix_cmds_ran) >= 2
        assert self.ssh.step_exec_counts.get("mkdir", 0) >= 2, "AI fix 后应重跑 mkdir 步骤"
        assert self.ssh.step_exec_counts.get("restart", 0) >= 2, "AI fix 后应重跑 restart 步骤"

    def test_final_success_and_cleanup(self):
        evs = self._run()
        completes = [e for e in evs if e.get("type") == "complete"]
        assert any(c.get("status") == "succeeded" for c in completes), \
            f"AI 修复后应部署成功: {[c.get('status') for c in completes]}"
        cleanup = [c for c, _ in self.ssh.exec_calls if "rm -f /tmp/.aiops_vars_123" in c]
        assert len(cleanup) == 1, "部署完成后应清理 vars 文件"

    def test_offline_blocks_public_source_step(self):
        # 离线模式下含公网源的步骤会被拦截
        import app.services.component_catalog_service as ccs
        blocked = ccs._offline_native_block("dnf install -y redis && curl http://download.fedoraproject.org/x")
        assert blocked, "离线模式应拦截公网源"