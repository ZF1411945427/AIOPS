<template>
  <div class="metrics-page">
    <div class="page-header">
      <h1>指标监控</h1>
      <div class="header-actions">
        <div class="time-range-group">
          <button v-for="tr in TIME_RANGES" :key="tr.value"
            class="tr-btn" :class="{ active: timeRange === tr.value }"
            @click="changeTimeRange(tr.value)">{{ tr.label }}</button>
        </div>
        <select v-model="aggregateMode" @change="loadMetrics" class="agg-select" title="跨资产聚合方式">
          <option value="avg">平均值</option>
          <option value="sum">总和</option>
          <option value="max">最大值</option>
          <option value="min">最小值</option>
        </select>
        <button class="btn-add" @click="openCustomModal">+ 自定义卡片</button>
        <button class="btn-ai" @click="openAiAnalyze" :disabled="aiLoading || !Object.keys(latestValues).length">
          {{ aiLoading ? 'AI 分析中...' : selectedMetrics.size ? `AI 分析选中指标 (${selectedMetrics.size})` : 'AI 体检（全部）' }}
        </button>
        <button class="btn-history" @click="openHistory" title="历史 AI 分析记录">🕘 历史</button>
        <button class="btn-export" @click="exportAllCsv" title="导出 CSV">⬇</button>
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
        <MetricCard
          v-for="name in filteredMetrics" :key="name"
          :name="name"
          :label="getMetricLabel(name)"
          :icon="getMetricIcon(name).icon"
          :latest="latestValues[name]"
          :assets="assets"
          :is-aggregate="isAggregateMode"
          :aggregate-label="aggregateLabel"
          :is-offline="isMetricOffline(name)"
          :selected="selectedMetrics.has(name)"
          :color="getMetricColor(name)"
          :chart-data="chartDataMap[name]"
          :trend="insightTrends[name] || null"
          @toggle-select="toggleSelectMetric"
          @drill="openDrillDown(name)"
        />
        <div v-if="filteredMetrics.length === 0 && !loading" class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">&#128202;</div>
          <div>暂无指标数据</div>
        </div>
      </template>
    </div>

    <div v-if="showHistory" class="modal-overlay" @click.self="closeHistory">
      <div class="modal-box" style="width:680px;max-height:80vh;overflow-y:auto">
        <div class="modal-head">
          <h3>🕘 AI 分析历史</h3>
          <button class="btn-cancel" @click="closeHistory">关闭</button>
        </div>
        <div v-if="historyLoading" class="loading-state">加载中...</div>
        <div v-else-if="historyDetail" class="history-detail">
          <button class="btn-cancel" @click="historyDetail = null" style="margin-bottom:10px">← 返回列表</button>
          <div class="history-title">{{ historyDetail.title }}</div>
          <div class="history-meta">{{ historyDetail.created_at }} · 评分: {{ historyDetail.score }}/100 · {{ historyDetail.provider }}</div>
          <div class="history-content" v-html="mdToHtml(historyDetail.analysis || '')"></div>
        </div>
        <div v-else>
          <div v-for="h in historyList" :key="h.id" class="history-item" @click="loadHistoryDetail(h.id)">
            <div class="hi-title">{{ h.title }}</div>
            <div class="hi-meta">{{ h.created_at }} · 评分{{ h.score }} · {{ h.provider }}</div>
            <div class="hi-preview">{{ h.analysis_preview }}</div>
            <button class="hi-del" @click.stop="deleteHistory(h.id)">删除</button>
          </div>
          <div v-if="!historyList.length" class="empty-hint">暂无历史分析记录</div>
        </div>
      </div>
    </div>

    <div v-if="rcaResult || rcaLoading || rcaError" class="ai-drawer-mask" @click.self="rcaResult = ''; rcaError = ''; rcaLoading = false">
      <div class="ai-drawer">
        <div class="ai-drawer-head">
          <div>
            <div class="ai-drawer-title">🔍 跨域根因分析 ({{ rcaMetric }})</div>
            <div class="ai-drawer-meta">指标 → 关联告警+调用链 → LLM 综合根因</div>
          </div>
          <button class="ai-drawer-close" @click="rcaResult = ''; rcaError = ''; rcaLoading = false">&times;</button>
        </div>
        <div class="ai-drawer-body">
          <div v-if="rcaLoading" class="ai-loading"><div class="ai-spinner"></div><span>正在跨域分析指标 {{ rcaMetric }}...</span></div>
          <div v-else-if="rcaError" class="ai-error-bar">{{ rcaError }}</div>
          <div v-else-if="rcaResult" class="ai-result" v-html="rcaResult"></div>
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

    <MetricDetailModal
      :visible="detailVisible"
      :name="detailName"
      :label="getMetricLabel(detailName)"
      :icon="getMetricIcon(detailName).icon"
      :unit="detailUnit"
      :latest="detailLatest"
      :assets="assets"
      :chart-data="detailChartData"
      :color="getMetricColor(detailName)"
      :is-aggregate="isAggregateMode"
      @close="closeDrillDown"
      @create-rule="quickCreateRule"
      @export="exportDetailCsv"
      @rca="runRca"
    />

    <div v-if="aiDrawer.show" class="ai-drawer-mask" @click.self="closeAiDrawer">
      <div class="ai-drawer">
        <div class="ai-drawer-head">
          <div>
            <div class="ai-drawer-title">AI 指标健康体检</div>
            <div v-if="aiMeta" class="ai-drawer-meta">{{ aiMeta }}</div>
          </div>
          <button class="ai-drawer-close" @click="closeAiDrawer">&times;</button>
        </div>
        <div class="ai-drawer-body">
          <div class="ai-question-row">
            <input
              v-model="aiQuestion" class="ai-question-input"
              placeholder="可选：输入你想问的（如：哪些指标有风险？）" @keyup.enter="runAiAnalyze"
            />
            <button class="btn-ai" :disabled="aiLoading" @click="runAiAnalyze">{{ aiLoading ? '分析中...' : '开始分析' }}</button>
          </div>
          <div v-if="aiError" class="ai-error-bar">{{ aiError }}</div>
          <div v-if="aiLoading" class="ai-loading">
            <div class="ai-spinner"></div>
            <span>AI 正在分析 {{ aiMetricCount }} 项指标...</span>
          </div>
          <div v-else-if="aiResult" class="ai-result" v-html="aiResult"></div>
          <div v-else class="ai-empty">点击「开始分析」，AI 将基于当前页面指标最新值做健康体检</div>
          <div v-if="aiResult && !aiLoading" class="ai-transfer-bar">
            <button class="btn-transfer" :disabled="transferring" @click="transferToAgent">
              {{ transferring ? '转交中...' : '转交执行 → 智能助手' }}
            </button>
            <span class="ai-transfer-tip">生成待确认动作，经你确认后才执行</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'
