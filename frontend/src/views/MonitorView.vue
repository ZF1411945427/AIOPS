<template>
  <div class="monitor-page" :class="{ 'is-fullscreen': isFullscreen }">
    <!-- Toolbar -->
    <div class="monitor-toolbar">
      <div class="toolbar-left">
        <span class="toolbar-title">实时监控看板</span>
        <el-tag size="small" :type="vmAvailable ? 'success' : 'danger'" effect="dark" class="vm-tag">
          VM {{ vmAvailable ? '在线' : '离线' }}
        </el-tag>
      </div>
      <div class="toolbar-center">
        <el-select v-model="selectedAsset" placeholder="全部资产" clearable size="small" style="width:200px" @change="onFilterChange">
          <el-option label="全部资产" :value="0" />
          <el-option v-for="a in assets" :key="a.id" :label="a.name + (a.ip ? ' ('+a.ip+')' : '')" :value="a.id" />
        </el-select>
        <el-radio-group v-model="timeRange" size="small" @change="onFilterChange">
          <el-radio-button value="1h">1h</el-radio-button>
          <el-radio-button value="6h">6h</el-radio-button>
          <el-radio-button value="24h">24h</el-radio-button>
          <el-radio-button value="7d">7d</el-radio-button>
          <el-radio-button value="30d">30d</el-radio-button>
        </el-radio-group>
      </div>
      <div class="toolbar-right">
        <el-switch v-model="autoRefresh" size="small" active-text="自动刷新" inactive-text="" style="margin-right:12px" />
        <el-button :icon="Refresh" size="small" circle @click="loadData" />
        <el-button :icon="FullScreen" size="small" circle @click="toggleFullscreen" />
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="monitor-loading"><el-icon class="is-loading" :size="32"><Loading /></el-icon><span>加载中...</span></div>

    <!-- Content -->
    <div v-else class="monitor-body">
      <!-- Row 1: Stat Cards -->
      <div class="stats-grid">
        <div v-for="card in statCards" :key="card.key" class="stat-card" @click="card.action && card.action()">
          <div class="stat-icon" :class="card.color"><el-icon :size="20"><component :is="card.icon" /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value">{{ stats[card.key] ?? '—' }}</div>
            <div class="stat-label">{{ card.label }}</div>
          </div>
        </div>
      </div>

      <!-- Row 2: Big Charts (4-column) -->
      <div class="charts-grid">
        <div class="chart-card chart-card-wide">
          <div class="chart-card-header">
            <span>CPU 使用率</span>
            <div class="chart-card-actions">
              <span class="chart-range-hint">{{ selectedAssetName ? selectedAssetName : '全部资产' }}</span>
            </div>
          </div>
          <div ref="cpuChartRef" class="chart-container" style="height:220px"></div>
        </div>
        <div class="chart-card chart-card-wide">
          <div class="chart-card-header">
            <span>内存使用率</span>
            <div class="chart-card-actions">
              <span class="chart-range-hint">{{ selectedAssetName ? selectedAssetName : '全部资产' }}</span>
            </div>
          </div>
          <div ref="memChartRef" class="chart-container" style="height:220px"></div>
        </div>
        <div class="chart-card chart-card-wide">
          <div class="chart-card-header"><span>磁盘使用率</span></div>
          <div ref="diskChartRef" class="chart-container" style="height:220px"></div>
        </div>
        <div class="chart-card chart-card-wide">
          <div class="chart-card-header"><span>系统负载</span></div>
          <div ref="loadChartRef" class="chart-container" style="height:220px"></div>
        </div>
      </div>

      <!-- Row 3: Network + Health + Alert trend -->
      <div class="charts-grid">
        <div class="chart-card chart-card-wide">
          <div class="chart-card-header"><span>网络流量</span></div>
          <div ref="netChartRef" class="chart-container" style="height:220px"></div>
        </div>
        <div class="chart-card">
          <div class="chart-card-header"><span>告警趋势</span></div>
          <div ref="alertTrendChartRef" class="chart-container" style="height:220px"></div>
        </div>
        <div class="chart-card">
          <div class="chart-card-header"><span>健康评分</span></div>
          <div ref="healthChartRef" class="chart-container" style="height:220px"></div>
        </div>
      </div>

      <!-- Row 4: Online by type + Severity distribution -->
      <div class="charts-grid">
        <div class="chart-card">
          <div class="chart-card-header"><span>在线资产类型</span></div>
          <div ref="onlineTypeChartRef" class="chart-container" style="height:220px"></div>
        </div>
        <div class="chart-card">
          <div class="chart-card-header"><span>告警级别分布</span></div>
          <div ref="severityChartRef" class="chart-container" style="height:220px"></div>
        </div>
        <div class="chart-card chart-card-wide">
          <div class="chart-card-header"><span>最新告警</span></div>
          <el-table :data="recentAlerts" style="width:100%" size="small" stripe max-height="190">
            <el-table-column prop="asset_name" label="资产" width="110" show-overflow-tooltip />
            <el-table-column prop="metric_name" label="指标" width="100" show-overflow-tooltip />
            <el-table-column label="级别" width="70">
              <template #default="{ row }"><el-tag :type="sevType(row.severity)" size="small" effect="light">{{ row.severity }}</el-tag></template>
            </el-table-column>
            <el-table-column label="状态" width="70">
              <template #default="{ row }"><el-tag :type="row.status === 'firing' ? 'danger' : 'warning'" size="small">{{ row.status }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="message" label="消息" min-width="150" show-overflow-tooltip />
          </el-table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, onBeforeUnmount, computed } from 'vue'
