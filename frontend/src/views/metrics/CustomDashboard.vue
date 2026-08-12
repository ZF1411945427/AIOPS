<template>
  <div class="custom-section">
    <div class="custom-header">
      <h2>自定义仪表盘</h2>
      <button class="btn-add btn-sm" @click="$emit('add')">+ 新增卡片</button>
    </div>
    <div v-if="!cards.length" class="custom-empty">编写 PromQL 查询，创建自定义指标卡片，支持拖拽排列和缩放大小</div>
    <div v-else class="custom-grid" ref="gridRef">
      <div v-for="(card, idx) in cards" :key="card.id"
        class="custom-card" :style="cardStyle(card)" draggable="true"
        @dragstart="onDragStart($event, idx)" @dragover.prevent="onDragOver($event, idx)"
        @drop="onDrop($event, idx)" @dragend="onDragEnd">
        <div class="custom-card-header">
          <span class="drag-handle" title="拖拽移动">&#x2261;</span>
          <span class="custom-card-title" :title="card.title">
            <span class="metric-cn">{{ card.title }}</span>
          </span>
          <span class="custom-card-promql-label" @click="$emit('edit', idx)">PromQL</span>
          <button class="card-btn-del" @click="$emit('delete', idx)" title="删除卡片">&times;</button>
        </div>
        <div class="custom-card-chart" :ref="el => setChartRef(card.id, el)"></div>
        <div class="resize-handle" @mousedown.prevent="onResizeStart($event, idx)" title="拖拽缩放"></div>
      </div>
    </div>
    <div v-if="loading" class="custom-loading">加载中...</div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  cards: { type: Array, default: () => [] },
  loading: Boolean,
})
const emit = defineEmits(['add', 'edit', 'delete', 'reorder', 'resize'])

const gridRef = ref(null)
const chartRefs = {}
const charts = {}
let dragIdx = null

function setChartRef(id, el) {
  if (el) chartRefs[id] = el
}

function cardStyle(card) {
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
  const items = [...props.cards]
  const item = items.splice(dragIdx, 1)[0]
  items.splice(idx, 0, item)
  dragIdx = idx
  emit('reorder', items)
}

function onDrop(e) {
  e.preventDefault()
  dragIdx = null
}

function onDragEnd() {
  dragIdx = null
}

