<template>
  <div class="alerts-page">
    <div class="page-header">
      <h1>告警中心</h1>
      <p>告警事件列表 · 共 {{ total }} 条</p>
    </div>

    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-icon blue">🔔</div>
        <div class="stat-body"><div class="stat-value">{{ stats.total || 0 }}</div><div class="stat-label">全部告警</div></div>
      </div>
      <div class="stat-card danger">
        <div class="stat-icon red">🔴</div>
        <div class="stat-body"><div class="stat-value">{{ stats.triggered || 0 }}</div><div class="stat-label">待处理</div></div>
      </div>
      <div class="stat-card warning">
        <div class="stat-icon yellow">🟡</div>
        <div class="stat-body"><div class="stat-value">{{ stats.acknowledged || 0 }}</div><div class="stat-label">已确认</div></div>
      </div>
      <div class="stat-card success">
        <div class="stat-icon green">✅</div>
        <div class="stat-body"><div class="stat-value">{{ stats.resolved || 0 }}</div><div class="stat-label">已解决</div></div>
      </div>
      <div class="stat-card">
        <div class="stat-icon gray">🛑</div>
        <div class="stat-body"><div class="stat-value">{{ stats.dedup_suppressed || 0 }}</div><div class="stat-label">已收敛</div></div>
      </div>
      <div class="stat-card">
        <div class="stat-icon gray">🌊</div>
        <div class="stat-body"><div class="stat-value">{{ stats.storm_suppressed || 0 }}</div><div class="stat-label">已抑制</div></div>
      </div>
    </div>

    <div class="toolbar">
      <select v-model="filters.status" @change="onFilterChange">
        <option value="">全部状态</option>
        <option value="triggered">已触发</option>
        <option value="acknowledged">已确认</option>
        <option value="resolved">已解决</option>
      </select>
      <select v-model="filters.severity" @change="onFilterChange">
        <option value="">全部级别</option>
        <option value="info">Info</option>
        <option value="warning">Warning</option>
        <option value="critical">Critical</option>
      </select>
      <button class="btn" @click="checkAlerts">触发检查</button>
      <button class="btn" @click="checkK8sEvents">K8S 事件检测</button>
      <div class="batch-actions" v-if="selected.size">
        <span class="batch-tip">已选 {{ selected.size }} 条</span>
        <button class="btn" @click="batchAckSelected">批量确认</button>
        <button class="btn btn-primary" @click="batchResolveSelected">批量解决</button>
        <button class="btn" @click="selected.clear(); selected = selected">取消</button>
      </div>
      <button v-else class="btn" @click="batchAck">全部确认</button>
      <button v-if="!selected.size" class="btn btn-primary" @click="batchResolve">全部解决</button>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="alerts.length" class="table">
          <thead>
            <tr>
              <th class="col-check"><input type="checkbox" :checked="allSelected" @change="toggleAll" /></th>
              <th>ID</th><th>时间</th><th>指标</th><th>当前值</th><th>阈值</th>
              <th>级别</th><th>状态</th><th>消息</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in alerts" :key="a.id" :class="`severity-${a.severity}`">
              <td class="col-check"><input type="checkbox" :checked="selected.has(a.id)" @change="toggleSelect(a.id)" /></td>
              <td>{{ a.id }}</td>
              <td class="text-sm">{{ formatTime(a.created_at) }}</td>
              <td>{{ a.metric_name }}</td>
              <td>{{ a.actual_value }}</td>
              <td>{{ a.threshold }}</td>
              <td><span class="badge" :class="a.severity">{{ a.severity }}</span></td>
              <td><span class="badge" :class="a.status">{{ a.status }}</span></td>
              <td class="text-sm msg-cell">{{ a.message }}</td>
              <td>
                <button v-if="a.status === 'triggered'" class="btn btn-sm" @click="ackAlert(a.id)">确认</button>
                <button v-else-if="a.status === 'acknowledged'" class="btn btn-sm btn-primary" @click="resolveAlert(a.id)">解决</button>
                <button class="btn btn-sm btn-rca" @click="openRca(a.id)">根因分析</button>
                <button class="btn btn-sm btn-ai" @click="openAiRca(a.id)">AI 深度分析</button>
                <button class="btn btn-sm btn-primary" @click="openAssistant(a.id)">💬 智能助手</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">🔕</div>
          <div>暂无告警</div>
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

    <!-- 根因分析弹窗 -->
    <div v-if="rcaVisible" class="modal-overlay" @click.self="rcaVisible = false">
      <div class="modal-box modal-lg">
        <div class="modal-header">
          <h3>根因分析 - 告警 #{{ rcaAlertId }}</h3>
          <button class="modal-close" @click="rcaVisible = false">×</button>
        </div>
        <div v-if="rcaLoading" class="modal-loading">分析中...</div>
        <div v-else-if="rcaData" class="modal-body">
          <div v-if="rcaData.report" class="rca-report" v-html="rcaReportHtml"></div>
          <div v-else>
            <div class="rca-section">
              <div class="rca-title">告警概况</div>
              <div class="rca-grid">
                <div><span class="rca-label">指标:</span> {{ rcaData.alert?.metric_name }}</div>
                <div><span class="rca-label">当前值:</span> {{ rcaData.alert?.actual_value }} / 阈值 {{ rcaData.alert?.threshold }}</div>
                <div><span class="rca-label">级别:</span> <span class="badge" :class="rcaData.alert?.severity">{{ rcaData.alert?.severity }}</span></div>
                <div><span class="rca-label">资产:</span> {{ rcaData.asset?.name || '未知' }} ({{ rcaData.asset?.ip || '-' }})</div>
              </div>
              <div class="rca-msg">{{ rcaData.alert?.message }}</div>
            </div>

            <div v-if="rcaData.root_candidates?.length" class="rca-section">
              <div class="rca-title">上游依赖（可能的根因来源）</div>
              <div v-for="rc in rcaData.root_candidates" :key="rc.id" class="rca-item">
                <span class="rca-dot"></span>{{ rc.name }} <span class="rca-type">{{ rc.ci_type || rc.type }}</span>
              </div>
            </div>

            <div v-if="rcaData.metric_history?.length" class="rca-section">
              <div class="rca-title">指标趋势（最近 {{ rcaData.metric_history.length }} 个数据点）</div>
              <div class="metric-chart">
                <span v-for="(m, i) in rcaData.metric_history" :key="i" class="metric-bar" :style="{ height: metricBarHeight(m.value) + 'px' }" :title="`${m.timestamp}: ${m.value}`"></span>
              </div>
            </div>

            <div v-if="rcaData.related_alerts?.length" class="rca-section">
              <div class="rca-title">同资产近期其他告警 ({{ rcaData.related_alerts.length }})</div>
              <div v-for="ra in rcaData.related_alerts" :key="ra.id" class="rca-item">
                <span class="badge" :class="ra.severity">{{ ra.severity }}</span>
                {{ ra.metric_name }} - {{ ra.message?.substring(0, 80) }}
              </div>
            </div>

            <div v-if="rcaData.k8s_events?.length" class="rca-section">
              <div class="rca-title">关联 K8S 事件 ({{ rcaData.k8s_events.length }})</div>
              <div v-for="ev in rcaData.k8s_events" :key="ev.id" class="rca-item">
                <span class="badge" :class="ev.severity">{{ ev.severity }}</span>
                <strong>{{ ev.reason }}</strong> {{ ev.kind }} {{ ev.namespace }} - {{ ev.message?.substring(0, 100) }}
              </div>
            </div>

            <div v-if="!rcaData.root_candidates?.length && !rcaData.related_alerts?.length && !rcaData.k8s_events?.length" class="rca-empty">
              未发现明显根因线索，建议使用 AI 深度分析获取更多洞察
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- AI 深度分析弹窗 -->
    <div v-if="aiVisible" class="modal-overlay" @click.self="aiVisible = false">
      <div class="modal-box modal-lg">
        <div class="modal-header">
          <h3>AI 深度分析 - 告警 #{{ aiAlertId }}</h3>
          <button class="modal-close" @click="aiVisible = false">×</button>
        </div>
        <div v-if="aiLoading" class="modal-loading">AI 分析中，请稍候...</div>
        <div v-else class="modal-body">
          <div v-if="aiError" class="rca-error">{{ aiError }}</div>
          <div v-else class="ai-result" v-html="aiResult"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'

