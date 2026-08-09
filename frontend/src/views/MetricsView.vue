<template>
  <div class="metrics-page">
    <div class="page-header">
      <h1>指标监控</h1>
      <div class="header-actions">
        <select v-model="aggregateMode" @change="onAggregateChange" class="agg-select" title="跨资产聚合方式">
          <option value="avg">平均值</option>
          <option value="sum">总和</option>
          <option value="max">最大值</option>
          <option value="min">最小值</option>
        </select>
        <button class="btn-add" @click="showCustomModal = true">+ 自定义卡片</button>
      </div>
    </div>

    <div class="toolbar">
      <select v-model="filterDomain" @change="onDomainChange">
        <option value="">全部业务域</option>
        <option v-for="d in domainList" :key="d" :value="d">{{ d }}</option>
      </select>
      <select v-model="selectedAsset" @change="changeAsset">
        <option value="0">全部资产</option>
        <option v-for="asset in filteredAssets" :key="asset.id" :value="asset.id">{{ asset.name }}{{ asset.status === 'offline' ? '（离线）' : '' }}</option>
      </select>
    </div>

    <div v-if="offlineWarning" class="offline-warning">
      <span class="warn-icon">&#9888;</span>
      <span class="warn-text">{{ offlineWarning }}</span>
      <button v-if="offlineAssetNames.length" class="warn-toggle" @click="showOfflineDetail = !showOfflineDetail">
        {{ showOfflineDetail ? '收起' : '详情' }}
      </button>
    </div>
    <div v-if="showOfflineDetail && offlineAssetNames.length" class="offline-detail">
      <span v-for="name in offlineAssetNames" :key="name" class="offline-chip">{{ name }}</span>
    </div>

    <div class="cat-tabs">
      <button class="cat-tab" :class="{ active: activeCat === 'all' }" @click="filterCategory('all')">全部 <span class="cat-count">{{ allMetrics.length }}</span></button>
      <button v-for="c in CATEGORIES" :key="c.key" class="cat-tab" :class="{ active: activeCat === c.key }" @click="filterCategory(c.key)" v-show="catCounts[c.key]">
        {{ c.icon }} {{ c.label }} <span class="cat-count">{{ catCounts[c.key] }}</span>
      </button>
    </div>

    <div class="metric-grid">
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
                <span v-if="isMetricOffline(name)" class="offline-badge">离线</span>
              </div>
              <div class="value" :class="{ loading: latestValues[name] === undefined }">
                <template v-if="isAggregateMode">
                  <span class="agg-badge">{{ aggregateMode === 'avg' ? '平均' : aggregateMode === 'sum' ? '总和' : aggregateMode === 'max' ? '最大' : '最小' }}</span>
                  {{ latestValues[name] !== undefined ? formatValue(latestValues[name]) : '加载中' }}
                  <span class="unit" v-if="latestValues[name]?.unit">{{ latestValues[name].unit }}</span>
                  <span class="count-badge" v-if="latestValues[name]?.count > 0">({{ latestValues[name].count }} 台)</span>
                </template>
                <template v-else>
                  {{ latestValues[name] !== undefined ? formatValue(latestValues[name]) : '加载中' }}
                  <span class="unit" v-if="latestValues[name]?.unit">{{ latestValues[name].unit }}</span>
                </template>
              </div>
              <div v-if="latestValues[name]?.timestamp" class="last-collect">
                最后采集: {{ formatTimestamp(latestValues[name].timestamp) }}
              </div>
            </div>
          </div>
          <div class="chart-wrap"><canvas :ref="el => setChartCanvas(name, el)"></canvas></div>
        </div>
        <div v-if="filteredMetrics.length === 0" class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">&#128202;</div>
          <div>暂无指标数据</div>
        </div>
      </template>
    </div>

    <div class="custom-section">
      <div class="custom-header">
        <h2>自定义仪表盘</h2>
      </div>
      <div v-if="!customCards.length" class="custom-empty">编写 PromQL 查询，创建自定义指标卡片，支持拖拽排列和缩放大小</div>
      <div v-else class="custom-grid" ref="customGridRef">
        <div v-for="(card, idx) in customCards" :key="card.id"
          class="custom-card"
          :style="getCustomCardStyle(card)"
          :data-order="card.order"
          draggable="true"
          @dragstart="onDragStart($event, idx)"
          @dragover.prevent="onDragOver($event, idx)"
          @drop="onDrop($event, idx)"
          @dragend="onDragEnd">
          <div class="custom-card-header">
            <span class="drag-handle" title="拖拽移动">&#x2261;</span>
            <span class="custom-card-title">{{ card.title }}</span>
            <span class="custom-card-promql-label" @click="editCustomCard(idx)">PromQL</span>
            <button class="card-btn-del" @click="deleteCustomCard(idx)" title="删除卡片">&times;</button>
          </div>
          <div class="custom-card-chart" :ref="el => setCustomChartCanvas(card.id, el)"></div>
          <div class="resize-handle" @mousedown.prevent="onResizeStart($event, idx)" title="拖拽缩放"></div>
        </div>
      </div>
    </div>

    <div v-if="showCustomModal" class="modal-overlay" @click.self="showCustomModal = false">
      <div class="modal-box">
        <h3>{{ editingCardIdx !== null ? '编辑' : '新增' }}自定义卡片</h3>
        <div class="form-group">
          <label>卡片标题</label>
          <input v-model="customForm.title" placeholder="例如: CPU 平均使用率" class="form-input" />
        </div>
        <div class="form-group">
          <label>PromQL 查询</label>
          <textarea v-model="customForm.promql" placeholder="例如: avg(cpu_usage) by (__name__)" class="form-textarea" rows="3"></textarea>
        </div>
        <div class="form-group">
          <label>时间范围</label>
          <select v-model="customForm.hours" class="form-input" style="width:auto">
            <option :value="1">最近 1 小时</option>
            <option :value="6">最近 6 小时</option>
            <option :value="24">最近 24 小时</option>
            <option :value="72">最近 3 天</option>
            <option :value="168">最近 7 天</option>
          </select>
        </div>
        <div class="form-group">
          <label>宽度</label>
          <div class="size-picker">
            <button v-for="w in [1,2,3,4]" :key="w" :class="{ active: customForm.w === w }" @click="customForm.w = w" class="size-btn">{{ w }}列</button>
          </div>
        </div>
        <div class="form-group">
          <label>高度</label>
          <div class="size-picker">
            <button v-for="h in [1,2]" :key="h" :class="{ active: customForm.h === h }" @click="customForm.h = h" class="size-btn">{{ h === 1 ? '标准' : '双倍' }}</button>
          </div>
        </div>
        <div class="form-actions">
          <button class="btn-cancel" @click="showCustomModal = false">取消</button>
          <button class="btn-save" @click="saveCustomCard">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import request from '@/api/request'
