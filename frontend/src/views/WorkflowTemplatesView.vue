<template>
  <div class="wft-page">
    <div class="page-header">
      <h1>SOP 工作流模板</h1>
      <p>标准化运维剧本管理 · 共 {{ total }} 个</p>
    </div>

    <div class="toolbar">
      <select v-model="categoryFilter" class="input select-input" @change="onFilterChange">
        <option value="">全部分类</option>
        <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
      </select>
      <input v-model="search" class="input search-input" placeholder="搜索名称/描述" @keyup.enter="onSearchChange">
      <button class="btn" @click="loadList">刷新</button>
      <button class="btn btn-primary" @click="openCreate">+ 新建模板</button>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="items.length" class="table">
          <thead>
            <tr><th>ID</th><th>名称</th><th>分类</th><th>触发类型</th><th>风险</th><th>节点数</th><th>启用</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="it in filteredItems" :key="it.id">
              <td>#{{ it.id }}</td>
              <td class="title-cell">{{ it.name }}</td>
              <td><span class="badge cat-badge">{{ it.category || '-' }}</span></td>
              <td><span class="badge trig-badge">{{ it.trigger_type }}</span></td>
              <td><span class="badge" :class="riskClass(it.risk_level)">{{ it.risk_level }}</span></td>
              <td>{{ (it.nodes || []).length }}</td>
              <td><span class="badge" :class="it.enabled ? 'en-badge' : 'dis-badge'">{{ it.enabled ? '启用' : '禁用' }}</span></td>
              <td class="ops">
                <button class="btn btn-sm" @click="openDetail(it.id)">查看</button>
                <button class="btn btn-sm" @click="openEdit(it.id)">编辑</button>
                <button class="btn btn-sm" @click="toggleEnabled(it)">{{ it.enabled ? '禁用' : '启用' }}</button>
                <button class="btn btn-sm btn-danger" @click="confirmDelete(it)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">📋</div><div>暂无 SOP 模板</div></div>
        <div v-if="totalPages > 1 && !search.trim()" class="pagination">
          <button class="btn btn-sm" :disabled="currentPage <= 1" @click="goPage(1)">首页</button>
          <button class="btn btn-sm" :disabled="currentPage <= 1" @click="goPage(currentPage - 1)">上一页</button>
          <span v-for="p in pageNumbers" :key="p" class="page-num" :class="{ active: p === currentPage }" @click="goPage(p)">{{ p }}</span>
          <button class="btn btn-sm" :disabled="currentPage >= totalPages" @click="goPage(currentPage + 1)">下一页</button>
          <button class="btn btn-sm" :disabled="currentPage >= totalPages" @click="goPage(totalPages)">末页</button>
          <span class="page-jump">跳转 <input type="number" class="page-input" v-model.number="jumpPage" min="1" :max="totalPages" @keyup.enter="goPage(jumpPage)" /> 页</span>
          <span class="page-info">共 {{ total }} 条 / {{ totalPages }} 页</span>
        </div>
      </div>
    </div>

    <div v-if="showDialog" class="modal-overlay" @click.self="closeDialog">
      <div class="modal-box xwide">
        <h3>{{ editing ? '编辑模板' : '新建模板' }}</h3>
        <div class="form-grid">
          <div class="form-row"><label>模板名称</label><input v-model="form.name" class="input" placeholder="如: 磁盘告警处置 SOP"></div>
          <div class="form-row"><label>分类</label>
            <select v-model="form.category" class="input">
              <option value="generic">generic</option>
              <option value="disk">disk</option>
              <option value="service">service</option>
              <option value="scaling">scaling</option>
              <option value="healing">healing</option>
              <option value="k8s">k8s</option>
              <option value="database">database</option>
              <option value="network">network</option>
              <option value="security">security</option>
              <option value="backup">backup</option>
              <option value="monitoring">monitoring</option>
              <option value="deployment">deployment</option>
              <option value="performance">performance</option>
              <option value="custom">custom</option>
            </select>
          </div>
          <div class="form-row"><label>触发类型</label>
            <select v-model="form.trigger_type" class="input">
              <option value="manual">manual</option>
              <option value="alert_auto">alert_auto</option>
              <option value="scheduled">scheduled</option>
            </select>
          </div>
          <div class="form-row"><label>风险等级</label>
            <select v-model="form.risk_level" class="input">
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
              <option value="critical">critical</option>
            </select>
          </div>
        </div>
        <div class="form-row"><label>描述</label><textarea v-model="form.description" class="input textarea" rows="2" placeholder="模板说明"></textarea></div>
        <div class="form-row"><label>触发条件 (JSON)</label>
          <textarea v-model="form.triggerConditionStr" class="input textarea" rows="2" placeholder='{"metric": "disk_usage", "threshold": 90}'></textarea>
        </div>
        <div class="form-row"><label>节点定义 (JSON 数组)</label>
          <textarea v-model="form.nodesStr" class="input textarea mono" rows="8" placeholder='[{"id":"n1","name":"查盘","action_type":"run_command","payload_template":{"command":"df -h","asset_id":"{{ context.asset_id }}"},"requires_confirm":false}]'></textarea>
        </div>
        <div class="form-row"><label>边定义 (JSON 数组)</label>
          <textarea v-model="form.edgesStr" class="input textarea mono" rows="4" placeholder='[{"source":"n1","target":"n2"}]'></textarea>
        </div>
        <div class="form-row"><label><input type="checkbox" v-model="form.enabled"> 启用此模板</label></div>
        <div class="modal-actions">
          <button class="btn" @click="closeDialog">取消</button>
          <button class="btn btn-primary" @click="saveItem">{{ editing ? '保存' : '创建' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showDetail" class="modal-overlay" @click.self="showDetail = false">
      <div class="modal-box xwide">
        <h3>模板详情 #{{ detail.id }} — {{ detail.name }}</h3>
        <div class="detail-row"><span class="detail-label">描述</span><span class="detail-val">{{ detail.description || '-' }}</span></div>
        <div class="detail-row"><span class="detail-label">分类</span><span class="badge cat-badge">{{ detail.category }}</span></div>
        <div class="detail-row"><span class="detail-label">触发类型</span><span class="badge trig-badge">{{ detail.trigger_type }}</span></div>
        <div class="detail-row"><span class="detail-label">风险等级</span><span class="badge" :class="riskClass(detail.risk_level)">{{ detail.risk_level }}</span></div>
        <div class="detail-row"><span class="detail-label">触发条件</span><code class="inline-code">{{ JSON.stringify(detail.trigger_condition || {}) }}</code></div>
        <div class="detail-block"><div class="detail-label">节点流程</div>
          <div class="node-preview">
            <div v-for="(n, i) in (detail.nodes || [])" :key="n.id" class="node-prev-item" :class="{ expanded: selectedNodeId === n.id }" @click="toggleNode(n.id)">
              <span class="node-prev-idx">{{ i + 1 }}</span>
              <span class="node-prev-name">{{ n.name || n.id }}</span>
              <span class="node-prev-action">{{ n.action_type }}</span>
              <span v-if="n.requires_confirm" class="badge confirm-badge">需确认</span>
              <span class="node-prev-arrow">{{ selectedNodeId === n.id ? '▼' : '▶' }}</span>
              <div v-if="selectedNodeId === n.id" class="node-detail" @click.stop>
                <div class="node-detail-row"><span class="node-detail-key">动作类型</span><code class="inline-code">{{ n.action_type }}</code></div>
                <div class="node-detail-row"><span class="node-detail-key">执行参数</span><code class="inline-code">{{ JSON.stringify(n.payload_template || {}) }}</code></div>
                <div v-if="n.payload_template && n.payload_template.command" class="node-detail-row"><span class="node-detail-key">实际命令</span><pre class="node-cmd">{{ n.payload_template.command }}</pre></div>
                <div v-if="n.payload_template && n.payload_template.service" class="node-detail-row"><span class="node-detail-key">目标服务</span><code class="inline-code">{{ n.payload_template.service }}</code></div>
                <div v-if="n.payload_template && n.payload_template.path" class="node-detail-row"><span class="node-detail-key">目标路径</span><code class="inline-code">{{ n.payload_template.path }}</code></div>
                <div class="node-detail-row"><span class="node-detail-key">需确认</span><span :class="n.requires_confirm ? 'txt-warn' : 'txt-ok'">{{ n.requires_confirm ? '是' : '否' }}</span></div>
                <div class="node-detail-row"><span class="node-detail-key">重试次数</span><code class="inline-code">{{ n.retry_count || 0 }}</code></div>
              </div>
            </div>
          </div>
        </div>
        <div class="detail-block"><div class="detail-label">边 (依赖关系)</div><code class="inline-code">{{ JSON.stringify(detail.edges || []) }}</code></div>
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
const total = ref(0)

const currentPage = ref(1)
const pageSize = ref(20)
const totalPages = ref(1)
const jumpPage = ref(1)
const pageNumbers = computed(() => {
  const pages = []
  const cur = currentPage.value
  const tp = totalPages.value
  if (tp <= 7) {
    for (let i = 1; i <= tp; i++) pages.push(i)
  } else {
    pages.push(1)
    if (cur > 4) pages.push('...')
    const start = Math.max(2, cur - 1)
    const end = Math.min(tp - 1, cur + 1)
    for (let i = start; i <= end; i++) pages.push(i)
    if (cur < tp - 3) pages.push('...')
    pages.push(tp)
  }
  return pages
})
function goPage(p) {
  if (p < 1 || p > totalPages.value || p === currentPage.value) return
  currentPage.value = p
  loadList()
}
function onFilterChange() {
  currentPage.value = 1
  loadList()
}
function onSearchChange() {
  currentPage.value = 1
  loadList()
}

const showDialog = ref(false)
const editing = ref(false)
const editingId = ref(null)
const form = ref({
  name: '', description: '', category: 'generic', trigger_type: 'manual',
  risk_level: 'medium', enabled: true,
  triggerConditionStr: '{}', nodesStr: '[]', edgesStr: '[]',
})

const showDetail = ref(false)
const detail = ref({})
const selectedNodeId = ref(null)

function toggleNode(nid) {
  selectedNodeId.value = selectedNodeId.value === nid ? null : nid
}

const filteredItems = computed(() => {
  if (!search.value.trim()) return items.value
  const kw = search.value.toLowerCase()
  return items.value.filter(it =>
    (it.name || '').toLowerCase().includes(kw) ||
    (it.description || '').toLowerCase().includes(kw)
  )
})

async function loadCategories() {
  try {
    const data = await request.get('/workflow/api/templates', { params: { per_page: 1000 } })
    const cats = new Set(['generic', 'disk', 'service', 'scaling', 'healing', 'k8s', 'database', 'network', 'security', 'backup', 'monitoring', 'deployment', 'performance', 'custom'])
    ;(data.items || []).forEach(it => { if (it.category) cats.add(it.category) })
    categories.value = [...cats].sort()
  } catch (e) { /* ignore */ }
}

async function loadList() {
  loading.value = true
  try {
    const params = {}
    if (categoryFilter.value) params.category = categoryFilter.value
    if (search.value.trim()) {
      params.per_page = 1000
    } else {
      params.page = currentPage.value
      params.per_page = pageSize.value
    }
    const data = await request.get('/workflow/api/templates', { params })
    items.value = data.items || []
    if (!search.value.trim()) {
      total.value = data.total || 0
      totalPages.value = data.total_pages || 1
    }
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = false
  editingId.value = null
  form.value = {
    name: '', description: '', category: 'generic', trigger_type: 'manual',
    risk_level: 'medium', enabled: true,
    triggerConditionStr: '{}', nodesStr: '[]', edgesStr: '[]',
  }
  showDialog.value = true
}

async function openEdit(id) {
  try {
    const data = await request.get(`/workflow/api/templates/${id}`)
    editing.value = true
    editingId.value = id
    form.value = {
      name: data.name || '',
      description: data.description || '',
      category: data.category || 'generic',
      trigger_type: data.trigger_type || 'manual',
      risk_level: data.risk_level || 'medium',
      enabled: !!data.enabled,
      triggerConditionStr: JSON.stringify(data.trigger_condition || {}, null, 2),
      nodesStr: JSON.stringify(data.nodes || [], null, 2),
      edgesStr: JSON.stringify(data.edges || [], null, 2),
    }
    showDialog.value = true
  } catch (e) {
    ElMessage.error('获取详情失败: ' + (e.message || e))
  }
}

async function openDetail(id) {
  try {
    detail.value = await request.get(`/workflow/api/templates/${id}`)
    selectedNodeId.value = null
    showDetail.value = true
  } catch (e) {
    ElMessage.error('获取详情失败: ' + (e.message || e))
  }
}

async function saveItem() {
  if (!form.value.name) {
    ElMessage.warning('请输入模板名称')
    return
  }
  let triggerCondition, nodes, edges
  try {
    triggerCondition = JSON.parse(form.value.triggerConditionStr || '{}')
  } catch (e) {
    ElMessage.warning('触发条件 JSON 格式错误')
    return
  }
  try {
    nodes = JSON.parse(form.value.nodesStr || '[]')
  } catch (e) {
    ElMessage.warning('节点定义 JSON 格式错误')
    return
  }
  try {
    edges = JSON.parse(form.value.edgesStr || '[]')
  } catch (e) {
    ElMessage.warning('边定义 JSON 格式错误')
    return
  }
  if (!Array.isArray(nodes) || !nodes.length) {
    ElMessage.warning('节点定义必须是非空数组')
    return
  }
  try {
    const payload = {
      name: form.value.name,
      description: form.value.description,
      category: form.value.category,
      trigger_type: form.value.trigger_type,
      risk_level: form.value.risk_level,
      enabled: form.value.enabled,
      trigger_condition: triggerCondition,
      nodes,
      edges,
    }
    if (editing.value && editingId.value) {
      await request.post(`/workflow/api/templates/${editingId.value}/update`, payload)
      ElMessage.success('已保存')
    } else {
      await request.post('/workflow/api/templates/create', payload)
      ElMessage.success('已创建')
    }
    showDialog.value = false
    loadList()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.message || e))
  }
}

async function toggleEnabled(it) {
  try {
    await request.post(`/workflow/api/templates/${it.id}/update`, { enabled: !it.enabled })
    ElMessage.success(it.enabled ? '已禁用' : '已启用')
    loadList()
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.message || e))
  }
}

