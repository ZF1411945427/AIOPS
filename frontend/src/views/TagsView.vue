<template>
  <div class="tags-page">
    <div class="page-header">
      <h1>标签管理</h1>
      <p>资产标签分类管理 · 共 {{ allTagsCount }} 个标签，{{ categories.length }} 个分类</p>
    </div>

    <div class="tags-layout">
      <!-- 左侧分类列表 -->
      <aside class="cat-sidebar">
        <div class="sidebar-head">
          <span>分类</span>
          <button class="btn-icon" title="新增分类" @click="openCatDialog()">+</button>
        </div>
        <div class="cat-list">
          <div class="cat-item" :class="{ active: !currentCatId }" @click="selectCat(null)">
            <span class="cat-icon">📋</span>
            <span class="cat-label">全部</span>
            <span class="cat-count">{{ allTagsCount }}</span>
          </div>
          <div v-for="c in categories" :key="c.id" class="cat-item" :class="{ active: currentCatId === c.id }" @click="selectCat(c.id)">
            <span class="cat-icon">{{ c.icon }}</span>
            <span class="cat-label">{{ c.label }}</span>
            <span class="cat-dot" :style="{ background: c.color }"></span>
            <span class="cat-count">{{ categoryCounts[c.id] || 0 }}</span>
            <button class="btn-icon-sm" @click.stop="openCatDialog(c)">✏️</button>
          </div>
        </div>
      </aside>

      <!-- 右侧标签卡片 -->
      <main class="tag-main">
        <!-- 工具栏 -->
        <div class="toolbar">
          <input v-model="search" class="search-input" placeholder="搜索标签..." @input="filterTags" />
          <div class="toolbar-right">
            <select v-model="sortBy" class="sel">
              <option value="count">按使用量</option>
              <option value="name">按名称</option>
              <option value="recent">按创建</option>
            </select>
            <button class="btn btn-primary" @click="openTagDialog()">+ 新建标签</button>
          </div>
        </div>

        <!-- 标签网格 -->
        <div v-if="filteredTags.length" class="tag-grid">
          <div v-for="t in filteredTags" :key="t.id" class="tag-card" :style="{ '--tag-color': t.color }">
            <div class="tag-card-head">
              <span class="tag-dot" :style="{ background: t.color }"></span>
              <span class="tag-name">{{ t.name }}</span>
              <span class="tag-usage">{{ t.usage_count }} 个资产</span>
            </div>
            <div v-if="t.description" class="tag-desc">{{ t.description }}</div>
            <div class="tag-card-foot">
              <span class="tag-cat-badge" v-if="getCatLabel(t.category_id)">{{ getCatLabel(t.category_id) }}</span>
              <div class="tag-actions">
                <button class="btn-icon-sm" title="编辑" @click="openTagDialog(t)">✏️</button>
                <button class="btn-icon-sm danger" title="删除" @click="deleteTag(t)">🗑️</button>
              </div>
            </div>
            <button class="tag-asset-btn" @click="selectTagByName(t.name)">查看资产</button>
          </div>
        </div>
        <div v-else-if="!loading" class="empty-state">
          <div style="font-size:40px;margin-bottom:12px;">🏷️</div>
          <div>{{ search ? '没有找到匹配的标签' : '暂无标签' }}</div>
          <button v-if="!search" class="btn btn-primary" style="margin-top:12px" @click="openTagDialog()">+ 新建第一个标签</button>
        </div>

        <!-- 翻页 -->
        <div v-if="totalPages > 1" class="pagination">
          <button class="btn btn-sm" :disabled="page <= 1" @click="goPage(page - 1)">上一页</button>
          <span v-for="p in totalPages" :key="p" class="page-num" :class="{ active: p === page }" @click="goPage(p)">{{ p }}</span>
          <button class="btn btn-sm" :disabled="page >= totalPages" @click="goPage(page + 1)">下一页</button>
          <span class="page-info">共 {{ total }} 条</span>
        </div>

        <!-- 标签关联资产 -->
        <div v-if="currentTagName" class="asset-panel">
          <div class="asset-panel-head">
            <span>「{{ currentTagName }}」关联资产 · {{ taggedAssets.length }} 项</span>
            <button class="btn-icon-sm" @click="currentTagName = ''">✕</button>
          </div>
          <table v-if="taggedAssets.length" class="table">
            <thead><tr><th>ID</th><th>名称</th><th>CI 类型</th><th>IP</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="a in taggedAssets" :key="a.id">
                <td>{{ a.id }}</td>
                <td>{{ a.name }}</td>
                <td><span class="badge ci-type">{{ a.ci_type || '-' }}</span></td>
                <td>{{ a.ip || '-' }}</td>
                <td><button class="btn btn-sm btn-danger" @click="removeTagFromAsset(a)">移除标签</button></td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-state" style="padding:20px">该标签无关联资产</div>
        </div>
      </main>
    </div>

    <!-- 新建/编辑分类弹框 -->
    <div v-if="showCatDialog" class="modal-overlay" @click.self="showCatDialog = false">
      <div class="modal-box">
        <h3>{{ editingCat ? '编辑分类' : '新建分类' }}</h3>
        <div class="form-row"><label>标识（英文）</label><input v-model="catForm.name" class="input" placeholder="如 env" :disabled="!!editingCat" /></div>
        <div class="form-row"><label>显示名称</label><input v-model="catForm.label" class="input" placeholder="如 环境" /></div>
        <div class="form-row"><label>图标</label><input v-model="catForm.icon" class="input" placeholder="🌐" /></div>
        <div class="form-row"><label>颜色</label>
          <div class="color-row">
            <input type="color" v-model="catForm.color" class="color-picker" />
            <span>{{ catForm.color }}</span>
          </div>
        </div>
        <div class="form-row"><label>排序</label><input type="number" v-model="catForm.sort_order" class="input" /></div>
        <div class="modal-actions">
          <button v-if="editingCat && editingCat.name !== 'other'" class="btn btn-danger" @click="deleteCat">删除分类</button>
          <div style="flex:1"></div>
          <button class="btn" @click="showCatDialog = false">取消</button>
          <button class="btn btn-primary" @click="saveCat">保存</button>
        </div>
      </div>
    </div>

    <!-- 新建/编辑标签弹框 -->
    <div v-if="showTagDialog" class="modal-overlay" @click.self="showTagDialog = false">
      <div class="modal-box">
        <h3>{{ editingTag ? '编辑标签' : '新建标签' }}</h3>
        <div class="form-row"><label>标签名称</label><input v-model="tagForm.name" class="input" placeholder="如 生产环境" /></div>
        <div class="form-row"><label>所属分类</label>
          <select v-model="tagForm.category_id" class="input">
            <option value="">未分类</option>
            <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.icon }} {{ c.label }}</option>
          </select>
        </div>
        <div class="form-row"><label>描述</label><input v-model="tagForm.description" class="input" placeholder="标签用途说明（可选）" /></div>
        <div class="form-row"><label>颜色</label>
          <div class="color-row">
            <input type="color" v-model="tagForm.color" class="color-picker" />
            <div class="color-presets">
              <span v-for="c in colorPresets" :key="c" class="color-preset" :style="{ background: c }" @click="tagForm.color = c"></span>
            </div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showTagDialog = false">取消</button>
          <button class="btn btn-primary" @click="saveTag">保存</button>
        </div>
      </div>
    </div>

    <!-- 打标签弹框 -->
    <div v-if="showAssignDialog" class="modal-overlay" @click.self="showAssignDialog = false">
      <div class="modal-box">
        <h3>给资产打标签</h3>
        <div class="form-row"><label>选择资产</label>
          <select v-model="assignForm.asset_id" class="input">
            <option v-for="a in allAssets" :key="a.id" :value="a.id">{{ a.name }} ({{ a.ip || '-' }})</option>
          </select>
        </div>
        <div class="form-row"><label>选择/输入标签</label>
          <div class="tag-picker">
            <div class="tag-picker-list">
              <span v-for="t in tags" :key="t.id" class="tag-chip" :class="{ active: assignForm.tag === t.name }" :style="{ '--tc': t.color }" @click="assignForm.tag = t.name">{{ t.name }}</span>
            </div>
            <input v-model="assignForm.tag" class="input" placeholder="或直接输入新标签名" />
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showAssignDialog = false">取消</button>
          <button class="btn btn-primary" @click="doAssign">确认打标签</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const categories = ref([])