import * as echarts from 'echarts'

const CATEGORIES = [
  { key: 'cpu', label: 'CPU / 负载', icon: '\u26A1', pattern: /cpu|loadavg|uptime/i },
  { key: 'memory', label: '内存', icon: '\uD83E\uDDE0', pattern: /memory|swap/i },
  { key: 'disk', label: '磁盘', icon: '\uD83D\uDCBF', pattern: /^disk/i },
  { key: 'network', label: '网络', icon: '\uD83D\uDCE5', pattern: /^net_|^network|tcp_/i },
  { key: 'system', label: '系统', icon: '\u2699', pattern: /process_|zombie|open_files|uptime/i },
  { key: 'docker', label: 'Docker', icon: '\uD83D\uDC33', pattern: /docker/i },
  { key: 'k8s', label: 'Kubernetes', icon: '\u2601', pattern: /deployment|node_|pod_/i },
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
const filterDomain = ref('')
const domainList = ref([])
const assetDomains = ref({})
const activeCat = ref('all')
const loading = ref(false)
const showOfflineDetail = ref(false)
const aggregateMode = ref('avg')

const chartCanvases = {}
const charts = {}
const customChartCanvases = {}
const customCharts = {}

let refreshTimer = null
let dragIdx = null

const customGridRef = ref(null)

const STORAGE_KEY = 'metrics_custom_cards'
const customCards = ref([])

const showCustomModal = ref(false)
const editingCardIdx = ref(null)
const customForm = ref({ title: '', promql: '', hours: 24, w: 2, h: 1 })

const isAggregateMode = computed(() => selectedAsset.value === '0' && aggregateMode.value)

function loadCustomCards() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) customCards.value = JSON.parse(raw)
  } catch (e) { /* ignore */ }
}