import { Refresh, FullScreen, Loading } from '@element-plus/icons-vue'
import {
  Monitor, CircleCheck, WarningFilled, Odometer, Coin, Connection, TrendCharts,
  Cellphone, DataBoard, SetUp
} from '@element-plus/icons-vue'
import request from '@/api/request'
import * as echarts from 'echarts'

const cpuChartRef = ref(null)
const memChartRef = ref(null)
const diskChartRef = ref(null)
const loadChartRef = ref(null)
const netChartRef = ref(null)
const alertTrendChartRef = ref(null)
const healthChartRef = ref(null)
const onlineTypeChartRef = ref(null)
const severityChartRef = ref(null)

let charts = []
const loading = ref(true)
const vmAvailable = ref(false)
const timeRange = ref('24h')
const selectedAsset = ref(0)
const selectedAssetName = ref('')
const autoRefresh = ref(false)
const isFullscreen = ref(false)
let refreshTimer = null

const stats = ref({})
const assets = ref([])
const recentAlerts = ref([])
const vmMetrics = ref({})
const alertTrend = ref([])
const severityDist = ref([])
const onlineByType = ref([])

const statCards = [
  { key: 'asset_total', label: '资产总数', icon: 'Monitor', color: 'primary' },
  { key: 'asset_online', label: '在线资产', icon: 'CircleCheck', color: 'success' },
  { key: 'alert_active', label: '活跃告警', icon: 'WarningFilled', color: 'warning' },
  { key: 'health_score', label: '系统健康分', icon: 'TrendCharts', color: 'info' },
  { key: 'rule_count', label: '告警规则', icon: 'Odometer', color: 'primary' },
  { key: 'incident_open', label: '未关闭事件', icon: 'Coin', color: 'danger' },
  { key: 'datasource_count', label: '数据源', icon: 'Connection', color: 'info' },
]

function sevType(s) {
  return { critical: 'danger', high: 'warning', warning: 'warning', low: 'success', info: 'info' }[s] || 'info'
}

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
  if (isFullscreen.value) {
    document.documentElement.requestFullscreen?.()
  } else {
    document.exitFullscreen?.()
  }
}

function onFilterChange() {
  const found = assets.value.find(a => a.id === selectedAsset.value)
  selectedAssetName.value = found ? found.name : ''
  loadData()
}

async function loadData() {
  try {
    const params = { time_range: timeRange.value, asset_id: selectedAsset.value }
    const data = await request.get('/api/dashboard/data', { params })
    stats.value = data.stats || {}
    recentAlerts.value = data.recent_alerts || []
    vmMetrics.value = data.vm_metrics || {}
    vmAvailable.value = data.vm_available || false
    alertTrend.value = data.alert_trend || []
    severityDist.value = data.severity_distribution || []
    onlineByType.value = data.online_by_type || []
    if (data.assets) {
      assets.value = data.assets
    }
    loading.value = false
    nextTick(() => {
      renderCpuChart()
      renderMemChart()
      renderDiskChart()
      renderLoadChart()
      renderNetChart()
      renderAlertTrendChart()
      renderHealthChart()
      renderOnlineTypeChart()
      renderSeverityChart()
    })
  } catch (e) {
    console.error('load monitor data:', e)
    loading.value = false
  }
}

