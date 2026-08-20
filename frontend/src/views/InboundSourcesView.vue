<template>
  <div class="inbound-page">
    <div class="page-header">
      <h1>入站集成</h1>
      <p>对接 Prometheus Alertmanager / Remote Write / 通用 Webhook · 共 {{ total }} 个入站源</p>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="openCreate">+ 新增入站源</button>
      <button class="btn" @click="loadSources">刷新</button>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="sources.length" class="source-list">
          <div v-for="s in sources" :key="s.id" class="source-card">
            <div class="source-head">
              <span class="source-name">{{ s.name }}</span>
              <span class="badge" :class="s.source_type">{{ sourceTypeLabel(s.source_type) }}</span>
              <span class="badge" :class="s.enabled ? 'resolved' : 'info'">{{ s.enabled ? '启用' : '禁用' }}</span>
            </div>

            <div class="source-meta">
              <div class="meta-title">入站端点（请配置到外部系统）</div>
              <div class="meta-item"><span class="meta-label">Alertmanager</span><span class="meta-value mono">{{ endpointFor(s, 'alertmanager') }}</span></div>
              <div class="meta-item"><span class="meta-label">Remote Write</span><span class="meta-value mono">{{ endpointFor(s, 'remote-write') }}</span></div>
              <div class="meta-item"><span class="meta-label">通用 Webhook</span><span class="meta-value mono">{{ endpointFor(s, 'webhook') }}</span></div>
              <div class="meta-item"><span class="meta-label">Token</span><span class="meta-value mono">{{ s.has_token ? (showToken === s.id ? s.endpoint_token : '••••••••••••') : '未设置' }}</span></div>
              <div class="meta-item" v-if="s.status_webhook_url"><span class="meta-label">状态回写</span><span class="meta-value mono">{{ s.status_webhook_url }}</span></div>
            </div>

            <div class="source-actions">
              <button class="btn btn-sm" @click="toggleShowToken(s)">{{ showToken === s.id ? '隐藏 Token' : '查看 Token' }}</button>
              <button class="btn btn-sm" @click="openEdit(s)">编辑</button>
              <button class="btn btn-sm" @click="regenerateToken(s)">重置 Token</button>
              <button class="btn btn-sm btn-danger" @click="deleteSource(s)">删除</button>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">🔌</div>
          <div>暂无入站源，点击"新增入站源"对接外部告警系统</div>
        </div>
      </div>
    </div>

    <div v-if="createVisible" class="modal-overlay" @click.self="createVisible = false">
      <div class="modal-box">
        <div class="modal-header">
          <h3>{{ editingId ? '编辑入站源' : '新增入站源' }}</h3>
          <button class="modal-close" @click="createVisible = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>名称</label>
            <input v-model="form.name" placeholder="如：生产 Prometheus" />
          </div>
          <div class="form-group">
            <label>类型</label>
            <select v-model="form.source_type">
              <option value="alertmanager">Alertmanager</option>
              <option value="prometheus_remote_write">Prometheus Remote Write</option>
              <option value="webhook">通用 Webhook</option>
              <option value="datadog">Datadog</option>
              <option value="pagerduty">PagerDuty</option>
            </select>
          </div>
          <div class="form-group">
            <label>入站标签 JSON（可选）</label>
            <textarea v-model="form.labels" rows="2" placeholder='{"env":"prod"}'></textarea>
          </div>
          <div class="form-group">
            <label>指标名 → 规则映射 JSON（remote_write 用）</label>
            <textarea v-model="form.metrics_to_rules" rows="2" placeholder='{"node_cpu":"cpu_usage"}'></textarea>
          </div>
          <div class="form-group">
            <label>无规则时自动创建告警规则</label>
            <input type="checkbox" v-model="form.auto_create_rule" style="width:auto;" />
          </div>
          <div class="form-group">
            <label>状态回写 URL（处置后回调源系统，可选）</label>
            <input v-model="form.status_webhook_url" placeholder="如：http://source-host/api/sync" />
          </div>
          <div class="form-group">
            <label>启用</label>
            <input type="checkbox" v-model="form.enabled" style="width:auto;" />
          </div>
          <div class="form-actions">
            <button class="btn" @click="createVisible = false">取消</button>
            <button class="btn btn-primary" @click="saveSource" :disabled="saving">{{ saving ? '保存中...' : '保存' }}</button>
          </div>
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
const sources = ref([])
const total = ref(0)
const createVisible = ref(false)
const saving = ref(false)
const editingId = ref(null)
const showToken = ref(null)

const form = reactive({
  name: '', source_type: 'alertmanager', labels: '{}',
  metrics_to_rules: '{}', auto_create_rule: false,
  status_webhook_url: '', enabled: true,
})

function sourceTypeLabel(t) {
  return { alertmanager: 'Alertmanager', prometheus_remote_write: 'Remote Write', webhook: 'Webhook', datadog: 'Datadog', pagerduty: 'PagerDuty' }[t] || t
}

