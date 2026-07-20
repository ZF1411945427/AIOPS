<template>
  <div class="et-page">
    <div class="page-header">
      <h1>Edge Agent 反向隧道</h1>
      <p>主机主动拨出 + 零入站端口 + 浏览器 WebSSH — 主机侧零监听，所有命令走已建立的反向隧道</p>
    </div>

    <div v-if="loading" class="loading-state">加载中...</div>

    <template v-else>
      <!-- 概览 -->
      <div class="et-overview">
        <div class="ov-card">
          <div class="ov-title">设备纳管</div>
          <div class="ov-row"><span class="ov-label">总会话数</span><span class="ov-val">{{ sessions.length }}</span></div>
          <div class="ov-row"><span class="ov-label">在线</span><span class="ov-val online">{{ onlineCount }}</span></div>
          <div class="ov-row"><span class="ov-label">离线</span><span class="ov-val offline">{{ offlineCount }}</span></div>
        </div>
        <div class="ov-card">
          <div class="ov-title">隧道 Token</div>
          <div class="token-area">
            <code v-if="tunnelToken" class="token-code">{{ tunnelToken }}</code>
            <span v-else class="token-empty">未生成</span>
          </div>
          <button class="action-btn" @click="generateToken">🔐 生成新 Token</button>
          <div class="token-hint">edge agent 启动时携带此 token：<code>python edge_agent.py --cloud {{ cloudUrl }} --token &lt;token&gt;</code></div>
        </div>
        <div class="ov-card">
          <div class="ov-title">命令执行测试</div>
          <div class="cmd-test">
            <select v-model="testAgentId" class="cmd-select">
              <option value="">选择 edge agent</option>
              <option v-for="s in onlineSessions" :key="s.agent_id" :value="s.agent_id">{{ s.hostname || s.agent_id }}</option>
            </select>
            <input v-model="testCommand" class="cmd-input" placeholder="如：whoami / df -h / uptime" @keyup.enter="runCommand" />
            <button class="action-btn primary" @click="runCommand" :disabled="!testAgentId || !testCommand || cmdRunning">{{ cmdRunning ? '执行中...' : '执行' }}</button>
          </div>
          <pre v-if="cmdResult" class="cmd-result" :class="cmdResult.status">{{ cmdResult.stdout || cmdResult.stderr || '无输出' }}</pre>
        </div>
      </div>

      <!-- 会话列表 -->
      <div class="panel">
        <div class="panel-head">
          <span>Edge Agent 会话 ({{ sessions.length }})</span>
          <button class="action-btn" @click="load">🔄 刷新</button>
        </div>
        <div class="panel-body">
          <div v-if="!sessions.length" class="empty-state">
            暂无 edge agent 接入。请在主机上安装 edge agent 并配置 tunnel_token 后启动。
          </div>
          <div v-for="s in sessions" :key="s.id" class="et-card" :class="{ online: s.online, offline: !s.online }">
            <div class="et-head">
              <span class="et-status-dot" :class="{ on: s.online }">●</span>
              <span class="et-hostname">{{ s.hostname || '(unknown)' }}</span>
              <span class="et-agent-id">{{ s.agent_id }}</span>
              <span class="et-os-badge">{{ osIcon(s.os_type) }} {{ s.os_type }}</span>
              <span class="et-status-tag" :class="s.online ? 'st-on' : 'st-off'">{{ s.online ? '在线' : '离线' }}</span>
            </div>
            <div class="et-meta">
              <span>📁 资产: {{ s.asset_id ? `#${s.asset_id}` : '未绑定' }}</span>
              <span>🌐 IP: {{ (s.ip_addresses || []).join(', ') || '-' }}</span>
              <span>📦 版本: {{ s.agent_version || '-' }}</span>
              <span>⏱ 心跳: {{ formatTime(s.last_heartbeat_at) }}</span>
              <span>🔌 连接: {{ formatTime(s.connected_at) }}</span>
              <span>🔄 重连: {{ s.reconnect_count || 0 }} 次</span>
            </div>
            <div class="et-actions">
              <button v-if="s.online" class="action-btn primary" @click="openTerminal(s)">🖥 WebSSH 终端</button>
              <button v-if="s.online" class="action-btn" @click="quickCmd(s, 'whoami')">whoami</button>
              <button v-if="s.online" class="action-btn" @click="quickCmd(s, 'hostname')">hostname</button>
              <button v-if="s.online" class="action-btn" @click="quickCmd(s, 'uptime')">uptime</button>
              <button class="action-btn" @click="bindAsset(s)">🔗 绑定资产</button>
              <button class="action-btn danger" @click="deleteSession(s)">删除</button>
            </div>
            <div v-if="s._cmdResult" class="et-cmd-result">
              <pre>{{ s._cmdResult.stdout || s._cmdResult.stderr || '无输出' }}</pre>
              <span class="cmd-meta">exit_code={{ s._cmdResult.exit_code }} duration={{ s._cmdResult.duration_ms }}ms</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 命令审计日志 -->
      <div class="panel" style="margin-top: 20px;">
        <div class="panel-head">
          <span>命令审计日志 ({{ commands.length }})</span>
          <button class="action-btn" @click="loadCommands">🔄 刷新</button>
        </div>
        <div class="panel-body">
          <div v-if="!commands.length" class="empty-state">暂无命令执行记录</div>
          <div v-for="c in commands" :key="c.id" class="cmd-log-card">
            <div class="cmd-log-head">
              <span class="cmd-log-user">{{ c.username || '#' + c.user_id }}</span>
              <span class="cmd-log-cmd">{{ c.command }}</span>
              <span class="cmd-log-status" :class="`st-${c.status}`">{{ c.status }}</span>
              <span class="cmd-log-time">{{ formatTime(c.created_at) }}</span>
              <span class="cmd-log-dur">{{ c.duration_ms }}ms</span>
            </div>
            <pre v-if="c.stdout || c.stderr" class="cmd-log-output">{{ c.stdout || c.stderr }}</pre>
          </div>
        </div>
      </div>
    </template>

    <!-- WebSSH 终端模态框 -->
    <div v-if="terminalVisible" class="modal-overlay" @click.self="closeTerminal">
      <div class="terminal-modal">
        <div class="terminal-head">
          <span class="terminal-title">🖥 {{ terminalSession?.hostname }} ({{ terminalSession?.agent_id }})</span>
          <span class="terminal-status" :class="{ on: terminalStatus === '已连接' }">{{ terminalStatus }}</span>
          <button class="terminal-close" @click="closeTerminal">✕</button>
        </div>
        <div :id="`terminal-${terminalSession?.agent_id}`" class="terminal-body"></div>
      </div>
    </div>

    <!-- 绑定资产弹窗 -->
    <div v-if="bindDialog" class="modal-overlay" @click.self="bindDialog = null">
      <div class="modal">
        <div class="modal-title">绑定资产到 Edge Agent</div>
        <div class="modal-body">
          <p class="modal-hint">Edge Agent: {{ bindDialog.hostname }} ({{ bindDialog.agent_id }})</p>
          <select v-model="bindDialog.asset_id" class="modal-select">
            <option value="">请选择资产</option>
            <option v-for="a in assetList" :key="a.id" :value="a.id">{{ a.name }} ({{ a.ip }})</option>
          </select>
        </div>
        <div class="modal-actions">
          <button class="btn-cancel" @click="bindDialog = null">取消</button>
          <button class="btn-save" @click="confirmBind">绑定</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(true)
