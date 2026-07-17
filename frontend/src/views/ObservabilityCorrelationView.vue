<template>
  <div class="obs-correlation">
    <!-- 页头 -->
    <div class="page-header">
      <div class="header-left">
        <h1>关联分析</h1>
        <p class="subtitle">日志 · 指标 · 链路 — 全域可观测信号关联分析</p>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="toolbar">
      <div class="toolbar-row">
        <div class="filter-group">
          <label>时间范围</label>
          <el-select v-model="hours" filterable @change="onFilterChange" style="width:140px">
            <el-option :value="1" label="近 1 小时" />
            <el-option :value="3" label="近 3 小时" />
            <el-option :value="6" label="近 6 小时" />
            <el-option :value="12" label="近 12 小时" />
            <el-option :value="24" label="近 24 小时" />
            <el-option :value="72" label="近 72 小时" />
          </el-select>
        </div>
        <div class="filter-group">
          <label>服务</label>
          <el-select v-model="service" clearable filterable placeholder="全部服务" @change="onFilterChange" style="width:180px">
            <el-option v-for="s in serviceList" :key="s" :value="s" :label="s" />
          </el-select>
        </div>
        <div class="filter-group">
          <label>资产</label>
          <el-select v-model="assetId" clearable filterable placeholder="全部资产" @change="onFilterChange" style="width:180px">
            <el-option v-for="a in assetList" :key="a.id" :value="a.id" :label="a.name" />
          </el-select>
        </div>
        <el-button type="primary" @click="loadAll" :loading="loading" icon="Search">查询</el-button>
        <el-button @click="loadAll" :loading="loading" icon="Refresh" />
        <el-button type="warning" @click="aiDeepAnalysis" :loading="aiLoading" icon="MagicStick" style="margin-left:8px">AI 深度分析</el-button>
        <el-switch v-model="autoRefresh" active-text="自动刷新" inline-prompt size="small" style="margin-left:4px" />
        <span class="toolbar-hint">点击时间轴泳道图或拓扑节点可联动过滤</span>
      </div>
    </div>

    <!-- RCA 建议 -->
    <div v-if="result && result.rca_suggestions && result.rca_suggestions.length" class="rca-bar">
      <span class="rca-icon">💡</span>
      <span v-for="(rca, i) in result.rca_suggestions" :key="i" class="rca-item">
        <span class="rca-badge" :class="rca.confidence">{{ rca.confidence }}</span>
        {{ rca.message }}
      </span>
    </div>

    <!-- 概览统计 -->
    <div v-if="result" class="summary-cards">
      <div class="summary-card alert-card" @click="activeTab='alerts'">
        <div class="sc-body"><div class="sc-value">{{ result.summary.total_alerts }}</div><div class="sc-label">告警</div></div>
      </div>
      <div class="summary-card metric-card" @click="activeTab='metrics'">
        <div class="sc-body"><div class="sc-value">{{ result.summary.total_metric_anomalies }}</div><div class="sc-label">指标异常</div></div>
      </div>
      <div class="summary-card log-card" @click="activeTab='logs'">
        <div class="sc-body"><div class="sc-value">{{ result.summary.total_log_anomalies }}</div><div class="sc-label">日志异常</div></div>
      </div>
      <div class="summary-card trace-card" @click="activeTab='traces'">
        <div class="sc-body"><div class="sc-value">{{ result.summary.total_trace_anomalies }}</div><div class="sc-label">链路异常</div></div>
      </div>
      <div class="summary-card asset-card" @click="activeTab='assets'">
        <div class="sc-body"><div class="sc-value">{{ result.summary.correlated_assets }}</div><div class="sc-label">关联资产</div></div>
      </div>
      <div class="summary-card signal-card" @click="activeTab='assets'">
        <div class="sc-body"><div class="sc-value">{{ result.summary.multi_signal_assets }}</div><div class="sc-label">多信号资产</div></div>
      </div>
    </div>

    <!-- 图表区 -->
    <div v-if="!loading || result" class="charts-row">
      <div class="chart-panel timeline-panel">
        <div class="panel-title">信号时间轴</div>
        <div ref="timelineChartRef" class="chart-container"></div>
      </div>
      <div class="chart-panel topology-panel">
        <div class="panel-title">服务拓扑</div>
        <div ref="topologyChartRef" class="chart-container"></div>
      </div>
    </div>

    <!-- 详情 Tab -->
    <div v-if="result" class="detail-panel">
      <el-tabs v-model="activeTab" class="detail-tabs">
        <el-tab-pane label="告警" name="alerts">
          <div class="tab-toolbar"><span>共 {{ result.alerts.length }} 条</span></div>
          <el-table :data="result.alerts" stripe size="small" max-height="360" style="width:100%">
            <el-table-column prop="severity" label="严重度" width="90">
              <template #default="{row}"><span class="severity-badge" :class="row.severity">{{ row.severity }}</span></template>
            </el-table-column>
            <el-table-column prop="metric_name" label="指标" width="120" />
            <el-table-column prop="actual_value" label="实际值" width="90">
              <template #default="{row}">{{ row.actual_value != null ? Number(row.actual_value).toFixed(2) : '-' }}</template>
            </el-table-column>
            <el-table-column prop="threshold" label="阈值" width="90">
              <template #default="{row}">{{ row.threshold != null ? Number(row.threshold).toFixed(2) : '-' }}</template>
            </el-table-column>
            <el-table-column prop="message" label="消息" min-width="200" show-overflow-tooltip />
            <el-table-column prop="created_at" label="时间" width="160">
              <template #default="{row}">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="指标异常" name="metrics">
          <div class="tab-toolbar"><span>共 {{ result.metric_anomalies.length }} 条</span></div>
          <el-table :data="result.metric_anomalies" stripe size="small" max-height="360" style="width:100%">
            <el-table-column prop="metric_name" label="指标" width="130" />
            <el-table-column prop="value" label="当前值" width="90">
              <template #default="{row}">{{ row.value }}</template>
            </el-table-column>
            <el-table-column prop="mean" label="均值" width="90" />
            <el-table-column prop="std" label="标准差" width="80" />
            <el-table-column prop="z_score" label="Z-Score" width="90">
              <template #default="{row}"><span :class="Math.abs(row.z_score)>3.5?'danger-text':'warn-text'">{{ row.z_score }}</span></template>
            </el-table-column>
            <el-table-column prop="severity" label="严重度" width="90">
              <template #default="{row}"><span class="severity-badge" :class="row.severity">{{ row.severity }}</span></template>
            </el-table-column>
            <el-table-column prop="timestamp" label="时间" width="160">
              <template #default="{row}">{{ formatTime(row.timestamp) }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="日志异常" name="logs">
          <div class="tab-toolbar"><span>共 {{ result.log_anomalies.length }} 条</span></div>
          <el-table :data="result.log_anomalies" stripe size="small" max-height="360" style="width:100%">
            <el-table-column prop="rule_name" label="规则" width="140" />
            <el-table-column prop="keyword" label="关键词" width="120">
              <template #default="{row}"><code>{{ row.keyword }}</code></template>
            </el-table-column>
            <el-table-column prop="severity" label="严重度" width="90">
              <template #default="{row}"><span class="severity-badge" :class="row.severity">{{ row.severity }}</span></template>
            </el-table-column>
            <el-table-column prop="message" label="消息" min-width="250" show-overflow-tooltip />
            <el-table-column prop="created_at" label="时间" width="160">
              <template #default="{row}">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="链路异常" name="traces">
          <div class="trace-summary-bar">
            <span>P95 延迟: <strong>{{ result.trace_anomalies.duration_p95_ms }}ms</strong></span>
            <span>错误率: <strong :class="result.trace_anomalies.error_rate_pct>5?'danger-text':''">{{ result.trace_anomalies.error_rate_pct }}%</strong></span>
            <span>总异常: <strong>{{ result.trace_anomalies.total_traces }}</strong></span>
          </div>
          <el-tabs type="border-card" size="small" class="inner-tabs">
            <el-tab-pane label="慢调用">
              <el-table :data="result.trace_anomalies.slow_traces" stripe size="small" max-height="280" style="width:100%">
                <el-table-column prop="service_name" label="服务" width="130" />
                <el-table-column prop="operation_name" label="操作" width="160" show-overflow-tooltip />
                <el-table-column prop="duration_ms" label="耗时(ms)" width="90">
                  <template #default="{row}"><span :class="row.z_score>3?'danger-text':'warn-text'">{{ row.duration_ms }}</span></template>
                </el-table-column>
                <el-table-column prop="z_score" label="Z-Score" width="80" />
                <el-table-column prop="started_at" label="时间" width="150">
                  <template #default="{row}">{{ formatTime(row.started_at) }}</template>
                </el-table-column>
                <el-table-column label="操作" width="70" fixed="right">
                  <template #default="{row}"><el-button size="small" @click="showTraceDetail(row.trace_id)">详情</el-button></template>
                </el-table-column>
              </el-table>
            </el-tab-pane>
            <el-tab-pane label="错误链路">
              <el-table :data="result.trace_anomalies.error_traces" stripe size="small" max-height="280" style="width:100%">
                <el-table-column prop="service_name" label="服务" width="130" />
                <el-table-column prop="operation_name" label="操作" width="160" show-overflow-tooltip />
                <el-table-column prop="status" label="状态" width="90">
                  <template #default="{row}"><span class="status-badge" :class="row.status">{{ row.status }}</span></template>
                </el-table-column>
                <el-table-column prop="started_at" label="时间" width="150">
                  <template #default="{row}">{{ formatTime(row.started_at) }}</template>
                </el-table-column>
                <el-table-column label="操作" width="70" fixed="right">
                  <template #default="{row}"><el-button size="small" @click="showTraceDetail(row.trace_id)">详情</el-button></template>
                </el-table-column>
              </el-table>
            </el-tab-pane>
            <el-tab-pane label="高错误率服务">
              <el-table :data="result.trace_anomalies.high_error_services" stripe size="small" max-height="280" style="width:100%">
                <el-table-column prop="service_name" label="服务" width="150" />
                <el-table-column prop="error_rate" label="错误率" width="90">
                  <template #default="{row}"><span :class="row.error_rate>20?'danger-text':'warn-text'">{{ row.error_rate }}%</span></template>
                </el-table-column>
                <el-table-column prop="error_count" label="错误数" width="80" />
                <el-table-column prop="total_count" label="总调用" width="80" />
              </el-table>
            </el-tab-pane>
          </el-tabs>
        </el-tab-pane>

        <el-tab-pane label="关联资产" name="assets">
          <div class="tab-toolbar"><span>共 {{ result.correlated_assets.length }} 个关联资产，{{ result.summary.multi_signal_assets }} 个涉及多类信号</span></div>
          <el-table :data="result.correlated_assets" stripe size="small" max-height="400" style="width:100%">
            <el-table-column prop="asset_name" label="资产名" width="140" />
            <el-table-column prop="ci_type" label="类型" width="80" />
            <el-table-column prop="health_status" label="健康状态" width="100">
              <template #default="{row}"><span class="health-dot" :class="row.health_status" />{{ row.health_status }}</template>
            </el-table-column>
            <el-table-column prop="cross_signal_score" label="关联评分" width="90">
              <template #default="{row}"><span class="score-value" :class="row.cross_signal_score>=10?'high':row.cross_signal_score>=5?'mid':''">{{ row.cross_signal_score }}</span></template>
            </el-table-column>
            <el-table-column prop="signal_count" label="信号种类" width="80" />
            <el-table-column prop="alerts" label="告警" width="60" />
            <el-table-column prop="metric_anomalies" label="指标异常" width="70" />
            <el-table-column prop="log_anomalies" label="日志异常" width="70" />
            <el-table-column prop="trace_anomalies" label="链路异常" width="70" />
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- Trace 详情抽屉 -->
    <el-drawer v-model="traceDetailVisible" title="链路详情" size="50%" direction="rtl">
      <div v-if="traceDetailLoading" class="loading-state"><div class="loading-spinner"></div></div>
      <div v-else-if="traceDetailData" class="trace-detail">
        <div class="td-header"><span class="td-label">Trace ID</span><code class="trace-id-full">{{ traceDetailData.trace_id }}</code></div>
        <div class="td-header"><span class="td-label">Span 数</span><span>{{ traceDetailData.total_spans }}</span></div>
        <el-table :data="traceDetailData.spans" stripe size="small" style="width:100%">
          <el-table-column prop="span_id" label="Span ID" width="110"><template #default="{row}"><code>{{ (row.span_id||'').substring(0,12) }}...</code></template></el-table-column>
          <el-table-column prop="service_name" label="服务" width="120" />
          <el-table-column prop="operation_name" label="操作" width="160" show-overflow-tooltip />
          <el-table-column prop="duration_ms" label="耗时(ms)" width="80">
            <template #default="{row}"><span :class="row.status!=='OK'?'danger-text':''">{{ row.duration_ms }}</span></template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="80">
            <template #default="{row}"><span class="status-badge" :class="row.status">{{ row.status }}</span></template>
          </el-table-column>
          <el-table-column prop="started_at" label="时间" width="150"><template #default="{row}">{{ row.started_at }}</template></el-table-column>
        </el-table>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import * as echarts from 'echarts'
