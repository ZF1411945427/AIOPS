<template>
  <div class="remediation-page">
    <div class="page-header">
      <h1>自愈规则</h1>
      <p>告警触发时自动执行预设动作 · 共 {{ total }} 条规则</p>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="openCreate">+ 新增规则</button>
      <button class="btn" @click="loadData">刷新</button>
    </div>

    <div class="panel">
      <div class="panel-header"><h3>响应规则</h3></div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="remediations.length" class="table">
          <thead>
            <tr>
              <th>名称</th><th>触发规则</th><th>动作</th><th>目标</th><th>状态</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in remediations" :key="r.id">
              <td>{{ r.name }}</td>
              <td>{{ ruleName(r.rule_id) }}</td>
              <td><span class="badge action">{{ actionLabel(r.action_type) }}</span></td>
              <td class="text-sm">{{ r.params?.target || '-' }}</td>
              <td><span class="badge" :class="r.enabled ? 'resolved' : 'info'">{{ r.enabled ? '启用' : '停用' }}</span></td>
              <td><button class="btn btn-sm btn-danger" @click="deleteRule(r)">删除</button></td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">🔧</div><div>暂无规则</div></div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header"><h3>执行记录 · 共 {{ logTotal }} 条</h3></div>
      <div class="panel-body">
        <table v-if="logs.length" class="table">
          <thead><tr><th>时间</th><th>动作</th><th>目标</th><th>结果</th><th>输出</th></tr></thead>
          <tbody>
            <tr v-for="lg in logs" :key="lg.id">
              <td class="text-sm">{{ formatTime(lg.created_at) }}</td>
              <td>{{ lg.action_type }}</td>
              <td class="text-sm">{{ lg.target }}</td>
              <td><span class="badge" :class="lg.success ? 'resolved' : 'critical'">{{ lg.success ? '成功' : '失败' }}</span></td>
              <td class="output-cell">{{ lg.output }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">暂无执行记录</div>
        <div v-if="totalPages > 1" class="pagination">
          <button class="btn btn-sm" :disabled="currentPage <= 1" @click="goPage(1)">首页</button>
          <button class="btn btn-sm" :disabled="currentPage <= 1" @click="goPage(currentPage - 1)">上一页</button>
          <span v-for="p in pageNumbers" :key="p" class="page-num" :class="{ active: p === currentPage }" @click="goPage(p)">{{ p }}</span>
          <button class="btn btn-sm" :disabled="currentPage >= totalPages" @click="goPage(currentPage + 1)">下一页</button>
          <button class="btn btn-sm" :disabled="currentPage >= totalPages" @click="goPage(totalPages)">末页</button>
          <span class="page-jump">跳转 <input type="number" class="page-input" v-model.number="jumpPage" min="1" :max="totalPages" @keyup.enter="goPage(jumpPage)" /> 页</span>
          <span class="page-info">共 {{ logTotal }} 条 / {{ totalPages }} 页</span>
        </div>
      </div>
    </div>

    <div v-if="createVisible" class="modal-overlay" @click.self="createVisible = false">
      <div class="modal-box">
        <div class="modal-header"><h3>新增自愈规则</h3><button class="modal-close" @click="createVisible = false">×</button></div>
        <div class="modal-body">
          <div class="form-group"><label>名称</label><input v-model="form.name" placeholder="如：CPU 高自动重启" /></div>
          <div class="form-group">
            <label>触发规则</label>
            <select v-model.number="form.rule_id">
              <option :value="0">任何告警</option>
              <option v-for="r in rules" :key="r.id" :value="r.id">{{ r.name }}</option>
            </select>
          </div>
          <div class="form-group">
            <label>动作类型</label>
            <select v-model="form.action_type" @change="onActionChange">
              <option v-for="(label, key) in actions" :key="key" :value="key">{{ label }}</option>
            </select>
          </div>
          <div class="form-group"><label>目标</label><input v-model="form.params_target" placeholder="如：nginx 或 asset_5" /></div>
          <div v-if="form.action_type === 'scale'" class="form-group"><label>实例数</label><input v-model.number="form.params_count" type="number" /></div>
          <div v-if="form.action_type === 'script'" class="form-group"><label>脚本路径</label><input v-model="form.params_script" placeholder="/opt/scripts/fix.sh" /></div>
          <div v-if="form.action_type === 'run_command'" class="form-group"><label>执行命令</label><input v-model="form.params_command" placeholder="如：hostname 或 uptime（危险命令会被拦截）" /></div>
          <div class="form-actions"><button class="btn" @click="createVisible = false">取消</button><button class="btn btn-primary" @click="createRule" :disabled="creating">{{ creating ? '创建中...' : '创建' }}</button></div>
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
const remediations = ref([])
const logs = ref([])
const rules = ref([])
const actions = ref({})
const total = ref(0)
const createVisible = ref(false)
const creating = ref(false)
const form = reactive({ name: '', rule_id: 0, action_type: 'restart', params_target: '', params_count: 2, params_script: '', params_command: '' })

const currentPage = ref(1)
const pageSize = ref(20)
const logTotal = ref(0)
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
  loadLogs()
}