const sessions = ref([])
const commands = ref([])
const tunnelToken = ref('')
const testAgentId = ref('')
const testCommand = ref('')
const cmdRunning = ref(false)
const cmdResult = ref(null)
const assetList = ref([])
const bindDialog = ref(null)
const terminalVisible = ref(false)
const terminalSession = ref(null)
const terminalStatus = ref('')
let terminalWs = null
let terminalTerm = null

const cloudUrl = computed(() => window.location.origin)
const onlineCount = computed(() => sessions.value.filter(s => s.online).length)
const offlineCount = computed(() => sessions.value.filter(s => !s.online).length)
const onlineSessions = computed(() => sessions.value.filter(s => s.online))

function osIcon(os) {
  return { linux: '🐧', windows: '🪟', macos: '🍎' }[os] || '💻'
}
function formatTime(t) {
  if (!t) return '-'
  return new Date(t).toLocaleString('zh-CN', { hour12: false })
}

async function load() {
  try {
    const data = await request.get('/edge/sessions')
    sessions.value = data.sessions || []
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

async function loadCommands() {
  try {
    const data = await request.get('/edge/commands', { params: { limit: 30 } })
    commands.value = data.commands || []
  } catch (e) { console.error(e) }
}

async function loadAssets() {
  try {
    const data = await request.get('/assets/api/list', { params: { page_size: 200 } })
    assetList.value = data.items || []
  } catch (e) { console.error(e) }
}

async function generateToken() {
  try {
    const data = await request.post('/edge/tokens')
    tunnelToken.value = data.tunnel_token
    ElMessage.success('Token 已生成，请复制到 edge agent 配置')
  } catch (e) { ElMessage.error('生成失败') }
}

async function runCommand() {
  if (!testAgentId.value || !testCommand.value) return
  cmdRunning.value = true
  cmdResult.value = null
  try {
    const data = await request.post('/edge/command', {
      agent_id: testAgentId.value,
      command: testCommand.value,
      timeout: 30,
    })
    cmdResult.value = data
  } catch (e) {
    cmdResult.value = { status: 'failed', stderr: e.message || String(e), exit_code: -1 }
  }
  finally { cmdRunning.value = false }
}

async function quickCmd(session, cmd) {
  try {
    const data = await request.post('/edge/command', { agent_id: session.agent_id, command: cmd, timeout: 10 })
    session._cmdResult = data
  } catch (e) {
    session._cmdResult = { status: 'failed', stderr: e.message, exit_code: -1 }
  }
}

function openTerminal(session) {
  terminalSession.value = session
  terminalVisible.value = true
  terminalStatus.value = '连接中...'
  nextTick(() => connectTerminal(session))
}

function connectTerminal(session) {
  if (!window._xtermLoaded) {
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = 'https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css'
    document.head.appendChild(link)
    const s = document.createElement('script')
    s.src = 'https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.js'
    s.onload = () => { window._xtermLoaded = true; connectTerminal(session) }
    document.head.appendChild(s)
    return
  }
  const token = localStorage.getItem('aiops_token') || ''
  const cols = 100, rows = 30
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${location.host}/webssh/${session.agent_id}?token=${encodeURIComponent(token)}&cols=${cols}&rows=${rows}`
  terminalWs = new WebSocket(wsUrl)
  terminalTerm = new window.Terminal({ cols, rows, cursorBlink: true, fontSize: 13 })
  const el = document.getElementById(`terminal-${session.agent_id}`)
  if (el) { el.innerHTML = ''; terminalTerm.open(el) }
  terminalWs.onopen = () => { terminalStatus.value = '已连接' }
  terminalWs.onmessage = (e) => terminalTerm.write(e.data)
  terminalWs.onclose = () => { terminalStatus.value = '已断开' }
  terminalWs.onerror = () => { terminalStatus.value = '连接错误' }
  terminalTerm.onData((data) => {
    if (terminalWs && terminalWs.readyState === WebSocket.OPEN) {
      terminalWs.send(JSON.stringify({ type: 'input', data }))
    }
  })
  terminalTerm.onResize(({ cols, rows }) => {
    if (terminalWs && terminalWs.readyState === WebSocket.OPEN) {
      terminalWs.send(JSON.stringify({ type: 'resize', cols, rows }))
    }
  })
}

function closeTerminal() {
  if (terminalWs) { terminalWs.close(); terminalWs = null }
  if (terminalTerm) { terminalTerm.dispose(); terminalTerm = null }
  terminalVisible.value = false
}

function bindAsset(session) {
  bindDialog.value = { ...session, asset_id: session.asset_id || '' }
}

async function confirmBind() {
  try {
    await request.post(`/edge/sessions/${bindDialog.value.id}/bind`, { asset_id: bindDialog.value.asset_id })
    ElMessage.success('绑定成功')
    bindDialog.value = null
    await load()
  } catch (e) { ElMessage.error('绑定失败') }
}

async function deleteSession(session) {
  try {
    await ElMessageBox.confirm(`确认删除 edge agent 会话「${session.hostname || session.agent_id}」？`, '删除确认', { type: 'warning' })
    await request.delete(`/edge/sessions/${session.id}`)
    ElMessage.success('已删除')
    await load()
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败') }
}

onMounted(async () => {
  await Promise.all([load(), loadCommands(), loadAssets()])
})
</script>

<style scoped>
.et-page { padding: 20px; }
.page-header { margin-bottom: 24px; }
.page-header h1 { font-size: 1.4rem; font-weight: 700; margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #888); font-size: 0.85rem; margin: 0; }
.loading-state { text-align: center; padding: 60px; color: var(--text-secondary, #888); }

.et-overview { display: grid; grid-template-columns: 1fr 1.2fr 1.5fr; gap: 16px; margin-bottom: 20px; }
.ov-card { background: var(--bg-card, #fff); border: 1px solid var(--border, #e5e7eb); border-radius: 10px; padding: 18px; }
.ov-title { font-size: 0.9rem; font-weight: 600; margin-bottom: 14px; }
.ov-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-light, #f0f0f0); font-size: 0.82rem; }
.ov-label { color: var(--text-secondary, #888); }
.ov-val { font-weight: 600; }
.ov-val.online { color: #16a34a; }
.ov-val.offline { color: #6b7280; }

.token-area { margin-bottom: 12px; }
.token-code { display: block; font-family: 'Fira Code', monospace; font-size: 0.72rem; padding: 8px 12px; background: #1e293b; color: #e2e8f0; border-radius: 6px; word-break: break-all; }
.token-empty { color: var(--text-secondary, #94a3b8); font-size: 0.82rem; }
.token-hint { font-size: 0.72rem; color: var(--text-secondary, #94a3b8); margin-top: 8px; line-height: 1.5; }
.token-hint code { font-family: 'Fira Code', monospace; font-size: 0.7rem; background: #f1f5f9; padding: 1px 6px; border-radius: 3px; }

.cmd-test { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.cmd-select, .cmd-input { padding: 7px 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 0.8rem; }
.cmd-select { min-width: 160px; }
.cmd-input { flex: 1; min-width: 180px; font-family: 'Fira Code', monospace; }
.cmd-result { font-family: 'Fira Code', monospace; font-size: 0.75rem; padding: 10px 12px; background: #1e293b; color: #e2e8f0; border-radius: 6px; white-space: pre-wrap; max-height: 200px; overflow-y: auto; margin: 0; }
.cmd-result.failed { color: #fca5a5; }

.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, #e5e7eb); border-radius: 10px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; padding: 14px 20px; border-bottom: 1px solid var(--border, #e5e7eb); font-weight: 600; font-size: 0.9rem; }
.panel-body { padding: 16px 20px; }
.empty-state { text-align: center; padding: 40px 20px; color: var(--text-secondary, #94a3b8); font-size: 0.85rem; }

.et-card { background: #fafbfc; border: 1px solid #e5e7eb; border-left: 4px solid #cbd5e1; border-radius: 8px; padding: 14px 16px; margin-bottom: 12px; }
.et-card.online { border-left-color: #16a34a; }
.et-card.offline { border-left-color: #cbd5e1; opacity: 0.75; }
.et-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
.et-status-dot { font-size: 0.7rem; color: #cbd5e1; }
.et-status-dot.on { color: #16a34a; animation: pulse 2s infinite; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
.et-hostname { font-size: 0.95rem; font-weight: 600; color: #1e293b; }
.et-agent-id { font-family: 'Fira Code', monospace; font-size: 0.72rem; color: var(--text-secondary, #64748b); background: #f1f5f9; padding: 2px 8px; border-radius: 4px; }
.et-os-badge { font-size: 0.72rem; padding: 2px 8px; background: #e0f2fe; color: #075985; border-radius: 10px; }
.et-status-tag { font-size: 0.72rem; padding: 2px 10px; border-radius: 10px; font-weight: 600; }
.et-status-tag.st-on { background: #dcfce7; color: #166534; }
.et-status-tag.st-off { background: #f1f5f9; color: #64748b; }
.et-meta { display: flex; gap: 16px; flex-wrap: wrap; font-size: 0.75rem; color: var(--text-secondary, #64748b); margin-bottom: 10px; }
.et-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.action-btn { padding: 5px 14px; background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 6px; cursor: pointer; font-size: 0.78rem; }
.action-btn:hover { background: #e2e8f0; }
.action-btn.primary { background: #6366f1; color: #fff; border-color: #6366f1; }
.action-btn.primary:hover { background: #4f46e5; }
.action-btn.danger { background: #fee2e2; color: #991b1b; border-color: #fca5a5; }
.et-cmd-result { margin-top: 10px; background: #1e293b; border-radius: 6px; padding: 10px 12px; }
.et-cmd-result pre { font-family: 'Fira Code', monospace; font-size: 0.72rem; color: #e2e8f0; white-space: pre-wrap; margin: 0 0 4px; }
.cmd-meta { font-size: 0.68rem; color: #94a3b8; }

.cmd-log-card { background: #fafbfc; border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px 14px; margin-bottom: 8px; }
.cmd-log-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 0.78rem; margin-bottom: 6px; }
.cmd-log-user { font-weight: 600; color: #1e293b; }
.cmd-log-cmd { font-family: 'Fira Code', monospace; font-size: 0.72rem; color: #4338ca; background: #eef2ff; padding: 1px 8px; border-radius: 4px; }
.cmd-log-status { font-size: 0.7rem; padding: 1px 8px; border-radius: 8px; font-weight: 600; }
.cmd-log-status.st-success { background: #dcfce7; color: #166534; }
.cmd-log-status.st-failed { background: #fee2e2; color: #991b1b; }
.cmd-log-status.st-timeout { background: #fef3c7; color: #92400e; }
.cmd-log-status.st-running { background: #dbeafe; color: #1e40af; }
.cmd-log-time { margin-left: auto; color: var(--text-secondary, #94a3b8); font-size: 0.7rem; }
.cmd-log-dur { font-size: 0.7rem; color: var(--text-secondary, #94a3b8); }
.cmd-log-output { font-family: 'Fira Code', monospace; font-size: 0.72rem; padding: 8px 10px; background: #1e293b; color: #e2e8f0; border-radius: 4px; white-space: pre-wrap; max-height: 120px; overflow-y: auto; margin: 0; }

.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 2000; }
.modal { background: #fff; border-radius: 10px; padding: 24px; min-width: 420px; max-width: 560px; }
.modal-title { font-size: 1rem; font-weight: 700; margin-bottom: 16px; }
.modal-body { display: flex; flex-direction: column; gap: 10px; }
.modal-hint { font-size: 0.82rem; color: var(--text-secondary, #64748b); }
.modal-select { padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 0.85rem; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; }
.btn-cancel { padding: 8px 18px; background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 6px; cursor: pointer; font-size: 0.85rem; }
.btn-save { padding: 8px 18px; background: #6366f1; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 0.85rem; font-weight: 600; }

.terminal-modal { background: #1e293b; border-radius: 10px; width: 90%; max-width: 1100px; height: 80%; display: flex; flex-direction: column; }
.terminal-head { display: flex; align-items: center; gap: 12px; padding: 12px 18px; border-bottom: 1px solid #334155; }
.terminal-title { color: #e2e8f0; font-size: 0.9rem; font-weight: 600; }
.terminal-status { font-size: 0.75rem; padding: 2px 10px; border-radius: 10px; background: #334155; color: #94a3b8; }
.terminal-status.on { background: #166534; color: #bbf7d0; }
.terminal-close { margin-left: auto; background: transparent; border: none; color: #94a3b8; font-size: 1.2rem; cursor: pointer; }
.terminal-close:hover { color: #ef4444; }
.terminal-body { flex: 1; padding: 12px; overflow: hidden; }

@media (max-width: 1000px) {
  .et-overview { grid-template-columns: 1fr; }
}
</style>
