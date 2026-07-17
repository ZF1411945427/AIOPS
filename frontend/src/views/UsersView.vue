<template>
  <div class="users-page">
    <div class="page-header">
      <h1>用户与权限</h1>
      <p>管理员账户与角色管理 · 共 {{ users.length }} 个用户</p>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="showDialog = true">+ 新增用户</button>
      <button class="btn" @click="loadUsers">刷新</button>
      <span v-if="tenantMode" class="tenant-mode-badge">多租户模式已开启</span>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="users.length" class="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>用户名</th>
              <th>角色</th>
              <th v-if="tenantMode">租户</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.id">
              <td>{{ u.id }}</td>
              <td>{{ u.username }}</td>
              <td>
                <select v-if="u.id !== currentUserId" v-model="u.role_id" class="role-select" @change="setUserRole(u)">
                  <option :value="null">- 无角色 -</option>
                  <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.name }}</option>
                </select>
                <span v-else class="text-sm">{{ roleName(u.role_id) }}</span>
              </td>
              <td v-if="tenantMode">
                <select v-if="u.id !== currentUserId" v-model="u.tenant_id" class="role-select" @change="setUserTenant(u)">
                  <option v-for="t in tenants" :key="t.id" :value="t.id">{{ t.name }}</option>
                </select>
                <span v-else class="text-sm">{{ tenantName(u.tenant_id) }}</span>
              </td>
              <td class="text-sm">{{ u.created_at || '-' }}</td>
              <td>
                <button class="btn btn-sm btn-warning" @click="openPwdDialog(u)">修改密码</button>
                <button v-if="u.id !== currentUserId" class="btn btn-sm btn-danger" @click="deleteUser(u.id, u.username)">删除</button>
                <span v-else class="text-sm current-tag">当前用户</span>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">👤</div><div>暂无用户</div></div>
      </div>
    </div>

    <div v-if="showDialog" class="modal-overlay" @click.self="showDialog = false">
      <div class="modal-box">
        <h3>新增用户</h3>
        <div class="form-row"><label>用户名</label><input v-model="form.username" class="input"></div>
        <div class="form-row"><label>密码</label><input v-model="form.password" type="password" class="input"></div>
        <div class="form-row"><label>角色</label>
          <select v-model="form.role_id" class="input">
            <option :value="null">- 无角色 -</option>
            <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.name }}</option>
          </select>
        </div>
        <div v-if="tenantMode" class="form-row"><label>租户</label>
          <select v-model="form.tenant_id" class="input">
            <option v-for="t in tenants" :key="t.id" :value="t.id">{{ t.name }}</option>
          </select>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showDialog = false">取消</button>
          <button class="btn btn-primary" @click="createUser">创建</button>
        </div>
      </div>
    </div>

    <div v-if="showPwdDialog" class="modal-overlay" @click.self="showPwdDialog = false">
      <div class="modal-box">
        <h3>修改密码 · {{ pwdTarget.username }}</h3>
        <div v-if="pwdTarget.id === currentUserId" class="form-row"><label>旧密码</label><input v-model="pwdForm.old_password" type="password" class="input" @keyup.enter="submitPassword"></div>
        <div class="form-row"><label>新密码</label><input v-model="pwdForm.new_password" type="password" class="input" placeholder="至少4位" @keyup.enter="submitPassword"></div>
        <div class="form-row"><label>确认新密码</label><input v-model="pwdForm.confirm_password" type="password" class="input" @keyup.enter="submitPassword"></div>
        <div class="modal-actions">
          <button class="btn" @click="showPwdDialog = false">取消</button>
          <button class="btn btn-primary" @click="submitPassword">确认修改</button>
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
const users = ref([])
const roles = ref([])
const tenants = ref([])
const tenantMode = ref(false)
const currentUserId = ref(0)
const showDialog = ref(false)
const form = ref({ username: '', password: '', role_id: null, tenant_id: 1 })
const showPwdDialog = ref(false)
const pwdTarget = ref({ id: 0, username: '' })
const pwdForm = ref({ old_password: '', new_password: '', confirm_password: '' })

