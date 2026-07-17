<template>
  <div class="cmdb-page">
    <div class="page-header">
      <h1>外部 CMDB</h1>
      <p>外部配置管理数据库同步 · 共 {{ configs.length }} 个配置</p>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="openCreate">+ 新增配置</button>
      <button class="btn" @click="loadConfigs">刷新</button>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="configs.length" class="card-grid">
          <div v-for="c in configs" :key="c.id" class="cmdb-card">
            <div class="card-top">
              <span class="cmdb-name">{{ c.name }}</span>
              <span class="badge" :class="c.enabled ? 'on' : 'off'">{{ c.enabled ? '启用' : '禁用' }}</span>
            </div>
            <div class="card-meta">
              <div><span class="meta-label">类型</span><span class="badge type">{{ typeLabel(c.cmdb_type) }}</span></div>
              <div><span class="meta-label">API URL</span><span class="text-sm">{{ c.api_url || '-' }}</span></div>
              <div><span class="meta-label">同步间隔</span><span>{{ c.sync_interval }}s</span></div>
              <div><span class="meta-label">上次同步</span><span class="text-sm">{{ c.last_synced_at || '从未' }}</span></div>
            </div>
            <div class="card-actions">
              <button class="btn btn-sm" @click="toggleConfig(c)">{{ c.enabled ? '禁用' : '启用' }}</button>
              <button class="btn btn-sm btn-primary" @click="syncConfig(c)" :disabled="syncing === c.id">{{ syncing === c.id ? '同步中...' : '同步' }}</button>
              <button class="btn btn-sm btn-danger" @click="deleteConfig(c)">删除</button>
            </div>
          </div>
        </div>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">🗄️</div><div>暂无 CMDB 配置</div></div>
      </div>
    </div>

    <div v-if="showDialog" class="modal-overlay" @click.self="showDialog = false">
      <div class="modal-box">
        <h3>新增 CMDB 配置</h3>
        <div class="form-row"><label>名称</label><input v-model="form.name" class="input"></div>
        <div class="form-row"><label>类型</label>
          <select v-model="form.cmdb_type" class="input">
            <option value="generic">通用</option>
            <option value="cmdb">CMDB</option>
            <option value="zabbix">Zabbix</option>
            <option value="nacos">Nacos</option>
          </select>
        </div>
        <div class="form-row"><label>API URL</label><input v-model="form.api_url" class="input" placeholder="http://cmdb.example.com/api/assets"></div>
        <div class="form-row"><label>同步间隔(秒)</label><input v-model.number="form.sync_interval" type="number" class="input"></div>
        <div class="form-row"><label>认证 JSON</label><input v-model="form.auth_json" class="input" placeholder='{"token": "xxx"}'></div>
        <div class="modal-actions">
          <button class="btn" @click="showDialog = false">取消</button>
          <button class="btn btn-primary" @click="createConfig">创建</button>
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
const configs = ref([])
const showDialog = ref(false)
const syncing = ref(0)
const form = ref({ name: '', cmdb_type: 'generic', api_url: '', sync_interval: 60, auth_json: '{}' })

function typeLabel(t) {
  return { generic: '通用', cmdb: 'CMDB', zabbix: 'Zabbix', nacos: 'Nacos' }[t] || t
}

async function loadConfigs() {
  loading.value = true
  try {
    const data = await request.get('/ext-cmdb/api/list')
    configs.value = data.configs || []
  } catch (e) {
    ElMessage.error('加载失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.value = { name: '', cmdb_type: 'generic', api_url: '', sync_interval: 60, auth_json: '{}' }
  showDialog.value = true
}

async function createConfig() {
  if (!form.value.name || !form.value.api_url) {
    ElMessage.warning('名称和 API URL 不能为空')
    return
  }
  try {
    await request.post('/ext-cmdb/api/create', form.value)
    ElMessage.success('创建成功')
    showDialog.value = false
    loadConfigs()
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.message || e))
  }
}

async function toggleConfig(c) {
  try {
    await request.post(`/ext-cmdb/api/${c.id}/toggle`)
    loadConfigs()
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.message || e))
  }
}

async function syncConfig(c) {
  syncing.value = c.id
  try {
    const data = await request.post(`/ext-cmdb/api/${c.id}/sync`)
    if (data.status === 'ok') {
      ElMessage.success(`同步成功，新增 ${data.synced} 个资产`)
      loadConfigs()
    } else {
      ElMessage.error(data.message || '同步失败')
    }
  } catch (e) {
    ElMessage.error('同步失败: ' + (e.message || e))
  } finally {
    syncing.value = 0
  }
}

async function deleteConfig(c) {
  try {
    await ElMessageBox.confirm(`确认删除配置「${c.name}」？`, '删除确认', { type: 'warning' })
    await request.delete(`/ext-cmdb/api/${c.id}/delete`)
    ElMessage.success('已删除')
    loadConfigs()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

onMounted(loadConfigs)
</script>

<style scoped>
.cmdb-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 16px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
.cmdb-card { border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; padding: 14px; background: var(--bg-card-solid, #fff); }
.card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.cmdb-name { font-weight: 600; font-size: 0.95rem; color: var(--text, #1e293b); }
.card-meta { font-size: 0.8rem; display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }
.card-meta > div { display: flex; gap: 8px; }
.meta-label { color: var(--text-secondary, #64748b); min-width: 64px; }
.card-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.text-sm { font-size: 0.75rem; color: var(--text-secondary, #64748b); word-break: break-all; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.on { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.off { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.type { background: rgba(99,102,241,0.1); color: #6366f1; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 400px; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; color: var(--text, #1e293b); }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
