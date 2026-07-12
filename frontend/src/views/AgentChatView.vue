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

        <div class="pending-bar" v-if="activeSessionId && pendingActions.length">
          <div class="pending-title">⏳ 待确认操作</div>
          <template v-if="pendingActions.length">
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
          </template>
          <div v-else class="pending-empty">暂无待确认操作</div>
        </div>

        <div class="chat-input-area">
          <div class="context-toolbar">
            <el-popover trigger="click" width="360" placement="top-start">
              <template #reference>
                <button class="context-btn">🔔 关联告警</button>
              </template>
              <div class="link-search">
                <input v-model="alertSearch" placeholder="搜索告警 ID 或指标..." class="link-input" />
              </div>
              <div class="link-list">
                <div v-for="a in filteredAlerts" :key="a.id" class="link-item" @click="linkAlert(a.id)">
                  <span class="badge" :class="a.severity">{{ a.severity }}</span>
                  <span class="link-text">#{{ a.id }} {{ a.metric_name }}</span>
                </div>
                <div v-if="!filteredAlerts.length" class="link-empty">未找到告警</div>
              </div>
            </el-popover>
            <el-popover trigger="click" width="360" placement="top-start">
              <template #reference>
                <button class="context-btn">🏢 关联资产</button>
              </template>
              <div class="link-search">
                <input v-model="assetSearch" placeholder="搜索资产名称或 IP..." class="link-input" />
              </div>
              <div class="link-list">
                <div v-for="a in filteredAssets" :key="a.id" class="link-item" @click="linkAsset(a.id)">
                  <span class="badge server">🖥️</span>
                  <span class="link-text">{{ a.name }} ({{ a.ip || 'N/A' }})</span>
                </div>
                <div v-if="!filteredAssets.length" class="link-empty">未找到资产</div>
              </div>
            </el-popover>
          </div>
          <input v-model="inputMessage" class="chat-input" placeholder="输入问题..." :disabled="loading" @keyup.enter="sendMessage" />
          <button class="send-btn" :disabled="loading || !inputMessage.trim()" @click="sendMessage">发送</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
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

const alertSearch = ref('')
const assetSearch = ref('')
const alertsList = ref([])
const assetsList = ref([])

const filteredAlerts = computed(() => {
  if (!alertSearch.value) return alertsList.value.slice(0, 10)
  const q = alertSearch.value.toLowerCase()
  return alertsList.value.filter(a => 
    String(a.id).includes(q) || a.metric_name.toLowerCase().includes(q)
  ).slice(0, 10)
})

const filteredAssets = computed(() => {
  if (!assetSearch.value) return assetsList.value.slice(0, 10)
  const q = assetSearch.value.toLowerCase()
  return assetsList.value.filter(a => 
    (a.name && a.name.toLowerCase().includes(q)) || 
    (a.ip && a.ip.includes(q)) ||
    (a.ci_type && a.ci_type.toLowerCase().includes(q)) ||
    String(a.id).includes(q)
  ).slice(0, 10)
})

async function loadShortcuts() {
  try {
    const [alertData, assetData] = await Promise.all([
      request.get('/alerts/api/list', { params: { status: 'triggered', per_page: 50 } }),
      request.get('/assets/api/list', { params: { ci_type: '' } })
    ])
    alertsList.value = alertData.alerts || []
    assetsList.value = Array.isArray(assetData) ? assetData : (assetData.assets || [])
  } catch (e) {
    console.error('Failed to load shortcuts', e)
  }
}

async function ensureSession() {
  if (activeSessionId.value) return activeSessionId.value
  try {
    const data = await request.post('/agent/session/new')
    if (data.session_id) {
      activeSessionId.value = data.session_id
      await loadSessions()
      if (!sessions.value.find(s => s.id === data.session_id))
        sessions.value.unshift({ id: data.session_id, title: data.title || '新会话' })
      return data.session_id
    }
  } catch (e) { console.error('ensureSession error:', e) }
  return null
}

async function linkAlert(alertId) {
  const sid = await ensureSession()
  if (!sid) return ElMessage.warning('创建会话失败，请重试')
  try {
    await request.post(`/agent/session/${sid}/link-alert`, { alert_id: alertId })
    ElMessage.success('已关联告警')
    loadMessages(sid)
  } catch (e) {
    console.error('linkAlert error:', e)
    ElMessage.error('关联告警失败: ' + (e.message || '未知错误'))
  }
}

