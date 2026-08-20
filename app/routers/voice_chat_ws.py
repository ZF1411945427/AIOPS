"""
WebSocket 全双工语音对话端点 /agent/voice/ws（借鉴小智 ESP32 语音协议，2026-08-19 融合改造）

与传统「录音→上传→SSE 文本→TTS 下载→播放」的回合制不同，本端点用一条持久 WebSocket
承载完整的语音对话闭环，实现三个核心体验：
  1. 流式对话：LLM 流式输出 token，文本完整后按句切分、逐句 TTS 合成实时下推（前端边收边播）
  2. 插话中断：任意时刻客户端发 `abort` → 立即停止当前 TTS 逐句下推 + 中止 LLM 生成，
     清空缓冲回到 listening，用户新语音无缝接入
  3. 状态机：idle ↔ listening ↔ processing ↔ speaking 自动流转，支持自动回听(VAD 由前端+后端联动)

协议（text = JSON 控制消息，binary = 音频帧）：
  客户端 → 服务器:
    {"type":"hello", "session_id":?}                  # 握手
    {"type":"listen", "state":"start"|"stop"}          # 开始/结束录音（stop 后跟随音频帧）
    {"type":"audio", ...}  (binary frame)              # PCM/Opus 音频帧（STT 前累积）
    {"type":"abort", "reason":"user_interrupt"}        # 插话中断
    {"type":"tts_done"}                                # 客户端播放完当前句
  服务器 → 客户端:
    {"type":"hello", "session_id":...}
    {"type":"stt", "text":"..."}                       # 语音识别结果
    {"type":"llm", "token":"..."}                      # LLM 流式文本
    {"type":"tts", "state":"start", "sentence":"..."}  # 开始某句 TTS
    {"type":"tts", "state":"sentence", "sentence":"..."}
    (binary frame)                                     # 该句 MP3 音频帧
    {"type":"tts", "state":"stop"}
    {"type":"emotion", "emotion":"happy"}              # 情绪（驱动前端粒子特效）
    {"type":"done", "reply":"...", "session_id":...}
    {"type":"error", "message":"..."}
"""
import asyncio
import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session

from app.logger import logger
from app.services.mobile_push_service import verify_login_token
from app.services.ws_manager import ws_manager

router = APIRouter(prefix="/agent", tags=["agent_voice_ws"])

# ── 会话级取消令牌（用户插话/断开时置 True，生成器定期检查）──
_VOICE_ABORT: dict = {}  # ws_id -> True
# ── 每连接"对话纪元"号（ws_id -> int）：新触发一次对话即自增。
# 取代单纯布尔 abort 无法表达"又开新一轮"的缺陷，防止新旧对话串号/误复位。──
_WS_EPOCHS: dict = {}


def _new_dialog_epoch(ws_id: str) -> int:
    """为某条 WS 连接递增"对话纪元"号并返回。

    每次用户真正说一句话并触发对话(而非打断/静默)时自增。对话任务通过捕获
    创建时的纪元号, 判断自己是否已被更新的对话取代/打断 —— 取代单纯布尔
    `_VOICE_ABORT` 只能"置 true"、却无法表达"又开了新一轮"的缺陷:
    asr_start 误复位会把上一轮对话的 abort 清掉, 导致尾句残留发声。
    """
    e = _WS_EPOCHS.get(ws_id, 0) + 1
    _WS_EPOCHS[ws_id] = e
    return e


def _current_dialog_epoch(ws_id: str) -> int:
    return _WS_EPOCHS.get(ws_id, 0)

