<template>
  <div class="tenant-page">
    <div class="page-header">
      <div class="title-row">
        <div>
          <h1>🏢 租户管理</h1>
          <p>多租户隔离模式 · 资源配额管理 · 数据完全隔离</p>
        </div>
        <div class="header-actions">
          <div class="mode-indicator" :class="tenantMode ? 'active' : 'inactive'">
            <span class="mode-dot"></span>
            {{ tenantMode ? '租户模式已开启' : '租户模式已关闭' }}
          </div>
        </div>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-icon" style="background:linear-gradient(135deg,#667eea,#764ba2)">🏢</div>
        <div class="stat-info"><div class="stat-value">{{ tenants.length }}</div><div class="stat-label">租户数量</div></div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background:linear-gradient(135deg,#f093fb,#f5576c)">👥</div>
        <div class="stat-info"><div class="stat-value">{{ totalUsers }}</div><div class="stat-label">总用户配额</div></div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background:linear-gradient(135deg,#4facfe,#00f2fe)">🖥️</div>
        <div class="stat-info"><div class="stat-value">{{ totalAssets }}</div><div class="stat-label">总资产配额</div></div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background:linear-gradient(135deg,#43e97b,#38f9d7)">⚙️</div>
        <div class="stat-info">
          <div class="stat-value" style="font-size:16px">{{ tenantMode ? '已开启' : '已关闭' }}</div>
          <div class="stat-label">当前模式</div>
        </div>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="toolbar">
      <button class="btn btn-primary" @click="openCreate">+ 新建租户</button>
      <div class="toolbar-right">
        <button class="btn" :class="tenantMode ? 'btn-success' : 'btn-warning'" @click="toggleMode">
          {{ tenantMode ? '关闭租户模式' : '开启租户模式' }}
        </button>
        <button class="btn" @click="loadTenants">刷新</button>
      </div>
    </div>

    <!-- 租户列表 -->
    <div class="panel">
      <div class="panel-body">
        <div v-if="!tenants.length" class="empty-state">
          <div style="font-size:48px;margin-bottom:12px">🏢</div>
          <div>暂无租户</div>
        </div>
        <table v-else class="table">
          <thead>
            <tr>
              <th>ID</th><th>租户名称</th><th>编码</th><th>状态</th>
              <th>用户配额</th><th>资产配额</th><th>创建时间</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in tenants" :key="t.id">
              <td>{{ t.id }}</td>
              <td><strong>{{ t.name }}</strong></td>
              <td><code>{{ t.code }}</code></td>
              <td>
                <span class="badge" :class="t.status === 'active' ? 'resolved' : 'warning'">
                  {{ t.status === 'active' ? '正常' : '禁用' }}
                </span>
              </td>
              <td>{{ t.quota_users }}</td>
              <td>{{ t.quota_assets }}</td>
              <td>{{ t.created_at }}</td>
              <td>
                <button class="btn btn-sm" @click="openEdit(t)">编辑</button>
                <button v-if="t.id !== 1" class="btn btn-sm btn-danger" @click="deleteTenant(t)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 提示 -->
    <div class="notice-box" v-if="!tenantMode">
      <h4>💡 当前为单租户模式</h4>
      <p>所有数据归属「默认租户」。开启租户模式后，新建数据将强制关联租户，所有列表自动按租户隔离。</p>
      <p style="color:#e6a23c;margin-top:8px">提示：开启租户模式前，建议先在测试环境验证。</p>
    </div>

    <!-- 新建/编辑弹窗 -->
    <div v-if="showDialog" class="modal-overlay" @click.self="showDialog = false">
      <div class="modal-box">
        <div class="modal-header">
          <h3>{{ editing ? '编辑租户' : '新建租户' }}</h3>
          <button class="modal-close" @click="showDialog = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>租户名称 *</label>
            <input v-model="form.name" placeholder="如：客户A公司" />
          </div>
          <div class="form-group">
            <label>租户编码 *</label>
            <input v-model="form.code" placeholder="如：tenant_a" :disabled="editing" />
          </div>
          <div class="form-group">
            <label>状态</label>
            <select v-model="form.status">
              <option value="active">正常</option>
              <option value="inactive">禁用</option>
            </select>
          </div>
          <div class="form-group">
            <label>用户配额</label>
            <input v-model.number="form.quota_users" type="number" min="1" />
          </div>
          <div class="form-group">
            <label>资产配额</label>
            <input v-model.number="form.quota_assets" type="number" min="1" />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn" @click="showDialog = false">取消</button>
          <button class="btn btn-primary" @click="saveTenant" :disabled="!form.name || !form.code">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, reactive, computed, onMounted } from 'vue'
import axios from 'axios'

const API = '/tenant/api'

export default {
  name: 'TenantManagementView',
  setup() {
    const tenants = ref([])
    const tenantMode = ref(false)
    const showDialog = ref(false)
    const editing = ref(null)
    const form = reactive({ name: '', code: '', status: 'active', quota_users: 50, quota_assets: 1000 })

    const totalUsers = computed(() => tenants.value.reduce((s, t) => s + (t.quota_users || 0), 0))
    const totalAssets = computed(() => tenants.value.reduce((s, t) => s + (t.quota_assets || 0), 0))

    const loadTenants = async () => {
      try {
        const { data } = await axios.get(`${API}/tenants`)
        tenants.value = data.items || []
      } catch (e) { console.error(e) }
    }

    const checkMode = async () => {
      try {
        const { data } = await axios.get('/api/system/configs')
        tenantMode.value = data['tenant_mode']?.value === 'true'
      } catch (e) { console.error(e) }
    }

    const toggleMode = async () => {
      const newVal = !tenantMode.value
      if (!confirm(`确定要${newVal ? '开启' : '关闭'}租户模式吗？`)) return
      try {
        await axios.put('/api/system/configs', { 'tenant_mode': newVal ? 'true' : 'false' })
        tenantMode.value = newVal
        alert(`${newVal ? '租户模式已开启' : '租户模式已关闭'}`)
      } catch (e) { alert('操作失败') }
    }

    const openCreate = () => {
      editing.value = null
      Object.assign(form, { name: '', code: '', status: 'active', quota_users: 50, quota_assets: 1000 })
      showDialog.value = true
    }

    const openEdit = (t) => {
      editing.value = t
      Object.assign(form, { name: t.name, code: t.code, status: t.status, quota_users: t.quota_users, quota_assets: t.quota_assets })
      showDialog.value = true
    }

    const saveTenant = async () => {
      try {
        if (editing.value) {
          await axios.put(`${API}/tenants/${editing.value.id}`, { ...form })
        } else {
          await axios.post(`${API}/tenants`, { ...form })
        }
        showDialog.value = false
        loadTenants()
      } catch (e) { alert('保存失败: ' + (e.response?.data?.error || e.message)) }
    }

    const deleteTenant = async (t) => {
      if (!confirm(`确定删除租户「${t.name}」（ID=${t.id}）？`)) return
      try {
        await axios.delete(`${API}/tenants/${t.id}`)
        loadTenants()
      } catch (e) { alert('删除失败') }
    }

    onMounted(() => { loadTenants(); checkMode() })

    return { tenants, tenantMode, showDialog, editing, form, totalUsers, totalAssets, loadTenants, toggleMode, openCreate, openEdit, saveTenant, deleteTenant }
  },
}
</script>

<style scoped>
.tenant-page { padding: 20px; }
.page-header { margin-bottom: 20px; }
.page-header h1 { margin: 0 0 4px; font-size: 22px; }
.page-header p { margin: 0; color: var(--text-muted, #999); font-size: 13px; }
.title-row { display: flex; justify-content: space-between; align-items: center; }
.header-actions { display: flex; gap: 10px; align-items: center; }
.mode-indicator { display: flex; align-items: center; gap: 6px; padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 500; }
.mode-indicator.active { background: #e8f8e8; color: #3a8d3a; }
.mode-indicator.inactive { background: #f0f0f0; color: #999; }
.mode-dot { width: 8px; height: 8px; border-radius: 50%; }
.active .mode-dot { background: #67c23a; }
.inactive .mode-dot { background: #999; }
.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }
.stat-card { display: flex; align-items: center; gap: 14px; padding: 18px 20px; background: var(--card-bg, #fff); border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.stat-icon { width: 48px; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 22px; color: #fff; flex-shrink: 0; }
.stat-value { font-size: 24px; font-weight: 700; }
.stat-label { font-size: 12px; color: var(--text-muted, #999); }
.toolbar { display: flex; justify-content: space-between; margin-bottom: 16px; }
.toolbar-right { display: flex; gap: 8px; }
.panel { background: var(--card-bg, #fff); border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); overflow: hidden; }
.panel-body { padding: 20px; }
.empty-state { text-align: center; padding: 48px 20px; color: var(--text-muted, #999); }
.table { width: 100%; border-collapse: collapse; }
.table th, .table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border-color, #f0f0f0); font-size: 13px; }
.table th { background: var(--hover-bg, #fafafa); font-weight: 600; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
.badge.resolved { background: #e8f8e8; color: #3a8d3a; }
.badge.warning { background: #fff3e0; color: #e67e00; }
.btn { padding: 6px 14px; border-radius: 6px; border: 1px solid var(--border-color, #ddd); background: #fff; cursor: pointer; font-size: 13px; }
.btn-primary { background: var(--primary, #409eff); color: #fff; border-color: var(--primary, #409eff); }
.btn-danger { color: #fff; background: #f56c6c; border-color: #f56c6c; }
.btn-sm { padding: 3px 10px; font-size: 12px; }
.btn-success { color: #fff; background: #67c23a; border-color: #67c23a; }
.btn-warning { color: #fff; background: #e6a23c; border-color: #e6a23c; }
.notice-box { margin-top: 20px; padding: 16px 20px; background: #fdf6ec; border: 1px solid #f5dab1; border-radius: 8px; }
.notice-box h4 { margin: 0 0 6px; }
.notice-box p { margin: 0; font-size: 13px; color: #666; line-height: 1.6; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 1000; display: flex; align-items: center; justify-content: center; }
.modal-box { background: var(--card-bg, #fff); border-radius: 12px; width: 480px; max-width: 90vw; max-height: 85vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.15); }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border-color, #e8e8e8); }
.modal-header h3 { margin: 0; }
.modal-close { background: none; border: none; font-size: 24px; cursor: pointer; color: var(--text-muted, #999); }
.modal-body { padding: 20px; }
.modal-footer { padding: 12px 20px; border-top: 1px solid var(--border-color, #e8e8e8); display: flex; justify-content: flex-end; gap: 8px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 13px; font-weight: 500; margin-bottom: 4px; }
.form-group input, .form-group select { width: 100%; padding: 8px 10px; border: 1px solid var(--border-color, #ddd); border-radius: 6px; font-size: 13px; box-sizing: border-box; }
</style>
