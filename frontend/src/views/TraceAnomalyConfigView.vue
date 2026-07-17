<template>
  <div class="ta-page">
    <div class="page-header">
      <h1>Trace 异常检测配置</h1>
      <p>链路追踪异常阈值 · 服务级别延迟/错误率检测</p>
    </div>
    <div class="toolbar">
      <input v-model="searchSvc" class="input" placeholder="服务名搜索" @keyup.enter="loadConfigs" />
      <button class="btn btn-primary" @click="openCreate">+ 新建配置</button>
      <button class="btn" @click="loadConfigs">刷新</button>
    </div>
    <div class="panel">
      <div class="panel-head">检测规则</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="!items.length" class="empty-state">暂无配置</div>
        <div v-else class="table-wrap">
          <table class="table">
            <thead><tr><th>名称</th><th>服务</th><th>延迟阈值(ms)</th><th>错误率阈值</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="c in items" :key="c.id">
                <td>{{ c.name }}</td>
                <td><code>{{ c.service_name || '*' }}</code></td>
                <td>{{ c.latency_threshold_ms }}</td>
                <td>{{ (c.error_rate_threshold * 100).toFixed(1) }}%</td>
                <td><span class="badge" :class="c.enabled ? 'resolved' : 'info'">{{ c.enabled ? '运行中' : '已暂停' }}</span></td>
                <td>
                  <button class="btn btn-sm" @click="openEdit(c)">编辑</button>
                  <button class="btn btn-sm" :class="c.enabled ? 'btn-warning' : 'btn-primary'" @click="toggleConfig(c)">{{ c.enabled ? '暂停' : '启用' }}</button>
                  <button class="btn btn-sm btn-danger" @click="deleteConfig(c)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
    <div v-if="showForm" class="modal-overlay" @click.self="showForm = false">
      <div class="modal-box">
        <h3>{{ editing ? '编辑配置' : '新建配置' }}</h3>
        <div class="form-group"><label class="form-label">名称</label><input v-model="form.name" class="input" /></div>
        <div class="form-group"><label class="form-label">服务名（留空=全部）</label><input v-model="form.service_name" class="input" placeholder="service-a" /></div>
        <div class="form-group"><label class="form-label">延迟阈值 (ms)</label><input v-model.number="form.latency_threshold_ms" type="number" class="input" /></div>
        <div class="form-group"><label class="form-label">错误率阈值 (0~1)</label><input v-model.number="form.error_rate_threshold" type="number" step="0.01" min="0" max="1" class="input" /></div>
        <div class="modal-actions">
          <button class="btn" @click="showForm = false">取消</button>
          <button class="btn btn-primary" @click="submitForm">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'
const items = ref([])
const loading = ref(false)
const showForm = ref(false)
const editing = ref(false)
const searchSvc = ref('')
const form = ref({ name: '', service_name: '', latency_threshold_ms: 1000, error_rate_threshold: 0.05 })
async function loadConfigs() {
  loading.value = true
  try {
    const params = {}
    if (searchSvc.value) params.service_name = searchSvc.value
    const res = await request.get('/trace-anomaly/api/configs', { params })
    items.value = res.items || []
  } catch (e) { ElMessage.error('加载失败: ' + (e.message || e)) }
  finally { loading.value = false }
}
function openCreate() {
  editing.value = false
  form.value = { name: '', service_name: '', latency_threshold_ms: 1000, error_rate_threshold: 0.05 }
  showForm.value = true
}
function openEdit(c) {
  editing.value = true
  form.value = { ...c }
  showForm.value = true
}
async function submitForm() {
  try {
    if (editing.value) {
      await request.put(`/trace-anomaly/api/configs/${form.value.id}`, form.value)
      ElMessage.success('已更新')
    } else {
      await request.post('/trace-anomaly/api/configs', form.value)
      ElMessage.success('已创建')
    }
    showForm.value = false
    loadConfigs()
  } catch (e) { ElMessage.error('操作失败: ' + (e.message || e)) }
}
async function toggleConfig(c) {
  try {
    await request.post(`/trace-anomaly/api/configs/${c.id}/toggle`)
    ElMessage.success(c.enabled ? '已暂停' : '已启用')
    loadConfigs()
  } catch (e) { ElMessage.error('操作失败: ' + (e.message || e)) }
}
async function deleteConfig(c) {
  if (!confirm(`确认删除「${c.name}」？`)) return
  try {
    await request.delete(`/trace-anomaly/api/configs/${c.id}`)
    ElMessage.success('已删除')
    loadConfigs()
  } catch (e) { ElMessage.error('删除失败: ' + (e.message || e)) }
}
onMounted(loadConfigs)
</script>
<style scoped>
.ta-page { padding: 4px; }
.page-header { margin-bottom: 12px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; margin: 0 0 4px; }
.page-header p { color: var(--text-secondary,#64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong,rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid,#fff); cursor: pointer; font-size: 0.82rem; }
.btn-primary { background: var(--accent,#6366f1); color: #fff; border-color: var(--accent,#6366f1); }
.btn-warning { background: #d97706; color: #fff; border-color: #d97706; }
.btn-danger { background: #ef4444; color: #fff; border-color: #ef4444; }
.btn-sm { padding: 3px 8px; font-size: 0.75rem; }
.input { padding: 5px 10px; border: 1px solid var(--border,rgba(0,0,0,0.1)); border-radius: 6px; font-size: 0.82rem; outline: none; }
.input:focus { border-color: var(--accent,#6366f1); }
.panel { background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; margin-bottom: 14px; }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; }
.panel-body { padding: 16px 18px; }
.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.table th { text-align: left; padding: 8px 10px; border-bottom: 2px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; color: var(--text-secondary,#64748b); font-size: 0.75rem; text-transform: uppercase; }
.table td { padding: 10px 10px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.05)); }
.table tbody tr:hover { background: var(--bg-hover,rgba(0,0,0,0.02)); }
code { background: rgba(99,102,241,0.08); padding: 1px 5px; border-radius: 4px; font-size: 0.78rem; }
.badge { padding: 2px 8px; border-radius: 6px; font-size: 0.72rem; font-weight: 600; }
.resolved { background: rgba(34,197,94,0.12); color: #22c55e; }
.info { background: rgba(148,163,184,0.12); color: #64748b; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary,#94a3b8); font-size: 0.9rem; }
.form-group { margin-bottom: 10px; }
.form-label { display: block; font-size: 0.78rem; font-weight: 600; color: var(--text-secondary,#64748b); margin-bottom: 4px; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid,#fff); border-radius: 12px; padding: 24px; min-width: 380px; box-shadow: 0 8px 32px rgba(0,0,0,0.15); }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; font-weight: 600; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
