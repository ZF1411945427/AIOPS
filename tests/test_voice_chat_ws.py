"""voice_chat_ws 纯逻辑测试（不连生产 DB，不触发网络/加载模型）。

覆盖：句子切分、情绪判定、登录 token 鉴权、插话中断 abort 标志位语义。
这些函数均为纯计算/HMAC，不依赖数据库，可在 DB 连接池告警期间安全运行。
"""
import asyncio

import pytest

from app.routers import voice_chat_ws as v
from app.services.mobile_push_service import issue_login_token, verify_login_token


class TestSplitSentences:
    def test_basic_split(self):
        sents = v._split_sentences("第一句。第二句！第三句？")
        assert len(sents) >= 2
        assert "第一句" in sents[0]

    def test_newline_split(self):
        sents = v._split_sentences("甲。\n乙！\n丙？")
        assert sents  # 非空即可，切分逻辑允许过短句合并

    def test_short_or_empty(self):
        assert v._split_sentences("") == []
        assert v._split_sentences(None) == []
        assert isinstance(v._split_sentences("   "), list)


class TestMakeEmotion:
    def test_alert(self):
        assert asyncio.run(v._make_emotion("发现严重故障告警")) == "alert"
        assert asyncio.run(v._make_emotion("执行失败")) == "alert"

    def test_happy(self):
        assert asyncio.run(v._make_emotion("处理完成，恢复正常")) == "happy"

    def test_thinking(self):
        assert asyncio.run(v._make_emotion("正在分析数据")) == "thinking"

    def test_neutral(self):
        assert asyncio.run(v._make_emotion("好的，请问还有什么需要")) == "neutral"


class TestAuth:
    def test_valid_login_token(self):
        tok = issue_login_token(2, "admin")
        payload = verify_login_token(tok)
        assert payload is not None
        assert payload.get("user_id") == 2

    def test_invalid_token(self):
        assert verify_login_token("") is None
        assert verify_login_token("bad.token.value") is None


class TestAbortFlagSemantics:
    def test_abort_flag_set_and_clear(self):
        v._VOICE_ABORT["fake_ws"] = False
        assert v._VOICE_ABORT.get("fake_ws") is False
        # 模拟用户插话发 abort
        v._VOICE_ABORT["fake_ws"] = True
        assert v._VOICE_ABORT.get("fake_ws") is True
        # 中断后清除
        v._VOICE_ABORT.pop("fake_ws", None)
        assert v._VOICE_ABORT.get("fake_ws") is None
