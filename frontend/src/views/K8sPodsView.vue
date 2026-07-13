<template>
  <div class="pods-page">
    <div class="page-header">
      <h1>K8s Pod 管理</h1>
      <p>Pod 列表与详情 · 共 {{ pods.length }} 个 Pod</p>
    </div>

    <div class="toolbar">
      <select v-model="clusterFilter" class="input" @change="loadPods">
        <option value="">全部集群</option>
        <option v-for="c in clusters" :key="c.name" :value="c.name">{{ c.name }}</option>
      </select>
      <input v-model="namespaceFilter" class="input" placeholder="命名空间筛选" @keyup.enter="loadPods" />
      <button class="btn btn-primary" @click="loadPods">查询</button>
      <button class="btn" @click="resetFilter">重置</button>
    </div>

    <div class="panel">
      <div class="panel-head">Pod 列表</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="pods.length" class="table-wrap">
          <table class="table">
            <thead><tr><th>名称</th><th>命名空间</th><th>集群</th><th>Phase</th><th>节点</th><th>Pod IP</th><th>重启</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="p in pods" :key="p.name" class="row-click" @click="openDetail(p)">
                <td class="name-cell">{{ p.name }}</td>
                <td>{{ p.namespace || '-' }}</td>
                <td>{{ p.cluster || '-' }}</td>
                <td><span class="badge" :class="phaseClass(p.phase || '')">{{ p.phase || '-' }}</span></td>
                <td>{{ p.node || '-' }}</td>
                <td>{{ p.pod_ip || '-' }}</td>
                <td>{{ p.restarts ?? 0 }}</td>
                <td>{{ p.phase || '-' }}</td>
                <td @click.stop>
                  <button class="btn btn-sm" @click.stop="openDescribe(p)">查看</button>
                  <button class="btn btn-sm" @click.stop="toggleLogs(p)">日志</button>
                  <button class="btn btn-sm" @click.stop="toggleTerminal(p)">终端</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">📦</div><div>暂无 Pod 数据</div></div>
      </div>
    </div>

    <div v-if="showDetail" class="modal-overlay" @click.self="showDetail = false">
      <div class="modal-box modal-lg">
        <h3>Pod 详情 · {{ detailPod?.name }}</h3>
        <div v-if="detailLoading" class="loading-state">加载中...</div>
        <div v-else-if="detailPod">
          <div class="detail-grid">
            <div class="info-item"><span class="ik">名称</span><span class="iv">{{ detailPod.name }}</span></div>
            <div class="info-item"><span class="ik">命名空间</span><span class="iv">{{ detailPod.namespace || '-' }}</span></div>
            <div class="info-item"><span class="ik">集群</span><span class="iv">{{ detailPod.cluster || '-' }}</span></div>
            <div class="info-item"><span class="ik">Phase</span><span class="iv"><span class="badge" :class="phaseClass(phaseOf(detailPod))">{{ phaseOf(detailPod) }}</span></span></div>
            <div class="info-item"><span class="ik">节点</span><span class="iv">{{ detailPod.attrs?.node || '-' }}</span></div>
            <div class="info-item"><span class="ik">Pod IP</span><span class="iv">{{ detailPod.attrs?.pod_ip || detailPod.ip || '-' }}</span></div>
            <div class="info-item"><span class="ik">主机 IP</span><span class="iv">{{ detailPod.attrs?.host_ip || '-' }}</span></div>
            <div class="info-item"><span class="ik">重启次数</span><span class="iv">{{ detailPod.attrs?.restart_count || detailPod.attrs?.restarts || 0 }}</span></div>
            <div class="info-item"><span class="ik">镜像</span><span class="iv">{{ detailPod.attrs?.image || '-' }}</span></div>
            <div class="info-item"><span class="ik">创建时间</span><span class="iv">{{ detailPod.created_at || '-' }}</span></div>
          </div>
          <div class="sub-title">完整属性 (attrs)</div>
          <div class="attrs-box">
            <div v-for="(v, k) in detailPod.attrs" :key="k" class="attr-row"><span class="ak">{{ k }}</span><span class="av">{{ formatVal(v) }}</span></div>
            <div v-if="!detailPod.attrs || !Object.keys(detailPod.attrs).length" class="empty-state">无额外属性</div>
          </div>
          <div class="sub-title">异常事件 ({{ anomalies.length }})</div>
          <div class="attrs-box">
            <div v-if="anomalies.length" class="event-list">
              <div v-for="e in anomalies" :key="e.id" class="event-item">
                <div class="event-line"><span class="ev-reason">{{ e.reason || '-' }}</span><span class="badge" :class="severityClass(e.severity)">{{ e.severity || 'info' }}</span><span class="ev-count">×{{ e.count || 1 }}</span></div>
                <div class="event-msg">{{ e.message || '-' }}</div>
                <div class="event-time">{{ e.first_seen }} ~ {{ e.last_seen }}</div>
              </div>
            </div>
            <div v-else class="empty-state">无异常事件</div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showDetail = false">关闭</button>
          <button class="btn btn-primary" @click="toggleLogs(detailPod)">{{ showLogs ? '关闭日志' : '查看日志' }}</button>
          <button class="btn btn-primary" @click="toggleTerminal(detailPod)">{{ showTerm ? '关闭终端' : '打开终端' }}</button>
        </div>
      </div>
    </div>

    <!-- 日志弹窗 -->
    <div v-if="showLogs" class="modal-overlay" @click.self="showLogs = false">
      <div class="modal-box wide log-modal">
        <div class="log-header">
          <h3>日志 · {{ logsPod?.name }}</h3>
          <button class="btn btn-sm" @click="showLogs = false">✕</button>
        </div>
        <div class="log-toolbar">
          <select v-model="logsContainer" class="input log-sel" @change="loadLogs(logsPod)">
            <option v-for="c in logsContainers" :key="c" :value="c">{{ c }}</option>
          </select>
          <select v-model="logsTail" class="input log-sel" @change="loadLogs(logsPod)">
            <option :value="100">最近 100 行</option>
            <option :value="500">最近 500 行</option>
            <option :value="1000">最近 1000 行</option>
            <option :value="2000">最近 2000 行</option>
            <option :value="5000">最近 5000 行</option>
          </select>
          <select v-model="logsSince" class="input log-sel" @change="loadLogs(logsPod)">
            <option :value="0">全部时间</option>
            <option :value="300">近 5 分钟</option>
            <option :value="3600">近 1 小时</option>
            <option :value="21600">近 6 小时</option>
            <option :value="86400">近 24 小时</option>
          </select>
          <label class="log-prev"><input type="checkbox" v-model="logsPrevious" @change="loadLogs(logsPod)" /> 上次崩溃容器</label>
          <input v-model="logsSearch" class="input log-search" placeholder="搜索关键字（过滤含关键字的行）" />
          <button class="btn btn-sm" @click="loadLogs(logsPod)">刷新</button>
          <button class="btn btn-sm" @click="downloadLogs">下载</button>
        </div>
        <div v-if="logsMeta" class="log-meta">
          <span>容器: {{ logsMeta.container }}</span>
          <span>总行数: {{ logsMeta.lines }}</span>
          <span v-if="logsMeta.truncated" class="log-warn">⚠ 已达 tail 上限</span>
          <span v-if="logsMeta.display_truncated" class="log-warn">⚠ 日志过大，仅显示前 {{ logsMeta.max_show }} 行，完整日志请下载</span>
          <span v-if="logsSearch && filteredLogsLines !== logsMeta.lines">过滤后: {{ filteredLogsLines }} 行</span>
        </div>
        <pre class="log-content">{{ logsLoading ? '加载中...' : (logsSearch ? filteredLogs : logsContent) }}</pre>
      </div>
    </div>

    <!-- 终端弹窗 -->
    <div v-if="showTerm" class="modal-overlay" @click.self="showTerm = false">
      <div class="modal-box wide term-modal">
        <div class="log-header">
          <h3>终端 · {{ termPod?.name }}</h3>
          <button class="btn btn-sm" @click="toggleTerminal(termPod)">✕</button>
        </div>
        <div id="xterm-container" class="xterm-box"></div>
      </div>
    </div>

    <!-- Describe 弹窗 -->
    <div v-if="showDescribe" class="modal-overlay" @click.self="closeDescribe">
      <div class="modal-box modal-lg">
        <div class="log-header">
          <h3>Pod 详情 (YAML) · {{ describePod?.name }}</h3>
          <button class="btn btn-sm" @click="closeDescribe">✕</button>
        </div>
        <div v-if="describeLoading" class="loading-state">加载中...</div>
        <div v-else>
          <button class="btn btn-sm" @click="copyDescribe">{{ copiedDescribe ? '已复制 ✓' : '复制 YAML' }}</button>
          <pre class="describe-yaml">{{ describeYaml }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
const loading = ref(false)
const pods = ref([])
const clusters = ref([])
const clusterFilter = ref(appStore.k8sCluster || '')
const namespaceFilter = ref('')
const showDetail = ref(false)
const detailLoading = ref(false)
const detailPod = ref(null)
const anomalies = ref([])
const showLogs = ref(false)
const showTerm = ref(false)
const logsLoading = ref(false)
const logsContent = ref('')
const logsPod = ref(null)
const logsContainers = ref([])
const logsContainer = ref('')
const logsTail = ref(500)
const logsSince = ref(0)
const logsPrevious = ref(false)
const logsSearch = ref('')
const logsMeta = ref(null)
const termPod = ref(null)
let termInstance = null

const showDescribe = ref(false)
const describeLoading = ref(false)
const describeYaml = ref('')
const describePod = ref(null)
const copiedDescribe = ref(false)

const filteredLogs = computed(() => {
  if (!logsSearch.value || !logsContent.value) return logsContent.value
  const kw = logsSearch.value.toLowerCase()
  return logsContent.value.split('\n').filter(l => l.toLowerCase().includes(kw)).join('\n')
})
const filteredLogsLines = computed(() => {
  if (!logsSearch.value || !logsContent.value) return logsMeta.value?.lines || 0
  return filteredLogs.value.split('\n').filter(l => l.trim()).length
})

function phaseOf(p) { return p?.attrs?.phase || p?.status || 'Unknown' }
function phaseClass(phase) {
  const p = (phase || '').toLowerCase()
  if (p === 'running') return 'phase-green'
  if (p === 'pending') return 'phase-amber'
  if (p === 'failed') return 'phase-red'
  if (p === 'succeeded') return 'phase-blue'
  return 'phase-gray'
}
function severityClass(s) {
  const v = (s || '').toLowerCase()
  if (v === 'warning' || v === 'error') return 'phase-red'
  if (v === 'critical') return 'phase-red'
  return 'phase-blue'
}
function formatVal(v) {
  if (v === null || v === undefined) return '-'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

async function loadPods() {
  loading.value = true
  try {
    const data = await request.get('/k8s/api/pods', { params: { cluster: clusterFilter.value, namespace: namespaceFilter.value } })
    pods.value = data.items || []
    clusters.value = data.clusters || []
    if (clusters.value.length && !clusters.value.some(c => c.name === clusterFilter.value)) {
      clusterFilter.value = clusters.value[0]?.name || ''
    }
    appStore.setK8sCluster(clusterFilter.value)
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

function resetFilter() { clusterFilter.value = ''; namespaceFilter.value = ''; loadPods() }

async function openDetail(p) {
  showDetail.value = true
  detailLoading.value = true
  detailPod.value = p
  anomalies.value = []
  try {
    const data = await request.get(`/containers/api/pod/${p.id}`)
    detailPod.value = data.pod || p
    anomalies.value = data.anomalies || []
  } catch (e) {
    detailPod.value = p
  } finally {
    detailLoading.value = false
  }
}

async function toggleLogs(p) {
  if (!p) return
  if (showLogs.value) { showLogs.value = false; return }
  showLogs.value = true
  logsPod.value = p
  logsContainers.value = []
  logsContainer.value = ''
  logsMeta.value = null
  logsSearch.value = ''
  await loadLogs(p)
}

async function loadLogs(p) {
  if (!p) return
  logsLoading.value = true
  logsContent.value = '加载中...'
  const cluster = p.cluster || clusters.value[0]?.name || ''
  if (!cluster) { logsContent.value = '无法确定集群'; logsLoading.value = false; return }
  try {
    const params = { tail: logsTail.value, since_seconds: logsSince.value }
    if (logsPrevious.value) params.previous = true
    if (logsContainer.value) params.container = logsContainer.value
    const data = await request.get(`/k8s/api/pod/${cluster}/${p.namespace}/${p.name}/logs`, { params })
    if (data.ok) {
      logsContent.value = data.logs || '(无日志输出)'
      logsContainers.value = data.containers || [p.name]
      if (!logsContainer.value && logsContainers.value.length) logsContainer.value = data.container || logsContainers.value[0]
      logsMeta.value = {
        container: data.container, lines: data.lines, truncated: data.truncated,
        display_truncated: data.display_truncated, max_show: data.max_show,
      }
    } else {
      logsContent.value = '获取日志失败: ' + (data.error || '未知错误')
      if (data.containers) { logsContainers.value = data.containers; if (!logsContainer.value && logsContainers.value.length) logsContainer.value = logsContainers.value[0] }
    }
  } catch (e) {
    logsContent.value = '请求异常: ' + (e.message || e)
  } finally {
    logsLoading.value = false
  }
}

function downloadLogs() {
  if (!logsPod.value) return
  const cluster = logsPod.value.cluster || clusters.value[0]?.name || ''
  if (!cluster) return
  const p = new URLSearchParams({ tail: String(logsTail.value), since_seconds: String(logsSince.value) })
  if (logsPrevious.value) p.append('previous', 'true')
  if (logsContainer.value) p.append('container', logsContainer.value)
  const token = localStorage.getItem('aiops-token')
  const url = `${request.defaults.baseURL || ''}/k8s/api/pod/${cluster}/${logsPod.value.namespace}/${logsPod.value.name}/logs/download?${p.toString()}`
  fetch(url, { headers: token ? { Authorization: 'Bearer ' + token } : {} })
    .then(r => r.ok ? r.text() : Promise.reject(r.statusText))
    .then(txt => {
      const blob = new Blob([txt], { type: 'text/plain' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `${logsPod.value.name}-${logsContainer.value || 'container'}.log`
      a.click()
      URL.revokeObjectURL(a.href)
    })
    .catch(e => ElMessage.error('下载失败: ' + e))
}

function toggleTerminal(p) {
  if (!p) return
  if (showTerm.value) { showTerm.value = false; disposeTerm(); return }
  showTerm.value = true
  termPod.value = p
  nextTick(() => initTerminal(p))
}

function disposeTerm() {
  if (termInstance) { termInstance.dispose(); termInstance = null }
}

function initTerminal(p) {
  nextTick(() => {
    const el = document.getElementById('xterm-container')
    if (!el) return
    initXterm(el, p)
  })
}

function initXterm(el, p) {
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
    const cluster = p.cluster || clusters.value[0]?.name || ''
    if (!cluster) { termInstance.write('无法确定集群\r\n'); return }
    const protocol = location.protocol === 'https:' ? 'wss://' : 'ws://'
    const token = localStorage.getItem('aiops-token') || ''
    const wsUrl = protocol + location.host + '/k8s/ws/pod/' + cluster + '/' + p.namespace + '/' + p.name + '/terminal'
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
    let lastOnDataTime = 0
    termInstance.onData(data => {
      const now = Date.now()
      if (now - lastOnDataTime < 15) return
      lastOnDataTime = now
      if (data.charCodeAt(0) === 0x1b) return
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(data)
    })
    window.addEventListener('resize', () => fitAddon.fit())
  }).catch(err => {
    el.textContent = '终端加载失败: ' + (err.message || err)
  })
}

async function openDescribe(p) {
  describePod.value = p
  showDescribe.value = true
  describeLoading.value = true
  describeYaml.value = ''
  copiedDescribe.value = false
  try {
    const cluster = p.cluster || clusters.value[0]?.name || ''
    const data = await request.get(`/k8s/api/describe/pods/${cluster}/${p.namespace}/${p.name}`)
    if (data.error) {
      describeYaml.value = '# 加载失败: ' + data.error
      ElMessage.error('加载详情失败: ' + data.error)
    } else {
      describeYaml.value = data.yaml || '# 无内容'
    }
  } catch (e) {
    describeYaml.value = '# 加载失败: ' + (e.message || e)
    ElMessage.error('加载详情失败: ' + (e.message || e))
  } finally {
    describeLoading.value = false
  }
}

function closeDescribe() {
  showDescribe.value = false
  describeYaml.value = ''
  describePod.value = null
}

async function copyDescribe() {
  try {
    await navigator.clipboard.writeText(describeYaml.value)
    copiedDescribe.value = true
    setTimeout(() => { copiedDescribe.value = false }, 2000)
  } catch {
    ElMessage.warning('复制失败，请手动选择文本复制')
  }
}

onMounted(loadPods)
</script>

<style scoped>
.pods-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.input { padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; min-width: 160px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
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
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.72rem; font-weight: 600; }
.phase-green { background: rgba(16,185,129,0.12); color: #10b981; }
.phase-amber { background: rgba(245,158,11,0.12); color: #f59e0b; }
.phase-red { background: rgba(239,68,68,0.12); color: #ef4444; }
.phase-blue { background: rgba(59,130,246,0.12); color: #3b82f6; }
.phase-gray { background: rgba(100,116,139,0.12); color: #64748b; }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 420px; box-shadow: 0 8px 24px rgba(0,0,0,0.15); max-height: 86vh; overflow-y: auto; }
.modal-lg { min-width: 640px; max-width: 800px; }
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
.event-list { display: flex; flex-direction: column; gap: 8px; }
.event-item { background: var(--bg-card-solid, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 6px; padding: 8px 10px; }
.event-line { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.ev-reason { font-weight: 600; font-size: 0.82rem; color: var(--text, #1e293b); }
.ev-count { font-size: 0.72rem; color: var(--text-secondary, #64748b); }
.event-msg { font-size: 0.78rem; color: var(--text, #1e293b); margin-bottom: 4px; }
.event-time { font-size: 0.7rem; color: var(--text-tertiary, #94a3b8); }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.log-modal { max-width: 900px; }
.log-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.log-header h3 { margin: 0; font-size: 0.95rem; }
.log-toolbar { display: flex; gap: 6px; margin-bottom: 8px; flex-wrap: wrap; align-items: center; }
.log-sel { min-width: 120px; padding: 4px 8px; font-size: 0.78rem; }
.log-search { min-width: 180px; padding: 4px 8px; font-size: 0.78rem; flex: 1; }
.log-prev { font-size: 0.75rem; color: var(--text-secondary, #64748b); display: flex; align-items: center; gap: 4px; cursor: pointer; }
.log-prev input { cursor: pointer; }
.log-meta { display: flex; gap: 12px; flex-wrap: wrap; font-size: 0.72rem; color: var(--text-secondary, #64748b); margin-bottom: 6px; padding: 4px 8px; background: var(--bg-hover, rgba(0,0,0,0.03)); border-radius: 4px; }
.log-warn { color: #f59e0b; font-weight: 600; }
.log-content { background: #1e293b; color: #e2e8f0; padding: 14px; border-radius: 6px; font-size: 12px; line-height: 1.6; overflow: auto; max-height: 56vh; white-space: pre-wrap; word-break: break-all; font-family: Consolas, monospace; }
.term-modal { max-width: 800px; }
.xterm-box { height: 50vh; background: #1e1e1e; border-radius: 6px; overflow: hidden; }
.describe-yaml { background: #1e1e1e; color: #d4d4d4; padding: 14px; border-radius: 8px; font-family: ui-monospace, 'Cascadia Code', Consolas, monospace; font-size: 0.78rem; line-height: 1.5; max-height: 62vh; overflow: auto; white-space: pre; margin-top: 10px; }
</style>
