<template>
  <div class="lifecycle-page">
    <div class="page-header">
      <h1>资产生命周期</h1>
      <p>资产状态机管理与流转追溯 · 共 {{ items.length }} 项资产</p>
    </div>

    <div class="toolbar">
      <button class="btn" @click="loadList">刷新</button>
    </div>

    <div class="panel">
      <div class="panel-head">状态机流转图</div>
      <div class="panel-body">
        <div class="state-flow">
          <template v-for="(s, i) in states" :key="s">
            <span class="state-node" :class="stateClass(s)">{{ s }}</span>
            <span v-if="i < states.length - 1" class="state-arrow">→</span>
          </template>
        </div>
        <div class="state-legend">
          <span class="leg-item"><span class="dot provisioning"></span>provisioning 初始</span>
          <span class="leg-item"><span class="dot active"></span>active 运行</span>
          <span class="leg-item"><span class="dot maintenance"></span>maintenance 维护</span>
          <span class="leg-item"><span class="dot retired"></span>retired 退役</span>
        </div>
      </div>
    </div>

    <div class="panel" style="margin-top:14px;">
      <div class="panel-head">资产列表</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="items.length" class="table">
          <thead>
            <tr>
              <th>名称</th>
              <th>CI 类型</th>
              <th>当前状态</th>
              <th>生命周期阶段</th>
              <th>变更时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="it in items" :key="it.id">
              <td>{{ it.name }}</td>
              <td><span class="badge ci-type">{{ it.ci_type || it.type || '-' }}</span></td>
              <td><span class="badge" :class="statusBadge(it.status)">{{ it.status || '-' }}</span></td>
              <td><span class="badge" :class="lifecycleClass(it.lifecycle_status)">{{ it.lifecycle_status }}</span></td>
              <td>{{ it.lifecycle_changed_at || '-' }}</td>
              <td class="ops">
                <button class="btn btn-sm btn-primary" @click="openTransition(it)" :disabled="!it.allowed_transitions || !it.allowed_transitions.length">流转</button>
                <button class="btn btn-sm" @click="openHistory(it)">历史</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">♻️</div><div>暂无资产数据</div></div>
      </div>
    </div>

    <div v-if="showTransition" class="modal-overlay" @click.self="showTransition = false">
      <div class="modal-box">
        <h3>资产流转 · {{ current.name }}</h3>
        <div class="form-row"><label>当前生命周期阶段</label>
          <span class="badge" :class="lifecycleClass(current.lifecycle_status)">{{ current.lifecycle_status }}</span>
        </div>
        <div class="form-row"><label>流转至</label>
          <select v-model="transForm.to_status" class="input">
            <option v-for="s in current.allowed_transitions" :key="s" :value="s">{{ s }}</option>
          </select>
        </div>
        <div class="form-row"><label>备注（可选）</label><input v-model="transForm.comment" class="input" placeholder="变更说明"></div>
        <div class="modal-actions">
          <button class="btn" @click="showTransition = false">取消</button>
          <button class="btn btn-primary" @click="doTransition">确认流转</button>
        </div>
      </div>
    </div>

    <div v-if="showHistory" class="modal-overlay" @click.self="showHistory = false">
      <div class="modal-box modal-lg">
        <h3>生命周期历史 · {{ current.name }}</h3>
        <div v-if="historyLoading" class="loading-state">加载中...</div>
        <div v-else-if="historyItems.length" class="timeline">
          <div v-for="(h, idx) in historyItems" :key="h.id" class="tl-item">
            <div class="tl-dot" :class="lifecycleClass(h.status)"></div>
            <div class="tl-content">
              <div class="tl-line">
                <span class="badge sm" :class="lifecycleClass(h.previous_status)">{{ h.previous_status || '起始' }}</span>
                <span class="tl-arrow">→</span>
                <span class="badge sm" :class="lifecycleClass(h.status)">{{ h.status }}</span>
              </div>
              <div class="tl-meta">{{ h.created_at }} · {{ h.changed_by || '系统' }}</div>
              <div v-if="h.comment" class="tl-comment">{{ h.comment }}</div>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">暂无历史记录</div>
        <div class="modal-actions">
          <button class="btn" @click="showHistory = false">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const items = ref([])
const states = ['provisioning', 'active', 'maintenance', 'retired']

const showTransition = ref(false)
const showHistory = ref(false)
const historyLoading = ref(false)
const historyItems = ref([])
const current = ref({})
const transForm = ref({ to_status: '', comment: '' })

function stateClass(s) {
  return `state-${s}`
}
function lifecycleClass(s) {
  return `lc-${s}`
}
function statusBadge(s) {
  if (!s) return 'badge-gray'
  if (s === 'online' || s === 'active') return 'badge-green'
  if (s === 'warning' || s === 'maintenance') return 'badge-orange'
  if (s === 'offline' || s === 'retired') return 'badge-red'
  return 'badge-gray'
}