async function loadData() {
  loading.value = true
  try {
    const data = await request.get('/remediation/api/list')
    remediations.value = data.remediations || []
    rules.value = data.rules || []
    actions.value = data.actions || {}
    total.value = data.total || 0
    loadLogs()
  } catch (e) {
    ElMessage.error('加载失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

async function loadLogs() {
  try {
    const data = await request.get('/remediation/api/logs', { params: { page: currentPage.value, per_page: pageSize.value } })
    logs.value = data.items || []
    logTotal.value = data.total || 0
    totalPages.value = data.total_pages || 1
  } catch (e) {
    ElMessage.error('加载执行记录失败: ' + e.message)
  }
}

function ruleName(id) {
  if (!id) return '任何告警'
  const r = rules.value.find(x => x.id === id)
  return r ? r.name : `规则#${id}`
}
function actionLabel(type) {
  return actions.value[type] || type
}
function onActionChange() {}

function openCreate() {
  Object.assign(form, { name: '', rule_id: 0, action_type: 'restart', params_target: '', params_count: 2, params_script: '', params_command: '' })
  createVisible.value = true
}

async function createRule() {
  if (!form.name || !form.action_type) { ElMessage.warning('请填写名称和动作'); return }
  creating.value = true
  try {
    const fd = new FormData()
    fd.append('name', form.name)
    fd.append('rule_id', form.rule_id)
    fd.append('action_type', form.action_type)
    fd.append('params_target', form.params_target)
    fd.append('params_count', form.params_count)
    fd.append('params_script', form.params_script)
    fd.append('params_command', form.params_command)
    await request.post('/remediation/api/create', fd)
    ElMessage.success('创建成功')
    createVisible.value = false
    loadData()
  } catch (e) { ElMessage.error('创建失败: ' + e.message) } finally { creating.value = false }
}

async function deleteRule(r) {
  try {
    await ElMessageBox.confirm(`确认删除规则"${r.name}"？`, '删除确认')
    await request.post(`/remediation/api/${r.id}/delete`)
    ElMessage.success('已删除')
    loadData()
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e)) }
}

function formatTime(s) { return s ? s.substring(0, 19) : '-' }

onMounted(loadData)
</script>

<style scoped>
.remediation-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.btn-danger { color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-danger:hover { background: rgba(239,68,68,0.08); }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 16px; }
.panel-header { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.panel-header h3 { margin: 0; font-size: 0.95rem; }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.output-cell { max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.78rem; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.action { background: rgba(99,102,241,0.1); color: #6366f1; }
.badge.resolved { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.critical { background: rgba(239,68,68,0.1); color: #ef4444; }
.badge.info { background: rgba(100,116,139,0.1); color: #64748b; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 6px; margin-top: 16px; flex-wrap: wrap; }
.page-info { font-size: 0.82rem; color: var(--text-secondary, #64748b); }
.page-num { display: inline-flex; align-items: center; justify-content: center; min-width: 30px; height: 30px; padding: 0 6px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.8rem; cursor: pointer; transition: all 0.2s; user-select: none; }
.page-num:hover { background: var(--bg-hover, rgba(99,102,241,0.08)); border-color: var(--accent, #6366f1); }
.page-num.active { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); font-weight: 600; }
.page-jump { font-size: 0.8rem; color: var(--text-secondary, #64748b); display: flex; align-items: center; gap: 4px; }
.page-input { width: 50px; padding: 3px 6px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; text-align: center; font-size: 0.8rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 12px; width: 90%; max-width: 520px; max-height: 85vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.2); }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.modal-header h3 { margin: 0; font-size: 1.1rem; }
.modal-close { background: none; border: none; font-size: 24px; cursor: pointer; color: var(--text-secondary, #64748b); line-height: 1; }
.modal-body { padding: 20px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 0.8rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.form-group input, .form-group select { width: 100%; padding: 8px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.85rem; box-sizing: border-box; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
