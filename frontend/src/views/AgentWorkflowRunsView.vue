<template>
  <div class="awr-page">
    <div class="page-header">
      <h1>智能体工作流执行监控</h1>
      <p>Agent Workflow 执行实例 · 共 {{ runs.length }} 个</p>
    </div>

    <div class="toolbar">
      <select v-model="statusFilter" class="input select-input" @change="loadRuns">
        <option value="">全部状态</option>
        <option value="running">执行中</option>
        <option value="completed">已完成</option>
        <option value="failed">失败</option>
        <option value="aborted">已中止</option>
      </select>
      <button class="btn" @click="loadRuns">刷新</button>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="runs.length" class="table">
          <thead>
            <tr><th>ID</th><th>工作流</th><th>状态</th><th>触发源</th><th>节点进度</th><th>开始时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in runs" :key="r.id">
              <td>#{{ r.id }}</td>
              <td class="title-cell">{{ getWorkflowName(r.workflow_id) }}</td>
              <td><span class="badge" :class="statusClass(r.status)">{{ statusLabel(r.status) }}</span></td>
              <td><span class="badge src-badge">{{ r.trigger_source }}</span></td>
              <td>{{ nodeProgress(r) }}</td>
              <td>{{ r.started_at || r.created_at || '-' }}</td>
              <td class="ops">
                <button class="btn btn-sm" @click="openDetail(r.id)">执行详情</button>
                <button class="btn btn-sm" @click="exportPdf(r.id)">下载报告</button>
                <button v-if="canAbort(r)" class="btn btn-sm btn-danger" @click="abortRun(r)">中止</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">🤖</div><div>暂无执行实例</div></div>
      </div>
    </div>

    <div v-if="showDetail" class="modal-overlay" @click.self="closeDetail">
      <div class="modal-box xwide">
        <div class="detail-modal-header">
          <h3>执行实例 #{{ detail.id }}</h3>
          <div class="detail-header-actions">
            <button class="btn btn-sm" @click="exportPdf" title="下载 PDF 报告">下载报告</button>
            <button class="btn btn-sm" @click="closeDetail">✕</button>
          </div>
        </div>

        <div class="detail-summary">
          <div class="summary-item"><span class="summary-label">状态</span><span class="badge badge-lg" :class="statusClass(detail.status)">{{ statusLabel(detail.status) }}</span></div>
          <div class="summary-item"><span class="summary-label">触发源</span><span class="badge src-badge">{{ detail.trigger_source }}</span></div>
          <div class="summary-item"><span class="summary-label">开始</span><span>{{ detail.started_at || '-' }}</span></div>
          <div class="summary-item"><span class="summary-label">完成</span><span>{{ detail.completed_at || '-' }}</span></div>
        </div>
        <div v-if="detail.error" class="error-box">错误: {{ detail.error }}</div>

        <div class="detail-block">
          <div class="detail-label">输入参数</div>
          <div class="kv-list">
            <div v-for="(v, k) in (detail.inputs || {})" :key="k" class="kv-row">
              <span class="kv-key">{{ k }}</span>
              <span class="kv-val">{{ typeof v === 'object' ? JSON.stringify(v) : v }}</span>
            </div>
            <div v-if="!detail.inputs || !Object.keys(detail.inputs).length" class="kv-empty">-</div>
          </div>
        </div>

        <div class="detail-block">
          <div class="detail-label">输出结果</div>
          <div v-if="detail.outputs && Object.keys(detail.outputs).length">
            <div v-for="(ov, ok) in detail.outputs" :key="ok" class="output-card">
              <div class="output-card-label">{{ ok }}</div>
              <div v-if="typeof ov === 'string' && ov.length > 80" class="output-text">{{ ov }}</div>
              <pre v-else class="code-block">{{ typeof ov === 'string' ? ov : JSON.stringify(ov, null, 2) }}</pre>
            </div>
          </div>
          <div v-else class="kv-empty">-</div>
        </div>

        <div class="detail-block">
          <div class="detail-label">节点执行 ({{ (detail.node_runs || []).length }})</div>
          <div class="node-flow">
            <div v-for="(nr, idx) in detailNodeList" :key="nr.id" class="node-card" :class="nodeStatusClass(nr.status)">
              <div class="node-header" @click="nr._exp = !nr._exp">
                <span class="node-idx">{{ idx + 1 }}</span>
                <span class="expand-arrow" :class="{ expanded: nr._exp }">▶</span>
                <span class="node-name">{{ nr.node_name || nr.node_id }}</span>
                <span class="node-type-tag">[{{ nr.node_type }}]</span>
                <span class="badge" :class="nodeStatusBadge(nr.status)">{{ nodeStatusLabel(nr.status) }}</span>
              </div>
                <div v-if="nr._exp" class="node-detail-body">
                  <div v-if="nr.status === 'awaiting_confirm'" class="node-awaiting-bar">
                    <span>⏳ 等待用户确认后执行</span>
                    <span v-if="nr.config?.execution_mode === 'auto'" class="force-confirm-hint">⚠️ 高危操作已自动从「自动执行」降级为「等待确认」</span>
                    <button class="btn btn-sm btn-primary" :disabled="confirmingId === nr.id" @click="confirmNode(nr)">{{ confirmingId === nr.id ? '确认中...' : '确认' }}</button>
                    <button class="btn btn-sm btn-outline" :disabled="confirmingId === nr.id" @click="cancelNode(nr)">取消</button>
                  </div>
                  <div v-if="nr.error && nr.status !== 'awaiting_confirm'" class="node-error">{{ nr.error }}</div>
                  <div class="node-meta">
                    <span>开始: {{ nr.started_at || '-' }}</span>
                    <span>完成: {{ nr.completed_at || '-' }}</span>
                  </div>
                  <div v-if="nr.output && Object.keys(nr.output).length" class="node-output-section">
                    <div v-for="(v, k) in nr.output" :key="k" class="node-output-row">
                      <span class="node-output-key">{{ k }}:</span>
                      <div v-if="typeof v === 'string' && v.length > 60" class="output-text">{{ v }}</div>
                      <pre v-else class="code-block code-sm">{{ typeof v === 'string' ? v : JSON.stringify(v, null, 2) }}</pre>
                    </div>
                  </div>
                  <div v-if="nr.status === 'failed'" class="node-actions">
                    <button class="btn btn-sm" @click="retryNode(nr)">重试</button>
                  </div>
                </div>
            </div>
          </div>
        </div>

        <div class="modal-actions">
          <button v-if="canAbort(detail)" class="btn btn-danger" @click="abortRun(detail)">中止</button>
          <button class="btn btn-primary" @click="exportPdf">导出 PDF</button>
          <button class="btn" @click="closeDetail">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const runs = ref([])
