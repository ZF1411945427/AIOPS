<template>
  <div class="k8s-list-page">
    <div class="page-header">
      <h1>{{ title }}</h1>
      <p>{{ subtitle }} · 共 {{ items.length }} 项</p>
    </div>

    <div class="toolbar">
      <select v-model="filters.cluster" @change="loadList">
        <option value="">全部集群</option>
        <option v-for="c in clusters" :key="c.name" :value="c.name">{{ c.name }}</option>
      </select>
      <input v-model="filters.namespace" class="input ns-input" placeholder="命名空间（留空查全部）" @keyup.enter="loadList" />
      <button class="btn" @click="loadList">查询</button>
      <button class="btn" @click="resetFilters">重置</button>
      <button v-if="resourceType === 'hpas'" class="btn btn-primary" @click="openCreateHpa">+ 创建 HPA</button>
    </div>

    <div v-if="errorMsg" class="error-banner">⚠️ {{ errorMsg }}</div>

    <div class="panel">
      <div class="panel-head">{{ title }}</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="items.length" class="table">
          <thead>
            <tr>
              <th v-for="col in columns" :key="col.key">{{ col.label }}</th>
              <th v-if="hasAction">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="it in items" :key="rowKey(it)">
              <td v-for="col in columns" :key="col.key">
                <template v-if="col.render === 'badge'"><span class="badge" :class="badgeClass(col.key, it[col.key])">{{ it[col.key] }}</span></template>
                <template v-else-if="col.render === 'list'"><span v-for="(v, i) in (it[col.key] || [])" :key="i" class="tag-mini">{{ v }}</span><span v-if="!(it[col.key] && it[col.key].length)" class="text-muted">-</span></template>
                <template v-else-if="col.render === 'lines'"><div class="lines-cell">{{ (it[col.key] || []).join('\n') || '-' }}</div></template>
                <template v-else-if="col.render === 'count'"><span class="badge count">{{ it[col.key] ?? 0 }}</span></template>
                <template v-else>{{ it[col.key] ?? '-' }}</template>
              </td>
              <td v-if="hasAction" class="action-cell">
                <button v-if="resourceType === 'configmaps'" class="btn btn-sm" @click="openCmDetail(it)">查看</button>
                <template v-if="resourceType === 'hpas'">
                  <button class="btn btn-sm" @click="openEditHpa(it)">编辑</button>
                  <button class="btn btn-sm btn-danger" @click="deleteHpa(it)">删除</button>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">📦</div>
          <div>暂无{{ title }}数据</div>
          <div class="text-muted" style="margin-top:4px;">请确认已选择集群或检查命名空间</div>
        </div>
      </div>
    </div>

    <div v-if="showCmDialog" class="modal-overlay" @click.self="closeCmDialog">
      <div class="modal-box modal-lg">
        <h3>ConfigMap 详情 · {{ cmMeta.name }}</h3>
        <div class="cm-meta">
          <span class="badge count">集群: {{ cmMeta.cluster }}</span>
          <span class="badge count">命名空间: {{ cmMeta.namespace }}</span>
        </div>
        <div v-if="cmLoading" class="loading-state">加载中...</div>
        <div v-else class="cm-body">
          <div v-for="(row, i) in cmRows" :key="i" class="cm-row">
            <input v-model="row.key" class="input cm-key" placeholder="键" />
            <textarea v-model="row.value" class="input cm-val" rows="2" placeholder="值"></textarea>
            <button class="btn btn-sm btn-danger" @click="cmRows.splice(i, 1)">删</button>
          </div>
          <button class="btn btn-sm" @click="cmRows.push({ key: '', value: '' })">+ 新增键</button>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="closeCmDialog">取消</button>
          <button class="btn btn-primary" :disabled="cmSaving" @click="saveCm">{{ cmSaving ? '保存中...' : '保存' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showHpaDialog" class="modal-overlay" @click.self="closeHpaDialog">
      <div class="modal-box">
        <h3>{{ hpaDialogMode === 'create' ? '创建 HPA' : '编辑 HPA · ' + hpaForm.name }}</h3>
        <div v-if="hpaDialogMode === 'create'" class="form-row">
          <label>集群</label>
          <select v-model="hpaForm.cluster" class="input">
            <option value="">请选择集群</option>
            <option v-for="c in clusters" :key="c.name" :value="c.name">{{ c.name }}</option>
          </select>
        </div>
        <div v-if="hpaDialogMode === 'create'" class="form-row">
          <label>命名空间</label>
          <input v-model="hpaForm.namespace" class="input" placeholder="default" />
        </div>
        <div v-if="hpaDialogMode === 'create'" class="form-row">
          <label>HPA 名称</label>
          <input v-model="hpaForm.name" class="input" placeholder="如: web-hpa" />
        </div>
        <div v-if="hpaDialogMode === 'create'" class="form-row">
          <label>目标 Deployment</label>
          <input v-model="hpaForm.target" class="input" placeholder="如: web-deploy" />
        </div>
        <div class="form-row form-row-3">
          <div><label>最小副本</label><input v-model.number="hpaForm.min_replicas" type="number" min="1" class="input" /></div>
          <div><label>最大副本</label><input v-model.number="hpaForm.max_replicas" type="number" min="1" class="input" /></div>
          <div><label>CPU 目标利用率 (%)</label><input v-model.number="hpaForm.cpu_percent" type="number" min="1" max="100" class="input" /></div>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="closeHpaDialog">取消</button>
          <button class="btn btn-primary" :disabled="hpaSaving" @click="saveHpa">{{ hpaSaving ? '保存中...' : '保存' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const props = defineProps({
  resourceType: { type: String, required: true },
})

const TITLE_MAP = {
  statefulsets: 'StatefulSet',
  daemonsets: 'DaemonSet',
  services: 'Service',
  ingresses: 'Ingress',
  configmaps: 'ConfigMap',
  secrets: 'Secret',
  hpas: 'HPA',
  pvcs: 'PVC',
  pvs: 'PV',
}

const COLUMN_MAP = {
  statefulsets: [
    { key: 'name', label: '名称' },
    { key: 'namespace', label: '命名空间' },
    { key: 'replicas', label: '副本' },
    { key: 'ready', label: '就绪' },
    { key: 'service', label: 'Service' },
    { key: 'image', label: '镜像' },
  ],
  daemonsets: [
    { key: 'name', label: '名称' },
    { key: 'namespace', label: '命名空间' },
    { key: 'desired', label: '期望' },
    { key: 'ready', label: '就绪' },
    { key: 'node_selector', label: '节点选择' },
  ],
  services: [
    { key: 'name', label: '名称' },
    { key: 'namespace', label: '命名空间' },
    { key: 'type', label: '类型' },
    { key: 'cluster_ip', label: 'ClusterIP' },
    { key: 'ports', label: '端口' },
  ],
  ingresses: [
    { key: 'name', label: '名称' },
    { key: 'namespace', label: '命名空间' },
    { key: 'rules', label: '规则', render: 'lines' },
    { key: 'tls', label: 'TLS', render: 'list' },
  ],
  configmaps: [
    { key: 'name', label: '名称' },
    { key: 'namespace', label: '命名空间' },
    { key: 'data_count', label: '键数量', render: 'count' },
    { key: 'data_keys', label: '键列表', render: 'list' },
  ],
  secrets: [
    { key: 'name', label: '名称' },
    { key: 'namespace', label: '命名空间' },
    { key: 'type', label: '类型' },
    { key: 'data_count', label: '键数量', render: 'count' },
  ],
  hpas: [
    { key: 'name', label: '名称' },
    { key: 'namespace', label: '命名空间' },
    { key: 'min_replicas', label: '最小副本' },
    { key: 'max_replicas', label: '最大副本' },
    { key: 'current_replicas', label: '当前副本' },
    { key: 'desired_replicas', label: '期望副本' },
    { key: 'target_cpu_utilization', label: 'CPU目标%' },
    { key: 'current_cpu_utilization', label: 'CPU当前%' },
  ],
  pvcs: [
    { key: 'name', label: '名称' },
    { key: 'namespace', label: '命名空间' },
    { key: 'status', label: '状态', render: 'badge' },
    { key: 'storage', label: '容量' },
    { key: 'access_modes', label: '访问模式' },
    { key: 'volume', label: 'Volume' },
  ],
  pvs: [
    { key: 'name', label: '名称' },
    { key: 'capacity', label: '容量' },
    { key: 'access_modes', label: '访问模式' },
    { key: 'reclaim', label: '回收策略' },
    { key: 'status', label: '状态', render: 'badge' },
    { key: 'claim', label: '绑定PVC' },
  ],
}

const loading = ref(false)
const items = ref([])
const clusters = ref([])
const errorMsg = ref('')
const filters = reactive({ cluster: '', namespace: '' })

const showCmDialog = ref(false)
const cmLoading = ref(false)
const cmSaving = ref(false)
const cmMeta = reactive({ cluster: '', namespace: '', name: '' })
const cmRows = ref([])

const showHpaDialog = ref(false)
const hpaDialogMode = ref('create')
const hpaSaving = ref(false)
const hpaForm = reactive({ cluster: '', namespace: 'default', name: '', target: '', min_replicas: 1, max_replicas: 3, cpu_percent: 80 })

const title = computed(() => TITLE_MAP[props.resourceType] || props.resourceType)
const subtitle = computed(() => `${title.value} 资源列表`)
const columns = computed(() => COLUMN_MAP[props.resourceType] || [])
const hasAction = computed(() => props.resourceType === 'configmaps' || props.resourceType === 'hpas')

function rowKey(it) {
  return (it.namespace || '') + '/' + (it.name || '') + '/' + Math.random().toString(36).slice(2, 6)
}

function badgeClass(key, val) {
  if (key === 'status') {
    if (val === 'Bound' || val === 'Available') return 'green'
    if (val === 'Pending') return 'yellow'
    return 'gray'
  }
  return 'gray'
}

async function loadList() {
  loading.value = true
  errorMsg.value = ''
  try {
    const data = await request.get('/k8s/api/' + props.resourceType, { params: { cluster: filters.cluster, namespace: filters.namespace } })
    items.value = data.items || []
    clusters.value = data.clusters || []
    if (data.error) errorMsg.value = data.error
  } catch (e) {
    errorMsg.value = e.message || String(e)
    items.value = []
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filters.cluster = ''
  filters.namespace = ''
  loadList()
}

async function openCmDetail(it) {
  cmMeta.cluster = filters.cluster
  cmMeta.namespace = it.namespace
  cmMeta.name = it.name
  showCmDialog.value = true
  cmLoading.value = true
  cmRows.value = []
  try {
    const data = await request.get(`/k8s/api/configmaps/${cmMeta.cluster}/${cmMeta.namespace}/${cmMeta.name}`)
    const obj = data.data || {}
    cmRows.value = Object.keys(obj).map(k => ({ key: k, value: obj[k] }))
  } catch (e) {
    ElMessage.error('加载详情失败: ' + (e.message || e))
  } finally {
    cmLoading.value = false
  }
}

function closeCmDialog() {
  showCmDialog.value = false
  cmRows.value = []
}

async function saveCm() {
  const data = {}
  for (const r of cmRows.value) {
    if (r.key) data[r.key] = r.value
  }
  cmSaving.value = true
  try {
    await request.post(`/k8s/api/configmaps/${cmMeta.cluster}/${cmMeta.namespace}/${cmMeta.name}/update`, { data })
    ElMessage.success('已保存')
    closeCmDialog()
    loadList()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.message || e))
  } finally {
    cmSaving.value = false
  }
}

function openCreateHpa() {
  hpaDialogMode.value = 'create'
  hpaForm.cluster = filters.cluster || (clusters.value[0]?.name || '')
  hpaForm.namespace = filters.namespace || 'default'
  hpaForm.name = ''
  hpaForm.target = ''
  hpaForm.min_replicas = 1
  hpaForm.max_replicas = 3
  hpaForm.cpu_percent = 80
  showHpaDialog.value = true
}

function openEditHpa(it) {
  hpaDialogMode.value = 'edit'
  hpaForm.cluster = filters.cluster
  hpaForm.namespace = it.namespace
  hpaForm.name = it.name
  hpaForm.target = ''
  hpaForm.min_replicas = it.min_replicas || 1
  hpaForm.max_replicas = it.max_replicas || 3
  hpaForm.cpu_percent = (typeof it.target_cpu_utilization === 'number' ? it.target_cpu_utilization : 80)
  showHpaDialog.value = true
}

function closeHpaDialog() {
  showHpaDialog.value = false
}

async function saveHpa() {
  if (hpaDialogMode.value === 'create') {
    if (!hpaForm.cluster || !hpaForm.name || !hpaForm.target) {
      ElMessage.warning('请填写集群、HPA 名称、目标 Deployment')
      return
    }
  }
  hpaSaving.value = true
  try {
    if (hpaDialogMode.value === 'create') {
      await request.post('/k8s/api/hpas/create', {
        cluster: hpaForm.cluster,
        namespace: hpaForm.namespace || 'default',
        name: hpaForm.name,
        target: hpaForm.target,
        min_replicas: hpaForm.min_replicas,
        max_replicas: hpaForm.max_replicas,
        cpu_percent: hpaForm.cpu_percent,
      })
    } else {
      await request.post(`/k8s/api/hpas/${hpaForm.cluster}/${hpaForm.namespace}/${hpaForm.name}/update`, {
        min_replicas: hpaForm.min_replicas,
        max_replicas: hpaForm.max_replicas,
        cpu_percent: hpaForm.cpu_percent,
      })
    }
    ElMessage.success(hpaDialogMode.value === 'create' ? '已创建' : '已更新')
    closeHpaDialog()
    loadList()
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.message || e))
  } finally {
    hpaSaving.value = false
  }
}

async function deleteHpa(it) {
  try {
    await ElMessageBox.confirm(`确认删除 HPA「${it.name}」？`, '删除确认', { type: 'warning' })
    await request.post(`/k8s/api/hpas/${filters.cluster}/${it.namespace}/${it.name}/delete`)
    ElMessage.success('已删除')
    loadList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

watch(() => props.resourceType, () => {
  items.value = []
  loadList()
})

onMounted(loadList)
</script>

<style scoped>
.k8s-list-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.toolbar select { padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; }
.ns-input { width: 220px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; transition: all 0.2s; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.error-banner { background: rgba(239,68,68,0.1); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); border-radius: 8px; padding: 10px 14px; margin-bottom: 14px; font-size: 0.82rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); vertical-align: top; }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.text-muted { color: var(--text-tertiary, #94a3b8); font-size: 0.78rem; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; background: rgba(100,116,139,0.1); color: #64748b; }
.badge.green { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.yellow { background: rgba(245,158,11,0.1); color: #f59e0b; }
.badge.count { background: rgba(99,102,241,0.1); color: var(--accent, #6366f1); }
.tag-mini { display: inline-block; padding: 1px 6px; border-radius: 4px; background: rgba(99,102,241,0.08); color: var(--accent, #6366f1); font-size: 0.7rem; margin-right: 4px; margin-bottom: 2px; }
.lines-cell { white-space: pre-line; font-size: 0.78rem; color: var(--text-secondary, #64748b); max-width: 360px; }
.action-cell { white-space: nowrap; }
.action-cell .btn { margin-right: 4px; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 380px; max-width: 92vw; box-shadow: 0 8px 24px rgba(0,0,0,0.15); max-height: 88vh; overflow-y: auto; }
.modal-lg { min-width: 640px; }
.modal-box h3 { margin: 0 0 12px; font-size: 1rem; color: var(--text, #1e293b); }
.cm-meta { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.cm-body { margin-bottom: 12px; }
.cm-row { display: flex; gap: 8px; margin-bottom: 8px; align-items: flex-start; }
.cm-key { width: 200px; flex-shrink: 0; }
.cm-val { flex: 1; font-family: ui-monospace, monospace; font-size: 0.78rem; resize: vertical; }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.form-row-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
