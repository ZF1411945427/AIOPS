<template>
  <div class="assets-page">
    <div class="page-header">
      <h1>资产管理</h1>
      <p>CMDB 配置管理 · 共 {{ assets.length }} 项资产</p>
    </div>

    <div class="toolbar">
      <input v-model="search" @input="onSearch" placeholder="搜索资产名称..." class="search-input">
      <select v-model="ciType" @change="loadAssets">
        <option value="">全部 CI 类型</option>
        <option v-for="ct in ciTypes" :key="ct" :value="ct">{{ ct }}</option>
      </select>
      <a href="javascript:void(0)" class="btn btn-primary" @click="openCreate">+ 新增资产</a>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="assets.length" class="table">
          <thead>
            <tr>
              <th>ID</th><th>名称</th><th>CI 类型</th><th>IP</th><th>状态</th>
              <th>最后探测</th><th>延迟</th><th>集群</th><th>标签</th>
              <th>创建时间</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in assets" :key="a.id">
              <td>{{ a.id }}</td>
              <td>{{ a.name }}</td>
              <td><span class="badge ci-type">{{ a.ci_type || '-' }}</span></td>
              <td>{{ a.ip || '-' }}</td>
              <td><span class="badge" :class="a.status">{{ a.status }}</span></td>
              <td class="text-sm">{{ a.last_checked || '-' }}</td>
              <td class="text-sm">{{ a.latency_ms ? a.latency_ms + 'ms' : '-' }}</td>
              <td class="text-sm">{{ a.k8s_cluster || '-' }}</td>
              <td class="text-sm">{{ a.tags || '-' }}</td>
              <td class="text-sm">{{ a.created_at || '-' }}</td>
              <td>
                <a href="javascript:void(0)" class="btn btn-sm" @click="openEdit(a.id)">编辑</a>
                <button class="btn btn-sm btn-danger" @click="deleteAsset(a.id, a.name)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">📦</div>
          <div>暂无资产数据</div>
        </div>
      </div>
    </div>

    <!-- 新增/编辑资产弹窗 -->
    <div v-if="showForm" class="modal-overlay" @click.self="closeForm">
      <div class="modal-box">
        <h3>{{ formMode === 'create' ? '新增资产' : '编辑资产 #' + form.id }}</h3>
        <div class="form-grid">
          <div class="form-row"><label>资产名称 *</label><input v-model="form.name" class="input" placeholder="如 web-server-01"></div>
          <div class="form-row"><label>CI 类型</label>
            <select v-model="form.ci_type" class="input">
              <option v-for="ct in ciTypes" :key="ct" :value="ct">{{ ct }}</option>
            </select>
          </div>
          <div class="form-row"><label>IP 地址</label><input v-model="form.ip" class="input" placeholder="10.0.0.1"></div>
          <div class="form-row"><label>状态</label>
            <select v-model="form.status" class="input">
              <option value="online">online</option>
              <option value="offline">offline</option>
            </select>
          </div>
          <div class="form-row"><label>K8s 集群</label><input v-model="form.k8s_cluster" class="input" placeholder="留空表示非 K8s 资产"></div>
          <div class="form-row"><label>标签</label><input v-model="form.tags" class="input" placeholder="逗号分隔，如 prod,web"></div>
          <div class="form-row"><label>连接方式</label>
            <select v-model="form.connection_type" class="input">
              <option value="ssh">SSH</option>
              <option value="agent">Agent</option>
              <option value="k8s">K8s API</option>
            </select>
          </div>
          <div class="form-row"><label>SSH 用户</label><input v-model="form.ssh_user" class="input" placeholder="root"></div>
          <div class="form-row"><label>SSH 端口</label><input v-model.number="form.ssh_port" class="input" type="number" placeholder="22"></div>
          <div class="form-row"><label>SSH 密码</label><input v-model="form.ssh_password" class="input" type="password" placeholder="留空则不设置"></div>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="closeForm">取消</button>
          <button class="btn btn-primary" @click="saveAsset">{{ formMode === 'create' ? '创建' : '保存' }}</button>
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
const assets = ref([])
const ciTypes = ref([])
const search = ref('')
const ciType = ref('')
let searchTimer = null

// 新增/编辑表单
const showForm = ref(false)
const formMode = ref('create')
const form = ref({ id: null, name: '', ci_type: 'server', ip: '', status: 'offline', k8s_cluster: '', tags: '', connection_type: 'ssh', ssh_user: 'root', ssh_port: 22, ssh_password: '' })

function openCreate() {
  formMode.value = 'create'
  form.value = { id: null, name: '', ci_type: 'server', ip: '', status: 'offline', k8s_cluster: '', tags: '', connection_type: 'ssh', ssh_user: 'root', ssh_port: 22, ssh_password: '' }
  showForm.value = true
}

async function openEdit(id) {
  try {
    const detail = await request.get(`/assets/api/${id}/detail`)
    formMode.value = 'edit'
    form.value = {
      id: detail.id, name: detail.name, ci_type: detail.ci_type || 'server',
      ip: detail.ip || '', status: detail.status || 'offline',
      k8s_cluster: detail.k8s_cluster || '', tags: detail.tags || '',
      connection_type: detail.connection_type || 'ssh',
      ssh_user: detail.ssh_user || 'root', ssh_port: detail.ssh_port || 22,
      ssh_password: detail.ssh_password || '',
    }
    showForm.value = true
  } catch (e) {
    ElMessage.error('加载资产详情失败: ' + (e.message || e))
  }
}

function closeForm() {
  showForm.value = false
}

async function saveAsset() {
  if (!form.value.name.trim()) {
    ElMessage.warning('资产名称不能为空')
    return
  }
  try {
    if (formMode.value === 'create') {
      await request.post('/assets/api/create', form.value)
      ElMessage.success('资产创建成功')
    } else {
      await request.post(`/assets/api/${form.value.id}/update`, form.value)
      ElMessage.success('资产更新成功')
    }
    showForm.value = false
    loadAssets()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.message || e))
  }
}

async function loadAssets() {
  loading.value = true
  try {
    const data = await request.get('/assets/api/list', { params: { search: search.value, ci_type: ciType.value } })
    assets.value = data || []
  } catch (e) {
    ElMessage.error('加载资产失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

async function loadCiTypes() {
  try {
    ciTypes.value = await request.get('/assets/api/ci-types')
  } catch (e) { /* 静默 */ }
}

function onSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(loadAssets, 300)
}

async function deleteAsset(id, name) {
  try {
    await ElMessageBox.confirm(`确认删除资产「${name}」？`, '删除确认', { type: 'warning' })
    await request.post(`/assets/api/${id}/delete`)
    ElMessage.success('已删除')
    loadAssets()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

onMounted(() => {
  loadAssets()
  loadCiTypes()
})
</script>

<style scoped>
.assets-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.search-input { padding: 6px 12px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; width: 240px; }
.toolbar select { padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; text-decoration: none; display: inline-block; transition: all 0.2s; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-danger:hover { background: rgba(239,68,68,0.2); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; white-space: nowrap; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); white-space: nowrap; }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.ci-type { background: rgba(59,130,246,0.1); color: #3b82f6; }
.badge.online { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.offline { background: rgba(100,116,139,0.1); color: #64748b; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 480px; max-width: 90vw; max-height: 90vh; overflow-y: auto; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.form-row { margin-bottom: 0; }
.form-row label { display: block; font-size: 0.76rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 5px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; }
</style>
