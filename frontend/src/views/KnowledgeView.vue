<template>
  <div class="kb-page">
    <div class="page-header">
      <h1>故障知识库</h1>
      <p>运维经验沉淀与共享 · 共 {{ items.length }} 条知识</p>
    </div>

    <div class="toolbar">
      <input v-model="search" class="input search-input" placeholder="搜索标题/症状/解决方案" @keyup.enter="loadList">
      <input v-model="tagFilter" class="input" placeholder="标签过滤（逗号分隔）" @keyup.enter="loadList">
      <button class="btn" @click="loadList">搜索</button>
      <button class="btn" @click="resetFilter">重置</button>
      <button class="btn" @click="loadList">刷新</button>
      <button class="btn btn-primary" @click="openCreate">+ 新建知识</button>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="items.length" class="table">
          <thead>
            <tr>
              <th>ID</th><th>标题</th><th>级别</th><th>标签</th><th>更新时间</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="it in items" :key="it.id">
              <td>{{ it.id }}</td>
              <td class="title-cell">{{ it.title }}</td>
              <td>
                <span class="badge" :class="sevClass(it.severity)">{{ it.severity || '-' }}</span>
              </td>
              <td>
                <span v-for="t in tagList(it.tags)" :key="t" class="tag-mini">{{ t }}</span>
              </td>
              <td>{{ it.updated_at || it.created_at || '-' }}</td>
              <td class="ops">
                <button class="btn btn-sm" @click="openDetail(it.id)">查看</button>
                <button class="btn btn-sm" @click="openEdit(it.id)">编辑</button>
                <button class="btn btn-sm btn-danger" @click="confirmDelete(it)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">📚</div><div>暂无知识条目</div></div>
      </div>
    </div>

    <div v-if="showDialog" class="modal-overlay" @click.self="closeDialog">
      <div class="modal-box wide">
        <h3>{{ editing ? '编辑知识' : '新建知识' }}</h3>
        <div class="form-row"><label>标题</label><input v-model="form.title" class="input" placeholder="简明扼要的故障标题"></div>
        <div class="form-row"><label>故障症状</label><textarea v-model="form.symptom" class="input textarea" rows="3" placeholder="故障表现/现象描述"></textarea></div>
        <div class="form-row"><label>根本原因</label><textarea v-model="form.root_cause" class="input textarea" rows="3" placeholder="故障根因分析"></textarea></div>
        <div class="form-row"><label>解决方案</label><textarea v-model="form.solution" class="input textarea" rows="4" placeholder="处置步骤/修复方案"></textarea></div>
        <div class="form-row"><label>标签（逗号分隔）</label><input v-model="form.tags" class="input" placeholder="如: 数据库,慢查询,生产"></div>
        <div class="form-row"><label>严重级别</label>
          <select v-model="form.severity" class="input">
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
          </select>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="closeDialog">取消</button>
          <button class="btn btn-primary" @click="saveItem">{{ editing ? '保存' : '创建' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showDetail" class="modal-overlay" @click.self="showDetail = false">
      <div class="modal-box wide">
        <h3>知识详情 #{{ detail.id }}</h3>
        <div class="detail-row"><span class="detail-label">标题</span><span class="detail-val">{{ detail.title }}</span></div>
        <div class="detail-row"><span class="detail-label">级别</span><span class="badge" :class="sevClass(detail.severity)">{{ detail.severity || '-' }}</span></div>
        <div class="detail-row"><span class="detail-label">标签</span>
          <span v-for="t in tagList(detail.tags)" :key="t" class="tag-mini">{{ t }}</span>
        </div>
        <div class="detail-block"><div class="detail-label">故障症状</div><div class="detail-text">{{ detail.symptom || '-' }}</div></div>
        <div class="detail-block"><div class="detail-label">根本原因</div><div class="detail-text">{{ detail.root_cause || '-' }}</div></div>
        <div class="detail-block"><div class="detail-label">解决方案</div><div class="detail-text">{{ detail.solution || '-' }}</div></div>
        <div class="detail-meta">创建: {{ detail.created_at || '-' }} · 更新: {{ detail.updated_at || '-' }}</div>
        <div class="modal-actions">
          <button class="btn" @click="showDetail = false">关闭</button>
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
const items = ref([])
const search = ref('')
const tagFilter = ref('')

const showDialog = ref(false)
const editing = ref(false)
const form = ref({ title: '', symptom: '', root_cause: '', solution: '', tags: '', severity: 'info' })

const showDetail = ref(false)
const detail = ref({})

function tagList(tags) {
  if (!tags) return []
  if (Array.isArray(tags)) return tags
  return String(tags).split(',').map(t => t.trim()).filter(Boolean)
}

function sevClass(s) {
  const m = { critical: 'sev-critical', high: 'sev-high', warning: 'sev-warning', info: 'sev-info' }
  return m[s] || 'sev-info'
}

async function loadList() {
  loading.value = true
  try {
    const params = {}
    if (search.value) params.search = search.value
    if (tagFilter.value) params.tags = tagFilter.value
    const data = await request.get('/knowledge/api/list', { params })
    items.value = data.items || []
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

function resetFilter() {
  search.value = ''
  tagFilter.value = ''
  loadList()
}

function openCreate() {
  editing.value = false
  form.value = { title: '', symptom: '', root_cause: '', solution: '', tags: '', severity: 'info' }
  showDialog.value = true
}

async function openEdit(id) {
  try {
    const data = await request.get(`/knowledge/api/${id}`)
    editing.value = true
    form.value = {
      title: data.title || '',
      symptom: data.symptom || '',
      root_cause: data.root_cause || '',
      solution: data.solution || '',
      tags: Array.isArray(data.tags) ? data.tags.join(',') : (data.tags || ''),
      severity: data.severity || 'info'
    }
    showDialog.value = true
  } catch (e) {
    ElMessage.error('获取详情失败: ' + (e.message || e))
  }
}

async function openDetail(id) {
  try {
    detail.value = await request.get(`/knowledge/api/${id}`)
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
    const payload = { ...form.value, tags: form.value.tags }
    if (editing.value) {
      await request.post(`/knowledge/api/${form.value.id || detail.value.id}/update`, payload)
      ElMessage.success('已保存')
    } else {
      await request.post('/knowledge/api/create', payload)
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
    await ElMessageBox.confirm(`确定删除知识「${it.title}」？`, '删除确认', { type: 'warning' })
    await request.post(`/knowledge/api/${it.id}/delete`)
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
.kb-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
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
.tag-mini { display: inline-block; padding: 1px 6px; border-radius: 4px; background: rgba(99,102,241,0.08); color: var(--accent, #6366f1); font-size: 0.7rem; margin-right: 4px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.sev-critical { background: rgba(239,68,68,0.12); color: #ef4444; }
.sev-high { background: rgba(249,115,22,0.12); color: #f97316; }
.sev-warning { background: rgba(245,158,11,0.12); color: #d97706; }
.sev-info { background: rgba(59,130,246,0.12); color: #3b82f6; }
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
.detail-meta { margin: 10px 0; font-size: 0.72rem; color: var(--text-tertiary, #94a3b8); }
</style>
