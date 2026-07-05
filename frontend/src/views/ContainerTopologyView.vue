<template>
  <div class="topo-page">
    <div class="page-header">
      <h1>K8s 资源拓扑</h1>
      <p>多集群资源关系力导向图 · {{ stats.total || 0 }} 节点 / {{ stats.link_count || 0 }} 关系</p>
    </div>

    <div class="stat-row">
      <div class="stat-card grad-indigo"><div class="stat-num">{{ stats.cluster_count || 0 }}</div><div class="stat-label">集群</div></div>
      <div class="stat-card grad-green"><div class="stat-num">{{ typeCount('node') }}</div><div class="stat-label">节点</div></div>
      <div class="stat-card grad-blue"><div class="stat-num">{{ typeCount('namespace') }}</div><div class="stat-label">命名空间</div></div>
      <div class="stat-card grad-amber"><div class="stat-num">{{ typeCount('deployment') }}</div><div class="stat-label">Deployment</div></div>
      <div class="stat-card grad-teal"><div class="stat-num">{{ typeCount('pod') }}</div><div class="stat-label">Pod</div></div>
      <div class="stat-card grad-violet"><div class="stat-num">{{ typeCount('service') }}</div><div class="stat-label">Service</div></div>
      <div class="stat-card grad-red"><div class="stat-num">{{ stats.abnormal_count || 0 }}</div><div class="stat-label">异常</div></div>
    </div>

    <div class="topo-wrap">
      <div class="graph-area">
        <div class="graph-toolbar">
          <button class="btn btn-sm" @click="zoom(1.2)">放大</button>
          <button class="btn btn-sm" @click="zoom(0.8)">缩小</button>
          <button class="btn btn-sm" @click="reset">重置</button>
          <button class="btn btn-sm" @click="loadGraph">刷新</button>
        </div>
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-if="errorMsg" class="error-state">{{ errorMsg }}</div>
        <div ref="chartRef" class="chart-box"></div>
      </div>

      <div class="side-panel">
        <div class="legend-block">
          <div class="legend-title">节点类型</div>
          <div class="legend-list">
            <div v-for="t in nodeTypeList" :key="t.type" class="legend-item">
              <span class="legend-dot" :style="{ background: t.color }"></span>
              <span class="legend-text">{{ typeLabel(t.type) }}</span>
              <span class="legend-count">{{ t.count }}</span>
            </div>
          </div>
        </div>
        <div class="legend-block">
          <div class="legend-title">关系类型</div>
          <div class="legend-list">
            <div class="legend-item">
              <span class="legend-line" style="background:#6366f1"></span>
              <span class="legend-text">owns 拥有</span>
            </div>
            <div class="legend-item">
              <span class="legend-line" style="background:#10b981"></span>
              <span class="legend-text">scheduled_on 调度</span>
            </div>
            <div class="legend-item">
              <span class="legend-line" style="background:#f59e0b"></span>
              <span class="legend-text">selects 选择</span>
            </div>
          </div>
        </div>

        <div v-if="selectedNode" class="detail-block">
          <div class="detail-head">
            <span class="detail-name">{{ selectedNode.name }}</span>
            <span class="badge" :style="{ background: typeColor(selectedNode.ci_type) + '22', color: typeColor(selectedNode.ci_type) }">{{ typeLabel(selectedNode.ci_type) }}</span>
            <span v-if="selectedNode.abnormal" class="badge badge-red">异常</span>
          </div>
          <div class="detail-body">
            <div class="detail-row"><span class="dk">全名</span><span class="dv">{{ selectedNode.full_name }}</span></div>
            <div class="detail-row"><span class="dk">集群</span><span class="dv">{{ selectedNode.cluster || '-' }}</span></div>
            <div class="detail-row"><span class="dk">状态</span><span class="dv">{{ selectedNode.status || '-' }}</span></div>
            <div v-for="(v, k) in selectedNode.attrs" :key="k" class="detail-row">
              <span class="dk">{{ k }}</span>
              <span class="dv">{{ formatVal(v) }}</span>
            </div>
          </div>
        </div>
        <div v-else class="detail-empty">点击节点查看详情</div>
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
const errorMsg = ref('')
const stats = ref({})
const nodes = ref([])
const links = ref([])
const selectedNode = ref(null)
const chartRef = ref(null)
let chart = null
let zoomLevel = 1

