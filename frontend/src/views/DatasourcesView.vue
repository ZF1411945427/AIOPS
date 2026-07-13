<template>
  <div class="ds-page">
    <div class="page-header">
      <h1>数据源管理</h1>
      <p>采集数据源配置 · 共 {{ sources.length }} 个</p>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="openCreate">+ 新增数据源</button>
      <button class="btn" @click="loadSources">刷新</button>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="sources.length" class="table">
          <thead>
            <tr>
              <th>ID</th><th>名称</th><th>类型</th><th>地址</th><th>认证</th>
              <th>状态</th><th>采集间隔</th><th>最后采集</th><th>采集状态</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in sources" :key="s.id">
              <td>{{ s.id }}</td>
              <td>{{ s.name }}</td>
              <td><span class="badge type">{{ s.type }}</span></td>
              <td class="text-sm">{{ s.endpoint || '-' }}</td>
              <td><span class="badge auth">{{ s.auth_type }}</span></td>
              <td><span class="badge" :class="s.enabled ? 'on' : 'off'">{{ s.enabled ? '启用' : '停用' }}</span></td>
              <td class="text-sm">{{ s.scrape_interval }}s</td>
              <td class="text-sm">{{ s.last_scraped_at || '-' }}</td>
              <td><span v-if="s.last_status" class="badge" :class="s.last_status === 'success' ? 'on' : 'off'">{{ s.last_status }}</span><span v-else class="text-sm">-</span></td>
              <td>
                <button class="btn btn-sm" @click="openEdit(s)">编辑</button>
                <button class="btn btn-sm" @click="toggleSource(s)">{{ s.enabled ? '停用' : '启用' }}</button>
                <button class="btn btn-sm" @click="testSource(s.id)">测试</button>
                <button class="btn btn-sm btn-danger" @click="deleteSource(s.id, s.name)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">🔌</div>
          <div>暂无数据源</div>
        </div>
      </div>
    </div>

    <!-- 新增/编辑弹窗 -->
    <div v-if="showDialog" class="modal-overlay" @click.self="showDialog = false">
      <div class="modal-box">
        <div class="modal-header">
          <h3>{{ isEdit ? '编辑数据源' : '新增数据源' }}</h3>
          <button class="modal-close" @click="showDialog = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group"><label>名称 <span class="required">*</span></label>
            <input v-model="form.name" class="input" placeholder="如: 生产环境 Prometheus" />
          </div>
          <div class="form-group"><label>类型 <span class="required">*</span></label>
            <select v-model="form.type" class="input" :disabled="isEdit">
              <option value="">-- 选择类型 --</option>
              <option v-for="(info, key) in dsTypes" :key="key" :value="key">{{ info.label }}</option>
            </select>
          </div>
          <div class="form-group"><label>地址 (endpoint)</label>
            <input v-model="form.endpoint" class="input" placeholder="如: http://prometheus:9090" />
          </div>
          <div class="form-group"><label>认证方式</label>
            <select v-model="form.auth_type" class="input">
              <option v-for="(label, key) in authTypes" :key="key" :value="key">{{ label }}</option>
            </select>
          </div>

          <!-- 认证配置 -->
          <div v-if="form.auth_type === 'basic'" class="auth-section">
            <div class="form-group"><label>用户名</label><input v-model="authConfig.username" class="input" placeholder="用户名" /></div>
            <div class="form-group"><label>密码</label><input v-model="authConfig.password" type="password" class="input" placeholder="密码" /></div>
          </div>
          <div v-if="form.auth_type === 'bearer'" class="auth-section">
            <div class="form-group"><label>Token</label><input v-model="authConfig.token" class="input" placeholder="Bearer Token" /></div>
          </div>
          <div v-if="form.auth_type === 'api_key'" class="auth-section">
            <div class="form-group"><label>Key</label><input v-model="authConfig.api_key" class="input" placeholder="API Key" /></div>
            <div class="form-group"><label>Value</label><input v-model="authConfig.api_value" class="input" placeholder="API Key 值" /></div>
          </div>

          <!-- SSH 认证额外配置 -->
          <div v-if="form.type === 'ssh'" class="auth-section">
            <div class="form-group"><label>SSH 用户</label><input v-model="authConfig.ssh_user" class="input" placeholder="root" /></div>
            <div class="form-group"><label>SSH 密码</label><input v-model="authConfig.ssh_password" type="password" class="input" placeholder="密码" /></div>
            <div class="form-group"><label>SSH 端口</label><input v-model.number="authConfig.ssh_port" type="number" class="input" placeholder="22" /></div>
          </div>

          <!-- K8s 认证额外配置 -->
          <div v-if="form.type === 'kubernetes'" class="auth-section">
            <div class="form-group"><label>API Server URL</label><input v-model="authConfig.k8s_api_server" class="input" placeholder="https://192.168.1.10:6443" /></div>
            <div class="form-group"><label>Token</label><textarea v-model="authConfig.k8s_token" class="input" rows="3" placeholder="ServiceAccount Token"></textarea></div>
          </div>

          <div class="form-group"><label>采集间隔 (秒)</label>
            <input v-model.number="form.scrape_interval" type="number" class="input" placeholder="30" min="10" />
          </div>
          <div class="form-actions">
            <button class="btn" @click="showDialog = false">取消</button>
            <button class="btn btn-primary" :disabled="saving" @click="saveSource">{{ saving ? '保存中...' : '保存' }}</button>
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
const saving = ref(false)
const sources = ref([])
const showDialog = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const dsTypes = ref({})
const authTypes = ref({})
const form = reactive({
  name: '',
  type: '',
  endpoint: '',
  auth_type: 'none',
  scrape_interval: 30,
})
const authConfig = reactive({
  username: '', password: '',
  token: '',
  api_key: '', api_value: '',
  ssh_user: 'root', ssh_password: '', ssh_port: 22,
  k8s_api_server: '', k8s_token: '',
})

