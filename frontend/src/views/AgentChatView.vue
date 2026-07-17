<template>
  <div class="agent-layout">
    <!-- 顶部全局操作栏 -->
    <div class="agent-topbar">
      <div class="topbar-left">
        <span class="topbar-brand">🤖 AIOps 智能助手</span>
        <span class="topbar-mode-hint">{{ currentModeLabel === 'Agent' ? 'Agent 模式 · 全功能工具' : 'Chat 模式 · 纯对话' }}</span>
      </div>
      <div class="topbar-right">
        <button class="topbar-btn" title="刷新" @click="refreshAll">🔄</button>
      </div>
    </div>

    <div class="agent-body">
      <!-- 左侧：会话管理栏 -->
      <div class="agent-sidebar">
        <div class="sidebar-search">
          <input v-model="searchQuery" class="sidebar-search-input" placeholder="搜索标题或 IP..." />
          <button class="sidebar-new-btn" title="新建会话" @click="newSession">＋</button>
        </div>
        <div class="sidebar-list">
          <div
            v-for="s in filteredSessions"
            :key="s.id"
            class="sidebar-item"
            :class="{ active: activeSessionId === s.id }"
            @click="switchSession(s.id)"
          >
            <div class="sidebar-item-title">
              <input
                v-if="renamingId === s.id"
                v-model="s._editingTitle"
                class="sidebar-rename-input"
                @blur="confirmRename(s)"
                @keyup.enter="confirmRename(s)"
                @click.stop
                autofocus
              />
              <span v-else class="sidebar-title-text" @dblclick.stop="startRename(s)">{{ s.title }}</span>
            </div>
            <span class="sidebar-item-date">{{ formatDate(s.created_at) }}</span>
            <button class="sidebar-del-btn" title="删除会话" @click.stop="deleteSession(s.id)">✕</button>
          </div>
          <div v-if="!filteredSessions.length && !loadingSessions" class="sidebar-empty">暂无会话</div>
        </div>
      </div>

      <!-- 中间：会话主体 -->
      <div class="agent-main">
        <!-- 会话头部 -->
        <div class="agent-chat-header" v-if="activeSessionId">
          <div class="chat-header-left">
            <input
              v-if="renamingId === activeSessionId"
              v-model="sessionTitleEdit"
              class="chat-header-rename"
              @blur="confirmRename(activeSessionObj)"
              @keyup.enter="confirmRename(activeSessionObj)"
              autofocus
            />
            <span v-else class="chat-header-title" @dblclick="startRenameHeader">{{ activeSessionTitle }}</span>
            <span class="chat-header-mode-tag">{{ currentModeLabel }}</span>
            <span v-if="isAgentUrgent" class="chat-header-urgent">紧急</span>
          </div>
          <div class="chat-header-right">
            <label class="model-label">模型：</label>
            <select v-model="currentProviderId" class="model-select" @change="onProviderChange">
              <option v-for="p in providerList" :key="p.id" :value="p.id">
                {{ p.name }} ({{ p.default_model || '' }})
              </option>
            </select>
          </div>
        </div>

        <!-- 消息列表 -->
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
            <div v-if="m.role === 'assistant' && m._steps && m._steps.length" class="msg-task-card-wrap">
              <TaskProgressCard :steps="m._steps" :task="m._task" :default-collapsed="false" />
            </div>
            <div class="msg-bubble" :class="[m.role, m.message_type === 'error' ? 'error-bubble' : '']">
              <div class="msg-content" v-html="renderContent(m.content)"></div>
              <div class="msg-meta">
                <span>{{ formatTime(m.created_at) }}</span>
                <span v-if="m.tool_calls && m.tool_calls !== '[]'" class="tool-badge">🔧</span>
              </div>
            </div>
          </div>

          <!-- 流式实时任务卡片 -->
          <div v-if="loading && streamingSteps.length" class="msg-row assistant">
            <div class="msg-task-card-wrap">
              <TaskProgressCard :steps="streamingSteps" :task="streamingTask" :default-collapsed="false" />
            </div>
          </div>

          <!-- 流式打字机效果 -->
          <div v-if="loading && typewriterText && !streamingSteps.length" class="msg-row assistant">
            <div class="msg-bubble assistant">
              <div class="msg-content" v-html="typewriterText"></div>
              <span class="typewriter-cursor">▊</span>
            </div>
          </div>

          <div v-if="loading" class="streaming-indicator">
            <span class="streaming-spinner"></span>
            <span>{{ streamingStatus || 'AI 正在思考...' }}</span>
          </div>
        </div>

        <!-- 待确认操作栏 -->
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

        <!-- 底部输入栏 -->
        <div class="agent-input-area">
          <!-- 设备标签栏 -->
          <div class="device-bar" v-if="activeSessionId && currentMode === 'agent'">
            <div class="device-tags">
              <span v-for="d in linkedDevices" :key="d.id" class="device-tag">
                {{ d.ip || d.name }}
                <span class="device-tag-sep">·</span>
                {{ d.name }}
                <button class="device-tag-close" @click="unlinkDevice(d.id)">×</button>
              </span>
              <el-popover trigger="click" width="340" placement="top-start">
                <template #reference>
                  <button class="device-add-btn">+ 添加设备</button>
                </template>
                <div class="device-add-popover">
                  <input v-model="assetSearch" placeholder="搜索资产名称或 IP..." class="link-input" />
                  <div class="link-list">
                    <div v-for="a in filteredAssets" :key="a.id" class="link-item" @click="linkDevice(a.id)">
                      <span class="badge server">🖥️</span>
                      <span class="link-text">{{ a.name }} ({{ a.ip || 'N/A' }})</span>
                    </div>
                    <div v-if="!filteredAssets.length" class="link-empty">未找到资产</div>
                  </div>
                </div>
              </el-popover>
            </div>
          </div>

          <!-- 关联上下文快捷按钮 -->
          <div class="context-toolbar" v-if="currentMode === 'agent'">
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
            <el-popover trigger="click" width="300" placement="top-start">
              <template #reference>
                <button class="context-btn">📊 关联分析</button>
              </template>
              <div class="correlation-popover">
                <div class="correlation-field">
                  <label>时间范围</label>
                  <div class="correlation-radio-group">
                    <button v-for="opt in correlationHourOptions" :key="opt.value"
                      class="correlation-radio-btn" :class="{ active: correlationHours === opt.value }"
                      @click="correlationHours = opt.value">{{ opt.label }}</button>
                  </div>
                </div>
                <div class="correlation-field">
                  <label>服务名（可选）</label>
                  <input v-model="correlationService" placeholder="模糊匹配服务名" class="link-input" />
                </div>
                <button class="correlation-run-btn" :disabled="correlationRunning" @click.stop="runCorrelationAnalysis">
                  <span v-if="correlationRunning" class="correlation-spinner"></span>
                  {{ correlationRunning ? '分析中...' : '🚀 开始分析' }}
                </button>
              </div>
            </el-popover>
          </div>

          <div class="input-row">
            <div class="input-wrap">
              <textarea
                v-model="inputMessage"
                class="chat-textarea"
                placeholder="输入消息... (Ctrl+Enter发送, Enter换行; @选择设备)"
                :disabled="loading"
                @keydown="onInputKeydown"
                rows="1"
                ref="textareaRef"
              ></textarea>
            </div>
            <div class="input-actions">
              <div class="mode-tabs">
                <button class="mode-tab" :class="{ active: currentMode === 'chat' }" @click="switchMode('chat')">Chat</button>
                <button class="mode-tab" :class="{ active: currentMode === 'agent' }" @click="switchMode('agent')">Agent</button>
              </div>
              <button v-if="!loading" class="send-btn" :disabled="!inputMessage.trim()" @click="sendMessage">发送</button>
              <button v-else class="stop-btn" @click="stopGenerating">■ 中止</button>
            </div>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'
