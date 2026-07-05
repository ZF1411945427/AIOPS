<template>
  <div class="pm-page">
    <div class="page-header">
      <h1>预测模型</h1>
      <p>时序预测模型配置 · 共 {{ models.length }} 个模型</p>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="openCreate">+ 新建模型</button>
      <button class="btn" @click="loadModels">刷新</button>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="models.length" class="card-grid">
          <div v-for="m in models" :key="m.id" class="model-card">
            <div class="card-top">
              <span class="model-name">{{ m.name }}</span>
              <span class="badge" :class="m.enabled ? 'on' : 'off'">{{ m.enabled ? '启用' : '禁用' }}</span>
            </div>
            <div class="card-meta">
              <div><span class="meta-label">指标</span><span>{{ m.metric_name || '-' }}</span></div>
              <div><span class="meta-label">类型</span><span class="badge type">{{ typeLabel(m.model_type) }}</span></div>
              <div><span class="meta-label">资产ID</span><span>{{ m.asset_id || '全局' }}</span></div>
              <div><span class="meta-label">参数</span><span class="text-sm">{{ m.params }}</span></div>
            </div>
            <div class="card-actions">
              <button class="btn btn-sm" @click="toggleModel(m)">{{ m.enabled ? '禁用' : '启用' }}</button>
              <button class="btn btn-sm btn-danger" @click="deleteModel(m)">删除</button>
            </div>
          </div>
        </div>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">📈</div><div>暂无预测模型</div></div>
      </div>
    </div>

    <div v-if="showDialog" class="modal-overlay" @click.self="showDialog = false">
      <div class="modal-box">
        <h3>新建预测模型</h3>
        <div class="form-row"><label>名称</label><input v-model="form.name" class="input"></div>
        <div class="form-row"><label>指标名</label><input v-model="form.metric_name" class="input"></div>
        <div class="form-row"><label>资产 ID（可选）</label><input v-model.number="form.asset_id" type="number" class="input"></div>
        <div class="form-row"><label>模型类型</label>
          <select v-model="form.model_type" class="input">
            <option value="linear">线性回归</option>
            <option value="polynomial">多项式</option>
            <option value="rolling_avg">移动平均</option>
          </select>
        </div>
        <div class="form-row"><label>参数 JSON</label><input v-model="form.params" class="input" placeholder='{"window": 20}'></div>
        <div class="modal-actions">
          <button class="btn" @click="showDialog = false">取消</button>
          <button class="btn btn-primary" @click="createModel">创建</button>
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
const models = ref([])
const showDialog = ref(false)
const form = ref({ name: '', metric_name: '', asset_id: 0, model_type: 'linear', params: '{"window": 20}' })

function typeLabel(t) {
  return { linear: '线性回归', polynomial: '多项式', rolling_avg: '移动平均' }[t] || t
}

async function loadModels() {
  loading.value = true
  try {
    const data = await request.get('/prediction-models/api/list')
    models.value = data.models || []
  } catch (e) {
    ElMessage.error('加载失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.value = { name: '', metric_name: '', asset_id: 0, model_type: 'linear', params: '{"window": 20}' }
  showDialog.value = true
}

async function createModel() {
  if (!form.value.name || !form.value.metric_name) {
    ElMessage.warning('名称和指标不能为空')
    return
  }
  try {
    await request.post('/prediction-models/api/create', form.value)
    ElMessage.success('创建成功')
    showDialog.value = false
    loadModels()
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.message || e))
  }
}

async function toggleModel(m) {
  try {
    await request.post(`/prediction-models/api/${m.id}/toggle`)
    loadModels()
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.message || e))
  }
}

async function deleteModel(m) {
  try {
    await ElMessageBox.confirm(`确认删除模型「${m.name}」？`, '删除确认', { type: 'warning' })
    await request.delete(`/prediction-models/api/${m.id}/delete`)
    ElMessage.success('已删除')
    loadModels()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

onMounted(loadModels)
</script>

<style scoped>
.pm-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 16px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.model-card { border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; padding: 14px; background: var(--bg-card-solid, #fff); }
.card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.model-name { font-weight: 600; font-size: 0.95rem; color: var(--text, #1e293b); }
.card-meta { font-size: 0.8rem; display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }
.card-meta > div { display: flex; gap: 8px; }
.meta-label { color: var(--text-secondary, #64748b); min-width: 56px; }
.card-actions { display: flex; gap: 8px; }
.text-sm { font-size: 0.75rem; color: var(--text-secondary, #64748b); word-break: break-all; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.on { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.off { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.type { background: rgba(99,102,241,0.1); color: #6366f1; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 380px; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; color: var(--text, #1e293b); }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