# ── 语音专属人设 prompt（借鉴小智 xiaozhi-server 的说话之道，替换文字版 agent prompt）──
# 语音通道永远用它，而不是配置里那套面向文字报告/表格的严肃 system_prompt：
# 那是给"看"的，逐句 TTS 朗读出来就生硬（念出一堆 # * 1. 和术语）。
# 本 prompt 让 AI 像真人一样开口说话：口语化、短句、先结论、有温度但克制、不油腻。
_VOICE_SYSTEM_PROMPT = """你是智渊，一个会说话的 AIOps 智能运维语音助手，服务一位运维工程师（以下称"爸爸"）。

说话方式（最重要的，每条都要做到）：
1. 说人话，像朋友聊天，绝不像写报告。别念文档，别罗列字段。
2. 短句优先，一句话一个意思，方便语音朗读。先说结论，再说一句必要细节。
3. 绝对禁止 Markdown 标记：不要用 #、*、`、-、数字序号、表格。这些朗读出来全是噪音。
4. 有温度但克制：可以自然带一点"嗯、呢、嘛、好、那"这类语气词，偶尔一句俏皮话调剂，
   但不要油腻、不要堆叠卖萌、不要每句都加表情符号。多数时候就正常说话。
5. 要提专业术语时，顺势用一句话人话解释一下，别让爸爸听不懂。
6. 你有能力查资产、看告警、分析日志和链路、执行运维操作，但要用"说"的方式讲清楚结果，
   不要展开长篇分析；爸爸没细问就别堆细节。

示例（照这个感觉说）：
- 爸爸问"看看现在有没有告警" → "我看了看，目前有 3 条严重告警，主要是 39 这台机器有个僵尸进程，另外 11 的负载有点高。不着急处理的，我先盯着，你要我处理哪个随时说。"
- 爸爸问"系统怎么样" → "整体挺稳的，资产和指标都正常，就是有几条告警挂在那，我给你念叨念叨？"

最重要的底线：
- 会话里会给你一段"当前实时盘面"（真实抓的告警/状态）。你回答涉及状态、告警、数据时，**只能基于盘面里有的说**，绝不编造、绝不虚构数字或告警。
- 盘面里没有、而你又没真查到的东西，就如实讲："这个我手头看不太到，得去查一下"，不要硬编。

记住：你在"说话"，不是在"写报告"。"""



def _get_db():
    from app.database import get_session_for, get_db_mode
    return get_session_for(get_db_mode())()


def _resolve_provider(db: Session):
    from app.models import AIProvider
    provider = db.query(AIProvider).filter(AIProvider.is_enabled == True).first()  # noqa: E712
    return provider


def _split_sentences(text: str, max_len: int = 60):
    """把回复文本按句切分（。！？!?；\n 及英文句号），供逐句 TTS 合成。

    切分后合并过短的片段，避免合成碎片化；单句超长时兜底整句（TTS 侧再截断）。
    """
    import re
    raw = (text or "").strip()
    if not raw:
        return []
    # 按中文/英文句末标点 + 换行切分
    parts = re.split(r'(?<=[。！？!?；;\n])', raw)
    sentences = []
    buf = ""
    for p in parts:
        seg = p.strip()
        if not seg:
            continue
        if buf and (buf + seg).strip():
            candidate = (buf + seg).strip()
            if len(candidate) <= max_len * 2:
                sentences.append(candidate)
                buf = ""
                continue
        if len(seg) > max_len:
            if buf:
                sentences.append(buf.strip())
                buf = ""
            sentences.append(seg)
        else:
            if buf:
                sentences.append(buf.strip())
                buf = ""
            buf = seg
    if buf.strip():
        sentences.append(buf.strip())
    return [s for s in sentences if s]


def _split_closed(text: str):
    """只切出"以句末标点完整闭合"的句子(供流式增量 TTS 用)：未闭合的尾巴留待结尾处理。

    避免 `_split_sentences` 把未闭合递增前缀误当整句，导致边生成边合成时重复/错乱。
    """
    import re as _re
    segs = _re.split(r'(?<=[。！？!?；;\n])', (text or "").strip())
    out = []
    for p in segs:
        s = p.strip()
        if not s:
            continue
        if s.endswith(("。", "！", "？", "!", "?", "；", ";", "\n")):
            out.append(s)
    return out


