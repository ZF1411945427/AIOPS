<template>
  <div class="bg-page">
    <div class="page-header">
      <h1>蓝绿发布</h1>
      <p>创建蓝绿 Deployment 组，一键切换流量标签 · 共 {{ total }} 个部署</p>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="openCreate">+ 新建部署</button>
      <button class="btn" @click="loadData">刷新</button>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="deploys.length" class="deploy-list">
          <div v-for="d in deploys" :key="d.id" class="deploy-card">
            <div class="deploy-head">
              <span class="deploy-name">{{ d.name }}</span>
              <span class="badge ns">{{ d.namespace }}</span>
              <span v-if="d.cluster" class="badge cluster">{{ d.cluster }}</span>
              <span class="badge" :class="d.status === 'active' ? 'resolved' : 'warning'">{{ d.status }}</span>
            </div>
            <div class="deploy-meta">
              <div class="meta-row">
                <span class="badge blue">活跃: {{ d.active_label }} ({{ d.active_replicas }}副本)</span>
                <span class="badge green">备用: {{ d.standby_label }} ({{ d.standby_replicas }}副本)</span>
              </div>
              <div v-if="d.last_switched_at" class="meta-row text-sm">上次切换: {{ d.last_switched_at }}</div>
              <div class="meta-row text-sm">创建时间: {{ d.created_at || '-' }}</div>
            </div>
            <div class="deploy-actions">
              <button class="btn btn-sm btn-primary" @click="switchDeploy(d)" :disabled="switching === d.id">
                {{ switching === d.id ? '切换中...' : '切换蓝绿' }}
              </button>
              <button class="btn btn-sm btn-warning" @click="rollbackDeploy(d)" :disabled="rollingback === d.id">
                {{ rollingback === d.id ? '回滚中...' : '回滚' }}
              </button>
              <button class="btn btn-sm" @click="showRecords(d)">历史</button>
              <button class="btn btn-sm btn-danger" @click="deleteDeploy(d)" :disabled="deleting === d.id">
                {{ deleting === d.id ? '删除中...' : '删除' }}
              </button>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">🔀</div>
          <div>暂无部署组，点击"新建部署"创建</div>
        </div>
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

    <!-- 历史记录面板 -->
    <div v-if="recordsVisible" class="modal-overlay" @click.self="recordsVisible = false">
      <div class="modal-box">
        <div class="modal-header">
          <h3>切换历史 · {{ currentDeploy?.name }}</h3>
          <button class="modal-close" @click="recordsVisible = false">×</button>
        </div>
        <div class="modal-body">
          <div v-if="recordsLoading" class="loading-state">加载中...</div>
          <div v-else-if="records.length" class="timeline">
            <div v-for="r in records" :key="r.id" class="timeline-item">
              <div class="timeline-dot" :class="r.note === '回滚' ? 'rollback' : 'switch'"></div>
              <div class="timeline-content">
                <div class="timeline-head">
                  <span class="timeline-action">
                    <span v-if="r.note === '回滚'" class="tag-rollback">回滚</span>
                    <span v-else class="tag-switch">切换</span>
                    {{ r.from_label }} → {{ r.to_label }}
                  </span>
                  <span class="timeline-time">{{ r.created_at }}</span>
                </div>
                <div class="timeline-meta">
                  <span>操作人: {{ r.operator }}</span>
                  <span v-if="r.note && r.note !== '回滚'">备注: {{ r.note }}</span>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="empty-state small">暂无切换记录</div>
        </div>
      </div>
    </div>

    <!-- 新建弹框 -->
    <div v-if="createVisible" class="modal-overlay" @click.self="createVisible = false">
      <div class="modal-box">
        <div class="modal-header">
          <h3>新建蓝绿部署</h3>
          <button class="modal-close" @click="createVisible = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-grid">
            <div class="form-group">
              <label>名称</label>
              <input v-model="form.name" placeholder="如：my-app" />
            </div>
            <div class="form-group">
              <label>命名空间</label>
              <input v-model="form.namespace" placeholder="default" />
            </div>
            <div class="form-group full">
              <label>K8s 集群（可选，仅记录则留空）</label>
              <select v-model="form.cluster">
                <option value="">-- 仅记录 --</option>
                <option v-for="c in clusters" :key="c.id" :value="c.name">{{ c.name }}</option>
              </select>
            </div>
            <div class="form-group">
              <label>蓝标签</label>
              <input v-model="form.active_label" placeholder="blue" />
            </div>
            <div class="form-group">
              <label>绿标签</label>
              <input v-model="form.standby_label" placeholder="green" />
            </div>
            <div class="form-group">
              <label>蓝副本数</label>
              <input v-model.number="form.active_replicas" type="number" min="0" />
            </div>
            <div class="form-group">
              <label>绿副本数</label>
              <input v-model.number="form.standby_replicas" type="number" min="0" />
            </div>
            <div class="form-group full">
              <label>容器镜像</label>
              <input v-model="form.image" placeholder="nginx:latest" />
            </div>
          </div>
          <div class="form-actions">
            <button class="btn" @click="createVisible = false">取消</button>
            <button class="btn btn-primary" @click="createDeploy" :disabled="creating">{{ creating ? '创建中...' : '创建' }}</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const deploys = ref([])
