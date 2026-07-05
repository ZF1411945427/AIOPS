<template>
  <div class="wf-page">
    <div class="page-header">
      <h1>自愈工作流</h1>
      <p>多步骤故障自愈流程编排 · 共 {{ total }} 个工作流</p>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="openCreate">+ 新建工作流</button>
      <button class="btn" @click="loadData">刷新</button>
    </div>

    <div class="panel">
      <div class="panel-header"><h3>工作流列表</h3></div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="workflows.length" class="wf-list">
          <div v-for="w in workflows" :key="w.id" class="wf-card">
            <div class="wf-head">
              <span class="wf-name">{{ w.name }}</span>
              <span class="badge" :class="w.enabled ? 'resolved' : 'info'">{{ w.enabled ? '启用' : '禁用' }}</span>
            </div>
            <div class="wf-steps">
              <span class="steps-label">步骤：</span>
              <span v-for="(s, i) in w.steps" :key="i" class="step-chip">
                {{ typeof s === 'object' ? s.action || s.step : s }}
                <span v-if="i < w.steps.length - 1" class="step-arrow">→</span>
              </span>
            </div>
            <div class="wf-actions">
              <button class="btn btn-sm btn-primary" @click="runWorkflow(w)" :disabled="running === w.id">{{ running === w.id ? '运行中...' : '运行' }}</button>
              <button class="btn btn-sm" @click="toggleWorkflow(w)">{{ w.enabled ? '禁用' : '启用' }}</button>
              <button class="btn btn-sm btn-danger" @click="deleteWorkflow(w)">删除</button>
            </div>
          </div>
        </div>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">⚙️</div><div>暂无工作流</div></div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header"><h3>自愈日志</h3></div>
      <div class="panel-body">
        <table v-if="logs.length" class="table">
          <thead><tr><th>时间</th><th>工作流</th><th>动作</th><th>目标</th><th>结果</th></tr></thead>
          <tbody>
            <tr v-for="lg in logs" :key="lg.id">
              <td class="text-sm">{{ formatTime(lg.created_at) }}</td>
              <td>#{{ lg.remediation_id }}</td>
              <td>{{ lg.action_type }}</td>
              <td class="text-sm">{{ lg.target }}</td>
              <td><span class="badge" :class="lg.success ? 'resolved' : 'critical'">{{ lg.success ? '成功' : '失败' }}</span></td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">暂无执行日志</div>
      </div>
    </div>

    <div v-if="createVisible" class="modal-overlay" @click.self="createVisible = false">
      <div class="modal-box">
        <div class="modal-header"><h3>新建自愈工作流</h3><button class="modal-close" @click="createVisible = false">×</button></div>
        <div class="modal-body">
          <div class="form-group"><label>名称</label><input v-model="form.name" placeholder="如：CPU 高自愈流程" /></div>
          <div class="form-group"><label>关联告警规则 ID（可选）</label><input v-model.number="form.rule_id" type="number" placeholder="留空匹配所有" /></div>
          <div class="form-group">
            <label>步骤定义（JSON 数组）</label>
            <textarea v-model="form.steps" rows="8" placeholder='["healthcheck","restart","notify"]'></textarea>
            <p class="form-tip">可用操作：restart / clean / scale / notify / healthcheck</p>
          </div>
          <div class="form-actions"><button class="btn" @click="createVisible = false">取消</button><button class="btn btn-primary" @click="createWorkflow" :disabled="creating">{{ creating ? '创建中...' : '创建' }}</button></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const workflows = ref([])
const logs = ref([])
const total = ref(0)
const createVisible = ref(false)
const creating = ref(false)
const running = ref(null)
const form = reactive({ name: '', rule_id: 0, steps: '["healthcheck","restart","notify"]' })

async function loadData() {
  loading.value = true
  try {
    const data = await request.get('/remediation-workflows/api/list')
    workflows.value = data.workflows || []
    logs.value = data.logs || []
    total.value = data.total || 0
  } catch (e) { ElMessage.error('加载失败: ' + e.message) } finally { loading.value = false }
}

function openCreate() {
  Object.assign(form, { name: '', rule_id: 0, steps: '["healthcheck","restart","notify"]' })
  createVisible.value = true
}

async function createWorkflow() {
  if (!form.name) { ElMessage.warning('请填写名称'); return }
  creating.value = true
  try {
    const fd = new FormData()
    fd.append('name', form.name)
    fd.append('rule_id', form.rule_id)
    fd.append('steps', form.steps)
    await request.post('/remediation-workflows/api/create', fd)
    ElMessage.success('创建成功')
    createVisible.value = false
    loadData()
  } catch (e) { ElMessage.error('创建失败: ' + e.message) } finally { creating.value = false }
}

async function toggleWorkflow(w) {
  try {
    await request.post(`/remediation-workflows/api/${w.id}/toggle`)
    ElMessage.success(w.enabled ? '已禁用' : '已启用')
    loadData()
  } catch (e) { ElMessage.error('操作失败: ' + e.message) }
}

async function deleteWorkflow(w) {
  try {
    await ElMessageBox.confirm(`确认删除工作流"${w.name}"？`, '删除确认')
    await request.post(`/remediation-workflows/api/${w.id}/delete`)
    ElMessage.success('已删除')
    loadData()
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e)) }
}

async function runWorkflow(w) {
  try {
    await ElMessageBox.confirm(`确认运行工作流"${w.name}"？将处理最近的触发告警`, '运行确认')
    running.value = w.id
    const data = await request.post(`/remediation-workflows/api/${w.id}/run`)
    ElMessage.success(`运行完成，处理 ${data.ran} 条告警`)
    loadData()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('运行失败: ' + (e.message || e))
  } finally { running.value = null }
}

function formatTime(s) { return s ? s.substring(11, 19) : '-' }

onMounted(loadData)
</script>

<style scoped>
.wf-page { padding: 4px; }
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
.wf-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 12px; }
.wf-card { border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; padding: 14px; }
.wf-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.wf-name { font-weight: 600; font-size: 0.95rem; }
.wf-steps { margin-bottom: 10px; font-size: 0.8rem; }
.steps-label { color: var(--text-secondary, #64748b); margin-right: 4px; }
.step-chip { display: inline-block; background: rgba(99,102,241,0.1); color: #6366f1; padding: 2px 8px; border-radius: 6px; margin-right: 4px; font-size: 0.75rem; }
.step-arrow { color: var(--text-tertiary, #94a3b8); margin-left: 4px; }
.wf-actions { display: flex; gap: 6px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.resolved { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.critical { background: rgba(239,68,68,0.1); color: #ef4444; }
.badge.info { background: rgba(100,116,139,0.1); color: #64748b; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 12px; width: 90%; max-width: 560px; max-height: 85vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.2); }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.modal-header h3 { margin: 0; font-size: 1.1rem; }
.modal-close { background: none; border: none; font-size: 24px; cursor: pointer; color: var(--text-secondary, #64748b); line-height: 1; }
.modal-body { padding: 20px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 0.8rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.form-group input, .form-group textarea { width: 100%; padding: 8px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.85rem; box-sizing: border-box; }
.form-group textarea { font-family: monospace; resize: vertical; }
.form-tip { font-size: 0.72rem; color: var(--text-tertiary, #94a3b8); margin: 4px 0 0; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
