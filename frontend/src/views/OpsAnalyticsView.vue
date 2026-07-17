<template>
  <div class="ops-analytics">
    <!-- 时间范围选择 -->
    <div class="toolbar">
      <el-radio-group v-model="dateRange" @change="loadAll">
        <el-radio-button label="7">近7天</el-radio-button>
        <el-radio-button label="30">近30天</el-radio-button>
        <el-radio-button label="90">近90天</el-radio-button>
      </el-radio-group>
      <el-button :icon="Refresh" circle @click="loadAll" :loading="loading" />
    </div>

    <!-- 核心指标卡片 -->
    <div class="kpi-grid">
      <div class="kpi-card" v-for="kpi in kpiCards" :key="kpi.label">
        <div class="kpi-icon" :style="{ background: kpi.bg }">
          <el-icon :size="22"><component :is="kpi.icon" /></el-icon>
        </div>
        <div class="kpi-body">
          <div class="kpi-value">{{ kpi.value }}</div>
          <div class="kpi-label">{{ kpi.label }}</div>
          <div class="kpi-sub" :class="kpi.trendClass">{{ kpi.sub }}</div>
        </div>
      </div>
    </div>

    <!-- 图表区域 -->
    <div class="chart-grid">
      <!-- 告警趋势 -->
      <div class="chart-card span-2">
        <div class="chart-header">
          <span class="chart-title">告警趋势分析</span>
          <el-tag size="small" type="info">{{ dateRange }}天</el-tag>
        </div>
        <div ref="alertTrendChart" class="chart-body"></div>
      </div>

      <!-- MTTA / MTTR -->
      <div class="chart-card">
        <div class="chart-header">
          <span class="chart-title">MTTR 趋势 (分钟)</span>
        </div>
        <div ref="mttrChart" class="chart-body"></div>
      </div>

      <!-- 自愈效果 -->
      <div class="chart-card">
        <div class="chart-header">
          <span class="chart-title">自愈成功率</span>
        </div>
        <div ref="remediationChart" class="chart-body"></div>
      </div>

      <!-- AI 效能 -->
      <div class="chart-card">
        <div class="chart-header">
          <span class="chart-title">AI 效能趋势</span>
        </div>
        <div ref="aiChart" class="chart-body"></div>
      </div>

      <!-- 通知送达 -->
      <div class="chart-card">
        <div class="chart-header">
          <span class="chart-title">通知送达率</span>
        </div>
        <div ref="notifChart" class="chart-body"></div>
      </div>

      <!-- 工具调用 Top 10 -->
      <div class="chart-card span-2">
        <div class="chart-header">
          <span class="chart-title">工具调用排行 Top 10</span>
        </div>
        <div ref="toolRankChart" class="chart-body"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import request from '@/api/request'
import {
  Refresh, WarningFilled, Timer, CircleCheck, Cpu,
  Bell, TrendCharts, DataAnalysis
} from '@element-plus/icons-vue'

const dateRange = ref('30')
const loading = ref(false)

const overviewData = ref({})
const mttaData = ref({})
const alertTrendData = ref({})
const remediationData = ref({})
const aiData = ref({})
const notifData = ref({})

const alertTrendChart = ref(null)
const mttrChart = ref(null)
const remediationChart = ref(null)
const aiChart = ref(null)
const notifChart = ref(null)
const toolRankChart = ref(null)
const charts = []

const kpiCards = ref([])

