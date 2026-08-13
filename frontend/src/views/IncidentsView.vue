<template>
  <div class="incidents-page">
    <div class="page-header">
      <h1>故障单管理</h1>
      <p>基于资产维度自动关联告警、归并故障单 · 共 {{ total }} 条</p>
    </div>

    <div class="toolbar">
      <select v-model="filters.status" @change="onStatusChange">
        <option value="">全部状态</option>
        <option value="open">进行中</option>
        <option value="resolved">已解决</option>
      </select>
      <button class="btn" @click="loadIncidents">刷新</button>
      
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="incidents.length" class="table">
          <colgroup>
            <col style="width:60px" />
            <col />
            <col style="width:70px" />
            <col style="width:80px" />
            <col style="width:80px" />
            <col style="width:140px" />
            <col style="width:100px" />
            <col style="width:470px" />
          </colgroup>
          <thead>
            <tr>
              <th>ID</th><th>标题</th><th>级别</th><th>状态</th>
              <th>关联告警</th><th>资产</th><th>时间</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="inc in incidents" :key="inc.id">
              <td>{{ inc.id }}</td>
              <td class="title-cell" @click="showDetail(inc.id)">{{ inc.title }}</td>
              <td><span class="badge" :class="inc.severity">{{ severityCn(inc.severity) }}</span></td>
              <td><span class="badge" :class="inc.status === 'open' ? 'triggered' : inc.status === 'pending_approval' ? 'acknowledged' : 'resolved'">{{ statusCn(inc.status) }}</span></td>
              <td>{{ inc.alert_count }}</td>
              <td>{{ inc.asset_name || inc.asset_id || '-' }}</td>
              <td class="text-sm">{{ formatTime(inc.created_at) }}</td>
              <td class="actions-cell">
                <button v-if="inc.status === 'open'" class="btn btn-sm btn-primary" @click="resolveIncident(inc.id)">解决</button>
                <button class="btn btn-sm" @click="quickRca(inc.id)">根因分析</button>
                <button class="btn btn-sm btn-ai" :disabled="!!aiRcaLoading[inc.id]" @click="quickAiRca(inc.id)">{{ aiRcaLoading[inc.id] ? 'AI 分析中...' : 'AI 深度分析' }}</button>
                <button class="btn btn-sm btn-investigate" :disabled="!!investigateLoading[inc.id]" @click="quickInvestigate(inc.id)">{{ investigateLoading[inc.id] ? '调查中...' : '自动调查' }}</button>
                <button class="btn btn-sm btn-sop" :disabled="!!sopGenerating[inc.id]" @click="quickSop(inc.id)">{{ sopGenerating[inc.id] ? '生成中...' : '生成 SOP' }}</button>
                <button class="btn btn-sm" @click="showDetail(inc.id)">详情</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">📋</div>
          <div>暂无故障单</div>
        </div>
      </div>
    </div>

    <div v-if="totalPages > 1" class="pagination">
      <button class="btn btn-sm" :disabled="filters.page <= 1" @click="goPage(1)">首页</button>
      <button class="btn btn-sm" :disabled="filters.page <= 1" @click="goPage(filters.page - 1)">上一页</button>
      <span v-for="p in pageNumbers" :key="p" class="page-num" :class="{ active: p === filters.page }" @click="goPage(p)">{{ p }}</span>
      <button class="btn btn-sm" :disabled="filters.page >= totalPages" @click="goPage(filters.page + 1)">下一页</button>
      <button class="btn btn-sm" :disabled="filters.page >= totalPages" @click="goPage(totalPages)">末页</button>
      <span class="page-jump">跳转 <input type="number" class="page-input" v-model.number="jumpPage" min="1" :max="totalPages" @keyup.enter="goPage(jumpPage)" /> 页</span>
      <span class="page-info">共 {{ total }} 条 / {{ totalPages }} 页</span>
    </div>

    <div v-if="detailVisible" class="modal-overlay" @click.self="detailVisible = false">
      <div class="modal-box">
        <div class="modal-header">
          <h3>故障单 #{{ detail?.id }} 详情</h3>
          <button class="modal-close" @click="detailVisible = false">×</button>
        </div>
        <div v-if="detail" class="modal-body">
          <div class="detail-grid">
            <div class="detail-item"><span class="detail-label">标题</span><span class="detail-value">{{ detail.incident.title }}</span></div>
            <div class="detail-item"><span class="detail-label">级别</span><span><span class="badge" :class="detail.incident.severity">{{ severityCn(detail.incident.severity) }}</span></span></div>
            <div class="detail-item"><span class="detail-label">状态</span><span><span class="badge" :class="detail.incident.status === 'open' ? 'triggered' : detail.incident.status === 'pending_approval' ? 'acknowledged' : 'resolved'">{{ statusCn(detail.incident.status) }}</span></span></div>
            <div class="detail-item"><span class="detail-label">关联告警</span><span class="detail-value">{{ detail.incident.alert_count }} 条</span></div>
            <div class="detail-item"><span class="detail-label">关联资产</span><span class="detail-value">{{ detail.asset ? detail.asset.name + ' (' + detail.asset.ip + ')' : '-' }}</span></div>
            <div class="detail-item"><span class="detail-label">创建时间</span><span class="detail-value">{{ detail.incident.created_at }}</span></div>
            <div v-if="detail.incident.resolved_at" class="detail-item"><span class="detail-label">解决时间</span><span class="detail-value">{{ detail.incident.resolved_at }}</span></div>
          </div>
          <div class="detail-actions">
            <button v-if="detail.incident.status === 'open'" class="btn btn-primary" @click="resolveFromDetail">解决故障单</button>
            <button class="btn" @click="doRca">根因分析</button>
            <button class="btn btn-ai" :disabled="!!aiRcaLoading[detail.incident.id]" @click="doAiRca()">{{ aiRcaLoading[detail.incident.id] ? 'AI 分析中...' : (aiRcaResult ? 'AI 深度分析' : 'AI 深度分析') }}</button>
            <button v-if="aiRcaResult && !aiRcaLoading[detail.incident.id]" class="btn btn-ai" style="opacity:0.75" @click="reAnalyze">重新分析</button>
            <button class="btn btn-investigate" :disabled="!!investigateLoading[detail.incident.id]" @click="triggerInvestigate(detail.incident.id)">{{ investigateLoading[detail.incident.id] ? '调查中...' : '自动调查' }}</button>
            <button class="btn btn-sop" :disabled="!!sopGenerating[detail.incident.id]" @click="generateSop(detail.incident.id)">{{ sopGenerating[detail.incident.id] ? '生成中...' : '生成 SOP 知识' }}</button>
          </div>
          <h4 class="sub-title">关联告警 ({{ detail.alerts.length }})</h4>
          <table class="table inner-table">
            <thead>
              <tr><th>ID</th><th>指标</th><th>级别</th><th>状态</th><th>时间</th></tr>
            </thead>
            <tbody>
              <tr v-for="a in detail.alerts" :key="a.id">
                <td>{{ a.id }}</td>
                <td>{{ a.metric_name }}</td>
                <td><span class="badge" :class="a.severity">{{ a.severity }}</span></td>
                <td><span class="badge" :class="a.status">{{ a.status }}</span></td>
                <td class="text-sm">{{ formatTime(a.created_at) }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="rcaResult" class="rca-box">
            <h4>根因分析</h4>
            <div class="rca-report" v-html="rcaResult"></div>
          </div>
          <div v-if="aiRcaResult" class="rca-box ai-rca-box">
            <h4>🤖 AI 深度分析</h4>
            <div class="ai-rca-content" v-html="aiRcaResult"></div>
          </div>

          <div v-if="investigation" class="rca-box inv-box">
            <h4>🧭 自动调查报告
              <span class="inv-status" :class="investigation.status">
                {{ { running: '调查中...', completed: '已完成', failed: '失败' }[investigation.status] || investigation.status }}
              </span>
            </h4>
            <div v-if="investigation.status === 'failed'" class="inv-error">{{ investigation.error_message || '调查失败' }}</div>
            <div v-else class="inv-content" v-html="invMd"></div>
          </div>

          </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import MarkdownIt from 'markdown-it'
import request from '@/api/request'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

const loading = ref(false)
const incidents = ref([])
const total = ref(0)
const totalPages = ref(1)
const filters = reactive({ status: '', page: 1 })
const jumpPage = ref(1)
const detailVisible = ref(false)
const detail = ref(null)
const rcaResult = ref('')
const aiRcaResult = ref('')
const aiRcaLoading = ref({})   // 按 incident id 跟踪，避免全局联动
const sopGenerating = ref({})  // 按 incident id 跟踪
const investigateLoading = ref({})  // 自动调查触发状态
const investigation = ref(null)      // 最新自动调查报告
const invMd = ref('')

const pageNumbers = computed(() => {
  const pages = []
  const cur = filters.page
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
  if (p < 1 || p > totalPages.value || p === filters.page) return
  filters.page = p
  loadIncidents()
}

function onStatusChange() {
  filters.page = 1
  loadIncidents()
}

async function loadIncidents() {
  loading.value = true
  try {
    const data = await request.get('/incidents/api/list', { params: { status: filters.status, page: filters.page, per_page: 20 } })
    incidents.value = data.incidents || []
    total.value = data.total || 0
    totalPages.value = data.total_pages || 1
  } catch (e) {
    ElMessage.error('加载故障单失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

async function showDetail(id) {
  rcaResult.value = ''
  aiRcaResult.value = ''
  investigation.value = null
  invMd.value = ''
  try {
    const data = await request.get(`/incidents/api/${id}`)
    detail.value = data
    detailVisible.value = true
    // 若已有 AI 分析缓存，直接展示，避免重复消耗 LLM
    if (data.incident?.ai_rca_result) {
      aiRcaResult.value = md.render(data.incident.ai_rca_result)
    } else {
      aiRcaResult.value = ''
    }
    loadInvestigation(id)
  } catch (e) {
    ElMessage.error('加载详情失败: ' + e.message)
  }
}

async function loadInvestigation(id) {
  try {
    const data = await request.get('/incidents/api/reports/investigation', { params: { incident_id: id, limit: 5 } })
    const items = data.items || []
    const latest = items[0] || null
    investigation.value = latest
    if (latest) {
      invMd.value = md.render(latest.report_md || '')
    }
  } catch (e) {
    // 报告列表加载失败不阻断详情
  }
}

async function triggerInvestigate(id) {
  investigateLoading.value[id] = true
  try {
    const data = await request.post(`/incidents/api/${id}/investigate`, {})
    if (data.ok === false) { ElMessage.error(data.error || '启动调查失败'); return }
    ElMessage.success('自动调查已启动，正在分析中...')
    // 轮询等待报告完成（最多 5 次）
    for (let i = 0; i < 5; i++) {
      await new Promise(r => setTimeout(r, 5000))
      await loadInvestigation(id)
      if (investigation.value && investigation.value.status === 'completed') {
        ElMessage.success('自动调查报告已生成')
        break
      }
    }
  } catch (e) {
    ElMessage.error('启动调查失败: ' + (e.message || e))
  } finally {
    investigateLoading.value[id] = false
  }
}

async function resolveIncident(id) {
  try {
    await ElMessageBox.confirm('确认解决此故障单？', '解决故障单')
    await request.post(`/incidents/api/${id}/resolve`)
    ElMessage.success('已解决')
    loadIncidents()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('解决失败: ' + (e.message || e))
  }
}

async function resolveFromDetail() {
  if (!detail.value) return
  try {
    await request.post(`/incidents/api/${detail.value.incident.id}/resolve`)
    ElMessage.success('已解决')
    detailVisible.value = false
    loadIncidents()
  } catch (e) {
    ElMessage.error('解决失败: ' + e.message)
  }
}

async function doRca() {
  if (!detail.value) return
  try {
    const data = await request.get(`/incidents/api/${detail.value.incident.id}/rca`)
    const analysis = data.analysis
    if (analysis && analysis.report) {
      rcaResult.value = md.render(analysis.report)
    } else if (typeof analysis === 'string') {
      rcaResult.value = md.render(analysis)
    } else {
      rcaResult.value = md.render('```\n' + JSON.stringify(analysis, null, 2) + '\n```')
    }
  } catch (e) {
    ElMessage.error('根因分析失败: ' + e.message)
  }
}

async function doAiRca(force = false) {
  if (!detail.value) return
  const id = detail.value.incident.id
  aiRcaLoading.value[id] = true
  if (force) aiRcaResult.value = ''  // 强制重新分析时清空旧结果
  try {
    const data = await request.post(`/incidents/api/${id}/ai-rca?force=${force ? 1 : 0}`, {}, { timeout: 130000 })
    if (data.ok === false) { ElMessage.error(data.error || 'AI 分析失败'); return }
    aiRcaResult.value = md.render(data.analysis || '')
    if (data.cached) ElMessage.info('已加载上次 AI 分析结果（' + (data.analyzed_at || '') + '）')
  } catch (e) {
    ElMessage.error('AI 深度分析失败: ' + (e.message || e))
  } finally {
    aiRcaLoading.value[id] = false
  }
}

// 强制重新分析（覆盖缓存）
function reAnalyze() {
  doAiRca(true)
}

async function generateSop(incidentId) {
  sopGenerating.value[incidentId] = true
  try {
    const data = await request.post(`/knowledge/api/auto-gen/sop/incident/${incidentId}`, {}, { timeout: 130000 })
    if (data.ok === false) {
      ElMessage.error(data.error || 'SOP 生成失败')
    } else {
      ElMessage.success('SOP 草稿已生成，请去「AI 知识草稿」审批入库')
    }
  } catch (e) {
    ElMessage.error('SOP 生成失败: ' + (e.message || e))
  } finally {
    sopGenerating.value[incidentId] = false
  }
}

// 列表行快捷操作：打开详情弹窗并自动触发分析（结果在弹窗内展示）
async function quickRca(id) {
  await showDetail(id)
  doRca()
}
async function quickAiRca(id) {
  await showDetail(id)
  doAiRca()
}
function quickSop(id) {
  generateSop(id)
}
async function quickInvestigate(id) {
  await showDetail(id)
  await triggerInvestigate(id)
}



function formatTime(s) {
  if (!s) return '-'
  return s.substring(5, 16)
}

function severityCn(s) {
  return { critical: '严重', warning: '警告', info: '提示' }[s] || s
}

function statusCn(s) {
  return { open: '进行中', resolved: '已解决' }[s] || s
}

onMounted(() => {
  loadIncidents()
})
</script>

<style scoped>
.incidents-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.toolbar select { padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; transition: all 0.2s; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary:disabled, .btn-ai:disabled, .btn-sop:disabled { opacity: 0.6; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; table-layout: fixed; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); vertical-align: middle; word-break: break-word; }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.title-cell { cursor: pointer; color: var(--accent, #6366f1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.title-cell:hover { text-decoration: underline; }
.actions-cell { display: flex; flex-wrap: wrap; gap: 4px; }
.actions-cell .btn { white-space: nowrap; }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.info, .badge.warning { background: rgba(245,158,11,0.1); color: #f59e0b; }
.badge.critical { background: rgba(239,68,68,0.1); color: #ef4444; }
.badge.triggered, .badge.firing { background: rgba(239,68,68,0.1); color: #ef4444; }
.badge.acknowledged { background: rgba(245,158,11,0.1); color: #f59e0b; }
.badge.resolved { background: rgba(34,197,94,0.1); color: #22c55e; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 6px; margin-top: 16px; flex-wrap: wrap; }
.page-info { font-size: 0.82rem; color: var(--text-secondary, #64748b); }
.page-num { display: inline-flex; align-items: center; justify-content: center; min-width: 30px; height: 30px; padding: 0 6px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.8rem; cursor: pointer; transition: all 0.2s; user-select: none; }
.page-num:hover { background: var(--bg-hover, rgba(99,102,241,0.08)); border-color: var(--accent, #6366f1); }
.page-num.active { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); font-weight: 600; }
.page-jump { font-size: 0.8rem; color: var(--text-secondary, #64748b); display: flex; align-items: center; gap: 4px; }
.page-input { width: 50px; padding: 3px 6px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; text-align: center; font-size: 0.8rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 12px; width: 90%; max-width: 800px; max-height: 85vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.2); }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.modal-header h3 { margin: 0; font-size: 1.1rem; }
.modal-close { background: none; border: none; font-size: 24px; cursor: pointer; color: var(--text-secondary, #64748b); line-height: 1; }
.modal-body { padding: 20px; }
.detail-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 16px; }
.detail-item { display: flex; flex-direction: column; gap: 4px; }
.detail-label { font-size: 0.72rem; color: var(--text-secondary, #64748b); text-transform: uppercase; letter-spacing: 0.3px; }
.detail-value { font-size: 0.88rem; color: var(--text, #1e293b); }
.detail-actions { display: flex; gap: 8px; margin-bottom: 16px; }
.sub-title { font-size: 0.95rem; margin: 16px 0 8px; color: var(--text, #1e293b); }
.inner-table { font-size: 0.82rem; }
.rca-box { margin-top: 16px; background: var(--bg-hover, rgba(0,0,0,0.03)); border-radius: 8px; padding: 12px; }
.rca-box h4 { margin: 0 0 8px; font-size: 0.9rem; }
.rca-box pre { margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 0.78rem; color: var(--text, #1e293b); }
.rca-report { font-size: 0.85rem; line-height: 1.7; color: var(--text, #1e293b); }
.rca-report :deep(h1), .rca-report :deep(h2), .rca-report :deep(h3), .rca-report :deep(h4) { margin: 14px 0 6px; font-weight: 600; }
.rca-report :deep(h2) { font-size: 1.05rem; color: #6366f1; }
.rca-report :deep(h3) { font-size: 0.92rem; }
.rca-report :deep(p) { margin: 6px 0; }
.rca-report :deep(ul), .rca-report :deep(ol) { padding-left: 20px; margin: 6px 0; }
.rca-report :deep(li) { margin-bottom: 4px; }
.rca-report :deep(strong) { color: #6366f1; }
.rca-report :deep(code) { background: rgba(99,102,241,0.1); padding: 1px 4px; border-radius: 3px; font-size: 0.8rem; color: #6366f1; }
.rca-report :deep(table) { border-collapse: collapse; margin: 8px 0; width: 100%; }
.rca-report :deep(th), .rca-report :deep(td) { border: 1px solid var(--border, rgba(0,0,0,0.1)); padding: 4px 8px; font-size: 0.8rem; }
.rca-report :deep(th) { background: rgba(99,102,241,0.06); font-weight: 600; }
.rca-report :deep(blockquote) { border-left: 3px solid #6366f1; padding: 6px 12px; margin: 8px 0; background: rgba(99,102,241,0.04); border-radius: 0 6px 6px 0; }
.btn-ai { background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff; border: none; }
.btn-ai:hover:not(:disabled) { background: linear-gradient(135deg, #4f46e5, #7c3aed); }
.btn-sop { background: rgba(34,197,94,0.1); color: #22c55e; border-color: rgba(34,197,94,0.3); font-weight: 600; }
.btn-investigate { background: rgba(6,182,212,0.1); color: #06b6d4; border-color: rgba(6,182,212,0.35); font-weight: 600; }
.btn-investigate:hover:not(:disabled) { background: rgba(6,182,212,0.18); }
.inv-box { background: rgba(6,182,212,0.04); border: 1px solid rgba(6,182,212,0.18); }
.inv-box h4 { color: #0891b2; display: flex; align-items: center; gap: 8px; }
.inv-status { font-size: 0.7rem; font-weight: 600; padding: 2px 8px; border-radius: 8px; }
.inv-status.completed { background: rgba(34,197,94,0.12); color: #16a34a; }
.inv-status.running { background: rgba(6,182,212,0.12); color: #0891b2; }
.inv-status.failed { background: rgba(239,68,68,0.12); color: #ef4444; }
.inv-error { color: #ef4444; font-size: 0.82rem; }
.inv-content { font-size: 0.85rem; line-height: 1.7; color: var(--text, #1e293b); }
.inv-content :deep(h1), .inv-content :deep(h2), .inv-content :deep(h3), .inv-content :deep(h4) { margin: 14px 0 6px; font-weight: 600; }
.inv-content :deep(h2) { font-size: 1rem; color: #0891b2; }
.inv-content :deep(h3) { font-size: 0.92rem; }
.inv-content :deep(p) { margin: 6px 0; }
.inv-content :deep(ul), .inv-content :deep(ol) { padding-left: 20px; margin: 6px 0; }
.inv-content :deep(li) { margin-bottom: 4px; }
.inv-content :deep(strong) { color: #0891b2; }
.inv-content :deep(code) { background: rgba(6,182,212,0.1); padding: 1px 4px; border-radius: 3px; font-size: 0.8rem; color: #0891b2; }
.ai-rca-box { background: linear-gradient(135deg, rgba(99,102,241,0.04), rgba(139,92,246,0.08)); border: 1px solid rgba(99,102,241,0.15); }
.ai-rca-box h4 { color: #6366f1; }
.ai-rca-content { font-size: 0.85rem; line-height: 1.7; color: var(--text, #1e293b); }
.ai-rca-content :deep(h1), .ai-rca-content :deep(h2), .ai-rca-content :deep(h3), .ai-rca-content :deep(h4) { margin: 14px 0 6px; font-weight: 600; }
.ai-rca-content :deep(h1) { font-size: 1.1rem; }
.ai-rca-content :deep(h2) { font-size: 1rem; color: #6366f1; }
.ai-rca-content :deep(h3) { font-size: 0.92rem; }
.ai-rca-content :deep(h4) { font-size: 0.85rem; }
.ai-rca-content :deep(p) { margin: 6px 0; }
.ai-rca-content :deep(ul), .ai-rca-content :deep(ol) { padding-left: 20px; margin: 6px 0; }
.ai-rca-content :deep(li) { margin-bottom: 4px; }
.ai-rca-content :deep(strong) { color: #6366f1; }
.ai-rca-content :deep(code) { background: rgba(99,102,241,0.1); padding: 1px 4px; border-radius: 3px; font-size: 0.8rem; }
</style>