const TYPE_COLOR = {
  cluster: '#6366f1', namespace: '#3b82f6', node: '#10b981',
  deployment: '#f59e0b', statefulset: '#f97316', daemonset: '#ea580c',
  pod: '#14b8a6', service: '#8b5cf6', ingress: '#ec4899', pvc: '#64748b',
}
const TYPE_LABEL = {
  cluster: '集群', namespace: '命名空间', node: '节点',
  deployment: 'Deployment', statefulset: 'StatefulSet', daemonset: 'DaemonSet',
  pod: 'Pod', service: 'Service', ingress: 'Ingress', pvc: 'PVC',
}
const TYPE_SIZE = {
  cluster: 44, namespace: 34, node: 32, deployment: 28,
  statefulset: 26, daemonset: 26, pod: 18, service: 24, ingress: 22, pvc: 20,
}
const REL_COLOR = { owns: '#6366f1', scheduled_on: '#10b981', selects: '#f59e0b' }

function typeColor(t) { return TYPE_COLOR[t] || '#94a3b8' }
function typeLabel(t) { return TYPE_LABEL[t] || t }
function typeSize(t) { return TYPE_SIZE[t] || 20 }
function typeCount(t) { return stats.value.by_type?.[t] || 0 }

const nodeTypeList = ref([])
function buildTypeList() {
  const bt = stats.value.by_type || {}
  const order = ['cluster', 'namespace', 'node', 'deployment', 'statefulset', 'daemonset', 'pod', 'service', 'ingress', 'pvc']
  nodeTypeList.value = order.filter(t => bt[t]).map(t => ({ type: t, color: typeColor(t), count: bt[t] }))
}

function formatVal(v) {
  if (v === null || v === undefined) return '-'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

async function loadGraph() {
  loading.value = true
  errorMsg.value = ''
  try {
    const data = await request.get('/containers/topology/graph')
    nodes.value = data.nodes || []
    links.value = data.links || []
    stats.value = data.stats || {}
    buildTypeList()
    await nextTick()
    renderGraph()
  } catch (e) {
    errorMsg.value = '加载失败: ' + (e.message || e)
  } finally {
    loading.value = false
  }
}

function renderGraph() {
  if (!chartRef.value) return
  if (!chart) chart = echarts.init(chartRef.value)
  const ndata = nodes.value.map(n => ({
    id: n.id,
    name: n.name,
    value: n,
    symbolSize: typeSize(n.ci_type),
    category: n.ci_type,
    itemStyle: {
      color: typeColor(n.ci_type),
      borderColor: n.abnormal ? '#ef4444' : '#fff',
      borderWidth: n.abnormal ? 3 : 1.5,
      shadowBlur: n.abnormal ? 12 : 0,
      shadowColor: n.abnormal ? 'rgba(239,68,68,0.6)' : 'transparent',
    },
    label: { show: true, position: 'right', fontSize: 11, color: '#475569' },
  }))
  const ldata = links.value.map(l => ({
    source: l.source,
    target: l.target,
    lineStyle: { color: REL_COLOR[l.type] || '#cbd5e1', width: 1.5, curveness: 0.1, opacity: 0.7 },
    value: l.type,
  }))
  chart.setOption({
    tooltip: {
      formatter: (p) => {
        if (p.dataType === 'node') {
          const n = p.data.value || {}
          return `<b>${n.name}</b><br/>类型: ${typeLabel(n.ci_type)}<br/>集群: ${n.cluster || '-'}<br/>状态: ${n.status || '-'}${n.abnormal ? '<br/><span style="color:#ef4444">⚠ 异常</span>' : ''}`
        }
        if (p.dataType === 'edge') return `关系: ${p.data.value || ''}`
        return p.name
      },
    },
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      zoom: zoomLevel,
      data: ndata,
      links: ldata,
      force: { repulsion: 260, edgeLength: [70, 160], gravity: 0.08, layoutAnimation: true },
      emphasis: { focus: 'adjacency', label: { fontSize: 14, fontWeight: 'bold' }, lineStyle: { width: 3, opacity: 1 } },
      lineStyle: { color: '#cbd5e1', width: 1.5, curveness: 0.1 },
    }],
  }, true)
  chart.off('click')
  chart.on('click', (params) => {
    if (params.dataType === 'node') {
      selectedNode.value = params.data.value
    }
  })
}