function endpointFor(s, kind) {
  return `/api/inbound/${s.id}/${kind}?token=<YOUR_TOKEN>`
}

async function loadSources() {
  loading.value = true
  try {
    const data = await request.get('/api/inbound/sources')
    sources.value = data.items || []
    total.value = data.count || 0
  } catch (e) {
    ElMessage.error('加载入站源失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { name: '', source_type: 'alertmanager', labels: '{}', metrics_to_rules: '{}', auto_create_rule: false, status_webhook_url: '', enabled: true })
  createVisible.value = true
}

function openEdit(s) {
  editingId.value = s.id
  Object.assign(form, {
    name: s.name, source_type: s.source_type,
    labels: JSON.stringify(s.labels || {}, null, 2),
    metrics_to_rules: JSON.stringify(s.metrics_to_rules || {}, null, 2),
    auto_create_rule: !!s.auto_create_rule,
    status_webhook_url: s.status_webhook_url || '',
    enabled: !!s.enabled,
  })
  createVisible.value = true
}

function toggleShowToken(s) {
  showToken.value = showToken.value === s.id ? null : s.id
}

async function saveSource() {
  if (!form.name) {
    ElMessage.warning('请填写名称')
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.name, source_type: form.source_type,
      labels: safeJson(form.labels),
      metrics_to_rules: safeJson(form.metrics_to_rules),
      auto_create_rule: form.auto_create_rule,
      status_webhook_url: form.status_webhook_url,
      enabled: form.enabled,
    }
    if (editingId.value) {
      await request.post(`/api/inbound/sources/${editingId.value}/update`, payload)
      ElMessage.success('更新成功')
    } else {
      await request.post('/api/inbound/sources/create', payload)
      ElMessage.success('创建成功')
    }
    createVisible.value = false
    loadSources()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.message || e.message))
  } finally {
    saving.value = false
  }
}

function safeJson(s) {
  try {
    const parsed = JSON.parse(s || '{}')
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch (e) {
    ElMessage.warning('JSON 格式有误，请检查')
    return {}
  }
}

async function regenerateToken(s) {
  try {
    const data = await request.post(`/api/inbound/sources/${s.id}/regenerate-token`)
    ElMessage.success('Token 已重置')
    showToken.value = s.id
    s.endpoint_token = data.endpoint_token
    s.has_token = true
  } catch (e) {
    ElMessage.error('重置失败: ' + e.message)
  }
}

async function deleteSource(s) {
  try {
    await ElMessageBox.confirm(`确认删除入站源「${s.name}」？`, '删除确认', { type: 'warning' })
    await request.post(`/api/inbound/sources/${s.id}/delete`)
    ElMessage.success('已删除')
    loadSources()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.response?.data?.message || e.message))
  }
}

onMounted(loadSources)
</script>

<style scoped>
.inbound-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; transition: all 0.2s; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-danger { color: #dc2626; border-color: rgba(220,38,38,0.3); }
.btn-danger:hover { background: rgba(220,38,38,0.08); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.source-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 12px; }
.source-card { border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; padding: 14px; background: var(--bg-card-solid, #fff); }
.source-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.source-name { font-weight: 600; font-size: 0.95rem; color: var(--text, #1e293b); }
.source-meta { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
.meta-title { font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); margin-top: 4px; }
.meta-item { display: flex; gap: 8px; font-size: 0.76rem; align-items: baseline; }
.meta-label { color: var(--text-secondary, #64748b); min-width: 92px; flex-shrink: 0; }
.meta-value { color: var(--text, #1e293b); word-break: break-all; }
.mono { font-family: monospace; font-size: 0.72rem; }
.source-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.alertmanager { background: rgba(217,70,239,0.1); color: #d946ef; }
.badge.prometheus_remote_write { background: rgba(245,158,11,0.1); color: #f59e0b; }
.badge.webhook { background: rgba(59,130,246,0.1); color: #3b82f6; }
.badge.datadog { background: rgba(16,185,129,0.1); color: #10b981; }
.badge.pagerduty { background: rgba(236,72,153,0.1); color: #ec4899; }
.badge.info { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.resolved { background: rgba(34,197,94,0.1); color: #22c55e; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 12px; width: 90%; max-width: 560px; max-height: 85vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.2); }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.modal-header h3 { margin: 0; font-size: 1.1rem; }
.modal-close { background: none; border: none; font-size: 24px; cursor: pointer; color: var(--text-secondary, #64748b); line-height: 1; }
.modal-body { padding: 20px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 0.8rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.form-group input, .form-group select, .form-group textarea { width: 100%; padding: 8px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.85rem; box-sizing: border-box; }
.form-group textarea { font-family: monospace; resize: vertical; }
.form-group input[type="checkbox"] { width: auto; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
