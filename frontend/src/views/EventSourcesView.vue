<template>
  <div class="event-sources-page">
    <div class="page-header">
      <h1>事件源配置</h1>
      <p>接入 Zabbix / Prometheus / Webhook 外部事件源 · 共 {{ total }} 个</p>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="openCreate">+ 新增事件源</button>
      <button class="btn" @click="loadSources">刷新</button>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="sources.length" class="source-list">
          <div v-for="s in sources" :key="s.id" class="source-card">
            <div class="source-head">
              <span class="source-name">{{ s.name }}</span>
              <span class="badge" :class="s.source_type">{{ s.source_type }}</span>
              <span class="badge" :class="s.enabled ? 'resolved' : 'info'">{{ s.enabled ? '启用' : '禁用' }}</span>
            </div>
            <div class="source-meta">
              <div class="meta-item"><span class="meta-label">API URL</span><span class="meta-value">{{ s.api_url || '-' }}</span></div>
              <div class="meta-item"><span class="meta-label">同步间隔</span><span class="meta-value">{{ s.sync_interval }}s</span></div>
              <div class="meta-item"><span class="meta-label">上次同步</span><span class="meta-value">{{ s.last_sync || '未同步' }}</span></div>
            </div>
            <div class="source-actions">
              <button class="btn btn-sm" @click="toggleSource(s)">{{ s.enabled ? '禁用' : '启用' }}</button>
              <button class="btn btn-sm btn-primary" @click="syncSource(s)" :disabled="syncing === s.id">
                {{ syncing === s.id ? '同步中...' : '同步' }}
              </button>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">🔌</div>
          <div>暂无事件源，点击"新增事件源"添加</div>
        </div>
      </div>
    </div>

    <div v-if="createVisible" class="modal-overlay" @click.self="createVisible = false">
      <div class="modal-box">
        <div class="modal-header">
          <h3>新增事件源</h3>
          <button class="modal-close" @click="createVisible = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>名称</label>
            <input v-model="form.name" placeholder="如：生产环境 Zabbix" />
          </div>
          <div class="form-group">
            <label>类型</label>
            <select v-model="form.source_type">
              <option value="zabbix">Zabbix</option>
              <option value="prometheus">Prometheus</option>
              <option value="webhook">Webhook</option>
              <option value="generic">通用</option>
            </select>
          </div>
          <div class="form-group">
            <label>API URL</label>
            <input v-model="form.api_url" placeholder="如：http://zabbix.example.com" />
          </div>
          <div class="form-group">
            <label>同步间隔(秒)</label>
            <input v-model.number="form.sync_interval" type="number" />
          </div>
          <div class="form-group">
            <label>认证 JSON</label>
            <textarea v-model="form.auth_json" rows="3" placeholder='{"user":"Admin","password":"zabbix"}'></textarea>
          </div>
          <div class="form-actions">
            <button class="btn" @click="createVisible = false">取消</button>
            <button class="btn btn-primary" @click="createSource" :disabled="creating">{{ creating ? '创建中...' : '创建' }}</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const sources = ref([])
const total = ref(0)
const createVisible = ref(false)
const creating = ref(false)
const syncing = ref(null)
const form = reactive({
  name: '', source_type: 'zabbix', api_url: '',
  sync_interval: 60, auth_json: '{"user":"Admin","password":"zabbix"}',
})

async function loadSources() {
  loading.value = true
  try {
    const data = await request.get('/event-sources/api/list')
    sources.value = data.sources || []
    total.value = data.total || 0
  } catch (e) {
    ElMessage.error('加载事件源失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, { name: '', source_type: 'zabbix', api_url: '', sync_interval: 60, auth_json: '{"user":"Admin","password":"zabbix"}' })
  createVisible.value = true
}

async function createSource() {
  if (!form.name || !form.api_url) {
    ElMessage.warning('请填写名称和 API URL')
    return
  }
  creating.value = true
  try {
    const fd = new FormData()
    fd.append('name', form.name)
    fd.append('source_type', form.source_type)
    fd.append('api_url', form.api_url)
    fd.append('auth_json', form.auth_json)
    fd.append('sync_interval', form.sync_interval)
    await request.post('/event-sources/api/create', fd)
    ElMessage.success('创建成功')
    createVisible.value = false
    loadSources()
  } catch (e) {
    ElMessage.error('创建失败: ' + e.message)
  } finally {
    creating.value = false
  }
}

async function toggleSource(s) {
  try {
    await request.post(`/event-sources/api/${s.id}/toggle`)
    ElMessage.success(s.enabled ? '已禁用' : '已启用')
    loadSources()
  } catch (e) {
    ElMessage.error('操作失败: ' + e.message)
  }
}

async function syncSource(s) {
  syncing.value = s.id
  try {
    const data = await request.post(`/event-sources/api/${s.id}/sync`)
    ElMessage.success(`同步完成，新增 ${data.synced} 条告警`)
    loadSources()
  } catch (e) {
    ElMessage.error('同步失败: ' + (e.response?.data?.error || e.message))
  } finally {
    syncing.value = null
  }
}

onMounted(loadSources)
</script>

<style scoped>
.event-sources-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; transition: all 0.2s; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.source-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }
.source-card { border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; padding: 14px; background: var(--bg-card-solid, #fff); }
.source-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.source-name { font-weight: 600; font-size: 0.95rem; color: var(--text, #1e293b); }
.source-meta { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
.meta-item { display: flex; gap: 8px; font-size: 0.78rem; }
.meta-label { color: var(--text-secondary, #64748b); min-width: 70px; }
.meta-value { color: var(--text, #1e293b); word-break: break-all; }
.source-actions { display: flex; gap: 8px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.zabbix { background: rgba(217,70,239,0.1); color: #d946ef; }
.badge.prometheus { background: rgba(245,158,11,0.1); color: #f59e0b; }
.badge.webhook { background: rgba(59,130,246,0.1); color: #3b82f6; }
.badge.generic { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.info { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.resolved { background: rgba(34,197,94,0.1); color: #22c55e; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 12px; width: 90%; max-width: 520px; max-height: 85vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.2); }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.modal-header h3 { margin: 0; font-size: 1.1rem; }
.modal-close { background: none; border: none; font-size: 24px; cursor: pointer; color: var(--text-secondary, #64748b); line-height: 1; }
.modal-body { padding: 20px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 0.8rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.form-group input, .form-group select, .form-group textarea { width: 100%; padding: 8px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.85rem; box-sizing: border-box; }
.form-group textarea { font-family: monospace; resize: vertical; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