function buildAuthConfig() {
  const at = form.auth_type
  const t = form.type
  if (at === 'basic') return { username: authConfig.username, password: authConfig.password }
  if (at === 'bearer') return { token: authConfig.token }
  if (at === 'api_key') return { api_key: authConfig.username, api_value: authConfig.password }
  if (t === 'ssh') return { ssh_user: authConfig.ssh_user, ssh_password: authConfig.ssh_password, ssh_port: authConfig.ssh_port }
  if (t === 'kubernetes') return { k8s_api_server: authConfig.k8s_api_server, k8s_token: authConfig.k8s_token }
  return {}
}

function parseAuthConfig(cfg, type, authType) {
  if (authType === 'basic') { authConfig.username = cfg.username || ''; authConfig.password = cfg.password || '' }
  else if (authType === 'bearer') { authConfig.token = cfg.token || '' }
  else if (authType === 'api_key') { authConfig.username = cfg.api_key || ''; authConfig.password = cfg.api_value || '' }
  if (type === 'ssh') { authConfig.ssh_user = cfg.ssh_user || 'root'; authConfig.ssh_password = cfg.ssh_password || ''; authConfig.ssh_port = cfg.ssh_port || 22 }
  if (type === 'kubernetes') { authConfig.k8s_api_server = cfg.k8s_api_server || ''; authConfig.k8s_token = cfg.k8s_token || '' }
}

