<template>
  <div v-if="visible" class="detail-mask" @click.self="$emit('close')">
    <div class="detail-box">
      <div class="detail-head">
        <div class="detail-title">
          <span class="detail-icon">{{ icon }}</span>
          <div>
            <div class="ds-cn">{{ label }}</div>
            <div class="ds-en">{{ name }}<span v-if="unit"> · {{ unit }}</span></div>
          </div>
        </div>
        <div class="detail-actions">
          <button class="d-btn rca" @click="$emit('rca', name)" title="跨域根因分析：自动关联告警+调用链">🔍 AI 根因</button>
          <button class="d-btn" @click="$emit('create-rule')">+ 创建告警规则</button>
          <button class="d-btn ghost" @click="$emit('export')">导出 CSV</button>
          <button class="d-close" @click="$emit('close')">&times;</button>
        </div>
      </div>
      <div class="detail-chart" ref="chartEl"></div>
      <div v-if="latest" class="detail-stats">
        <div class="d-stat"><span class="d-stat-label">当前值</span><span class="d-stat-val" :style="valueStyle">{{ formatValue(latest) }}</span></div>
        <div class="d-stat"><span class="d-stat-label">采集时间</span><span class="d-stat-val">{{ formatTime(latest.timestamp) }}</span></div>
        <div v-if="latest?.count" class="d-stat"><span class="d-stat-label">资产数</span><span class="d-stat-val">{{ latest.count }} 台</span></div>
        <div v-if="threshold" class="d-stat"><span class="d-stat-label">阈值提醒</span><span class="d-stat-val" style="font-size:12px">{{ threshold.warn }} 预警 / {{ threshold.crit }} 严重</span></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { formatValue, formatTime, metricStatus, statusColor, THRESHOLDS } from './metricsUtils.js'

const props = defineProps({
  visible: Boolean,
  name: String,
  label: String,
  icon: String,
  unit: String,
  latest: Object,
  chartData: Object, // {labels, values, series}
  color: String,
})
const emit = defineEmits(['close', 'create-rule', 'export', 'rca'])

const chartEl = ref(null)
let chart = null

const threshold = computed(() => THRESHOLDS[props.name] || null)

const valueStyle = computed(() => {
  const sc = metricStatus(props.name, props.latest)
  const c = statusColor(sc)
  return c ? { color: c, fontWeight: 700 } : {}
})

function draw() {
  if (!chartEl.value || !props.visible) return
  if (chart) { chart.dispose(); chart = null }
  chart = echarts.init(chartEl.value, null, { renderer: 'canvas' })
  const data = props.chartData
  if (!data || !data.labels || data.labels.length < 2) {
    chart.setOption({
      grid: { left: 40, right: 20, top: 20, bottom: 40 },
      xAxis: { type: 'category', show: true }, yAxis: { type: 'value', show: true },
      graphic: [{ type: 'text', left: 'center', top: 'middle', style: { text: '无数据', fill: '#94a3b8', fontSize: 14 } }],
      animation: false,
    })
    return
  }
  const color = props.color || '#6366f1'
  const series = []
  if (props.isAggregate && data.series && data.series.length) {
    data.series.forEach((s, si) => {
      series.push({
        name: s.name, type: 'line', data: s.values, smooth: true, symbol: 'none',
        lineStyle: { color: '#94a3b8', width: 1, opacity: 0.45 }, z: 1,
      })
    })
  }
  series.push({
    name: props.isAggregate ? '聚合' : props.label,
    type: 'line', data: data.values, smooth: true, symbol: 'none',
    lineStyle: { color, width: 2.5 }, z: 3,
    areaStyle: { color: color + '1f' },
  })
  const opt = {
    grid: { left: 50, right: 20, top: 30, bottom: 50 },
    xAxis: { type: 'category', data: data.labels, boundaryGap: false },
    yAxis: { type: 'value' },
    tooltip: { trigger: 'axis' },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { type: 'slider', height: 18, bottom: 8 },
    ],
    legend: series.length > 1 ? { top: 0, type: 'scroll' } : undefined,
    series,
    animation: false,
  }
  if (threshold.value) {
    const markLines = []
    if (threshold.value.warn) markLines.push({ yAxis: threshold.value.warn, lineStyle: { color: '#f59e0b', type: 'dashed' }, label: { formatter: 'warn ' + threshold.value.warn, fontSize: 10 } })
    if (threshold.value.crit) markLines.push({ yAxis: threshold.value.crit, lineStyle: { color: '#ef4444', type: 'dashed' }, label: { formatter: 'crit ' + threshold.value.crit, fontSize: 10 } })
    if (markLines.length) opt.series[series.length - 1].markLine = { symbol: 'none', data: markLines }
  }
  chart.setOption(opt, true)
}

watch(() => [props.visible, props.chartData], () => { nextTick(draw) }, { deep: true })
onMounted(() => nextTick(draw))
onBeforeUnmount(() => { if (chart) chart.dispose() })
</script>

<style scoped>
.detail-mask {
  position: fixed; inset: 0; z-index: 3000;
  background: rgba(0,0,0,0.5);
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
}
.detail-box {
  background: var(--card-bg, #fff);
  border-radius: 16px;
  width: 860px; max-width: 96vw;
  box-shadow: 0 24px 70px rgba(0,0,0,0.35);
  padding: 20px 24px 24px;
  animation: detailIn 0.2s ease;
}
@keyframes detailIn { from { transform: translateY(20px); opacity: 0 } to { transform: translateY(0); opacity: 1 } }
.detail-head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 12px;
}
.detail-title { display: flex; align-items: center; gap: 12px; }
.detail-icon {
  font-size: 1.4rem; width: 44px; height: 44px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 12px; background: rgba(129,140,248,0.12);
}
.ds-cn { font-size: 17px; font-weight: 800; color: var(--text-primary); }
.ds-en { font-size: 12px; color: var(--text-tertiary, #94a3b8); }
.detail-actions { display: flex; align-items: center; gap: 8px; }
.d-btn {
  padding: 6px 14px; border-radius: 8px; border: none; cursor: pointer;
  background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff;
  font-size: 12px; font-weight: 600; font-family: inherit;
}
.d-btn.ghost {
  background: transparent; border: 1px solid rgba(148,163,184,0.3); color: var(--text-secondary);
}
.d-btn.rca { background: linear-gradient(135deg, #0ea5e9, #6366f1); }
.d-close {
  border: none; background: none; font-size: 24px; color: #909399; cursor: pointer; line-height: 1;
}
.detail-chart { width: 100%; height: 380px; }
.detail-chart canvas { width: 100% !important; height: 100% !important; }
.detail-stats {
  display: flex; gap: 24px; margin-top: 14px;
  padding-top: 14px; border-top: 1px solid rgba(148,163,184,0.15);
  flex-wrap: wrap;
}
.d-stat { display: flex; flex-direction: column; gap: 2px; }
.d-stat-label { font-size: 11px; color: var(--text-tertiary, #94a3b8); }
.d-stat-val { font-size: 15px; font-weight: 700; color: var(--text-primary); }
</style>