import { useAgentSSE } from '@/composables/useAgentSSE'
import TaskProgressCard from '@/components/agent/TaskProgressCard.vue'

const STORAGE_KEY = 'aiops_last_session_id'

function parseHistorySteps(toolCallsStr) {
  if (!toolCallsStr || toolCallsStr === '[]') return []
  try {
    const arr = JSON.parse(toolCallsStr)
    return arr.map((item, i) => item.step || {
      step_id: `hist_${i}_${item.tool_name}`,
      tool_name: item.tool_name,
      title: item.tool_name,
      status: 'success',
      summary: (typeof item.result === 'string' ? item.result : JSON.stringify(item.result)).slice(0, 200),
      raw_output: JSON.stringify(item.result, null, 2),
      expanded: false,
    })
  } catch (e) { return [] }
}

const messagesRef = ref(null)
const textareaRef = ref(null)
const inputMessage = ref('')
const loading = ref(false)
const loadingSessions = ref(false)
const confirmingId = ref(null)
const sessions = ref([])
const messages = ref([])
const activeSessionId = ref(null)
const pendingAutoSend = ref(false)
const skipNextUserPush = ref(false)
const pendingActions = ref([])
const welcomeMessage = ref('你好，我可以帮你查询资源、分析告警、生成运维任务等。')
const suggestedQuestions = ref(['帮我查一下当前告警', '分析最近一次故障', '列出所有服务器资产', '查看 K8s 集群状态'])
const searchQuery = ref('')
const renamingId = ref(null)
const sessionTitleEdit = ref('')
const providerList = ref([])
const currentProviderId = ref(null)
const linkedDevices = ref([])
const currentMode = ref('agent')
const typewriterText = ref('')
const typewriterTimer = ref(null)
const typewriterBuffer = ref('')

