<template>
  <div class="rb-page">
    <div class="page-header">
      <h1>Runbook 手册</h1>
      <p>标准运维操作流程 · 共 {{ items.length }} 个</p>
    </div>

    <div class="toolbar">
      <select v-model="categoryFilter" class="input select-input" @change="loadList">
        <option value="">全部分类</option>
        <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
      </select>
      <input v-model="search" class="input search-input" placeholder="搜索标题/内容" @keyup.enter="loadList">
      <button class="btn" @click="loadList">刷新</button>
      <button class="btn btn-primary" @click="openCreate">+ 新建 Runbook</button>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="items.length" class="table">
          <thead>
            <tr><th>ID</th><th>标题</th><th>分类</th><th>更新时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="it in filteredItems" :key="it.id">
              <td>{{ it.id }}</td>
              <td class="title-cell">{{ it.title }}</td>
              <td><span class="badge cat-badge">{{ it.category || '-' }}</span></td>
              <td>{{ it.updated_at || it.created_at || '-' }}</td>
              <td class="ops">
                <button class="btn btn-sm" @click="openDetail(it.id)">查看</button>
                <button class="btn btn-sm" @click="openEdit(it.id)">编辑</button>
                <button class="btn btn-sm btn-danger" @click="confirmDelete(it)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">📖</div><div>暂无 Runbook</div></div>
      </div>
    </div>

    <div v-if="showDialog" class="modal-overlay" @click.self="closeDialog">
      <div class="modal-box wide">
        <h3>{{ editing ? '编辑 Runbook' : '新建 Runbook' }}</h3>
        <div class="form-row"><label>标题</label><input v-model="form.title" class="input" placeholder="Runbook 标题"></div>
        <div class="form-row"><label>分类</label>
          <input v-model="form.category" class="input" placeholder="如: 数据库 / 中间件 / 网络" list="rb-cats">
          <datalist id="rb-cats">
            <option v-for="c in categories" :key="c" :value="c"></option>
          </datalist>
        </div>
        <div class="form-row"><label>内容</label><textarea v-model="form.content" class="input textarea" rows="6" placeholder="Runbook 详细操作说明"></textarea></div>
        <div class="form-row"><label>操作步骤（每行一步）</label><textarea v-model="form.steps" class="input textarea" rows="5" placeholder="步骤1...&#10;步骤2..."></textarea></div>
        <div class="modal-actions">
          <button class="btn" @click="closeDialog">取消</button>
          <button class="btn btn-primary" @click="saveItem">{{ editing ? '保存' : '创建' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showDetail" class="modal-overlay" @click.self="showDetail = false">
      <div class="modal-box wide">
        <h3>Runbook 详情 #{{ detail.id }}</h3>
        <div class="detail-row"><span class="detail-label">标题</span><span class="detail-val">{{ detail.title }}</span></div>
        <div class="detail-row"><span class="detail-label">分类</span><span class="badge cat-badge">{{ detail.category || '-' }}</span></div>
        <div class="detail-row"><span class="detail-label">更新时间</span><span class="detail-val">{{ detail.updated_at || detail.created_at || '-' }}</span></div>
        <div class="detail-block"><div class="detail-label">内容</div><div class="detail-text">{{ detail.content || '-' }}</div></div>
        <div class="detail-block"><div class="detail-label">操作步骤</div>
          <ol v-if="stepList(detail.steps).length" class="steps-list">
            <li v-for="(s, i) in stepList(detail.steps)" :key="i">{{ s }}</li>
          </ol>
          <div v-else class="empty-state">无步骤</div>
        </div>
        <div class="modal-actions"><button class="btn" @click="showDetail = false">关闭</button></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const items = ref([])
const categories = ref([])
const search = ref('')
const categoryFilter = ref('')

const showDialog = ref(false)
const editing = ref(false)
const form = ref({ title: '', category: '', content: '', steps: '' })
const editingId = ref(null)

const showDetail = ref(false)
const detail = ref({})

const filteredItems = computed(() => {
  if (!search.value.trim()) return items.value
  const kw = search.value.toLowerCase()
  return items.value.filter(it =>
    (it.title || '').toLowerCase().includes(kw) ||
    (it.content || '').toLowerCase().includes(kw)
  )
})

function stepList(steps) {
  if (!steps) return []
  if (Array.isArray(steps)) return steps
  return String(steps).split(/\r?\n/).map(s => s.trim()).filter(Boolean)
}

async function loadList() {
  loading.value = true
  try {
    const params = {}
    if (categoryFilter.value) params.category = categoryFilter.value
    const data = await request.get('/runbooks/api/list', { params })
    items.value = data.items || []
    categories.value = data.categories || []
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = false
  editingId.value = null
  form.value = { title: '', category: '', content: '', steps: '' }
  showDialog.value = true
}

async function openEdit(id) {
  try {
    const data = await request.get(`/runbooks/api/${id}`)
    editing.value = true
    editingId.value = id
    form.value = {
      title: data.title || '',
      category: data.category || '',
      content: data.content || '',
      steps: Array.isArray(data.steps) ? data.steps.join('\n') : (data.steps || '')
    }
    showDialog.value = true
  } catch (e) {
    ElMessage.error('获取详情失败: ' + (e.message || e))
  }
}

async function openDetail(id) {
  try {
    detail.value = await request.get(`/runbooks/api/${id}`)
    showDetail.value = true
  } catch (e) {
    ElMessage.error('获取详情失败: ' + (e.message || e))
  }
}

async function saveItem() {
  if (!form.value.title) {
    ElMessage.warning('请输入标题')
    return
  }
  try {
    const payload = { ...form.value, steps: form.value.steps }
    if (editing.value && editingId.value) {
      await request.post(`/runbooks/api/${editingId.value}/update`, payload)
      ElMessage.success('已保存')
    } else {
      await request.post('/runbooks/api/create', payload)
      ElMessage.success('已创建')
    }
    showDialog.value = false
    loadList()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.message || e))
  }
}

async function confirmDelete(it) {
  try {
    await ElMessageBox.confirm(`确定删除 Runbook「${it.title}」？`, '删除确认', { type: 'warning' })
    await request.post(`/runbooks/api/${it.id}/delete`)
    ElMessage.success('已删除')
    loadList()
  } catch (e) {
    if (e !== 'cancel' && e?.message !== 'cancel') {
      ElMessage.error('删除失败: ' + (e.message || e))
    }
  }
}

function closeDialog() {
  showDialog.value = false
}

onMounted(loadList)
</script>

<style scoped>
.rb-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.select-input { min-width: 160px; }
.search-input { min-width: 240px; }
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
.title-cell { font-weight: 500; }
.ops { display: flex; gap: 6px; }
.badge.cat-badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; background: rgba(20,184,166,0.12); color: #14b8a6; }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 380px; max-width: 90vw; max-height: 90vh; overflow-y: auto; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-box.wide { min-width: 560px; }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; color: var(--text, #1e293b); }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.textarea { resize: vertical; font-family: inherit; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.detail-row { display: flex; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-size: 0.85rem; }
.detail-label { min-width: 80px; color: var(--text-secondary, #64748b); font-size: 0.78rem; }
.detail-val { color: var(--text, #1e293b); }
.detail-block { margin: 10px 0; }
.detail-text { margin-top: 4px; padding: 10px; background: var(--bg-hover, rgba(0,0,0,0.03)); border-radius: 6px; font-size: 0.82rem; white-space: pre-wrap; line-height: 1.5; }
.steps-list { margin-top: 6px; padding-left: 20px; }
.steps-list li { padding: 4px 0; font-size: 0.82rem; color: var(--text, #1e293b); line-height: 1.5; }
</style>
