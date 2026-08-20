<template>
  <div class="aiops-chat-widget" :style="widgetStyle">
    <!-- Floating bubble trigger: 左=语音开关, 右=AI助手 -->
    <div
      class="chat-trigger"
      :class="{ open: isOpen, dragging: isDragging, voiceon: voiceActive }"
      @mousedown="onTriggerMouseDown"
      role="button"
      :aria-label="isOpen ? '关闭 AI 助手' : '打开 AI 助手'"
    >
      <!-- 左格: 语音常驻聆听开关 -->
      <div
        class="trigger-voice"
        :class="{ active: voiceActive, busy: isRecording }"
        :title="voiceActive ? '语音聆听中（点此关闭）' : (speechSuppRec ? '开启语音指挥（随时说话）' : '当前浏览器不支持语音')"
        @click="onVoiceClick"
      >
        <span class="tv-icon" :class="{ pulse: voiceActive }">{{ voiceActive ? '🎙' : '🎤' }}</span>
        <span class="tv-label">{{ voiceActive ? (isRecording ? '聆听…' : '聆听中') : '语音' }}</span>
        <span class="tv-dot" :class="{ on: voiceActive }"></span>
      </div>

      <!-- 分隔线 -->
      <span class="trigger-divider"></span>

      <!-- 右格: AI 助手(聊天) -->
      <div
        class="trigger-assistant"
        :title="isOpen ? '关闭 AI 助手' : '打开 AI 助手'"
        @click="onTriggerClick"
      >
        <span class="trigger-icon" v-if="!isOpen">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="8"></circle>
            <circle cx="12" cy="12" r="2.3"></circle>
            <circle cx="7" cy="9" r="1" class="ai-node"></circle>
            <circle cx="17" cy="9" r="1" class="ai-node"></circle>
            <circle cx="7" cy="15" r="1" class="ai-node"></circle>
            <circle cx="17" cy="15" r="1" class="ai-node"></circle>
            <line x1="12" y1="2.8" x2="12" y2="5.5"></line>
            <line x1="12" y1="18.5" x2="12" y2="21.2"></line>
            <line x1="2.8" y1="12" x2="5.5" y2="12"></line>
            <line x1="18.5" y1="12" x2="21.2" y2="12"></line>
          </svg>
        </span>
        <span class="trigger-icon close-icon" v-else>
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true">
            <line x1="5" y1="5" x2="19" y2="19"></line>
            <line x1="19" y1="5" x2="5" y2="19"></line>
          </svg>
        </span>
        <span class="ai-status-dot" :class="{ 'is-off': isOpen }" aria-hidden="true"></span>
      </div>
    </div>

    <!-- Chat panel -->
    <Transition name="slide-up">
      <div v-if="isOpen" class="chat-panel" :style="panelStyle">
        <!-- Header (可拖动) -->
        <div class="panel-header" @mousedown="onPanelHeaderMouseDown">
          <div class="panel-header-left">
            <span class="panel-title">AIOps 智能助手</span>
            <span class="panel-subtitle" v-if="activeSession">当前会话</span>
          </div>
          <div class="panel-header-actions">
            <button class="panel-btn" title="新会话" @click="newSession">+</button>
            <button class="panel-btn" title="关闭" @click="isOpen = false">✕</button>
          </div>
        </div>

        <div class="panel-body">
          <!-- Session list -->
          <div class="session-list" v-if="showSessionList">
            <div class="session-list-header">
              <span>会话历史</span>
              <button class="session-back-btn" @click="showSessionList = false">← 返回</button>
            </div>
            <div
              v-for="s in sessions"
              :key="s.id"
              class="session-item"
              :class="{ active: activeSessionId === s.id }"
              @click="switchSession(s.id)"
            >
              <span class="session-title">{{ s.title }}</span>
              <button class="session-del-btn" title="删除会话" @click.stop="deleteSession(s.id)">✕</button>
            </div>
            <div v-if="!sessions.length && !loadingSessions" class="session-empty">暂无历史会话</div>
          </div>

          <!-- Messages -->
          <div class="messages-area" ref="messagesRef" v-show="!showSessionList">
            <div v-if="!messages.length && !loading" class="welcome-area">
              <div class="welcome-icon">🤖</div>
              <div class="welcome-title">AIOps 智能助手</div>
              <div class="welcome-desc">{{ welcomeMessage }}</div>
              <div class="suggested-questions" v-if="suggestedQuestions.length">
                <button
                  v-for="(q, idx) in suggestedQuestions"
                  :key="idx"
                  class="suggested-btn"
                  @click="askQuestion(q)"
                >{{ q }}</button>
              </div>
            </div>

            <div v-for="(m, idx) in messages" :key="idx" class="msg-row" :class="m.role">
              <div class="msg-bubble" :class="[m.role, m.message_type === 'error' ? 'error-bubble' : '']">
                <div class="msg-content">{{ m.content }}</div>
                <div class="msg-meta">
                  <span>{{ formatTime(m.created_at) }}</span>
                  <span v-if="m.tool_calls && m.tool_calls !== '[]'" class="tool-badge">🔧</span>
                </div>
              </div>
            </div>

            <div v-if="loading" class="streaming-indicator">
              <el-icon class="is-loading" :size="14"><Loading /></el-icon>
              <span>AI 正在思考...</span>
            </div>
          </div>
        </div>

        <!-- Pending actions -->
        <div class="pending-bar" v-if="pendingActions.length">
          <div class="pending-title">⏳ 待确认</div>
          <div v-for="pa in pendingActions" :key="pa.id" class="pending-item">
            <div class="pending-item-left">
              <span class="pending-item-text">{{ pa.title }}</span>
              <el-tag :type="riskTagType(pa.risk_level)" size="small" effect="light">{{ pa.risk_level }}</el-tag>
            </div>
            <div class="pending-actions">
              <button class="pending-btn confirm" @click="confirmAction(pa.id)">确认</button>
              <button class="pending-btn cancel" @click="cancelAction(pa.id)">取消</button>
            </div>
          </div>
        </div>

        <!-- Input area -->
        <div class="input-area">
          <div class="input-row">
            <input
              v-model="inputMessage"
              class="chat-input"
              placeholder="输入问题...（语音指挥在左侧🎤）"
              :disabled="loading"
              @keyup.enter="sendMessage"
            />
            <button
              class="send-btn"
              :disabled="loading || !inputMessage.trim()"
              @click="sendMessage"
            >发送</button>
          </div>
          <div class="voice-toolbar">
            <button class="history-btn" @click="showSessionList = !showSessionList">
              <el-icon :size="14"><Clock /></el-icon>
              <span>历史会话</span>
            </button>
            <button class="tts-toggle" :class="{ on: speechEnabled }" @click="speechEnabled = !speechEnabled">
              <span class="tts-char">{{ speechEnabled ? '🔊' : '🔇' }}</span>
              <span>{{ speechEnabled ? '语音播报' : '已静音' }}</span>
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, nextTick, watch, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const STORAGE_KEY = 'aiops_last_session_id'
const POS_STORAGE_KEY = 'aiops_chat_widget_pos'

const isOpen = ref(false)
const showSessionList = ref(false)
const inputMessage = ref('')
const loading = ref(false)
const loadingSessions = ref(false)
const messagesRef = ref(null)
const sessions = ref([])
const messages = ref([])
const activeSessionId = ref(null)
const activeSession = ref(null)
const pendingActions = ref([])
const welcomeMessage = ref('你好，我可以帮你查询资源、分析告警、生成运维任务等。')
const suggestedQuestions = ref([
  '帮我查一下当前告警',
  '分析最近一次故障',
  '列出所有服务器资产',
  '查看 K8s 集群状态',
])
let restoring = false

// ── 语音指挥能力（🎤 录音 → STT 识别 → 发送 + 🔊 云健 TTS 播报 + 导航跳转） ──
const speechEnabled = ref(true)      // TTS 播报开关
const isRecording = ref(false)       // 是否正在录音（临时语音）
const voiceActive = ref(false)       // 常驻语音聆听开关（左格）
const speechSuppRec = ref(false)     // 录音/语音识别是否受支持（不支则禁用 🎤）
const _voiceAudio = ref(null)        // 播报用 audio 元素引用
let _voiceMr = null                  // MediaRecorder
let _voiceMrChunks = []
let _voiceMrTimeout = 0
let _lastByVoice = false             // 本次发送是否由语音发起（驱动回复播报）

// ── 常驻聆听（语音指挥）状态 ──
let _listenStream = null             // 常驻麦克风流
let _listenMr = null                 // 常驻 MediaRecorder
let _listenMrChunks = []
let _listenMrMime = ''               // 常驻录音 mime
let _listenCtx = null                // 常驻 AudioContext(音量检测)
let _listenAnalyser = null
let _listenRaf = 0                   // 音量轮询 raf
let _listenSilentMs = 0              // 已捕捉语音后静音累计（旧：按帧累加，新版仍保留引用）
let _listenLastVoiceTs = 0           // 本段最近一次捕捉到人声的时间戳（用于真实静音时长判定）
let _listenSegStartTs = 0            // 本段开始录音的时间戳（用于最小录音时长保护）
let _listenSomeone = false           // 本段是否已捕捉到人声
let _listenProcessing = false        // 是否正在处理上一段（防并发）
let _listenGuard = 0                 // 单段最长兜底
let _listenMax = 12000               // 单段最长 12s
let _listenVoiceFrames = 0           // 连续有声帧计数（去抖：连续多帧才确认有人说话，抑制环境噪声幻听）
let _voiceClickBusy = false          // 开关防抖

