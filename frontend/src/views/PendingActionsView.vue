<template>
  <div class="pa-page">
    <div class="page-header">
      <h1>待确认动作</h1>
      <p>AI Agent 生成的待确认/已执行动作 · {{ actions.length }} 条</p>
    </div>

    <div class="toolbar">
      <button class="btn" @click="loadActions">刷新</button>
      <span class="text-sm" style="margin-left:auto;">待处理: {{ pendingCount }} · 已执行: {{ executedCount }}</span>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="actions.length" class="table">
          <thead>
            <tr><th>ID</th><th>动作</th><th>类型</th><th>风险</th><th>状态</th><th>原因</th><th>结果</th><th>时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="a in actions" :key="a.id">
              <td>{{ a.id }}</td>
              <td>{{ a.title }}</td>
              <td><span class="badge type">{{ a.action_type }}</span></td>
              <td><span class="badge" :class="riskClass(a.risk_level)">{{ riskLabel(a.risk_level) }}</span></td>
              <td><span class="badge" :class="statusClass(a.status)">{{ statusLabel(a.status) }}</span></td>
              <td class="text-sm" style="max-width:240px;">{{ a.reason || '-' }}</td>
              <td class="text-sm" style="max-width:240px;">{{ a.result_message || '-' }}</td>
              <td class="text-sm">{{ a.created_at || '-' }}</td>
              <td>
                <template v-if="a.status === 'pending'">
                  <button class="btn btn-sm btn-primary" @click="confirmAction(a)" :disabled="busy === a.id">{{ busy === a.id ? '处理中...' : '确认' }}</button>
                  <button class="btn btn-sm btn-danger" @click="cancelAction(a)" :disabled="busy === a.id">取消</button>
                </template>
                <span v-else class="text-sm">—</span>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">⏳</div><div>暂无待确认动作</div></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const actions = ref([])
const busy = ref(0)

const pendingCount = computed(() => actions.value.filter(a => a.status === 'pending').length)
const executedCount = computed(() => actions.value.filter(a => ['executed', 'failed', 'canceled'].includes(a.status)).length)

function riskLabel(r) {
  return { low: '低', medium: '中', high: '高', critical: '极高' }[r] || r || '中'
}
function riskClass(r) {
  return { low: 'on', medium: 'warn', high: 'err', critical: 'err' }[r] || 'warn'
}
function statusLabel(s) {
  return { pending: '待确认', confirmed: '已确认', executing: '执行中', executed: '已执行', failed: '失败', canceled: '已取消' }[s] || s
}
function statusClass(s) {
  if (s === 'pending') return 'warn'
  if (s === 'executed') return 'on'
  if (s === 'failed' || s === 'canceled') return 'err'
  if (s === 'executing' || s === 'confirmed') return 'info'
  return 'off'
}

async function loadActions() {
  loading.value = true
  try {
    const data = await request.get('/agent/api/pending')
    actions.value = data.actions || []
  } catch (e) {
    ElMessage.error('加载失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

async function confirmAction(a) {
  try {
    await ElMessageBox.confirm(`确认执行动作「${a.title}」？\n风险等级: ${riskLabel(a.risk_level)}`, '执行确认', { type: a.risk_level === 'critical' ? 'error' : 'warning' })
  } catch (e) {
    return
  }
  busy.value = a.id
  try {
    const data = await request.post(`/agent/pending/${a.id}/confirm`)
    if (data.result && data.result.status === 'executing') {
      ElMessage.info('命令正在远程执行中，请稍候...')
      await pollStatus(a.id)
    } else if (data.result && data.result.status === 'completed') {
      ElMessage.success('执行完成')
      loadActions()
    } else {
      ElMessage.success('已确认')
      loadActions()
    }
  } catch (e) {
    ElMessage.error('确认失败: ' + (e.message || e))
  } finally {
    busy.value = 0
  }
}

async function pollStatus(id) {
  for (let i = 0; i < 60; i++) {
    await new Promise(r => setTimeout(r, 2000))
    try {
      const s = await request.get(`/agent/pending/${id}/status`)
      if (s.is_terminal) {
        if (s.status === 'executed') ElMessage.success('执行完成')
        else if (s.status === 'failed') ElMessage.error('执行失败: ' + (s.result_message || ''))
        else if (s.status === 'canceled') ElMessage.warning('已取消')
        loadActions()
        return
      }
    } catch (e) { /* 继续轮询 */ }
  }
  ElMessage.warning('执行超时，请稍后刷新查看结果')
  loadActions()
}

async function cancelAction(a) {
  try {
    await ElMessageBox.confirm(`确认取消动作「${a.title}」？`, '取消确认', { type: 'info' })
    await request.post(`/agent/pending/${a.id}/cancel`)
    ElMessage.success('已取消')
    loadActions()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('取消失败: ' + (e.message || e))
  }
}

onMounted(loadActions)
</script>

<style scoped>
.pa-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-danger:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; white-space: nowrap; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); vertical-align: top; }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.on { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.warn { background: rgba(245,158,11,0.1); color: #f59e0b; }
.badge.err { background: rgba(239,68,68,0.1); color: #ef4444; }
.badge.info { background: rgba(59,130,246,0.1); color: #3b82f6; }
.badge.off { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.type { background: rgba(99,102,241,0.1); color: #6366f1; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
</style>
