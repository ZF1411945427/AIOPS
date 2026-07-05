<template>
  <div class="topology-page">
    <div class="page-header">
      <h1>拓扑视图</h1>
      <p>资产关系网络可视化 · {{ nodes.length }} 个节点 / {{ relations.length }} 条关系</p>
    </div>

    <div class="stat-row">
      <div class="stat-card">
        <div class="stat-num">{{ nodes.length }}</div>
        <div class="stat-label">节点数</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ relations.length }}</div>
        <div class="stat-label">关系数</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ abnormalCount }}</div>
        <div class="stat-label">异常节点</div>
      </div>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="openCreate">+ 新增关系</button>
      <button class="btn" @click="loadAll">刷新</button>
    </div>

    <div class="content-grid">
      <div class="panel chart-panel">
        <div class="panel-head">拓扑图</div>
        <div class="panel-body">
          <div v-if="loading" class="loading-state">加载中...</div>
          <div ref="chartRef" class="chart-box"></div>
        </div>
      </div>

      <div class="panel legend-panel">
        <div class="panel-head">图例</div>
        <div class="panel-body">
          <div class="legend-section">节点类型</div>
          <div v-for="(color, type) in typeColors" :key="type" class="legend-item">
            <span class="legend-dot" :style="{ background: color }"></span>{{ type }}
          </div>
          <div class="legend-section">状态</div>
          <div class="legend-item"><span class="legend-dot green"></span>正常</div>
          <div class="legend-item"><span class="legend-dot red-border"></span>异常</div>

          <div v-if="selectedNode" class="node-detail">
            <div class="legend-section">节点详情</div>
            <div class="detail-row"><span class="dlabel">名称</span><span class="dvalue">{{ selectedNode.name }}</span></div>
            <div class="detail-row"><span class="dlabel">类型</span><span class="dvalue">{{ selectedNode.ci_type || selectedNode.type || '-' }}</span></div>
            <div class="detail-row"><span class="dlabel">状态</span><span class="dvalue">{{ selectedNode.status || '-' }}</span></div>
            <div class="detail-row"><span class="dlabel">IP</span><span class="dvalue">{{ selectedNode.ip || '-' }}</span></div>
            <div class="detail-row"><span class="dlabel">ID</span><span class="dvalue">{{ selectedNode.id }}</span></div>
            <button class="btn btn-sm" @click="selectedNode = null" style="margin-top:8px;">关闭</button>
          </div>
        </div>
      </div>
    </div>

    <div class="panel" style="margin-top:14px;">
      <div class="panel-head">关系列表</div>
      <div class="panel-body">
        <table v-if="relations.length" class="table">
          <thead>
            <tr><th>ID</th><th>源节点</th><th>目标节点</th><th>关系类型</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in relations" :key="r.id">
              <td>{{ r.id }}</td>
              <td>{{ nodeName(r.source_id) }}</td>
              <td>{{ nodeName(r.target_id) }}</td>
              <td><span class="badge rel-type">{{ r.relation_type }}</span></td>
              <td><button class="btn btn-sm btn-danger" @click="deleteRelation(r)">删除</button></td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">🕸️</div><div>暂无关系</div></div>
      </div>
    </div>

    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal-box">
        <h3>新增关系</h3>
        <div class="form-row"><label>源节点</label>
          <select v-model="createForm.source_id" class="input">
            <option v-for="n in nodes" :key="n.id" :value="n.id">{{ n.name }} ({{ n.ci_type || n.type || '-' }})</option>
          </select>
        </div>
        <div class="form-row"><label>目标节点</label>
          <select v-model="createForm.target_id" class="input">
            <option v-for="n in nodes" :key="n.id" :value="n.id">{{ n.name }} ({{ n.ci_type || n.type || '-' }})</option>
          </select>
        </div>
        <div class="form-row"><label>关系类型</label><input v-model="createForm.relation_type" class="input" placeholder="如: depends_on"></div>
        <div class="modal-actions">
          <button class="btn" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" @click="createRelation">确认</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick, computed } from 'vue'
import * as echarts from 'echarts'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const nodes = ref([])
const relations = ref([])
const selectedNode = ref(null)
const showCreate = ref(false)
const createForm = ref({ source_id: 0, target_id: 0, relation_type: 'depends_on' })

const chartRef = ref(null)
let chart = null

const typeColors = {
  host: '#409EFF',
  server: '#409EFF',
  service: '#67C23A',
  database: '#E6A23C',
  middleware: '#9B59B6',
  network: '#00C9A7',
  default: '#909399',
}

function nodeColor(n) {
  const t = (n.ci_type || n.type || '').toLowerCase()
  return typeColors[t] || typeColors.default
}

function isAbnormal(n) {
  const s = (n.status || '').toLowerCase()
  return s === 'offline' || s === 'error' || s === 'critical' || s === 'down'
}

const abnormalCount = computed(() => nodes.value.filter(isAbnormal).length)

function nodeName(id) {
  const n = nodes.value.find(x => x.id === id)
  return n ? n.name : `#${id}`
}