import request from '@/api/request'
import { ElMessage } from 'element-plus'

const hours = ref(1)
const service = ref('')
const assetId = ref(0)
const loading = ref(false)
const activeTab = ref('alerts')
const result = ref(null)
const aiLoading = ref(false)
const serviceList = ref([])
const assetList = ref([])
const assetMap = ref({})

const timelineChartRef = ref(null)
const topologyChartRef = ref(null)
let timelineChart = null
let topologyChart = null

const traceDetailVisible = ref(false)
const traceDetailLoading = ref(false)
const traceDetailData = ref(null)

let ws = null
let wsReconnectTimer = null
const autoRefresh = ref(false)

function connectWs() {
  if (ws && ws.readyState === WebSocket.OPEN) return
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const token = localStorage.getItem('aiops-token') || ''
  ws = new WebSocket(protocol + '//' + location.host + '/ws/correlation?token=' + token)
  ws.onopen = () => { console.log('[WS] 关联分析频道已连接') }
  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      if (msg.type === 'heartbeat' && autoRefresh.value) {
        loadAll()
      }
    } catch (err) {}
  }
  ws.onclose = () => {
    wsReconnectTimer = setTimeout(() => { connectWs() }, 15000)
  }
  ws.onerror = () => { if (ws) ws.close() }
}

