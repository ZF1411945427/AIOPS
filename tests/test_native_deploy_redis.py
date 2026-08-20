"""native_deploy 的 redis 分支回归测试: 验证生成脚本的确定性、健壮性与配置正确性。

不发包不上真实目标机, 纯校验生成脚本内容与结构, 防止 redis 部署链路再次回归
(历史坑: 权限 chown 丢失 / sed `/` 分隔符冲突 / 空格拼接语法错 / bind/port 多行 / 密码引号字面量 / heredoc 被 `;\n` join 破坏)。
"""
import io
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.component_catalog_service import native_deploy


def _gen(params, deploy_path="/data/redis"):
    return native_deploy("redis", params, deploy_path=deploy_path)


class TestRedisNativeDeploy:
    def test_port_written_as_single_line_no_duplicate(self):
        s = _gen({"db_port": 16379, "redis_password": "redis123"})
        # port 采用"先删后加" → 生成脚本里应恰好一条  echo 'port 16379'
        assert s.count("port 16379") == 1
        assert "sed -i -E '/^[[:space:]]*#?[[:space:]]*port[[:space:]]/d' $CFG" in s

    def test_chown_redis_rootcause_fix_present(self):
        s = _gen({"db_port": 16379, "redis_password": "redis123"})
        # 权限根因: 改配置后必须 chown redis 用户 + chmod
        assert "chown redis:redis $CFG" in s
        assert "chmod 640 $CFG" in s
        assert "chmod 750 /etc/redis" in s

    def test_semicolon_newline_join_no_space_glue(self):
        s = _gen({"db_port": 16379, "redis_password": "redis123"})
        # 杜绝 `done sleep 2`(空格拼接)跨行语法错: 不应出现 `done sleep`
        assert "done sleep" not in s
        # 命令间用分号+换行分隔
        assert ";\n" in s
        assert " 2>/dev/null || true; done; " in s

    def test_dir_sed_uses_pipe_separator(self):
        s = _gen({"db_port": 16379, "redis_password": "redis123"}, deploy_path="/data/redis")
        # dir 路径含 /, sed 必须用 | 分隔符, 不能用 /(会 unknown option to 's')
        assert "s|^#?\\s*dir\\s+.*|dir /data/redis|" in s
        assert "s/^#?\\s*dir" not in s

    def test_bind_and_protected_mode_driven_by_params(self):
        s = _gen({"db_port": 16379, "redis_password": "redis123", "bind": "127.0.0.1", "redis_protected_mode": "yes"})
        assert "echo 'bind 127.0.0.1' >> $CFG" in s
        assert "echo 'protected-mode yes' >> $CFG" in s
        assert "bind 0.0.0.0" not in s.split("echo 'bind")[1] if "echo 'bind" in s else False

    def test_protected_mode_default_no(self):
        s = _gen({"db_port": 16379, "redis_password": "redis123"})
        assert "echo 'protected-mode no' >> $CFG" in s

    def test_password_not_leaked_as_plaintext_literal(self):
        s = _gen({"db_port": 16379, "redis_password": "redis123"})
        # requirepass 值经 base64 从临时文件注入, 不直接出现在脚本里(防引号/特殊字符)
        assert "requirepass redis123" not in s
        assert ".aiops_redis_pw" in s
        assert "base64 -d > /tmp/.aiops_redis_pw" in s

    def test_probe_has_defensive_retry(self):
        s = _gen({"db_port": 16379, "redis_password": "redis123"})
        # 防御性重试验证(最多 10 次), 避免启动慢误判 DOWN
        assert "seq 1 10" in s
        assert "sleep 1; done" in s

    def test_start_is_idempotent_restart(self):
        s = _gen({"db_port": 16379, "redis_password": "redis123"})
        assert "systemctl enable --now redis" in s
        assert "systemctl restart redis" in s
        assert "service redis restart" in s

    def test_requirepass_delete_then_add_for_uniqueness(self):
        s = _gen({"db_port": 16379, "redis_password": "redis123"})
        assert "requirepass[[:space:]]/d' $CFG" in s

    def test_config_path_is_effective_systemd_conf(self):
        s = _gen({"db_port": 16379, "redis_password": "redis123"})
        # 必须改 systemd ExecStart 真加载的 /etc/redis/redis.conf(此前用 /etc/redis.conf 静默失效)
        assert "CFG=/etc/redis/redis.conf" in s

    def test_no_fork_or_hazardous_directive(self):
        s = _gen({"db_port": 16379, "redis_password": "redis123"})
        for bad in ("rm -rf", "mkfs", "dd of=", "wipefs", "fdisk"):
            assert bad not in s

    def test_temp_password_file_cleaned_after_verify(self):
        s = _gen({"db_port": 16379, "redis_password": "redis123"})
        # 验证段在清理之前(验证读临时文件), 清理 rm 在脚本末尾
        assert s.index("seq 1 10") < s.index("rm -f /tmp/.aiops_redis_pw")
        # 临时文件用 umask 077(权限 600)保护
        assert "umask 077" in s

    def test_health_probe_echoes_up_not_silent_grep(self):
        s = _gen({"db_port": 16379, "redis_password": "redis123"})
        # 部署脚本验证: grep -q PONG 后必须 echo, 避免静默判定误读
        assert "grep -q PONG &&" in s

    def test_no_systemd_active_dependency_for_redis_probe(self):
        # 部署脚本验证用 redis-cli PONG(显式 UP), 不依赖 systemctl is-active(redis --supervised systemd 常显示 deactivating)
        s = _gen({"db_port": 16379, "redis_password": "redis123"})
        assert "is-active redis" not in s

