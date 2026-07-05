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
      <select v-model="filters.status" @change="loadAlerts">
        <option value="">全部状态</option>
        <option value="triggered">已触发</option>
        <option value="acknowledged">已确认</option>
        <option value="resolved">已解决</option>
      </select>
      <select v-model="filters.severity" @change="loadAlerts">
        <option value="">全部级别</option>
        <option value="info">Info</option>
        <option value="warning">Warning</option>
        <option value="critical">Critical</option>
      </select>
      <button class="btn" @click="checkAlerts">触发检查</button>
      <button class="btn" @click="batchAck">全部确认</button>
      <button class="btn btn-primary" @click="batchResolve">全部解决</button>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="alerts.length" class="table">
          <thead>
            <tr>
              <th>ID</th><th>时间</th><th>指标</th><th>当前值</th><th>阈值</th>
              <th>级别</th><th>状态</th><th>消息</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in alerts" :key="a.id" :class="`severity-${a.severity}`">
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
      <button class="btn btn-sm" :disabled="filters.page <= 1" @click="goPage(filters.page - 1)">上一页</button>
      <span class="page-info">第 {{ filters.page }} / {{ totalPages }} 页</span>
      <button class="btn btn-sm" :disabled="filters.page >= totalPages" @click="goPage(filters.page + 1)">下一页</button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const alerts = ref([])
const total = ref(0)
const totalPages = ref(1)
const stats = ref({})
const filters = reactive({ status: '', severity: '', page: 1 })

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
  filters.page = p
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

function formatTime(s) {
  if (!s) return '-'
  return s.substring(5, 16)
}

onMounted(loadAlerts)
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
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
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
.pagination { display: flex; justify-content: center; align-items: center; gap: 10px; margin-top: 16px; }
.page-info { font-size: 0.82rem; color: var(--text-secondary, #64748b); }
</style>
