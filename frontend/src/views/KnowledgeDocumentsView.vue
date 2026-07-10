<template>
  <div class="kbdoc-page">
    <div class="page-header">
      <h1>RAG 知识库文档</h1>
      <p>语义检索增强 · 文档向量化索引</p>
    </div>

    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-icon blue">📄</div>
        <div class="stat-body"><div class="stat-value">{{ stats.total_docs || 0 }}</div><div class="stat-label">文档总数</div></div>
      </div>
      <div class="stat-card success">
        <div class="stat-icon green">✅</div>
        <div class="stat-body"><div class="stat-value">{{ stats.indexed_count || 0 }}</div><div class="stat-label">已索引</div></div>
      </div>
      <div class="stat-card">
        <div class="stat-icon indigo">🧩</div>
        <div class="stat-body"><div class="stat-value">{{ stats.total_chunks || 0 }}</div><div class="stat-label">切片总数</div></div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head">语义检索（RAG）</div>
      <div class="panel-body">
        <div class="rag-box">
          <input v-model="ragQuery" class="input" placeholder="输入检索问题，语义匹配知识切片..." @keyup.enter="runSearch">
          <button class="btn btn-primary" @click="runSearch" :disabled="ragSearching">{{ ragSearching ? '检索中...' : '检索' }}</button>
        </div>
        <div v-if="ragItems.length" class="rag-results">
          <div v-for="(r, i) in ragItems" :key="i" class="rag-item">
            <div class="rag-head">
              <span class="rag-score">相似度 {{ ((r.similarity || r.score || 0) * 100).toFixed(1) }}%</span>
              <span v-if="r.doc_title" class="rag-doc">{{ r.doc_title }}</span>
              <span v-if="r.source_type" class="rag-meta badge src">{{ r.source_type }}</span>
              <span v-if="r.tags" class="rag-meta badge tag">{{ r.tags }}</span>
            </div>
            <div class="rag-content">{{ r.content || r.chunk_text || r.text || '' }}</div>
          </div>
          <div class="rag-count">共 {{ ragItems.length }} 条匹配</div>
        </div>
        <div v-else-if="ragSearched" class="empty-state">无匹配结果</div>
      </div>
    </div>

    <div class="panel" style="margin-top:14px;">
      <div class="panel-head">文档管理</div>
      <div class="panel-body">
        <div class="upload-zone" @click="triggerUpload" @dragover.prevent="dragOver = true" @dragleave.prevent="dragOver = false" @drop.prevent="handleDrop" :class="{ active: dragOver }">
          <div style="font-size:28px;margin-bottom:6px;">📤</div>
          <div>点击或拖拽文件上传（支持 md / txt / pdf / docx，≤10MB）</div>
          <input ref="fileInput" type="file" accept=".md,.txt,.pdf,.docx" style="display:none" @change="handleFileSelect">
        </div>
        <div class="toolbar">
          <button class="btn btn-primary" @click="openCreate">+ 手动创建</button>
          <button class="btn" @click="loadList">刷新</button>
          <span v-if="uploading" class="uploading-tip">上传中...</span>
        </div>

        <table v-if="docs.length" class="table">
          <thead>
            <tr><th>ID</th><th>标题</th><th>来源</th><th>状态</th><th>切片数</th><th>更新时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="d in docs" :key="d.id">
              <td>{{ d.id }}</td>
              <td class="title-cell">{{ d.title }}</td>
              <td><span class="badge" :class="srcClass(d.source_type)">{{ d.source_type || '-' }}</span></td>
              <td><span class="badge" :class="statusClass(d.status)">{{ d.status || d.index_status || '-' }}</span></td>
              <td>{{ d.chunk_count ?? d.chunks_count ?? '-' }}</td>
              <td>{{ d.updated_at || d.created_at || '-' }}</td>
              <td class="ops">
                <button class="btn btn-sm" @click="openDetail(d.id)">查看</button>
                <button class="btn btn-sm" @click="reindex(d)">重建索引</button>
                <button class="btn btn-sm btn-danger" @click="confirmDelete(d)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else-if="!loading" class="empty-state"><div style="font-size:32px;margin-bottom:8px;">📄</div><div>暂无文档</div></div>
        <div v-else class="loading-state">加载中...</div>
      </div>
    </div>

    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal-box wide">
        <h3>手动创建文档</h3>
        <div class="form-row"><label>标题</label><input v-model="form.title" class="input" placeholder="文档标题"></div>
        <div class="form-row"><label>内容</label><textarea v-model="form.content" class="input textarea" rows="8" placeholder="文档正文内容"></textarea></div>
        <div class="form-row"><label>标签（逗号分隔）</label><input v-model="form.tags" class="input" placeholder="如: 运维,数据库"></div>
        <div class="modal-actions">
          <button class="btn" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" @click="createDoc">创建</button>
        </div>
      </div>
    </div>

    <div v-if="showDetail" class="modal-overlay" @click.self="showDetail = false">
      <div class="modal-box wide">
        <h3>文档详情 #{{ detail.id }}</h3>
        <div class="detail-row"><span class="detail-label">标题</span><span class="detail-val">{{ detail.title }}</span></div>
        <div class="detail-row"><span class="detail-label">来源</span><span class="badge" :class="srcClass(detail.source_type)">{{ detail.source_type || '-' }}</span></div>
        <div class="detail-row"><span class="detail-label">状态</span><span class="badge" :class="statusClass(detail.status || detail.index_status)">{{ detail.status || detail.index_status || '-' }}</span></div>
        <div class="detail-row"><span class="detail-label">标签</span>
          <span v-for="t in tagList(detail.tags)" :key="t" class="tag-mini">{{ t }}</span>
        </div>
        <div class="detail-block"><div class="detail-label">内容预览</div><div class="detail-text">{{ (detail.content || '').slice(0, 5000) }}</div></div>
        <div class="detail-block"><div class="detail-label">切片列表（{{ (detail.chunks || []).length }} 条）</div>
          <div v-if="detail.chunks && detail.chunks.length" class="chunks-list">
            <div v-for="c in detail.chunks" :key="c.id" class="chunk-item">
              <span class="chunk-id">#{{ c.id }}</span>
              <span class="chunk-text">{{ (c.content || c.text || '').slice(0, 200) }}{{ (c.content || c.text || '').length > 200 ? '...' : '' }}</span>
            </div>
          </div>
          <div v-else class="empty-state">无切片</div>
        </div>
        <div class="modal-actions"><button class="btn" @click="showDetail = false">关闭</button></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const docs = ref([])
