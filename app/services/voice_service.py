"""语音服务(STT/TTS)云引擎分发层(纯云端, 无本地模型)。

对应 CONTRACT.md 26.6。根据 `voice_providers` 表配置分发音频推理:
- STT(语音识别): 阿里云 / 百度 / 腾讯(需 SDK)
- TTS(语音合成): 阿里云 / 百度 / 腾讯 / edge-tts(免费)

2026-08-19 起移除全部本地语音模型(sherpa KWS/ASR/VITS/VAD, 已删除):
- 调用云 STT 失败时返回空(不再回退本地); 由调用方按空结果处理。
- TTS 云失败回退 edge-tts(微软免费云端), 再失败返回空。
密钥等敏感信息只在本模块解密使用, 不进日志。
"""
import logging

logger = logging.getLogger("aiops.voice")


# ────────────────────────── 配置解析 ──────────────────────────
def resolve_stt_provider(db):
    """按优先级取已启用的 STT 云引擎配置(engine_type in stt/both); 无则 None。"""
    from app.models.agent import VoiceProvider
    try:
        rows = db.query(VoiceProvider).filter(
            VoiceProvider.is_enabled.is_(True),
            VoiceProvider.engine_type.in_(["stt", "both"]),
        ).order_by(VoiceProvider.priority.asc()).all()
        return rows[0] if rows else None
    except Exception:
        return None


def resolve_tts_provider(db):
    """按优先级取已启用的 TTS 云引擎配置(engine_type in tts/both); 无则 None。"""
    from app.models.agent import VoiceProvider
    try:
        rows = db.query(VoiceProvider).filter(
            VoiceProvider.is_enabled.is_(True),
            VoiceProvider.engine_type.in_(["tts", "both"]),
        ).order_by(VoiceProvider.priority.asc()).all()
        return rows[0] if rows else None
    except Exception:
        return None


# ────────────────────────── STT: 语音识别 ──────────────────────────
def transcribe_audio_file(db, audio_bytes, sample_rate=16000, audio_format="wav"):
    """STT 云端分发。返回 (text, provider)。

    provider: "aliyun" / "baidu" / "tencent"; 无配置/无密钥/调用失败返回 ("", provider) 。
    """
    provider_cfg = resolve_stt_provider(db)
    if provider_cfg is None:
        return "", "none"
    engine = provider_cfg.engine
    secret = provider_cfg.get_access_key_secret()
    if not secret:
        return "", provider_cfg.engine

    try:
        if engine == "aliyun":
            text = _aliyun_stt(provider_cfg, audio_bytes, audio_format)
        elif engine == "baidu":
            text = _baidu_stt(provider_cfg, audio_bytes, audio_format)
        elif engine == "tencent":
            text = _tencent_stt(provider_cfg, audio_bytes, audio_format)
        else:
            text = ""
    except Exception as e:
        logger.warning("云 STT(%s) 调用失败: %s", engine, e)
        return "", engine
    return (text or "").strip(), engine


def _aliyun_stt(provider_cfg, audio_bytes, audio_format):
    """阿里云智能语音交互 - 一句话识别 REST。AppKey + access_key_secret(需 Token)."""
    import requests
    ak_id = provider_cfg.access_key_id
    ak_secret = provider_cfg.get_access_key_secret()
    app_key = provider_cfg.app_id or ""
    region = provider_cfg.region or "cn-shanghai"
    if not (ak_id and ak_secret and app_key):
        return ""

    token = _aliyun_get_token(ak_id, ak_secret)
    if not token:
        return ""
    base = provider_cfg.base_url or f"https://nls-gateway-{region}.aliyuncs.com"
    params = {
        "appkey": app_key,
        "token": token,
        "format": "wav",
        "sample_rate": 16000,
        "enable_punctuation_prediction": "true",
        "enable_inverse_text_normalization": "true",
    }
    headers = {"Content-Type": "application/octet-stream"}
    try:
        resp = requests.post(f"{base}/stream/v1/asr", params=params, data=audio_bytes,
                             headers=headers, timeout=15)
    except Exception as e:
        logger.warning("阿里 STT 请求失败: %s", e)
        return ""
    if resp.status_code != 200:
        logger.warning("阿里 STT HTTP %s: %s", resp.status_code, resp.text[:200])
        return ""
    try:
        data = resp.json()
    except Exception:
        return ""
    if data.get("status") == 20000000:
        return (data.get("result") or "").strip()
    logger.warning("阿里 STT 业务错误: %s", data)
    return ""


def _aliyun_get_token(ak_id, ak_secret):
    """换取阿里云访问凭证 Token(带进程级缓存, 过期自动重取)。"""
    import time
    cache = getattr(_aliyun_get_token, "_cache", {})
    now = time.time()
    if cache and cache.get("expire_at", 0) > now + 60:
        return cache["token"]
    import requests
    try:
        resp = requests.get(
            "https://nls-meta.cn-shanghai.aliyuncs.com/",
            params={"AccessKeyId": ak_id, "Action": "CreateToken", "Format": "JSON", "Version": "2019-02-28"},
            timeout=10,
        )
        data = resp.json()
        token = (data.get("Token") or {}).get("Id", "")
        if token:
            _aliyun_get_token._cache = {"token": token, "expire_at": now + 1500}
            return token
    except Exception as e:
        logger.warning("阿里 GetToken 失败: %s", e)
    return ""