const tags = ref([])
const currentCatId = ref(null)
const currentTagName = ref('')
const taggedAssets = ref([])
const allAssets = ref([])
const search = ref('')
const sortBy = ref('count')
const page = ref(1)
const perPage = ref(24)
const total = ref(0)
const totalPages = ref(1)
const allTagsCount = ref(0)
const categoryCounts = ref({})
const showCatDialog = ref(false)
const showTagDialog = ref(false)
const showAssignDialog = ref(false)
const editingCat = ref(null)
const editingTag = ref(null)
const catForm = ref({ name: '', label: '', icon: '🏷️', color: '#6366f1', sort_order: 0 })
const tagForm = ref({ name: '', category_id: '', color: '#6366f1', description: '' })
const assignForm = ref({ asset_id: 0, tag: '' })

const colorPresets = ['#6366f1', '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16', '#f97316']

const filteredTags = computed(() => {
  let list = tags.value
  if (currentCatId.value) {
    list = list.filter(t => t.category_id === currentCatId.value)
  }
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter(t => t.name.toLowerCase().includes(q))
  }
  if (sortBy.value === 'count') list = [...list].sort((a, b) => b.usage_count - a.usage_count)
  else if (sortBy.value === 'name') list = [...list].sort((a, b) => a.name.localeCompare(b.name))
  return list
})

