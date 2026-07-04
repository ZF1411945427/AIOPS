<template>
  <div class="aiops-chat-widget" :style="widgetStyle">
    <!-- Floating bubble trigger -->
    <button
      class="chat-trigger"
      :class="{ open: isOpen, dragging: isDragging }"
      @mousedown="onTriggerMouseDown"
      @click="onTriggerClick"
    >
      <span class="trigger-icon" v-if="!isOpen">🤖</span>
      <span class="trigger-icon close-icon" v-else>✕</span>
    </button>

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
              placeholder="输入问题..."
              :disabled="loading"
              @keyup.enter="sendMessage"
            />
            <button
              class="send-btn"
              :disabled="loading || !inputMessage.trim()"
              @click="sendMessage"
            >发送</button>
          </div>
          <button class="history-btn" @click="showSessionList = !showSessionList">
            <el-icon :size="14"><Clock /></el-icon>
            <span>历史会话</span>
          </button>
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
  // 限制在视口内（按钮 52px 大小，至少保留一半可见可点击）
  const HALF = 26
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

onMounted(() => { restorePos() })
onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
})

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
  return new Date(dateStr).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
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
  width: 52px;
  height: 52px;
  border-radius: 50%;
  border: none;
  background: linear-gradient(135deg, #6366f1, #2563eb);
  color: #fff;
  font-size: 24px;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(99,102,241,0.35);
  transition: all 0.25s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  user-select: none;
}

.chat-trigger:hover {
  transform: scale(1.08);
  box-shadow: 0 6px 24px rgba(99,102,241,0.45);
}

.chat-trigger.dragging {
  cursor: grabbing;
  transform: none !important;
  transition: none !important;
}

.chat-trigger.open {
  background: #475569;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}

.trigger-icon {
  line-height: 1;
}

.close-icon {
  font-size: 18px;
  font-weight: 300;
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

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
