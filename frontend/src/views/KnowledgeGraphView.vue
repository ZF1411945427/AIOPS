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
      <div class="modal-box modal-wide">
        <h3>{{ nodeDetail.name || '节点详情' }}</h3>
        <div class="detail-row"><span class="detail-label">ID</span><span class="detail-val">{{ nodeDetail.id }}</span></div>
        <div class="detail-row"><span class="detail-label">类型</span><span class="badge" :style="{ background: typeColor(nodeDetail.type) + '22', color: typeColor(nodeDetail.type) }">{{ nodeDetail.type || '-' }}</span></div>
        <div v-if="nodeDetail.ip" class="detail-row"><span class="detail-label">IP</span><span class="detail-val mono">{{ nodeDetail.ip }}</span></div>
        <div v-if="nodeDetail.status" class="detail-row"><span class="detail-label">状态</span><span class="detail-val">{{ nodeDetail.status }}</span></div>
        <div v-if="nodeDetail.alert_count > 0" class="detail-row"><span class="detail-label">告警</span><span class="detail-val" style="color:#ef4444;font-weight:700">{{ nodeDetail.alert_count }} 条活跃告警</span></div>

        <div v-if="connectedUp.length" class="detail-block">
          <div class="detail-label conn-label">⬆ 上游依赖（它依赖谁）</div>
          <div class="conn-list">
            <div v-for="n in connectedUp" :key="n.id" class="conn-item" :style="{ borderLeftColor: typeColor(n.type) }">
              <span class="conn-name">{{ n.name }}</span>
              <span class="badge sm" :style="{ background: typeColor(n.type) + '22', color: typeColor(n.type) }">{{ n.type }}</span>
            </div>
          </div>
        </div>

        <div v-if="connectedDown.length" class="detail-block">
          <div class="detail-label conn-label">⬇ 下游影响（谁依赖它）</div>
          <div class="conn-list">
            <div v-for="n in connectedDown" :key="n.id" class="conn-item" :style="{ borderLeftColor: typeColor(n.type) }">
              <span class="conn-name">{{ n.name }}</span>
              <span class="badge sm" :style="{ background: typeColor(n.type) + '22', color: typeColor(n.type) }">{{ n.type }}</span>
            </div>
          </div>
        </div>

        <div v-if="!connectedUp.length && !connectedDown.length" class="detail-block">
          <div class="detail-label" style="color:#94a3b8">暂无上下游关系</div>
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
const connectedUp = ref([])
const connectedDown = ref([])

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
    loading.value = false
    await nextTick()
    await nextTick()
    renderChart()
  } catch (e) {
    loading.value = false
    ElMessage.error('加载图谱失败: ' + (e.message || e))
  }
}

function renderChart() {
  if (!chartRef.value) { console.warn('[KG] chartRef is null'); return }
  console.log('[KG] chartRef:', chartRef.value, 'size:', chartRef.value.offsetWidth, chartRef.value.offsetHeight)
  if (chart) chart.dispose()
  chart = echarts.init(chartRef.value)

  const nodes = (graph.value.nodes || []).map(n => ({
    id: String(n.id),
    name: n.name || n.label || String(n.id),
    symbolSize: n.alert_count > 0 ? 48 : 30,
    category: n.type || 'other',
    itemStyle: { color: typeColor(n.type), borderColor: '#fff', borderWidth: 2 },
    label: { show: true, fontSize: 10, color: '#334155', formatter: (p) => p.name?.length > 12 ? p.name.slice(0, 12) + '...' : p.name },
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
    animation: true,
    animationDuration: 1500,
    animationEasingUpdate: 'quinticInOut',
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      force: { repulsion: [80, 300], edgeLength: [60, 180], gravity: 0.15, friction: 0.6 },
      label: { show: true, position: 'right', fontSize: 10, color: '#475569' },
      edgeLabel: { show: false },
      categories,
      data: nodes,
      links: edges,
      lineStyle: { color: '#cbd5e1', width: 0.8, curveness: 0.15, opacity: 0.6 },
      emphasis: { focus: 'adjacency', lineStyle: { width: 2.5 }, itemStyle: { borderWidth: 3 } }
    }]
  })
  console.log('[KG] chart rendered, nodes:', nodes.length, 'edges:', edges.length)

  chart.off('click')
  chart.on('click', (params) => {
    if (params.dataType === 'node' && params.data?.raw) {
      const clickedId = params.data.id
      nodeDetail.value = params.data.raw

      const allEdges = graph.value.edges || []
      const nodeMap = {}
      ;(graph.value.nodes || []).forEach(n => { nodeMap[String(n.id)] = n })

      connectedUp.value = allEdges
        .filter(e => String(e.target ?? e.to ?? e.target_id) === clickedId)
        .map(e => nodeMap[String(e.source ?? e.from ?? e.source_id)])
        .filter(Boolean)

      connectedDown.value = allEdges
        .filter(e => String(e.source ?? e.from ?? e.source_id) === clickedId)
        .map(e => nodeMap[String(e.target ?? e.to ?? e.target_id)])
        .filter(Boolean)

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
.chart-box { width: 100%; height: 700px; background: radial-gradient(circle at 50% 50%, rgba(99,102,241,0.03), transparent 70%); border-radius: 8px; }
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
.badge.sm { font-size: 0.65rem; padding: 1px 6px; }
.modal-wide { min-width: 480px; max-width: 560px; }
.conn-label { font-weight: 600; color: var(--text, #1e293b); margin-bottom: 6px; }
.conn-list { display: flex; flex-direction: column; gap: 4px; }
.conn-item { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-left: 3px solid #cbd5e1; background: var(--bg-hover, rgba(0,0,0,0.02)); border-radius: 0 6px 6px 0; font-size: 0.82rem; }
.conn-name { flex: 1; color: var(--text, #1e293b); font-weight: 500; }
.mono { font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
</style>