function roleName(roleId) {
  const r = roles.value.find(x => x.id === roleId)
  return r ? r.name : '-'
}

function tenantName(tenantId) {
  const t = tenants.value.find(x => x.id === tenantId)
  return t ? t.name : '-'
}

async function setUserRole(u) {
  try {
    await request.post('/users/api/' + u.id + '/set-role', { role_id: u.role_id })
    ElMessage.success('角色已更新')
  } catch (e) {
    ElMessage.error('更新角色失败: ' + e.message)
  }
}

async function setUserTenant(u) {
  try {
    await request.post('/users/api/' + u.id + '/set-tenant', { tenant_id: u.tenant_id })
    ElMessage.success('租户已更新')
  } catch (e) {
    ElMessage.error('更新租户失败: ' + e.message)
  }
}

async function loadUsers() {
  loading.value = true
  try {
    const data = await request.get('/users/api/list')
    users.value = data.users || []
    roles.value = data.roles || []
    tenants.value = data.tenants || []
    currentUserId.value = data.current_user_id || 0
    tenantMode.value = data.tenant_mode || false
  } catch (e) {
    ElMessage.error('加载用户失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

async function createUser() {
  if (!form.value.username || !form.value.password) {
    ElMessage.warning('用户名和密码不能为空')
    return
  }
  try {
    const data = await request.post('/users/api/create', form.value)
    if (data.status === 'ok') {
      ElMessage.success('创建成功')
      showDialog.value = false
      form.value = { username: '', password: '', role_id: null, tenant_id: 1 }
      loadUsers()
    } else {
      ElMessage.error(data.message || '创建失败')
    }
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.message || e))
  }
}

async function deleteUser(id, name) {
  try {
    await ElMessageBox.confirm(`确认删除用户「${name}」？`, '删除确认', { type: 'warning' })
    const data = await request.delete(`/users/api/${id}/delete`)
    if (data.status === 'ok') {
      ElMessage.success('已删除')
      loadUsers()
    } else {
      ElMessage.error(data.message || '删除失败')
    }
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

function openPwdDialog(u) {
  pwdTarget.value = { id: u.id, username: u.username }
  pwdForm.value = { old_password: '', new_password: '', confirm_password: '' }
  showPwdDialog.value = true
}

async function submitPassword() {
  const isSelf = pwdTarget.value.id === currentUserId.value
  if (isSelf && !pwdForm.value.old_password) {
    ElMessage.warning('请输入旧密码')
    return
  }
  if (!pwdForm.value.new_password || pwdForm.value.new_password.length < 4) {
    ElMessage.warning('新密码至少4位')
    return
  }
  if (pwdForm.value.new_password !== pwdForm.value.confirm_password) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  try {
    let data
    if (isSelf) {
      data = await request.post('/users/api/change-password', {
        old_password: pwdForm.value.old_password,
        new_password: pwdForm.value.new_password,
      })
    } else {
      data = await request.post(`/users/api/${pwdTarget.value.id}/reset-password`, {
        new_password: pwdForm.value.new_password,
      })
    }
    if (data.status === 'ok') {
      ElMessage.success('密码修改成功')
      showPwdDialog.value = false
    } else {
      ElMessage.error(data.message || '修改失败')
    }
  } catch (e) {
    ElMessage.error('修改失败: ' + (e.message || e))
  }
}

onMounted(loadUsers)
</script>

<style scoped>
.users-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-warning { background: rgba(245,158,11,0.1); color: #f59e0b; border-color: rgba(245,158,11,0.3); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.btn-sm + .btn-sm { margin-left: 4px; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.current-tag { margin-left: 6px; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 360px; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; color: var(--text, #1e293b); }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.role-select { padding: 3px 6px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 4px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.8rem; max-width: 140px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