function getCatTagCount(catId) {
  return tags.value.filter(t => t.category_id === catId).length
}

function getCatLabel(catId) {
  if (!catId) return ''
  const c = categories.value.find(c => c.id === catId)
  return c ? c.label : ''
}

function selectCat(id) {
  currentCatId.value = id
  search.value = ''
  page.value = 1
  loadTags()
}

function selectTagByName(name) {
  currentTagName.value = name
  loadTaggedAssets(name)
}

function goPage(p) {
  if (p < 1 || p > totalPages.value) return
  page.value = p
  loadTags()
}

watch([search, sortBy], () => {
  page.value = 1
  loadTags()
})

async function loadCategories() {
  try {
    const d = await request.get('/tags/api/categories')
    categories.value = d.categories || []
  } catch { categories.value = [] }
}

async function loadTags() {
  try {
    const d = await request.get('/tags/api/list', {
      params: { page: page.value, per_page: perPage.value, sort_by: sortBy.value, search: search.value, category_id: currentCatId.value || undefined }
    })
    tags.value = d.tags || []
    total.value = d.total || 0
    totalPages.value = d.total_pages || 1
    categoryCounts.value = d.category_counts || {}
    allTagsCount.value = d.all_tags_count || 0
  } catch { tags.value = [] }
}

async function loadTaggedAssets(tagName) {
  try {
    const d = await request.get('/tags/api/assets', { params: { tag: tagName } })
    taggedAssets.value = d.assets || []
  } catch { taggedAssets.value = [] }
}

async function loadAllAssets() {
  try {
    const d = await request.get('/tags/api/all-assets')
    allAssets.value = d.assets || []
  } catch { allAssets.value = [] }
}

async function loadAll() {
  loading.value = true
  await Promise.all([loadCategories(), loadTags(), loadAllAssets()])
  loading.value = false
}

function openCatDialog(cat = null) {
  editingCat.value = cat
  if (cat) {
    catForm.value = { name: cat.name, label: cat.label, icon: cat.icon, color: cat.color, sort_order: cat.sort_order }
  } else {
    catForm.value = { name: '', label: '', icon: '🏷️', color: '#6366f1', sort_order: 0 }
  }
  showCatDialog.value = true
}

async function saveCat() {
  if (!catForm.value.name.trim()) { ElMessage.warning('分类标识不能为空'); return }
  try {
    if (editingCat.value) {
      await request.put(`/tags/api/categories/${editingCat.value.id}`, catForm.value)
      ElMessage.success('保存成功')
    } else {
      await request.post('/tags/api/categories', catForm.value)
      ElMessage.success('创建成功')
    }
    showCatDialog.value = false
    await Promise.all([loadCategories(), loadTags()])
  } catch (e) { ElMessage.error('保存失败: ' + (e.message || e)) }
}

async function deleteCat() {
  if (!editingCat.value) return
  try {
    await ElMessageBox.confirm('删除分类不会删除标签，标签将变为"未分类"。确认删除？', '删除确认', { type: 'warning' })
    await request.delete(`/tags/api/categories/${editingCat.value.id}`)
    ElMessage.success('已删除')
    showCatDialog.value = false
    await Promise.all([loadCategories(), loadTags()])
  } catch { }
}

function openTagDialog(tag = null) {
  editingTag.value = tag
  if (tag) {
    tagForm.value = { name: tag.name, category_id: tag.category_id || '', color: tag.color, description: tag.description || '' }
  } else {
    tagForm.value = { name: '', category_id: currentCatId.value || '', color: '#6366f1', description: '' }
  }
  showTagDialog.value = true
}