const alertSearch = ref('')
const assetSearch = ref('')
const alertsList = ref([])
const assetsList = ref([])
const correlationHours = ref(1)
const correlationService = ref('')
const correlationRunning = ref(false)
const correlationHourOptions = [
  { label: '1小时', value: 1 },
  { label: '6小时', value: 6 },
  { label: '24小时', value: 24 },
]

const filteredSessions = computed(() => {
  if (!searchQuery.value) return sessions.value
  const q = searchQuery.value.toLowerCase()
  return sessions.value.filter(s => (s.title || '').toLowerCase().includes(q))
})

const activeSessionTitle = computed(() => {
  const s = sessions.value.find(s => s.id === activeSessionId.value)
  return s ? (s.title || '新会话') : '未命名会话'
})

const activeSessionObj = computed(() => {
  return sessions.value.find(s => s.id === activeSessionId.value)
})

const currentModeLabel = computed(() => currentMode.value === 'chat' ? 'Chat' : 'Agent')
const isAgentUrgent = computed(() => streamingTask.value?.urgency === 'urgent' && currentMode.value === 'agent')

const filteredAlerts = computed(() => {
  if (!alertSearch.value) return alertsList.value.slice(0, 10)
  const q = alertSearch.value.toLowerCase()
  return alertsList.value.filter(a => String(a.id).includes(q) || a.metric_name.toLowerCase().includes(q)).slice(0, 10)
})
const filteredAssets = computed(() => {
  if (!assetSearch.value) return assetsList.value.slice(0, 10)
  const q = assetSearch.value.toLowerCase()
  return assetsList.value.filter(a => (a.name && a.name.toLowerCase().includes(q)) || (a.ip && a.ip.includes(q)) || (a.ci_type && a.ci_type.toLowerCase().includes(q)) || String(a.id).includes(q)).slice(0, 10)
})

const {
  connect: startSSE,
  disconnect: stopSSE,
  streamingContent,
  streamingStatus,
  streamingDone,
  streamingError,
  pendingActions: ssePendingActions,
  streamingSteps,
  streamingTask,
  streamingReport,
} = useAgentSSE()

watch(ssePendingActions, (newActions) => {
  if (newActions.length) pendingActions.value = [...newActions]
}, { deep: true })

watch(messages, (newMessages) => {
  if (pendingAutoSend.value && newMessages.length > 0) {
    const last = newMessages[newMessages.length - 1]
    if (last.role === 'user') {
      pendingAutoSend.value = false
      skipNextUserPush.value = true
      inputMessage.value = last.content
      nextTick(() => sendMessage())
    }
  }
})

watch(activeSessionId, (id) => {
  if (id) localStorage.setItem(STORAGE_KEY, id)
  else localStorage.removeItem(STORAGE_KEY)
})

watch(streamingContent, (val) => {
  if (val && !streamingSteps.value.length) startTypewriter(val)
})

function startTypewriter(fullText) {
  if (typewriterTimer.value) clearInterval(typewriterTimer.value)
  typewriterBuffer.value = fullText
  typewriterText.value = ''
  let idx = 0
  typewriterTimer.value = setInterval(() => {
    if (idx >= typewriterBuffer.value.length) {
      clearInterval(typewriterTimer.value)
      typewriterTimer.value = null
      typewriterText.value = typewriterBuffer.value
      return
    }
    const chunk = Math.min(3, typewriterBuffer.value.length - idx)
    typewriterText.value += typewriterBuffer.value.substring(idx, idx + chunk)
    idx += chunk
    scrollToBottom()
  }, 20)
}

function stopTypewriter() {
  if (typewriterTimer.value) { clearInterval(typewriterTimer.value); typewriterTimer.value = null }
  typewriterText.value = typewriterBuffer.value || ''
}

function renderContent(text) {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')
}

async function loadSessions() {
  loadingSessions.value = true
  try {
    const data = await request.get('/agent/sessions')
    sessions.value = (data.sessions || []).map(s => ({ ...s, _editingTitle: s.title, _mode: 'agent' }))
  } catch (e) { console.error(e) }
  finally { loadingSessions.value = false }
}

async function loadMessages(sessionId) {
  try {
    const data = await request.get(`/agent/history/${sessionId}`)
    const msgs = data.messages || []
    msgs.forEach(m => {
      if (m.role === 'assistant') {
        m._steps = parseHistorySteps(m.tool_calls)
        m._task = m._steps.length ? { title: '运维任务进度', urgency: 'normal', totalSteps: m._steps.length, completedSteps: m._steps.filter(s => s.status !== 'running').length, percent: 100 } : null
      }
    })
    messages.value = msgs
    await nextTick()
    scrollToBottom(true)
  } catch (e) { console.error(e) }
}

function switchSession(sessionId) {
  activeSessionId.value = sessionId
  renamingId.value = null
  stopTypewriter()
  loadMessages(sessionId)
  loadPendingActions(sessionId)
  loadDevices(sessionId)
  const s = sessions.value.find(x => x.id === sessionId)
  if (s && s._mode) currentMode.value = s._mode
}

