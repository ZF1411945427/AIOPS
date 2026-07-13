<template>
  <div class="docker-page">
    <div class="page-header">
      <h1>Docker 容器列表</h1>
      <p>Docker 容器清单与详情 · 共 {{ containers.length }} 个</p>
    </div>

    <div class="toolbar">
      <input v-model="searchFilter" class="input" placeholder="容器名搜索" @keyup.enter="loadContainers" />
      <select v-model="hostFilter" class="input" @change="loadContainers">
        <option value="">全部主机</option>
        <option v-for="h in hosts" :key="h" :value="h">{{ h }}</option>
      </select>
      <select v-model="statusFilter" class="input" @change="loadContainers">
        <option value="">全部状态</option>
        <option value="running">运行中</option>
        <option value="exited">已停止</option>
      </select>
      <button class="btn btn-primary" @click="loadContainers">查询</button>
      <button class="btn" @click="resetFilter">重置</button>
      <button class="btn btn-primary" @click="scanLocal" :disabled="scanning">{{ scanning ? '扫描中...' : '扫描本地 Docker' }}</button>
    </div>

    <div class="panel">
      <div class="panel-head">容器列表</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="containers.length" class="table-wrap">
          <table class="table">
            <thead><tr><th>容器名</th><th>主机</th><th>镜像</th><th>状态</th><th>端口</th><th>创建时间</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="c in containers" :key="c.id" class="row-click" @click="openDetail(c)">
                <td class="name-cell">{{ c.name }}</td>
                <td>{{ c.host }}</td>
                <td class="img-cell">{{ c.image }}</td>
                <td><span class="badge" :class="c.state === 'running' ? 'state-run' : 'state-stop'">{{ c.state }}</span></td>
                <td class="port-cell">{{ c.ports || '-' }}</td>
                <td>{{ c.created_at || '-' }}</td>
                <td @click.stop>
                  <button class="btn btn-sm" @click.stop="openDetail(c)">详情</button>
                  <button class="btn btn-sm" @click.stop="toggleLogs(c)">日志</button>
                  <button class="btn btn-sm" @click.stop="toggleTerminal(c)">终端</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">🐳</div><div>暂无容器</div></div>
      </div>
    </div>

    <div v-if="showDetail" class="modal-overlay" @click.self="showDetail = false">
      <div class="modal-box modal-lg">
        <h3>容器详情 · {{ detailContainer?.name }}</h3>
        <div v-if="detailLoading" class="loading-state">加载中...</div>
        <div v-else-if="detailContainer">
          <div class="detail-grid">
            <div class="info-item"><span class="ik">容器名</span><span class="iv">{{ detailContainer.name }}</span></div>
            <div class="info-item"><span class="ik">全名</span><span class="iv">{{ detailContainer.full_name }}</span></div>
            <div class="info-item"><span class="ik">主机</span><span class="iv">{{ detailContainer.host }}</span></div>
            <div class="info-item"><span class="ik">镜像</span><span class="iv">{{ detailContainer.image }}</span></div>
            <div class="info-item"><span class="ik">状态</span><span class="iv"><span class="badge" :class="detailContainer.state === 'running' ? 'state-run' : 'state-stop'">{{ detailContainer.state }}</span></span></div>
            <div class="info-item"><span class="ik">IP</span><span class="iv">{{ detailContainer.ip || '-' }}</span></div>
            <div class="info-item"><span class="ik">端口</span><span class="iv">{{ detailContainer.ports || '-' }}</span></div>
            <div class="info-item"><span class="ik">创建时间</span><span class="iv">{{ detailContainer.created_at || '-' }}</span></div>
          </div>
          <div class="sub-title">完整属性 (attrs)</div>
          <div class="attrs-box">
            <div v-for="(v, k) in detailContainer.attrs" :key="k" class="attr-row"><span class="ak">{{ k }}</span><span class="av">{{ formatVal(v) }}</span></div>
            <div v-if="!detailContainer.attrs || !Object.keys(detailContainer.attrs).length" class="empty-state">无额外属性</div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showDetail = false">关闭</button>
          <button v-if="detailContainer" class="btn btn-primary" @click="showDetail = false; toggleLogs(detailContainer)">查看日志</button>
          <button v-if="detailContainer" class="btn btn-primary" @click="showDetail = false; toggleTerminal(detailContainer)">打开终端</button>
        </div>
      </div>
    </div>

    <div v-if="showLogs" class="modal-overlay" @click.self="showLogs = false">
      <div class="modal-box wide log-modal">
        <div class="log-header">
          <h3>日志 · {{ logsContainerItem?.name }}</h3>
          <button class="btn btn-sm" @click="showLogs = false">✕</button>
        </div>
        <div class="log-toolbar">
          <select v-model="logsTail" class="input log-sel" @change="loadLogs(logsContainerItem)">
            <option :value="100">最近 100 行</option>
            <option :value="500">最近 500 行</option>
            <option :value="1000">最近 1000 行</option>
            <option :value="2000">最近 2000 行</option>
            <option :value="5000">最近 5000 行</option>
          </select>
          <input v-model="logsSearch" class="input log-search" placeholder="搜索关键字（过滤）" />
          <button class="btn btn-sm" @click="loadLogs(logsContainerItem)">刷新</button>
        </div>
        <div v-if="logsMeta" class="log-meta">
          <span>容器: {{ logsMeta.container }}</span>
          <span>行数: {{ logsMeta.lines }}</span>
        </div>
        <pre class="log-content">{{ logsLoading ? '加载中...' : (logsSearch ? filteredLogs : logsContent) }}</pre>
      </div>
    </div>

    <div v-if="showTerm" class="modal-overlay" @click.self="showTerm = false">
      <div class="modal-box wide term-modal">
        <div class="log-header">
          <h3>终端 · {{ termContainer?.name }}</h3>
          <button class="btn btn-sm" @click="toggleTerminal(termContainer)">✕</button>
        </div>
        <div id="xterm-container" class="xterm-box"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const containers = ref([])
