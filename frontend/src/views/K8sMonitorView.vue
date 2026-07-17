<template>
  <div class="k8s-monitor-page">
    <div class="page-header">
      <h1>K8s 监控</h1>
      <p>Kubernetes 集群资源监控 · {{ cluster || '全部集群' }}</p>
    </div>

    <div class="toolbar">
      <select v-model="cluster" @change="loadMonitor">
        <option value="">全部集群</option>
        <option v-for="c in clusters" :key="c.name" :value="c.name">{{ c.name }}</option>
      </select>
      <select v-model="hours" @change="loadMonitor">
        <option :value="1">最近 1 小时</option>
        <option :value="3">最近 3 小时</option>
        <option :value="6">最近 6 小时</option>
        <option :value="12">最近 12 小时</option>
        <option :value="24">最近 24 小时</option>
      </select>
      <button class="btn" @click="loadMonitor">刷新</button>
      <span v-if="clusterInfo" class="cluster-info-tag">{{ clusterInfo.name }} · {{ clusterInfo.status }} · {{ clusterInfo.last_scraped_at || '-' }}</span>
    </div>

    <div class="stat-cards">
      <div class="stat-card stat-blue">
        <div class="stat-icon">🖥️</div>
        <div class="stat-body"><div class="stat-value">{{ stats.node_count || 0 }}</div><div class="stat-label">节点</div></div>
      </div>
      <div class="stat-card stat-purple">
        <div class="stat-icon">📦</div>
        <div class="stat-body"><div class="stat-value">{{ stats.pod_count || 0 }}</div><div class="stat-label">Pod（运行 {{ stats.running_pods || 0 }}）</div></div>
      </div>
      <div class="stat-card stat-orange">
        <div class="stat-icon">🚀</div>
        <div class="stat-body"><div class="stat-value">{{ stats.dep_count || 0 }}</div><div class="stat-label">Deployment</div></div>
      </div>
    </div>

    <div v-if="loading" class="panel"><div class="panel-body"><div class="loading-state">加载中...</div></div></div>

    <template v-else>
      <div v-if="hasSeries" class="charts-grid">
        <div class="chart-panel">
          <div class="chart-head">CPU 使用率（节点）</div>
          <div class="chart-body">
            <div ref="cpuChartRef" class="chart-canvas"></div>
            <div v-if="!seriesLen('cpu')" class="chart-empty">暂无 CPU 数据</div>
          </div>
        </div>
        <div class="chart-panel">
          <div class="chart-head">内存使用率（节点）</div>
          <div class="chart-body">
            <div ref="memChartRef" class="chart-canvas"></div>
            <div v-if="!seriesLen('memory')" class="chart-empty">暂无内存数据</div>
          </div>
        </div>
        <div class="chart-panel">
          <div class="chart-head">Pod 重启次数</div>
          <div class="chart-body">
            <div ref="restartChartRef" class="chart-canvas"></div>
            <div v-if="!seriesLen('restarts')" class="chart-empty">暂无重启数据</div>
          </div>
        </div>
      </div>

      <div v-else class="panel">
        <div class="panel-body">
          <div class="empty-state">
            <div style="font-size:36px;margin-bottom:8px;">📊</div>
            <div>暂无监控时序数据</div>
            <div class="text-muted" style="margin-top:4px;">请确认已配置采集任务并产生 MetricRecord</div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import request from '@/api/request'

const loading = ref(false)
const clusters = ref([])
const cluster = ref('')
const hours = ref(1)
const stats = reactive({ node_count: 0, pod_count: 0, dep_count: 0, running_pods: 0 })
const nodeSeries = ref({})
const podSeries = ref({})
const clusterInfo = ref(null)

const cpuChartRef = ref(null)
const memChartRef = ref(null)
const restartChartRef = ref(null)
let cpuChart = null, memChart = null, restartChart = null

const hasSeries = computed(() => seriesLen('cpu') || seriesLen('memory') || seriesLen('restarts') || seriesLen('replicas'))
function seriesLen(k) {
  if (k === 'cpu' || k === 'memory') return (nodeSeries.value[k] || []).length
  return (podSeries.value[k] || []).length
}