function saveCustomCards() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(customCards.value))
  } catch (e) { /* ignore */ }
}

function editCustomCard(idx) {
  const card = customCards.value[idx]
  customForm.value = { title: card.title, promql: card.promql, hours: card.hours || 24, w: card.w || 2, h: card.h || 1 }
  editingCardIdx.value = idx
  showCustomModal.value = true
}

function saveCustomCard() {
  if (!customForm.value.title.trim() || !customForm.value.promql.trim()) return
  if (editingCardIdx.value !== null) {
    const card = customCards.value[editingCardIdx.value]
    Object.assign(card, { ...customForm.value, id: card.id, order: card.order })
  } else {
    const maxOrder = customCards.value.reduce((m, c) => Math.max(m, c.order || 0), -1)
    customCards.value.push({
      id: 'custom_' + Date.now(),
      title: customForm.value.title,
      promql: customForm.value.promql,
      hours: customForm.value.hours,
      w: customForm.value.w,
      h: customForm.value.h,
      order: maxOrder + 1,
    })
  }
  saveCustomCards()
  showCustomModal.value = false
  editingCardIdx.value = null
  nextTick(() => loadCustomChartData())
}

function deleteCustomCard(idx) {
  const id = customCards.value[idx]?.id
  if (customCharts[id]) { customCharts[id].dispose(); delete customCharts[id] }
  customCards.value.splice(idx, 1)
  saveCustomCards()
}

function getCustomCardStyle(card) {
  return {
    gridColumn: `span ${card.w || 2}`,
    gridRow: `span ${card.h || 1}`,
  }
}

function onDragStart(e, idx) {
  dragIdx = idx
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', idx)
}

function onDragOver(e, idx) {
  e.preventDefault()
  if (dragIdx === null || dragIdx === idx) return
  const cards = customCards.value
  const item = cards.splice(dragIdx, 1)[0]
  cards.splice(idx, 0, item)
  dragIdx = idx
  cards.forEach((c, i) => { c.order = i })
  saveCustomCards()
}

function onDrop(e, idx) {
  e.preventDefault()
  dragIdx = null
  saveCustomCards()
}

function onDragEnd() {
  dragIdx = null
}

function onResizeStart(e, idx) {
  const card = customCards.value[idx]
  if (!card) return
  const startX = e.clientX
  const startY = e.clientY
  const startW = card.w || 2
  const startH = card.h || 1
  const gridEl = customGridRef.value
  if (!gridEl) return
  const gridRect = gridEl.getBoundingClientRect()
  const colW = gridRect.width / 4

  function onMouseMove(ev) {
    const dx = ev.clientX - startX
    const dy = ev.clientY - startY
    card.w = Math.max(1, Math.min(4, Math.round(startW + dx / colW)))
    card.h = Math.max(1, Math.min(2, Math.round(startH + dy / 60)))
  }

  function onMouseUp() {
    saveCustomCards()
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  }

  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

const filteredAssets = computed(() => {
  if (!filterDomain.value) return assets.value
  return assets.value.filter(a => {
    const doms = assetDomains.value[a.id]
    return doms && doms.includes(filterDomain.value)
  })
})

const catCounts = computed(() => {
  const counts = {}
  for (const n of allMetrics.value) {
    const cat = getMetricCategory(n)
    counts[cat] = (counts[cat] || 0) + 1
  }
  return counts
})

const assetStatusMap = computed(() => {
  const m = {}
  for (const a of assets.value) m[a.id] = a.status
  return m
})

const offlineAssetNames = computed(() => {
  const names = assets.value.filter(a => a.status === 'offline').map(a => a.name)
  return [...new Set(names)]
})

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
  return { icon: '\uD83D\uDCCA', label: '其他' }
}