async function saveTag() {
  if (!tagForm.value.name.trim()) { ElMessage.warning('标签名称不能为空'); return }
  try {
    if (editingTag.value) {
      await request.put(`/tags/api/${editingTag.value.id}`, tagForm.value)
      ElMessage.success('保存成功')
    } else {
      await request.post('/tags/api', tagForm.value)
      ElMessage.success('创建成功')
    }
    showTagDialog.value = false
    await loadTags()
  } catch (e) { ElMessage.error('保存失败: ' + (e.message || e)) }
}

async function deleteTag(tag) {
  try {
    await ElMessageBox.confirm(`确认删除标签「${tag.name}」？资产上的该标签也会被移除。`, '删除确认', { type: 'warning' })
    await request.delete(`/tags/api/${tag.id}`)
    ElMessage.success('已删除')
    if (currentTagName.value === tag.name) currentTagName.value = ''
    await loadTags()
  } catch { }
}

async function removeTagFromAsset(asset) {
  try {
    await request.post('/tags/api/remove', { asset_id: asset.id, tag: currentTagName.value })
    ElMessage.success('已移除')
    await loadTaggedAssets(currentTagName.value)
    await loadTags()
  } catch (e) { ElMessage.error('移除失败') }
}

function openAssignDialog() {
  if (!allAssets.value.length) loadAllAssets()
  assignForm.value = { asset_id: allAssets.value[0]?.id || 0, tag: '' }
  showAssignDialog.value = true
}

async function doAssign() {
  if (!assignForm.value.asset_id || !assignForm.value.tag) { ElMessage.warning('请选择资产并输入标签'); return }
  try {
    await request.post('/tags/api/assign', assignForm.value)
    ElMessage.success('已打标签')
    showAssignDialog.value = false
    await Promise.all([loadTags(), loadAllAssets()])
  } catch (e) { ElMessage.error('操作失败') }
}

function filterTags() { }

onMounted(loadAll)
</script>

<style scoped>
.tags-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }

.tags-layout { display: flex; gap: 16px; height: calc(100vh - 130px); }