const stats = ref({})
const fileInput = ref(null)
const uploading = ref(false)
const dragOver = ref(false)

const ragQuery = ref('')
const ragItems = ref([])
const ragSearched = ref(false)
const ragSearching = ref(false)

const showCreate = ref(false)
const form = ref({ title: '', content: '', tags: '', source: 'manual' })

const showDetail = ref(false)
const detail = ref({})

function tagList(tags) {
  if (!tags) return []
  if (Array.isArray(tags)) return tags
  return String(tags).split(',').map(t => t.trim()).filter(Boolean)
}

function srcClass(s) {
  const m = { manual: 'src-manual', upload: 'src-upload', wiki: 'src-wiki', archive: 'src-archive' }
  return m[s] || 'src-manual'
}

function statusClass(s) {
  if (!s) return 'st-pending'
  if (s === 'indexed' || s === 'ok' || s === 'done') return 'st-indexed'
  if (s === 'failed' || s === 'error') return 'st-failed'
  return 'st-pending'
}

async function loadList() {
  loading.value = true
  try {
    const data = await request.get('/knowledge/documents/api/list')
    docs.value = data.items || []
    stats.value = { total_docs: data.total_docs, indexed_count: data.indexed_count, total_chunks: data.total_chunks }
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

async function runSearch() {
  if (!ragQuery.value.trim()) {
    ElMessage.warning('请输入检索内容')
    return
  }
  ragSearching.value = true
  ragSearched.value = true
  try {
    const data = await request.get('/knowledge/documents/search', { params: { q: ragQuery.value } })
    ragItems.value = data.items || []
  } catch (e) {
    ElMessage.error('检索失败: ' + (e.message || e))
    ragItems.value = []
  } finally {
    ragSearching.value = false
  }
}

function triggerUpload() {
  fileInput.value?.click()
}

async function handleFileSelect(e) {
  const f = e.target.files?.[0]
  if (f) await uploadFile(f)
  e.target.value = ''
}

async function handleDrop(e) {
  dragOver.value = false
  const f = e.dataTransfer.files?.[0]
  if (f) await uploadFile(f)
}

async function uploadFile(file) {
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('title', file.name.replace(/\.[^.]+$/, ''))
    fd.append('tags', '')
    await request.post('/knowledge/documents/api/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    ElMessage.success('上传成功')
    loadList()
  } catch (e) {
    ElMessage.error('上传失败: ' + (e.message || e))
  } finally {
    uploading.value = false
  }
}

function openCreate() {
  form.value = { title: '', content: '', tags: '', source: 'manual' }
  showCreate.value = true
}

async function createDoc() {
  if (!form.value.title || !form.value.content) {
    ElMessage.warning('请输入标题和内容')
    return
  }
  try {
    await request.post('/knowledge/documents/api/create', { ...form.value, tags: form.value.tags })
    ElMessage.success('已创建')
    showCreate.value = false
    loadList()
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.message || e))
  }
}