async function confirmDelete(it) {
  try {
    await ElMessageBox.confirm(`确定删除模板「${it.name}」？`, '删除确认', { type: 'warning' })
    await request.post(`/workflow/api/templates/${it.id}/delete`)
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

function riskClass(r) {
  return { 'risk-low': r === 'low', 'risk-medium': r === 'medium', 'risk-high': r === 'high', 'risk-critical': r === 'critical' }
}

onMounted(() => {
  loadCategories()
  loadList()
})
</script>

<style scoped>
.wft-page { padding: 4px; }
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
.ops { display: flex; gap: 6px; flex-wrap: wrap; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.cat-badge { background: rgba(20,184,166,0.12); color: #14b8a6; }
.badge.trig-badge { background: rgba(99,102,241,0.12); color: #6366f1; }
.badge.risk-low { background: rgba(16,185,129,0.12); color: #10b981; }
.badge.risk-medium { background: rgba(245,158,11,0.12); color: #f59e0b; }
.badge.risk-high { background: rgba(239,68,68,0.12); color: #ef4444; }
.badge.risk-critical { background: rgba(220,38,38,0.18); color: #dc2626; }
.badge.en-badge { background: rgba(16,185,129,0.12); color: #10b981; }
.badge.dis-badge { background: rgba(100,116,139,0.12); color: #64748b; }
.badge.confirm-badge { background: rgba(245,158,11,0.12); color: #f59e0b; }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 6px; margin-top: 16px; flex-wrap: wrap; }
.page-info { font-size: 0.82rem; color: var(--text-secondary, #64748b); }
.page-num { display: inline-flex; align-items: center; justify-content: center; min-width: 30px; height: 30px; padding: 0 6px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.8rem; cursor: pointer; transition: all 0.2s; user-select: none; }
.page-num:hover { background: var(--bg-hover, rgba(99,102,241,0.08)); border-color: var(--accent, #6366f1); }
.page-num.active { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); font-weight: 600; }
.page-jump { font-size: 0.8rem; color: var(--text-secondary, #64748b); display: flex; align-items: center; gap: 4px; }
.page-input { width: 50px; padding: 3px 6px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; text-align: center; font-size: 0.8rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 380px; max-width: 90vw; max-height: 90vh; overflow-y: auto; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-box.xwide { min-width: 720px; }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; color: var(--text, #1e293b); }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.textarea { resize: vertical; font-family: inherit; }
.textarea.mono { font-family: 'Consolas', monospace; font-size: 0.78rem; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.detail-row { display: flex; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-size: 0.85rem; align-items: center; }
.detail-label { min-width: 80px; color: var(--text-secondary, #64748b); font-size: 0.78rem; }
.detail-val { color: var(--text, #1e293b); }
.detail-block { margin: 10px 0; }
.inline-code { font-family: 'Consolas', monospace; background: rgba(0,0,0,0.04); padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; word-break: break-all; }
.node-preview { display: flex; flex-direction: column; gap: 6px; margin-top: 6px; }
.node-prev-item { display: flex; align-items: center; gap: 8px; padding: 6px 10px; background: var(--bg-hover, rgba(0,0,0,0.03)); border-radius: 6px; font-size: 0.82rem; }
.node-prev-idx { display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; border-radius: 50%; background: var(--accent, #6366f1); color: #fff; font-size: 0.7rem; font-weight: 600; }
.node-prev-name { font-weight: 500; }
.node-prev-action { margin-left: auto; font-size: 0.7rem; color: var(--text-secondary, #64748b); font-family: 'Consolas', monospace; background: rgba(99,102,241,0.08); padding: 1px 6px; border-radius: 4px; }
.node-prev-item { cursor: pointer; transition: background 0.2s; }
.node-prev-item:hover { background: rgba(99,102,241,0.06); }
.node-prev-item.expanded { background: rgba(99,102,241,0.08); border: 1px solid rgba(99,102,241,0.2); }
.node-prev-arrow { font-size: 0.7rem; color: var(--text-secondary, #94a3b8); margin-left: 4px; }
.node-detail { width: 100%; margin-top: 8px; padding: 10px 12px; background: rgba(0,0,0,0.03); border-radius: 6px; display: flex; flex-direction: column; gap: 6px; }
.node-detail-row { display: flex; gap: 8px; align-items: flex-start; font-size: 0.78rem; }
.node-detail-key { min-width: 70px; color: var(--text-secondary, #64748b); flex-shrink: 0; }
.node-cmd { flex: 1; margin: 0; padding: 8px 10px; background: rgba(0,0,0,0.06); border-radius: 6px; font-family: 'Consolas', 'Monaco', monospace; font-size: 0.75rem; white-space: pre-wrap; word-break: break-all; color: var(--text, #1e293b); line-height: 1.5; }
.txt-warn { color: #f59e0b; font-weight: 600; }
.txt-ok { color: #10b981; }
</style>