async function linkAsset(assetId) {
  const sid = await ensureSession()
  if (!sid) return ElMessage.warning('创建会话失败，请重试')
  try {
    await request.post(`/agent/session/${sid}/link-asset`, { asset_id: assetId })
    ElMessage.success('已关联资产')
    loadMessages(sid)
  } catch (e) {
    console.error('linkAsset error:', e)
    ElMessage.error('关联资产失败: ' + (e.message || '未知错误'))
  }
}

function formatTime(dateStr) {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function riskTagType(level) {
  return { critical: 'danger', high: 'warning', medium: 'warning', low: 'success' }[level] || 'info'
}


async function loadPendingActions(sessionId) {
  if (!sessionId) { pendingActions.value = []; return }
  try {
    const data = await request.get('/agent/api/pending')
    const all = data.actions || []
    pendingActions.value = all.filter(a => a.session_id === sessionId || !a.session_id)
  } catch (e) { pendingActions.value = [] }
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
  await loadShortcuts()
  // 从外部跳转传入的 session_id（如告警中心→智能助手）
  const pendingId = window._pendingAgentSessionId
  if (pendingId) {
    window._pendingAgentSessionId = null
    switchSession(pendingId)
  } else if (sessions.value.length > 0) {
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
    await nextTick()
    scrollToBottom(true)
  } catch (e) { console.error(e) }
}

function switchSession(sessionId) {
  activeSessionId.value = sessionId
  loadMessages(sessionId)
  loadPendingActions(sessionId)
}

function newSession() {
  activeSessionId.value = null
  messages.value = []
  pendingActions.value = []
  pendingStatusFilter.value = 'pending'
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
    // 重新加载消息和待确认操作
    if (activeSessionId.value) {
      await loadMessages(activeSessionId.value)
      await loadPendingActions(activeSessionId.value)
    } else {
      messages.value.push({ role: 'assistant', content: data.reply, created_at: new Date().toISOString() })
    }
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
    if (result.status === 'completed') {
      ElMessage.success('执行完成')
      if (activeSessionId.value) {
        await loadMessages(activeSessionId.value)
        await loadPendingActions(activeSessionId.value)
      }
    } else if (result.status === 'executing') {
      ElMessage.info('命令正在远程执行中，请稍候...')
      const history = await pollSessionForNewMessage(activeSessionId.value, messages.value.length)
      if (history) {
        messages.value = history.messages || []
      }
      await loadPendingActions(activeSessionId.value)
    } else {
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
        await loadPendingActions(activeSessionId.value)
      }
    }
  } catch (e) { ElMessage.error('操作失败: ' + e.message) }
  finally { confirmingId.value = null }
}

async function pollSessionForNewMessage(sessionId, beforeCount) {
  for (let i = 0; i < 60; i++) {
    await new Promise(resolve => setTimeout(resolve, 2000))
    try {
      const data = await request.get(`/agent/history/${sessionId}`)
      const msgs = data.messages || []
      if (msgs.length > beforeCount) {
        await nextTick()
        scrollToBottom(true)
        return data
      }
    } catch (e) { /* 忽略单次轮询错误 */ }
  }
  ElMessage.warning('执行结果加载超时，请稍后手动刷新')
  return null
}

async function cancelAction(id) {
  try {
    await request.post(`/agent/pending/${id}/cancel`)
    ElMessage.success('已取消')
    if (activeSessionId.value) await loadPendingActions(activeSessionId.value)
  } catch (e) { ElMessage.error('操作失败: ' + e.message) }
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
.context-toolbar {
  display: flex; gap: 6px; padding: 6px 8px;
}
.context-btn {
  padding: 5px 12px; background: #f1f5f9; border: 1px solid transparent; border-radius: 16px;
  font-size: 0.78rem; color: #6366f1; cursor: pointer; transition: all 0.2s;
  font-weight: 500; white-space: nowrap;
}
.context-btn:hover { background: #e0e7ff; border-color: #c7d2fe; }
.link-search { margin-bottom: 8px; }
.link-input {
  width: 100%; padding: 6px 10px; border: 1px solid #e2e8f0; border-radius: 6px;
  font-size: 0.82rem; outline: none; box-sizing: border-box;
}
.link-input:focus { border-color: #6366f1; }
.link-list { max-height: 200px; overflow-y: auto; }
.link-item {
  display: flex; align-items: center; gap: 8px; padding: 8px; border-radius: 6px;
  cursor: pointer; transition: background 0.15s; font-size: 0.82rem; color: #1e293b;
}
.link-item:hover { background: #f1f5f9; }
.link-text { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.link-empty { padding: 12px; text-align: center; color: #94a3b8; font-size: 0.8rem; }
</style>
