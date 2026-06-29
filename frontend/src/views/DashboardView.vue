<template>
  <div class="workbench-page-shell">
    <div class="dash-layout">
      <div class="dash-main">
        <!-- Row 1: Stat Cards -->
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-icon primary"><el-icon :size="22"><Monitor /></el-icon></div>
            <div class="stat-info"><div class="stat-value">{{ stats.asset_total }}</div><div class="stat-label">资产总数</div></div>
          </div>
          <div class="stat-card">
            <div class="stat-icon success"><el-icon :size="22"><CircleCheck /></el-icon></div>
            <div class="stat-info"><div class="stat-value">{{ stats.asset_online }}</div><div class="stat-label">在线资产</div></div>
          </div>
          <div class="stat-card">
            <div class="stat-icon warning"><el-icon :size="22"><WarningFilled /></el-icon></div>
            <div class="stat-info"><div class="stat-value">{{ stats.alert_active }}</div><div class="stat-label">活跃告警</div></div>
          </div>
          <div class="stat-card">
            <div class="stat-icon danger"><el-icon :size="22"><Odometer /></el-icon></div>
            <div class="stat-info"><div class="stat-value">{{ stats.rule_count }}</div><div class="stat-label">告警规则</div></div>
          </div>
          <div class="stat-card">
            <div class="stat-icon info"><el-icon :size="22"><Coin /></el-icon></div>
            <div class="stat-info"><div class="stat-value">{{ stats.incident_open }}</div><div class="stat-label">未关闭事件</div></div>
          </div>
          <div class="stat-card">
            <div class="stat-icon" style="background:rgba(139,92,246,0.1);color:#8b5cf6;"><el-icon :size="22"><Connection /></el-icon></div>
            <div class="stat-info"><div class="stat-value">{{ stats.datasource_count }}</div><div class="stat-label">数据源</div></div>
          </div>
          <div class="stat-card">
            <div class="stat-icon" :class="healthColorClass"><el-icon :size="22"><TrendCharts /></el-icon></div>
            <div class="stat-info"><div class="stat-value">{{ stats.health_score }}</div><div class="stat-label">系统健康分</div></div>
          </div>
        </div>

        <!-- Row 2: Charts -->
        <div class="charts-grid">
          <div class="chart-card"><div class="chart-title">资产类型分布</div><div ref="assetChartRef" style="height:240px"></div></div>
          <div class="chart-card"><div class="chart-title">告警严重级别</div><div ref="severityChartRef" style="height:240px"></div></div>
          <div class="chart-card"><div class="chart-title">系统健康评分</div><div ref="healthChartRef" style="height:240px"></div></div>
          <div class="chart-card"><div class="chart-title">近 7 天告警趋势</div><div ref="trendChartRef" style="height:240px"></div></div>
        </div>

        <!-- Row 3: Recent Alerts -->
        <div class="table-card">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
            <span style="font-size:15px;font-weight:600;color:var(--text-primary)">最新告警</span>
          </div>
          <el-table :data="recentAlerts" style="width:100%" size="small" stripe>
            <el-table-column prop="asset_name" label="资产" width="120" show-overflow-tooltip />
            <el-table-column prop="metric_name" label="指标" width="120" show-overflow-tooltip />
            <el-table-column label="级别" width="80">
              <template #default="{ row }">
                <el-tag :type="sevType(row.severity)" size="small" effect="light">{{ row.severity }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.status === 'firing' ? 'danger' : 'warning'" size="small">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="message" label="消息" min-width="200" show-overflow-tooltip />
            <el-table-column label="时间" width="160">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
          </el-table>
          <div v-if="!recentAlerts.length" style="text-align:center;padding:40px 0;color:var(--text-muted);font-size:14px;">暂无告警数据</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { Monitor, CircleCheck, WarningFilled, Odometer, Coin, Connection, TrendCharts } from '@element-plus/icons-vue'
import request from '@/api/request'
import * as echarts from 'echarts'

const assetChartRef = ref(null)
const severityChartRef = ref(null)
const healthChartRef = ref(null)
const trendChartRef = ref(null)
let assetChart, severityChart, healthChart, trendChart

const stats = ref({ asset_total: '—', asset_online: '—', alert_active: '—', rule_count: '—', incident_open: '—', datasource_count: '—', health_score: '—', health_status: 'healthy' })
const recentAlerts = ref([])
const healthColorClass = ref('success')

function sevType(s) {
  return { critical: 'danger', high: 'warning', warning: 'warning', low: 'success', info: 'info' }[s] || 'info'
}
function formatTime(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

onMounted(async () => {
  await loadDashboardData()
})

onBeforeUnmount(() => {
  [assetChart, severityChart, healthChart, trendChart].forEach(c => c?.dispose())
})

async function loadDashboardData() {
  try {
    const data = await request.get('/api/dashboard/data')
    stats.value = data.stats || stats.value
    recentAlerts.value = data.recent_alerts || []

    const hs = stats.value.health_score
    if (hs !== '—') {
      if (hs >= 80) healthColorClass.value = 'success'
      else if (hs >= 60) healthColorClass.value = 'warning'
      else healthColorClass.value = 'danger'
    }

    nextTick(() => {
      renderAssetChart(data.asset_type_distribution || [])
      renderSeverityChart(data.severity_distribution || [])
      renderHealthChart(stats.value.health_score)
      renderTrendChart(data.alert_trend || [])
    })
  } catch (e) {
    console.error('load dashboard data:', e)
  }
}

function renderAssetChart(data) {
  if (assetChart) assetChart.dispose()
  if (!assetChartRef.value) return
  assetChart = echarts.init(assetChartRef.value)
  const colors = ['#818cf8','#6366f1','#a5b4fc','#4f46e5','#c4b5fd','#8b5cf6','#a78bfa','#7c3aed']
  assetChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [{
      type: 'pie', radius: ['45%', '70%'], avoidLabelOverlap: true,
      label: { show: true, formatter: '{b}', fontSize: 11, color: '#94a3b8' },
      emphasis: { label: { show: true, fontWeight: 'bold' } },
      data: data.map((d, i) => ({ name: d.type, value: d.count, itemStyle: { color: colors[i % colors.length] } })),
    }],
  })
}