// ── 语音填表模式（借鉴 form-field-extractor：语音逐项填写当前表单） ──
const formFillActive = ref(false)        // 是否处于语音填表模式（常驻聆听持续投喂）
const formFillCtrl = ref(null)           // 当前表单控制器（window._metricCardForm 等）
function _activeFormCtrl() { return formFillCtrl.value }

// 语音指令 → 页面导航意图（前端轻量匹配，命中即 window._navigateTo 跳转）
// key = 匹配到的关键词，value = 目标菜单 key（见 app/routers/menu_config.json）
const VOICE_NAV_RULES = [
  { keys: ['日志中心', '打开日志', '看日志', '去日志'], nav: 'logs', label: '日志中心' },
  { keys: ['告警中心', '打开告警', '看告警', '去告警', '告警列表'], nav: 'alerts', label: '告警中心' },
  { keys: ['指标监控', '指标看板', '打开指标', '去指标', '看指标'], nav: 'metrics', label: '指标监控' },
  { keys: ['监控面板', '实时监控看板', '实时监控', '监控看板'], nav: 'monitor-view', label: '监控面板' },
  { keys: ['系统态势', '态势总览'], nav: 'system-posture', label: '系统态势' },
  { keys: ['故障单', '工单', '故障管理'], nav: 'incident', label: '故障单' },
  { keys: ['资产', '资产列表', '资产管理'], nav: 'asset-list', label: '资产列表' },
  { keys: ['拓扑', '拓扑视图'], nav: 'topology', label: '拓扑视图' },
  { keys: ['预测', '容量预测'], nav: 'prediction-models', label: '预测模型' },
]

function initVoice() {
  speechSuppRec.value = !(
    !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder
  )
}

// ═══════════════ 常驻语音聆听（左格开关 → 随时说话指挥, 全局生效） ═══════════════
function onVoiceClick() {
  if (!speechSuppRec.value) { ElMessage.warning('当前浏览器不支持录音'); return }
  if (_voiceClickBusy) return
  _voiceClickBusy = true
  try {
    if (voiceActive.value) {
      stopAlwaysListen()
    } else {
      startAlwaysListen()
    }
  } finally {
    setTimeout(() => { _voiceClickBusy = false }, 200)
  }
}

async function startAlwaysListen() {
  if (voiceActive.value) return
  let stream
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    })
  } catch (e) {
    const name = e && e.name
    const msg = { NotAllowedError: '麦克风权限被拒，请点地址栏🔒允许', NotFoundError: '未检测到麦克风' }[name] || '无法获取麦克风：' + (e && e.message || '')
    ElMessage.warning(msg)
    return
  }
  _listenStream = stream
  voiceActive.value = true
  _listenMrChunks = []
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']
  const mime = candidates.find(m => window.MediaRecorder.isTypeSupported(m)) || ''
  _listenMrMime = mime
  try {
    _listenMr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
  } catch (e) { _listenMr = new MediaRecorder(stream) }
  _listenMr.ondataavailable = (e) => { if (e.data && e.data.size && e.target === _listenMr) _listenMrChunks.push(e.data) }
  _listenMr.onstop = () => { /* 由 lop loop 决定下一段；不在此处理数据 */ }
  _listenMr.start(250)
  isRecording.value = true
  _listenSomeone = false
  _listenSilentMs = 0
  _listenSegStartTs = Date.now()
  _listenLastVoiceTs = 0
  _startListenDetector()
  ElMessage.success('🔊 语音指挥已开启，请说话')
}

function stopAlwaysListen(silent) {
  const wasOn = voiceActive.value
  voiceActive.value = false
  isRecording.value = false
  _stopListenDetector()
  if (_listenMr && _listenMr.state === 'recording') { try { _listenMr.stop() } catch (e) {} }
  _listenMr = null
  _listenMrChunks = []
  if (_listenStream) { try { _listenStream.getTracks().forEach(t => t.stop()) } catch (e) {}; _listenStream = null }
  _listenSomeone = false; _listenSilentMs = 0; _listenProcessing = false
  if (!silent && wasOn) ElMessage.info('语音指挥已关闭')
}

function _startListenDetector() {
  _stopListenDetector()
  try {
    const AC = _listenCtx || new (window.AudioContext || window.webkitAudioContext)()
    _listenCtx = AC
    if (AC.state === 'suspended') { try { AC.resume().catch(() => {}) } catch (e) {} }
    const src = AC.createMediaStreamSource(_listenStream)
    _listenAnalyser = AC.createAnalyser()
    _listenAnalyser.fftSize = 1024
    _listenAnalyser.smoothingTimeConstant = 0.4
    src.connect(_listenAnalyser)
  } catch (e) { _listenAnalyser = null }

  const tick = () => {
    if (!voiceActive.value) return
    const now = Date.now()
    let rms = 0
    if (_listenAnalyser) {
      try {
        const data = new Uint8Array(_listenAnalyser.fftSize)
        _listenAnalyser.getByteTimeDomainData(data)
        // 用 RMS(均方根)能量而非单点峰值 —— 对短促噪声/爆点更鲁棒，减少误触发(幻听)
        let sum = 0
        const n = data.length
        for (let i = 0; i < n; i++) { const v = (data[i] - 128) / 128; sum += v * v }
        rms = Math.sqrt(sum / n)
      } catch (e) {}
    }
    // 说话判定：RMS 超过阈值，且需连续多帧持续(去抖)，避免环境噪声瞬时峰值造成幻听
    const rmsThresh = 0.02
    if (rms > rmsThresh) {
      _listenVoiceFrames++
      if (_listenVoiceFrames >= 3) {
        // 持续有声 → 确认为"有人说话"
        stopVoiceSpeech()
        _listenSomeone = true
        _listenLastVoiceTs = now
        _listenSilentMs = 0
        if (!_listenGuard) { _listenGuard = setTimeout(() => forceEndListenSegment(), _listenMax) }
      }
    } else {
      _listenVoiceFrames = 0
      if (_listenSomeone) {
        // 静音时长达到阈值即切段识别。取值权衡：越短响应越快，但中文词间停顿久会被切成新段导致听不全。
        // 从 2000 → 1300 → 900(爸爸多次嫌慢，进一步加快响应)。
        if (now - _listenLastVoiceTs >= 900) forceEndListenSegment()
      }
    }
    _listenRaf = requestAnimationFrame(tick)
  }
  _listenRaf = requestAnimationFrame(tick)
}

function _stopListenDetector() {
  if (_listenRaf) { cancelAnimationFrame(_listenRaf); _listenRaf = 0 }
  if (_listenGuard) { clearTimeout(_listenGuard); _listenGuard = 0 }
  if (_listenCtx && _listenCtx.state !== 'closed') { try { _listenCtx.close() } catch (e) {} }
  _listenCtx = null
  _listenAnalyser = null
}

function forceEndListenSegment() {
  const now = Date.now()
  if (_listenGuard) { clearTimeout(_listenGuard); _listenGuard = 0 }
  if (_listenProcessing) { _listenSilentMs = 0; return }
  // 最小录音时长保护：本段不足 0.8s（刚起音/噪声误触发）不切段，继续录
  if (now - _listenSegStartTs < 800) { _listenSomeone = true; return }
  _listenSilentMs = 0
  if (!_listenMr || _listenMr.state !== 'recording' || !_listenMrChunks.length) { _listenSomeone = false; return }
  const chunks = _listenMrChunks.slice()
  _listenMrChunks = []
  if (_listenMr) { try { _listenMr.stop() } catch (e) {} }
  // 立即重开下一段（常驻）
  isRecording.value = false
  _listenSomeone = false
  _listenProcessing = true
  _processListenSegment(chunks).finally(() => {
    _listenProcessing = false
    if (voiceActive.value) restartListenSegment()
  })
}

function restartListenSegment() {
  if (!voiceActive.value) return
  _listenMrChunks = []
  try {
    _listenMr = new MediaRecorder(_listenStream, _listenMrMime ? { mimeType: _listenMrMime } : undefined)
  } catch (e) { _listenMr = new MediaRecorder(_listenStream) }
  _listenMr.ondataavailable = (e) => { if (e.data && e.data.size && e.target === _listenMr) _listenMrChunks.push(e.data) }
  _listenMr.onstop = () => {}
  _listenMr.start(250)
  isRecording.value = true
  _listenSomeone = false
  _listenSilentMs = 0
  _listenSegStartTs = Date.now()
  _listenLastVoiceTs = 0
  _listenVoiceFrames = 0
}

