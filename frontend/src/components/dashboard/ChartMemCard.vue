<template>
  <div ref="chartEl" class="chart-card-body"></div>
</template>
<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'
import request from '@/api/request'
const props = defineProps({ card: Object })
const chartEl = ref(null)
let chart = null
onMounted(async () => {
  chart = echarts.init(chartEl.value)
  try {
    const d = await request.get('/api/dashboard/data')
    const data = d.vm_metrics?.memory_usage || []
    chart.setOption({
      tooltip: { trigger: 'axis', valueFormatter: v => v + '%' },
      grid: { left: 40, right: 12, top: 12, bottom: 22 },
      xAxis: { type: 'category', data: data.map(x => (x.time || '').slice(5, 16)), axisLabel: { color: '#94a3b8', fontSize: 10, rotate: 30 } },
      yAxis: { type: 'value', axisLabel: { color: '#94a3b8', formatter: '{value}%' }, min: 0 },
      series: [{ type: 'line', smooth: true, symbol: 'none', data: data.map(x => x.value), lineStyle: { color: '#10b981', width: 2 }, areaStyle: { color: 'rgba(16,185,129,0.12)' } }],
    })
  } catch {}
})
onBeforeUnmount(() => chart?.dispose())
</script>
<style scoped>
.chart-card-body { width: 100%; height: 100%; }
</style>