async function loadList() {
  loading.value = true
  try {
    const data = await request.get('/lifecycle/api/list')
    items.value = data.items || []
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

function openTransition(it) {
  current.value = it
  transForm.value = { to_status: it.allowed_transitions?.[0] || '', comment: '' }
  showTransition.value = true
}

async function doTransition() {
  if (!transForm.value.to_status) {
    ElMessage.warning('请选择目标状态')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认将「${current.value.name}」从 ${current.value.lifecycle_status} 流转至 ${transForm.value.to_status}?`,
      '流转确认',
      { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    const data = await request.post(`/lifecycle/api/transition/${current.value.id}`, {
      to_status: transForm.value.to_status,
      comment: transForm.value.comment,
    })
    if (data.ok === false) {
      ElMessage.error(data.error || '流转失败')
      return
    }
    ElMessage.success('流转成功')
    showTransition.value = false
    loadList()
  } catch (e) {
    ElMessage.error('流转失败: ' + (e.message || e))
  }
}

async function openHistory(it) {
  current.value = it
  showHistory.value = true
  historyLoading.value = true
  historyItems.value = []
  try {
    const data = await request.get(`/lifecycle/api/history/${it.id}`)
    historyItems.value = data.items || []
  } catch (e) {
    ElMessage.error('历史加载失败: ' + (e.message || e))
  } finally {
    historyLoading.value = false
  }
}

onMounted(loadList)
</script>

<style scoped>
.lifecycle-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 16px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.ops { display: flex; gap: 6px; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); }
.panel-body { padding: 16px 18px; }
.state-flow { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.state-node { padding: 6px 14px; border-radius: 8px; font-size: 0.82rem; font-weight: 600; color: #fff; }
.state-arrow { color: var(--text-secondary, #64748b); font-weight: 600; }
.state-provisioning { background: #94a3b8; }
.state-active { background: #22c55e; }
.state-maintenance { background: #f59e0b; }
.state-retired { background: #6b7280; }
.state-legend { margin-top: 12px; display: flex; gap: 16px; flex-wrap: wrap; font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.leg-item { display: inline-flex; align-items: center; gap: 6px; }
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.dot.provisioning { background: #94a3b8; }
.dot.active { background: #22c55e; }
.dot.maintenance { background: #f59e0b; }
.dot.retired { background: #6b7280; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.72rem; font-weight: 600; }
.badge.sm { padding: 1px 6px; font-size: 0.68rem; }
.badge.ci-type { background: rgba(59,130,246,0.1); color: #3b82f6; }
.badge-green { background: rgba(34,197,94,0.12); color: #16a34a; }
.badge-orange { background: rgba(245,158,11,0.12); color: #d97706; }
.badge-red { background: rgba(239,68,68,0.12); color: #dc2626; }
.badge-gray { background: rgba(107,114,128,0.12); color: #4b5563; }
.lc-provisioning { background: rgba(148,163,184,0.15); color: #475569; }
.lc-active { background: rgba(34,197,94,0.15); color: #16a34a; }
.lc-maintenance { background: rgba(245,158,11,0.15); color: #d97706; }
.lc-retired { background: rgba(107,114,128,0.15); color: #4b5563; }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 380px; max-width: 560px; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-lg { min-width: 560px; max-width: 640px; }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; color: var(--text, #1e293b); }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.timeline { max-height: 420px; overflow-y: auto; }
.tl-item { position: relative; padding-left: 24px; padding-bottom: 16px; border-left: 2px solid var(--border, rgba(0,0,0,0.07)); margin-left: 6px; }
.tl-dot { position: absolute; left: -7px; top: 2px; width: 12px; height: 12px; border-radius: 50%; border: 2px solid #fff; box-shadow: 0 0 0 1px var(--border, rgba(0,0,0,0.1)); }
.lc-active .tl-dot, .tl-dot.lc-active { background: #22c55e; }
.lc-maintenance .tl-dot, .tl-dot.lc-maintenance { background: #f59e0b; }
.lc-retired .tl-dot, .tl-dot.lc-retired { background: #6b7280; }
.lc-provisioning .tl-dot, .tl-dot.lc-provisioning { background: #94a3b8; }
.tl-content { padding-left: 8px; }
.tl-line { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.tl-arrow { color: var(--text-secondary, #64748b); }
.tl-meta { font-size: 0.75rem; color: var(--text-secondary, #64748b); }
.tl-comment { margin-top: 4px; font-size: 0.8rem; color: var(--text, #1e293b); background: var(--bg-hover, rgba(0,0,0,0.03)); padding: 4px 8px; border-radius: 4px; }
</style>