async def _stream_llm_tokens(provider, messages, ws: WebSocket, ws_id: str, tools=None, on_partial=None, ws_lock=None):
    """异步流式调用 stream_llm，逐 token 经 WS 下发；支持 abort 中断。返回完整文本。

    改造：不再用 run_in_executor 一次性攒完再逐个发(会造成"字慢半拍"且无法边生成边合成)，
    而是逐个拉取 token、逐个下发；on_partial(text_so_far) 在每个 token 后回调，调用方
    可借此边生成边切句合成 TTS(真流式出语音，首句无需等整段)。
    ws_lock: 可选的 WS 发送互斥锁(避免 LLM 文本发送与并发 TTS 音频发送冲突)。
    """
    from app.services.agent_service import stream_llm
    loop = asyncio.get_running_loop()
    it = iter(stream_llm(provider, messages, tools))

    def _next():
        try:
            return next(it)
        except StopIteration:
            return None
        except Exception as e:  # stream_llm 内部错误
            return {"error": str(e)}

    full_text = []
    while True:
        if _VOICE_ABORT.get(ws_id):
            return "".join(full_text).strip(), True
        item = await loop.run_in_executor(None, _next)
        if item is None:
            break
        if "token" in item:
            tok = item["token"]
            full_text.append(tok)
            try:
                if ws_lock:
                    async with ws_lock:
                        await ws.send_json({"type": "llm", "token": tok})
                else:
                    await ws.send_json({"type": "llm", "token": tok})
            except Exception:
                raise
            if on_partial:
                on_partial("".join(full_text))
        elif "error" in item:
            logger.warning("语音 WS LLM 错误: %s", item["error"])
            raise RuntimeError(item["error"])
    return "".join(full_text).strip(), False


async def _synthesize_and_push(ws: WebSocket, db: Session, sentence: str, voice: str):
    """合成单句 TTS 并经 WS 下发 (tts state + binary MP3)。返回是否成功。"""
    from app.services import voice_service
    data, media_type, engine = voice_service.synthesize(db, sentence, voice=voice)
    if not data:
        return False
    try:
        await ws.send_json({"type": "tts", "state": "sentence", "sentence": sentence, "engine": engine})
        await ws.send_bytes(data)
    except Exception:
        raise
    return True


async def _make_emotion(text: str) -> str:
    """极轻量规则情绪判定（无额外 LLM 调用，避免延迟）。

    只对"明确的负面/正面/进行中"语境触发对应情绪；"告警/警告/warning"等中性运维词
    不单独触发 alert（AI 常在中性能力描述/历史复述里提到它们，会误报警示情绪）。
    优先级：alert(负面事件) > happy(正面结果) > thinking(进行中) > neutral。
    """
    t = (text or "").lower()
    # 明确负面动作/结论（当下发生）→ 警示。
    # 刻意排除"故障/异常/告警/警告"等名词：AI 常在能力描述/历史复述中提及（如"帮你分析故障"），
    # 会误报警示情绪；只对"失败/出错/严重/宕机/不可用/超时/无法/拒绝/error/failed/critical/404"这类
    # 明确负面动作触发。
    if any(k in t for k in ("失败", "出错", "严重", "宕机", "不可用", "超时", "无法", "拒绝",
                            "连接断开", "error", "failed", "critical", "exception", "404")):
        return "alert"
    # 正面结果 → 愉悦
    if any(k in t for k in ("完成", "成功", "已处理", "恢复正常", "正常了", "解决了", "没有异常", "ok")):
        return "happy"
    # 进行中/分析类 → 思考
    if any(k in t for k in ("正在", "分析", "查询", "检索", "执行", "检查")):
        return "thinking"
    return "neutral"