/* 左侧分类 */
.cat-sidebar { width: 200px; flex-shrink: 0; background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; display: flex; flex-direction: column; overflow: hidden; }
.sidebar-head { padding: 12px 16px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.85rem; display: flex; justify-content: space-between; align-items: center; color: var(--text, #1e293b); }
.cat-list { overflow-y: auto; flex: 1; padding: 8px; }
.cat-item { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 8px; cursor: pointer; font-size: 0.82rem; color: var(--text, #1e293b); transition: all 0.15s; }
.cat-item:hover { background: var(--bg-hover, rgba(0,0,0,0.04)); }
.cat-item.active { background: rgba(99,102,241,0.1); color: var(--accent, #6366f1); font-weight: 600; }
.cat-icon { font-size: 0.9rem; }
.cat-label { flex: 1; }
.cat-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.cat-count { font-size: 0.7rem; background: rgba(0,0,0,0.06); padding: 1px 6px; border-radius: 10px; color: var(--text-secondary, #64748b); }
.cat-item.active .cat-count { background: rgba(99,102,241,0.15); color: var(--accent, #6366f1); }

/* 右侧主体 */
.tag-main { flex: 1; display: flex; flex-direction: column; gap: 12px; min-width: 0; overflow: hidden; }

.toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.search-input { padding: 6px 12px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; width: 200px; }
.toolbar-right { display: flex; gap: 8px; align-items: center; margin-left: auto; }
.sel { padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; }

/* 标签网格 */
.tag-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; overflow-y: auto; flex: 1; }
.tag-card { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; padding: 14px; display: flex; flex-direction: column; gap: 8px; position: relative; transition: box-shadow 0.2s; }
.tag-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
.tag-card:hover .tag-asset-btn { opacity: 1; }
.tag-card-head { display: flex; align-items: center; gap: 8px; }
.tag-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.tag-name { font-weight: 600; font-size: 0.88rem; color: var(--text, #1e293b); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tag-usage { font-size: 0.7rem; color: var(--text-tertiary, #94a3b8); }
.tag-desc { font-size: 0.75rem; color: var(--text-secondary, #64748b); line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.tag-card-foot { display: flex; align-items: center; justify-content: space-between; }
.tag-cat-badge { font-size: 0.68rem; padding: 2px 8px; border-radius: 8px; background: rgba(0,0,0,0.05); color: var(--text-secondary, #64748b); }
.tag-actions { display: flex; gap: 4px; opacity: 0; transition: opacity 0.15s; }
.tag-card:hover .tag-actions { opacity: 1; }
.tag-asset-btn { position: absolute; bottom: 0; left: 0; right: 0; border: none; border-top: 1px solid var(--border, rgba(0,0,0,0.07)); background: transparent; color: var(--accent, #6366f1); font-size: 0.75rem; padding: 6px; cursor: pointer; opacity: 0; transition: opacity 0.15s; border-radius: 0 0 10px 10px; }
.tag-asset-btn:hover { background: rgba(99,102,241,0.05); }

/* 关联资产面板 */
.asset-panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; overflow: hidden; flex-shrink: 0; max-height: 300px; display: flex; flex-direction: column; }
.asset-panel-head { padding: 10px 16px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.85rem; display: flex; justify-content: space-between; align-items: center; color: var(--text, #1e293b); }
.asset-panel .table { flex: 1; overflow-y: auto; }

/* 通用 */
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-sm { padding: 3px 8px; font-size: 0.72rem; }
.btn-icon { width: 24px; height: 24px; border: none; background: transparent; cursor: pointer; font-size: 0.9rem; color: var(--text-secondary, #64748b); border-radius: 4px; display: flex; align-items: center; justify-content: center; }
.btn-icon:hover { background: rgba(0,0,0,0.06); }
.btn-icon-sm { width: 22px; height: 22px; border: none; background: transparent; cursor: pointer; font-size: 0.75rem; color: var(--text-secondary, #64748b); border-radius: 4px; display: flex; align-items: center; justify-content: center; }
.btn-icon-sm:hover { background: rgba(0,0,0,0.08); }
.btn-icon-sm.danger:hover { background: rgba(239,68,68,0.1); color: #ef4444; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 8px 12px; font-size: 0.72rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 8px 12px; font-size: 0.82rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.badge.ci-type { display: inline-block; padding: 2px 7px; border-radius: 8px; font-size: 0.68rem; font-weight: 600; background: rgba(59,130,246,0.1); color: #3b82f6; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.88rem; }

/* 弹框 */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 200; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 12px; padding: 20px 24px; min-width: 420px; max-width: 520px; box-shadow: 0 16px 40px rgba(0,0,0,0.18); }
.modal-box h3 { margin: 0 0 18px; font-size: 1rem; font-weight: 600; color: var(--text, #1e293b); }
.form-row { margin-bottom: 14px; }
.form-row label { display: block; font-size: 0.76rem; color: var(--text-secondary, #64748b); margin-bottom: 5px; font-weight: 500; }
.input { width: 100%; padding: 7px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.input:focus { outline: none; border-color: var(--accent, #6366f1); }
.color-row { display: flex; align-items: center; gap: 10px; }
.color-picker { width: 36px; height: 36px; border: none; border-radius: 6px; cursor: pointer; padding: 0; }
.color-presets { display: flex; gap: 6px; }
.color-preset { width: 22px; height: 22px; border-radius: 50%; cursor: pointer; border: 2px solid transparent; transition: border-color 0.1s; }
.color-preset:hover { border-color: rgba(0,0,0,0.3); }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; }

/* 翻页 */
.pagination { display: flex; align-items: center; justify-content: center; gap: 6px; padding: 12px 0; flex-shrink: 0; }
.page-num { min-width: 28px; height: 28px; border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 0.78rem; cursor: pointer; color: var(--text, #1e293b); }
.page-num:hover { background: rgba(0,0,0,0.05); }
.page-num.active { background: var(--accent, #6366f1); color: #fff; font-weight: 600; }
.page-info { font-size: 0.75rem; color: var(--text-tertiary, #94a3b8); margin-left: 8px; }

/* 标签选择器 */
.tag-picker-list { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; max-height: 100px; overflow-y: auto; }
.tag-chip { padding: 3px 10px; border-radius: 12px; background: rgba(99,102,241,0.08); color: var(--accent, #6366f1); font-size: 0.75rem; cursor: pointer; transition: all 0.15s; border: 1.5px solid transparent; }
.tag-chip:hover { background: rgba(99,102,241,0.15); }
.tag-chip.active { border-color: var(--accent, #6366f1); background: rgba(99,102,241,0.18); }
</style>
