<template>
  <div class="path-page">
    <div class="page-header">
      <h1>路径查询</h1>
      <p>查找资产之间的连通路径 · BFS 最短路径算法</p>
    </div>

    <div class="panel">
      <div class="panel-head">查询条件</div>
      <div class="panel-body">
        <div class="query-row">
          <div class="form-row inline">
            <label>源节点</label>
            <select v-model="sourceId" class="input">
              <option :value="0">请选择</option>
              <option v-for="n in nodes" :key="n.id" :value="n.id">{{ n.name }} ({{ n.ci_type || n.type || '-' }})</option>
            </select>
          </div>
          <div class="arrow-icon">→</div>
          <div class="form-row inline">
            <label>目标节点</label>
            <select v-model="targetId" class="input">
              <option :value="0">请选择</option>
              <option v-for="n in nodes" :key="n.id" :value="n.id">{{ n.name }} ({{ n.ci_type || n.type || '-' }})</option>
            </select>
          </div>
          <button class="btn btn-primary" @click="findPath" :disabled="searching">查找路径</button>
        </div>
      </div>
    </div>

    <div class="panel" style="margin-top:14px;">
      <div class="panel-head">查询结果</div>
      <div class="panel-body">
        <div v-if="searching" class="loading-state">查询中...</div>
        <div v-else-if="errorMsg" class="empty-state"><div style="font-size:32px;margin-bottom:8px;">⚠️</div><div>{{ errorMsg }}</div></div>
        <div v-else-if="!pathResult" class="empty-state"><div style="font-size:32px;margin-bottom:8px;">🔍</div><div>请选择源节点和目标节点后查询</div></div>
        <div v-else>
          <div class="result-summary">路径长度：<b>{{ pathResult.length }}</b> 跳 · 经节点 <b>{{ pathResult.nodes.length }}</b> 个</div>

          <div class="path-list">
            <template v-for="(n, idx) in pathResult.nodes" :key="n.id">
              <div class="path-node" :class="nodeStatusClass(n)">
                <div class="pn-index">{{ idx + 1 }}</div>
                <div class="pn-main">
                  <div class="pn-name">{{ n.name }}</div>
                  <div class="pn-meta">
                    <span class="badge ci-type">{{ n.ci_type || n.type || '-' }}</span>
                    <span class="badge" :class="statusBadge(n.status)">{{ n.status || '-' }}</span>
                    <span v-if="n.ip" class="pn-ip">{{ n.ip }}</span>
                  </div>
                </div>
              </div>
              <div v-if="idx < pathResult.nodes.length - 1" class="path-edge">
                <span class="edge-arrow">↓</span>
                <span v-if="pathResult.edges[idx]" class="edge-type">{{ pathResult.edges[idx].relation_type }}</span>
              </div>
            </template>
          </div>

          <div class="chart-wrap">
            <div class="chart-title">路径可视化</div>
            <div ref="chartRef" class="chart-box"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const nodes = ref([])
const sourceId = ref(0)
const targetId = ref(0)
const searching = ref(false)
const pathResult = ref(null)
const errorMsg = ref('')

const chartRef = ref(null)
let chart = null

const typeColors = {
  host: '#409EFF', server: '#409EFF', service: '#67C23A',
  database: '#E6A23C', middleware: '#9B59B6', network: '#00C9A7',
  default: '#909399',
}

function nodeColor(n) {
  const t = (n.ci_type || n.type || '').toLowerCase()
  return typeColors[t] || typeColors.default
}

function statusBadge(s) {
  if (!s) return 'badge-gray'
  if (s === 'online' || s === 'active') return 'badge-green'
  if (s === 'warning' || s === 'maintenance') return 'badge-orange'
  if (s === 'offline' || s === 'retired') return 'badge-red'
  return 'badge-gray'
}

function nodeStatusClass(n) {
  const s = (n.status || '').toLowerCase()
  if (s === 'offline' || s === 'error' || s === 'critical') return 'abnormal'
  return ''
}

async function loadNodes() {
  try {
    const data = await request.get('/topology/api/list')
    nodes.value = data.nodes || []
  } catch (e) {
    ElMessage.error('节点加载失败: ' + (e.message || e))
  }
}

async function findPath() {
  if (!sourceId.value || !targetId.value) {
    ElMessage.warning('请选择源节点和目标节点')
    return
  }
  searching.value = true
  errorMsg.value = ''
  pathResult.value = null
  try {
    const data = await request.post('/topology/api/path/find', {
      source_id: sourceId.value,
      target_id: targetId.value,
    })
    if (data.ok === false) {
      errorMsg.value = data.error || '查询失败'
      return
    }
    pathResult.value = data
    await nextTick()
    renderChart()
  } catch (e) {
    errorMsg.value = e.message || '查询失败'
  } finally {
    searching.value = false
  }
}