async function _processListenSegment(chunks) {
  if (!chunks.length) return
  const blob = new Blob(chunks, { type: chunks[0].type || 'audio/webm' })
  let pcm
  const ac = new (window.AudioContext || window.webkitAudioContext)()
  try {
    const buf = await blob.arrayBuffer()
    let audioBuffer
    try { audioBuffer = await ac.decodeAudioData(buf) } catch (de) { try { ac.close() } catch(e){} return }
    const srcRate = audioBuffer.sampleRate, srcLen = audioBuffer.length, targetRate = 16000
    const mono = new Float32Array(srcLen)
    if (audioBuffer.numberOfChannels === 1) mono.set(audioBuffer.getChannelData(0))
    else for (let c = 0; c < audioBuffer.numberOfChannels; c++) { const ch = audioBuffer.getChannelData(c); for (let i=0;i<srcLen;i++) mono[i]+=ch[i]/audioBuffer.numberOfChannels }
    // 高质量低通降采样 + 峰值归一化(替代原线性插值, 抑制混叠, 提升 STT 精度)
    const resampled = _lowpassResample(mono, srcRate, targetRate)
    let maxVol=0; for (let i=0;i<resampled.length;i++){const v=Math.abs(resampled[i]); if(v>maxVol)maxVol=v}
    if (maxVol < 0.02) return
    pcm = resampled
  } finally { try { ac.close() } catch(e){} }
  const wav = _encodeVoiceWav(pcm, 16000)
  const wavBlob = new Blob([wav], { type: 'audio/wav' })
  const b64 = await _blobToVoiceBase64(wavBlob)
  let text = ''
  try {
    const resp = await request.post('/agent/voice/transcribe', { audio_base64: b64, format: 'wav' })
    text = ((resp && resp.text) || '').trim()
  } catch (e) { console.warn('常驻STT失败:', e && e.message) }
  if (!text) return
  // 诊断：把 STT 识别出的文字用 Toast 显示，便于确认"听清了没/听成什么"
  try { ElMessage({ message: '听到: ' + text, type: 'info', duration: 2500 }) } catch (e) {}
  // 语音填表模式：已激活则直接投喂给当前表单
  if (formFillActive.value && _activeFormCtrl()) {
    await _processFormFill(text)
    return
  }
  // 未激活填表模式，但这句话本身就是"填写某字段" → 先自动打开指标卡片表单再填
  if (_wantFormFill(text)) {
    const opened = await ensureMetricCardForm()
    if (opened) { await _processFormFill(text); return }
  }
  // 语音 UI 动作：打开/点击某按钮 → 直接执行，不进聊天、不弹 AI
  if (await _processUiAction(text)) return
  // 通用"点XX按钮"：在当前页面 DOM 按文字模糊匹配可点击元素并真实点击
  if (await _clickButtonByVoice(text)) return
  // 建指标卡语音触发：进入"语音填指标卡"模式（打开指标页 + 弹窗 + 持续语音填充）
  if (_wantMetricCard(text)) {
    await startMetricCardForm()
    return
  }
  if (await tryVoiceNavigate(text)) return
  // 浮标语音永不录入 AI 聊天：尝试语音查询并播报结果；无法处理的引导去主脑
  await _voiceCommandFallback(text)
}

async function sendTextFromVoice(text) {
  if (loading.value) return
  loading.value = true
  scrollToBottom()
  try {
    const data = await request.post('/agent/chat/send', { session_id: activeSessionId.value, message: text })
    if (data.error) {
      messages.value.push({ role: 'assistant', content: data.error, message_type: 'error', created_at: new Date().toISOString() })
      return
    }
    if (data.session_id && data.session_id !== activeSessionId.value) {
      activeSessionId.value = data.session_id
      const s = sessions.value.find(s => s.id === data.session_id)
      if (!s) sessions.value.unshift({ id: data.session_id, title: text.slice(0, 64) })
      activeSession.value = { id: data.session_id, title: text.slice(0, 64) }
    }
    messages.value.push({ role: 'assistant', content: data.reply, created_at: new Date().toISOString() })
    scrollToBottom()
    if (data.reply) speakText(data.reply)
    if (data.pending_actions && data.pending_actions.length) pendingActions.value = data.pending_actions
  } catch (e) {
    messages.value.push({ role: 'assistant', content: '请求失败: ' + e.message, message_type: 'error', created_at: new Date().toISOString() })
  } finally { loading.value = false }
}

// ── 拖拽相关状态 ──
// widgetPos: null=未拖动（用默认右下角定位）；{left, top}=已拖动到指定坐标
const widgetPos = ref(null)
const isDragging = ref(false)
const dragInfo = ref({ startX: 0, startY: 0, originLeft: 0, originTop: 0, moved: false })
const DRAG_THRESHOLD = 5 // 位移阈值，超过则判定为拖动而非点击

// 计算根容器样式：未拖动时使用默认 right/bottom 定位，拖动后切换为 left/top 定位
const widgetStyle = computed(() => {
  if (!widgetPos.value) return {}
  return { left: widgetPos.value.left + 'px', top: widgetPos.value.top + 'px', right: 'auto', bottom: 'auto' }
})

// 面板样式：跟随触发按钮位置，保证打开时不会超出视口
const panelStyle = computed(() => {
  if (!widgetPos.value) return {}
  const p = widgetPos.value
  const PANEL_W = 400
  const PANEL_H = 580
  const TRIGGER_OFFSET = 88 // 触发按钮上方 88px 处显示面板
  let left = p.left
  let top = p.top - TRIGGER_OFFSET - PANEL_H + 52 // 让面板底部贴近触发按钮上方
  // 防溢出
  if (left + PANEL_W > window.innerWidth - 8) left = window.innerWidth - PANEL_W - 8
  if (left < 8) left = 8
  if (top < 8) top = 8
  if (top + PANEL_H > window.innerHeight - 8) top = window.innerHeight - PANEL_H - 8
  return { left: left + 'px', top: top + 'px', right: 'auto', bottom: 'auto' }
})

// 触发按钮鼠标按下：记录起始位置，挂载全局移动/抬起监听
function onTriggerMouseDown(e) {
  if (e.button !== 0) return // 只响应左键
  const rect = e.currentTarget.getBoundingClientRect()
  dragInfo.value = {
    startX: e.clientX,
    startY: e.clientY,
    originLeft: rect.left,
    originTop: rect.top,
    moved: false,
  }
  isDragging.value = true
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}

// 面板 header 鼠标按下：拖动整个组件（已打开时也可拖）
function onPanelHeaderMouseDown(e) {
  if (e.button !== 0) return
  // 点击 header 内的按钮不触发拖动
  if (e.target.closest('.panel-btn')) return
  const triggerEl = document.querySelector('.aiops-chat-widget .chat-trigger')
  const rect = triggerEl ? triggerEl.getBoundingClientRect() : e.currentTarget.getBoundingClientRect()
  dragInfo.value = {
    startX: e.clientX,
    startY: e.clientY,
    originLeft: rect.left,
    originTop: rect.top,
    moved: false,
  }
  isDragging.value = true
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}

function onMouseMove(e) {
  const dx = e.clientX - dragInfo.value.startX
  const dy = e.clientY - dragInfo.value.startY
  if (!dragInfo.value.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return
  dragInfo.value.moved = true
  let newLeft = dragInfo.value.originLeft + dx
  let newTop = dragInfo.value.originTop + dy
  // 限制在视口内（条形浮标约 110px，至少保留一半可见可点击）
  const HALF = 55
  newLeft = Math.max(-HALF, Math.min(window.innerWidth - HALF, newLeft))
  newTop = Math.max(-HALF, Math.min(window.innerHeight - HALF, newTop))
  widgetPos.value = { left: newLeft, top: newTop }
}

function onMouseUp() {
  isDragging.value = false
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
  // 持久化位置（只在真实拖动后保存，避免点击误存）
  if (dragInfo.value.moved && widgetPos.value) {
    try { localStorage.setItem(POS_STORAGE_KEY, JSON.stringify(widgetPos.value)) } catch (e) {}
  }
}

// 区分点击与拖动：拖动过则不触发 toggle
function onTriggerClick() {
  if (dragInfo.value.moved) return
  toggleOpen()
}

// 恢复上次位置
function restorePos() {
  try {
    const saved = localStorage.getItem(POS_STORAGE_KEY)
    if (saved) widgetPos.value = JSON.parse(saved)
  } catch (e) {}
}

onMounted(() => { 
  restorePos()
  initVoice()
  window.addEventListener('open-chat-session', handleOpenChatSession)
})
onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
  window.removeEventListener('open-chat-session', handleOpenChatSession)
  stopVoiceRecord(true)
  stopVoiceSpeech()
  stopAlwaysListen(true)
})

function handleOpenChatSession(e) {
  const { sessionId } = e.detail
  isOpen.value = true
  if (sessionId) {
    switchSession(sessionId)
  } else {
    restoreLastSession()
  }
}

function toggleOpen() {
  isOpen.value = !isOpen.value
  if (isOpen.value) {
    restoreLastSession()
  }
}