function zoom(factor) {
  zoomLevel = Math.max(0.3, Math.min(4, zoomLevel * factor))
  if (chart) chart.setOption({ series: [{ zoom: zoomLevel }] })
}
function reset() {
  zoomLevel = 1
  selectedNode.value = null
  if (chart) chart.setOption({ series: [{ zoom: 1, center: ['50%', '50%'] }] })
}

function handleResize() { chart?.resize() }
onMounted(() => { loadGraph(); window.addEventListener('resize', handleResize) })
onBeforeUnmount(() => { window.removeEventListener('resize', handleResize); chart?.dispose(); chart = null })
</script>

<style scoped>
.topo-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.stat-row { display: grid; grid-template-columns: repeat(7, 1fr); gap: 10px; margin-bottom: 16px; }
.stat-card { border-radius: 10px; padding: 14px; color: #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.stat-num { font-size: 1.5rem; font-weight: 700; line-height: 1.2; }
.stat-label { font-size: 0.72rem; opacity: 0.9; margin-top: 2px; }
.grad-indigo { background: linear-gradient(135deg, #6366f1, #818cf8); }
.grad-green { background: linear-gradient(135deg, #10b981, #34d399); }
.grad-blue { background: linear-gradient(135deg, #3b82f6, #60a5fa); }
.grad-amber { background: linear-gradient(135deg, #f59e0b, #fbbf24); }
.grad-teal { background: linear-gradient(135deg, #14b8a6, #2dd4bf); }
.grad-violet { background: linear-gradient(135deg, #8b5cf6, #a78bfa); }
.grad-red { background: linear-gradient(135deg, #ef4444, #f87171); }
.topo-wrap { display: flex; gap: 14px; }
.graph-area { flex: 1; position: relative; background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; min-height: 560px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.graph-toolbar { position: absolute; top: 12px; left: 12px; z-index: 5; display: flex; gap: 6px; }
.btn { padding: 5px 12px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.8rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.chart-box { width: 100%; height: 560px; }
.loading-state, .error-state { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); z-index: 4; color: var(--text-secondary, #64748b); font-size: 0.9rem; }
.error-state { color: #ef4444; }
.side-panel { width: 240px; display: flex; flex-direction: column; gap: 12px; }
.legend-block { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; padding: 12px 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.legend-title { font-weight: 600; font-size: 0.82rem; color: var(--text, #1e293b); margin-bottom: 8px; }
.legend-list { display: flex; flex-direction: column; gap: 6px; }
.legend-item { display: flex; align-items: center; gap: 8px; font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.legend-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
.legend-line { width: 18px; height: 3px; border-radius: 2px; flex-shrink: 0; }
.legend-text { flex: 1; }
.legend-count { font-weight: 600; color: var(--text, #1e293b); }
.detail-block { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; padding: 12px 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); max-height: 420px; overflow-y: auto; }
.detail-head { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; }
.detail-name { font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); word-break: break-all; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge-red { background: rgba(239,68,68,0.1); color: #ef4444; }
.detail-body { display: flex; flex-direction: column; gap: 6px; }
.detail-row { display: flex; gap: 8px; font-size: 0.76rem; line-height: 1.5; }
.dk { width: 84px; flex-shrink: 0; color: var(--text-secondary, #64748b); }
.dv { flex: 1; color: var(--text, #1e293b); word-break: break-all; }
.detail-empty { text-align: center; padding: 24px 12px; color: var(--text-tertiary, #94a3b8); font-size: 0.82rem; background: var(--bg-card, #fff); border: 1px dashed var(--border-strong, rgba(0,0,0,0.12)); border-radius: 10px; }
</style>