const statusFilter = ref('')
const workflowNames = ref({})
const showDetail = ref(false)
const detail = ref({})
const confirmingId = ref(null)
let pollTimer = null

async function loadRuns(silent = false) {
  if (!silent) loading.value = true
  try {
    const params = {}
    if (statusFilter.value) params.status = statusFilter.value
    const data = await request.get('/agent-workflow/api/runs', { params })
    runs.value = data.items || []
    for (const r of runs.value) {
      if (r.workflow_id && !workflowNames.value[r.workflow_id]) {
        try {
          const wf = await request.get(`/agent-workflow/api/workflows/${r.workflow_id}`)
          workflowNames.value[r.workflow_id] = wf.name
        } catch {}
      }
    }
  } catch (e) {
    if (!silent) ElMessage.error('加载失败: ' + (e.message || e))
  } finally {
    if (!silent) loading.value = false
  }
}

function getWorkflowName(id) {
  return workflowNames.value[id] || `#${id || '-'}`
}

async function openDetail(id) {
  try {
    detail.value = await request.get(`/agent-workflow/api/runs/${id}`)
    showDetail.value = true
  } catch (e) {
    ElMessage.error('获取详情失败: ' + (e.message || e))
  }
}

function closeDetail() {
  showDetail.value = false
  detail.value = {}
}

async function abortRun(r) {
  try {
    await ElMessageBox.confirm(`中止执行实例 #${r.id}？`, '中止确认', { type: 'warning' })
    await request.post(`/agent-workflow/api/runs/${r.id}/abort`, { reason: '用户手动中止' })
    ElMessage.success('已中止')
    if (showDetail.value && detail.value.id === r.id) {
      detail.value = await request.get(`/agent-workflow/api/runs/${r.id}`)
    }
    loadRuns()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('中止失败: ' + (e.message || e))
  }
}

async function retryNode(nr) {
  try {
    await request.post(`/agent-workflow/api/runs/${nr.run_id}/node/${nr.id}/retry`)
    ElMessage.success('节点已重试')
    detail.value = await request.get(`/agent-workflow/api/runs/${nr.run_id}`)
    loadRuns()
  } catch (e) {
    ElMessage.error('重试失败: ' + (e.message || e))
  }
}

async function confirmNode(nr) {
  confirmingId.value = nr.id
  try {
    await request.post(`/agent-workflow/api/runs/${nr.run_id}/node/${nr.id}/confirm`)
    ElMessage.success('已确认，继续执行')
    await openDetail(nr.run_id)
    loadRuns()
  } catch (e) {
    ElMessage.error('确认失败: ' + (e.message || e))
  } finally {
    confirmingId.value = null
  }
}

