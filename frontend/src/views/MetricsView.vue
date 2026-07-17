<template>
  <div class="metrics-page">
    <div class="page-header">
      <h1>指标监控</h1>
      <p>实时指标 · 共 <span id="metricCount">{{ allMetrics.length }}</span> 个指标</p>
    </div>

    <div class="toolbar">
      <select v-model="selectedAsset" @change="changeAsset">
        <option value="0">全部资产</option>
        <option v-for="asset in assets" :key="asset.id" :value="asset.id">{{ asset.name }}{{ asset.status === 'offline' ? '（离线）' : '' }}</option>
      </select>
    </div>

    <div v-if="offlineWarning" class="offline-warning">
      <span class="warn-icon">⚠️</span>
      <span class="warn-text">{{ offlineWarning }}</span>
      <button v-if="offlineAssetNames.length" class="warn-toggle" @click="showOfflineDetail = !showOfflineDetail">
        {{ showOfflineDetail ? '收起' : '详情' }}
      </button>
    </div>
    <div v-if="showOfflineDetail && offlineAssetNames.length" class="offline-detail">
      <span v-for="name in offlineAssetNames" :key="name" class="offline-chip">{{ name }}</span>
    </div>

    <div class="cat-tabs" id="catTabs">
      <button class="cat-tab" :class="{ active: activeCat === 'all' }" @click="filterCategory('all')">全部 <span class="cat-count">{{ allMetrics.length }}</span></button>
      <button v-for="c in CATEGORIES" :key="c.key" class="cat-tab" :class="{ active: activeCat === c.key }" @click="filterCategory(c.key)" v-show="catCounts[c.key]">
        {{ c.icon }} {{ c.label }} <span class="cat-count">{{ catCounts[c.key] }}</span>
      </button>
    </div>

    <div class="metric-grid" id="metricGrid">
      <div v-if="loading" class="loading-overlay">
        <div class="loading-spinner"></div>
        <div>正在加载指标数据...</div>
      </div>
      <template v-else>
        <div v-for="name in filteredMetrics" :key="name" class="metric-card" :data-cat="getMetricCategory(name)">
          <div class="top">
            <div class="icon">{{ getMetricIcon(name).icon }}</div>
            <div class="info">
              <div class="name" :title="name">
                {{ name }}
                <span v-if="isMetricOffline(name)" class="offline-badge" title="该指标来自离线资产">离线</span>
              </div>
              <div class="value" :class="{ loading: latestValues[name] === undefined }">
                {{ latestValues[name] !== undefined ? formatValue(latestValues[name]) : '加载中' }}
                <span class="unit" v-if="latestValues[name]?.unit">{{ latestValues[name].unit }}</span>
              </div>
              <div v-if="latestValues[name]?.timestamp" class="last-collect">
                最后采集: {{ formatTimestamp(latestValues[name].timestamp) }}
              </div>
            </div>
          </div>
          <div class="chart-wrap"><canvas :ref="el => chartCanvases[name] = el"></canvas></div>
        </div>
        <div v-if="filteredMetrics.length === 0" class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">📊</div>
          <div>暂无指标数据</div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import request from '@/api/request'
import * as echarts from 'echarts'

const CATEGORIES = [
  { key: 'cpu', label: 'CPU / 负载', icon: '⚡', pattern: /cpu|loadavg|uptime/i },
  { key: 'memory', label: '内存', icon: '🧠', pattern: /memory|swap/i },
  { key: 'disk', label: '磁盘', icon: '💿', pattern: /^disk/i },
  { key: 'network', label: '网络', icon: '📥', pattern: /^net_|^network/i },
  { key: 'docker', label: 'Docker', icon: '🐳', pattern: /docker/i },
  { key: 'k8s', label: 'Kubernetes', icon: '☸️', pattern: /deployment|node_|pod_/i },
]

const colorPalette = [
  '#6366f1','#ec4899','#14b8a6','#f97316','#8b5cf6','#06b6d4',
  '#84cc16','#ef4444','#0ea5e9','#a855f7','#22c55e','#eab308',
  '#7c3aed','#0284c7','#d946ef','#65a30d','#fb923c','#0d9488',
  '#c026d3','#16a34a','#ca8a04','#4f46e5','#0891b2','#db2777',
]

const assets = ref([])
const allMetrics = ref([])
const latestValues = ref({})
const selectedAsset = ref('0')
const activeCat = ref('all')
const loading = ref(false)
const showOfflineDetail = ref(false)

const chartCanvases = ref({})
const charts = {}

let refreshTimer = null