function disconnectWs() {
  if (wsReconnectTimer) clearTimeout(wsReconnectTimer)
  if (ws) { ws.close(); ws = null }
}

function formatTime(isoStr) {
  if (!isoStr) return '-'
  try { return new Date(isoStr).toLocaleString('zh-CN', { hour12: false }) }
  catch { return isoStr }
}

async function loadServices() {
  const data = await request.get('/observability/correlation/services', { params: { hours: hours.value } })
  serviceList.value = data.services || []
}

async function loadAssets() {
  const data = await request.get('/observability/correlation/assets', { params: { hours: hours.value } })
  assetList.value = data.assets || []
  assetMap.value = {}
  for (const a of assetList.value) assetMap.value[a.id] = a.name
}

async function loadAll() {
  loading.value = true
  try {
    const params = { hours: hours.value, service: service.value || '', asset_id: assetId.value || 0 }
    const [analyzeRes, timelineRes, topologyRes] = await Promise.all([
      request.get('/observability/correlation/analyze', { params }),
      request.get('/observability/correlation/timeline', { params }),
      request.get('/observability/correlation/topology', { params }),
    ])
    result.value = analyzeRes
    result.value._timeline = timelineRes
    result.value._topology = topologyRes
    await nextTick()
    renderTimelineChart(timelineRes)
    renderTopologyChart(topologyRes)
    ElMessage.success('分析完成: ' + analyzeRes.summary.total_alerts + '告警 ' + analyzeRes.summary.total_metric_anomalies + '指标 ' + analyzeRes.summary.total_log_anomalies + '日志 ' + analyzeRes.summary.total_trace_anomalies + '链路')
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

async function aiDeepAnalysis() {
  aiLoading.value = true
  try {
    const res = await request.post('/agent/correlation-analyze', {
      hours: hours.value,
      service: service.value || '',
      asset_id: assetId.value || 0,
    })
    ElMessage.success('分析请求已发送，即将跳转至 AI 助手')
    window._pendingAgentSessionId = res.session_id
    setTimeout(() => {
      window._navigateTo('agent-chat')
    }, 600)
  } catch (e) {
    ElMessage.error('AI 深度分析失败: ' + (e.message || '未知错误'))
  } finally {
    aiLoading.value = false
  }
}

function onFilterChange() {
  loadAll()
}

function renderTimelineChart(data) {
  if (!timelineChartRef.value) return
  if (!timelineChart) timelineChart = echarts.init(timelineChartRef.value)
  const points = data.timeline || []
  const bucket = data.bucket_minutes || 1
  const timestamps = points.map(p => p.timestamp)
  timelineChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['告警', '指标异常', '日志异常', '链路错误'], top: 0, itemWidth: 10, itemHeight: 8, textStyle: { fontSize: 11 } },
    grid: { left: 45, right: 45, top: 28, bottom: 20 },
    xAxis: { type: 'time', axisLabel: { fontSize: 10 } },
    yAxis: [
      { type: 'value', name: '事件数', nameTextStyle: { fontSize: 10 }, axisLabel: { fontSize: 10 }, splitLine: { lineStyle: { type: 'dashed' } } },
      { type: 'value', name: '链路错误', nameTextStyle: { fontSize: 10 }, axisLabel: { fontSize: 10 }, splitLine: { show: false } },
    ],
    series: [
      { name: '告警', type: 'bar', stack: 'signals', data: timestamps.map((t, i) => [t, points[i].alerts]), itemStyle: { color: '#ef4444' }, barWidth: '70%' },
      { name: '指标异常', type: 'bar', stack: 'signals', data: timestamps.map((t, i) => [t, points[i].metrics]), itemStyle: { color: '#8b5cf6' } },
      { name: '日志异常', type: 'bar', stack: 'signals', data: timestamps.map((t, i) => [t, points[i].logs]), itemStyle: { color: '#f59e0b' } },
      { name: '链路错误', type: 'line', yAxisIndex: 1, data: timestamps.map((t, i) => [t, points[i].traces]), itemStyle: { color: '#3b82f6' }, lineStyle: { width: 2 }, symbol: 'circle', symbolSize: 4 },
    ],
  }, true)
  timelineChart.off('click')
  timelineChart.on('click', (params) => {
    if (params.componentType === 'series') {
      const ts = params.data[0]
      ElMessage.info('选中时间: ' + new Date(ts).toLocaleString('zh-CN'))
    }
  })
}