async function cancelNode(nr) {
  try {
    await request.post(`/agent-workflow/api/runs/${nr.run_id}/node/${nr.id}/cancel`)
    ElMessage.success('已取消执行')
    await openDetail(nr.run_id)
    loadRuns()
  } catch (e) {
    ElMessage.error('取消失败: ' + (e.message || e))
  }
}

function statusClass(s) {
  return { 'st-running': s === 'running', 'st-completed': s === 'completed', 'st-failed': s === 'failed', 'st-aborted': s === 'aborted', 'st-pending': s === 'pending', 'st-awaiting': s === 'awaiting_confirm' }
}
function statusLabel(s) {
  return { running: '执行中', completed: '已完成', failed: '失败', aborted: '已中止', pending: '等待', awaiting_confirm: '等待确认' }[s] || s
}
function nodeStatusClass(s) {
  return { 'nr-completed': s === 'completed', 'nr-failed': s === 'failed', 'nr-running': s === 'running', 'nr-skipped': s === 'skipped', 'nr-pending': s === 'pending', 'nr-awaiting': s === 'awaiting_confirm' }
}
function nodeStatusBadge(s) {
  return { 'st-completed': s === 'completed', 'st-failed': s === 'failed', 'st-running': s === 'running', 'st-skipped': s === 'skipped', 'st-pending': s === 'pending', 'st-awaiting': s === 'awaiting_confirm' }
}
function nodeStatusLabel(s) {
  return { completed: '已完成', failed: '失败', running: '执行中', skipped: '已跳过', pending: '等待', awaiting_confirm: '待确认' }[s] || s
}
function nodeProgress(r) {
  const nrs = r.node_runs || []
  if (!nrs.length) return '-'
  const done = nrs.filter(n => ['completed', 'failed', 'skipped'].includes(n.status)).length
  return `${done}/${nrs.length}`
}
function canAbort(r) {
  return r && !['completed', 'failed', 'aborted'].includes(r.status)
}

const detailNodeList = computed(() => {
  const nodes = detail.value?.node_runs || []
  nodes.forEach(n => { if (n._exp === undefined) n._exp = true })
  return nodes
})

async function exportPdf(runId) {
  const id = typeof runId === 'number' ? runId : detail.value?.id
  if (!id) return
  try {
    const blob = await request.get(`/agent-workflow/api/runs/${id}/pdf`, { responseType: 'blob' })
    // 后端错误时返回 JSON（也是 blob），需解析后给出友好提示
    if (blob.type && blob.type.includes('application/json')) {
      const text = await blob.text()
      let msg = '下载报告失败'
      try { msg = JSON.parse(text).error || msg } catch {}
      ElMessage.error(msg)
      return
    }
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `workflow_run_${id}.pdf`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error('下载报告失败: ' + (e.message || e))
  }
}