async function restoreLastSession() {
  if (restoring) return
  restoring = true
  try {
    await loadSessions()
    if (sessions.value.length > 0) {
      const lastId = localStorage.getItem(STORAGE_KEY)
      const targetId = lastId && sessions.value.some(s => s.id == lastId)
        ? parseInt(lastId) : sessions.value[0].id
      switchSession(targetId)
    }
  } finally {
    restoring = false
  }
}

watch(activeSessionId, (id) => {
  if (id) {
    localStorage.setItem(STORAGE_KEY, id)
  } else {
    localStorage.removeItem(STORAGE_KEY)
  }
})

function formatTime(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function riskTagType(level) {
  return { critical: 'danger', high: 'warning', medium: 'warning', low: 'success' }[level] || 'info'
}

function scrollToBottom() {
  // 双 nextTick 确保 DOM 完成渲染后再滚动
  nextTick(() => {
    nextTick(() => {
      if (messagesRef.value) {
        messagesRef.value.scrollTop = messagesRef.value.scrollHeight
      }
    })
  })
  // setTimeout 兜底：处理 Transition 动画期间高度未定型的场景
  setTimeout(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  }, 50)
  // 动画结束后再滚一次（slide-up 动画 0.3s）
  setTimeout(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  }, 350)
}

watch(messages, scrollToBottom, { deep: true })
// 面板打开时也滚动到底部
watch(isOpen, (val) => {
  if (val) {
    scrollToBottom()
  }
})

async function loadSessions() {
  loadingSessions.value = true
  try {
    const data = await request.get('/agent/sessions')
    sessions.value = data.sessions || []
  } catch (e) {
    console.error('load sessions:', e)
  } finally {
    loadingSessions.value = false
  }
}

async function loadMessages(sessionId) {
  try {
    const data = await request.get(`/agent/history/${sessionId}`)
    messages.value = data.messages || []
    if (data.pending_actions) {
      pendingActions.value = data.pending_actions
    }
    scrollToBottom()
  } catch (e) {
    console.error('load messages:', e)
  }
}

function switchSession(sessionId) {
  activeSessionId.value = sessionId
  const s = sessions.value.find(s => s.id === sessionId)
  activeSession.value = s || null
  showSessionList.value = false
  loadMessages(sessionId)
}

function newSession() {
  activeSessionId.value = null
  activeSession.value = null
  messages.value = []
  pendingActions.value = []
  inputMessage.value = ''
  showSessionList.value = false
}

async function sendMessage() {
  const message = inputMessage.value.trim()
  if (!message || loading.value) return
  _lastByVoice = false   // 默认文字提问不播报；语音路径会先置 true

  messages.value.push({
    role: 'user',
    content: message,
    created_at: new Date().toISOString(),
  })
  inputMessage.value = ''
  loading.value = true
  scrollToBottom()

  try {
    const data = await request.post('/agent/chat/send', {
      session_id: activeSessionId.value,
      message,
    })

    if (data.error) {
      messages.value.push({
        role: 'assistant',
        content: data.error,
        message_type: 'error',
        created_at: new Date().toISOString(),
      })
      return
    }

    if (data.session_id && data.session_id !== activeSessionId.value) {
      activeSessionId.value = data.session_id
      const s = sessions.value.find(s => s.id === data.session_id)
      if (!s) {
        sessions.value.unshift({ id: data.session_id, title: message.slice(0, 64) })
      }
      activeSession.value = { id: data.session_id, title: message.slice(0, 64) }
    }

    messages.value.push({
      role: 'assistant',
      content: data.reply,
      created_at: new Date().toISOString(),
    })
    scrollToBottom()
    // 语音指挥回复 → 云健 TTS 播报（仅当本次由语音发起时播报，避免文字提问也朗读）
    if (data.reply && _lastByVoice) speakText(data.reply)

    if (data.pending_actions && data.pending_actions.length > 0) {
      pendingActions.value = data.pending_actions
    }
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: '请求失败: ' + e.message,
      message_type: 'error',
      created_at: new Date().toISOString(),
    })
  } finally {
    loading.value = false
  }
}

function askQuestion(q) {
  inputMessage.value = q
  sendMessage()
}

// ═══════════════ 语音指挥：录音 → STT → 发送 + 云健 TTS 播报 + 导航跳转 ═══════════════
function toggleVoice() {
  if (isRecording.value) {
    stopVoiceRecord()
  } else {
    startVoiceRecord()
  }
}

async function startVoiceRecord() {
  if (speechSuppRec.value === false) {
    ElMessage.warning('当前浏览器不支持录音（请用 Chrome/Edge 通过 http://localhost 或 https 访问）')
    return
  }
  if (loading.value) return
  let stream
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    })
  } catch (e) {
    ElMessage.warning('无法获取麦克风：' + (e && e.message ? e.message : '请检查权限'))
    return
  }
  _voiceMrChunks = []
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']
  const mime = candidates.find(m => window.MediaRecorder.isTypeSupported(m)) || ''
  try {
    _voiceMr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
  } catch (e) {
    _voiceMr = new MediaRecorder(stream)
  }
  _voiceMr.ondataavailable = (e) => { if (e.data && e.data.size) _voiceMrChunks.push(e.data) }
  _voiceMr.onstop = () => {
    if (stream) stream.getTracks().forEach(t => t.stop())
    _voiceMr = null
    processVoiceAudio()
  }
  _voiceMr.start()
  isRecording.value = true
  // 15s 兜底
  if (_voiceMrTimeout) clearTimeout(_voiceMrTimeout)
  _voiceMrTimeout = setTimeout(() => { if (_voiceMr && _voiceMr.state === 'recording') { try { _voiceMr.stop() } catch (e) {} } }, 15000)
}

function stopVoiceRecord(silent) {
  if (_voiceMrTimeout) { clearTimeout(_voiceMrTimeout); _voiceMrTimeout = 0 }
  if (_voiceMr && _voiceMr.state === 'recording') {
    if (silent) { _voiceMr.stop(); return }   // 组件卸载时只停不处理
    try { _voiceMr.stop() } catch (e) {}
  }
  isRecording.value = false
}

async function processVoiceAudio() {
  if (!_voiceMrChunks.length) {
    isRecording.value = false
    return
  }
  const blob = new Blob(_voiceMrChunks, { type: _voiceMrChunks[0].type || 'audio/webm' })
  isRecording.value = false

  // webm/mp3 → 16k WAV（复用主脑核心链路）
  let pcm
  const ac = new (window.AudioContext || window.webkitAudioContext)()
  try {
    const buf = await blob.arrayBuffer()
    let audioBuffer
    try {
      audioBuffer = await ac.decodeAudioData(buf)
    } catch (de) {
      ElMessage.warning('音频解码失败，请重试')
      try { ac.close() } catch (e2) {}
      return
    }
    const srcRate = audioBuffer.sampleRate
    const srcLen = audioBuffer.length
    const targetRate = 16000
    // 混音单声道
    const mono = new Float32Array(srcLen)
    if (audioBuffer.numberOfChannels === 1) mono.set(audioBuffer.getChannelData(0))
    else for (let c = 0; c < audioBuffer.numberOfChannels; c++) {
      const ch = audioBuffer.getChannelData(c)
      for (let i = 0; i < srcLen; i++) mono[i] += ch[i] / audioBuffer.numberOfChannels
    }
    // 高质量低通降采样 + 峰值归一化(替代原线性插值, 抑制混叠, 提升 STT 精度)
    const resampled = _lowpassResample(mono, srcRate, targetRate)
    // 静音检测
    let maxVol = 0
    for (let i = 0; i < resampled.length; i++) { const v = Math.abs(resampled[i]); if (v > maxVol) maxVol = v }
    if (maxVol < 0.02) { ElMessage.info('没听到声音，请再说一次'); return }
    pcm = resampled
  } finally {
    try { ac.close() } catch (e3) {}
  }

  const wav = _encodeVoiceWav(pcm, 16000)
  const wavBlob = new Blob([wav], { type: 'audio/wav' })
  const b64 = await _blobToVoiceBase64(wavBlob)
  let text = ''
  try {
    const resp = await request.post('/agent/voice/transcribe', { audio_base64: b64, format: 'wav' })
    text = ((resp && resp.text) || '').trim()
  } catch (e) {
    ElMessage.error('语音识别失败：' + (e && e.message ? e.message : '请检查后端语音服务'))
  }
  if (!text) { ElMessage.info('未识别到语音，请再说一次'); return }
  // 诊断：显示 STT 识别出的原文
  try { ElMessage({ message: '听到: ' + text, type: 'info', duration: 2500 }) } catch (e) {}

  // 语音填表模式：投喂给当前表单
  if (formFillActive.value && _activeFormCtrl()) {
    await _processFormFill(text)
    return
  }
  // 未激活填表模式，但这句话本身就是"填写某字段" → 先自动打开指标卡片表单再填
  if (_wantFormFill(text)) {
    const opened = await ensureMetricCardForm()
    if (opened) { await _processFormFill(text); return }
  }
  // 语音 UI 动作：打开/点击某按钮 → 直接执行，不进聊天、不弹 AI
  if (await _processUiAction(text)) return
  // 通用"点XX按钮"：在当前页面 DOM 按文字模糊匹配可点击元素并真实点击
  if (await _clickButtonByVoice(text)) return
  // 语音建指标卡触发
  if (_wantMetricCard(text)) {
    await startMetricCardForm()
    return
  }

  // 语音指令 → 匹配导航意图则只跳转，不走聊天
  if (await tryVoiceNavigate(text)) return
  // 浮标语音永不录入 AI 聊天：尝试语音查询并播报结果；无法处理的引导去主脑
  await _voiceCommandFallback(text)
}