function newSession() {
  activeSessionId.value = null; messages.value = []; pendingActions.value = []; inputMessage.value = ''
  searchQuery.value = ''; linkedDevices.value = []; renamingId.value = null
  stopTypewriter()
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
  } catch (e) { console.error(e) }
  return null
}

async function deleteSession(id) {
  try {
    await request.post(`/agent/session/${id}/delete`)
    sessions.value = sessions.value.filter(s => s.id !== id)
    if (activeSessionId.value === id) {
      activeSessionId.value = sessions.value.length ? sessions.value[0].id : null
      if (activeSessionId.value) switchSession(activeSessionId.value)
      else { messages.value = []; pendingActions.value = []; linkedDevices.value = [] }
    }
  } catch (e) { console.error(e) }
}

function startRename(s) {
  renamingId.value = s.id; s._editingTitle = s.title || '新会话'
}

function startRenameHeader() {
  if (activeSessionObj.value) { renamingId.value = activeSessionId.value; sessionTitleEdit.value = activeSessionObj.value.title || '新会话' }
}

async function confirmRename(s) {
  if (!s || !s.id) return
  const newTitle = (s._editingTitle || '').trim() || (s.title || '')
  try {
    const data = await request.post(`/agent/session/${s.id}/rename`, { title: newTitle })
    s.title = data.title || newTitle
  } catch (e) { console.error(e) }
  renamingId.value = null
}

async function loadProviders() {
  try {
    const data = await request.get('/agent/providers')
    providerList.value = data.providers || []
    if (providerList.value.length && !currentProviderId.value) currentProviderId.value = providerList.value[0].id
  } catch (e) { console.error(e) }
}

async function onProviderChange() {
  if (!activeSessionId.value || !currentProviderId.value) return
  try {
    await request.post(`/agent/session/${activeSessionId.value}/set-provider`, { provider_id: currentProviderId.value })
    ElMessage.success('模型已切换')
  } catch (e) { console.error(e) }
}

async function switchMode(mode) {
  if (loading.value) return
  currentMode.value = mode
  if (activeSessionId.value) {
    try {
      await request.post(`/agent/session/${activeSessionId.value}/set-mode`, { mode })
      const s = sessions.value.find(x => x.id === activeSessionId.value)
      if (s) s._mode = mode
    } catch (e) { console.error(e) }
  }
}

async function loadDevices(sessionId) {
  if (!sessionId) { linkedDevices.value = []; return }
  try {
    const data = await request.get(`/agent/session/${sessionId}/devices`)
    linkedDevices.value = data.devices || []
  } catch (e) { linkedDevices.value = [] }
}

async function linkDevice(assetId) {
  const sid = activeSessionId.value || await ensureSession()
  if (!sid) return
  try {
    await request.post(`/agent/session/${sid}/link-device`, { asset_id: assetId })
    ElMessage.success('设备已绑定')
    await loadDevices(sid)
  } catch (e) { ElMessage.error('绑定失败: ' + (e.message || '')) }
}

async function unlinkDevice(assetId) {
  if (!activeSessionId.value) return
  try {
    await request.post(`/agent/session/${activeSessionId.value}/unlink-device`, { asset_id: assetId })
    await loadDevices(activeSessionId.value)
  } catch (e) { ElMessage.error('解绑失败: ' + (e.message || '')) }
}

function onInputKeydown(e) {
  if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); sendMessage() }
}

function refreshAll() {
  if (activeSessionId.value) { loadMessages(activeSessionId.value); loadPendingActions(activeSessionId.value); loadDevices(activeSessionId.value) }
  loadSessions(); ElMessage.success('已刷新')
}

async function loadShortcuts() {
  try {
    const [alertData, assetData] = await Promise.all([
      request.get('/alerts/api/list', { params: { status: 'triggered', per_page: 50 } }),
      request.get('/assets/api/list', { params: { ci_type: '' } })
    ])
    alertsList.value = alertData.alerts || []
    assetsList.value = (assetData && assetData.items) || []
  } catch (e) { console.error(e) }
}

async function linkAlert(alertId) {
  const sid = await ensureSession()
  if (!sid) return ElMessage.warning('创建会话失败，请重试')
  try {
    await request.post(`/agent/session/${sid}/link-alert`, { alert_id: alertId })
    ElMessage.success('已关联告警')
    loadMessages(sid)
  } catch (e) { ElMessage.error('关联告警失败: ' + (e.message || '未知错误')) }
}

async function linkAsset(assetId) {
  const sid = await ensureSession()
  if (!sid) return ElMessage.warning('创建会话失败，请重试')
  try {
    await request.post(`/agent/session/${sid}/link-asset`, { asset_id: assetId })
    ElMessage.success('已关联资产')
    loadMessages(sid)
  } catch (e) { ElMessage.error('关联资产失败: ' + (e.message || '未知错误')) }
}