function renderTopologyChart(data) {
  if (!topologyChartRef.value) return
  if (!topologyChart) topologyChart = echarts.init(topologyChartRef.value)
  const nodes = (data.nodes || []).map(n => ({
    id: n.id,
    name: n.name,
    value: n.call_count,
    symbolSize: Math.max(20, Math.min(60, (n.call_count || 1) * 2)),
    itemStyle: {
      color: n.error_rate > 20 ? '#ef4444' : n.error_rate > 5 ? '#f59e0b' : n.call_count > 0 ? '#10b981' : '#9ca3af',
    },
    label: { show: true, fontSize: 10, fontWeight: 'bold', color: '#1f2937' },
    callCount: n.call_count,
    errorRate: n.error_rate,
    avgDuration: n.avg_duration_ms,
  }))
  const links = (data.edges || []).map(e => ({
    source: e.source, target: e.target, value: e.call_count,
    lineStyle: { color: '#d1d5db', width: Math.max(1, Math.min(4, (e.call_count || 1) / 10)), curveness: 0.2 },
    label: { show: false },
  }))
  if (nodes.length === 0) {
    topologyChart.setOption({ title: { text: '暂无拓扑数据', left: 'center', top: 'center', textStyle: { fontSize: 13, color: '#9ca3af' } } }, true)
    return
  }
  topologyChart.setOption({
    tooltip: {
      trigger: 'item',
      formatter: (p) => {
        if (p.dataType === 'node') return '<strong>' + p.name + '</strong><br/>调用: ' + (p.data.callCount || 0) + '<br/>错误率: ' + (p.data.errorRate || 0) + '%<br/>平均延迟: ' + (p.data.avgDuration || 0) + 'ms'
        return p.data.source + ' → ' + p.data.target + '<br/>调用: ' + (p.data.value || 0)
      }
    },
    series: [{
      type: 'graph', layout: 'force', roam: true, draggable: true,
      data: nodes, links, categories: [{ name: '健康' }, { name: '告警' }, { name: '严重' }],
      edgeSymbol: ['none', 'arrow'], edgeSymbolSize: [0, 8],
      force: { repulsion: 300, edgeLength: 120, layoutAnimation: false },
      lineStyle: { color: 'source', curveness: 0.2, opacity: 0.6 },
      label: { show: true, fontSize: 10, fontWeight: 'bold', color: '#1f2937' },
      emphasis: { focus: 'adjacency', lineStyle: { width: 3 } },
    }],
  }, true)
  topologyChart.off('click')
  topologyChart.on('click', (params) => {
    if (params.dataType === 'node') {
      service.value = params.data.name
      loadAll()
    }
  })
}

