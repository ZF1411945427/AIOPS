<template>
  <div class="tags-page">
    <div class="page-header">
      <h1>标签管理</h1>
      <p>资产标签云与关联管理 · 共 {{ tags.length }} 个标签</p>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="openAssign">+ 打标签</button>
      <button class="btn" @click="loadAll">刷新</button>
    </div>

    <div class="panel">
      <div class="panel-head">标签云</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="tags.length" class="tag-cloud">
          <span v-for="t in tags" :key="t.name" class="tag-chip" :class="{ active: currentTag === t.name }" @click="selectTag(t.name)">
            {{ t.name }} <span class="tag-count">{{ t.count }}</span>
          </span>
        </div>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">🏷️</div><div>暂无标签</div></div>
      </div>
    </div>

    <div v-if="currentTag" class="panel" style="margin-top:14px;">
      <div class="panel-head">标签「{{ currentTag }}」关联资产 · {{ taggedAssets.length }} 项</div>
      <div class="panel-body">
        <table v-if="taggedAssets.length" class="table">
          <thead><tr><th>ID</th><th>名称</th><th>CI 类型</th><th>IP</th><th>标签</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="a in taggedAssets" :key="a.id">
              <td>{{ a.id }}</td>
              <td>{{ a.name }}</td>
              <td><span class="badge ci-type">{{ a.ci_type || '-' }}</span></td>
              <td>{{ a.ip || '-' }}</td>
              <td><span v-for="t in a.tags" :key="t" class="tag-mini">{{ t }}</span></td>
              <td><button class="btn btn-sm btn-danger" @click="removeTag(a)">移除</button></td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">该标签无关联资产</div>
      </div>
    </div>

    <div v-if="showAssignDialog" class="modal-overlay" @click.self="showAssignDialog = false">
      <div class="modal-box">
        <h3>打标签</h3>
        <div class="form-row"><label>资产</label>
          <select v-model="assignForm.asset_id" class="input">
            <option v-for="a in allAssets" :key="a.id" :value="a.id">{{ a.name }} ({{ a.ip || '-' }})</option>
          </select>
        </div>
        <div class="form-row"><label>标签</label><input v-model="assignForm.tag" class="input" placeholder="如: 生产环境"></div>
        <div class="modal-actions">
          <button class="btn" @click="showAssignDialog = false">取消</button>
          <button class="btn btn-primary" @click="assignTag">确认</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const tags = ref([])
const currentTag = ref('')
const taggedAssets = ref([])
const allAssets = ref([])
const showAssignDialog = ref(false)
const assignForm = ref({ asset_id: 0, tag: '' })

async function loadCloud() {
  try {
    const data = await request.get('/tags/api/cloud')
    tags.value = data.tags || []
  } catch (e) { /* 静默 */ }
}

async function loadTagged() {
  if (!currentTag.value) { taggedAssets.value = []; return }
  try {
    const data = await request.get('/tags/api/assets', { params: { tag: currentTag.value } })
    taggedAssets.value = data.assets || []
  } catch (e) { /* 静默 */ }
}

async function loadAllAssets() {
  try {
    const data = await request.get('/tags/api/all-assets')
    allAssets.value = data.assets || []
  } catch (e) { /* 静默 */ }
}

async function loadAll() {
  loading.value = true
  await Promise.all([loadCloud(), loadAllAssets()])
  if (currentTag.value) await loadTagged()
  loading.value = false
}

function selectTag(t) {
  currentTag.value = currentTag.value === t ? '' : t
  loadTagged()
}

async function openAssign() {
  if (!allAssets.value.length) await loadAllAssets()
  assignForm.value = { asset_id: allAssets.value[0]?.id || 0, tag: currentTag.value }
  showAssignDialog.value = true
}

async function assignTag() {
  if (!assignForm.value.asset_id || !assignForm.value.tag) {
    ElMessage.warning('请选择资产并输入标签')
    return
  }
  try {
    await request.post('/tags/api/assign', assignForm.value)
    ElMessage.success('已打标签')
    showAssignDialog.value = false
    loadAll()
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.message || e))
  }
}

async function removeTag(a) {
  try {
    await request.post('/tags/api/remove', { asset_id: a.id, tag: currentTag.value })
    ElMessage.success('已移除')
    loadAll()
  } catch (e) {
    ElMessage.error('移除失败: ' + (e.message || e))
  }
}

onMounted(loadAll)
</script>

<style scoped>
.tags-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 16px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); }
.panel-body { padding: 16px 18px; }
.tag-cloud { display: flex; flex-wrap: wrap; gap: 8px; }
.tag-chip { padding: 6px 12px; border-radius: 16px; background: rgba(99,102,241,0.08); color: var(--accent, #6366f1); font-size: 0.82rem; cursor: pointer; transition: all 0.2s; }
.tag-chip:hover { background: rgba(99,102,241,0.15); }
.tag-chip.active { background: var(--accent, #6366f1); color: #fff; }
.tag-count { font-size: 0.7rem; opacity: 0.8; margin-left: 4px; }
.tag-mini { display: inline-block; padding: 1px 6px; border-radius: 4px; background: rgba(99,102,241,0.08); color: var(--accent, #6366f1); font-size: 0.7rem; margin-right: 4px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.badge.ci-type { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; background: rgba(59,130,246,0.1); color: #3b82f6; }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 380px; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; color: var(--text, #1e293b); }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
