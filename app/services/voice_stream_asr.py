"""流式语音识别(STT) —— 百度实时语音识别 Realtime ASR 封装(异步)。

对应 CONTRACT.md 26.6 语音契约,新增"流式识别"通道(区别于整段的 transcribe_audio_file)。

原理:连接百度实时语音识别 WebSocket(`wss://vop.baidu.com/realtime_asr?sn=xxx`),
边收前端推来的 16kHz 16bit 单声道 PCM 帧,边把百度返回的
  - MID_TEXT(临时结果) → 实时流式出字(边说边识别)
  - FIN_TEXT(最终结果) → 一句话定稿
回传给前端,实现"真·实时流式识别",消除"整段录音→静音切分→一次性识别"的
"未识别到语音"打断感。

鉴权(百度文档确认):连接时带 ?sn= 随机串;START(data) 里带 appid + appkey(API Key),
不是用 sec-websocket-protocol 头。
协议帧:
  客户端→服务端: Text(START json) / Binary(160ms=5120B PCM帧, 间隔≤5s) / Text(FINISH/CANCEL/HEARTBEAT json)
  服务端→客户端: Text(json: MID_TEXT 临时 | FIN_TEXT 最终 | HEARTBEAT | 错误)
"""
import asyncio
import json
import logging
import uuid

logger = logging.getLogger("aiops.voice")

_ASR_WS = "wss://vop.baidu.com/realtime_asr"
# 默认识别模型:15372 中文普通话(加强标点)。可被 voice_providers.stt_model 覆盖。
_DEFAULT_PID = 15372
# 服务端 5s 收不到音频会断开,发送间隔需控制在 5s 内
_CHUNK_MS = 160  # 建议最佳 160ms/帧
# 16kHz 16bit 单声道:1s=32000B,160ms=5120B
_BYTES_PER_CHUNK = int(16000 * 2 * _CHUNK_MS / 1000)


def _build_pid(provider_cfg) -> int:
    """从配置解析 dev_pid(百度识别模型号)。"""
    try:
        pid = int((provider_cfg.stt_model or "").strip() or 0)
        if pid:
            return pid
    except Exception:
        pass
    return _DEFAULT_PID


async def stream_recognize(
    provider_cfg,
    asyncgen_pcm,
    on_partial=None,
    on_final=None,
    on_error=None,
    sample_rate: int = 16000,
):
    """流式识别一段 PCM 音频(异步)。

    参数:
      provider_cfg   : voice_providers 表里的百度配置行(需 engine=baidu)
      asyncgen_pcm   : 异步生成器,逐个产出 PCM 二进制块(bytes,任意大小,内部切 160ms 帧)
      on_partial(str): 回调,百度返回临时结果 MID_TEXT 时调用(实时出字)
      on_final(str)  : 回调,一句话最终结果 FIN_TEXT 时调用
      on_error(str)  : 回调,出错时调用
    返回: None(识别由回调驱动)
    """
    appid = provider_cfg.app_id
    appkey = provider_cfg.access_key_id
    if not (appid and appkey):
        if on_error:
            on_error("未配置百度实时语音识别(appid/appkey)")
        return

    sn = uuid.uuid4().hex
    url = f"{_ASR_WS}?sn={sn}"
    try:
        import websockets
    except ImportError:
        if on_error:
            on_error("后端未安装 websockets 客户端库")
        return

    try:
        async with websockets.connect(url, max_size=None, open_timeout=10) as ws:
            # 1. 发送 START 帧(带鉴权 appid+appkey + 模型)
            start = {
                "type": "START",
                "data": {
                    "appid": int(appid),
                    "appkey": appkey,
                    "dev_pid": _build_pid(provider_cfg),
                    "cuid": f"aiops-{uuid.uuid4().hex[:12]}",
                    "format": "pcm",
                    "sample": sample_rate,
                },
            }
            await ws.send(json.dumps(start))

            # 2. 并发:推送 PCM 帧 + 接收识别结果
            async def pump():
                buf = bytearray()
                async for chunk in asyncgen_pcm:
                    if not chunk:
                        continue
                    buf.extend(chunk)
                    # 切 160ms 帧(5120B)发送;不足一块则保留等下一块
                    while len(buf) >= _BYTES_PER_CHUNK:
                        frame = bytes(buf[:_BYTES_PER_CHUNK])
                        del buf[:_BYTES_PER_CHUNK]
                        await ws.send(frame)
                        await asyncio.sleep(0)  # 让出事件循环,便于收结果/控制节奏
                # 末尾不足一帧的也发出去(让服务端识别完整)
                if buf:
                    await ws.send(bytes(buf))
                # 3. 发送结束帧
                try:
                    await ws.send(json.dumps({"type": "FINISH"}))
                except Exception:
                    pass

            async def receive():
                try:
                    async for raw in ws:
                        # websockets 库: 文本帧已是 str, 二进制帧是 bytes/bytearray
                        if isinstance(raw, (bytes, bytearray)):
                            continue  # 服务端不会回二进制,忽略
                        text = (raw or "").strip()
                        if not text:
                            continue
                        try:
                            d = json.loads(text)
                        except Exception:
                            continue
                        t = d.get("type")
                        err = d.get("err_no")
                        if err not in (0, None):
                            if on_error:
                                on_error(f"百度ASR: {d.get('err_msg') or err}")
                            continue
                        if t == "MID_TEXT":
                            res = (d.get("result") or "").strip()
                            if res and on_partial:
                                on_partial(res)
                        elif t == "FIN_TEXT":
                            res = (d.get("result") or "").strip()
                            if on_final:
                                on_final(res)
                        # HEARTBEAT:忽略
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning("百度实时ASR 接收异常: %s", e)
                    if on_error:
                        on_error(str(e))

            await asyncio.gather(pump(), receive())
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning("百度实时ASR 连接异常: %s", e)
        if on_error:
            on_error(f"百度实时ASR: {e}")