function formatValue(lv) {
  if (lv === null || lv === undefined) return '\u2014'
  const v = typeof lv === 'object' ? lv.value : lv
  if (v === null) return '\u2014'
  return typeof v === 'number' ? v.toFixed(1) : v
}

function setChartCanvas(name, el) {
  if (el) chartCanvases[name] = el
}

function setCustomChartCanvas(id, el) {
  if (el) customChartCanvases[id] = el
}

async function loadAssets() {
  try {
    const data = await request.get('/assets/api/list', { params: { page_size: 500 } })
    assets.value = Array.isArray(data) ? data : (data?.items || [])
  } catch (e) {
    console.error('load assets:', e)
  }
}

async function loadDomains() {
  try {
    const [domains, assetDom] = await Promise.all([
      request.get('/api/traces/domains'),
      request.get('/api/traces/asset-domains')
    ])
    domainList.value = domains || []
    assetDomains.value = assetDom || {}
  } catch (e) { /* ignore */ }
}

async function onDomainChange() {
  selectedAsset.value = '0'
  await loadMetrics()
}

function onAggregateChange() {
  loadMetrics()
}

async function loadMetrics() {
  loading.value = true
  try {
    const assetParam = selectedAsset.value
    const aggParam = (assetParam === '0' && aggregateMode.value) ? aggregateMode.value : ''
    const [namesRes, latestRes] = await Promise.all([
      request.get('/metrics/api/v2/names'),
      request.get(`/metrics/api/v2/latest?asset_id=${assetParam}&aggregate=${aggParam}`)
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
    const assetParam = selectedAsset.value
    const aggParam = (assetParam === '0' && aggregateMode.value) ? aggregateMode.value : ''
    const isAgg = assetParam === '0' && aggParam
    let allData

    if (isAgg) {
      const resp = await request.get(`/metrics/api/v2/range?asset_id=${assetParam}&hours=24&aggregate=${aggParam}`)
      allData = resp
    } else {
      allData = await request.get(`/metrics/api/v2/range?asset_id=${assetParam}&hours=24`)
    }

    let idx = 0
    for (const name of allMetrics.value) {
      const canvas = chartCanvases[name]
      if (!canvas) continue
      if (charts[name]) { charts[name].dispose(); delete charts[name] }

      if (isAgg && allData?.avg) {
        charts[name] = buildAggChart(canvas, allData, name, idx++)
      } else {
        const grouped = {}
        if (Array.isArray(allData)) {
          allData.forEach(d => {
            if (!grouped[d.name]) grouped[d.name] = []
            grouped[d.name].push(d)
          })
        }
        const data = grouped[name] || []
        if (data.length < 2) continue
        charts[name] = buildSimpleChart(canvas, data, idx++)
      }
    }
  } catch (e) {
    console.error('chart data error:', e)
  }
}

function buildSimpleChart(canvas, data, colorIdx) {
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
      lineStyle: { color, width: 1.5 },
      areaStyle: { color: color + '25' },
    }],
    animation: false,
  })
  return chart
}

