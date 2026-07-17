<template>
  <div class="roles-page">
    <div class="page-head">
      <div><h1>角色权限</h1><p class="desc">{{ roles.length }} 个角色 · 勾选决定每个角色能看到哪些菜单</p></div>
      <button class="btn-primary" @click="openCreate">+ 新建角色</button>
    </div>

    <div class="body-wrap">
      <div class="role-list">
        <div v-if="loadingRoles" class="loading">加载中...</div>
        <div v-for="r in roles" :key="r.id" class="role-item" :class="{ active: activeRole?.id === r.id }" @click="selectRole(r)">
          <div class="role-top">
            <span class="role-name">{{ r.name }}</span>
            <span v-if="r.is_system" class="badge-system">内置</span>
          </div>
          <div class="role-desc">{{ r.description }}</div>
        </div>
        <div v-if="!loadingRoles && roles.length === 0" class="empty">暂无角色</div>
      </div>

      <div v-if="activeRole" class="perm-panel">
        <div class="perm-head">
          <div>
            <h2>{{ activeRole.name }}</h2>
            <div class="perm-meta">关联 {{ roleUsers.length }} 个用户</div>
          </div>
          <div class="perm-actions">
            <button class="btn-plain" @click="openEdit(activeRole)">✎ 编辑</button>
            <button v-if="!activeRole.is_system" class="btn-danger-sm" @click="deleteRole(activeRole)">✕ 删除</button>
          </div>
        </div>

        <div class="perm-section">
          <div class="perm-title">
            菜单可见权限
            <span class="count">{{ selectedKeys.length }} / {{ allKeys.length }}</span>
          </div>
          <div class="tree-wrap">
            <div v-for="g in menuData" :key="g.key" class="tree-group">
              <label class="node node-group">
                <input type="checkbox" :checked="isGroupChecked(g)" @change="toggleGroup(g, $event.target.checked)" />
                <span class="node-label">{{ g.label }}</span>
                <span class="node-count">{{ countChecked(g) }}/{{ countGroup(g) }}</span>
              </label>
              <div class="children">
                <template v-for="item in g.items" :key="item.key">
                  <label v-if="!item.items" class="node node-leaf">
                    <input type="checkbox" :checked="selectedKeys.includes(item.key)" @change="toggleKey(item.key)" />
                    <span>{{ item.label }}</span>
                  </label>
                  <div v-else class="sub-tree">
                    <label class="node node-sub">
                      <input type="checkbox" :checked="isSubGroupChecked(item)" @change="toggleSubGroup(item, $event.target.checked)" />
                      <span>{{ item.label }}</span>
                    </label>
                    <div class="sub-children">
                      <label v-for="sub in item.items" :key="sub.key" class="node node-leaf">
                        <input type="checkbox" :checked="selectedKeys.includes(sub.key)" @change="toggleKey(sub.key)" />
                        <span>{{ sub.label }}</span>
                      </label>
                    </div>
                  </div>
                </template>
              </div>
            </div>
          </div>
          <div class="tree-actions">
            <button class="btn-primary" :disabled="saving" @click="saveMenus">{{ saving ? '保存中...' : '保存权限' }}</button>
            <button class="btn-plain" @click="selectAll">全选</button>
            <button class="btn-plain" @click="clearAll">清空</button>
          </div>
        </div>
      </div>

      <div v-else class="perm-panel empty-panel">
        <div class="empty-tip">← 选择一个角色开始配置</div>
      </div>
    </div>

    <div v-if="showForm" class="mask" @click.self="showForm = false">
      <div class="dialog">
        <h3>{{ editingRole ? '编辑角色' : '新建角色' }}</h3>
        <div class="field"><label>名称</label><input v-model="form.name" class="input" placeholder="如：安全审计员" /></div>
        <div class="field"><label>描述</label><input v-model="form.description" class="input" placeholder="简要描述角色职责" /></div>
        <div class="dialog-actions">
          <button class="btn-plain" @click="showForm = false">取消</button>
          <button class="btn-primary" @click="submitRole">{{ editingRole ? '更新' : '创建' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const roles = ref([])
const activeRole = ref(null)
const menuData = ref([])
const selectedKeys = ref([])
const allKeys = ref([])
const roleUsers = ref([])
const loadingRoles = ref(false)
const saving = ref(false)
const showForm = ref(false)
const editingRole = ref(null)
const form = ref({ name: '', description: '' })

async function loadRoles() {
  loadingRoles.value = true
  try {
    const data = await request.get('/api/roles')
    roles.value = data.roles || []
    if (activeRole.value) {
      const still = roles.value.find(r => r.id === activeRole.value.id)
      if (!still) activeRole.value = null
    }
    if (!activeRole.value && roles.value.length) selectRole(roles.value[0])
  } catch (e) {
    ElMessage.error('加载角色失败: ' + e.message)
  } finally {
    loadingRoles.value = false
  }
}

function selectRole(r) {
  activeRole.value = r
  loadRoleMenus(r)
  loadRoleUsers(r)
}

async function loadRoleMenus(r) {
  try {
    const [menuResult, menusResult] = await Promise.all([
      request.get('/api/menu'),
      request.get('/api/roles/' + r.id + '/menus'),
    ])
    const raw = Array.isArray(menuResult) ? menuResult : (menuResult.menu || [])
    menuData.value = raw
    selectedKeys.value = menusResult.menu_keys || []
    allKeys.value = collectAllKeys(raw)
  } catch (e) {
    ElMessage.error('加载菜单权限失败: ' + e.message)
  }
}

async function loadRoleUsers(r) {
  try {
    const data = await request.get('/api/roles/' + r.id + '/users')
    roleUsers.value = data.users || []
  } catch (e) {
    roleUsers.value = []
  }
}

function collectAllKeys(groups) {
  const keys = []
  for (const g of groups) {
    keys.push(g.key)
    for (const item of (g.items || [])) {
      keys.push(item.key)
      for (const sub of (item.items || [])) keys.push(sub.key)
    }
  }
  return keys
}

function countGroup(g) {
  let n = 0
  for (const item of (g.items || [])) {
    n += item.items ? item.items.length : 1
  }
  return n
}

function countChecked(g) {
  let n = 0
  for (const item of (g.items || [])) {
    if (item.items) {
      for (const sub of item.items) { if (selectedKeys.value.includes(sub.key)) n++ }
    } else if (selectedKeys.value.includes(item.key)) n++
  }
  return n
}

function isGroupChecked(g) {
  const items = []
  for (const item of (g.items || [])) {
    if (item.items) { for (const sub of item.items) items.push(sub.key) }
    else items.push(item.key)
  }
  return items.length > 0 && items.every(k => selectedKeys.value.includes(k))
}

function isSubGroupChecked(item) {
  return item.items && item.items.length > 0 && item.items.every(s => selectedKeys.value.includes(s.key))
}

function toggleGroup(g, checked) {
  for (const item of (g.items || [])) {
    if (item.items) { for (const sub of item.items) toggleKey(sub.key, checked) }
    else toggleKey(item.key, checked)
  }
}

function toggleSubGroup(item, checked) {
  if (!item.items) return
  for (const sub of item.items) toggleKey(sub.key, checked)
}

function toggleKey(key, force) {
  if (force === true) { if (!selectedKeys.value.includes(key)) selectedKeys.value.push(key) }
  else if (force === false) { selectedKeys.value = selectedKeys.value.filter(k => k !== key) }
  else {
    const idx = selectedKeys.value.indexOf(key)
    idx >= 0 ? selectedKeys.value.splice(idx, 1) : selectedKeys.value.push(key)
  }
}

function selectAll() { selectedKeys.value = [...allKeys.value] }
function clearAll() { selectedKeys.value = [] }

async function saveMenus() {
  if (!activeRole.value) return
  saving.value = true
  try {
    await request.put('/api/roles/' + activeRole.value.id + '/menus', { menu_keys: selectedKeys.value })
    ElMessage.success('保存成功')
  } catch (e) {
    ElMessage.error('保存失败: ' + e.message)
  } finally {
    saving.value = false
  }
}

function openCreate() { editingRole.value = null; form.value = { name: '', description: '' }; showForm.value = true }
function openEdit(r) { editingRole.value = r; form.value = { name: r.name, description: r.description }; showForm.value = true }

async function submitRole() {
  if (!form.value.name.trim()) { ElMessage.warning('请输入名称'); return }
  try {
    if (editingRole.value) await request.put('/api/roles/' + editingRole.value.id, form.value)
    else await request.post('/api/roles', form.value)
    ElMessage.success(editingRole.value ? '已更新' : '已创建')
    showForm.value = false
    await loadRoles()
  } catch (e) { ElMessage.error('操作失败: ' + e.message) }
}

async function deleteRole(r) {
  try {
    await ElMessageBox.confirm('确定删除角色「' + r.name + '」？', '确认', { type: 'warning' })
    await request.delete('/api/roles/' + r.id)
    ElMessage.success('已删除')
    if (activeRole.value?.id === r.id) activeRole.value = null
    await loadRoles()
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e)) }
}