function disposeCharts() {
  charts.forEach(c => { try { c.dispose() } catch(e) {} })
  charts = []
}

function makeChart(refName) {
  let el = null
  if (typeof refName === 'string') {
    const map = {
      cpuChartRef, memChartRef, diskChartRef, loadChartRef,
      netChartRef, alertTrendChartRef, healthChartRef,
      onlineTypeChartRef, severityChartRef
    }
    el = map[refName]?.value
  } else {
    el = refName
  }
  if (!el) return null
  const c = echarts.init(el)
  charts.push(c)
  return c
}

function renderCpuChart() {
  const chart = makeChart('cpuChartRef')
  if (!chart) return
  const data = vmMetrics.value['cpu_usage'] || []
  chart.setOption({
    tooltip: { trigger: 'axis', valueFormatter: v => v + '%' },
    grid: { left: 45, right: 16, top: 16, bottom: 24 },
    xAxis: { type: 'category', data: data.map(d => d.time.slice(5, 16)), axisLabel: { color: '#94a3b8', fontSize: 10, rotate: 30 } },
    yAxis: { type: 'value', axisLabel: { color: '#94a3b8', formatter: '{value}%' }, min: 0 },
    series: [{
      type: 'line', smooth: true, symbol: 'none',
      lineStyle: { color: '#818cf8', width: 2 },
      areaStyle: { color: 'rgba(129,140,248,0.12)' },
      data: data.map(d => d.value),
    }],
  })
}

function renderMemChart() {
  const chart = makeChart('memChartRef')
  if (!chart) return
  const data = vmMetrics.value['memory_usage'] || []
  chart.setOption({
    tooltip: { trigger: 'axis', valueFormatter: v => v + '%' },
    grid: { left: 45, right: 16, top: 16, bottom: 24 },
    xAxis: { type: 'category', data: data.map(d => d.time.slice(5, 16)), axisLabel: { color: '#94a3b8', fontSize: 10, rotate: 30 } },
    yAxis: { type: 'value', axisLabel: { color: '#94a3b8', formatter: '{value}%' }, min: 0 },
    series: [{
      type: 'line', smooth: true, symbol: 'none',
      lineStyle: { color: '#10b981', width: 2 },
      areaStyle: { color: 'rgba(16,185,129,0.12)' },
      data: data.map(d => d.value),
    }],
  })
}

function renderDiskChart() {
  const chart = makeChart('diskChartRef')
  if (!chart) return
  const data = vmMetrics.value['disk_usage'] || []
  if (data.length === 0) {
    chart.setOption({ title: { text: '暂无磁盘数据', left: 'center', top: 'center', textStyle: { color: '#94a3b8', fontSize: 13 } } })
    return
  }
  const latest = data[data.length - 1]?.value || 0
  chart.setOption({
    tooltip: { formatter: () => `磁盘使用率: ${latest}%` },
    series: [{
      type: 'gauge', center: ['50%', '55%'], radius: '75%',
      startAngle: 220, endAngle: -40,
      min: 0, max: 100,
      axisLine: { lineStyle: { width: 14, color: [[0.5, '#10b981'], [0.8, '#f59e0b'], [1, '#ef4444']] } },
      axisTick: { show: false },
      splitLine: { length: 6, lineStyle: { color: '#1e293b', width: 2 } },
      axisLabel: { color: '#94a3b8', fontSize: 9, distance: 14 },
      detail: { valueAnimation: true, formatter: '{value}%', color: '#e2e8f0', fontSize: 22, fontWeight: 700, offsetCenter: [0, '55%'] },
      title: { offsetCenter: [0, '78%'], fontSize: 11, color: '#94a3b8' },
      data: [{ value: latest, name: '磁盘' }],
    }],
  })
}