function renderChart() {
  if (!chartRef.value || !pathResult.value) return
  if (!chart) chart = echarts.init(chartRef.value)
  const result = pathResult.value
  const pathIds = new Set(result.path)
  const graphNodes = result.nodes.map((n, idx) => ({
    id: String(n.id),
    name: n.name,
    symbolSize: idx === 0 || idx === result.nodes.length - 1 ? 46 : 36,
    itemStyle: {
      color: nodeColor(n),
      borderColor: idx === 0 ? '#22c55e' : (idx === result.nodes.length - 1 ? '#ef4444' : '#6366f1'),
      borderWidth: 3,
    },
    label: { show: true, position: 'bottom', fontSize: 10 },
    raw: n,
  }))
  const graphEdges = result.edges.map((e, idx) => ({
    source: String(e.source_id),
    target: String(e.target_id),
    label: { show: true, formatter: e.relation_type, fontSize: 9 },
    lineStyle: { color: '#6366f1', width: 2, curveness: 0 },
  }))
  chart.setOption({
    tooltip: {
      formatter: (p) => {
        if (p.dataType === 'node') {
          const n = p.data.raw
          return `<b>${n.name}</b><br/>类型: ${n.ci_type || n.type || '-'}<br/>状态: ${n.status || '-'}`
        }
        return ''
      },
    },
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      data: graphNodes,
      links: graphEdges,
      force: { repulsion: 300, edgeLength: 140, gravity: 0.05 },
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: 10,
      lineStyle: { color: '#6366f1', curveness: 0 },
      emphasis: { focus: 'adjacency' },
    }],
  }, true)
}

function handleResize() {
  if (chart) chart.resize()
}

onMounted(() => {
  loadNodes()
  window.addEventListener('resize', handleResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (chart) { chart.dispose(); chart = null }
})
</script>

<style scoped>
.path-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); }
.panel-body { padding: 16px 18px; }
.query-row { display: flex; align-items: flex-end; gap: 12px; flex-wrap: wrap; }
.form-row { margin-bottom: 0; }
.form-row.inline { display: flex; flex-direction: column; min-width: 220px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.arrow-icon { font-size: 1.2rem; color: var(--text-secondary, #64748b); padding-bottom: 6px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.result-summary { font-size: 0.85rem; color: var(--text, #1e293b); margin-bottom: 14px; }
.result-summary b { color: var(--accent, #6366f1); }
.path-list { display: flex; flex-direction: column; align-items: center; padding: 12px 0; }
.path-node { display: flex; align-items: center; gap: 12px; background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; padding: 10px 16px; min-width: 320px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.path-node.abnormal { border-color: rgba(239,68,68,0.4); }
.pn-index { width: 28px; height: 28px; border-radius: 50%; background: var(--accent, #6366f1); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 0.78rem; font-weight: 600; flex-shrink: 0; }
.pn-main { flex: 1; }
.pn-name { font-size: 0.9rem; font-weight: 600; color: var(--text, #1e293b); }
.pn-meta { display: flex; gap: 6px; align-items: center; margin-top: 4px; flex-wrap: wrap; }
.pn-ip { font-size: 0.72rem; color: var(--text-secondary, #64748b); }
.path-edge { display: flex; flex-direction: column; align-items: center; padding: 4px 0; }
.edge-arrow { color: var(--accent, #6366f1); font-size: 1rem; font-weight: 700; }
.edge-type { font-size: 0.7rem; color: var(--text-secondary, #64748b); background: var(--bg-hover, rgba(0,0,0,0.03)); padding: 1px 6px; border-radius: 4px; margin-top: 2px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.72rem; font-weight: 600; }
.badge.ci-type { background: rgba(59,130,246,0.1); color: #3b82f6; }
.badge-green { background: rgba(34,197,94,0.12); color: #16a34a; }
.badge-orange { background: rgba(245,158,11,0.12); color: #d97706; }
.badge-red { background: rgba(239,68,68,0.12); color: #dc2626; }
.badge-gray { background: rgba(107,114,128,0.12); color: #4b5563; }
.chart-wrap { margin-top: 20px; }
.chart-title { font-size: 0.82rem; font-weight: 600; color: var(--text-secondary, #64748b); margin-bottom: 8px; }
.chart-box { width: 100%; height: 360px; }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
</style>