import * as echarts from 'echarts'
import MetricCard from './metrics/MetricCard.vue'
import MetricDetailModal from './metrics/MetricDetailModal.vue'
import { formatValue, formatTime, formatAxisTime, TIME_RANGES, THRESHOLDS, metricStatus, statusColor } from './metrics/metricsUtils.js'

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

const METRIC_LABELS = {
  cpu_usage: 'CPU 使用率', cpu_iowait: 'CPU I/O 等待',
  loadavg_1min: '1 分钟负载', loadavg_5min: '5 分钟负载', loadavg_15min: '15 分钟负载',
  memory_usage: '内存使用率', memory_available: '可用内存', swap_usage: '交换分区使用率',
  disk_usage: '磁盘使用率', disk_inode_usage: '磁盘 Inode 使用率',
  network_rx_bytes: '网络接收速率', network_tx_bytes: '网络发送速率',
  tcp_established: 'TCP 已建立连接', tcp_time_wait: 'TCP 等待连接',
  http_connections: 'HTTP 连接数', mysql_connections: 'MySQL 连接数',
  ssh_connections: 'SSH 连接数', open_files: '打开文件数',
  process_count: '进程数', zombie_process: '僵尸进程数',
  svc_up: '服务在线状态', uptime_seconds: '运行时长',
  synthetic_api_healthz_latency_ms: 'API 健康检查延迟', synthetic_api_healthz_up: 'API 健康检查状态', synthetic_api_healthz_status: 'API 健康检查响应码',
  synthetic_api_readyz_latency_ms: 'API 就绪检查延迟', synthetic_api_readyz_up: 'API 就绪检查状态', synthetic_api_readyz_status: 'API 就绪检查响应码',
  synthetic_victoria_metrics_latency_ms: 'VictoriaMetrics 延迟', synthetic_victoria_metrics_up: 'VictoriaMetrics 状态', synthetic_victoria_metrics_status: 'VictoriaMetrics 响应码',
}

function getMetricLabel(name) { return METRIC_LABELS[name] || name }
function getMetricIcon(name) {
  for (const c of CATEGORIES) { if (c.pattern.test(name)) return c }
  return { icon: '\uD83D\uDCCA', label: '其他' }
}
function getMetricCategory(name) {
  for (const c of CATEGORIES) { if (c.pattern.test(name)) return c.key }
  return 'other'
}
function getMetricColor(name) {
  const idx = allMetrics.value.indexOf(name)
  return colorPalette[(idx % colorPalette.length) + (colorPalette.length - idx - 1) % colorPalette.length]
}

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
const timeRange = ref(24)
const chartDataMap = ref({})

let refreshTimer = null

const customDashRef = ref(null)
const customCards = ref([])
const customLoading = ref(false)
const showCustomModal = ref(false)
const editingCardIdx = ref(null)
const customForm = ref({ title: '', promql: '', hours: 24, w: 2, h: 1 })

