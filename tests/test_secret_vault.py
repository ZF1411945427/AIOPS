"""Secrets Vault 单测: 加解密往返 / 掩码输出 / 引用注入递归 / CRUD 守卫。

对齐 CONTRACT.md 第五章(F3 凭据保险库): 列表详情一律掩码 + has_value,
空值 = 不更新, 引用解析 fail-open。
"""
import pytest
from types import SimpleNamespace

from app.services import secret_vault
from app.services.secret_vault import (
    encrypt_secret_value, decrypt_secret_value,
    resolve_secret_refs, find_secret_refs, to_dict,
)


class TestCryptography:
    def test_encrypt_decrypt_roundtrip(self):
        ct = encrypt_secret_value("super-secret-password")
        assert ct and ct != "super-secret-password"
        assert decrypt_secret_value(ct) == "super-secret-password"

    def test_empty_value_returns_empty(self):
        assert encrypt_secret_value("") == ""
        assert encrypt_secret_value("  ") == ""
        assert decrypt_secret_value("") == ""

    def test_decrypt_garbage_returns_empty(self):
        assert decrypt_secret_value("not-a-valid-ciphertext") == ""

    def test_deterministic_encryption(self):
        # 同一明文每次密文不同(Fernet 带随机 IV) — 安全性校验
        assert encrypt_secret_value("pw") != encrypt_secret_value("pw")


class TestToDict:
    def _secret(self, **kw):
        base = dict(id=1, name="db_pwd", description="数据库密码",
                    value_type="password", scope="global",
                    secret_value_encrypted=encrypt_secret_value("x"),
                    created_by="admin", created_at=None, updated_at=None)
        base.update(kw)
        return SimpleNamespace(**base)

    def test_masked_output_never_leaks_plaintext(self):
        d = to_dict(self._secret())
        assert d["value_masked"] == "***"
        assert d["has_value"] is True
        assert "x" not in str(d)

    def test_no_value_false(self):
        d = to_dict(self._secret(secret_value_encrypted=""))
        assert d["has_value"] is False

    def test_timestamps_formatted(self):
        from datetime import datetime
        d = to_dict(self._secret(created_at=datetime(2026, 1, 2, 3, 4, 5)))
        assert d["created_at"] == "2026-01-02 03:04:05"


class TestFindRefs:
    def test_extract_dedup_preserves_order(self):
        assert find_secret_refs("{{secret:a}} x {{secret:b}} {{secret:a}}") == ["a", "b"]

    def test_empty_and_no_refs(self):
        assert find_secret_refs("") == []
        assert find_secret_refs("no refs here") == []


class TestResolveRefs:
    def test_string_ref_resolved(self, monkeypatch):
        monkeypatch.setattr(secret_vault, "get_secret_by_name",
                            lambda db, name: SimpleNamespace(secret_value_encrypted=encrypt_secret_value("v1")))
        monkeypatch.setattr(secret_vault, "_get_db", lambda: SimpleNamespace(close=lambda: None))
        assert resolve_secret_refs("user={{secret:u1}} pw={{secret:u1}}") == "user=v1 pw=v1"

    def test_missing_ref_fail_open(self, monkeypatch):
        monkeypatch.setattr(secret_vault, "get_secret_by_name", lambda db, name: None)
        monkeypatch.setattr(secret_vault, "_get_db", lambda: SimpleNamespace(close=lambda: None))
        assert resolve_secret_refs("{{secret:nope}}") == "{{secret:nope}}"

    def test_no_ref_returns_same(self):
        assert resolve_secret_refs("plain") == "plain"

    def test_dict_recursive(self, monkeypatch):
        monkeypatch.setattr(secret_vault, "get_secret_by_name",
                            lambda db, name: SimpleNamespace(secret_value_encrypted=encrypt_secret_value("tok")))
        monkeypatch.setattr(secret_vault, "_get_db", lambda: SimpleNamespace(close=lambda: None))
        out = resolve_secret_refs({"auth": {"token": "{{secret:t}}"}, "keep": 1})
        assert out == {"auth": {"token": "tok"}, "keep": 1}

    def test_list_recursive(self, monkeypatch):
        monkeypatch.setattr(secret_vault, "get_secret_by_name",
                            lambda db, name: SimpleNamespace(secret_value_encrypted=encrypt_secret_value("z")))
        monkeypatch.setattr(secret_vault, "_get_db", lambda: SimpleNamespace(close=lambda: None))
        assert resolve_secret_refs(["{{secret:a}}", 42, None]) == ["z", 42, None]


class TestCreateValidation:
    def test_invalid_name_raises(self, monkeypatch):
        monkeypatch.setattr(secret_vault, "get_secret_by_name", lambda db, name: None)
        with pytest.raises(ValueError):
            secret_vault.create_secret(None, {"name": ""})
        with pytest.raises(ValueError):
            secret_vault.create_secret(None, {"name": "a b"})
        with pytest.raises(ValueError):
            secret_vault.create_secret(None, {"name": "{{secret:x}}"})

    def test_duplicate_name_raises(self, monkeypatch):
        monkeypatch.setattr(secret_vault, "get_secret_by_name", lambda db, name: object())
        with pytest.raises(ValueError):
            secret_vault.create_secret(None, {"name": "dup"})

    def test_create_encrypts_value(self, monkeypatch):
        from datetime import datetime
        captured = {}

        class FakeDB:
            def add(self, s): captured["obj"] = s
            def commit(self): captured["obj"].id = 1; captured["obj"].created_at = datetime.now()
            def refresh(self, s): pass

        monkeypatch.setattr(secret_vault, "get_secret_by_name", lambda db, name: None)
        secret = secret_vault.create_secret(FakeDB(), {"name": "ok", "secret_value": "plain", "description": "d"})
        enc = captured["obj"].secret_value_encrypted
        assert enc and enc != "plain"
        assert decrypt_secret_value(enc) == "plain"
        assert secret.id == 1
