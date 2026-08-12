<template>
  <div class="metric-card" :class="[selected ? 'card-selected' : '', isOffline ? 'offline' : '', statusClass ? 'status-' + statusClass : '']" @click="$emit('drill')">
    <div class="card-check" @click.stop>
      <input type="checkbox" :checked="selected" @change="$emit('toggle-select', name)" />
    </div>
    <div class="top">
      <div class="icon" :style="iconStyle">{{ icon }}</div>
      <div class="info">
        <div class="name" :title="`${label} · ${name}`">
          <span class="metric-cn">{{ label }}</span>
          <span class="metric-en">{{ name }}</span>
          <span v-if="isOffline" class="offline-badge">离线</span>
        </div>
        <div v-if="trend" class="trend-badge" :style="{ color: TREND_COLORS[trend.trend] || '#94a3b8' }" :title="'趋势: ' + trend.trend + ' · 相对变化 ' + trend.rel_change_pct + '%'">
          <span class="trend-icon">{{ TREND_ICONS[trend.trend] || '❓' }}</span>
          <span class="trend-text">{{ TREND_CN_RAW[trend.trend] || trend.trend }}</span>
          <span v-if="trend.rel_change_pct" class="trend-pct">{{ trend.rel_change_pct > 0 ? '+' : '' }}{{ trend.rel_change_pct }}%</span>
        </div>
        <div class="value" :class="{ loading: !latest }">
          <template v-if="isAggregate">
            <span class="agg-badge">{{ aggregateLabel }}</span>
            <span :style="valueStyle">{{ latest ? formatValue(latest) : '加载中' }}</span>
            <span class="unit" v-if="latest?.unit">{{ latest.unit }}</span>
            <span class="count-badge" v-if="latest?.count > 0">({{ latest.count }} 台)</span>
          </template>
          <template v-else>
            <span :style="valueStyle">{{ latest ? formatValue(latest) : '加载中' }}</span>
            <span class="unit" v-if="latest?.unit">{{ latest.unit }}</span>
          </template>
        </div>
        <div v-if="latest?.timestamp" class="last-collect">最后采集: {{ formatTime(latest.timestamp) }}</div>
      </div>
    </div>
    <div class="chart-wrap" ref="chartEl"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, computed } from 'vue'
import * as echarts from 'echarts'
import { formatValue, formatTime, metricStatus, statusColor } from './metricsUtils.js'

const TREND_ICONS = { rising: '📈', falling: '📉', steady: '➡️', volatile: '〰️', spike: '⚡', unknown: '❓' }
const TREND_COLORS = { rising: '#ef4444', falling: '#22c55e', steady: '#94a3b8', volatile: '#f59e0b', spike: '#dc2626', unknown: '#94a3b8' }
const TREND_CN_RAW = { rising: '持续上升', falling: '持续下降', steady: '平稳', volatile: '剧烈波动', spike: '频繁突刺', unknown: '数据不足' }

const props = defineProps({
  name: String,
  label: String,
  icon: { type: String, default: '📊' },
  latest: Object,
  isAggregate: Boolean,
  aggregateLabel: { type: String, default: '' },
  isOffline: Boolean,
  selected: Boolean,
  color: { type: String, default: '#6366f1' },
  chartData: { type: Object, default: null },
  trend: { type: Object, default: null },
})

const emit = defineEmits(['toggle-select', 'drill'])

const chartEl = ref(null)
let chart = null

const statusClass = computed(() => {
  const v = props.latest
  if (!v) return null
  return metricStatus(props.name, v)
})

const valueStyle = computed(() => {
  const sc = statusClass.value
  if (!sc) return {}
  const c = statusColor(sc)
  if (!c) return {}
  return { color: c, fontWeight: 700 }
})

const iconStyle = computed(() => {
  const sc = statusClass.value
  if (!sc) return {}
  const c = statusColor(sc)
  if (!c) return {}
  return { background: c + '18', color: c }
})

