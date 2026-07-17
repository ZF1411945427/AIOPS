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
            <tr v-for="it in pagedItems" :key="it.id" :data-lc-id="it.id" :class="{ 'row-focus': focusId === it.id }">
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

    <div class="pagination" v-if="items.length > pageSize">
      <div class="pg-info">共 <b>{{ items.length }}</b> 项</div>
      <div class="pg-pages">
        <button class="pg-btn" :disabled="currentPage === 1" @click="goPage(currentPage - 1)">‹ 上一页</button>
        <template v-for="(p, idx) in pageNumbers" :key="idx">
          <span v-if="p === '...'" class="pg-ellipsis">…</span>
          <button v-else class="pg-btn" :class="{ active: p === currentPage }" @click="goPage(p)">{{ p }}</button>
        </template>
        <button class="pg-btn" :disabled="currentPage === totalPages" @click="goPage(currentPage + 1)">下一页 ›</button>
      </div>
      <div class="pg-size">
        <select v-model.number="pageSize" class="pg-select">
          <option v-for="s in pageSizeOptions" :key="s" :value="s">{{ s }} 条/页</option>
        </select>
        <span class="pg-jump">跳至 <input class="pg-input" @keyup.enter="jumpPage($event)" placeholder="页"> 页</span>
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
              <div class="tl-meta">{{ h.created_at }} · {{ h.user_id || '系统' }}</div>
              <div v-if="h.description" class="tl-comment">{{ h.description }}</div>
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
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const items = ref([])
const states = ['provisioning', 'active', 'maintenance', 'retired']
const focusId = ref(null)

const showTransition = ref(false)
const showHistory = ref(false)
const historyLoading = ref(false)
const historyItems = ref([])
const current = ref({})
const transForm = ref({ to_status: '', comment: '' })

const currentPage = ref(1)
const pageSize = ref(20)
const pageSizeOptions = [10, 20, 50, 100]
const totalPages = computed(() => Math.max(1, Math.ceil(items.value.length / pageSize.value)))
const pagedItems = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return items.value.slice(start, start + pageSize.value)
})
const pageNumbers = computed(() => {
  const tp = totalPages.value
  const cp = currentPage.value
  const arr = []
  if (tp <= 7) { for (let i = 1; i <= tp; i++) arr.push(i) }
  else {
    arr.push(1)
    if (cp > 4) arr.push('...')
    for (let i = Math.max(2, cp - 1); i <= Math.min(tp - 1, cp + 1); i++) arr.push(i)
    if (cp < tp - 3) arr.push('...')
    arr.push(tp)
  }
  return arr
})
function goPage(p) {
  if (p === '...' || p < 1 || p > totalPages.value) return
  currentPage.value = p
}
function jumpPage(e) {
  const n = parseInt(e.target.value)
  if (!isNaN(n) && n >= 1 && n <= totalPages.value) currentPage.value = n
  e.target.value = ''
}
watch(pageSize, () => { currentPage.value = 1 })
watch(() => items.value.length, () => { if (currentPage.value > totalPages.value) currentPage.value = totalPages.value })

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

onMounted(async () => {
  await loadList()
  const fid = (typeof window !== 'undefined') ? window._lifecycleFocusId : null
  if (fid !== null && fid !== undefined && fid !== '') {
    window._lifecycleFocusId = null
    const idx = items.value.findIndex(x => x.id === fid)
    const it = idx >= 0 ? items.value[idx] : null
    if (it) {
      focusId.value = it.id
      currentPage.value = Math.floor(idx / pageSize.value) + 1
      nextTick(() => {
        nextTick(() => {
          const el = document.querySelector(`tr[data-lc-id="${it.id}"]`)
          if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
        })
        if (it.allowed_transitions && it.allowed_transitions.length) openTransition(it)
        else ElMessage.info(`「${it.name}」当前为终态(${it.lifecycle_status})，无法流转，可查看历史记录`)
      })
    } else {
      ElMessage.warning('未找到目标资产')
    }
  }
})
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
.table tr.row-focus td { background: rgba(99,102,241,0.10); box-shadow: inset 3px 0 0 var(--accent, #6366f1); }
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

.pagination { display: flex; align-items: center; justify-content: space-between; margin-top: 14px; padding: 10px 16px; background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; flex-wrap: wrap; gap: 8px; }
.pg-info { font-size: 0.8rem; color: var(--text-secondary, #64748b); }
.pg-info b { color: var(--accent, #6366f1); }
.pg-pages { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.pg-btn { min-width: 30px; height: 28px; padding: 0 8px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 5px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.76rem; cursor: pointer; transition: all 0.15s; }
.pg-btn:hover:not(:disabled):not(.active) { background: var(--bg-hover, rgba(0,0,0,0.03)); border-color: var(--accent, #6366f1); }
.pg-btn.active { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.pg-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.pg-ellipsis { color: var(--text-tertiary, #94a3b8); padding: 0 4px; font-size: 0.8rem; }
.pg-size { display: flex; align-items: center; gap: 10px; font-size: 0.76rem; color: var(--text-secondary, #64748b); }
.pg-select { padding: 4px 8px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 5px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.76rem; cursor: pointer; }
.pg-jump { display: flex; align-items: center; gap: 4px; }
.pg-input { width: 42px; height: 24px; padding: 0 4px; text-align: center; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 4px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.76rem; }
</style>