async function runCorrelationAnalysis() {
  correlationRunning.value = true
  try {
    const res = await request.post('/agent/correlation-analyze', { hours: correlationHours.value, service: correlationService.value })
    const sid = res.session_id
    if (!sid) { ElMessage.error('创建关联分析会话失败'); return }
    ElMessage.success('关联数据已注入，正在分析...')
    window._pendingAgentSessionId = sid
    activeSessionId.value = sid; pendingAutoSend.value = true
    await loadMessages(sid)
  } catch (e) { ElMessage.error('关联分析失败: ' + (e.message || '未知错误')) }
  finally { correlationRunning.value = false }
}

async function loadPendingActions(sessionId) {
  if (!sessionId) { pendingActions.value = []; return }
  try {
    const data = await request.get('/agent/api/pending')
    pendingActions.value = (data.actions || []).filter(a => a.session_id === sessionId || !a.session_id)
  } catch (e) { pendingActions.value = [] }
}

async function confirmAction(id) {
  confirmingId.value = id
  try {
    const data = await request.post(`/agent/pending/${id}/confirm`)
    const result = data.result || {}
    if (result.status === 'completed') {
      ElMessage.success('执行完成')
      if (activeSessionId.value) { await loadMessages(activeSessionId.value); await loadPendingActions(activeSessionId.value) }
    } else if (result.status === 'executing') {
      ElMessage.info('命令正在远程执行中，请稍候...')
      const history = await pollSessionForNewMessage(activeSessionId.value, messages.value.length)
      if (history) messages.value = history.messages || []
      await loadPendingActions(activeSessionId.value)
    } else {
      if (result.success) { ElMessage.success('执行成功') } else { ElMessage({ message: '执行失败', type: 'error', duration: 6000 }) }
      if (result.reply) { messages.value.push({ role: 'assistant', content: result.reply, created_at: new Date().toISOString() }); await nextTick(); scrollToBottom(true) }
      if (activeSessionId.value) { await loadMessages(activeSessionId.value); await loadPendingActions(activeSessionId.value) }
    }
  } catch (e) { ElMessage.error('操作失败: ' + e.message) }
  finally { confirmingId.value = null }
}

async function cancelAction(id) {
  try { await request.post(`/agent/pending/${id}/cancel`); ElMessage.success('已取消'); if (activeSessionId.value) await loadPendingActions(activeSessionId.value) }
  catch (e) { ElMessage.error('操作失败: ' + e.message) }
}

async function pollSessionForNewMessage(sessionId, beforeCount) {
  for (let i = 0; i < 60; i++) {
    await new Promise(resolve => setTimeout(resolve, 2000))
    try {
      const data = await request.get(`/agent/history/${sessionId}`)
      const msgs = data.messages || []
      if (msgs.length > beforeCount) { await nextTick(); scrollToBottom(true); return data }
    } catch (e) { /* ignore */ }
  }
  ElMessage.warning('执行结果加载超时，请稍后手动刷新')
  return null
}

async function sendMessage() {
  const message = inputMessage.value.trim()
  if (!message || loading.value) return
  const sessionId = await ensureSession()
  if (!sessionId) return
  stopTypewriter()
  if (!skipNextUserPush.value) {
    messages.value.push({ role: 'user', content: message, created_at: new Date().toISOString() })
    await nextTick(); scrollToBottom(true)
  }
  skipNextUserPush.value = false; inputMessage.value = ''; loading.value = true
  try {
    const sseDone = new Promise((resolve) => {
      const checkDone = setInterval(() => {
        if (streamingDone.value) { clearInterval(checkDone); resolve() }
      }, 100)
      setTimeout(() => { clearInterval(checkDone); resolve() }, 120000)
    })
    startSSE(sessionId, message)
    await sseDone
    stopTypewriter()
    if (streamingContent.value) {
      messages.value.push({ role: 'assistant', content: streamingContent.value, created_at: new Date().toISOString(), _steps: streamingSteps.value.map(s => ({ ...s })), _task: streamingTask.value ? { ...streamingTask.value } : null })
      await loadMessages(activeSessionId.value)
      await loadPendingActions(activeSessionId.value)
    } else if (streamingError.value) {
      messages.value.push({ role: 'assistant', content: streamingError.value, message_type: 'error', created_at: new Date().toISOString() })
    }
    await nextTick(); scrollToBottom(true)
  } catch (e) {
    stopTypewriter()
    messages.value.push({ role: 'assistant', content: '请求失败: ' + e.message, message_type: 'error', created_at: new Date().toISOString() })
    await nextTick(); scrollToBottom(true)
  } finally {
    stopSSE(); loading.value = false
  }
}

function askQuestion(q) { inputMessage.value = q; sendMessage() }

function stopGenerating() {
  stopTypewriter(); stopSSE(); loading.value = false
  streamingContent.value = ''; streamingError.value = null; streamingDone.value = false
}

