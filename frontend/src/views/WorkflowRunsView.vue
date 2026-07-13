<template>
  <div class="wf-page">
    <div class="page-header">
      <div class="title-row">
        <div>
          <h1>工作流执行监控</h1>
          <p>SOP 工作流实例实时监控 · 共 {{ total }} 个</p>
        </div>
        <button class="btn btn-guide" @click="showGuide = !showGuide">📖 操作说明</button>
      </div>
    </div>

    <div class="toolbar">
      <select v-model="statusFilter" class="input select-input" @change="onFilterChange">
        <option value="">全部状态</option>
        <option value="running">执行中</option>
        <option value="paused">待确认</option>
        <option value="completed">已完成</option>
        <option value="failed">失败</option>
        <option value="aborted">已中止</option>
      </select>
      <button class="btn" @click="loadRuns">刷新</button>
      <button class="btn btn-primary" @click="openCreate">+ 触发工作流</button>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="runs.length" class="table">
          <thead>
            <tr><th>ID</th><th>标题</th><th>状态</th><th>触发源</th><th>节点进度</th><th>开始时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in runs" :key="r.id">
              <td>#{{ r.id }}</td>
              <td class="title-cell">{{ r.title }}</td>
              <td><span class="badge" :class="statusClass(r.status)">{{ statusLabel(r.status) }}</span></td>
              <td><span class="badge src-badge">{{ r.trigger_source }}</span></td>
              <td>
                <span class="progress-text">
                  {{ nodeProgress(r) }}
                </span>
              </td>
              <td>{{ r.started_at || r.created_at || '-' }}</td>
              <td class="ops">
                <button class="btn btn-sm" @click="openDetail(r.id)">详情</button>
                <button v-if="canAbort(r)" class="btn btn-sm btn-danger" @click="abortRun(r)">中止</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">⚙️</div><div>暂无工作流实例</div></div>
        <div v-if="totalPages > 1" class="pagination">
          <button class="btn btn-sm" :disabled="currentPage <= 1" @click="goPage(1)">首页</button>
          <button class="btn btn-sm" :disabled="currentPage <= 1" @click="goPage(currentPage - 1)">上一页</button>
          <span v-for="p in pageNumbers" :key="p" class="page-num" :class="{ active: p === currentPage }" @click="goPage(p)">{{ p }}</span>
          <button class="btn btn-sm" :disabled="currentPage >= totalPages" @click="goPage(currentPage + 1)">下一页</button>
          <button class="btn btn-sm" :disabled="currentPage >= totalPages" @click="goPage(totalPages)">末页</button>
          <span class="page-jump">跳转 <input type="number" class="page-input" v-model.number="jumpPage" min="1" :max="totalPages" @keyup.enter="goPage(jumpPage)" /> 页</span>
          <span class="page-info">共 {{ total }} 条 / {{ totalPages }} 页</span>
        </div>
      </div>
    </div>

    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal-box wide">
        <h3>触发工作流</h3>
        <div class="form-row"><label>选择 SOP 模板</label>
          <select v-model="createForm.template_id" class="input">
            <option :value="null">-- 自定义节点 --</option>
            <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }} ({{ t.category }})</option>
          </select>
        </div>
        <div class="form-row"><label>工作流标题</label><input v-model="createForm.title" class="input" placeholder="工作流标题"></div>
        <div class="form-row"><label>运行时上下文 (JSON)</label>
          <textarea v-model="createForm.contextStr" class="input textarea" rows="4" placeholder='{"asset_id": 1, "alert_id": 5, "service_name": "nginx"}'></textarea>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" @click="createRun">触发</button>
        </div>
      </div>
    </div>

    <div v-if="showDetail" class="modal-overlay" @click.self="closeDetail">
      <div class="modal-box xwide">
        <h3>工作流 #{{ detail.id }} — {{ detail.title }}</h3>
        <div class="detail-summary">
          <div class="summary-item"><span class="summary-label">状态</span><span class="badge" :class="statusClass(detail.status)">{{ statusLabel(detail.status) }}</span></div>
          <div class="summary-item"><span class="summary-label">触发源</span><span>{{ detail.trigger_source }}</span></div>
          <div class="summary-item"><span class="summary-label">开始</span><span>{{ detail.started_at || '-' }}</span></div>
          <div class="summary-item"><span class="summary-label">完成</span><span>{{ detail.completed_at || '-' }}</span></div>
        </div>
        <div class="detail-block">
          <div class="detail-label">上下文</div>
          <pre class="code-block">{{ JSON.stringify(detail.context || {}, null, 2) }}</pre>
        </div>
        <div class="detail-block">
          <div class="detail-label">节点执行状态</div>
          <div class="node-flow">
            <div v-for="(nr, idx) in (detail.node_runs || [])" :key="nr.id" class="node-card" :class="nodeStatusClass(nr.status)">
              <div class="node-header">
                <span class="node-idx">{{ idx + 1 }}</span>
                <span class="node-name">{{ nr.node_name || nr.node_id }}</span>
                <span class="badge" :class="nodeStatusBadge(nr.status)">{{ nodeStatusLabel(nr.status) }}</span>
                <span v-if="nr.requires_confirm" class="badge confirm-badge">需确认</span>
                <span class="node-action">{{ nr.action_type }}</span>
              </div>
              <div class="node-payload"><span class="mono-label">payload:</span><code>{{ JSON.stringify(nr.payload) }}</code></div>
              <div v-if="nr.result && Object.keys(nr.result).length" class="node-result"><span class="mono-label">result:</span><pre class="code-block small">{{ JSON.stringify(nr.result, null, 2) }}</pre></div>
              <div class="node-meta">
                <span v-if="nr.started_at">开始: {{ nr.started_at }}</span>
                <span v-if="nr.completed_at">完成: {{ nr.completed_at }}</span>
              </div>
              <div v-if="nr.status === 'awaiting_confirm'" class="node-actions">
                <button class="btn btn-sm btn-primary" @click="confirmNode(nr)">确认执行</button>
                <button class="btn btn-sm btn-danger" @click="cancelNode(nr)">取消</button>
              </div>
              <div v-if="nr.status === 'failed'" class="node-actions">
                <button class="btn btn-sm" @click="retryNode(nr)">重试</button>
              </div>
            </div>
          </div>
        </div>
        <div class="modal-actions">
          <button v-if="canAbort(detail)" class="btn btn-danger" @click="abortRun(detail)">中止工作流</button>
          <button class="btn" @click="closeDetail">关闭</button>
        </div>
      </div>
    </div>

    <GuideDrawer v-model="showGuide" title="📖 工作流执行监控 · 操作说明">
      <section class="guide-section">
        <h4>1. 目的</h4>
        <p>工作流执行监控用于查看和管理所有<strong>SOP 工作流</strong>的运行实例。当告警触发或人工触发工作流后，每个执行实例都会在此页面实时显示运行状态、节点进度和输出结果。</p>
      </section>
      <section class="guide-section">
        <h4>2. 操作步骤</h4>
        <ul>
          <li><strong>触发工作流</strong> — 点击右上角「+ 触发工作流」，选择 SOP 模板（如告警响应、巡检报告），填入运行时上下文 JSON，点击「触发」</li>
          <li><strong>查看运行状态</strong> — 表格中实时显示每个工作流实例的状态（执行中/待确认/已完成/失败/已中止），节点进度列显示当前执行到第几个节点</li>
          <li><strong>查看详情</strong> — 点击「详情」按钮可看到每个节点的输入参数、执行结果、耗时和错误信息</li>
          <li><strong>中止工作流</strong> — 对执行中的工作流点击「中止」可强制终止，剩余节点将被跳过</li>
          <li><strong>按状态筛选</strong> — 顶部状态下拉框可筛选只看「执行中」「已完成」「失败」等特定状态的工作流</li>
        </ul>
      </section>
      <section class="guide-section">
        <h4>3. 运行时上下文说明</h4>
        <p>触发工作流时需要填入上下文 JSON，对应 SOP 模板的输入参数。常用字段：<code>asset_id</code>（资产ID）、<code>alert_id</code>（告警ID）、<code>service_name</code>（服务名）等，具体以所选模板的输入定义为准。</p>
      </section>
      <section class="guide-section">
        <h4>4. 实现了什么</h4>
        <p>统一管理所有工作流的执行生命周期，实现<strong>监控告警→触发SOP→自动执行→结果记录</strong>的完整闭环。每个执行步骤、输入输出、耗时均有记录，便于事后审计和问题追溯。</p>
      </section>
    </GuideDrawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GuideDrawer from '@/components/GuideDrawer.vue'
