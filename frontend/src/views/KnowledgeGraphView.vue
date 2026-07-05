<template>
  <div class="kg-page">
    <div class="page-header">
      <h1>运维知识图谱</h1>
      <p>依赖关系可视化 · 力导向图</p>
    </div>

    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-icon blue">🔵</div>
        <div class="stat-body"><div class="stat-value">{{ graph.node_count || 0 }}</div><div class="stat-label">节点数</div></div>
      </div>
      <div class="stat-card">
        <div class="stat-icon indigo">🔗</div>
        <div class="stat-body"><div class="stat-value">{{ graph.edge_count || 0 }}</div><div class="stat-label">边数</div></div>
      </div>
    </div>

    <div class="legend">
      <span v-for="(color, type) in legendMap" :key="type" class="legend-item">
        <span class="legend-dot" :style="{ background: color }"></span>{{ type }}
      </span>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="(graph.nodes || []).length" ref="chartRef" class="chart-box"></div>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">🕸️</div><div>暂无图谱数据</div></div>
      </div>
    </div>

    <div v-if="showNodeDetail" class="modal-overlay" @click.self="showNodeDetail = false">
      <div class="modal-box">
        <h3>节点详情</h3>
        <div class="detail-row"><span class="detail-label">ID</span><span class="detail-val">{{ nodeDetail.id }}</span></div>
        <div class="detail-row"><span class="detail-label">名称</span><span class="detail-val">{{ nodeDetail.name }}</span></div>
        <div class="detail-row"><span class="detail-label">类型</span><span class="badge" :style="{ background: typeColor(nodeDetail.type) + '22', color: typeColor(nodeDetail.type) }">{{ nodeDetail.type || '-' }}</span></div>
        <div v-if="nodeDetail.properties" class="detail-block">
          <div class="detail-label">属性</div>
          <pre class="detail-pre">{{ formatProps(nodeDetail.properties) }}</pre>
        </div>
        <div class="modal-actions"><button class="btn" @click="showNodeDetail = false">关闭</button></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import request from '@/api/request'

const loading = ref(false)
const graph = ref({ nodes: [], edges: [], node_count: 0, edge_count: 0 })
const chartRef = ref(null)
let chart = null

const showNodeDetail = ref(false)
const nodeDetail = ref({})

const typeColorMap = {
  service: '#3b82f6',
  host: '#22c55e',
  database: '#f97316',
  middleware: '#a855f7',
  alert: '#ef4444',
  kb: '#6366f1',
  runbook: '#14b8a6',
  asset: '#0ea5e9'
}
const defaultColor = '#94a3b8'
const legendMap = typeColorMap

function typeColor(t) {
  return typeColorMap[t] || defaultColor
}

function formatProps(p) {
  if (!p) return '-'
  if (typeof p === 'string') {
    try { return JSON.stringify(JSON.parse(p), null, 2) } catch { return p }
  }
  try { return JSON.stringify(p, null, 2) } catch { return String(p) }
}

async function loadGraph() {
  loading.value = true
  try {
    const data = await request.get('/knowledge/graph/api/graph')
    graph.value = {
      nodes: data.nodes || [],
      edges: data.edges || [],
      node_count: data.node_count ?? (data.nodes || []).length,
      edge_count: data.edge_count ?? (data.edges || []).length
    }
    await nextTick()
    renderChart()
  } catch (e) {
    ElMessage.error('加载图谱失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

function renderChart() {
  if (!chartRef.value) return
  if (chart) chart.dispose()
  chart = echarts.init(chartRef.value)

  const nodes = (graph.value.nodes || []).map(n => ({
    id: String(n.id),
    name: n.name || n.label || String(n.id),
    symbolSize: 36,
    category: n.type || 'other',
    itemStyle: { color: typeColor(n.type) },
    raw: n
  }))

  const edges = (graph.value.edges || []).map(e => ({
    source: String(e.source ?? e.from ?? e.source_id),
    target: String(e.target ?? e.to ?? e.target_id),
    label: { show: true, formatter: e.relation || e.relation_type || e.label || '', fontSize: 10, color: '#94a3b8' },
    lineStyle: { color: '#cbd5e1', curveness: 0.1 }
  }))

  const categories = Object.keys(typeColorMap).map(t => ({ name: t }))

  chart.setOption({
    tooltip: {
      formatter: (p) => {
        if (p.dataType === 'node') {
          const n = p.data.raw || {}
          return `<b>${n.name || p.name}</b><br/>类型: ${n.type || '-'}<br/>ID: ${n.id}`
        }
        if (p.dataType === 'edge') {
          return `${p.data.source} → ${p.data.target}<br/>${p.data.label?.formatter || ''}`
        }
        return p.name
      }
    },
    legend: { show: false },
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      force: { repulsion: 200, edgeLength: 120, gravity: 0.1 },
      label: { show: true, position: 'right', fontSize: 11, color: '#475569' },
      edgeLabel: { show: true },
      categories,
      data: nodes,
      links: edges,
      lineStyle: { color: '#cbd5e1', width: 1, curveness: 0.1 },
      emphasis: { focus: 'adjacency', lineStyle: { width: 2 } }
    }]
  })

  chart.off('click')
  chart.on('click', (params) => {
    if (params.dataType === 'node' && params.data?.raw) {
      nodeDetail.value = params.data.raw
      showNodeDetail.value = true
    }
  })

  window.addEventListener('resize', handleResize)
}

function handleResize() {
  chart && chart.resize()
}

onMounted(loadGraph)
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (chart) { chart.dispose(); chart = null }
})
</script>

<style scoped>
.kg-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.stat-cards { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 12px; }
.stat-card { display: flex; align-items: center; gap: 12px; padding: 14px 16px; background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.stat-icon { width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 20px; }
.stat-icon.blue { background: rgba(59,130,246,0.12); }
.stat-icon.indigo { background: rgba(99,102,241,0.12); }
.stat-value { font-size: 1.4rem; font-weight: 700; color: var(--text, #1e293b); }
.stat-label { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.legend { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; padding: 8px 12px; background: var(--bg-card, #fff); border-radius: 8px; border: 1px solid var(--border, rgba(0,0,0,0.07)); }
.legend-item { display: flex; align-items: center; gap: 6px; font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.legend-dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.chart-box { width: 100%; height: 600px; }
.loading-state, .empty-state { text-align: center; padding: 40px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 400px; max-width: 90vw; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; color: var(--text, #1e293b); }
.detail-row { display: flex; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-size: 0.85rem; }
.detail-label { min-width: 80px; color: var(--text-secondary, #64748b); font-size: 0.78rem; }
.detail-val { color: var(--text, #1e293b); }
.detail-block { margin: 10px 0; }
.detail-pre { margin-top: 4px; padding: 10px; background: var(--bg-hover, rgba(0,0,0,0.03)); border-radius: 6px; font-size: 0.75rem; white-space: pre-wrap; max-height: 240px; overflow-y: auto; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
</style>