const detailVisible = ref(false)
const detailName = ref('')
const detailLatest = ref(null)
const detailUnit = ref('')
const detailChartData = ref(null)

const aiDrawer = ref({ show: false })
const aiQuestion = ref('')
const aiLoading = ref(false)
const aiError = ref('')
const aiResult = ref('')
const aiResultRaw = ref('')
const aiMeta = ref('')
const aiMetricCount = ref(0)
const transferring = ref(false)
const selectedMetrics = ref(new Set())
const insightTrends = ref({})
const showHistory = ref(false)
const historyList = ref([])
const historyLoading = ref(false)
const historyDetail = ref(null)
const rcaLoading = ref(false)
const rcaResult = ref('')
const rcaError = ref('')
const rcaMetric = ref('')

const isAggregateMode = computed(() => selectedAsset.value === '0' && aggregateMode.value)
const aggregateLabel = computed(() => {
  if (!isAggregateMode.value) return ''
  return aggregateMode.value === 'avg' ? '平均' : aggregateMode.value === 'sum' ? '总和' : aggregateMode.value === 'max' ? '最大' : '最小'
})
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
  return [...new Set(assets.value.filter(a => a.status === 'offline').map(a => a.name))]
})
const offlineWarning = computed(() => {
  if (selectedAsset.value === '0') {
    if (offlineAssetNames.value.length) return `部分指标来自 ${offlineAssetNames.value.length} 个离线资产，显示的是历史数据`
    return ''
  }
  const asset = assets.value.find(a => a.id == selectedAsset.value)
  if (asset && asset.status === 'offline') {
    let latest = ''
    for (const n of allMetrics.value) {
      const ts = latestValues.value[n]?.timestamp
      if (ts && (!latest || ts > latest)) latest = ts
    }
    return `资产「${asset.name}」当前离线，显示的是历史数据${latest ? '（最后采集: ' + formatTime(latest) + '）' : ''}`
  }
  return ''
})
const filteredMetrics = computed(() => {
  if (activeCat.value === 'all') return allMetrics.value
  return allMetrics.value.filter(n => getMetricCategory(n) === activeCat.value)
})

function isMetricOffline(name) {
  const lv = latestValues.value[name]
  if (!lv || !lv.asset_id) return false
  return assetStatusMap.value[lv.asset_id] === 'offline'
}

function toggleSelectMetric(name) {
  const next = new Set(selectedMetrics.value)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  selectedMetrics.value = next
}

function filterCategory(cat) { activeCat.value = cat }

async function loadAssets() {
  try {
    const data = await request.get('/assets/api/list', { params: { page_size: 500 } })
    assets.value = Array.isArray(data) ? data : (data?.items || [])
  } catch (e) {
    ElMessage.error('资产列表加载失败: ' + (e.message || e))
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
  } catch (e) {
    ElMessage.warning('业务域加载失败: ' + (e.message || e))
  }
}

async function onDomainChange() {
  selectedAsset.value = '0'
  selectedMetrics.value = new Set()
  await loadMetrics()
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
    await loadChartData()
  } catch (e) {
    ElMessage.error('指标数据加载失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

async function loadChartData() {
  try {
    const assetParam = selectedAsset.value
    const aggParam = (assetParam === '0' && aggregateMode.value) ? aggregateMode.value : ''
    const isAgg = assetParam === '0' && aggParam
    const hours = timeRange.value
    const cm = {}
    if (isAgg) {
      const resp = await request.get(`/metrics/api/v2/range-all?hours=${hours}&aggregate=${aggParam}`)
      for (const name of allMetrics.value) {
        const d = resp[name]
        if (!d || !d.avg || !d.avg.length) continue
        const labels = d.avg.map(pt => formatAxisTime(pt.time))
        cm[name] = { labels, values: d.avg.map(pt => pt.value), series: (d.series || []).filter(s => s.values && s.values.length > 1) }
      }
    } else {
      const allData = await request.get(`/metrics/api/v2/range?asset_id=${assetParam}&hours=${hours}`)
      const grouped = {}
      if (Array.isArray(allData)) {
        allData.forEach(d => {
          if (!grouped[d.name]) grouped[d.name] = []
          grouped[d.name].push(d)
        })
      }
      for (const name of allMetrics.value) {
        const data = grouped[name] || []
        if (data.length < 2) continue
        const labels = data.map(d => formatAxisTime(d.time))
        cm[name] = { labels, values: data.map(d => d.value) }
      }
    }
    chartDataMap.value = cm
  } catch (e) {
    ElMessage.error('指标趋势加载失败: ' + (e.message || e))
  }
}

async function loadCustomCardData() {
  customLoading.value = true
  try {
    const chartData = {}
    for (const card of customCards.value) {
      try {
        const resp = await request.post('/metrics/api/v2/custom-query', {
          promql: card.promql, hours: card.hours || 24,
        })
        if (resp.error || !resp.series?.length) continue
        chartData[card.id] = resp.series
      } catch (e) {
        chartData[card.id] = null
      }
    }
    if (customDashRef.value) {
      customDashRef.value.updateCharts(chartData)
    }
  } catch (e) {
    ElMessage.error('自定义卡片数据加载失败: ' + (e.message || e))
  } finally {
    customLoading.value = false
  }
}

async function changeTimeRange(hours) {
  timeRange.value = hours
  selectedMetrics.value = new Set()
  await loadMetrics()
}

function changeAsset() {
  selectedMetrics.value = new Set()
  loadMetrics()
}

// --- Custom Card Backend Persistence ---
async function loadCustomCards() {
  try {
    const data = await request.get('/metrics/api/cards')
    customCards.value = Array.isArray(data) ? data : []
  } catch (e) {
    customCards.value = []
  }
}

async function saveCustomCard() {
  if (!customForm.value.title.trim() || !customForm.value.promql.trim()) {
    ElMessage.warning('标题和 PromQL 不能为空')
    return
  }
  try {
    if (editingCardIdx.value !== null) {
      const card = customCards.value[editingCardIdx.value]
      await request.put(`/metrics/api/cards/${card.id}`, { ...customForm.value })
      Object.assign(card, { ...customForm.value })
    } else {
      const maxOrder = customCards.value.reduce((m, c) => Math.max(m, c.order || 0), -1)
      const res = await request.post('/metrics/api/cards', { ...customForm.value, order: maxOrder + 1 })
      if (res.ok) {
        customCards.value.push({ id: res.id, ...customForm.value, order: maxOrder + 1 })
      }
    }
    showCustomModal.value = false
    editingCardIdx.value = null
    ElMessage.success('卡片已保存')
    await nextTick()
    loadCustomCardData()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.message || e))
  }
}