async function loadSources() {
  loading.value = true
  try {
    const data = await request.get('/datasources/api/list')
    sources.value = data.sources || []
    dsTypes.value = data.ds_types || {}
    authTypes.value = data.auth_types || {}
  } catch (e) {
    ElMessage.error('加载失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  isEdit.value = false
  editId.value = null
  Object.assign(form, { name: '', type: '', endpoint: '', auth_type: 'none', scrape_interval: 30 })
  Object.assign(authConfig, { username: '', password: '', token: '', api_key: '', api_value: '', ssh_user: 'root', ssh_password: '', ssh_port: 22, k8s_api_server: '', k8s_token: '' })
  showDialog.value = true
}

async function openEdit(s) {
  isEdit.value = true
  editId.value = s.id
  form.name = s.name
  form.type = s.type
  form.endpoint = s.endpoint || ''
  form.auth_type = s.auth_type || 'none'
  form.scrape_interval = s.scrape_interval || 30
  Object.assign(authConfig, { username: '', password: '', token: '', api_key: '', api_value: '', ssh_user: 'root', ssh_password: '', ssh_port: 22, k8s_api_server: '', k8s_token: '' })
  try {
    const detail = await request.get(`/datasources/api/${s.id}`)
    if (detail.auth_config) {
      try {
        const cfg = JSON.parse(detail.auth_config)
        parseAuthConfig(cfg, form.type, form.auth_type)
      } catch {}
    }
  } catch {}
  showDialog.value = true
}

async function saveSource() {
  if (!form.name || !form.type) { ElMessage.warning('请填写名称和类型'); return }
  saving.value = true
  try {
    const payload = {
      name: form.name,
      type: form.type,
      endpoint: form.endpoint,
      auth_type: form.auth_type,
      scrape_interval: form.scrape_interval,
      auth_config: JSON.stringify(buildAuthConfig()),
      enabled: true,
    }
    if (isEdit.value) {
      await request.put(`/datasources/api/${editId.value}`, payload)
      ElMessage.success('更新成功')
    } else {
      await request.post('/datasources/api/create', payload)
      ElMessage.success('创建成功')
    }
    showDialog.value = false
    loadSources()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.error || e.message))
  } finally {
    saving.value = false
  }
}

async function toggleSource(s) {
  try {
    await request.post(`/datasources/api/${s.id}/toggle`)
    ElMessage.success(s.enabled ? '已停用' : '已启用')
    loadSources()
  } catch (e) {
    ElMessage.error('操作失败: ' + e.message)
  }
}

async function testSource(id) {
  try {
    ElMessage.info('测试中...')
    const data = await request.post(`/datasources/api/${id}/test`)
    if (data.ok) ElMessage.success('连接成功: ' + data.message)
    else ElMessage.warning('连接失败: ' + data.message)
  } catch (e) {
    ElMessage.error('测试失败: ' + e.message)
  }
}

async function deleteSource(id, name) {
  try {
    await ElMessageBox.confirm(`确认删除数据源「${name}」？`, '删除确认', { type: 'warning' })
    await request.post(`/datasources/api/${id}/delete`)
    ElMessage.success('已删除')
    loadSources()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

onMounted(loadSources)
</script>

<style scoped>
.ds-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 16px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; transition: all 0.2s; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-danger { color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-danger:hover { background: rgba(239,68,68,0.08); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 16px; }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; white-space: nowrap; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); white-space: nowrap; }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.type { background: rgba(99,102,241,0.1); color: #6366f1; }
.badge.auth { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.on { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.off { background: rgba(100,116,139,0.1); color: #64748b; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 12px; width: 90%; max-width: 520px; max-height: 85vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.2); }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.modal-header h3 { margin: 0; font-size: 1rem; }
.modal-close { background: none; border: none; font-size: 20px; cursor: pointer; color: var(--text-secondary, #64748b); line-height: 1; padding: 0; }
.modal-close:hover { color: var(--text, #1e293b); }
.modal-body { padding: 20px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 0.8rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.form-group input, .form-group select, .form-group textarea { width: 100%; padding: 8px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.85rem; box-sizing: border-box; }
.form-group textarea { resize: vertical; font-family: inherit; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.required { color: #ef4444; }
.auth-section { background: var(--bg-hover, rgba(0,0,0,0.03)); border-radius: 6px; padding: 12px; margin-bottom: 12px; }
</style>