def _build_voice_context(db: Session) -> str:
    """抓取轻量实时盘面（活跃告警计数 + 最新几条摘要），供语音人设引用真实数据。

    避免语音对话凭空编造告警/状态：把真实盘面喂给 LLM，并只在有数据时才给。
    查询失败 / 无数据时返回空串，由调用方决定是否追加（绝不影响语音对话本身）。
    """
    try:
        from app.models import Alert
        from sqlalchemy import func
        total = db.query(func.count(Alert.id)).filter(
            Alert.status == "triggered", Alert.archived == False  # noqa: E712
        ).scalar() or 0
        latest = (
            db.query(Alert)
            .filter(Alert.status == "triggered", Alert.archived == False)  # noqa: E712
            .order_by(Alert.created_at.desc())
            .limit(3)
            .all()
        )
        if total <= 0:
            return ""
        lines = [f"当前活跃告警共 {total} 条。"]
        for a in latest:
            sev = (a.severity or "").upper()
            msg = (a.message or "").strip()[:60]
            lines.append(f"- [{sev}] {msg or a.metric_name}")
        return "\n".join(lines)
    except Exception as e:
        logger.warning("[except:pass] 语音盘面抓取失败(不影响对话): %s", e)
        return ""


async def _run_voice_dialog(ws: WebSocket, db: Session, session_id, config_name,
                            user_text: str, user_id: int, voice: str):
    """一次完整的语音对话：STT 文本 → LLM 流式 → 逐句 TTS 下推。支持中途 abort。"""
    ws_id = str(id(ws))
    from app.services.agent_service import (
        get_or_create_session, get_message_history, add_message,
    )
    from app.models import AgentConfig

    # 创建/复用会话
    session = get_or_create_session(db, user_id, session_id)
    config = db.query(AgentConfig).filter(AgentConfig.name == config_name).first()
    if not config or session.title == "新会话":
        session.title = (user_text or "语音对话")[:30]
        db.commit()

    provider = _resolve_provider(db)
    if not provider:
        await ws.send_json({"type": "error", "message": "未配置可用的 LLM 提供商"})
        return None

    # 记录用户消息
    add_message(db, session.id, "user", user_text or "（语音）")

    messages = get_message_history(db, session, config)
    # 语音通道用专属口语化人设（小智式说话之道），不用配置里面向文字报告/表格的严肃 prompt
    system_prompt = _VOICE_SYSTEM_PROMPT
    messages.insert(0, {"role": "system", "content": system_prompt})
    # 注入真实实时盘面：让回复只基于真实数据，避免语音对话编造假告警/状态
    ctx = _build_voice_context(db)
    if ctx:
        messages.insert(1, {"role": "system", "content":
            "当前实时盘面（真实抓取，回答涉及状态/告警/数据时只能基于它，不得编造）：\n" + ctx})
    messages.append({"role": "user", "content": user_text or ""})

    # 流式 LLM + 边生成边切句合成 TTS(真流式)——借鉴小智，不再等整段生成完才合成，
    # 首句一旦产出立即并发合成推送，整段合成重叠进行，大幅降低"字早出声后到"延迟。
    from app.services import voice_service as _vs
    loop = asyncio.get_running_loop()
    ws_send_lock = asyncio.Lock()
    tts_queue = asyncio.Queue()
    _sent_done = set()

    def _feed_sentences(text):
        # 增量切句：只把尚未入队、已闭合的句子入队交给 TTS 后台合成(未闭合尾巴留待收尾)
        for s in _split_closed(text or ""):
            if s and s not in _sent_done:
                _sent_done.add(s)
                try: tts_queue.put_nowait(s)
                except Exception: pass

    def _on_partial(text_so_far):
        _feed_sentences(text_so_far)

    async def _tts_consumer():
        while True:
            s = await tts_queue.get()
            if s is None:
                break
            if _VOICE_ABORT.get(ws_id):
                continue
            try:
                data, mime, eng = await loop.run_in_executor(
                    None, lambda x=s: _vs.synthesize(db, x, voice=voice))
            except Exception:
                data, mime, eng = None, None, ""
            if not data:
                continue
            try:
                async with ws_send_lock:
                    await ws.send_json({"type": "tts", "state": "sentence", "sentence": s, "engine": eng})
                    await ws.send_bytes(data)
            except Exception:
                break

    try:
        await ws.send_json({"type": "tts", "state": "start"})
    except Exception:
        return None
    consumer = asyncio.create_task(_tts_consumer())
    try:
        full_text, aborted = await _stream_llm_tokens(
            provider, messages, ws, ws_id, on_partial=_on_partial, ws_lock=ws_send_lock)
    except asyncio.CancelledError:
        # 被插话中断/新语音打断/连接断开：清理 TTS consumer 后让取消向上传播
        consumer.cancel()
        raise
    except RuntimeError as e:
        consumer.cancel()
        await ws.send_json({"type": "error", "message": f"LLM 调用失败: {e}"})
        return None
    except Exception as e:
        consumer.cancel()
        logger.warning("[except:pass] voice LLM 异常: %s", e, exc_info=True)
        await ws.send_json({"type": "error", "message": "LLM 调用异常"})
        return None

    if aborted or _VOICE_ABORT.get(ws_id):
        consumer.cancel()
        return None
    if not full_text:
        full_text = "抱歉，我没有理解你的意思，请再说一次。"

    # 情绪判定
    emotion = await _make_emotion(full_text)
    try:
        await ws.send_json({"type": "emotion", "emotion": emotion})
    except Exception:
        pass

    # 落库 assistant
    try:
        add_message(db, session.id, "assistant", full_text)
    except Exception as _e1:
        logger.warning("[except:pass] add msg: %s", _e1)

    # 收尾：LLM 结束后的尾巴(无句末标点的最后一句)也交给 TTS
    # 用完整切分(含未闭合尾巴)补入所有尚未入队的句子
    for s in _split_sentences(full_text):
        if s and s not in _sent_done:
            _sent_done.add(s)
            try: tts_queue.put_nowait(s)
            except Exception: pass
    # 等 TTS 全部合成推送完(或插话中断)；超时兜底防永久卡
    try:
        await tts_queue.put(None)
        await asyncio.wait_for(consumer, timeout=120)
    except (asyncio.TimeoutError, Exception):
        if not consumer.done():
            consumer.cancel()
    if not _VOICE_ABORT.get(ws_id):
        try:
            await ws.send_json({"type": "tts", "state": "stop"})
        except Exception:
            pass

    return {"session_id": session.id, "reply": full_text}