function drawChart(data) {
  if (!chartEl.value) return
  if (chart) { chart.dispose(); chart = null }
  chart = echarts.init(chartEl.value, null, { renderer: 'canvas' })
  if (!data || !data.labels || data.labels.length < 2) {
    chart.setOption({
      grid: { left: 0, right: 0, top: 0, bottom: 0 },
      xAxis: { show: false }, yAxis: { show: false },
      graphic: [{ type: 'text', left: 'center', top: 'center', style: { text: data ? '无数据' : '加载中', fill: '#94a3b8', fontSize: 12 } }],
      animation: false,
    })
    return
  }
  const color = props.color
  chart.setOption({
    grid: { left: 0, right: 0, top: 2, bottom: 0 },
    xAxis: { type: 'category', data: data.labels, show: false },
    yAxis: { type: 'value', show: false },
    tooltip: { trigger: 'axis', show: false },
    series: [{
      type: 'line', data: data.values, smooth: true, symbol: 'none',
      lineStyle: { color, width: 1.5 },
      areaStyle: { color: color + '25' },
    }],
    animation: false,
  })
}

watch(() => props.chartData, (data) => drawChart(data), { deep: true })
onMounted(() => { if (props.chartData) drawChart(props.chartData) })
onBeforeUnmount(() => { if (chart) chart.dispose() })
</script>

<style scoped>
.metric-card {
  background: var(--card-bg);
  border: 1px solid rgba(148,163,184,0.12);
  border-radius: 12px;
  padding: 16px;
  position: relative;
  overflow: hidden;
  transition: all 0.2s;
  cursor: pointer;
}
.metric-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; height: 2px;
  background: var(--primary-light, #818cf8);
  opacity: 0;
  transition: opacity 0.2s;
}
.metric-card:hover {
  border-color: rgba(148,163,184,0.25);
  transform: translateY(-1px);
}
.metric-card:hover::before { opacity: 1; }
.metric-card.card-selected {
  border-color: #6366f1;
  box-shadow: 0 0 0 1px rgba(99,102,241,0.35), 0 4px 12px rgba(99,102,241,0.12);
}
.metric-card.offline { opacity: 0.85; }
.metric-card.status-critical { border-left: 3px solid #ef4444; }
.metric-card.status-warning { border-left: 3px solid #f59e0b; }
.metric-card.status-normal { border-left: 3px solid #22c55e; }
.metric-card .card-check {
  position: absolute; top: 8px; right: 8px; z-index: 2;
  display: flex; align-items: center; gap: 4px;
}
.metric-card .card-check input {
  width: 14px; height: 14px; margin: 0; cursor: pointer; accent-color: #6366f1;
}
.metric-card .top { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.metric-card .icon {
  font-size: 1.2rem;
  width: 38px; height: 38px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 10px;
  background: rgba(129,140,248,0.1);
  flex-shrink: 0;
  transition: all 0.3s;
}
.metric-card .info { flex: 1; min-width: 0; }
.metric-card .name {
  font-size: 0.75rem; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: 0.5px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  line-height: 1.35;
}
.metric-cn {
  display: block; font-size: 0.78rem; font-weight: 600;
  color: var(--text-primary); text-transform: none; letter-spacing: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.metric-en {
  display: block; font-size: 0.68rem;
  color: var(--text-tertiary, #94a3b8); opacity: 0.8;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.metric-card .value {
  font-size: 1.5rem; font-weight: 700; color: var(--text-primary);
  line-height: 1.2;
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  transition: color 0.3s;
}
.metric-card .value.loading { color: var(--text-muted); font-size: 1rem; }
.metric-card .unit { font-size: 0.75rem; color: var(--text-secondary); font-weight: 400; }
.agg-badge {
  display: inline-block; padding: 1px 6px; font-size: 10px; font-weight: 600;
  background: rgba(99, 102, 241, 0.15); color: var(--primary, #6366f1);
  border-radius: 4px; text-transform: uppercase;
}
.count-badge { font-size: 11px; color: var(--text-muted); font-weight: 400; }
.offline-badge {
  display: inline-block; padding: 1px 6px; margin-left: 6px; font-size: 11px;
  background: rgba(239, 68, 68, 0.12); color: #ef4444; border-radius: 4px; vertical-align: middle;
}
.trend-badge {
  display: inline-flex; align-items: center; gap: 3px; margin-left: 6px;
  font-size: 11px; font-weight: 600; white-space: nowrap;
}
.trend-icon { font-size: 12px; }
.trend-text { font-size: 10px; }
.trend-pct { font-size: 10px; padding: 0 4px; border-radius: 3px; background: rgba(0,0,0,0.06); }
.last-collect { font-size: 11px; color: var(--text-secondary, #94a3b8); margin-top: 2px; }
.metric-card .chart-wrap { position: relative; width: 100%; height: 130px; }
.metric-card .chart-wrap canvas { width: 100% !important; height: 100% !important; }
</style>