import request from '@/api/request'

const loading = ref(false)
const showGuide = ref(false)
const runs = ref([])
const total = ref(0)
const statusFilter = ref('')
const templates = ref([])
const showCreate = ref(false)
const createForm = ref({ template_id: null, title: '', contextStr: '{}' })
const showDetail = ref(false)
const detail = ref({})
let pollTimer = null

const currentPage = ref(1)
const pageSize = ref(20)
const totalPages = ref(1)
const jumpPage = ref(1)
const pageNumbers = computed(() => {
  const pages = []
  const cur = currentPage.value
  const tp = totalPages.value
  if (tp <= 7) {
    for (let i = 1; i <= tp; i++) pages.push(i)
  } else {
    pages.push(1)
    if (cur > 4) pages.push('...')
    const start = Math.max(2, cur - 1)
    const end = Math.min(tp - 1, cur + 1)
    for (let i = start; i <= end; i++) pages.push(i)
    if (cur < tp - 3) pages.push('...')
    pages.push(tp)
  }
  return pages
})
function goPage(p) {
  if (p < 1 || p > totalPages.value || p === currentPage.value) return
  currentPage.value = p
  loadRuns()
}

function onFilterChange() {
  currentPage.value = 1
  loadRuns()
}

async function loadRuns() {
  loading.value = true
  try {
    const params = { page: currentPage.value, per_page: pageSize.value }
    if (statusFilter.value) params.status = statusFilter.value
    const data = await request.get('/workflow/api/runs', { params })
    runs.value = data.items || []
    total.value = data.total || 0
    totalPages.value = data.total_pages || 1
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

async function loadTemplates() {
  try {
    const data = await request.get('/workflow/api/templates', { params: { only_enabled: true } })
    templates.value = data.items || []
  } catch (e) {
    console.error('load templates:', e)
  }
}

async function openCreate() {
  if (!templates.value.length) await loadTemplates()
  createForm.value = { template_id: null, title: '', contextStr: '{}' }
  showCreate.value = true
}

async function createRun() {
  try {
    let context = {}
    try { context = JSON.parse(createForm.value.contextStr || '{}') } catch (e) {
      ElMessage.warning('上下文 JSON 格式错误')
      return
    }
    const payload = { title: createForm.value.title, context }
    if (createForm.value.template_id) payload.template_id = createForm.value.template_id
    const data = await request.post('/workflow/api/runs/create', payload)
    ElMessage.success(`工作流 #${data.id} 已创建`)
    showCreate.value = false
    loadRuns()
    openDetail(data.id)
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.message || e))
  }
}