function buildAggChart(canvas, allData, name, colorIdx) {
  const avgColor = colorPalette[colorIdx % colorPalette.length]
  const avgData = allData.avg || []
  const seriesData = (allData.series || []).filter(s => s.name && s.values && s.values.length > 1)
  const labels = avgData.length ? avgData.map(d => {
    const t = new Date(d.time)
    return `${t.getHours().toString().padStart(2,'0')}:${t.getMinutes().toString().padStart(2,'0')}`
  }) : []
  const avgValues = avgData.map(d => d.value)

  const series = [{
    name: aggregateMode.value === 'avg' ? '平均值' : aggregateMode.value,
    type: 'line',
    data: avgValues,
    smooth: true,
    symbol: 'none',
    lineStyle: { color: avgColor, width: 2.5 },
    areaStyle: { color: avgColor + '20' },
    z: 2,
  }]

  seriesData.forEach((s, si) => {
    const vals = s.values.map(v => v.value)
    series.push({
      name: s.name ? `资产 #${s.name}` : `series ${si}`,
      type: 'line',
      data: vals,
      smooth: true,
      symbol: 'none',
      lineStyle: { color: avgColor, width: 1, opacity: 0.35 },
      z: 1,
    })
  })

  const chart = echarts.init(canvas, null, { renderer: 'canvas' })
  chart.setOption({
    grid: { left: 0, right: 0, top: 2, bottom: 0 },
    xAxis: { type: 'category', data: labels, show: false },
    yAxis: { type: 'value', show: false },
    tooltip: { trigger: 'axis', show: false },
    series,
    animation: false,
  })
  return chart
}

async function loadCustomChartData() {
  for (const card of customCards.value) {
    const canvas = customChartCanvases[card.id]
    if (!canvas) continue
    if (customCharts[card.id]) { customCharts[card.id].dispose(); delete customCharts[card.id] }
    try {
      const resp = await request.post('/metrics/api/v2/custom-query', {
        promql: card.promql,
        hours: card.hours || 24,
      })
      if (resp.error || !resp.series?.length) {
        customCharts[card.id] = buildEmptyChart(canvas, resp.error || '无数据')
        continue
      }
      const colorIdx = customCards.value.indexOf(card)
      customCharts[card.id] = buildCustomChart(canvas, resp.series, colorIdx)
    } catch (e) {
      customCharts[card.id] = buildEmptyChart(canvas, '查询失败')
    }
  }
}

function buildCustomChart(canvas, series, colorIdx) {
  const maxLen = Math.max(...series.map(s => s.values?.length || 0))
  if (maxLen < 2) return buildEmptyChart(canvas, '数据不足')
  const labels = series[0].values.map(d => {
    const t = new Date(d.time)
    return `${t.getHours().toString().padStart(2,'0')}:${t.getMinutes().toString().padStart(2,'0')}`
  })
  const chart = echarts.init(canvas, null, { renderer: 'canvas' })
  chart.setOption({
    grid: { left: 0, right: 0, top: 2, bottom: 0 },
    xAxis: { type: 'category', data: labels, show: false },
    yAxis: { type: 'value', show: false },
    tooltip: { trigger: 'axis', show: false },
    series: series.map((s, si) => ({
      name: s.name,
      type: 'line',
      data: s.values.map(v => v.value),
      smooth: true,
      symbol: 'none',
      lineStyle: { color: colorPalette[(colorIdx + si) % colorPalette.length], width: 1.5 },
      areaStyle: { color: colorPalette[(colorIdx + si) % colorPalette.length] + '20' },
    })),
    animation: false,
  })
  return chart
}