function formatTime(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const now = new Date()
  const p = (n) => String(n).padStart(2, '0')
  if (d.toDateString() === now.toDateString()) return `今天 ${d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function riskTagType(level) {
  return { critical: 'danger', high: 'warning', medium: 'warning', low: 'success' }[level] || 'info'
}

function scrollToBottom(force = false) {
  const el = messagesRef.value
  if (!el) return
  el.scrollTop = el.scrollHeight
  if (force) requestAnimationFrame(() => { if (messagesRef.value) messagesRef.value.scrollTop = messagesRef.value.scrollHeight })
}

onMounted(async () => {
  await loadSessions(); await loadShortcuts(); await loadProviders()
  const pendingId = window._pendingAgentSessionId
  if (pendingId) {
    window._pendingAgentSessionId = null; pendingAutoSend.value = true; switchSession(pendingId)
  } else if (sessions.value.length > 0) {
    const lastId = localStorage.getItem(STORAGE_KEY)
    const targetId = lastId && sessions.value.some(s => s.id == lastId) ? parseInt(lastId) : sessions.value[0].id
    switchSession(targetId)
  }
})

onUnmounted(() => { stopSSE(); stopTypewriter() })
</script>

<style scoped>
.agent-layout {
  display: flex; flex-direction: column; height: 100vh; background: #f8fafc; overflow: hidden;
}
.agent-topbar {
  display: flex; align-items: center; justify-content: space-between; flex-shrink: 0;
  height: 48px; padding: 0 20px; background: #fff; border-bottom: 1px solid #e2e8f0;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04); z-index: 100;
}
.topbar-left { display: flex; align-items: center; gap: 12px; }
.topbar-brand { font-weight: 700; font-size: 0.95rem; color: #1e293b; letter-spacing: 0.3px; }
.topbar-right { display: flex; align-items: center; gap: 6px; }
.topbar-btn {
  width: 32px; height: 32px; border: none; border-radius: 8px; background: transparent;
  font-size: 1rem; cursor: pointer; transition: all 0.15s; display: flex;
  align-items: center; justify-content: center; color: #64748b;
}
.topbar-btn:hover { background: #f1f5f9; color: #1e293b; }
.topbar-mode-hint { font-size: 0.75rem; color: #94a3b8; font-weight: 400; }

.agent-body {
  display: flex; flex: 1; min-height: 0; overflow: hidden;
}

.agent-sidebar {
  width: 260px; flex-shrink: 0; display: flex; flex-direction: column;
  background: #fff; border-right: 1px solid #e2e8f0;
}
.sidebar-search {
  display: flex; align-items: center; gap: 6px; padding: 12px; border-bottom: 1px solid #f1f5f9;
}
.sidebar-search-input {
  flex: 1; height: 32px; padding: 0 10px; border: 1px solid #e2e8f0; border-radius: 8px;
  font-size: 0.8rem; outline: none; background: #f8fafc; transition: border-color 0.15s;
  box-sizing: border-box;
}
.sidebar-search-input:focus { border-color: #6366f1; background: #fff; }
.sidebar-new-btn {
  width: 32px; height: 32px; border: none; border-radius: 8px; background: #6366f1;
  color: #fff; font-size: 1.1rem; cursor: pointer; transition: background 0.15s;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.sidebar-new-btn:hover { background: #4f46e5; }
.sidebar-list {
  flex: 1; overflow-y: auto; padding: 4px 8px;
}
.sidebar-item {
  display: flex; align-items: center; gap: 6px; padding: 8px 10px; border-radius: 8px;
  cursor: pointer; transition: background 0.15s; position: relative;
}
.sidebar-item:hover { background: #f1f5f9; }
.sidebar-item.active { background: #eef2ff; }
.sidebar-item-title { flex: 1; min-width: 0; font-size: 0.85rem; color: #334155; font-weight: 500; }
.sidebar-title-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; }
.sidebar-rename-input {
  width: 100%; padding: 2px 6px; border: 1px solid #6366f1; border-radius: 4px;
  font-size: 0.85rem; outline: none; box-sizing: border-box;
}
.sidebar-item-date { font-size: 0.7rem; color: #94a3b8; white-space: nowrap; }
.sidebar-del-btn {
  width: 20px; height: 20px; border: none; border-radius: 4px; background: transparent;
  color: #94a3b8; font-size: 10px; cursor: pointer; display: none;
  align-items: center; justify-content: center; flex-shrink: 0;
}
.sidebar-item:hover .sidebar-del-btn { display: flex; }
.sidebar-del-btn:hover { background: rgba(239,68,68,0.1); color: #ef4444; }
.sidebar-empty { padding: 24px; text-align: center; color: #94a3b8; font-size: 0.82rem; }

.agent-main {
  flex: 1; display: flex; flex-direction: column; min-width: 0; position: relative;
  background: #fff;
}

.agent-chat-header {
  display: flex; align-items: center; justify-content: space-between; flex-shrink: 0;
  padding: 12px 20px; border-bottom: 1px solid #f1f5f9;
}
.chat-header-left { display: flex; align-items: center; gap: 10px; min-width: 0; }
.chat-header-title {
  font-weight: 600; font-size: 0.95rem; color: #1e293b; cursor: pointer;
  max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.chat-header-title:hover { color: #6366f1; }
.chat-header-rename {
  font-weight: 600; font-size: 0.95rem; border: 1px solid #6366f1; border-radius: 6px;
  padding: 4px 10px; outline: none;
}
.chat-header-mode-tag {
  font-size: 0.7rem; padding: 2px 8px; border-radius: 10px; font-weight: 600;
  background: #eef2ff; color: #6366f1; text-transform: uppercase;
}
.chat-header-urgent {
  font-size: 0.7rem; padding: 2px 8px; border-radius: 10px; font-weight: 700;
  background: #fef2f2; color: #ef4444; animation: urgent-pulse 1.5s ease-in-out infinite;
}
@keyframes urgent-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.6; } }
.chat-header-right { display: flex; align-items: center; gap: 8px; }
.model-label { font-size: 0.78rem; color: #64748b; white-space: nowrap; }
.model-select {
  padding: 4px 10px; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 0.8rem;
  outline: none; background: #f8fafc; color: #334155; cursor: pointer;
}

.chat-messages {
  flex: 1; overflow-y: auto; padding: 16px 20px; display: flex; flex-direction: column;
  gap: 8px;
}
.welcome-area {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  flex: 1; text-align: center; padding: 60px 20px; gap: 12px;
}
.welcome-icon { font-size: 3rem; }
.welcome-title { font-size: 1.2rem; font-weight: 700; color: #1e293b; }
.welcome-desc { font-size: 0.85rem; color: #64748b; max-width: 420px; line-height: 1.5; }
.suggested-questions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-top: 8px; }
.suggested-btn {
  padding: 6px 16px; border: 1px solid #e2e8f0; border-radius: 16px; background: #f8fafc;
  font-size: 0.8rem; color: #475569; cursor: pointer; transition: all 0.15s;
}
.suggested-btn:hover { border-color: #6366f1; color: #6366f1; background: #eef2ff; }

.msg-row { display: flex; flex-direction: column; }
.msg-row.user { align-items: flex-end; }
.msg-row.assistant { align-items: flex-start; }
.msg-bubble {
  max-width: 720px; padding: 12px 16px; border-radius: 12px; line-height: 1.6;
  font-size: 0.85rem; word-break: break-word;
}
.msg-bubble.user {
  background: #6366f1; color: #fff; border-bottom-right-radius: 4px;
}
.msg-bubble.assistant {
  background: #f1f5f9; color: #1e293b; border-bottom-left-radius: 4px;
}
.msg-bubble.error-bubble { background: #fef2f2; border: 1px solid #fecaca; color: #dc2626; }
.msg-content { line-height: 1.6; }
.msg-meta { display: flex; gap: 8px; font-size: 0.7rem; color: #94a3b8; margin-top: 4px; }
.msg-row.user .msg-meta { color: rgba(255,255,255,0.7); }
.tool-badge { cursor: help; }
.streaming-indicator {
  display: flex; align-items: center; gap: 8px; padding: 8px 16px; color: #64748b; font-size: 0.82rem;
}
.streaming-spinner {
  width: 14px; height: 14px; border: 2px solid #e2e8f0; border-top-color: #6366f1;
  border-radius: 50%; animation: spin 0.6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.pending-bar {
  flex-shrink: 0; padding: 10px 20px; border-top: 1px solid #f1f5f9; background: #fffbeb;
}
.pending-title { font-size: 0.78rem; font-weight: 600; color: #d97706; margin-bottom: 6px; }
.pending-item {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 6px 0; font-size: 0.82rem;
}
.pending-item-left { display: flex; align-items: center; gap: 8px; }
.pending-item-text { color: #1e293b; }
.pending-actions { display: flex; gap: 6px; }
.pending-btn {
  padding: 4px 12px; border-radius: 6px; font-size: 0.78rem; font-weight: 600;
  cursor: pointer; transition: all 0.15s; border: none; white-space: nowrap;
}
.pending-btn.confirm { background: #059669; color: #fff; }
.pending-btn.confirm:hover { background: #047857; }
.pending-btn.cancel { background: #e2e8f0; color: #475569; }
.pending-btn.cancel:hover { background: #cbd5e1; }
.pending-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.pending-empty { font-size: 0.78rem; color: #94a3b8; }
.confirm-spinner {
  display: inline-block; width: 12px; height: 12px;
  border: 2px solid rgba(255,255,255,0.3); border-top-color: #fff;
  border-radius: 50%; animation: spin 0.6s linear infinite;
  vertical-align: middle; margin-right: 4px;
}

.agent-input-area {
  flex-shrink: 0; border-top: 1px solid #e2e8f0; background: #fff; padding: 10px 20px 14px;
}
.device-bar { margin-bottom: 8px; }
.device-tags { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.device-tag {
  display: flex; align-items: center; gap: 3px; padding: 3px 10px;
  background: #eef2ff; border-radius: 12px; font-size: 0.75rem; color: #4338ca;
}
.device-tag-sep { color: #a5b4fc; }
.device-tag-close {
  background: none; border: none; cursor: pointer; color: #6366f1;
  font-size: 0.85rem; padding: 0 2px; line-height: 1;
}
.device-add-btn {
  padding: 3px 10px; border: 1px dashed #c7d2fe; border-radius: 12px;
  background: #f8faff; font-size: 0.75rem; color: #6366f1; cursor: pointer;
}
.device-add-btn:hover { background: #eef2ff; }
.device-add-popover { padding: 4px 0; }

.context-toolbar {
  display: flex; gap: 6px; padding: 6px 0;
}
.context-btn {
  padding: 5px 12px; background: #f1f5f9; border: 1px solid transparent; border-radius: 16px;
  font-size: 0.78rem; color: #6366f1; cursor: pointer; transition: all 0.2s;
  font-weight: 500; white-space: nowrap;
}
.context-btn:hover { background: #e0e7ff; border-color: #c7d2fe; }

.input-row {
  display: flex; align-items: flex-end; gap: 10px;
}
.input-wrap { flex: 1; position: relative; }
.chat-textarea {
  width: 100%; padding: 10px 14px; border: 1px solid #e2e8f0; border-radius: 12px;
  font-size: 0.85rem; outline: none; resize: none; font-family: inherit;
  line-height: 1.5; min-height: 42px; max-height: 150px; box-sizing: border-box;
  background: #f8fafc; transition: border-color 0.15s;
}
.chat-textarea:focus { border-color: #6366f1; background: #fff; }
.chat-textarea:disabled { background: #f1f5f9; cursor: not-allowed; }
.input-actions {
  display: flex; align-items: center; gap: 6px; flex-shrink: 0;
}
.mode-tabs {
  display: flex; background: #f1f5f9; border-radius: 8px; overflow: hidden;
}
.mode-tab {
  padding: 8px 14px; border: none; font-size: 0.78rem; font-weight: 600;
  cursor: pointer; transition: all 0.15s; background: transparent; color: #64748b;
}
.mode-tab.active { background: #6366f1; color: #fff; }
.mode-tab:not(.active):hover { color: #334155; }
.send-btn {
  padding: 8px 20px; border: none; border-radius: 8px; background: #6366f1;
  color: #fff; font-size: 0.85rem; font-weight: 600; cursor: pointer; transition: all 0.15s;
  white-space: nowrap;
}
.send-btn:hover { background: #4f46e5; }
.send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.stop-btn {
  padding: 8px 16px; border: 1px solid #ef4444; border-radius: 8px;
  background: #fef2f2; color: #dc2626; font-size: 0.82rem; font-weight: 600;
  cursor: pointer; transition: all 0.15s; white-space: nowrap;
}
.stop-btn:hover { background: #fee2e2; }

.msg-task-card-wrap { width: 100%; max-width: 720px; margin: 8px 0; }
.msg-row.assistant .msg-task-card-wrap { margin-right: auto; }

.typewriter-cursor {
  display: inline-block; animation: blink 0.8s step-end infinite;
  color: #6366f1; font-size: 1em; margin-left: 1px;
}
@keyframes blink { 50% { opacity: 0; } }

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
.correlation-popover { padding: 4px 0; }
.correlation-field { margin-bottom: 10px; }
.correlation-field label { display: block; font-size: 0.78rem; color: #64748b; margin-bottom: 4px; font-weight: 500; }
.correlation-run-btn {
  width: 100%; padding: 8px 0; border: none; border-radius: 8px;
  background: linear-gradient(135deg, #f59e0b, #d97706); color: #fff;
  font-size: 0.85rem; font-weight: 600; cursor: pointer; transition: all 0.2s;
  display: flex; align-items: center; justify-content: center; gap: 6px;
}
.correlation-run-btn:hover { background: linear-gradient(135deg, #fbbf24, #f59e0b); }
.correlation-run-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.correlation-spinner {
  display: inline-block; width: 14px; height: 14px;
  border: 2px solid rgba(255,255,255,0.3); border-top-color: #fff;
  border-radius: 50%; animation: correlation-spin 0.6s linear infinite;
}
@keyframes correlation-spin { to { transform: rotate(360deg); } }
.correlation-radio-group { display: flex; gap: 6px; }
.correlation-radio-btn {
  flex: 1; padding: 6px 0; border: 1px solid #e2e8f0; border-radius: 6px;
  background: #fff; color: #475569; font-size: 0.78rem; font-weight: 500;
  cursor: pointer; transition: all 0.15s; text-align: center;
}
.correlation-radio-btn:hover { border-color: #c7d2fe; color: #6366f1; }
.correlation-radio-btn.active { background: #6366f1; border-color: #6366f1; color: #fff; }
</style>