function renderLoadChart() {
  const chart = makeChart('loadChartRef')
  if (!chart) return
  const data = vmMetrics.value['loadavg_1min'] || []
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 45, right: 16, top: 16, bottom: 24 },
    xAxis: { type: 'category', data: data.map(d => d.time.slice(5, 16)), axisLabel: { color: '#94a3b8', fontSize: 10, rotate: 30 } },
    yAxis: { type: 'value', axisLabel: { color: '#94a3b8' } },
    series: [{
      type: 'bar', barWidth: '40%',
      itemStyle: { color: '#f59e0b', borderRadius: [3,3,0,0] },
      data: data.map(d => d.value),
    }],
  })
}

function renderNetChart() {
  const chart = makeChart('netChartRef')
  if (!chart) return
  const rxData = vmMetrics.value['network_rx_bytes'] || []
  const txData = vmMetrics.value['network_tx_bytes'] || []
  if (!rxData.length && !txData.length) {
    chart.setOption({ title: { text: '暂无网络流量数据', left: 'center', top: 'center', textStyle: { color: '#94a3b8', fontSize: 13 } } })
    return
  }
  const times = rxData.length ? rxData.map(d => d.time.slice(5, 16)) : txData.map(d => d.time.slice(5, 16))
  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['接收', '发送'], textStyle: { color: '#94a3b8' }, top: 0, right: 0 },
    grid: { left: 50, right: 20, top: 36, bottom: 24 },
    xAxis: { type: 'category', data: times, axisLabel: { color: '#94a3b8', fontSize: 10, rotate: 30 } },
    yAxis: { type: 'value', axisLabel: { color: '#94a3b8', formatter: v => (v / 1024).toFixed(1) + 'KB' } },
    series: [
      { name: '接收', type: 'line', smooth: true, symbol: 'none',
        lineStyle: { color: '#3b82f6', width: 2 }, areaStyle: { color: 'rgba(59,130,246,0.1)' },
        data: rxData.map(d => d.value) },
      { name: '发送', type: 'line', smooth: true, symbol: 'none',
        lineStyle: { color: '#8b5cf6', width: 2 }, areaStyle: { color: 'rgba(139,92,246,0.1)' },
        data: txData.length ? txData.map(d => d.value) : [] },
    ],
  })
}

function renderAlertTrendChart() {
  const chart = makeChart('alertTrendChartRef')
  if (!chart) return
  const data = alertTrend.value
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 16, top: 16, bottom: 30 },
    xAxis: { type: 'category', data: data.map(d => d.date.slice(5)), axisLabel: { color: '#94a3b8', fontSize: 10, rotate: 30 } },
    yAxis: { type: 'value', axisLabel: { color: '#94a3b8' } },
    series: [{
      type: 'line', smooth: true, symbol: 'circle', symbolSize: 5,
      lineStyle: { color: '#ef4444', width: 2 },
      areaStyle: { color: 'rgba(239,68,68,0.1)' },
      data: data.map(d => d.count),
    }],
  })
}

function renderHealthChart() {
  const chart = makeChart('healthChartRef')
  if (!chart) return
  const score = typeof stats.value.health_score === 'number' ? stats.value.health_score : 0
  chart.setOption({
    series: [{
      type: 'gauge', center: ['50%', '55%'], radius: '80%',
      startAngle: 220, endAngle: -40, min: 0, max: 100,
      axisLine: { lineStyle: { width: 16, color: [[0.4, '#ef4444'], [0.6, '#f59e0b'], [1, '#10b981']] } },
      axisTick: { show: false },
      splitLine: { length: 6, lineStyle: { color: '#1e293b', width: 2 } },
      axisLabel: { color: '#94a3b8', fontSize: 9, distance: 16 },
      detail: { valueAnimation: true, formatter: '{value}', color: '#e2e8f0', fontSize: 26, fontWeight: 700, offsetCenter: [0, '55%'] },
      title: { offsetCenter: [0, '78%'], fontSize: 11, color: '#94a3b8' },
      data: [{ value: score, name: '健康分' }],
    }],
  })
}