async def _drive_stream_asr(provider_cfg, queue: asyncio.Queue, websocket: WebSocket,
                            final_holder: list, abort_holder: list):
    """从 queue 读 PCM 帧, 驱动百度 realtime_asr 流式识别, 向前端回 asr_partial, 定稿入 final_holder。

    queue     : 前端二进制帧进入的 asyncio.Queue
    final_holder: 单元素 list, 结束时放入最终定稿文本(无则 "")
    abort_holder: 单元素 list, 置 True 立即退出
    """
    from app.services import voice_stream_asr

    async def pcm_gen():
        sentinel = object()
        while True:
            if abort_holder and abort_holder[0]:
                break
            try:
                item = await asyncio.wait_for(queue.get(), timeout=3.0)
            except asyncio.TimeoutError:
                # 3s 无新音频:视为该句结束(服务端也应已出 fin),退出让调用方收尾
                break
            if item is sentinel:
                break
            yield item

    holding = {"final": "", "partial": ""}
    loop = asyncio.get_running_loop()

    def _send_sync(payload):
        # stream_recognize 的回调是同步触发的, 把 async 发送提交回事件循环
        try:
            coro = websocket.send_json(payload)
            loop.create_task(coro)
        except Exception:
            pass

    def on_partial(t):
        holding["partial"] = t
        _send_sync({"type": "asr_partial", "text": t})

    def on_final(t):
        holding["partial"] = ""
        holding["final"] = t

    def on_error(e):
        _send_sync({"type": "asr_error", "message": e})

    await voice_stream_asr.stream_recognize(
        provider_cfg, pcm_gen(), on_partial=on_partial, on_final=on_final, on_error=on_error
    )
    if final_holder:
        final_holder[0] = holding["final"] or holding["partial"]