def _baidu_stt(provider_cfg, audio_bytes, audio_format):
    """百度短语音识别 REST(整包 base64 上传)."""
    import requests
    api_key = provider_cfg.access_key_id
    secret_key = provider_cfg.get_access_key_secret()
    if not (api_key and secret_key):
        return ""
    token = _baidu_get_token(api_key, secret_key)
    if not token:
        return ""
    import base64
    b64 = base64.b64encode(audio_bytes).decode("utf-8")
    extra = provider_cfg.get_extra()
    dev_pid = int(extra.get("dev_pid", 1537))
    base = provider_cfg.base_url or "https://vop.baidu.com/server_api"
    payload = {
        "format": "wav",
        "rate": 16000,
        "channel": 1,
        "cuid": "aiops-" + (provider_cfg.app_id or "java"),
        "token": token,
        "dev_pid": dev_pid,
        "speech": b64,
        "len": len(audio_bytes),
    }
    try:
        resp = requests.post(base, json=payload, timeout=15)
        data = resp.json()
    except Exception as e:
        logger.warning("百度 STT 请求失败: %s", e)
        return ""
    if data.get("err_no") == 0:
        return (data.get("result") or [""])[0].strip()
    logger.warning("百度 STT 错误: err_no=%s msg=%s", data.get("err_no"), data.get("err_msg"))
    return ""


def _baidu_get_token(api_key, secret_key):
    import time
    cache = getattr(_baidu_get_token, "_cache", {})
    now = time.time()
    if cache and cache.get("expire_at", 0) > now + 60:
        return cache["token"]
    import requests
    try:
        resp = requests.post(
            "https://aip.baidubce.com/oauth/2.0/token",
            params={"grant_type": "client_credentials",
                    "client_id": api_key, "client_secret": secret_key},
            timeout=10,
        )
        data = resp.json()
        token = data.get("access_token", "")
        if token:
            _baidu_get_token._cache = {"token": token, "expire_at": now + (int(data.get("expires_in", 2592000)) - 60)}
            return token
    except Exception as e:
        logger.warning("百度 Token 失败: %s", e)
    return ""


def _tencent_stt(provider_cfg, audio_bytes, audio_format):
    """腾讯云一句话识别(ASR). 需 tencentcloud-sdk-python, 未装则报错并返回空。"""
    sid = provider_cfg.access_key_id
    skey = provider_cfg.get_access_key_secret()
    if not (sid and skey):
        return ""
    try:
        from tencentcloud.common import credential
        from tencentcloud.asr.v20190614 import asr_client, models
    except ImportError:
        logger.warning("未安装 tencentcloud-sdk-python, 腾讯 STT 不可用")
        return ""
    import base64
    cred = credential.Credential(sid, skey)
    region = provider_cfg.region or "ap-beijing"
    client = asr_client.AsrClient(cred, region)
    req = models.SentenceRecognitionRequest()
    req.ProjectId = 0
    req.SubServiceType = 2
    req.EngSerViceType = "16k_zh"
    req.SourceType = 1
    req.Data = base64.b64encode(audio_bytes).decode("utf-8")
    req.VoiceFormat = "wav"
    req.DataLen = len(audio_bytes)
    try:
        resp = client.SentenceRecognition(req)
        return (resp.Result or "").strip()
    except Exception as e:
        logger.warning("腾讯 STT 失败: %s", e)
        return ""


# ────────────────────────── TTS: 语音合成 ──────────────────────────
def synthesize(db, text, voice="jarvis"):
    """TTS 云端分发。返回 (audio_bytes, media_type, engine)。

    engine: "aliyun" / "baidu" / "tencent" / "edge-tts"(默认免费) / ""(失败)
    云 TTS 失败回退 edge-tts, 再失败返回 (None, None, "")。
    """
    provider_cfg = resolve_tts_provider(db)
    if provider_cfg is not None and provider_cfg.get_access_key_secret():
        engine = provider_cfg.engine
        try:
            if engine == "aliyun":
                data, mime = _aliyun_tts(provider_cfg, text)
                if data:
                    return data, mime, "aliyun"
            elif engine == "baidu":
                data, mime = _baidu_tts(provider_cfg, text)
                if data:
                    return data, mime, "baidu"
            elif engine == "tencent":
                data, mime = _tencent_tts(provider_cfg, text)
                if data:
                    return data, mime, "tencent"
        except Exception as e:
            logger.warning("云 TTS(%s) 调用失败, 回退 edge-tts: %s", engine, e)

    # 默认/回退: edge-tts(微软免费云端)
    return _edge_tts(text, voice)