function editCustomCard(idx) {
  const card = customCards.value[idx]
  customForm.value = { title: card.title, promql: card.promql, hours: card.hours || 24, w: card.w || 2, h: card.h || 1 }
  editingCardIdx.value = idx
  showCustomModal.value = true
}

function openCustomModal() {
  customForm.value = { title: '', promql: '', hours: 24, w: 2, h: 1 }
  editingCardIdx.value = null
  showCustomModal.value = true
}

async function deleteCustomCard(idx) {
  const card = customCards.value[idx]
  if (!card) return
  try {
    await request.delete(`/metrics/api/cards/${card.id}`)
    customCards.value.splice(idx, 1)
    ElMessage.success('卡片已删除')
  } catch (e) {
    ElMessage.error('删除失败: ' + (e.message || e))
  }
}

async function reorderCustomCards(newOrder) {
  customCards.value = newOrder
  for (let i = 0; i < newOrder.length; i++) {
    try {
      await request.put(`/metrics/api/cards/${newOrder[i].id}`, { order: i })
    } catch (e) { /* ignore */ }
  }
}

async function resizeCustomCard(idx, dims) {
  const card = customCards.value[idx]
  if (!card) return
  card.w = dims.w
  card.h = dims.h
  try {
    await request.put(`/metrics/api/cards/${card.id}`, { w: dims.w, h: dims.h })
  } catch (e) { /* ignore */ }
}

// --- Drill-down ---
async function openDrillDown(name) {
  detailName.value = name
  detailLatest.value = latestValues.value[name] || null
  detailUnit.value = (latestValues.value[name]?.unit) || ''
  detailVisible.value = true
  detailChartData.value = null
  try {
    const assetParam = selectedAsset.value
    const aggParam = (assetParam === '0' && aggregateMode.value) ? aggregateMode.value : ''
    const hours = timeRange.value
    let resp
    if (aggParam) {
      resp = await request.get(`/metrics/api/v2/range?asset_id=${assetParam}&name=${name}&hours=${hours}&aggregate=${aggParam}`)
    } else {
      resp = await request.get(`/metrics/api/v2/range?asset_id=${assetParam}&name=${name}&hours=${hours}`)
    }
    if (aggParam && resp?.avg) {
      const labels = resp.avg.map(pt => formatAxisTime(pt.time))
      detailChartData.value = { labels, values: resp.avg.map(pt => pt.value), series: (resp.series || []).filter(s => s.values?.length > 1) }
    } else if (Array.isArray(resp)) {
      const labels = resp.map(d => formatAxisTime(d.time))
      detailChartData.value = { labels, values: resp.map(d => d.value) }
    }
  } catch (e) {
    ElMessage.error('详情数据加载失败: ' + (e.message || e))
  }
}

function closeDrillDown() {
  detailVisible.value = false
  detailName.value = ''
  detailChartData.value = null
}