function renderSeverityChart(data) {
  if (severityChart) severityChart.dispose()
  if (!severityChartRef.value) return
  severityChart = echarts.init(severityChartRef.value)
  const colorMap = { critical: '#ef4444', high: '#f97316', warning: '#f59e0b', info: '#3b82f6', low: '#10b981' }
  severityChart.setOption({
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: data.map(d => d.severity), axisLabel: { color: '#94a3b8' } },
    yAxis: { type: 'value', axisLabel: { color: '#94a3b8' } },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    series: [{
      type: 'bar', barWidth: '50%',
      data: data.map(d => ({ value: d.count, itemStyle: { color: colorMap[d.severity] || '#818cf8', borderRadius: [4,4,0,0] } })),
    }],
  })
}

function renderHealthChart(score) {
  if (healthChart) healthChart.dispose()
  if (!healthChartRef.value) return
  healthChart = echarts.init(healthChartRef.value)
  const num = typeof score === 'number' ? score : 0
  healthChart.setOption({
    series: [{
      type: 'gauge', center: ['50%', '55%'], radius: '80%',
      startAngle: 220, endAngle: -40,
      min: 0, max: 100,
      axisLine: {
        lineStyle: {
          width: 18,
          color: [[0.4, '#ef4444'], [0.6, '#f59e0b'], [1, '#10b981']],
        },
      },
      axisTick: { show: false },
      splitLine: { length: 8, lineStyle: { color: '#1e293b', width: 2 } },
      axisLabel: { color: '#94a3b8', fontSize: 10, distance: 20 },
      detail: {
        valueAnimation: true,
        formatter: '{value}',
        color: '#e2e8f0',
        fontSize: 28,
        fontWeight: 700,
        offsetCenter: [0, '60%'],
      },
      title: { offsetCenter: [0, '85%'], fontSize: 12, color: '#94a3b8' },
      data: [{ value: num, name: '健康分' }],
    }],
  })
}

function renderTrendChart(data) {
  if (trendChart) trendChart.dispose()
  if (!trendChartRef.value) return
  trendChart = echarts.init(trendChartRef.value)
  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: data.map(d => d.date.slice(5)), axisLabel: { color: '#94a3b8', fontSize: 11 } },
    yAxis: { type: 'value', axisLabel: { color: '#94a3b8' } },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    series: [{
      type: 'line', smooth: true, symbol: 'circle', symbolSize: 6,
      lineStyle: { color: '#818cf8', width: 2 },
      itemStyle: { color: '#818cf8' },
      areaStyle: { color: 'rgba(129,140,248,0.15)' },
      data: data.map(d => d.count),
    }],
  })
}
</script>

<style scoped>
.dash-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.dash-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}
.stats-grid .stat-card { padding: 16px 18px; margin: 0; }
.stats-grid .stat-icon { width: 44px; height: 44px; font-size: 18px; border-radius: 10px; }
.stats-grid .stat-value { font-size: 22px; }
.stats-grid .stat-label { font-size: 12px; }

.charts-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

@media (max-width: 1200px) {
  .stats-grid { grid-template-columns: repeat(4, 1fr); }
}
@media (max-width: 768px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
  .charts-grid { grid-template-columns: 1fr; }
}

.stat-card {
  background: var(--card-bg);
  border-radius: 12px;
  padding: 20px 24px;
  display: flex;
  align-items: center;
  gap: 16px;
  transition: var(--transition);
  cursor: default;
  position: relative;
  border: 1px solid rgba(148,163,184,0.1);
}
.stat-card::before {
  content: '';
  position: absolute;
  top: 8px; left: -1px;
  width: 3px; height: calc(100% - 16px);
  border-radius: 0 2px 2px 0;
  background: var(--primary-light);
  opacity: 0.4;
}
.stat-card:hover { border-color: rgba(148,163,184,0.2); }
.stat-card .stat-icon {
  width: 56px; height: 56px;
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  font-size: 24px; flex-shrink: 0;
}
.stat-card .stat-icon.primary { background: rgba(99,102,241,0.1); color: var(--primary); }
.stat-card .stat-icon.success { background: rgba(16,185,129,0.1); color: var(--success); }
.stat-card .stat-icon.warning { background: rgba(245,158,11,0.1); color: var(--warning); }
.stat-card .stat-icon.danger { background: rgba(239,68,68,0.1); color: var(--danger); }
.stat-card .stat-icon.info { background: rgba(59,130,246,0.1); color: var(--info); }
.stat-info .stat-value { font-size: 28px; font-weight: 700; color: var(--text-primary); line-height: 1.2; }
.stat-info .stat-label { font-size: 13px; color: var(--text-secondary); margin-top: 4px; }
</style>