async def _run_voice_dialog_task(ws: WebSocket, db: Session, session_id, config_name,
                                 user_text: str, user_id: int, voice: str,
                                 dialog_lock: asyncio.Lock, state: dict, epoch: int):
    """后台串行执行一轮语音对话, 结束后自行回 done 消息, 并把最新 session 写回 state。

    dialog_lock : 同一 WS 连接上所有对话任务共享的互斥锁, 保证 db session 不被并发使用
                  (插话打断会用 cancel 旧任务 + 起新任务, 新任务 await 锁等旧任务释放)。
    state       : {'session_id': ...} 可变容器, 供主循环读取最新会话 id。
    epoch       : 创建本任务时的对话纪元号。若任务真正开始执行时已有更新的纪元
                  (说明用户已又说了新一句), 直接放弃, 避免新对话覆盖旧话被瞬间打断。
    """
    ws_id = str(id(ws))
    async with dialog_lock:
        # 若排队期间又来了更新的对话(epoch 已变大), 放弃本次执行, 避免误触发旧文本对话
        if epoch != _current_dialog_epoch(ws_id):
            return
        if _VOICE_ABORT.get(ws_id):
            _VOICE_ABORT[ws_id] = False
        try:
            result = await _run_voice_dialog(ws, db, session_id, config_name,
                                             user_text, user_id, voice)
            if result:
                state["session_id"] = result["session_id"]
                await ws.send_json({
                    "type": "done", "reply": result["reply"], "session_id": result["session_id"],
                })
        except asyncio.CancelledError:
            raise   # 被新对话打断/连接断开，正常取消
        except Exception as e:
            logger.warning("[except:pass] 后台语音对话异常: %s", e, exc_info=True)
            try:
                await ws.send_json({"type": "error", "message": "语音对话异常"})
            except Exception:
                pass


async def _cancel_dialog_task(task):
    """打断当前对话任务(若有且未结束), 并等待其让出 db 串行锁。

    用 cancel + 带超时的 wait 兜底, 避免旧任务持锁不放导致新对话无限排队。
    返回 True 表示旧任务已结束(可安全起新对话)。
    """
    if task is None:
        return True
    if not task.done():
        task.cancel()
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
    except asyncio.TimeoutError:
        pass
    except (asyncio.CancelledError, Exception):
        pass
    return task.done()