const catCounts = computed(() => {
  const counts = {}
  for (const n of allMetrics.value) {
    const cat = getMetricCategory(n)
    counts[cat] = (counts[cat] || 0) + 1
  }
  return counts
})

// 资产状态映射: asset_id -> status
const assetStatusMap = computed(() => {
  const m = {}
  for (const a of assets.value) m[a.id] = a.status
  return m
})

// 离线资产名列表 (去重)
const offlineAssetNames = computed(() => {
  const names = assets.value.filter(a => a.status === 'offline').map(a => a.name)
  return [...new Set(names)]
})

// 离线警告文案 — 精简版，只显示数量
const offlineWarning = computed(() => {
  if (selectedAsset.value === '0') {
    if (offlineAssetNames.value.length) {
      return `部分指标来自 ${offlineAssetNames.value.length} 个离线资产，显示的是历史数据`
    }
    return ''
  }
  const asset = assets.value.find(a => a.id == selectedAsset.value)
  if (asset && asset.status === 'offline') {
    let latest = ''
    for (const n of allMetrics.value) {
      const ts = latestValues.value[n]?.timestamp
      if (ts && (!latest || ts > latest)) latest = ts
    }
    return `资产「${asset.name}」当前离线，显示的是历史数据${latest ? '（最后采集: ' + formatTimestamp(latest) + '）' : ''}`
  }
  return ''
})

// 判断某个指标是否来自离线资产
function isMetricOffline(name) {
  const lv = latestValues.value[name]
  if (!lv || !lv.asset_id) return false
  return assetStatusMap.value[lv.asset_id] === 'offline'
}

function formatTimestamp(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  const mm = (d.getMonth() + 1).toString().padStart(2, '0')
  const dd = d.getDate().toString().padStart(2, '0')
  const hh = d.getHours().toString().padStart(2, '0')
  const mi = d.getMinutes().toString().padStart(2, '0')
  return `${mm}-${dd} ${hh}:${mi}`
}

const filteredMetrics = computed(() => {
  if (activeCat.value === 'all') return allMetrics.value
  return allMetrics.value.filter(n => getMetricCategory(n) === activeCat.value)
})

function getMetricCategory(name) {
  for (const c of CATEGORIES) {
    if (c.pattern.test(name)) return c.key
  }
  return 'other'
}

function getMetricIcon(name) {
  for (const c of CATEGORIES) {
    if (c.pattern.test(name)) return c
  }
  return { icon: '📊', label: '其他' }
}

function formatValue(lv) {
  if (lv === null || lv === undefined) return '—'
  const v = typeof lv === 'object' ? lv.value : lv
  if (v === null) return '—'
  return typeof v === 'number' ? v.toFixed(1) : v
}

async function loadAssets() {
  try {
    const data = await request.get('/assets/api/list')
    assets.value = Array.isArray(data) ? data : []
  } catch (e) {
    console.error('load assets:', e)
  }
}

async function loadMetrics() {
  loading.value = true
  try {
    const [namesRes, latestRes] = await Promise.all([
      request.get('/metrics/api/v2/names'),
      request.get('/metrics/api/v2/latest?asset_id=' + selectedAsset.value)
    ])
    const allNames = Array.isArray(namesRes) ? namesRes : []
    allMetrics.value = allNames.filter(n => latestRes[n] !== undefined)
    latestValues.value = latestRes

    await nextTick()
    loadChartData()
  } catch (e) {
    console.error('load metrics error:', e)
  } finally {
    loading.value = false
  }
}

async function loadChartData() {
  try {
    const allData = await request.get('/metrics/api/v2/range?asset_id=' + selectedAsset.value + '&hours=24')
    const grouped = {}
    allData.forEach(d => {
      if (!grouped[d.name]) grouped[d.name] = []
      grouped[d.name].push(d)
    })

    let idx = 0
    for (const name of allMetrics.value) {
      const canvas = chartCanvases.value[name]
      const data = grouped[name] || []
      if (data.length < 2 || !canvas) continue
      if (charts[name]) { charts[name].dispose(); delete charts[name] }
      charts[name] = buildChart(canvas, data, idx++)
    }
  } catch (e) {
    console.error('chart data error:', e)
  }
}

function buildChart(canvas, data, colorIdx) {
  const labels = data.map(d => {
    const t = new Date(d.time)
    return `${t.getHours().toString().padStart(2,'0')}:${t.getMinutes().toString().padStart(2,'0')}`
  })
  const values = data.map(d => d.value)
  const color = colorPalette[colorIdx % colorPalette.length]
  const chart = echarts.init(canvas, null, { renderer: 'canvas' })
  chart.setOption({
    grid: { left: 0, right: 0, top: 2, bottom: 0 },
    xAxis: { type: 'category', data: labels, show: false },
    yAxis: { type: 'value', show: false },
    series: [{
      type: 'line',
      data: values,
      smooth: true,
      symbol: 'none',
      lineStyle: { color: color, width: 1.5 },
      areaStyle: { color: color + '25' },
    }],
    animation: false,
  })
  return chart
}