function buildEmptyChart(canvas, msg) {
  const chart = echarts.init(canvas, null, { renderer: 'canvas' })
  chart.setOption({
    grid: { left: 0, right: 0, top: 0, bottom: 0 },
    xAxis: { show: false },
    yAxis: { show: false },
    graphic: [{
      type: 'text',
      left: 'center',
      top: 'center',
      style: { text: msg, fill: '#94a3b8', fontSize: 12 },
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
  loadCustomCards()
  await loadAssets()
  await loadDomains()
  await loadMetrics()
  await nextTick()
  loadCustomChartData()
  refreshTimer = setInterval(() => {
    loadChartData()
    loadCustomChartData()
  }, 15000)
})

onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  Object.values(charts).forEach(c => c?.dispose())
  Object.values(customCharts).forEach(c => c?.dispose())
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
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.page-header h1 {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.agg-select {
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid rgba(148,163,184,0.2);
  background: var(--card-bg);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
}
.btn-add {
  padding: 7px 16px;
  border-radius: 8px;
  border: none;
  background: var(--primary, #6366f1);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.2s;
}
.btn-add:hover { background: var(--primary-light, #818cf8); }
.btn-sm { padding: 5px 12px; font-size: 12px; }
.toolbar {
  margin-bottom: 16px;
  display: flex;
  gap: 10px;
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
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
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
.agg-badge {
  display: inline-block;
  padding: 1px 6px;
  font-size: 10px;
  font-weight: 600;
  background: rgba(99, 102, 241, 0.15);
  color: var(--primary, #6366f1);
  border-radius: 4px;
  text-transform: uppercase;
}
.count-badge {
  font-size: 11px;
  color: var(--text-muted);
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

.custom-section {
  margin-top: 32px;
  padding-top: 24px;
  border-top: 1px solid rgba(148,163,184,0.15);
}
.custom-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.custom-header h2 {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.custom-empty {
  padding: 40px 0;
  text-align: center;
  color: var(--text-muted);
  font-size: 14px;
}
.custom-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.custom-card {
  background: var(--card-bg);
  border: 1px solid rgba(148,163,184,0.12);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  position: relative;
  transition: border-color 0.2s;
  min-height: 200px;
}
.custom-card:hover {
  border-color: rgba(148,163,184,0.3);
}
.custom-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  user-select: none;
}
.drag-handle {
  cursor: grab;
  color: var(--text-muted);
  font-size: 18px;
  line-height: 1;
  padding: 0 2px;
}
.drag-handle:active {
  cursor: grabbing;
}
.custom-card-title {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.custom-card-promql-label {
  font-size: 10px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(99, 102, 241, 0.1);
  color: var(--primary, #6366f1);
  cursor: pointer;
}
.card-btn-del {
  width: 22px;
  height: 22px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 16px;
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}
.card-btn-del:hover {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}
.custom-card-chart {
  flex: 1;
  min-height: 120px;
  padding: 0 8px 8px;
}
.custom-card-chart canvas {
  width: 100% !important;
  height: 100% !important;
}
.resize-handle {
  position: absolute;
  bottom: 0;
  right: 0;
  width: 16px;
  height: 16px;
  cursor: nwse-resize;
  opacity: 0;
  transition: opacity 0.2s;
}
.resize-handle::after {
  content: '';
  position: absolute;
  bottom: 3px;
  right: 3px;
  width: 8px;
  height: 8px;
  border-right: 2px solid var(--text-muted);
  border-bottom: 2px solid var(--text-muted);
}
.custom-card:hover .resize-handle {
  opacity: 0.6;
}
.resize-handle:hover {
  opacity: 1 !important;
}

.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}
.modal-box {
  background: var(--card-bg, #fff);
  border-radius: 16px;
  padding: 24px;
  width: 480px;
  max-width: 90vw;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3);
}
.modal-box h3 {
  margin: 0 0 20px;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}
.form-group {
  margin-bottom: 16px;
}
.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.form-input {
  width: 100%;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid rgba(148,163,184,0.2);
  background: var(--bg-color, #f8fafc);
  color: var(--text-primary);
  font-size: 13px;
  font-family: inherit;
  box-sizing: border-box;
}
.form-textarea {
  width: 100%;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid rgba(148,163,184,0.2);
  background: var(--bg-color, #f8fafc);
  color: var(--text-primary);
  font-size: 13px;
  font-family: monospace;
  resize: vertical;
  box-sizing: border-box;
}
.size-picker {
  display: flex;
  gap: 8px;
}
.size-btn {
  padding: 6px 14px;
  border-radius: 8px;
  border: 1px solid rgba(148,163,184,0.2);
  background: var(--bg-color, #f8fafc);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}
.size-btn.active {
  border-color: var(--primary, #6366f1);
  background: rgba(99, 102, 241, 0.1);
  color: var(--primary, #6366f1);
}
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}
.btn-cancel {
  padding: 8px 20px;
  border-radius: 8px;
  border: 1px solid rgba(148,163,184,0.2);
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
}
.btn-save {
  padding: 8px 20px;
  border-radius: 8px;
  border: none;
  background: var(--primary, #6366f1);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
}
</style>