function buildKPIs() {
  const o = overviewData.value
  const r = o.remediation || {}
  const ai = o.ai || {}
  kpiCards.value = [
    {
      label: '活跃告警', value: o.alerts?.active ?? 0,
      sub: `近${dateRange.value}天 ${o.alerts?.['total_' + dateRange.value + 'd'] ?? 0} 条`,
      icon: WarningFilled, bg: 'rgba(239,68,68,0.12)', trendClass: ''
    },
    {
      label: '平均 MTTR (分钟)', value: mttaData.value.avg_mttr_min ?? 0,
      sub: `已恢复 ${mttaData.value.resolved_count ?? 0} 条`,
      icon: Timer, bg: 'rgba(99,102,241,0.12)', trendClass: ''
    },
    {
      label: '自愈成功率', value: (r.success_rate ?? 0) + '%',
      sub: `成功 ${r.success_30d ?? 0} / ${r.total_30d ?? 0}`,
      icon: CircleCheck, bg: 'rgba(16,185,129,0.12)', trendClass: ''
    },
    {
      label: 'AI 工具成功率', value: (ai.tool_success_rate ?? 0) + '%',
      sub: `调用 ${ai.tool_calls_30d ?? 0} 次`,
      icon: Cpu, bg: 'rgba(245,158,11,0.12)', trendClass: ''
    },
    {
      label: '未关闭故障', value: o.incidents?.open ?? 0,
      sub: `近${dateRange.value}天 ${o.incidents?.total_30d ?? 0} 个`,
      icon: TrendCharts, bg: 'rgba(168,85,247,0.12)', trendClass: ''
    },
    {
      label: '通知成功率', value: (notifData.value.success_rate ?? 0) + '%',
      sub: `成功 ${notifData.value.success ?? 0} / ${notifData.value.total ?? 0}`,
      icon: Bell, bg: 'rgba(14,165,233,0.12)', trendClass: ''
    },
  ]
}

async function loadAll() {
  loading.value = true
  try {
    const [ov, mt, at, rm, ai, nf] = await Promise.all([
      request.get('/api/ops-analytics/overview'),
      request.get('/api/ops-analytics/mtta-mttr', { params: { days: dateRange.value } }),
      request.get('/api/ops-analytics/alert-trend', { params: { days: dateRange.value } }),
      request.get('/api/ops-analytics/remediation-effect', { params: { days: dateRange.value } }),
      request.get('/api/ops-analytics/ai-efficiency', { params: { days: dateRange.value } }),
      request.get('/api/ops-analytics/notification-stats', { params: { days: dateRange.value } }),
    ])
    overviewData.value = ov
    mttaData.value = mt
    alertTrendData.value = at
    remediationData.value = rm
    aiData.value = ai
    notifData.value = nf
    buildKPIs()
    await nextTick()
    renderCharts()
  } catch (e) {
    console.error('load analytics:', e)
  } finally {
    loading.value = false
  }
}