import { ElMessage, ElMessageBox } from 'element-plus'
import MarkdownIt from 'markdown-it'
import request from '@/api/request'
import { connectAlertsWs, disconnectAlertsWs, onAlert } from '@/utils/websocket'



const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

const loading = ref(false)
const alerts = ref([])
const total = ref(0)
const totalPages = ref(1)
const stats = ref({})
const filters = reactive({ status: '', severity: '', page: 1 })
const jumpPage = ref(1)
const selected = ref(new Set())

const allSelected = computed(() => {
  return alerts.value.length > 0 && alerts.value.every(a => selected.value.has(a.id))
})

function toggleSelect(id) {
  const s = new Set(selected.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  selected.value = s
}

function toggleAll() {
  if (allSelected.value) {
    selected.value = new Set()
  } else {
    selected.value = new Set(alerts.value.map(a => a.id))
  }
}

async function batchAckSelected() {
  if (!selected.value.size) return
  try {
    await ElMessageBox.confirm(`确认将选中的 ${selected.value.size} 条告警标记为已确认？`, '批量确认')
    const ids = [...selected.value]
    await request.post('/alerts/api/batch-acknowledge', { ids })
    ElMessage.success(`已确认 ${ids.length} 条告警`)
    selected.value = new Set()
    loadAlerts()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('批量确认失败: ' + (e.message || e))
  }
}

async function batchResolveSelected() {
  if (!selected.value.size) return
  try {
    await ElMessageBox.confirm(`确认将选中的 ${selected.value.size} 条告警标记为已解决？`, '批量解决')
    const ids = [...selected.value]
    await request.post('/alerts/api/batch-resolve', { ids })
    ElMessage.success(`已解决 ${ids.length} 条告警`)
    selected.value = new Set()
    loadAlerts()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('批量解决失败: ' + (e.message || e))
  }
}

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
  return pages.filter(p => p !== '...' || true)
})