onMounted(() => {
  loadRuns()
  pollTimer = setInterval(() => {
    if (showDetail.value) return
    // 只在有执行中/等待确认的实例时才静默刷新，避免无意义的空轮询闪刷
    const hasActive = runs.value.some(r => r.status === 'running' || r.status === 'awaiting_confirm' || r.status === 'pending')
    if (hasActive) loadRuns(true)
  }, 10000)
})
onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.awr-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 16px; }
.select-input { min-width: 160px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; }
.table td { padding: 10px 12px; font-size: 0.85rem; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.title-cell { font-weight: 500; }
.ops { display: flex; gap: 6px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.st-running { background: rgba(99,102,241,0.12); color: #6366f1; }
.badge.st-completed { background: rgba(16,185,129,0.12); color: #10b981; }
.badge.st-failed { background: rgba(239,68,68,0.12); color: #ef4444; }
.badge.st-aborted { background: rgba(100,116,139,0.12); color: #64748b; }
.badge.st-pending { background: rgba(100,116,139,0.12); color: #64748b; }
.badge.st-awaiting { background: rgba(245,158,11,0.12); color: #d97706; }
.badge.src-badge { background: rgba(20,184,166,0.12); color: #14b8a6; }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 380px; max-width: 90vw; max-height: 90vh; overflow-y: auto; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-box.xwide { min-width: 720px; }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; }
.detail-summary { display: flex; flex-wrap: wrap; gap: 16px; padding: 12px; background: var(--bg-hover, rgba(0,0,0,0.03)); border-radius: 8px; margin-bottom: 12px; }
.summary-item { display: flex; gap: 6px; align-items: center; font-size: 0.82rem; }
.summary-label { color: var(--text-secondary, #64748b); font-size: 0.75rem; }
.error-box { padding: 10px; background: rgba(239,68,68,0.08); border-radius: 6px; color: #ef4444; font-size: 0.82rem; margin-bottom: 12px; }
.detail-block { margin: 10px 0; }
.detail-label { font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 6px; font-weight: 600; }
.code-block { background: rgba(0,0,0,0.04); border-radius: 6px; padding: 8px 10px; font-size: 0.75rem; font-family: 'Consolas', monospace; white-space: pre-wrap; word-break: break-all; margin: 4px 0; max-height: 200px; overflow-y: auto; }
.code-block.small { font-size: 0.7rem; max-height: 150px; }
.code-block:empty { display: none; }
.detail-modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.detail-modal-header h3 { margin: 0; font-size: 1rem; }
.detail-header-actions { display: flex; gap: 8px; }
.badge-lg { padding: 3px 12px; font-size: 0.78rem; }
.kv-list { background: rgba(0,0,0,0.015); border-radius: 6px; padding: 8px 10px; }
.kv-row { display: flex; gap: 8px; font-size: 0.82rem; padding: 3px 0; }
.kv-key { color: var(--text-tertiary, #94a3b8); min-width: 100px; font-size: 0.78rem; }
.kv-val { color: var(--text, #1e293b); word-break: break-all; }
.kv-empty { color: var(--text-tertiary, #94a3b8); font-size: 0.8rem; }
.output-card { background: rgba(0,0,0,0.02); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; padding: 12px 14px; margin-bottom: 10px; }
.output-card-label { font-size: 0.72rem; font-weight: 600; color: var(--text-secondary, #64748b); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
.output-text { font-size: 0.85rem; line-height: 1.7; white-space: pre-wrap; color: var(--text, #1e293b); max-height: 400px; overflow-y: auto; padding: 6px 0; }
.node-flow { display: flex; flex-direction: column; gap: 10px; }
.node-card { border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; padding: 10px 12px; }
.node-card.nr-completed { border-left: 3px solid #10b981; }
.node-card.nr-failed { border-left: 3px solid #ef4444; }
.node-card.nr-running { border-left: 3px solid #6366f1; }
.node-card.nr-skipped { border-left: 3px solid #94a3b8; opacity: 0.7; }
.node-card.nr-pending { border-left: 3px solid #cbd5e1; }
.node-card.nr-awaiting { border-left: 3px solid #d97706; background: rgba(245,158,11,0.04); }
.node-header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; cursor: pointer; user-select: none; }
.node-header:hover { background: rgba(0,0,0,0.02); }
.expand-arrow { font-size: 0.55rem; color: var(--text-tertiary, #94a3b8); transition: transform 0.15s; display: inline-block; width: 10px; }
.expand-arrow.expanded { transform: rotate(90deg); }
.node-idx { display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; border-radius: 50%; background: var(--accent, #6366f1); color: #fff; font-size: 0.7rem; font-weight: 600; }
.node-name { font-weight: 500; font-size: 0.85rem; }
.node-type-tag { margin-left: auto; font-size: 0.7rem; color: var(--text-secondary, #64748b); }
.node-error { font-size: 0.78rem; color: #ef4444; margin: 4px 0; word-break: break-all; }
.node-output { margin: 4px 0; }
.mono-label { font-size: 0.7rem; color: var(--text-tertiary, #94a3b8); }
.node-meta { display: flex; gap: 12px; font-size: 0.7rem; color: var(--text-tertiary, #94a3b8); margin-top: 4px; }
.node-detail-body { border-top: 1px solid var(--border, rgba(0,0,0,0.05)); padding: 10px 0 4px; margin-top: 6px; }
.node-output-section { margin-top: 6px; }
.node-output-row { margin-bottom: 6px; }
.node-output-key { font-size: 0.72rem; font-weight: 600; color: var(--text-secondary, #64748b); display: block; margin-bottom: 2px; }
.code-sm { max-height: 120px; font-size: 0.7rem; margin: 2px 0; }
.node-actions { display: flex; gap: 6px; margin-top: 8px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { opacity: 0.9; }
.btn-outline { background: transparent; color: var(--text, #1e293b); border: 1px solid var(--border, rgba(0,0,0,0.2)); }
.btn-outline:hover { background: rgba(0,0,0,0.04); }
.node-awaiting-bar { display: flex; align-items: center; gap: 10px; padding: 8px 10px; background: rgba(245,158,11,0.08); border: 1px solid rgba(245,158,11,0.2); border-radius: 6px; margin-bottom: 8px; font-size: 0.82rem; color: #92400e; }
.node-awaiting-bar .btn { margin-left: auto; }
.force-confirm-hint { color: #b91c1c; font-weight: 600; font-size: 0.78rem; }
</style>