async function loadMonitor() {
  loading.value = true
  try {
    const data = await request.get('/k8s-monitor/api/list', { params: { cluster: cluster.value, hours: hours.value } })
    clusters.value = data.clusters || []
    stats.node_count = data.node_count || 0
    stats.pod_count = data.pod_count || 0
    stats.dep_count = data.dep_count || 0
    stats.running_pods = data.running_pods || 0
    nodeSeries.value = data.node_series || {}
    podSeries.value = data.pod_series || {}
    clusterInfo.value = data.cluster_info || null
    await nextTick()
    renderCharts()
  } catch (e) {
    ElMessage.error('加载监控数据失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

function fmtTime(t) {
  if (!t) return ''
  const d = new Date(t)
  const hh = d.getHours().toString().padStart(2, '0')
  const mi = d.getMinutes().toString().padStart(2, '0')
  return `${hh}:${mi}`
}

function buildLineOption(points, color, unit) {
  const labels = points.map(p => fmtTime(p.t))
  const values = points.map(p => Number(p.v))
  return {
    tooltip: { trigger: 'axis', formatter: (ps) => `${ps[0].axisValue}<br/>${ps[0].data}${unit || ''}` },
    grid: { left: 40, right: 16, top: 16, bottom: 28 },
    xAxis: { type: 'category', data: labels, axisLabel: { fontSize: 10, color: '#94a3b8' }, axisLine: { lineStyle: { color: 'rgba(0,0,0,0.1)' } } },
    yAxis: { type: 'value', axisLabel: { fontSize: 10, color: '#94a3b8' }, splitLine: { lineStyle: { color: 'rgba(0,0,0,0.06)' } } },
    series: [{
      type: 'line', data: values, smooth: true, symbol: 'circle', symbolSize: 4,
      lineStyle: { color, width: 2 },
      itemStyle: { color },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: color + '55' },
        { offset: 1, color: color + '05' },
      ]) },
    }],
  }
}

function renderCharts() {
  const cpuPts = nodeSeries.value.cpu || []
  if (cpuPts.length && cpuChartRef.value) {
    if (!cpuChart) cpuChart = echarts.init(cpuChartRef.value)
    cpuChart.setOption(buildLineOption(cpuPts, '#6366f1', '%'))
  }
  const memPts = nodeSeries.value.memory || []
  if (memPts.length && memChartRef.value) {
    if (!memChart) memChart = echarts.init(memChartRef.value)
    memChart.setOption(buildLineOption(memPts, '#14b8a6', '%'))
  }
  const restartPts = podSeries.value.restarts || []
  if (restartPts.length && restartChartRef.value) {
    if (!restartChart) restartChart = echarts.init(restartChartRef.value)
    restartChart.setOption(buildLineOption(restartPts, '#f97316', ''))
  }
}

function handleResize() {
  cpuChart?.resize()
  memChart?.resize()
  restartChart?.resize()
}

onMounted(() => {
  loadMonitor()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  cpuChart?.dispose()
  memChart?.dispose()
  restartChart?.dispose()
})
</script>

<style scoped>
.k8s-monitor-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.toolbar select { padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.cluster-info-tag { font-size: 0.75rem; color: var(--text-secondary, #64748b); margin-left: 8px; }
.stat-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 16px; }
.stat-card { display: flex; align-items: center; gap: 12px; border-radius: 10px; padding: 14px 16px; color: #fff; box-shadow: 0 2px 6px rgba(0,0,0,0.08); }
.stat-icon { width: 40px; height: 40px; border-radius: 10px; background: rgba(255,255,255,0.2); display: flex; align-items: center; justify-content: center; font-size: 20px; }
.stat-value { font-size: 1.4rem; font-weight: 700; }
.stat-label { font-size: 0.72rem; opacity: 0.92; }
.stat-blue { background: linear-gradient(135deg, #3b82f6, #1d4ed8); }
.stat-purple { background: linear-gradient(135deg, #8b5cf6, #6d28d9); }
.stat-orange { background: linear-gradient(135deg, #f97316, #c2410c); }
.charts-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 14px; }
.chart-panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); overflow: hidden; }
.chart-head { padding: 10px 16px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.85rem; color: var(--text, #1e293b); }
.chart-body { position: relative; padding: 8px; }
.chart-canvas { width: 100%; height: 240px; }
.chart-empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: var(--text-tertiary, #94a3b8); font-size: 0.82rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.text-muted { color: var(--text-tertiary, #94a3b8); font-size: 0.78rem; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
</style>