async function openDetail(id) {
  try {
    const resp = await request.get(`/knowledge/documents/api/${id}`)
    detail.value = { ...resp.doc, chunks: resp.chunks || [] }
    showDetail.value = true
  } catch (e) {
    ElMessage.error('获取详情失败: ' + (e.message || e))
  }
}

async function reindex(d) {
  try {
    await request.post(`/knowledge/documents/api/${d.id}/reindex`)
    ElMessage.success('已触发重建索引')
    loadList()
  } catch (e) {
    ElMessage.error('重建失败: ' + (e.message || e))
  }
}

async function confirmDelete(d) {
  try {
    await ElMessageBox.confirm(`确定删除文档「${d.title}」？`, '删除确认', { type: 'warning' })
    await request.post(`/knowledge/documents/api/${d.id}/delete`)
    ElMessage.success('已删除')
    loadList()
  } catch (e) {
    if (e !== 'cancel' && e?.message !== 'cancel') {
      ElMessage.error('删除失败: ' + (e.message || e))
    }
  }
}

onMounted(loadList)
</script>

<style scoped>
.kbdoc-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.stat-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }
.stat-card { display: flex; align-items: center; gap: 12px; padding: 14px 16px; background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.stat-icon { width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 20px; }
.stat-icon.blue { background: rgba(59,130,246,0.12); }
.stat-icon.green { background: rgba(34,197,94,0.12); }
.stat-icon.indigo { background: rgba(99,102,241,0.12); }
.stat-value { font-size: 1.4rem; font-weight: 700; color: var(--text, #1e293b); }
.stat-label { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); }
.panel-body { padding: 16px 18px; }
.rag-box { display: flex; gap: 8px; margin-bottom: 12px; }
.rag-results { display: flex; flex-direction: column; gap: 8px; }
.rag-item { padding: 10px 12px; border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; background: var(--bg-hover, rgba(0,0,0,0.02)); }
.rag-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }
.rag-score { font-size: 0.72rem; font-weight: 700; color: #22c55e; background: rgba(34,197,94,0.1); padding: 2px 8px; border-radius: 8px; }
.rag-doc { font-size: 0.78rem; color: var(--text, #1e293b); font-weight: 500; }
.rag-meta { font-size: 0.7rem; }
.rag-content { font-size: 0.82rem; color: var(--text-secondary, #475569); line-height: 1.5; white-space: pre-wrap; }
.rag-count { font-size: 0.72rem; color: var(--text-tertiary, #94a3b8); margin-top: 6px; }
.upload-zone { border: 2px dashed var(--border-strong, rgba(0,0,0,0.15)); border-radius: 10px; padding: 20px; text-align: center; cursor: pointer; transition: all 0.2s; color: var(--text-secondary, #64748b); font-size: 0.85rem; margin-bottom: 12px; }
.upload-zone:hover, .upload-zone.active { border-color: var(--accent, #6366f1); background: rgba(99,102,241,0.04); color: var(--accent, #6366f1); }
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; }
.uploading-tip { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.title-cell { font-weight: 500; }
.ops { display: flex; gap: 6px; flex-wrap: wrap; }
.tag-mini { display: inline-block; padding: 1px 6px; border-radius: 4px; background: rgba(99,102,241,0.08); color: var(--accent, #6366f1); font-size: 0.7rem; margin-right: 4px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.src-manual { background: rgba(99,102,241,0.1); color: #6366f1; }
.badge.src-upload { background: rgba(59,130,246,0.1); color: #3b82f6; }
.badge.src-wiki { background: rgba(168,85,247,0.1); color: #a855f7; }
.badge.src-archive { background: rgba(245,158,11,0.1); color: #d97706; }
.badge.st-indexed { background: rgba(34,197,94,0.12); color: #22c55e; }
.badge.st-failed { background: rgba(239,68,68,0.12); color: #ef4444; }
.badge.st-pending { background: rgba(148,163,184,0.12); color: #64748b; }
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
.detail-text { margin-top: 4px; padding: 10px; background: var(--bg-hover, rgba(0,0,0,0.03)); border-radius: 6px; font-size: 0.82rem; white-space: pre-wrap; line-height: 1.5; max-height: 300px; overflow-y: auto; }
.chunks-list { margin-top: 6px; display: flex; flex-direction: column; gap: 6px; }
.chunk-item { padding: 8px 10px; background: var(--bg-hover, rgba(0,0,0,0.03)); border-radius: 6px; font-size: 0.78rem; display: flex; gap: 8px; }
.chunk-id { color: var(--accent, #6366f1); font-weight: 600; min-width: 40px; }
.chunk-text { color: var(--text-secondary, #475569); }
</style>