async function openDetail(id) {
  try {
    detail.value = await request.get(`/workflow/api/runs/${id}`)
    showDetail.value = true
  } catch (e) {
    ElMessage.error('获取详情失败: ' + (e.message || e))
  }
}

function closeDetail() {
  showDetail.value = false
  detail.value = {}
}

async function confirmNode(nr) {
  try {
    await ElMessageBox.confirm(`确认执行节点「${nr.node_name || nr.node_id}」？此操作将调用 ${nr.action_type} 工具。`, '节点确认', { type: 'warning' })
    await request.post(`/workflow/api/runs/${nr.run_id}/node/${nr.id}/confirm`)
    ElMessage.success('节点已确认执行')
    detail.value = await request.get(`/workflow/api/runs/${nr.run_id}`)
    loadRuns()
  } catch (e) {
    if (e !== 'cancel' && e?.message !== 'cancel') {
      ElMessage.error('确认失败: ' + (e.message || e))
    }
  }
}

async function cancelNode(nr) {
  try {
    await ElMessageBox.confirm(`取消节点「${nr.node_name}」？取消后整个工作流将被中止。`, '取消节点', { type: 'warning' })
    await request.post(`/workflow/api/runs/${nr.run_id}/node/${nr.id}/cancel`, { reason: '用户取消' })
    ElMessage.success('节点已取消')
    detail.value = await request.get(`/workflow/api/runs/${nr.run_id}`)
    loadRuns()
  } catch (e) {
    if (e !== 'cancel' && e?.message !== 'cancel') {
      ElMessage.error('取消失败: ' + (e.message || e))
    }
  }
}