async function quickCreateRule() {
  const name = detailName.value
  const lv = latestValues.value[name]
  const threshold = THRESHOLDS[name]
  if (!threshold) {
    ElMessage.info('该指标无预设阈值，请前往告警设置手动创建')
    return
  }
  try {
    const res = await request.post('/metrics/api/quick-create-rule', {
      name: `${getMetricLabel(name)} 告警规则`,
      metric_name: name,
      condition: '>',
      threshold: threshold.crit,
      severity: 'critical',
    })
    if (res.ok) {
      ElMessage.success(`告警规则已创建 (#${res.rule_id})，可在告警中心查看`)
    }
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.message || e))
  }
}

async function exportAllCsv() {
  try {
    const res = await request.get(`/metrics/api/export-csv?asset_id=${selectedAsset.value}&hours=${timeRange.value}`)
    if (res.ok && res.csv) {
      downloadCsv(res.csv, `metrics_${new Date().toISOString().slice(0, 10)}.csv`)
      ElMessage.success('导出成功')
    }
  } catch (e) {
    ElMessage.error('导出失败: ' + (e.message || e))
  }
}

async function exportDetailCsv() {
  try {
    const res = await request.get(`/metrics/api/export-csv?asset_id=${selectedAsset.value}&hours=${timeRange.value}`)
    if (res.ok && res.csv) {
      downloadCsv(res.csv, `metrics_${detailName.value}_${new Date().toISOString().slice(0, 10)}.csv`)
      ElMessage.success('导出成功')
    }
  } catch (e) {
    ElMessage.error('导出失败: ' + (e.message || e))
  }
}