// 根因分析
const rcaVisible = ref(false)
const rcaLoading = ref(false)
const rcaAlertId = ref(null)
const rcaData = ref(null)

const rcaReportHtml = computed(() => {
  return rcaData.value?.report ? md.render(rcaData.value.report) : ''
})

// AI 深度分析
const aiVisible = ref(false)
const aiLoading = ref(false)
const aiAlertId = ref(null)
const aiResult = ref('')
const aiError = ref('')

async function loadAlerts() {
  loading.value = true
  try {
    const data = await request.get('/alerts/api/list', { params: filters })
    alerts.value = data.alerts || []
    total.value = data.total || 0
    totalPages.value = data.total_pages || 1
    stats.value = data.stats || {}
  } catch (e) {
    ElMessage.error('加载告警失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function goPage(p) {
  if (p < 1 || p > totalPages.value || p === filters.page) return
  filters.page = p
  loadAlerts()
}

function onFilterChange() {
  filters.page = 1
  loadAlerts()
}

async function checkAlerts() {
  try {
    const data = await request.post('/alerts/api/check')
    ElMessage.success(`检查完成，新增告警: ${data.new_alerts}`)
    loadAlerts()
  } catch (e) {
    ElMessage.error('检查失败: ' + e.message)
  }
}

async function checkK8sEvents() {
  try {
    const data = await request.post('/alerts/api/check-k8s-events')
    ElMessage.success(`K8S 事件检测完成：扫描 ${data.scanned} 个事件，新增告警 ${data.new_alerts} 条，跳过 ${data.skipped} 条`)
    loadAlerts()
  } catch (e) {
    ElMessage.error('K8S 事件检测失败: ' + e.message)
  }
}

async function batchAck() {
  try {
    await ElMessageBox.confirm('确认将所有已触发告警标记为已确认？', '批量确认')
    const data = await request.post('/alerts/api/batch-acknowledge')
    ElMessage.success(`已确认 ${data.acknowledged} 条告警`)
    loadAlerts()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('批量确认失败: ' + (e.message || e))
  }
}

async function batchResolve() {
  try {
    await ElMessageBox.confirm('确认将所有已确认告警标记为已解决？', '批量解决')
    const data = await request.post('/alerts/api/batch-resolve')
    ElMessage.success(`已解决 ${data.resolved} 条告警`)
    loadAlerts()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('批量解决失败: ' + (e.message || e))
  }
}

async function ackAlert(id) {
  try {
    await request.post(`/alerts/api/${id}/acknowledge`)
    ElMessage.success('已确认')
    loadAlerts()
  } catch (e) {
    ElMessage.error('确认失败: ' + e.message)
  }
}

async function resolveAlert(id) {
  try {
    await request.post(`/alerts/api/${id}/resolve`)
    ElMessage.success('已解决')
    loadAlerts()
  } catch (e) {
    ElMessage.error('解决失败: ' + e.message)
  }
}

async function openRca(id) {
  rcaAlertId.value = id
  rcaVisible.value = true
  rcaLoading.value = true
  rcaData.value = null
  try {
    const data = await request.get(`/alerts/api/${id}/rca`, { timeout: 60000 })
    rcaData.value = data
  } catch (e) {
    ElMessage.error('根因分析失败: ' + (e.message || e))
  } finally {
    rcaLoading.value = false
  }
}

function metricBarHeight(val) {
  const vals = rcaData.value?.metric_history?.map(m => m.value) || []
  if (!vals.length) return 10
  const max = Math.max(...vals, 1)
  const min = Math.min(...vals, 0)
  const range = max - min || 1
  return 10 + ((val - min) / range) * 40
}

async function openAiRca(id) {
  aiAlertId.value = id
  aiVisible.value = true
  aiLoading.value = true
  aiResult.value = ''
  aiError.value = ''
  try {
    const data = await request.post(`/alerts/api/${id}/ai-rca`, {}, { timeout: 120000 })
    if (data.ok === false) {
      aiError.value = data.error || 'AI 分析失败'
    } else {
      aiResult.value = md.render(data.analysis || '')
    }
  } catch (e) {
    aiError.value = 'AI 分析失败: ' + (e.message || e)
  } finally {
    aiLoading.value = false
  }
}

function formatTime(s) {
  if (!s) return '-'
  return s.substring(5, 16)
}

async function openAssistant(alertId) {
  try {
    const data = await request.post(`/alerts/api/${alertId}/open-assistant`)
    if (data.session_id) {
      window._pendingAgentSessionId = data.session_id
      window._navigateTo('agent-chat')
    }
  } catch (e) {
    ElMessage.error('打开助手失败: ' + (e.message || e))
  }
}

function insertAlertAtTop(alert) {
  const exists = alerts.value.find(a => a.id === alert.id)
  if (exists) return
  alerts.value.unshift(alert)
  total.value++
  if (stats.value.triggered !== undefined && alert.status === 'triggered') {
    stats.value.triggered++
  }
}

onMounted(() => {
  loadAlerts()
  connectAlertsWs('')
  onAlert(insertAlertAtTop)
})

onBeforeUnmount(() => {
  disconnectAlertsWs()
})

</script>

<style scoped>
.alerts-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.stat-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 16px; }
.stat-card { display: flex; align-items: center; gap: 12px; background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.stat-icon { width: 38px; height: 38px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px; background: rgba(99,102,241,0.1); }
.stat-icon.blue { background: rgba(59,130,246,0.1); }
.stat-icon.red { background: rgba(239,68,68,0.1); }
.stat-icon.yellow { background: rgba(245,158,11,0.1); }
.stat-icon.green { background: rgba(34,197,94,0.1); }
.stat-icon.gray { background: rgba(100,116,139,0.1); }
.stat-value { font-size: 1.3rem; font-weight: 700; color: var(--text, #1e293b); }
.stat-label { font-size: 0.72rem; color: var(--text-secondary, #64748b); }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.toolbar select { padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; transition: all 0.2s; }
.batch-actions { display: inline-flex; align-items: center; gap: 8px; background: linear-gradient(135deg, #6366f1, #8b5cf6); padding: 5px 12px; border-radius: 6px; }
.batch-tip { color: #fff; font-size: 0.8rem; font-weight: 600; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.btn-rca { background: #e0e7ff; color: #4f46e5; border-color: #c7d2fe; }
.btn-rca:hover { background: #c7d2fe; }
.btn-ai { background: #fef3c7; color: #b45309; border-color: #fde68a; }
.btn-ai:hover { background: #fde68a; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.col-check { width: 32px; }
.table th.col-check { text-align: center; }
.table td.col-check { text-align: center; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.msg-cell { max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.info { background: rgba(59,130,246,0.1); color: #3b82f6; }
.badge.warning { background: rgba(245,158,11,0.1); color: #f59e0b; }
.badge.critical, .badge.triggered { background: rgba(239,68,68,0.1); color: #ef4444; }
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
.btn-rca { background: rgba(99,102,241,0.1); color: #6366f1; border-color: rgba(99,102,241,0.3); }
.btn-rca:hover { background: rgba(99,102,241,0.2); }
.btn-ai { background: rgba(168,85,247,0.1); color: #a855f7; border-color: rgba(168,85,247,0.3); margin-left: 4px; }
.btn-ai:hover { background: rgba(168,85,247,0.2); }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card, #fff); border-radius: 12px; max-height: 85vh; overflow: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.15); }
.modal-lg { width: 700px; max-width: 92vw; }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); position: sticky; top: 0; background: var(--bg-card, #fff); z-index: 1; }
.modal-header h3 { margin: 0; font-size: 1rem; font-weight: 600; }
.modal-close { font-size: 1.4rem; background: none; border: none; cursor: pointer; color: var(--text-secondary, #64748b); padding: 0; line-height: 1; }
.modal-close:hover { color: var(--text, #1e293b); }
.modal-body { padding: 16px 20px; }
.modal-loading { padding: 60px 20px; text-align: center; color: var(--text-secondary, #64748b); }
.rca-section { margin-bottom: 16px; }
.rca-title { font-weight: 600; font-size: 0.85rem; color: var(--text, #1e293b); margin-bottom: 8px; padding-bottom: 4px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.rca-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 0.8rem; color: var(--text-secondary, #64748b); }
.rca-label { color: var(--text-tertiary, #94a3b8); margin-right: 4px; }
.rca-msg { margin-top: 6px; padding: 8px 10px; background: rgba(239,68,68,0.06); border-radius: 6px; font-size: 0.78rem; color: var(--text, #1e293b); }
.rca-item { display: flex; align-items: center; gap: 6px; padding: 4px 0; font-size: 0.8rem; color: var(--text, #1e293b); }
.rca-dot { width: 6px; height: 6px; border-radius: 50%; background: #f59e0b; flex-shrink: 0; }
.rca-type { font-size: 0.7rem; color: var(--text-tertiary, #94a3b8); }
.rca-empty { padding: 20px; text-align: center; color: var(--text-tertiary, #94a3b8); font-size: 0.82rem; }
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
.rca-error { padding: 20px; text-align: center; color: #ef4444; font-size: 0.85rem; }
.metric-chart { display: flex; align-items: flex-end; gap: 3px; height: 50px; padding: 4px 0; }
.metric-bar { width: 8px; background: linear-gradient(180deg, #6366f1, #818cf8); border-radius: 2px 2px 0 0; min-height: 6px; transition: height 0.3s; }
.ai-result { font-size: 0.85rem; line-height: 1.7; color: var(--text, #1e293b); }
.ai-result :deep(h1), .ai-result :deep(h2), .ai-result :deep(h3), .ai-result :deep(h4) { margin: 14px 0 6px; font-weight: 600; color: var(--text, #1e293b); }
.ai-result :deep(h1) { font-size: 1.1rem; }
.ai-result :deep(h2) { font-size: 1rem; color: #6366f1; }
.ai-result :deep(h3) { font-size: 0.92rem; }
.ai-result :deep(h4) { font-size: 0.85rem; }
.ai-result :deep(p) { margin: 6px 0; }
.ai-result :deep(ul), .ai-result :deep(ol) { padding-left: 20px; margin: 6px 0; }
.ai-result :deep(li) { margin-bottom: 4px; }
.ai-result :deep(strong) { color: #6366f1; }
.ai-result :deep(code) { background: rgba(99,102,241,0.1); padding: 1px 4px; border-radius: 3px; font-size: 0.8rem; }
.ai-result :deep(blockquote) { border-left: 3px solid #6366f1; padding-left: 12px; margin: 8px 0; color: var(--text-secondary, #64748b); }
.ai-result :deep(table) { border-collapse: collapse; margin: 8px 0; }
.ai-result :deep(th), .ai-result :deep(td) { border: 1px solid var(--border, rgba(0,0,0,0.1)); padding: 4px 8px; font-size: 0.8rem; }
</style>