async function loadAll() {
  loading.value = true
  try {
    const data = await request.get('/topology/api/list')
    nodes.value = data.nodes || []
    relations.value = data.relations || data.edges || []
    await nextTick()
    renderChart()
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

function renderChart() {
  if (!chartRef.value) return
  if (!chart) chart = echarts.init(chartRef.value)
  const nodeMap = new Map(nodes.value.map(n => [n.id, n]))
  const categories = Object.keys(typeColors).filter(k => k !== 'default')
  const graphNodes = nodes.value.map(n => ({
    id: String(n.id),
    name: n.name,
    symbolSize: 38,
    category: categories.indexOf((n.ci_type || n.type || '').toLowerCase()) >= 0
      ? (n.ci_type || n.type || '').toLowerCase() : 'default',
    itemStyle: {
      color: nodeColor(n),
      borderColor: isAbnormal(n) ? '#ef4444' : 'transparent',
      borderWidth: isAbnormal(n) ? 3 : 0,
    },
    label: { show: true, position: 'bottom', fontSize: 10 },
    raw: n,
  }))
  const graphEdges = relations.value.map(r => ({
    source: String(r.source_id),
    target: String(r.target_id),
    label: { show: false, formatter: r.relation_type, fontSize: 9 },
  }))
  chart.setOption({
    tooltip: {
      formatter: (p) => {
        if (p.dataType === 'node') {
          const n = p.data.raw
          return `<b>${n.name}</b><br/>类型: ${n.ci_type || n.type || '-'}<br/>状态: ${n.status || '-'}<br/>IP: ${n.ip || '-'}`
        }
        if (p.dataType === 'edge') {
          return `${nodeName(Number(p.data.source))} → ${nodeName(Number(p.data.target))}`
        }
        return ''
      },
    },
    legend: [{ data: categories, bottom: 0, textStyle: { fontSize: 10 } }],
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      data: graphNodes,
      links: graphEdges,
      categories: categories.map(c => ({ name: c })),
      force: { repulsion: 220, edgeLength: 120, gravity: 0.08 },
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: 8,
      lineStyle: { color: '#aaa', curveness: 0.1 },
      emphasis: { focus: 'adjacency', lineStyle: { width: 3 } },
    }],
  }, true)
  chart.off('click')
  chart.on('click', (p) => {
    if (p.dataType === 'node' && p.data.raw) {
      selectedNode.value = p.data.raw
    }
  })
}

function openCreate() {
  if (!nodes.value.length) {
    ElMessage.warning('暂无节点可建立关系')
    return
  }
  createForm.value = {
    source_id: nodes.value[0].id,
    target_id: nodes.value[1]?.id || nodes.value[0].id,
    relation_type: 'depends_on',
  }
  showCreate.value = true
}

async function createRelation() {
  if (!createForm.value.source_id || !createForm.value.target_id) {
    ElMessage.warning('请选择源节点和目标节点')
    return
  }
  if (createForm.value.source_id === createForm.value.target_id) {
    ElMessage.warning('源节点与目标节点不能相同')
    return
  }
  try {
    const data = await request.post('/topology/api/relations/create', createForm.value)
    if (data.ok === false) {
      ElMessage.error(data.error || '创建失败')
      return
    }
    ElMessage.success('关系已创建')
    showCreate.value = false
    loadAll()
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.message || e))
  }
}

async function deleteRelation(r) {
  try {
    await ElMessageBox.confirm(
      `确认删除关系「${nodeName(r.source_id)} → ${nodeName(r.target_id)}」?`,
      '删除确认',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    const data = await request.post(`/topology/api/relations/${r.id}/delete`)
    if (data.ok === false) {
      ElMessage.error(data.error || '删除失败')
      return
    }
    ElMessage.success('已删除')
    loadAll()
  } catch (e) {
    ElMessage.error('删除失败: ' + (e.message || e))
  }
}

function handleResize() {
  if (chart) chart.resize()
}

onMounted(() => {
  loadAll()
  window.addEventListener('resize', handleResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (chart) { chart.dispose(); chart = null }
})
</script>

<style scoped>
.topology-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.stat-row { display: flex; gap: 12px; margin-bottom: 14px; }
.stat-card { flex: 1; background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.stat-num { font-size: 1.5rem; font-weight: 700; color: var(--accent, #6366f1); }
.stat-label { font-size: 0.75rem; color: var(--text-secondary, #64748b); margin-top: 2px; }
.toolbar { display: flex; gap: 8px; margin-bottom: 14px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.content-grid { display: grid; grid-template-columns: 1fr 280px; gap: 14px; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); }
.panel-body { padding: 16px 18px; }
.chart-box { width: 100%; height: 480px; }
.legend-section { font-size: 0.78rem; font-weight: 600; color: var(--text-secondary, #64748b); margin: 10px 0 6px; text-transform: uppercase; letter-spacing: 0.3px; }
.legend-section:first-child { margin-top: 0; }
.legend-item { display: flex; align-items: center; gap: 8px; font-size: 0.82rem; color: var(--text, #1e293b); padding: 3px 0; }
.legend-dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
.legend-dot.green { background: #67C23A; }
.legend-dot.red-border { background: #fff; border: 2px solid #ef4444; }
.node-detail { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border, rgba(0,0,0,0.07)); }
.detail-row { display: flex; justify-content: space-between; font-size: 0.8rem; padding: 3px 0; }
.dlabel { color: var(--text-secondary, #64748b); }
.dvalue { color: var(--text, #1e293b); font-weight: 500; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.badge.rel-type { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.72rem; font-weight: 600; background: rgba(99,102,241,0.1); color: var(--accent, #6366f1); }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 380px; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; color: var(--text, #1e293b); }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
