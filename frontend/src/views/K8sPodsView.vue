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
                  <button class="btn btn-sm" @click.stop="toggleLogs(p)">{{ showLogs && (detailPod?.name === p.name || termPod?.name === p.name) ? '日志' : '日志' }}</button>
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
          <h3>日志 · {{ detailPod?.name || termPod?.name }}</h3>
          <button class="btn btn-sm" @click="toggleLogs(detailPod || termPod)">✕</button>
        </div>
        <pre class="log-content">{{ logsLoading ? '加载中...' : logsContent }}</pre>
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
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const pods = ref([])
const clusters = ref([])
const clusterFilter = ref('')
const namespaceFilter = ref('')
const showDetail = ref(false)
const detailLoading = ref(false)
const detailPod = ref(null)
const anomalies = ref([])
const showLogs = ref(false)
const showTerm = ref(false)
const logsLoading = ref(false)
const logsContent = ref('')
const termPod = ref(null)
let termInstance = null

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
  logsLoading.value = true
  logsContent.value = '加载中...'
  const cluster = p.cluster || clusters.value[0]?.name || ''
  if (!cluster) { logsContent.value = '无法确定集群'; return }
  try {
    const data = await request.get(`/k8s/api/pod/${cluster}/${p.namespace}/${p.name}/logs?tail=200`)
    if (data.ok) {
      logsContent.value = data.logs || '(无日志输出)'
    } else {
      logsContent.value = '获取日志失败: ' + (data.error || '未知错误')
    }
  } catch (e) {
    logsContent.value = '请求异常: ' + (e.message || e)
  } finally {
    logsLoading.value = false
  }
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
    if (typeof Terminal === 'undefined') {
      el.textContent = '终端组件加载中...'
      const script = document.createElement('script')
      script.src = '/static/js/xterm.min.js'
      script.onload = () => {
        const fitScript = document.createElement('script')
        fitScript.src = '/static/js/xterm-addon-fit.min.js'
        fitScript.onload = () => doInitTerm(el, p)
        document.body.appendChild(fitScript)
      }
      document.body.appendChild(script)
    } else {
      doInitTerm(el, p)
    }
  })
}

function doInitTerm(el, p) {
  if (termInstance) try { termInstance.dispose() } catch {}
  termInstance = new Terminal({
    cursorBlink: true, fontSize: 13,
    fontFamily: "'Consolas','Courier New',monospace",
    theme: { background: '#1e1e1e', foreground: '#d4d4d4' },
  })
  termInstance.open(el)
  termInstance.write('正在连接...\r\n')
  const cluster = p.cluster || clusters.value[0]?.name || ''
  if (!cluster) { termInstance.write('无法确定集群\r\n'); return }
  const protocol = location.protocol === 'https:' ? 'wss://' : 'ws://'
  const ws = new WebSocket(protocol + location.host + '/k8s/ws/pod/' + cluster + '/' + p.namespace + '/' + p.name + '/terminal')
  ws.onopen = () => { termInstance.clear(); termInstance.focus() }
  ws.onmessage = e => { termInstance.write(e.data) }
  ws.onerror = () => { termInstance.write('\r\n[连接错误]\r\n') }
  ws.onclose = () => { termInstance.write('\r\n[连接关闭]\r\n') }
  termInstance.onData(data => { if (ws && ws.readyState === WebSocket.OPEN) ws.send(data) })
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
.log-modal { max-width: 800px; }
.log-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.log-header h3 { margin: 0; font-size: 0.95rem; }
.log-content { background: #1e293b; color: #e2e8f0; padding: 14px; border-radius: 6px; font-size: 12px; line-height: 1.6; overflow: auto; max-height: 60vh; white-space: pre-wrap; word-break: break-all; font-family: Consolas, monospace; }
.term-modal { max-width: 800px; }
.xterm-box { height: 50vh; background: #1e1e1e; border-radius: 6px; overflow: hidden; }
</style>