onMounted(loadRoles)
</script>

<style scoped>
.roles-page { height: calc(100vh - 100px); display: flex; flex-direction: column; }
.page-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; flex-shrink: 0; }
.page-head h1 { margin: 0; font-size: 20px; font-weight: 700; }
.desc { margin: 4px 0 0; font-size: 13px; color: var(--text-muted); }
.body-wrap { display: flex; gap: 16px; flex: 1; min-height: 0; }

.role-list { width: 220px; flex-shrink: 0; background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 8px; padding: 8px; overflow-y: auto; }
.role-item { padding: 10px 12px; border-radius: 6px; cursor: pointer; margin-bottom: 2px; border: 1px solid transparent; transition: all .12s; }
.role-item:hover { background: var(--hover-bg); }
.role-item.active { background: color-mix(in srgb, var(--primary) 10%, transparent); border-color: var(--primary); }
.role-top { display: flex; align-items: center; gap: 6px; }
.role-name { font-weight: 600; font-size: 14px; }
.role-desc { font-size: 12px; color: var(--text-muted); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.badge-system { font-size: 10px; background: var(--warning); color: #fff; padding: 0 5px; border-radius: 3px; line-height: 16px; }

.perm-panel { flex: 1; background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 8px; padding: 16px; overflow-y: auto; min-height: 0; }
.perm-panel.empty-panel { display: flex; align-items: center; justify-content: center; }
.empty-tip { color: var(--text-muted); font-size: 14px; }
.perm-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--border-color); }
.perm-head h2 { margin: 0; font-size: 17px; }
.perm-meta { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
.perm-actions { display: flex; gap: 6px; }
.perm-section { margin-bottom: 0; }
.perm-title { font-weight: 600; font-size: 14px; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
.count { font-weight: 400; font-size: 12px; color: var(--text-muted); }
.tree-wrap { max-height: 380px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: 6px; }
.tree-group { border-bottom: 1px solid var(--border-color); }
.tree-group:last-child { border-bottom: none; }
.node { display: flex; align-items: center; gap: 6px; padding: 7px 10px; cursor: pointer; font-size: 13px; user-select: none; }
.node:hover { background: var(--hover-bg); }
.node-group { background: color-mix(in srgb, var(--primary) 6%, transparent); font-weight: 600; }
.node-label { flex: 1; }
.node-count { font-weight: 400; font-size: 11px; color: var(--text-muted); }
.children { padding-left: 16px; }
.node-leaf { padding-left: 10px; }
.sub-tree { border-left: 2px solid var(--border-color); margin-left: 8px; }
.sub-tree .node-sub { font-weight: 600; background: color-mix(in srgb, var(--text-muted) 5%, transparent); }
.sub-children { padding-left: 12px; }
.tree-actions { display: flex; gap: 8px; align-items: center; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border-color); }

.btn-primary { padding: 7px 18px; border: none; border-radius: 6px; background: var(--primary); color: #fff; cursor: pointer; font-size: 13px; font-weight: 500; }
.btn-primary:hover { opacity: .88; }
.btn-primary:disabled { opacity: .5; cursor: not-allowed; }
.btn-plain { padding: 6px 14px; border: 1px solid var(--border-color); border-radius: 6px; background: transparent; color: var(--text); cursor: pointer; font-size: 13px; }
.btn-plain:hover { background: var(--hover-bg); }
.btn-danger-sm { padding: 6px 14px; border: 1px solid rgba(239,68,68,0.3); border-radius: 6px; background: transparent; color: #ef4444; cursor: pointer; font-size: 13px; }
.btn-danger-sm:hover { background: rgba(239,68,68,0.08); }

.mask { position: fixed; inset: 0; background: rgba(0,0,0,.35); display: flex; align-items: center; justify-content: center; z-index: 100; }
.dialog { background: var(--card-bg); border-radius: 10px; padding: 20px 24px; min-width: 360px; box-shadow: 0 8px 30px rgba(0,0,0,.15); }
.dialog h3 { margin: 0 0 16px; font-size: 16px; }
.field { margin-bottom: 12px; }
.field label { display: block; font-size: 12px; color: var(--text-muted); margin-bottom: 4px; }
.input { width: 100%; padding: 7px 10px; border: 1px solid var(--border-color); border-radius: 6px; background: var(--input-bg); color: var(--text); font-size: 13px; box-sizing: border-box; }
.dialog-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.loading, .empty { text-align: center; padding: 24px; color: var(--text-muted); font-size: 13px; }
input[type="checkbox"] { margin: 0; cursor: pointer; }
</style>