const clusters = ref([])
const total = ref(0)
const createVisible = ref(false)
const creating = ref(false)
const switching = ref(null)
const rollingback = ref(null)
const deleting = ref(null)
const recordsVisible = ref(false)
const recordsLoading = ref(false)
const records = ref([])
const currentDeploy = ref(null)
const form = reactive({
  name: '', namespace: 'default', cluster: '',
  active_label: 'blue', standby_label: 'green',
  active_replicas: 3, standby_replicas: 3, image: 'nginx:latest',
})

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
  loadData()
}

async function loadData() {
  loading.value = true
  try {
    const data = await request.get('/blue-green/api/list', { params: { page: currentPage.value, per_page: pageSize.value } })
    deploys.value = data.deploys || []
    clusters.value = data.clusters || []
    total.value = data.total || 0
    totalPages.value = data.total_pages || 1
  } catch (e) {
    ElMessage.error('加载失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, { name: '', namespace: 'default', cluster: '', active_label: 'blue', standby_label: 'green', active_replicas: 3, standby_replicas: 3, image: 'nginx:latest' })
  createVisible.value = true
}

async function createDeploy() {
  if (!form.name) { ElMessage.warning('请填写名称'); return }
  creating.value = true
  try {
    const fd = new FormData()
    fd.append('name', form.name)
    fd.append('namespace', form.namespace)
    fd.append('cluster', form.cluster)
    fd.append('active_label', form.active_label)
    fd.append('standby_label', form.standby_label)
    fd.append('active_replicas', form.active_replicas)
    fd.append('standby_replicas', form.standby_replicas)
    fd.append('image', form.image)
    const data = await request.post('/blue-green/api/create', fd)
    ElMessage.success('创建成功' + (data.k8s_msg ? '（' + data.k8s_msg + '）' : ''))
    createVisible.value = false
    currentPage.value = 1
    loadData()
  } catch (e) {
    ElMessage.error('创建失败: ' + e.message)
  } finally {
    creating.value = false
  }
}

async function switchDeploy(d) {
  try {
    await ElMessageBox.confirm(`确认切换 ${d.name} 的蓝绿流量？\n\n活跃「${d.active_label}」将变为备用，备用「${d.standby_label}」将变为活跃。`, '切换确认')
    switching.value = d.id
    const fd = new FormData()
    fd.append('note', '')
    const data = await request.post(`/blue-green/api/${d.id}/switch`, fd)
    ElMessage.success(`已切换，当前活跃: ${data.active_label}` + (data.k8s_msg ? '（K8s: ' + data.k8s_msg + '）' : ''))
    loadData()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('切换失败: ' + (e.message || e))
  } finally {
    switching.value = null
  }
}

async function rollbackDeploy(d) {
  try {
    await ElMessageBox.confirm(`确认回滚 ${d.name}？\n\n将切回到上一次活跃版本「${d.standby_label}」（当前备用）。`, '回滚确认', { type: 'warning' })
    rollingback.value = d.id
    const fd = new FormData()
    const data = await request.post(`/blue-green/api/${d.id}/rollback`, fd)
    if (data.error) { ElMessage.warning(data.error); return }
    ElMessage.success(`已回滚，当前活跃: ${data.active_label}` + (data.k8s_msg ? '（K8s: ' + data.k8s_msg + '）' : ''))
    loadData()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('回滚失败: ' + (e.message || e))
  } finally {
    rollingback.value = null
  }
}

async function showRecords(d) {
  currentDeploy.value = d
  recordsVisible.value = true
  recordsLoading.value = true
  records.value = []
  try {
    const data = await request.get(`/blue-green/api/${d.id}/records`)
    records.value = data.records || []
  } catch (e) {
    ElMessage.error('加载历史失败: ' + e.message)
  } finally {
    recordsLoading.value = false
  }
}

async function deleteDeploy(d) {
  try {
    await ElMessageBox.confirm(`确认删除 ${d.name}？将同时清理 K8s 资源`, '删除确认', { type: 'warning' })
    deleting.value = d.id
    const data = await request.post(`/blue-green/api/${d.id}/delete`)
    ElMessage.success('已删除' + (data.k8s_msg ? '（' + data.k8s_msg + '）' : ''))
    loadData()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  } finally {
    deleting.value = null
  }
}

onMounted(loadData)
</script>

<style scoped>
.bg-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; transition: all 0.2s; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-danger { background: #ef4444; color: #fff; border-color: #ef4444; }
.btn-danger:hover { background: #dc2626; }
.btn-warning { background: #f59e0b; color: #fff; border-color: #f59e0b; }
.btn-warning:hover { background: #d97706; }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.deploy-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 12px; }
.deploy-card { border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; padding: 14px; }
.deploy-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.deploy-name { font-weight: 600; font-size: 0.95rem; color: var(--text, #1e293b); }
.deploy-meta { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
.meta-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.deploy-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.ns { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.cluster { background: rgba(99,102,241,0.1); color: #6366f1; }
.badge.blue { background: rgba(59,130,246,0.1); color: #3b82f6; }
.badge.green { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.resolved { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.warning { background: rgba(245,158,11,0.1); color: #f59e0b; }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.empty-state.small { padding: 16px; font-size: 0.82rem; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 6px; margin-top: 16px; flex-wrap: wrap; }
.page-info { font-size: 0.82rem; color: var(--text-secondary, #64748b); }
.page-num { display: inline-flex; align-items: center; justify-content: center; min-width: 30px; height: 30px; padding: 0 6px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.8rem; cursor: pointer; transition: all 0.2s; user-select: none; }
.page-num:hover { background: var(--bg-hover, rgba(99,102,241,0.08)); border-color: var(--accent, #6366f1); }
.page-num.active { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); font-weight: 600; }
.page-jump { font-size: 0.8rem; color: var(--text-secondary, #64748b); display: flex; align-items: center; gap: 4px; }
.page-input { width: 50px; padding: 3px 6px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; text-align: center; font-size: 0.8rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 12px; width: 90%; max-width: 600px; max-height: 85vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.2); }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.modal-header h3 { margin: 0; font-size: 1.1rem; }
.modal-close { background: none; border: none; font-size: 24px; cursor: pointer; color: var(--text-secondary, #64748b); line-height: 1; }
.modal-body { padding: 20px; }
.form-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }
.form-group { display: flex; flex-direction: column; gap: 4px; }
.form-group.full { grid-column: 1 / -1; }
.form-group label { font-size: 0.8rem; color: var(--text-secondary, #64748b); }
.form-group input, .form-group select { width: 100%; padding: 8px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.85rem; box-sizing: border-box; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }

/* 时间线 */
.timeline { display: flex; flex-direction: column; gap: 0; }
.timeline-item { display: flex; gap: 12px; padding-bottom: 16px; position: relative; }
.timeline-item:last-child { padding-bottom: 0; }
.timeline-item:not(:last-child)::before { content: ''; position: absolute; left: 7px; top: 18px; bottom: 0; width: 2px; background: var(--border, rgba(0,0,0,0.1)); }
.timeline-dot { width: 16px; height: 16px; border-radius: 50%; flex-shrink: 0; margin-top: 3px; }
.timeline-dot.switch { background: #6366f1; }
.timeline-dot.rollback { background: #f59e0b; }
.timeline-content { flex: 1; }
.timeline-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.timeline-action { font-size: 0.85rem; font-weight: 600; color: var(--text, #1e293b); }
.timeline-time { font-size: 0.75rem; color: var(--text-secondary, #64748b); }
.timeline-meta { font-size: 0.78rem; color: var(--text-secondary, #64748b); display: flex; gap: 12px; }
.tag-switch, .tag-rollback { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 0.68rem; font-weight: 700; margin-right: 4px; }
.tag-switch { background: rgba(99,102,241,0.12); color: #6366f1; }
.tag-rollback { background: rgba(245,158,11,0.12); color: #f59e0b; }
</style>