function filterCategory(cat) {
  activeCat.value = cat
}

function changeAsset() {
  loadMetrics()
}

onMounted(async () => {
  await loadAssets()
  await loadMetrics()
  refreshTimer = setInterval(loadChartData, 15000)
})

onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  Object.values(charts).forEach(c => c?.dispose())
})
</script>

<style scoped>
.offline-warning {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  margin-bottom: 12px;
  background: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.3);
  border-radius: 8px;
  color: #d97706;
  font-size: 13px;
}
.warn-icon { font-size: 16px; }
.warn-toggle {
  margin-left: auto;
  padding: 2px 10px;
  border: 1px solid rgba(245, 158, 11, 0.4);
  background: transparent;
  color: #d97706;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  white-space: nowrap;
}
.warn-toggle:hover { background: rgba(245, 158, 11, 0.15); }
.offline-detail {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 16px;
  margin-bottom: 12px;
  background: rgba(239, 68, 68, 0.05);
  border-radius: 8px;
}
.offline-chip {
  padding: 2px 8px;
  font-size: 12px;
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
  border-radius: 4px;
}
.offline-badge {
  display: inline-block;
  padding: 1px 6px;
  margin-left: 6px;
  font-size: 11px;
  background: rgba(239, 68, 68, 0.12);
  color: #ef4444;
  border-radius: 4px;
  vertical-align: middle;
}
.last-collect {
  font-size: 11px;
  color: var(--text-secondary, #94a3b8);
  margin-top: 2px;
}
.metrics-page {
  padding: 20px;
}
.page-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 16px;
}
.page-header h1 {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.page-header p {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}
.toolbar {
  margin-bottom: 16px;
}
.toolbar select {
  padding: 8px 14px;
  border-radius: 8px;
  border: 1px solid rgba(148,163,184,0.2);
  background: var(--card-bg);
  color: var(--text-primary);
  font-size: 13px;
  min-width: 160px;
  cursor: pointer;
}
.cat-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}
.cat-tab {
  padding: 6px 14px;
  border-radius: 20px;
  border: 1px solid rgba(148,163,184,0.2);
  background: var(--card-bg);
  color: var(--text-secondary);
  font-size: 0.78rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
}
.cat-tab:hover {
  border-color: var(--primary-light);
  color: var(--primary-light);
  background: rgba(129,140,248,0.06);
}
.cat-tab.active {
  border-color: var(--primary);
  background: var(--primary);
  color: #fff;
}
.cat-tab .cat-count {
  display: inline-block;
  margin-left: 4px;
  font-size: 0.7rem;
  opacity: 0.7;
}
.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
  position: relative;
  min-height: 200px;
}
.loading-overlay {
  grid-column: 1/-1;
  text-align: center;
  padding: 60px 0;
  color: var(--text-muted);
}
.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(148,163,184,0.2);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto 12px;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.empty-state {
  grid-column: 1/-1;
  text-align: center;
  padding: 60px 0;
  color: var(--text-muted);
}
.metric-card {
  background: var(--card-bg);
  border: 1px solid rgba(148,163,184,0.12);
  border-radius: 12px;
  padding: 16px;
  position: relative;
  overflow: hidden;
  transition: all 0.2s;
}
.metric-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; height: 2px;
  background: var(--primary-light);
  opacity: 0;
  transition: opacity 0.2s;
}
.metric-card:hover {
  border-color: rgba(148,163,184,0.25);
  transform: translateY(-1px);
}
.metric-card:hover::before {
  opacity: 1;
}
.metric-card .top {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.metric-card .icon {
  font-size: 1.2rem;
  width: 38px;
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: rgba(129,140,248,0.1);
  flex-shrink: 0;
}
.metric-card .info {
  flex: 1;
  min-width: 0;
}
.metric-card .name {
  font-size: 0.75rem;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.metric-card .value {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
}
.metric-card .value.loading {
  color: var(--text-muted);
  font-size: 1rem;
}
.metric-card .unit {
  font-size: 0.75rem;
  color: var(--text-secondary);
  font-weight: 400;
}
.metric-card .chart-wrap {
  position: relative;
  width: 100%;
  height: 130px;
}
.metric-card .chart-wrap canvas {
  width: 100% !important;
  height: 100% !important;
}
</style>
