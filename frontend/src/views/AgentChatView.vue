<template>
  <div class="workbench-page-shell">
    <div class="section-toolbar">
      <div class="toolbar-head">
        <span class="toolbar-title">AI 智能助手</span>
        <span class="toolbar-desc">智能运维对话，支持查询资源、分析告警、执行任务</span>
      </div>
    </div>

    <div class="chat-panel" style="flex:1">
      <div class="chat-sessions">
        <div class="sessions-header">
          <span>历史会话</span>
          <button class="new-session-btn" @click="newSession">＋</button>
        </div>
        <div class="sessions-list">
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
          <div v-if="!sessions.length && !loadingSessions" class="sessions-empty">暂无历史会话</div>
        </div>
      </div>

      <div class="chat-main">
        <div class="chat-messages" ref="messagesRef">
          <div v-if="!messages.length && !loading" class="welcome-area">
            <div class="welcome-icon">🤖</div>
            <div class="welcome-title">AI 智能助手</div>
            <div class="welcome-desc">{{ welcomeMessage }}</div>
            <div class="suggested-questions" v-if="suggestedQuestions.length">
              <button v-for="(q, idx) in suggestedQuestions" :key="idx" class="suggested-btn" @click="askQuestion(q)">{{ q }}</button>
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

        <div class="pending-bar" v-if="pendingActions.length">
          <div class="pending-title">⏳ 待确认操作</div>
          <div v-for="pa in pendingActions" :key="pa.id" class="pending-item">
            <div class="pending-item-left">
              <span class="pending-item-text">{{ pa.title }}</span>
              <el-tag :type="riskTagType(pa.risk_level)" size="small" effect="light">{{ pa.risk_level }}</el-tag>
            </div>
            <div class="pending-actions">
              <button class="pending-btn confirm" :disabled="confirmingId === pa.id" @click="confirmAction(pa.id)">
                <span v-if="confirmingId === pa.id" class="confirm-spinner"></span>
                {{ confirmingId === pa.id ? '执行中...' : '确认' }}
              </button>
              <button class="pending-btn cancel" :disabled="confirmingId === pa.id" @click="cancelAction(pa.id)">取消</button>
            </div>
          </div>
        </div>

        <div class="chat-input-area">
          <input v-model="inputMessage" class="chat-input" placeholder="输入问题..." :disabled="loading" @keyup.enter="sendMessage" />
          <button class="send-btn" :disabled="loading || !inputMessage.trim()" @click="sendMessage">发送</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import request from '@/api/request'

const STORAGE_KEY = 'aiops_last_session_id'

const messagesRef = ref(null)
const inputMessage = ref('')
const loading = ref(false)
const loadingSessions = ref(false)
const confirmingId = ref(null)
const sessions = ref([])
const messages = ref([])
const activeSessionId = ref(null)
const pendingActions = ref([])
const welcomeMessage = ref('你好，我可以帮你查询资源、分析告警、生成运维任务等。')
const suggestedQuestions = ref(['帮我查一下当前告警', '分析最近一次故障', '列出所有服务器资产', '查看 K8s 集群状态'])