async function retryNode(nr) {
  try {
    await request.post(`/workflow/api/runs/${nr.run_id}/node/${nr.id}/retry`)
    ElMessage.success('节点已重试')
    detail.value = await request.get(`/workflow/api/runs/${nr.run_id}`)
    loadRuns()
  } catch (e) {
    ElMessage.error('重试失败: ' + (e.message || e))
  }
}

async function abortRun(r) {
  try {
    await ElMessageBox.confirm(`中止工作流 #${r.id}「${r.title}」？未完成的节点将被跳过。`, '中止工作流', { type: 'warning' })
    await request.post(`/workflow/api/runs/${r.id}/abort`, { reason: '用户手动中止' })
    ElMessage.success('工作流已中止')
    if (showDetail.value && detail.value.id === r.id) {
      detail.value = await request.get(`/workflow/api/runs/${r.id}`)
    }
    loadRuns()
  } catch (e) {
    if (e !== 'cancel' && e?.message !== 'cancel') {
      ElMessage.error('中止失败: ' + (e.message || e))
    }
  }
}

function statusClass(s) {
  return { 'st-running': s === 'running', 'st-paused': s === 'paused', 'st-completed': s === 'completed', 'st-failed': s === 'failed', 'st-aborted': s === 'aborted', 'st-pending': s === 'pending' }
}
function statusLabel(s) {
  return { running: '执行中', paused: '待确认', completed: '已完成', failed: '失败', aborted: '已中止', pending: '等待' }[s] || s
}
function nodeStatusClass(s) {
  return { 'nr-completed': s === 'completed', 'nr-failed': s === 'failed', 'nr-awaiting': s === 'awaiting_confirm', 'nr-running': s === 'running', 'nr-skipped': s === 'skipped', 'nr-pending': s === 'pending' }
}
function nodeStatusBadge(s) {
  return { 'st-completed': s === 'completed', 'st-failed': s === 'failed', 'st-paused': s === 'awaiting_confirm', 'st-running': s === 'running', 'st-aborted': s === 'skipped', 'st-pending': s === 'pending' }
}
function nodeStatusLabel(s) {
  return { completed: '已完成', failed: '失败', awaiting_confirm: '待确认', running: '执行中', skipped: '已跳过', pending: '等待' }[s] || s
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

onMounted(() => {
  loadRuns()
  loadTemplates()
  pollTimer = setInterval(() => {
    if (!showDetail.value) loadRuns()
  }, 5000)
})
onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.wf-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.select-input { min-width: 160px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.title-cell { font-weight: 500; }
.ops { display: flex; gap: 6px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.st-running { background: rgba(99,102,241,0.12); color: #6366f1; }
.badge.st-paused { background: rgba(245,158,11,0.12); color: #f59e0b; }
.badge.st-completed { background: rgba(16,185,129,0.12); color: #10b981; }
.badge.st-failed { background: rgba(239,68,68,0.12); color: #ef4444; }
.badge.st-aborted { background: rgba(100,116,139,0.12); color: #64748b; }
.badge.st-pending { background: rgba(100,116,139,0.12); color: #64748b; }
.badge.confirm-badge { background: rgba(245,158,11,0.12); color: #f59e0b; margin-left: 4px; }
.badge.src-badge { background: rgba(20,184,166,0.12); color: #14b8a6; }
.progress-text { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 6px; margin-top: 16px; flex-wrap: wrap; }
.page-info { font-size: 0.82rem; color: var(--text-secondary, #64748b); }
.page-num { display: inline-flex; align-items: center; justify-content: center; min-width: 30px; height: 30px; padding: 0 6px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.8rem; cursor: pointer; transition: all 0.2s; user-select: none; }
.page-num:hover { background: var(--bg-hover, rgba(99,102,241,0.08)); border-color: var(--accent, #6366f1); }
.page-num.active { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); font-weight: 600; }
.page-jump { font-size: 0.8rem; color: var(--text-secondary, #64748b); display: flex; align-items: center; gap: 4px; }
.page-input { width: 50px; padding: 3px 6px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; text-align: center; font-size: 0.8rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 380px; max-width: 90vw; max-height: 90vh; overflow-y: auto; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-box.wide { min-width: 560px; }
.modal-box.xwide { min-width: 720px; }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; color: var(--text, #1e293b); }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.textarea { resize: vertical; font-family: inherit; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.detail-summary { display: flex; flex-wrap: wrap; gap: 16px; padding: 12px; background: var(--bg-hover, rgba(0,0,0,0.03)); border-radius: 8px; margin-bottom: 12px; }
.summary-item { display: flex; gap: 6px; align-items: center; font-size: 0.82rem; }
.summary-label { color: var(--text-secondary, #64748b); font-size: 0.75rem; }
.detail-block { margin: 10px 0; }
.detail-label { font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 6px; font-weight: 600; }
.code-block { background: rgba(0,0,0,0.04); border-radius: 6px; padding: 8px 10px; font-size: 0.75rem; font-family: 'Consolas', monospace; white-space: pre-wrap; word-break: break-all; margin: 4px 0; max-height: 200px; overflow-y: auto; }
.code-block.small { font-size: 0.7rem; max-height: 150px; }
.node-flow { display: flex; flex-direction: column; gap: 10px; }
.node-card { border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; padding: 10px 12px; background: var(--bg-card, #fff); }
.node-card.nr-completed { border-left: 3px solid #10b981; }
.node-card.nr-failed { border-left: 3px solid #ef4444; }
.node-card.nr-awaiting { border-left: 3px solid #f59e0b; background: rgba(245,158,11,0.04); }
.node-card.nr-running { border-left: 3px solid #6366f1; }
.node-card.nr-skipped { border-left: 3px solid #94a3b8; opacity: 0.7; }
.node-card.nr-pending { border-left: 3px solid #cbd5e1; }
.node-header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
.node-idx { display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; border-radius: 50%; background: var(--accent, #6366f1); color: #fff; font-size: 0.7rem; font-weight: 600; }
.node-name { font-weight: 500; font-size: 0.85rem; color: var(--text, #1e293b); }
.node-action { margin-left: auto; font-size: 0.7rem; color: var(--text-secondary, #64748b); font-family: 'Consolas', monospace; background: rgba(99,102,241,0.08); padding: 1px 6px; border-radius: 4px; }
.node-payload { font-size: 0.75rem; color: var(--text-secondary, #64748b); margin: 4px 0; word-break: break-all; }
.node-payload code { font-family: 'Consolas', monospace; background: rgba(0,0,0,0.04); padding: 1px 4px; border-radius: 3px; font-size: 0.72rem; }
.mono-label { font-size: 0.7rem; color: var(--text-tertiary, #94a3b8); margin-right: 4px; }
.node-result { margin: 4px 0; }
.node-meta { display: flex; gap: 12px; font-size: 0.7rem; color: var(--text-tertiary, #94a3b8); margin-top: 4px; }
.node-actions { display: flex; gap: 6px; margin-top: 8px; }
.wf-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.title-row { display: flex; align-items: center; gap: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
</style>