function downloadCsv(content, filename) {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// --- AI Analysis ---
function openAiAnalyze() {
  const keys = Object.keys(latestValues.value)
  if (!keys.length) return
  const selectedCount = selectedMetrics.value.size
  const scope = selectedCount ? `已选 ${selectedCount} 项` : `共 ${keys.length} 项`
  aiDrawer.value = { show: true }
  aiQuestion.value = ''
  aiError.value = ''
  aiResult.value = ''
  aiResultRaw.value = ''
  aiMeta.value = `资产: ${selectedAsset.value === '0' ? '全部（' + (aggregateMode.value || 'avg') + '聚合）' : '资产#' + selectedAsset.value} · ${scope}`
}

function closeAiDrawer() {
  if (aiLoading.value) return
  aiDrawer.value = { show: false }
}

function buildMetricsScope() {
  const selected = [...selectedMetrics.value].filter(n => n in latestValues.value)
  const names = selected.length ? selected : Object.keys(latestValues.value)
  return names.slice(0, 200).map(name => {
    const v = latestValues.value[name] || {}
    return { name, value: v.value, unit: v.unit, asset_id: v.asset_id, aggregate: v.aggregate || (isAggregateMode.value ? aggregateMode.value : '') }
  })
}

async function runAiAnalyze() {
  const metrics = buildMetricsScope()
  if (!metrics.length) return
  aiLoading.value = true
  aiError.value = ''
  aiResult.value = ''
  insightTrends.value = {}
  try {
    const res = await request.post('/ai-insight/analyze', {
      source_type: 'metrics',
      metrics, question: aiQuestion.value.trim(),
      hours: timeRange.value,
      title: `指标体检 #${Date.now().toString().slice(-6)}`,
    }, { timeout: 120000 })
    if (res.ok) {
      aiResult.value = mdToHtml(res.analysis || '')
      aiResultRaw.value = res.analysis || ''
      aiMetricCount.value = (res.meta && res.meta.metric_count) || metrics.length
      if (res.enhanced && res.enhanced.trends) {
        insightTrends.value = res.enhanced.trends
      }
      const scope = selectedMetrics.value.size ? `已选 ${selectedMetrics.value.size} 项` : `共 ${metrics.length} 项`
      aiMeta.value = `资产: ${selectedAsset.value === '0' ? '全部（' + (aggregateMode.value || 'avg') + '聚合）' : '资产#' + selectedAsset.value} · 分析 ${metrics.length} 项指标 · 模型: ${res.provider || '-'} · 记录 #${res.record_id || '-'}`
    } else {
      aiError.value = res.error || 'AI 分析失败'
    }
  } catch (e) {
    aiError.value = 'AI 分析请求失败：' + (e.message || e)
  } finally {
    aiLoading.value = false
  }
}

async function transferToAgent() {
  if (transferring.value || !aiResult.value) return
  transferring.value = true
  aiError.value = ''
  const metrics = buildMetricsScope().map(m => `${m.name}=${m.value}${m.unit || ''}${m.asset_id ? `(asset#${m.asset_id})` : ''}`)
  try {
    const res = await request.post('/agent/transfer-from-analysis', {
      source_type: 'metrics',
      title: `指标体检转交 #${Date.now().toString().slice(-6)}`,
      analysis: aiResultRaw.value || '',
      context: {
        asset_id: selectedAsset.value === '0' ? null : selectedAsset.value,
        aggregate_mode: isAggregateMode.value ? aggregateMode.value : '',
        metric_count: metrics.length,
        sample_metrics: metrics.slice(0, 30).join('; '),
      },
      instruction: '',
    })
    if (res.session_id) {
      window._pendingAgentSessionId = res.session_id
      window._navigateTo && window._navigateTo('agent-chat')
    } else {
      aiError.value = res.error || '转交失败'
    }
  } catch (e) {
    aiError.value = '转交执行请求失败：' + (e.message || e)
  } finally {
    transferring.value = false
  }
}

function mdToHtml(text) {
  const esc = t => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const lines = esc(text).split('\n')
  const html = []
  for (const line of lines) {
    const m = line.match(/^(\s*)([-*]|\d+[.、)])\s+(.*)$/)
    if (m) {
      html.push(`<div class="ai-li">${m[1] ? '<span class="ai-li-indent"></span>' : ''}<span class="ai-li-mark">${m[2]}</span> ${m[3]}</div>`)
    } else if (/^#{1,4}\s/.test(line)) {
      html.push(`<div class="ai-h">${line.replace(/^#{1,4}\s*/, '')}</div>`)
    } else if (line.trim() === '') {
      html.push('')
    } else {
      html.push(`<div class="ai-p">${line}</div>`)
    }
  }
  return html.join('\n')
}

async function openHistory() {
  showHistory.value = true
  historyDetail.value = null
  historyLoading.value = true
  try {
    historyList.value = await request.get('/ai-insight/history', { params: { source_type: 'metrics', limit: 50 } })
  } catch (e) {
    ElMessage.error('历史加载失败: ' + (e.message || e))
  } finally {
    historyLoading.value = false
  }
}

async function loadHistoryDetail(id) {
  try {
    historyDetail.value = await request.get(`/ai-insight/history/${id}`)
  } catch (e) {
    ElMessage.error('历史详情加载失败: ' + (e.message || e))
  }
}

async function deleteHistory(id) {
  try {
    await request.delete(`/ai-insight/history/${id}`)
    historyList.value = historyList.value.filter(h => h.id !== id)
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error('删除失败: ' + (e.message || e))
  }
}

async function runRca(name) {
  if (!name) { ElMessage.warning('请选择一个指标'); return }
  const assetId = selectedAsset.value === '0' ? (latestValues.value[name]?.asset_id || 0) : selectedAsset.value
  if (!assetId) { ElMessage.warning('该指标无关联资产，无法进行跨域根因分析'); return }
  rcaMetric.value = name
  rcaLoading.value = true
  rcaError.value = ''
  rcaResult.value = ''
  try {
    const res = await request.post('/ai-insight/rca', {
      metric_name: name, asset_id: assetId, hours: timeRange.value,
    }, { timeout: 120000 })
    if (res.ok) {
      rcaResult.value = mdToHtml(res.analysis || '')
    } else {
      rcaError.value = res.error || 'RCA 分析失败'
    }
  } catch (e) {
    rcaError.value = 'RCA 请求失败：' + (e.message || e)
  } finally {
    rcaLoading.value = false
  }
}

function closeHistory() { showHistory.value = false; historyDetail.value = null }

onMounted(async () => {
  await loadCustomCards()
  await loadAssets()
  await loadDomains()
  await loadMetrics()
  await nextTick()
  loadCustomCardData()
  refreshTimer = setInterval(() => {
    loadChartData()
    loadCustomCardData()
  }, 15000)
})

onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<style scoped>
.offline-warning {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px; margin-bottom: 12px;
  background: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.3);
  border-radius: 8px; color: #d97706; font-size: 13px;
}
.warn-icon { font-size: 16px; }
.warn-toggle {
  margin-left: auto; padding: 2px 10px;
  border: 1px solid rgba(245, 158, 11, 0.4);
  background: transparent; color: #d97706; border-radius: 4px;
  cursor: pointer; font-size: 12px; white-space: nowrap;
}
.warn-toggle:hover { background: rgba(245, 158, 11, 0.15); }
.offline-detail {
  display: flex; flex-wrap: wrap; gap: 6px;
  padding: 10px 16px; margin-bottom: 12px;
  background: rgba(239, 68, 68, 0.05); border-radius: 8px;
}
.offline-chip {
  padding: 2px 8px; font-size: 12px;
  background: rgba(239, 68, 68, 0.1); color: #ef4444; border-radius: 4px;
}
.metrics-page { padding: 20px; }
.page-header {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; flex-wrap: wrap; gap: 10px;
}
.page-header h1 { font-size: 20px; font-weight: 700; color: var(--text-primary); margin: 0; }
.header-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.time-range-group { display: flex; gap: 2px; background: rgba(148,163,184,0.08); border-radius: 8px; padding: 2px; }
.tr-btn {
  padding: 4px 10px; border: none; background: transparent; color: var(--text-secondary);
  font-size: 12px; cursor: pointer; border-radius: 6px; font-family: inherit; transition: all 0.15s;
}
.tr-btn:hover { color: var(--text-primary); background: rgba(148,163,184,0.1); }
.tr-btn.active { background: var(--card-bg, #fff); color: var(--primary); box-shadow: 0 1px 3px rgba(0,0,0,0.1); font-weight: 600; }
.agg-select {
  padding: 6px 12px; border-radius: 8px;
  border: 1px solid rgba(148,163,184,0.2);
  background: var(--card-bg); color: var(--text-primary);
  font-size: 13px; cursor: pointer; font-family: inherit;
}
.btn-add {
  padding: 7px 16px; border-radius: 8px; border: none;
  background: var(--primary, #6366f1); color: #fff; font-size: 13px;
  font-weight: 600; cursor: pointer; font-family: inherit; transition: background 0.2s;
}
.btn-add:hover { background: var(--primary-light, #818cf8); }
.btn-export {
  width: 34px; height: 34px; border-radius: 8px; border: 1px solid rgba(148,163,184,0.2);
  background: var(--card-bg); color: var(--text-secondary); font-size: 15px;
  cursor: pointer; font-family: inherit; display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.btn-export:hover { border-color: var(--primary); color: var(--primary); }
.toolbar { margin-bottom: 16px; display: flex; gap: 10px; }
.toolbar select {
  padding: 8px 14px; border-radius: 8px;
  border: 1px solid rgba(148,163,184,0.2);
  background: var(--card-bg); color: var(--text-primary);
  font-size: 13px; min-width: 160px; cursor: pointer;
}
.cat-tabs {
  display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px;
}
.cat-tab {
  padding: 6px 14px; border-radius: 20px;
  border: 1px solid rgba(148,163,184,0.2);
  background: var(--card-bg); color: var(--text-secondary);
  font-size: 0.78rem; font-weight: 500; cursor: pointer;
  transition: all 0.2s; font-family: inherit;
}
.cat-tab:hover { border-color: var(--primary-light); color: var(--primary-light); background: rgba(129,140,248,0.06); }
.cat-tab.active { border-color: var(--primary); background: var(--primary); color: #fff; }
.cat-tab .cat-count { display: inline-block; margin-left: 4px; font-size: 0.7rem; opacity: 0.7; }
.metric-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px; margin-bottom: 24px; position: relative; min-height: 200px;
}
.loading-overlay { grid-column: 1/-1; text-align: center; padding: 60px 0; color: var(--text-muted); }
.loading-spinner {
  width: 32px; height: 32px; border: 3px solid rgba(148,163,184,0.2);
  border-top-color: var(--primary); border-radius: 50%;
  animation: spin 0.8s linear infinite; margin: 0 auto 12px;
}
@keyframes spin { to { transform: rotate(360deg); } }
.empty-state { grid-column: 1/-1; text-align: center; padding: 60px 0; color: var(--text-muted); }

/* Modal */
.modal-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 9999;
}
.modal-box {
  background: var(--card-bg, #fff); border-radius: 16px; padding: 24px;
  width: 480px; max-width: 90vw; box-shadow: 0 20px 60px rgba(0,0,0,0.3);
}
.modal-box h3 { margin: 0 0 20px; font-size: 16px; font-weight: 700; color: var(--text-primary); }
.form-group { margin-bottom: 16px; }
.form-group label { display: block; font-size: 13px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; }
.form-input {
  width: 100%; padding: 8px 12px; border-radius: 8px;
  border: 1px solid rgba(148,163,184,0.2); background: var(--bg-color, #f8fafc);
  color: var(--text-primary); font-size: 13px; font-family: inherit; box-sizing: border-box;
}
.form-textarea {
  width: 100%; padding: 8px 12px; border-radius: 8px;
  border: 1px solid rgba(148,163,184,0.2); background: var(--bg-color, #f8fafc);
  color: var(--text-primary); font-size: 13px; font-family: monospace;
  resize: vertical; box-sizing: border-box;
}
.size-picker { display: flex; gap: 8px; }
.size-btn {
  padding: 6px 14px; border-radius: 8px; border: 1px solid rgba(148,163,184,0.2);
  background: var(--bg-color, #f8fafc); color: var(--text-secondary);
  font-size: 13px; cursor: pointer; font-family: inherit; transition: all 0.15s;
}
.size-btn.active { border-color: var(--primary, #6366f1); background: rgba(99, 102, 241, 0.1); color: var(--primary, #6366f1); }
.form-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; }
.btn-cancel {
  padding: 8px 20px; border-radius: 8px; border: 1px solid rgba(148,163,184,0.2);
  background: transparent; color: var(--text-secondary); font-size: 13px; cursor: pointer; font-family: inherit;
}
.btn-save {
  padding: 8px 20px; border-radius: 8px; border: none;
  background: var(--primary, #6366f1); color: #fff; font-size: 13px; font-weight: 600; cursor: pointer; font-family: inherit;
}
.btn-ai {
  padding: 8px 16px; border-radius: 8px; border: none;
  background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff;
  font-size: 13px; font-weight: 600; cursor: pointer; font-family: inherit; transition: opacity 0.15s;
}
.btn-ai:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-history {
  padding: 7px 14px; border-radius: 8px; border: 1px solid rgba(148,163,184,0.2);
  background: var(--card-bg); color: var(--text-secondary); font-size: 13px;
  cursor: pointer; font-family: inherit; transition: all 0.15s;
}
.btn-history:hover { border-color: var(--primary); color: var(--primary); }
.history-item {
  padding: 10px 12px; border-bottom: 1px solid rgba(148,163,184,0.1); cursor: pointer; transition: background 0.15s; position: relative;
}
.history-item:hover { background: rgba(99,102,241,0.04); }
.hi-title { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.hi-meta { font-size: 11px; color: var(--text-muted); margin: 2px 0; }
.hi-preview { font-size: 12px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hi-del { position: absolute; top: 10px; right: 10px; font-size: 11px; color: #ef4444; background: none; border: 1px solid rgba(239,68,68,0.2); border-radius: 4px; padding: 2px 8px; cursor: pointer; }
.history-detail { padding: 10px 0; }
.history-title { font-size: 15px; font-weight: 700; color: var(--text-primary); }
.history-meta { font-size: 11px; color: var(--text-muted); margin: 4px 0 12px; }
.history-content { font-size: 13px; line-height: 1.8; color: #303133; }
.modal-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.modal-head h3 { margin: 0; font-size: 16px; }
.loading-state { text-align: center; padding: 40px; color: var(--text-muted); }
.empty-hint { text-align: center; padding: 30px; color: var(--text-muted); }

/* AI Drawer */
.ai-drawer-mask { position: fixed; inset: 0; z-index: 2000; background: rgba(0,0,0,0.45); display: flex; justify-content: flex-end; }
.ai-drawer {
  width: 460px; max-width: 92vw; height: 100%;
  background: #fff; display: flex; flex-direction: column;
  box-shadow: -4px 0 24px rgba(0,0,0,0.15); animation: aiSlideIn 0.25s ease;
}
@keyframes aiSlideIn { from { transform: translateX(60px); opacity: 0 } to { transform: translateX(0); opacity: 1 } }
.ai-drawer-head { display: flex; align-items: flex-start; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid #ebeef5; }
.ai-drawer-title { font-size: 16px; font-weight: 700; color: #303133; }
.ai-drawer-meta { font-size: 12px; color: #909399; margin-top: 4px; }
.ai-drawer-close { border: none; background: none; font-size: 22px; color: #909399; cursor: pointer; line-height: 1; }
.ai-drawer-body { flex: 1; overflow-y: auto; padding: 16px 20px; }
.ai-question-row { display: flex; gap: 8px; margin-bottom: 12px; }
.ai-question-input { flex: 1; padding: 8px 12px; border-radius: 8px; border: 1px solid rgba(148,163,184,0.3); font-size: 13px; font-family: inherit; }
.ai-error-bar { background: #fef0f0; color: #f56c6c; border: 1px solid #fbc4c4; border-radius: 6px; padding: 10px 12px; font-size: 13px; margin-bottom: 10px; }
.ai-loading { display: flex; align-items: center; gap: 10px; color: #909399; font-size: 13px; padding: 24px 0; }
.ai-spinner { width: 18px; height: 18px; border: 2px solid #e0e7ff; border-top-color: #6366f1; border-radius: 50%; animation: aiSpin 0.8s linear infinite; }
@keyframes aiSpin { to { transform: rotate(360deg) } }
.ai-result { font-size: 13px; line-height: 1.8; color: #303133; }
.ai-result .ai-h { font-weight: 700; color: #4f46e5; margin: 12px 0 6px; font-size: 14px; }
.ai-result .ai-p { margin: 4px 0; }
.ai-result .ai-li { margin: 3px 0; }
.ai-result .ai-li-mark { color: #6366f1; font-weight: 600; }
.ai-empty { color: #909399; font-size: 13px; text-align: center; padding: 40px 0; }
.ai-transfer-bar { display: flex; align-items: center; gap: 10px; margin-top: 14px; padding-top: 14px; border-top: 1px dashed rgba(148,163,184,0.3); }
.btn-transfer { padding: 7px 16px; border-radius: 6px; border: none; cursor: pointer; background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; font-size: 13px; font-weight: 600; font-family: inherit; }
.btn-transfer:disabled { opacity: 0.5; cursor: not-allowed; }
.ai-transfer-tip { font-size: 11px; color: #909399; }
</style>