async function showTraceDetail(traceId) {
  traceDetailVisible.value = true
  traceDetailLoading.value = true
  try {
    const data = await request.get('/observability/correlation/trace-detail', { params: { trace_id: traceId } })
    traceDetailData.value = data
  } catch (e) {
    ElMessage.error('加载链路详情失败')
    traceDetailData.value = null
  } finally {
    traceDetailLoading.value = false
  }
}

function handleResize() {
  if (timelineChart) timelineChart.resize()
  if (topologyChart) topologyChart.resize()
}

onMounted(async () => {
  await Promise.all([loadServices(), loadAssets()])
  await loadAll()
  connectWs()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  disconnectWs()
  window.removeEventListener('resize', handleResize)
  if (timelineChart) { timelineChart.dispose(); timelineChart = null }
  if (topologyChart) { topologyChart.dispose(); topologyChart = null }
})
</script>

<style scoped>
.obs-correlation { padding: 24px 28px; min-height: 100vh; background: var(--bg-page, #f3f4f6); }
.page-header { margin-bottom: 22px; }
.page-header h1 { font-size: 24px; font-weight: 700; color: #111827; margin: 0 0 2px 0; }
.subtitle { font-size: 13px; color: #6b7280; margin: 0; }

.toolbar { background: #fff; border-radius: 10px; padding: 14px 20px; margin-bottom: 16px; border: 1px solid #e5e7eb; }
.toolbar-row { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.filter-group { display: flex; align-items: center; gap: 8px; }
.filter-group label { font-size: 13px; font-weight: 500; color: #374151; white-space: nowrap; min-width: 4em; }
.toolbar-hint { font-size: 11px; color: #9ca3af; margin-left: auto; }

.summary-cards { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.summary-card { flex: 1; min-width: 110px; background: #fff; border-radius: 10px; padding: 14px 16px; display: flex; align-items: center; gap: 12px; cursor: pointer; transition: box-shadow .2s,transform .2s; border: 1px solid #e5e7eb; border-left: 3px solid #d1d5db; }
.summary-card:hover { box-shadow: 0 4px 14px rgba(0,0,0,.08); transform: translateY(-1px); }
.summary-card.alert-card { border-left-color: #ef4444; }
.summary-card.metric-card { border-left-color: #8b5cf6; }
.summary-card.log-card { border-left-color: #f59e0b; }
.summary-card.trace-card { border-left-color: #3b82f6; }
.summary-card.asset-card { border-left-color: #10b981; }
.summary-card.signal-card { border-left-color: #ec4899; }
.sc-value { font-size: 26px; font-weight: 700; color: #111827; line-height: 1; }
.sc-label { font-size: 12px; color: #6b7280; margin-top: 2px; font-weight: 500; }

.charts-row { display: flex; gap: 14px; margin-bottom: 16px; }
.chart-panel { background: #fff; border-radius: 10px; border: 1px solid #e5e7eb; padding: 14px; flex: 1; min-width: 0; }
.timeline-panel { flex: 1.6; }
.topology-panel { flex: 1; }
.panel-title { font-size: 13px; font-weight: 600; color: #374151; margin-bottom: 10px; }
.chart-container { width: 100%; height: 220px; }

.detail-panel { background: #fff; border-radius: 10px; border: 1px solid #e5e7eb; padding: 14px 18px; }
.detail-tabs :deep(.el-tabs__header) { margin-bottom: 12px; }
.detail-tabs :deep(.el-tabs__item) { font-size: 13px; font-weight: 500; }
.tab-toolbar { margin-bottom: 10px; font-size: 12px; color: #6b7280; }

.trace-summary-bar { display: flex; gap: 20px; padding: 10px 14px; background: #f9fafb; border-radius: 6px; margin-bottom: 12px; font-size: 12px; color: #374151; }
.trace-summary-bar strong { font-weight: 700; font-size: 14px; margin-left: 4px; }

.inner-tabs :deep(.el-tabs__header) { margin-bottom: 10px; }
.inner-tabs :deep(.el-tabs__item) { font-size: 12px; padding: 0 12px; }

.severity-badge { display: inline-block; padding: 1px 8px; border-radius: 8px; font-size: 11px; font-weight: 600; }
.severity-badge.critical, .severity-badge.high { background: #fee2e2; color: #dc2626; }
.severity-badge.warning, .severity-badge.medium { background: #fef3c7; color: #d97706; }
.severity-badge.info, .severity-badge.low { background: #e0f2fe; color: #0369a1; }

.status-badge { display: inline-block; padding: 1px 8px; border-radius: 8px; font-size: 11px; font-weight: 600; }
.status-badge.OK { background: #d1fae5; color: #065f46; }
.status-badge.ERROR, .status-badge.FAIL { background: #fee2e2; color: #dc2626; }
.status-badge.TIMEOUT { background: #fef3c7; color: #d97706; }

.danger-text { color: #dc2626; font-weight: 700; }
.warn-text { color: #d97706; font-weight: 600; }

.health-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
.health-dot.green { background: #10b981; }
.health-dot.yellow { background: #f59e0b; }
.health-dot.red { background: #ef4444; }
.health-dot.unknown { background: #9ca3af; }

.score-value { font-weight: 700; font-size: 14px; padding: 2px 8px; border-radius: 6px; }
.score-value.high { background: #fee2e2; color: #dc2626; }
.score-value.mid { background: #fef3c7; color: #d97706; }
.score-value:not(.high):not(.mid) { color: #374151; }

.loading-state { display: flex; flex-direction: column; align-items: center; padding: 60px; color: #6b7280; gap: 12px; }
.loading-spinner { width: 36px; height: 36px; border: 3px solid #e5e7eb; border-top-color: #3b82f6; border-radius: 50%; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.trace-detail { padding: 0 4px; }
.td-header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; padding: 8px 12px; background: #f9fafb; border-radius: 6px; }
.td-label { font-size: 12px; color: #6b7280; font-weight: 600; flex-shrink: 0; }
.trace-id-full { font-size: 12px; word-break: break-all; font-family: monospace; background: #f3f4f6; padding: 2px 8px; border-radius: 4px; }
code { background: #f3f4f6; padding: 1px 5px; border-radius: 3px; font-size: 11px; font-family: monospace; }

/* RCA 建议条 */
.rca-bar { background: #fff8e1; border: 1px solid #ffe082; border-radius: 8px; padding: 10px 14px; margin-bottom: 14px; display: flex; align-items: flex-start; gap: 10px; flex-wrap: wrap; font-size: 13px; }
.rca-icon { font-size: 16px; line-height: 1.4; }
.rca-item { display: inline-flex; align-items: center; gap: 6px; }
.rca-badge { display: inline-block; padding: 1px 7px; border-radius: 6px; font-size: 10px; font-weight: 700; text-transform: uppercase; }
.rca-badge.high { background: #fee2e2; color: #dc2626; }
.rca-badge.medium { background: #fef3c7; color: #d97706; }
.rca-badge.low { background: #e0f2fe; color: #0369a1; }
</style>
