<template>
  <div class="users-page">
    <div class="page-header">
      <h1>用户与权限</h1>
      <p>管理员账户与角色管理 · 共 {{ users.length }} 个用户</p>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="showDialog = true">+ 新增用户</button>
      <button class="btn" @click="loadUsers">刷新</button>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="users.length" class="table">
          <thead>
            <tr><th>ID</th><th>用户名</th><th>角色</th><th>创建时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.id">
              <td>{{ u.id }}</td>
              <td>{{ u.username }}</td>
              <td><span class="badge" :class="u.role">{{ roleLabel(u.role) }}</span></td>
              <td class="text-sm">{{ u.created_at || '-' }}</td>
              <td>
                <button v-if="u.id !== currentUserId" class="btn btn-sm btn-danger" @click="deleteUser(u.id, u.username)">删除</button>
                <span v-else class="text-sm">当前用户</span>
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
          <select v-model="form.role" class="input">
            <option value="admin">管理员</option>
            <option value="operator">操作员</option>
            <option value="viewer">观察者</option>
          </select>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showDialog = false">取消</button>
          <button class="btn btn-primary" @click="createUser">创建</button>
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
const currentUserId = ref(0)
const showDialog = ref(false)
const form = ref({ username: '', password: '', role: 'operator' })

function roleLabel(r) {
  return { admin: '管理员', operator: '操作员', viewer: '观察者' }[r] || r
}

async function loadUsers() {
  loading.value = true
  try {
    const data = await request.get('/users/api/list')
    users.value = data.users || []
    currentUserId.value = data.current_user_id || 0
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
      form.value = { username: '', password: '', role: 'operator' }
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
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.admin { background: rgba(99,102,241,0.1); color: #6366f1; }
.badge.operator { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.viewer { background: rgba(100,116,139,0.1); color: #64748b; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 360px; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; color: var(--text, #1e293b); }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