function renderCharts() {
  charts.forEach(c => c?.dispose())
  charts.length = 0

  if (alertTrendChart.value) {
    const c = echarts.init(alertTrendChart.value)
    const d = alertTrendData.value
    c.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['严重', '警告', '信息', '已恢复'], top: 0 },
      grid: { left: 40, right: 20, top: 40, bottom: 30 },
      xAxis: { type: 'category', data: d.dates || [], axisLabel: { fontSize: 11 } },
      yAxis: { type: 'value' },
      series: [
        { name: '严重', type: 'line', smooth: true, data: d.critical || [], itemStyle: { color: '#ef4444' }, areaStyle: { opacity: 0.1 } },
        { name: '警告', type: 'line', smooth: true, data: d.warning || [], itemStyle: { color: '#f59e0b' }, areaStyle: { opacity: 0.1 } },
        { name: '信息', type: 'line', smooth: true, data: d.info || [], itemStyle: { color: '#3b82f6' }, areaStyle: { opacity: 0.1 } },
        { name: '已恢复', type: 'line', smooth: true, data: d.resolved || [], itemStyle: { color: '#10b981' } },
      ],
    })
    charts.push(c)
  }

  if (mttrChart.value) {
    const c = echarts.init(mttrChart.value)
    const d = mttaData.value
    c.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 40, right: 20, top: 20, bottom: 30 },
      xAxis: { type: 'category', data: (d.daily || []).map(x => x.date), axisLabel: { fontSize: 11 } },
      yAxis: { type: 'value', name: '分钟' },
      series: [
        { name: 'MTTR', type: 'bar', data: (d.daily || []).map(x => x.mttr_min), itemStyle: { color: '#6366f1', borderRadius: [4, 4, 0, 0] } },
      ],
    })
    charts.push(c)
  }

  if (remediationChart.value) {
    const c = echarts.init(remediationChart.value)
    const d = remediationData.value
    c.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['执行', '成功'], top: 0 },
      grid: { left: 40, right: 20, top: 40, bottom: 30 },
      xAxis: { type: 'category', data: (d.daily || []).map(x => x.date), axisLabel: { fontSize: 11 } },
      yAxis: { type: 'value' },
      series: [
        { name: '执行', type: 'bar', data: (d.daily || []).map(x => x.total), itemStyle: { color: '#a78bfa', borderRadius: [4, 4, 0, 0] } },
        { name: '成功', type: 'bar', data: (d.daily || []).map(x => x.success), itemStyle: { color: '#10b981', borderRadius: [4, 4, 0, 0] } },
      ],
    })
    charts.push(c)
  }

  if (aiChart.value) {
    const c = echarts.init(aiChart.value)
    const d = aiData.value
    c.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['评估', '成功'], top: 0 },
      grid: { left: 40, right: 20, top: 40, bottom: 30 },
      xAxis: { type: 'category', data: (d.daily || []).map(x => x.date), axisLabel: { fontSize: 11 } },
      yAxis: { type: 'value' },
      series: [
        { name: '评估', type: 'line', smooth: true, data: (d.daily || []).map(x => x.total), itemStyle: { color: '#f59e0b' }, areaStyle: { opacity: 0.1 } },
        { name: '成功', type: 'line', smooth: true, data: (d.daily || []).map(x => x.success), itemStyle: { color: '#10b981' } },
      ],
    })
    charts.push(c)
  }

  if (notifChart.value) {
    const c = echarts.init(notifChart.value)
    const d = notifData.value
    c.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 40, right: 20, top: 20, bottom: 30 },
      xAxis: { type: 'category', data: (d.daily || []).map(x => x.date), axisLabel: { fontSize: 11 } },
      yAxis: { type: 'value' },
      series: [
        { name: '发送', type: 'bar', data: (d.daily || []).map(x => x.total), itemStyle: { color: '#0ea5e9', borderRadius: [4, 4, 0, 0] } },
        { name: '成功', type: 'line', smooth: true, data: (d.daily || []).map(x => x.success), itemStyle: { color: '#10b981' } },
      ],
    })
    charts.push(c)
  }

  if (toolRankChart.value) {
    const c = echarts.init(toolRankChart.value)
    const tools = aiData.value.tools?.top_tools || []
    c.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 120, right: 20, top: 20, bottom: 30 },
      xAxis: { type: 'value' },
      yAxis: { type: 'category', data: tools.map(t => t.name).reverse(), axisLabel: { fontSize: 11 } },
      series: [
        { type: 'bar', data: tools.map(t => t.count).reverse(), itemStyle: { color: '#6366f1', borderRadius: [0, 4, 4, 0] } },
      ],
    })
    charts.push(c)
  }
}

function handleResize() {
  charts.forEach(c => c?.resize())
}

onMounted(() => {
  loadAll()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  charts.forEach(c => c?.dispose())
})
</script>

<style scoped>
.ops-analytics { padding: 4px; }
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.kpi-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 10px;
  transition: box-shadow 0.2s;
}
.kpi-card:hover { box-shadow: 0 2px 12px rgba(0,0,0,0.06); }
.kpi-icon {
  width: 48px; height: 48px;
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.kpi-body { flex: 1; min-width: 0; }
.kpi-value {
  font-size: 24px; font-weight: 700;
  color: var(--text-primary, #1f2937);
  line-height: 1.2;
}
.kpi-label {
  font-size: 13px; color: var(--text-secondary, #6b7280);
  margin-top: 2px;
}
.kpi-sub {
  font-size: 11px; color: var(--text-tertiary, #9ca3af);
  margin-top: 2px;
}
.chart-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.chart-card {
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 10px;
  padding: 12px;
}
.chart-card.span-2 { grid-column: span 2; }
.chart-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 8px;
}
.chart-title {
  font-size: 14px; font-weight: 600;
  color: var(--text-primary, #1f2937);
}
.chart-body {
  width: 100%;
  height: 240px;
}
@media (max-width: 1200px) {
  .chart-grid { grid-template-columns: repeat(2, 1fr); }
  .chart-card.span-2 { grid-column: span 2; }
}
@media (max-width: 768px) {
  .chart-grid { grid-template-columns: 1fr; }
  .chart-card.span-2 { grid-column: span 1; }
}
</style>