function formatTime(dateStr) {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function riskTagType(level) {
  return { critical: 'danger', high: 'warning', medium: 'warning', low: 'success' }[level] || 'info'
}

function scrollToBottom(force = false) {
  const el = messagesRef.value
  if (!el) return
  el.scrollTop = el.scrollHeight
  if (force) {
    const retry = (delay) => {
      setTimeout(() => {
        if (messagesRef.value) messagesRef.value.scrollTop = messagesRef.value.scrollHeight
      }, delay)
    }
    requestAnimationFrame(() => retry(0))
    retry(50)
    retry(200)
  }
}



watch(activeSessionId, (id) => {
  if (id) localStorage.setItem(STORAGE_KEY, id)
  else localStorage.removeItem(STORAGE_KEY)
})

onMounted(async () => {
  await loadSessions()
  if (sessions.value.length > 0) {
    const lastId = localStorage.getItem(STORAGE_KEY)
    const targetId = lastId && sessions.value.some(s => s.id == lastId)
      ? parseInt(lastId) : sessions.value[0].id
    switchSession(targetId)
  }
})

async function loadSessions() {
  loadingSessions.value = true
  try {
    const data = await request.get('/agent/sessions')
    sessions.value = data.sessions || []
  } catch (e) { console.error(e) }
  finally { loadingSessions.value = false }
}

async function loadMessages(sessionId) {
  try {
    const data = await request.get(`/agent/history/${sessionId}`)
    messages.value = data.messages || []
    pendingActions.value = data.pending_actions || []
    await nextTick()
    scrollToBottom(true)
  } catch (e) { console.error(e) }
}

function switchSession(sessionId) {
  activeSessionId.value = sessionId
  loadMessages(sessionId)
}

function newSession() {
  activeSessionId.value = null
  messages.value = []
  pendingActions.value = []
  inputMessage.value = ''
}

async function sendMessage() {
  const message = inputMessage.value.trim()
  if (!message || loading.value) return
  messages.value.push({ role: 'user', content: message, created_at: new Date().toISOString() })
  await nextTick()
  scrollToBottom(true)
  inputMessage.value = ''
  loading.value = true
  try {
    const data = await request.post('/agent/chat/send', { session_id: activeSessionId.value, message })
    if (data.error) {
      messages.value.push({ role: 'assistant', content: data.error, message_type: 'error', created_at: new Date().toISOString() })
      await nextTick()
      scrollToBottom(true)
      return
    }
    if (data.session_id && data.session_id !== activeSessionId.value) {
      activeSessionId.value = data.session_id
      if (!sessions.value.find(s => s.id === data.session_id))
        sessions.value.unshift({ id: data.session_id, title: message.slice(0, 64) })
    }
    // 重新从后端加载消息
    if (activeSessionId.value) {
      await loadMessages(activeSessionId.value)
    } else {
      messages.value.push({ role: 'assistant', content: data.reply, created_at: new Date().toISOString() })
    }
    // 优先用 send 响应的 pending_actions（最可靠，同 db session 创建）
    // loadMessages 的 /agent/history 可能因 db session 隔离返回空 pending_actions
    if (data.pending_actions && data.pending_actions.length > 0)
      pendingActions.value = data.pending_actions
    await nextTick()
    scrollToBottom(true)
  } catch (e) {
    messages.value.push({ role: 'assistant', content: '请求失败: ' + e.message, message_type: 'error', created_at: new Date().toISOString() })
    await nextTick()
    scrollToBottom(true)
  } finally { loading.value = false }
}

function askQuestion(q) { inputMessage.value = q; sendMessage() }

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
  confirmingId.value = id
  try {
    const data = await request.post(`/agent/pending/${id}/confirm`)
    const result = data.result || {}
    // 异步模式：confirm 立即返回 executing，后台线程执行命令+LLM总结
    if (result.status === 'executing') {
      ElMessage.info('命令正在远程执行中，请稍候...')
      // 轮询状态直到终态（executed/failed/canceled）
      const pollResult = await pollPendingStatus(id)
      if (pollResult.status === 'executed') {
        ElMessage.success('执行成功')
      } else if (pollResult.status === 'failed') {
        ElMessage({ message: pollResult.result_message || '执行失败', type: 'error', duration: 6000 })
      }
      // 重新加载消息：后端已把 LLM 总结或兜底 message 存为 assistant 消息
      if (activeSessionId.value) {
        await loadMessages(activeSessionId.value)
      }
    } else {
      // 兼容同步模式（理论上不会走到，但兜底）
      const execResult = result.result || {}
      if (result.success) {
        ElMessage.success(execResult.message || '执行成功')
      } else {
        ElMessage({ message: execResult.message || '执行失败', type: 'error', duration: 6000 })
      }
      if (result.reply) {
        messages.value.push({ role: 'assistant', content: result.reply, created_at: new Date().toISOString() })
        await nextTick()
        scrollToBottom(true)
      }
      if (activeSessionId.value) {
        await loadMessages(activeSessionId.value)
      }
    }
    pendingActions.value = pendingActions.value.filter(a => a.id !== id)
  } catch (e) { ElMessage.error('操作失败: ' + e.message) }
  finally { confirmingId.value = null }
}

async function pollPendingStatus(id) {
  // 轮询 /pending/{id}/status，每 2s 一次，最多 60s（30 次）
  for (let i = 0; i < 30; i++) {
    await new Promise(resolve => setTimeout(resolve, 2000))
    try {
      const data = await request.get(`/agent/pending/${id}/status`)
      if (data.is_terminal) {
        return data
      }
    } catch (e) { /* 忽略单次轮询错误，继续 */ }
  }
  return { status: 'timeout', result_message: '执行超时，请稍后查看待确认列表' }
}

async function cancelAction(id) {
  try { await request.post(`/agent/pending/${id}/cancel`); ElMessage.success('已取消'); pendingActions.value = pendingActions.value.filter(a => a.id !== id) }
  catch (e) { ElMessage.error('操作失败: ' + e.message) }
}
</script>

<style scoped>
.session-item { display: flex; align-items: center; justify-content: space-between; }
.session-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.session-del-btn {
  flex-shrink: 0; width: 18px; height: 18px; border: none; background: transparent;
  color: #94a3b8; font-size: 11px; cursor: pointer; border-radius: 4px; display: none;
  align-items: center; justify-content: center; margin-left: 4px;
}
.session-item:hover .session-del-btn { display: flex; }
.session-del-btn:hover { background: rgba(239,68,68,0.1); color: #ef4444; }
.confirm-spinner {
  display: inline-block; width: 12px; height: 12px;
  border: 2px solid rgba(255,255,255,0.3); border-top-color: #fff;
  border-radius: 50%; animation: spin 0.6s linear infinite;
  vertical-align: middle; margin-right: 4px;
}
@keyframes spin { to { transform: rotate(360deg); } }
.pending-btn:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