@router.websocket("/voice/ws")
async def voice_chat_ws(websocket: WebSocket, token: str = Query("")):
    """全双工语音对话 WebSocket 入口。token 用登录 JWT（aiops-token）。

    关键设计(2026-08 修复"插话中断失效"):
      对话(_run_voice_dialog) 不再在 receive 循环里同步 await —— 那样对话期间
      (LLM 流式+TTS 推送可长达十几秒) receive 循环被阻塞, 客户端发的 abort/
      asr_start 全部读不到, 插话中断形同虚设。
      改造: 主循环专职 receive; 对话放到后台任务(dialog_task)跑, 用 dialog_lock
      保证同一连接 db 串行; 收到 abort/新语音立即置 _VOICE_ABORT / cancel 旧任务,
      让用户随时可打断正在说话的 AI。
    """
    payload = verify_login_token(token) if token else None
    if not payload:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "未认证，请先登录"})
        await websocket.close()
        return
    user_id = int(payload.get("user_id") or 0)
    if not user_id:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "无效用户"})
        await websocket.close()
        return

    await websocket.accept()
    ws_id = str(id(websocket))
    _VOICE_ABORT[ws_id] = False

    db = _get_db()
    session_id = None
    config_name = "default"
    voice = "jarvis"
    # 接收队列：音频帧累积缓冲
    audio_buffer = bytearray()
    # ── 后台对话任务 + 其 db 串行锁 + 会话状态容器 ──
    dialog_task = None
    dialog_lock = asyncio.Lock()
    state = {"session_id": session_id}
    # ── 流式识别会话状态（百度 realtime_asr，向前端回 asr_partial/asr_final）──
    asr_task = None                # 后台流式识别任务(asyncio.Task)
    asr_pending = None             # 最近一条的定稿文本 holder(供 asr_end 触发对话)
    asr_queue = None               # 供流式识别后台任务消费的 PCM 队列
    try:
        # 等待客户端 hello
        await websocket.send_json({"type": "hello", "session_id": session_id,
                                   "available": True, "transport": "websocket"})

        while True:
            msg = await websocket.receive()
            mtype = msg.get("type")

            if mtype == "websocket.disconnect":
                break

            # 二进制帧 = 音频数据（PCM），流式泵入当前识别条
            if mtype == "websocket.receive" and "bytes" in msg and msg["bytes"] is not None:
                b = msg["bytes"]
                if asr_task is not None and asr_queue is not None:
                    # 流式识别进行中：推给后台识别任务实时处理
                    try:
                        asr_queue.put_nowait(b)
                    except Exception:
                        pass
                else:
                    # 回退：整段累积(兼容旧协议,不丢数据)
                    audio_buffer.extend(b)
                continue

            text = msg.get("text")
            if text is None:
                continue
            try:
                data = json.loads(text)
            except Exception:
                continue
            t = data.get("type", "")

            if t == "hello":
                session_id = data.get("session_id") or state["session_id"] or session_id
                state["session_id"] = session_id
                await websocket.send_json({"type": "hello", "session_id": session_id,
                                           "transport": "websocket"})

            elif t == "asr_start":
                # 开始一条流式识别（百度 realtime_asr）：前台边推 PCM 边收 asr_partial
                # 若正在对话(上一次请求尚未完成), 立即打断旧对话任务, 让新语音无缝接入
                if dialog_task is not None and not dialog_task.done():
                    _VOICE_ABORT[ws_id] = True
                    await _cancel_dialog_task(dialog_task)
                    dialog_task = None
                asr_queue = asyncio.Queue()
                holding_holder = [""]
                abort = [False]
                try:
                    from app.services import voice_service
                    provider_cfg = voice_service.resolve_stt_provider(db)
                except Exception:
                    provider_cfg = None
                if provider_cfg is None or provider_cfg.engine != "baidu":
                    # 非百度/未配置流式:退回整段模式, 让 listen 处理
                    if not _VOICE_ABORT.get(ws_id):
                        await websocket.send_json({"type": "asr_error", "message": "未配置百度实时语音识别, 请配置百度STT"})
                    asr_task = None
                    asr_pending = None   # 清残留, 防 asr_end 误用上一次定稿文本触发错误对话
                else:
                    async def _run_asr():
                        try:
                            await _drive_stream_asr(
                                provider_cfg, asr_queue, websocket, holding_holder, abort
                            )
                        except asyncio.CancelledError:
                            raise
                        except Exception as e:
                            logger.warning("[except:pass] 流式ASR: %s", e)
                    asr_task = asyncio.create_task(_run_asr())
                    asr_pending = holding_holder

            elif t == "asr_end":
                # 结束本条流式识别 → 取定稿文本 → 触发 LLM 对话(后台任务, 不阻塞 receive)
                if asr_task is not None:
                    try:
                        # 等后台识别收尾(发 FINISH/收 FIN_TEXT)
                        await asyncio.wait_for(asr_task, timeout=5)
                    except (asyncio.TimeoutError, Exception):
                        if not asr_task.done():
                            asr_task.cancel()
                    asr_task = None
                text_res = (asr_pending[0] if asr_pending else "").strip()
                asr_pending = None
                if not text_res:
                    # 识别空：静默回听(不弹"未识别到语音"打断体验)
                    try:
                        await websocket.send_json({"type": "no_speech", "ready": True})
                    except Exception:
                        pass
                    continue
                if _VOICE_ABORT.get(ws_id):
                    # 流式末帧期间被新语音/插话打断: 放弃本次定稿, 不触发对话(新语音会自己起新对话)
                    continue
                await websocket.send_json({"type": "stt", "text": text_res, "provider": "baidu"})
                session_id = state["session_id"] or session_id
                epoch = _new_dialog_epoch(ws_id)
                _VOICE_ABORT[ws_id] = False
                dialog_task = asyncio.create_task(
                    _run_voice_dialog_task(websocket, db, session_id, config_name, text_res,
                                           user_id, voice, dialog_lock, state, epoch)
                )

            elif t == "listen":
                state_v = data.get("state")
                if state_v == "stop" and audio_buffer:
                    # 整段音频累积完成 → STT
                    try:
                        await websocket.send_json({"type": "status", "state": "recognizing"})
                        from app.services import voice_service
                        text_res, provider = voice_service.transcribe_audio_file(
                            db, bytes(audio_buffer), sample_rate=16000, audio_format=data.get("format", "wav")
                        )
                    except Exception as _s:
                        logger.warning("[except:pass] voice STT: %s", _s)
                        text_res, provider = "", "none"
                    audio_buffer.clear()

                    if not text_res or _VOICE_ABORT.get(ws_id):
                        # 识别空/失败或已被打断：发出不打断的静默回听信号(前端收到后自动回听)，
                        # 而不是 error 弹打断提示(避免"未识别到语音，请再说一次"打断体验)
                        if not _VOICE_ABORT.get(ws_id):
                            try:
                                await websocket.send_json({"type": "no_speech", "ready": True})
                            except Exception:
                                pass
                        continue
                    await websocket.send_json({"type": "stt", "text": text_res, "provider": provider})

                    # 若正在对话, 先打断旧任务再起新对话
                    if dialog_task is not None and not dialog_task.done():
                        _VOICE_ABORT[ws_id] = True
                        await _cancel_dialog_task(dialog_task)
                    session_id = state["session_id"] or session_id
                    epoch = _new_dialog_epoch(ws_id)
                    _VOICE_ABORT[ws_id] = False
                    dialog_task = asyncio.create_task(
                        _run_voice_dialog_task(websocket, db, session_id, config_name, text_res,
                                               user_id, voice, dialog_lock, state, epoch)
                    )

            elif t == "abort":
                # 插话中断：置标志 + 立即打断后台对话任务(此时 receive 循环未被阻塞, 一定能收到)
                _VOICE_ABORT[ws_id] = True
                if dialog_task is not None and not dialog_task.done():
                    # 让后台任务尽快退出(协作式 + cancel 兜底)
                    await _cancel_dialog_task(dialog_task)
                    dialog_task = None
                await websocket.send_json({"type": "aborted", "reason": data.get("reason", "user_interrupt"),
                                           "ready": True})

            elif t == "tts_done":
                # 客户端播完一句（流控/状态同步，可忽略）
                await websocket.send_json({"type": "ack", "event": "tts_done"})

            elif t == "ping":
                await websocket.send_json({"type": "pong", "ts": time.time()})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("[except:pass] voice_chat_ws: %s", e, exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": "语音通道异常"})
        except Exception:
            pass
    finally:
        _VOICE_ABORT[ws_id] = True
        if dialog_task is not None:
            if not dialog_task.done():
                dialog_task.cancel()
        if asr_task is not None and not asr_task.done():
            asr_task.cancel()
        _VOICE_ABORT.pop(ws_id, None)
        try:
            db.close()
        except Exception:
            pass