const hosts = ref([])
const searchFilter = ref('')
const hostFilter = ref('')
const statusFilter = ref('')
const scanning = ref(false)

const showDetail = ref(false)
const detailLoading = ref(false)
const detailContainer = ref(null)

const showLogs = ref(false)
const logsLoading = ref(false)
const logsContent = ref('')
const logsContainerItem = ref(null)
const logsTail = ref(500)
const logsSearch = ref('')
const logsMeta = ref(null)

const showTerm = ref(false)
const termContainer = ref(null)
let termInstance = null

const filteredLogs = computed(() => {
  if (!logsSearch.value || !logsContent.value) return logsContent.value
  const kw = logsSearch.value.toLowerCase()
  return logsContent.value.split('\n').filter(l => l.toLowerCase().includes(kw)).join('\n')
})

function formatVal(v) {
  if (v === null || v === undefined) return '-'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

async function loadContainers() {
  loading.value = true
  try {
    const data = await request.get('/containers/api/docker', { params: { search: searchFilter.value, host: hostFilter.value, status: statusFilter.value } })
    containers.value = data.items || []
    hosts.value = data.hosts || []
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

function resetFilter() { searchFilter.value = ''; hostFilter.value = ''; statusFilter.value = ''; loadContainers() }

async function scanLocal() {
  scanning.value = true
  try {
    const data = await request.post('/containers/api/docker/local/scan')
    if (data.ok) {
      ElMessage.success('扫描完成，共导入 ' + data.count + ' 个容器')
      await loadContainers()
    } else {
      ElMessage.error('扫描失败: ' + (data.error || ''))
    }
  } catch (e) {
    ElMessage.error('扫描失败: ' + (e.message || e))
  } finally {
    scanning.value = false
  }
}

async function openDetail(c) {
  showDetail.value = true
  detailLoading.value = true
  detailContainer.value = c
  try {
    const data = await request.get(`/containers/api/docker/${c.id}`)
    detailContainer.value = data.container || c
  } catch (e) {
    ElMessage.error('详情加载失败: ' + (e.message || e))
  } finally {
    detailLoading.value = false
  }
}

function toggleLogs(c) {
  if (!c) return
  if (showLogs.value) { showLogs.value = false; return }
  showLogs.value = true
  logsContainerItem.value = c
  logsMeta.value = null
  logsSearch.value = ''
  loadLogs(c)
}

async function loadLogs(c) {
  if (!c) return
  logsLoading.value = true
  logsContent.value = '加载中...'
  try {
    const data = await request.get(`/containers/api/docker/${c.id}/logs`, { params: { tail: logsTail.value } })
    if (data.ok) {
      logsContent.value = data.logs || '(无日志输出)'
      logsMeta.value = { container: data.container, lines: data.lines }
    } else {
      logsContent.value = '获取日志失败: ' + (data.error || '')
    }
  } catch (e) {
    logsContent.value = '请求异常: ' + (e.message || e)
  } finally {
    logsLoading.value = false
  }
}

function toggleTerminal(c) {
  if (!c) return
  if (showTerm.value) { showTerm.value = false; disposeTerm(); return }
  showTerm.value = true
  termContainer.value = c
  nextTick(() => initTerminal(c))
}

function disposeTerm() {
  if (termInstance) { termInstance.dispose(); termInstance = null }
}

function initTerminal(c) {
  nextTick(() => {
    const el = document.getElementById('xterm-container')
    if (!el) return
    initXterm(el, c)
  })
}

function initXterm(el, c) {
  Promise.all([
    import('@xterm/xterm'),
    import('@xterm/addon-fit'),
  ]).then(([{ Terminal }, { FitAddon }]) => {
    if (termInstance) try { termInstance.dispose() } catch {}
    const fitAddon = new FitAddon()
    termInstance = new Terminal({
      cursorBlink: true, fontSize: 13,
      fontFamily: "'Consolas','Courier New',monospace",
      theme: { background: '#0d1117', foreground: '#e6edf3', cursor: '#e6edf3', selection: '#3b5998' },
    })
    termInstance.loadAddon(fitAddon)
    termInstance.open(el)
    fitAddon.fit()
    termInstance.write('正在连接...\r\n')
    const protocol = location.protocol === 'https:' ? 'wss://' : 'ws://'
    const token = localStorage.getItem('aiops-token') || ''
    const wsUrl = protocol + location.host + '/containers/ws/docker/' + c.id + '/terminal'
    const ws = new WebSocket(token ? wsUrl + '?token=' + encodeURIComponent(token) : wsUrl)
    ws.binaryType = 'arraybuffer'
    ws.onopen = () => { termInstance.clear(); termInstance.focus(); fitAddon.fit() }
    ws.onmessage = e => {
      if (e.data instanceof ArrayBuffer) {
        termInstance.write(new Uint8Array(e.data))
      } else {
        termInstance.write(e.data)
      }
    }
    ws.onerror = () => { termInstance.write('\r\n[连接错误]\r\n') }
    ws.onclose = () => { termInstance.write('\r\n[连接关闭]\r\n') }
    let inputBuf = []
    termInstance.onData(data => {
      if (data.charCodeAt(0) === 0x1b) return
      if (data === '\x7f') {
        if (inputBuf.length > 0) {
          inputBuf.pop()
          termInstance.write('\b \b')
        }
        return
      }
      if (data === '\r') {
        const cmd = inputBuf.join('')
        inputBuf = []
        termInstance.write('\r\n')
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(cmd + '\r')
        return
      }
      for (let i = 0; i < data.length; i++) {
        const ch = data[i]
        if (ch >= ' ' && ch < '\x7f') {
          inputBuf.push(ch)
          termInstance.write(ch)
        }
      }
    })
    window.addEventListener('resize', () => fitAddon.fit())
  }).catch(err => {
    el.textContent = '终端加载失败: ' + (err.message || err)
  })
}

onMounted(loadContainers)
</script>

<style scoped>
.docker-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; align-items: center; }
.input { padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; min-width: 160px; box-sizing: border-box; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); }
.panel-body { padding: 8px 18px 18px; }
.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; white-space: nowrap; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr.row-click:hover td { background: var(--bg-hover, rgba(99,102,241,0.05)); cursor: pointer; }
.name-cell { font-weight: 600; }
.img-cell, .port-cell { max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.72rem; font-weight: 600; }
.state-run { background: rgba(16,185,129,0.12); color: #10b981; }
.state-stop { background: rgba(239,68,68,0.12); color: #ef4444; }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 420px; box-shadow: 0 8px 24px rgba(0,0,0,0.15); max-height: 86vh; overflow-y: auto; }
.modal-lg { min-width: 620px; max-width: 780px; }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; color: var(--text, #1e293b); }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; margin-bottom: 14px; }
.info-item { display: flex; gap: 8px; font-size: 0.82rem; line-height: 1.6; }
.ik { width: 72px; flex-shrink: 0; color: var(--text-secondary, #64748b); }
.iv { flex: 1; color: var(--text, #1e293b); word-break: break-all; }
.sub-title { font-weight: 600; font-size: 0.85rem; color: var(--text, #1e293b); margin: 12px 0 8px; padding-bottom: 6px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.attrs-box { background: var(--bg-hover, rgba(0,0,0,0.02)); border-radius: 8px; padding: 10px 14px; }
.attr-row { display: flex; gap: 12px; font-size: 0.78rem; line-height: 1.7; }
.ak { width: 140px; flex-shrink: 0; color: var(--text-secondary, #64748b); }
.av { flex: 1; color: var(--text, #1e293b); word-break: break-all; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.wide { min-width: 700px; max-width: 900px; }
.log-modal { max-width: 900px; }
.log-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.log-header h3 { margin: 0; font-size: 0.95rem; }
.log-toolbar { display: flex; gap: 6px; margin-bottom: 8px; flex-wrap: wrap; align-items: center; }
.log-sel { min-width: 120px; padding: 4px 8px; font-size: 0.78rem; }
.log-search { min-width: 180px; padding: 4px 8px; font-size: 0.78rem; flex: 1; }
.log-meta { display: flex; gap: 12px; flex-wrap: wrap; font-size: 0.72rem; color: var(--text-secondary, #64748b); margin-bottom: 6px; padding: 4px 8px; background: var(--bg-hover, rgba(0,0,0,0.03)); border-radius: 4px; }
.log-content { background: #1e293b; color: #e2e8f0; padding: 14px; border-radius: 6px; font-size: 12px; line-height: 1.6; overflow: auto; max-height: 56vh; white-space: pre-wrap; word-break: break-all; font-family: Consolas, monospace; }
.term-modal { max-width: 800px; }
.xterm-box { height: 50vh; background: #1e1e1e; border-radius: 6px; overflow: hidden; }
</style>