function onResizeStart(e, idx) {
  const card = props.cards[idx]
  if (!card) return
  const startX = e.clientX, startY = e.clientY
  const startW = card.w || 2, startH = card.h || 1
  const gridEl = gridRef.value
  if (!gridEl) return
  const gridRect = gridEl.getBoundingClientRect()
  const colW = gridRect.width / 4
  function onMove(ev) {
    const dx = ev.clientX - startX, dy = ev.clientY - startY
    emit('resize', idx, { w: Math.max(1, Math.min(4, Math.round(startW + dx / colW))), h: Math.max(1, Math.min(2, Math.round(startH + dy / 60))) })
  }
  function onUp() {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

function drawChart(id, series) {
  const canvas = chartRefs[id]
  if (!canvas) return
  if (charts[id]) { charts[id].dispose(); delete charts[id] }
  charts[id] = echarts.init(canvas, null, { renderer: 'canvas' })
  if (!series || !series.length) {
    charts[id].setOption({
      grid: { left: 0, right: 0, top: 0, bottom: 0 },
      xAxis: { show: false }, yAxis: { show: false },
      graphic: [{ type: 'text', left: 'center', top: 'center', style: { text: '无数据', fill: '#94a3b8', fontSize: 12 } }],
      animation: false,
    })
    return
  }
  const maxLen = Math.max(...series.map(s => s.values?.length || 0))
  if (maxLen < 2) {
    charts[id].setOption({
      grid: { left: 0, right: 0, top: 0, bottom: 0 },
      xAxis: { show: false }, yAxis: { show: false },
      graphic: [{ type: 'text', left: 'center', top: 'center', style: { text: '数据不足', fill: '#94a3b8', fontSize: 12 } }],
      animation: false,
    })
    return
  }
  const labels = series[0].values.map(d => {
    const t = new Date(d.time)
    return `${t.getHours().toString().padStart(2, '0')}:${t.getMinutes().toString().padStart(2, '0')}`
  })
  const colorPalette = ['#6366f1','#ec4899','#14b8a6','#f97316','#8b5cf6','#06b6d4','#84cc16','#ef4444']
  charts[id].setOption({
    grid: { left: 0, right: 0, top: 2, bottom: 0 },
    xAxis: { type: 'category', data: labels, show: false },
    yAxis: { type: 'value', show: false },
    tooltip: { trigger: 'axis', show: false },
    series: series.map((s, si) => ({
      name: s.name, type: 'line', data: s.values.map(v => v.value),
      smooth: true, symbol: 'none',
      lineStyle: { color: colorPalette[si % colorPalette.length], width: 1.5 },
      areaStyle: { color: colorPalette[si % colorPalette.length] + '20' },
    })),
    animation: false,
  })
}

function updateCharts(chartData) {
  if (!chartData) return
  for (const [id, series] of Object.entries(chartData)) {
    drawChart(id, series)
  }
}

onBeforeUnmount(() => {
  Object.values(charts).forEach(c => c?.dispose())
})

defineExpose({ updateCharts })
</script>

<style scoped>
.custom-section { margin-top: 32px; padding-top: 24px; border-top: 1px solid rgba(148,163,184,0.15); }
.custom-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.custom-header h2 { font-size: 16px; font-weight: 700; color: var(--text-primary); margin: 0; }
.custom-empty { padding: 40px 0; text-align: center; color: var(--text-muted); font-size: 14px; }
.custom-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.custom-card {
  background: var(--card-bg); border: 1px solid rgba(148,163,184,0.12);
  border-radius: 12px; display: flex; flex-direction: column;
  position: relative; transition: border-color 0.2s; min-height: 200px;
}
.custom-card:hover { border-color: rgba(148,163,184,0.3); }
.custom-card-header {
  display: flex; align-items: center; gap: 8px; padding: 10px 12px 6px;
  font-size: 13px; font-weight: 600; color: var(--text-primary); user-select: none;
}
.drag-handle { cursor: grab; color: var(--text-muted); font-size: 18px; line-height: 1; padding: 0 2px; }
.drag-handle:active { cursor: grabbing; }
.custom-card-title {
  flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.custom-card-title .metric-cn { font-size: 13px; }
.custom-card-promql-label {
  font-size: 10px; font-weight: 500; padding: 1px 6px; border-radius: 4px;
  background: rgba(99, 102, 241, 0.1); color: var(--primary, #6366f1); cursor: pointer;
}
.card-btn-del {
  width: 22px; height: 22px; border: none; background: transparent;
  color: var(--text-muted); font-size: 16px; cursor: pointer; border-radius: 4px;
  display: flex; align-items: center; justify-content: center; line-height: 1;
}
.card-btn-del:hover { background: rgba(239, 68, 68, 0.1); color: #ef4444; }
.custom-card-chart { flex: 1; min-height: 120px; padding: 0 8px 8px; }
.custom-card-chart canvas { width: 100% !important; height: 100% !important; }
.resize-handle {
  position: absolute; bottom: 0; right: 0; width: 16px; height: 16px;
  cursor: nwse-resize; opacity: 0; transition: opacity 0.2s;
}
.resize-handle::after {
  content: ''; position: absolute; bottom: 3px; right: 3px;
  width: 8px; height: 8px;
  border-right: 2px solid var(--text-muted); border-bottom: 2px solid var(--text-muted);
}
.custom-card:hover .resize-handle { opacity: 0.6; }
.resize-handle:hover { opacity: 1 !important; }
.btn-add {
  padding: 7px 16px; border-radius: 8px; border: none;
  background: var(--primary, #6366f1); color: #fff; font-size: 13px;
  font-weight: 600; cursor: pointer; font-family: inherit; transition: background 0.2s;
}
.btn-add:hover { background: var(--primary-light, #818cf8); }
.btn-sm { padding: 5px 12px; font-size: 12px; }
.custom-loading { text-align: center; padding: 20px; color: var(--text-muted); }
</style>