// ── 浮标语音兜底：纯指挥，绝不进 AI 聊天记录 ──
// 处理各类语音指令：查告警/查资产/查指标等 → 前端直接调接口，结果用 TTS 播报；
// 若无法识别为可执行指令 → 播报引导去主脑(AI 助手)处理。全程不写聊天记录、不开 AI 弹窗。
async function _voiceCommandFallback(text) {
  if (!text || !text.trim()) return
  // ① 语音查询：查告警/查某某/几个告警/资产/指标 → 前端调接口 + 语音播报结果
  let handled = false
  try { handled = await _voiceQuery(text) } catch (e) {}
  if (handled) return
  // ② 明确是要填表/建指标卡，但表单没打开 → 针对性提示，别只说"不支持"
  if (_wantFormFill(text) || _wantMetricCard(text)) {
    speakText('请先到指标监控页面，或直接说「建指标卡」打开表单后再填写')
    return
  }
  // ③ 无法处理的指令 → 引导去主脑，不录入、不弹窗
  speakText('浮标语音仅支持导航、点按钮和填表；深入问答请到主脑 AI 助手')
}

// ── 语音查询 + 语音播报：浮标语音直接调接口查数据，结果用 TTS 播报，不落聊天 ──
async function _voiceQuery(text) {
  const t = text || ''
  // 查告警
  if (/(告警|警告|有没有报警|几个报警|报警情况)/.test(t)) {
    try {
      const data = await request.get('/alerts/api/list', { params: { page: 1, per_page: 1 } })
      const s = (data && data.stats) || {}
      const trig = s.triggered || 0
      const ack = s.acknowledged || 0
      speakText(`当前有${trig}条触发告警，${ack}条已确认告警`)
    } catch (e) { speakText('查询告警失败') }
    return true
  }
  // 查资产/主机
  if (/(资产|主机|几台|多少台|服务器)/.test(t)) {
    try {
      const data = await request.get('/assets/api/list', { params: { page: 1, page_size: 1 } })
      const total = (data && data.total) || 0
      speakText(`当前共纳管${total}台资产`)
    } catch (e) { speakText('查询资产失败') }
    return true
  }
  return false
}

function _blobToVoiceBase64(blob) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader()
    fr.onload = () => resolve(String(fr.result).split(',')[1] || '')
    fr.onerror = reject
    fr.readAsDataURL(blob)
  })
}

function _encodeVoiceWav(samples, sampleRate) {
  const numChannels = 1, bitsPerSample = 16
  const byteRate = sampleRate * numChannels * bitsPerSample / 8
  const blockAlign = numChannels * bitsPerSample / 8
  const dataSize = samples.length * numChannels * bitsPerSample / 8
  const buf = new ArrayBuffer(44 + dataSize)
  const v = new DataView(buf)
  const s = (str, off) => { for (let i = 0; i < str.length; i++) v.setUint8(off + i, str.charCodeAt(i)) }
  s('RIFF', 0); v.setUint32(4, 36 + dataSize, true); s('WAVE', 8)
  s('fmt ', 12); v.setUint32(16, 16, true); v.setUint16(20, 1, true)
  v.setUint16(22, numChannels, true); v.setUint32(24, sampleRate, true)
  v.setUint32(28, byteRate, true); v.setUint16(32, blockAlign, true)
  v.setUint16(34, bitsPerSample, true); s('data', 36)
  v.setUint32(40, dataSize, true)
  let off = 44
  for (let i = 0; i < samples.length; i++) {
    const sv = Math.max(-1, Math.min(1, samples[i]))
    v.setInt16(off, sv < 0 ? sv * 0x8000 : sv * 0x7FFF, true)
    off += 2
  }
  return buf
}

// ── 高质量降采样(抗混叠加窗sinc低通) + 峰值归一化 ──
// 原线性插值重采样在 48k→16k 会混叠高频噪声进语音频带, 导致 STT 错字/漏字。
// 这里用 Kaiser 窗控 sinc 做低通抽取, 再按峰值归一化(提升低音量微麦的识别率)。
function _lowpassResample(src, srcRate, targetRate) {
  const outLen = Math.max(1, Math.round(src.length * targetRate / srcRate))
  const out = new Float32Array(outLen)
  const ratio = srcRate / targetRate
  // 截止频率(归一化到 Nyquist=1): 取目标采样率奈奎斯特的 0.95, 即 0.95*(1/ratio), 防混叠
  const cutoff = Math.min(0.45, 0.95 / ratio)   // 归一化频率(相对源采样率)
  const halfN = 24   // 单边 sinc 半窗长度(48点窗口, 过渡带更窄, CPU仍友好)
  const beta = (  8.5 )   // Kaiser beta(更高阻带) default 8.5
  // 预计算低通滤波器系数
  const filter = new Float32Array(halfN * 2 + 1)
  const kaiserI0 = (x) => { let s = 1, d = 0, t = 1; do { d += 2; t *= (x * x) / (d * d); s += t } while (t > 1e-9); return s }
  const i0b = kaiserI0(beta)
  let sum = 0
  for (let i = -halfN; i <= halfN; i++) {
    let h
    if (i === 0) h = cutoff
    else h = Math.sin(Math.PI * cutoff * i) / (Math.PI * i)
    const wpar = i / halfN
    h *= kaiserI0(beta * Math.sqrt(Math.max(0, 1 - wpar * wpar))) / i0b
    filter[i + halfN] = h
    sum += h
  }
  for (let i = 0; i < filter.length; i++) filter[i] /= sum   // 归一化增益1

  // 低通滤波 + 抽取
  for (let i = 0; i < outLen; i++) {
    const center = i * ratio
    const idx0 = Math.floor(center)
    let acc = 0
    for (let j = -halfN; j <= halfN; j++) {
      const si = idx0 + j
      if (si < 0 || si >= src.length) continue
      acc += src[si] * filter[j + halfN]
    }
    out[i] = acc
  }
  // 峰值归一化: 仅在峰值过低时才适度提增益(上限1.5x), 避免把本底噪声一起放大
  let peak = 0
  for (let i = 0; i < out.length; i++) { const a = Math.abs(out[i]); if (a > peak) peak = a }
  if (peak > 0 && peak < 0.4) {
    const g = Math.min(0.5 / peak, 1.5)
    for (let i = 0; i < out.length; i++) out[i] *= g
  }
  return out
}

function _toWavBase64(pcm, rate) {
  const wav = _encodeVoiceWav(pcm, rate)
  const wavBlob = new Blob([wav], { type: 'audio/wav' })
  return _blobToVoiceBase64(wavBlob)
}

// 语音指令 → 命中导航意图：先播报"收到"，稍后跳转；返回是否已导航
// 逻辑：① 快速本地 VOICE_NAV_RULES 命中即跳；② 未命中再调后端 /agent/voice/nav-intent
//      （后端做全量菜单同音模糊匹配 + LLM 兜底，解决"拓扑被识别成简谱/点头"类近音词）
async function tryVoiceNavigate(text) {
  if (!text || !text.trim()) return false
  // ① 本地快速规则（无网络延迟）
  for (const rule of VOICE_NAV_RULES) {
    if (rule.keys.some(k => text.includes(k))) {
      speakText('收到，正在打开' + (rule.label || rule.nav))
      if (window._navigateTo) {
        setTimeout(() => { try { window._navigateTo(rule.nav) } catch (e) {} }, 900)
        return true
      }
    }
  }
  // ② 后端导航意图识别（全量菜单模糊匹配 + LLM 兜底）
  try {
    const resp = await request.post('/agent/voice/nav-intent', { text })
    if (resp && resp.hit && resp.nav) {
      speakText('收到，正在打开' + (resp.label || resp.nav))
      if (window._navigateTo) {
        setTimeout(() => { try { window._navigateTo(resp.nav) } catch (e) {} }, 900)
        return true
      }
    }
  } catch (e) { console.warn('导航意图识别失败:', e && e.message) }
  return false
}