function renderOnlineTypeChart() {
  const chart = makeChart('onlineTypeChartRef')
  if (!chart) return
  const data = onlineByType.value
  if (!data.length) {
    chart.setOption({ title: { text: '暂无数据', left: 'center', top: 'center', textStyle: { color: '#94a3b8', fontSize: 13 } } })
    return
  }
  chart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [{
      type: 'pie', radius: ['40%', '65%'], avoidLabelOverlap: true,
      label: { show: true, formatter: '{b}', fontSize: 10, color: '#94a3b8' },
      emphasis: { label: { show: true, fontWeight: 'bold' } },
      data: data.map((d, i) => ({
        name: d.type, value: d.count,
        itemStyle: { color: ['#818cf8','#10b981','#f59e0b','#ef4444','#3b82f6','#8b5cf6'][i % 6] },
      })),
    }],
  })
}

function renderSeverityChart() {
  const chart = makeChart('severityChartRef')
  if (!chart) return
  const colorMap = { critical: '#ef4444', high: '#f97316', warning: '#f59e0b', info: '#3b82f6', low: '#10b981' }
  const data = severityDist.value
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 16, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: data.map(d => d.severity), axisLabel: { color: '#94a3b8' } },
    yAxis: { type: 'value', axisLabel: { color: '#94a3b8' } },
    series: [{
      type: 'bar', barWidth: '50%',
      data: data.map(d => ({
        value: d.count,
        itemStyle: { color: colorMap[d.severity] || '#818cf8', borderRadius: [4,4,0,0] },
      })),
    }],
  })
}

onMounted(() => {
  loadData()
})

onBeforeUnmount(() => {
  disposeCharts()
  if (refreshTimer) clearInterval(refreshTimer)
})

// Auto-refresh watcher
import { watch } from 'vue'
watch(autoRefresh, (val) => {
  if (refreshTimer) clearInterval(refreshTimer)
  if (val) {
    refreshTimer = setInterval(loadData, 15000)
  }
})
</script>

<style scoped>
.monitor-page {
  padding: 16px 20px;
  min-height: 100%;
  background: transparent;
  transition: all 0.3s;
}
.monitor-page.is-fullscreen {
  padding: 24px 32px;
  background: var(--bg-primary, #0f172a);
}

.monitor-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}
.toolbar-left { display: flex; align-items: center; gap: 10px; }
.toolbar-title { font-size: 18px; font-weight: 700; color: var(--text-primary); }
.toolbar-center { display: flex; align-items: center; gap: 12px; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }
.vm-tag { font-size: 11px; }

.monitor-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 0;
  gap: 12px;
  color: var(--text-muted);
}

.monitor-body {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* Stats */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 12px;
}
.stat-card {
  background: var(--card-bg);
  border-radius: 10px;
  padding: 14px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid rgba(148,163,184,0.08);
  cursor: default;
  transition: var(--transition);
}
.stat-card:hover { border-color: rgba(148,163,184,0.2); }
.stat-icon {
  width: 40px; height: 40px;
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.stat-icon.primary { background: rgba(99,102,241,0.1); color: var(--primary); }
.stat-icon.success { background: rgba(16,185,129,0.1); color: var(--success); }
.stat-icon.warning { background: rgba(245,158,11,0.1); color: var(--warning); }
.stat-icon.danger { background: rgba(239,68,68,0.1); color: var(--danger); }
.stat-icon.info { background: rgba(59,130,246,0.1); color: var(--info); }
.stat-info .stat-value { font-size: 22px; font-weight: 700; color: var(--text-primary); line-height: 1.2; }
.stat-info .stat-label { font-size: 11px; color: var(--text-secondary); margin-top: 2px; }

/* Charts */
.charts-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr 1fr;
  gap: 14px;
}
.chart-card {
  background: var(--card-bg);
  border-radius: 10px;
  padding: 14px;
  border: 1px solid rgba(148,163,184,0.08);
}
.chart-card-wide {
  grid-column: span 2;
}
.chart-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.chart-range-hint { font-size: 11px; color: var(--text-muted); font-weight: 400; }
.chart-container { width: 100%; }

@media (max-width: 1400px) {
  .stats-grid { grid-template-columns: repeat(4, 1fr); }
  .charts-grid { grid-template-columns: 1fr 1fr; }
  .chart-card-wide { grid-column: span 1; }
}
@media (max-width: 900px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
  .charts-grid { grid-template-columns: 1fr; }
}
</style>