def _edge_tts(text, voice):
    """edge-tts(微软, 免费云端)。返回 (mp3_bytes, "audio/mpeg", "edge-tts")。"""
    import asyncio
    try:
        import edge_tts
    except ImportError:
        logger.warning("未安装 edge-tts, TTS 不可用")
        return None, None, ""
    voices = {"jarvis": "zh-CN-YunjianNeural"}
    v = voices.get(voice, voices["jarvis"])
    mp3 = b""
    try:
        communicate = edge_tts.Communicate(text, voice=v, rate="-8%", pitch="-4Hz")
        mp3 = asyncio.run(_stream_tts(communicate))
    except Exception as e:
        logger.warning("edge-tts 失败: %s", e)
    if mp3:
        return mp3, "audio/mpeg", "edge-tts"
    return None, None, ""


async def _stream_tts(communicate):
    data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            data += chunk["data"]
    return data


def _aliyun_tts(provider_cfg, text):
    """阿里云智能语音交互 - 语音合成 REST(返回 MP3)."""
    import requests
    ak_id = provider_cfg.access_key_id
    ak_secret = provider_cfg.get_access_key_secret()
    app_key = provider_cfg.app_id or ""
    if not (ak_id and ak_secret and app_key):
        return None, None
    token = _aliyun_get_token(ak_id, ak_secret)
    if not token:
        return None, None
    extra = provider_cfg.get_extra()
    voice = provider_cfg.tts_voice or "xiaoyun"
    region = provider_cfg.region or "cn-shanghai"
    base = provider_cfg.base_url or f"https://nls-gateway-{region}.aliyuncs.com"
    params = {
        "appkey": app_key,
        "token": token,
        "text": text,
        "format": "mp3",
        "sample_rate": 16000,
        "voice": voice,
        "volume": extra.get("volume", 50),
        "speech_rate": extra.get("speech_rate", 0),
        "pitch_rate": extra.get("pitch_rate", 0),
    }
    try:
        resp = requests.get(f"{base}/stream/v1/tts", params=params, timeout=15)
        if resp.status_code == 200 and resp.content:
            return resp.content, "audio/mpeg"
    except Exception as e:
        logger.warning("阿里 TTS 请求失败: %s", e)
    return None, None


def _baidu_tts(provider_cfg, text):
    """百度短文本在线合成 REST(基础音库)."""
    import requests
    api_key = provider_cfg.access_key_id
    secret_key = provider_cfg.get_access_key_secret()
    if not (api_key and secret_key):
        return None, None
    token = _baidu_get_token(api_key, secret_key)
    if not token:
        return None, None
    extra = provider_cfg.get_extra()
    per = int(extra.get("per", 0))
    spd = int(extra.get("spd", 5))
    pit = int(extra.get("pit", 5))
    vol = int(extra.get("vol", 5))
    base = provider_cfg.base_url or "https://tsn.baidu.com/text2audio"
    payload = {
        "tex": text, "tok": token, "cuid": "aiops-voice",
        "ctp": 1, "lan": "zh", "spd": spd, "pit": pit, "vol": vol, "per": per,
        "aue": 3,
    }
    try:
        resp = requests.post(base, data=payload, timeout=15)
        ct = resp.headers.get("Content-Type", "")
        if "audio" in ct.lower() and resp.content:
            return resp.content, "audio/mpeg"
        if resp.content and not resp.content.startswith(b"err"):
            return resp.content, "audio/mpeg"
        try:
            err = resp.json()
            logger.warning("百度 TTS 错误: code=%s msg=%s", err.get("err_no"), err.get("err_msg"))
        except Exception:
            pass
    except Exception as e:
        logger.warning("百度 TTS 请求失败: %s", e)
    return None, None


def _tencent_tts(provider_cfg, text):
    """腾讯云语音合成(需 tencentcloud-sdk-python)."""
    sid = provider_cfg.access_key_id
    skey = provider_cfg.get_access_key_secret()
    if not (sid and skey):
        return None, None
    try:
        from tencentcloud.common import credential
        from tencentcloud.tts.v20190823 import tts_client, models
    except ImportError:
        logger.warning("未安装 tencentcloud-sdk-python, 腾讯 TTS 不可用")
        return None, None
    import base64
    extra = provider_cfg.get_extra()
    cred = credential.Credential(sid, skey)
    region = provider_cfg.region or "ap-beijing"
    client = tts_client.TtsClient(cred, region)
    req = models.TextToVoiceRequest()
    req.Text = text
    req.SessionId = "aiops"
    req.ModelType = 1
    req.VoiceType = int(extra.get("voice_type", 101001))
    req.Codec = "mp3"
    req.Volume = float(extra.get("volume", 5))
    req.Speed = float(extra.get("speed", 0))
    try:
        resp = client.TextToVoice(req)
        if resp.Audio and resp.Audio.startswith("data:audio"):
            b64 = resp.Audio.split(",", 1)[1]
            return base64.b64decode(b64), "audio/mpeg"
    except Exception as e:
        logger.warning("腾讯 TTS 失败: %s", e)
    return None, None