// ── 语音 UI 动作层：识别"打开/点击 XX按钮" → 直接在前端触发对应控件，不发给 AI ──
// 常用按钮预制映射（避免发给 AI 聊天 → 造成记录刷屏 / AI 无法点按钮只能回话）
// 命中即执行并 return true（不进聊天、不弹 AI 弹窗）
const VOICE_UI_RULES = [
  {
    keys: ['自定义卡片', '添加卡片', '新建卡片', '新增卡片', '添加一个卡片', '新建一个卡片'],
    // 打开"新增自定义指标卡片"弹窗（=点击 Metrics 页"+ 自定义卡片"按钮）
    run: async () => {
      if (!window._metricCardForm) {
        // 不在指标页 → 先跳转再等弹窗控制器就绪
        if (window._navigateTo) {
          try { window._navigateTo('metrics') } catch (e) {}
          speakText('正在打开指标监控')
        }
        const deadline = Date.now() + 5000
        while (Date.now() < deadline) {
          if (window._metricCardForm) break
          await new Promise(r => setTimeout(r, 300))
        }
      }
      const ctrl = window._metricCardForm
      if (!ctrl) {
        speakText('指标卡片表单暂不可用')
        return true
      }
      try { if (!ctrl.isOpen()) ctrl.open() } catch (e) {}
      speakText('已打开自定义卡片表单，可语音填写字段，说"保存"提交')
      formFillCtrl.value = ctrl
      formFillActive.value = true
      return true
    },
  },
]

// 判断这句话是否命中"打开/点击 XX按钮"的 UI 操作意图
function _wantUiAction(text) {
  if (!text) return false
  const t = text
  // 触发词：打开/点击/点/按/按下 + 目标；或 目标 + 按钮
  const hasClickVerb = /(打开|点击|点一下|点|按下|按一下|按|进入|跳到)/.test(t)
  if (!hasClickVerb) return false
  for (const rule of VOICE_UI_RULES) {
    if (rule.keys.some(k => t.includes(k))) return true
  }
  return false
}

async function _processUiAction(text) {
  const t = text || ''
  for (const rule of VOICE_UI_RULES) {
    if (rule.keys.some(k => t.includes(k))) {
      try { await rule.run() } catch (e) { console.warn('语音UI动作失败:', e) }
      return true
    }
  }
  return false
}

// ── 通用"点XX按钮"：在当前页面 DOM 按文字模糊匹配可点击元素并真实点击 ──
// 从语音里提取目标按钮名，遍历页面里的按钮/可点击元素，按文字(子串+字重叠)模糊匹配，
// 找到即 element.click()。适配任意页面的任意按钮（你说哪个就点哪个）。
function _extractButtonTarget(text) {
  let t = (text || '').trim()
  // 去掉引导/句尾词
  t = t.replace(/^(帮我|请你|把|给我|麻烦|我想|我要|请)/, '')
  t = t.replace(/(按钮|一下|去点|点一下|好了|就行|可以)/g, '')
  t = t.replace(/^(打开|点击|点|按下|按一下|按|进入|切到|跳转)/, '')
  t = t.replace(/^(打开|点击|点|按下|按一下|按|进入|切到|看|查看|打开看一下)/, '')
  t = t.trim()
  return t
}

function _textSim(a, b) {
  // 字符重叠相似度（容忍 STT 同音/漏字）
  if (!a || !b) return 0
  if (a.includes(b) || b.includes(a)) return 0.9
  const sa = new Set(a.split(''))
  const sb = new Set(b.split(''))
  let same = 0
  for (const ch of sa) if (sb.has(ch)) same++
  return same / Math.max(sa.size, sb.size, 1)
}

async function _clickButtonByVoice(text) {
  if (!text || !text.trim()) return false
  // 只有明确"点/点击/按钮/打开+元素"才走点按钮，避免和导航冲突（导航词无匹配元素自然跳过）
  if (!/(点|点击|按钮|打开)/.test(text)) return false
  const target = _extractButtonTarget(text)
  if (!target || target.length < 2) return false

  // 收集当前页面可点击元素（优先真按钮，再考虑带点击语义的元素）
  const selector = 'button, a[href], [role="button"], input[type="button"], input[type="submit"], summary, [class*="btn"]'
  let nodes = []
  try { nodes = Array.from(document.querySelectorAll(selector)) } catch (e) { nodes = [] }

  let best = null
  let bestScore = 0
  for (const el of nodes) {
    if (el.disabled) continue
    const label = (el.innerText || el.value || el.getAttribute('title') || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '').trim()
    if (!label) continue
    // 只用短文本（真正的按钮文字），太长的是容器跳过
    if (label.length > 30) continue
    let score = _textSim(target, label)
    // 同音容错：若 label 含目标词或目标词含 label 提升
    if (label.includes(target) || target.includes(label)) score = Math.max(score, 0.85)
    if (score > bestScore) { bestScore = score; best = el }
  }

  if (best && bestScore > 0.36) {
    try {
      best.click()
      const lbl = (best.innerText || best.value || best.title || '').trim() || target
      speakText(`好的，已点击${lbl.slice(0, 20)}`)
    } catch (e) { speakText('点按钮失败') }
    return true
  }
  return false
}

// ── 语音填表（借鉴 form-field-extractor：扫字段 → LLM 解析语音→字段值 → 填表 → 缺漏提示）──

// 判断这句话是不是"建/创建/新增 指标卡/卡片"类语音建卡指令
function _wantMetricCard(text) {
  if (!text) return false
  const t = text
  const build = /(建|创建|新增|做个|做一张|写个|添加|加)/
  // "建 + 指标卡/卡片/监控卡" 或直接 "指标卡"
  if ((/指标卡|监控卡|仪表盘卡|卡片/.test(t)) && (/建|创建|新增|加一|做/.test(t))) return true
  // "帮我建一张...的指标卡"
  if (build.test(t) && /指标|卡片|看板|仪表/.test(t)) return true
  return false
}

// 进入语音建指标卡模式：跳转到指标监控页 + 打开新增卡片弹窗 + 开启语音填表模式
async function startMetricCardForm() {
  speakText('好的，正在打开指标监控，为您创建自定义卡片')
  const ok = await ensureMetricCardForm()
  if (ok) speakText('您可以语音填写标题、分类、时间范围、PromQL、宽度、高度，说"保存"即可提交')
}

// 确保指标卡片表单已打开并进入填表模式；返回是否就绪
async function ensureMetricCardForm() {
  if (window._metricCardForm) {
    try { if (!window._metricCardForm.isOpen()) window._metricCardForm.open() } catch (e) {}
    formFillCtrl.value = window._metricCardForm
    formFillActive.value = true
    return true
  }
  // 不在指标页 → 先跳转再等弹窗控制器就绪
  if (window._navigateTo) {
    try { window._navigateTo('metrics') } catch (e) {}
  }
  const deadline = Date.now() + 6000
  while (Date.now() < deadline) {
    if (window._metricCardForm) break
    await new Promise(r => setTimeout(r, 300))
  }
  const ctrl = window._metricCardForm
  if (!ctrl) {
    speakText('指标卡片表单暂不可用，请手动打开')
    return false
  }
  try { if (!ctrl.isOpen()) ctrl.open() } catch (e) {}
  formFillCtrl.value = ctrl
  formFillActive.value = true
  return true
}

// 判断这句话是否"填写某字段"的填表指令（如"请把卡片标题填写为X / 标题是X / 分类选X / PromQL是X"）
// 对 STT 容错：只要能看出在填卡片字段(标题/分类/PromQL/宽度/高度/卡片/指标卡)且带内容即可触发
function _wantFormFill(text) {
  if (!text) return false
  const t = text
  // 明确的字段填充动词/结构
  const hasVerb = /(填写|填为|填|标题是|标题为|标题设|分类选|分类是|时间选择|时间范围|PromQL|宽度|高度|查询是|填写为|设置为|选为|:"|是)/.test(t)
  // 出现任一卡片字段名
  const hasField = /(标题|分类|时间|PromQL|宽度|高度|卡片|指标卡|查询|promql)/i.test(t)
  if (!hasField) return false
  // 有字段名 + (有填充动词 或 明显含具体值/数字/英文/中文内容)
  if (hasVerb) return true
  // 即使动词被 STT 吃掉，只要字段名后跟了实质内容（长度>字段名）也算填表意图
  const m = t.match(/(标题|分类|时间|PromQL|宽度|高度)/)
  if (m) {
    const after = t.slice(t.indexOf(m[0]) + m[0].length).trim()
    if (after.length >= 1) return true
  }
  return false
}

// 处理一条语音填表输入：调后端解析 → 填充表单 / 触发保存 / 取消
async function _processFormFill(text) {
  const ctrl = _activeFormCtrl()
  if (!ctrl) { formFillActive.value = false; return }
  // ① "AI 生成 PromQL" 意图：把后的自然语言描述交给 AI 生成器，而非当纯文本填 promql 框
  if (/(AI|生成|自动).{0,6}(PromQL|promql|查询|表达式|语句)/.test(text) && !/(填写为|填为|promql是)/.test(text)) {
    const desc = text.replace(/.*?(AI|生成|自动|帮.*(PromQL|promql|生成|查询)|生成.*(PromQL|promql))/, '').replace(/^(为|：|:|\s|，|,)+/, '').trim() || text
    if (ctrl.generatePromql) {
      speakText('好的，正在用 AI 生成 PromQL')
      const r = await ctrl.generatePromql(desc)
      if (r && r.ok) {
        speakText(`已生成 PromQL：${(r.promql || '').slice(0, 40)}，请核对后说"保存"`)
      } else {
        speakText((r && r.message) || 'AI 生成失败，请再说一次')
      }
      return
    }
  }
  let schema = []
  try { schema = ctrl.getSchema ? ctrl.getSchema() : [] } catch (e) {}
  let resp = null
  try {
    resp = await request.post('/agent/voice/form-fill', { text, fields: schema })
  } catch (e) {
    console.warn('语音填表解析失败:', e && e.message)
    speakText('没听清，请再说一次')
    return
  }
  if (!resp) { speakText('没听清，请再说一次'); return }
  const action = resp.action
  if (action === 'save') {
    const ok = ctrl.validate ? ctrl.validate() : true
    if (!ok) {
      speakText('还缺标题或 PromQL，请补充后再保存')
      return
    }
    const r = await ctrl.save()
    speakText(r && r.ok ? '卡片已保存' : ('保存失败，' + ((r && r.message) || '')))
    formFillActive.value = false
    formFillCtrl.value = null
    return
  }
  if (action === 'cancel') {
    try { if (ctrl.close) ctrl.close() } catch (e) {}
    speakText('好的，已取消')
    formFillActive.value = false
    formFillCtrl.value = null
    return
  }
  if (action === 'fill' && resp.values) {
    let applied = []
    try { applied = ctrl.fill ? ctrl.fill(resp.values) : [] } catch (e) { applied = [] }
    if (applied.length) {
      speakText(resp.feedback || '已填写')
    } else {
      speakText('没有识别到可填写的字段，请再说一次')
    }
    return
  }
  // none / error
  speakText('没听清，请再说一次')
}

// 云健 TTS 播报（复用后端 /agent/tts：有云 TTS 走云、否则回退 edge-tts 云健）
async function speakText(text) {
  if (!speechEnabled.value || !text || !text.trim()) return
  try {
    stopVoiceSpeech()
    // 音色: 默认 /agent/tts 走云分发(当前百度音色, 免重启立即可用);
    // 若要强制云健男声可加 &engine=edge-tts(需后端已重启含 executor 修复)
    const url = '/agent/tts?text=' + encodeURIComponent(text.slice(0, 300)) + '&voice=jarvis'
    const resp = await fetch(url, { credentials: 'include' })
    if (!resp.ok) return
    const blob = await resp.blob()
    const audioUrl = URL.createObjectURL(blob)
    const audio = new Audio(audioUrl)
    _voiceAudio.value = audio
    audio.onended = () => { URL.revokeObjectURL(audioUrl); _voiceAudio.value = null }
    audio.play().catch(() => {})
  } catch (e) { console.warn('TTS 播报失败:', e) }
}

function stopVoiceSpeech() {
  if (_voiceAudio.value) {
    try { _voiceAudio.value.pause(); _voiceAudio.value.src = '' } catch (e) {}
    _voiceAudio.value = null
  }
}

async function deleteSession(id) {
  try {
    await request.post(`/agent/session/${id}/delete`)
    sessions.value = sessions.value.filter(s => s.id !== id)
    if (activeSessionId.value === id) {
      activeSessionId.value = sessions.value.length ? sessions.value[0].id : null
      if (activeSessionId.value) switchSession(activeSessionId.value)
      else { messages.value = []; pendingActions.value = [] }
    }
  } catch (e) { console.error(e) }
}

async function confirmAction(id) {
  try {
    await request.post(`/agent/pending/${id}/confirm`)
    ElMessage.success('已确认')
    pendingActions.value = pendingActions.value.filter(a => a.id !== id)
  } catch (e) {
    ElMessage.error('操作失败: ' + e.message)
  }
}

async function cancelAction(id) {
  try {
    await request.post(`/agent/pending/${id}/cancel`)
    ElMessage.success('已取消')
    pendingActions.value = pendingActions.value.filter(a => a.id !== id)
  } catch (e) {
    ElMessage.error('操作失败: ' + e.message)
  }
}

defineExpose({ toggleOpen })
</script>

<style scoped>
.aiops-chat-widget {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 1000;
  font-family: var(--font-sans);
}

/* Trigger button */
.chat-trigger {
  width: 112px;
  height: 56px;
  border-radius: 18px;
  border: none;
  cursor: pointer;
  position: relative;
  user-select: none;
  color: #fff;
  display: flex;
  align-items: center;
  background:
    radial-gradient(circle at 30% 25%, rgba(255,255,255,.3), transparent 45%),
    linear-gradient(135deg, #7c3aed 0%, #4f46e5 50%, #2563eb 100%);
  box-shadow:
    0 6px 20px rgba(79,70,229,.42),
    0 2px 8px rgba(79,70,229,.28),
    inset 0 1px 0 rgba(255,255,255,.32),
    inset 0 -6px 14px rgba(30,27,75,.34);
  transition: transform .3s cubic-bezier(.34,1.56,.64,1), box-shadow .3s ease, background .3s ease;
}

/* 左格：语音开关 */
.trigger-voice {
  flex: 1;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  border-radius: 18px 0 0 18px;
  position: relative;
  cursor: pointer;
}
.trigger-voice:hover { background: rgba(255,255,255,.14); }
.trigger-voice.active { background: rgba(52,211,153,.22); }
.trigger-voice .tv-icon { font-size: 20px; line-height: 1; }
.trigger-voice .tv-icon.pulse { animation: voiceMicPulse 1.1s ease-in-out infinite; }
@keyframes voiceMicPulse { 50% { transform: scale(1.18); filter: drop-shadow(0 0 6px rgba(52,211,153,.9)); } }
.trigger-voice .tv-label { font-size: 9px; line-height: 1; opacity: .92; letter-spacing: .5px; }
.trigger-voice .tv-dot {
  position: absolute;
  top: 6px;
  right: 8px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #94a3b8;
  transition: background .2s, box-shadow .2s;
}
.trigger-voice .tv-dot.on { background: #34d399; box-shadow: 0 0 8px #34d399; animation: rigBlink 1.6s ease-in-out infinite; }

/* 分隔线 */
.trigger-divider {
  width: 1px;
  height: 30px;
  background: rgba(255,255,255,.35);
  flex-shrink: 0;
}

/* 右格：AI 助手 */
.trigger-assistant {
  flex: 1;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  border-radius: 0 18px 18px 0;
  cursor: pointer;
}
.trigger-assistant:hover { background: rgba(255,255,255,.14); }

/* 呼吸光环（未打开时） */
.chat-trigger::before {
  content: '';
  position: absolute;
  inset: -10px;
  border-radius: 22px;
  border: 2px solid rgba(129,140,248,.45);
  animation: rigPing 2.6s cubic-bezier(0, 0, .2, 1) infinite;
  pointer-events: none;
}
@keyframes rigPing {
  0%   { transform: scale(.9); opacity: .8; }
  70%, 100% { transform: scale(1.22); opacity: 0; }
}

/* 旋转变光线（打开时围绕整体转圈） */
.chat-trigger::after {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: 22px;
  background: conic-gradient(from 0deg,
      rgba(167,139,250,0) 0deg,
      rgba(167,139,250,.8) 90deg,
      rgba(255,255,255,0) 180deg,
      rgba(167,139,250,0) 270deg,
      rgba(167,139,250,.0) 360deg);
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 2px), #000 calc(100% - 1.5px));
  mask: radial-gradient(farthest-side, transparent calc(100% - 2px), #000 calc(100% - 1.5px));
  opacity: 0;
  pointer-events: none;
}
.chat-trigger.open::after { opacity: 1; animation: rigSpin 3.2s linear infinite; }
@keyframes rigSpin { to { transform: rotate(360deg); } }

/* AI 助手角标状态点（右格内） */
.chat-trigger .ai-status-dot {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #34d399;
  box-shadow: 0 0 6px #34d399;
  border: 1.5px solid #fff;
  animation: rigBlink 2.2s ease-in-out infinite;
  transition: background .3s ease, box-shadow .3s ease;
}
.chat-trigger .ai-status-dot.is-off { background: #94a3b8; box-shadow: none; animation: none; }
@keyframes rigBlink { 50% { opacity: .45; } }

.chat-trigger:hover {
  transform: scale(1.04) translateY(-2px);
  box-shadow:
    0 10px 32px rgba(124,58,237,.55),
    0 3px 12px rgba(79,70,229,.34),
    inset 0 1px 0 rgba(255,255,255,.4),
    inset 0 -6px 14px rgba(30,27,75,.3);
}
.chat-trigger:hover .trigger-icon svg { animation: rigFloat .9s ease-in-out infinite; }
@keyframes rigFloat { 50% { transform: translateY(-2px); } }

.chat-trigger.dragging {
  cursor: grabbing;
  transform: scale(.92) !important;
  transition: none !important;
  box-shadow:
    0 4px 16px rgba(79,70,229,.5),
    inset 0 1px 0 rgba(255,255,255,.34);
}
.chat-trigger.dragging::before { opacity: .2; animation: none; }

.chat-trigger.open {
  background:
    radial-gradient(circle at 30% 25%, rgba(255,255,255,.16), transparent 45%),
    linear-gradient(135deg, #475569, #334155);
  box-shadow:
    0 6px 20px rgba(15,23,42,.35),
    inset 0 1px 0 rgba(255,255,255,.16);
}
.chat-trigger.open:hover { transform: scale(1.02); }

.trigger-icon {
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: inherit;
  filter: drop-shadow(0 0 6px rgba(255,255,255,.35));
}
.trigger-icon svg { width: 24px; height: 24px; }
.trigger-icon svg .ai-node { opacity: .85; }

.close-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #e2e8f0 !important;
}

/* Chat panel */
.chat-panel {
  position: fixed;
  bottom: 88px;
  right: 24px;
  width: 400px;
  height: 580px;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 8px 40px rgba(0,0,0,0.12);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(148,163,184,0.12);
}

.slide-up-enter-active {
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.slide-up-leave-active {
  transition: all 0.2s ease;
}
.slide-up-enter-from {
  opacity: 0;
  transform: translateY(20px) scale(0.95);
}
.slide-up-leave-to {
  opacity: 0;
  transform: translateY(12px) scale(0.97);
}

/* Panel header */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid rgba(148,163,184,0.12);
  background: linear-gradient(180deg, rgba(248,251,255,0.98), rgba(243,247,255,0.94));
  flex-shrink: 0;
  cursor: move;
  user-select: none;
}

.panel-header-left {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.panel-title {
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
}

.panel-subtitle {
  font-size: 11px;
  color: #94a3b8;
}

.panel-header-actions {
  display: flex;
  gap: 4px;
}

.panel-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  color: #64748b;
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.panel-btn:hover {
  background: rgba(0,0,0,0.04);
  color: #1e293b;
}

/* Panel body */
.panel-body {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: #fff;
}

/* Session list */
.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.session-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 8px 12px;
  font-size: 13px;
  font-weight: 600;
  color: #1e293b;
  border-bottom: 1px solid rgba(148,163,184,0.1);
  margin-bottom: 4px;
}

.session-back-btn {
  border: none;
  background: transparent;
  color: #6366f1;
  font-size: 12px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
}

.session-back-btn:hover {
  background: rgba(99,102,241,0.08);
}

.session-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 13px;
  color: #475569;
  cursor: pointer;
  margin-bottom: 2px;
  transition: all 0.12s;
}

.session-item .session-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-del-btn {
  flex-shrink: 0; width: 18px; height: 18px; border: none; background: transparent;
  color: #94a3b8; font-size: 11px; cursor: pointer; border-radius: 4px; display: none;
  align-items: center; justify-content: center; margin-left: 4px; padding: 0;
}

.session-item:hover .session-del-btn { display: flex; }
.session-del-btn:hover { background: rgba(239,68,68,0.1); color: #ef4444; }

.session-item:hover {
  background: #f1f5f9;
}

.session-item.active {
  background: rgba(99,102,241,0.08);
  color: #6366f1;
  font-weight: 600;
}

.session-empty {
  text-align: center;
  color: #94a3b8;
  font-size: 13px;
  padding: 40px 16px;
}

/* Messages area */
.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  scroll-behavior: smooth;
}

.welcome-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  text-align: center;
  min-height: 100%;
}

.welcome-icon {
  width: 48px;
  height: 48px;
  background: linear-gradient(135deg, rgba(99,102,241,0.12), rgba(37,99,235,0.08));
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  margin-bottom: 12px;
}

.welcome-title {
  font-size: 16px;
  font-weight: 700;
  background: linear-gradient(135deg, #6366f1, #2563eb);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: 6px;
}

.welcome-desc {
  color: #64748b;
  font-size: 13px;
  margin-bottom: 20px;
  max-width: 340px;
  line-height: 1.5;
}

.suggested-questions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: center;
}

.suggested-btn {
  background: #f8fafc;
  border: 1px solid rgba(148,163,184,0.18);
  color: #64748b;
  padding: 7px 14px;
  border-radius: 16px;
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}

.suggested-btn:hover {
  background: rgba(99,102,241,0.08);
  border-color: #6366f1;
  color: #6366f1;
}

.msg-row {
  display: flex;
  margin-bottom: 14px;
  animation: fadeInUp 0.25s ease;
}

.msg-row.user { justify-content: flex-end; }
.msg-row.assistant { justify-content: flex-start; }

.msg-bubble {
  max-width: 85%;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.55;
}

.msg-bubble.user {
  background: linear-gradient(135deg, #6366f1, #4f46e5);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.msg-bubble.assistant {
  background: #f8fafc;
  border: 1px solid rgba(148,163,184,0.15);
  color: #1e293b;
  border-bottom-left-radius: 4px;
}

.msg-bubble.error-bubble {
  background: rgba(239,68,68,0.08);
  border-color: rgba(239,68,68,0.15);
  color: #ef4444;
}

.msg-content {
  white-space: pre-wrap;
  word-break: break-word;
}

.msg-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  font-size: 10px;
}

.msg-bubble.user .msg-meta { color: rgba(255,255,255,0.7); }
.msg-bubble.assistant .msg-meta { color: #94a3b8; }

.tool-badge { font-size: 11px; }

.streaming-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #94a3b8;
  font-size: 12px;
  padding: 6px 0;
}

/* Pending bar */
.pending-bar {
  border-top: 1px solid rgba(245,158,11,0.2);
  background: rgba(255,251,235,0.9);
  padding: 10px 14px;
  flex-shrink: 0;
  max-height: 120px;
  overflow-y: auto;
}

.pending-title {
  font-size: 12px;
  font-weight: 600;
  color: #f59e0b;
  margin-bottom: 6px;
}

.pending-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border: 1px solid rgba(245,158,11,0.15);
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 4px;
  gap: 8px;
}

.pending-item-left {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex: 1;
}

.pending-item-text {
  font-size: 12px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pending-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.pending-btn {
  border: none;
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 11px;
  cursor: pointer;
  font-family: inherit;
  font-weight: 500;
}

.pending-btn.confirm { background: #22c55e; color: #fff; }
.pending-btn.confirm:hover { background: #16a34a; }
.pending-btn.cancel { background: #e2e8f0; color: #475569; }
.pending-btn.cancel:hover { background: #cbd5e1; }

/* Input area */
.input-area {
  border-top: 1px solid rgba(148,163,184,0.12);
  padding: 10px 12px;
  background: #f8fafc;
  flex-shrink: 0;
}

.input-row {
  display: flex;
  gap: 6px;
}

.chat-input {
  flex: 1;
  border: 1px solid rgba(148,163,184,0.25);
  border-radius: 10px;
  padding: 9px 14px;
  font-size: 13px;
  outline: none;
  font-family: inherit;
  background: #fff;
  color: #1e293b;
  transition: border-color 0.2s;
}

.chat-input:focus {
  border-color: #6366f1;
  box-shadow: 0 0 0 2px rgba(99,102,241,0.12);
}

.chat-input::placeholder {
  color: #94a3b8;
}

.send-btn {
  background: linear-gradient(135deg, #6366f1, #4f46e5);
  color: #fff;
  border: none;
  border-radius: 10px;
  padding: 9px 18px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  white-space: nowrap;
  transition: all 0.15s;
}

.send-btn:hover {
  box-shadow: 0 2px 8px rgba(99,102,241,0.3);
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  box-shadow: none;
}

.history-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  border: none;
  background: transparent;
  color: #94a3b8;
  font-size: 11px;
  cursor: pointer;
  font-family: inherit;
  padding: 4px 6px;
  border-radius: 4px;
  transition: all 0.12s;
}

.history-btn:hover {
  background: rgba(0,0,0,0.03);
  color: #64748b;
}

/* ── 语音指挥 UI ── */
.voice-btn-wrap {
  display: flex;
  align-items: center;
  gap: 5px;
  position: relative;
}
.voice-btn {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  border: 1px solid rgba(148,163,184,0.28);
  background: #fff;
  color: #6366f1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
  transition: all 0.15s;
}
.voice-btn:hover { background: #eef2ff; }
.voice-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.voice-btn.recording {
  background: #ef4444;
  color: #fff;
  border-color: #ef4444;
  animation: voicePulse 1.1s ease-in-out infinite;
}
.voice-hint {
  position: absolute;
  bottom: -16px;
  left: 0;
  font-size: 10px;
  color: #ef4444;
  white-space: nowrap;
  background: rgba(239,68,68,0.1);
  padding: 1px 5px;
  border-radius: 4px;
}
@keyframes voicePulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(239,68,68,0.4); }
  50% { box-shadow: 0 0 0 6px rgba(239,68,68,0.12); }
}

.voice-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin-top: 2px;
}
.tts-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  border: none;
  background: transparent;
  color: #94a3b8;
  font-size: 11px;
  cursor: pointer;
  font-family: inherit;
  padding: 4px 6px;
  border-radius: 4px;
  transition: all 0.12s;
}
.tts-toggle:hover { background: rgba(0,0,0,0.03); color: #64748b; }
.tts-toggle.on { color: #6366f1; }

[data-theme='dark'] .input-area { background: #1e2430; }
[data-theme='dark'] .chat-input, [data-theme='dark'] .voice-btn { background: #0f1219; color: #e2e8f0; }
[data-theme='dark'] .voice-btn { color: #a5b4fc; }
[data-theme='dark'] .voice-btn:hover { background: #1a2030; }

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
