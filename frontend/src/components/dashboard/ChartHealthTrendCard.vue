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
    chart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 30, right: 10, top: 10, bottom: 20 },
      xAxis: { type: 'category', data: d.alert_trend?.map(x => x.date) || [], axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value', min: 0, max: 100 },
      series: [{ type: 'line', smooth: true, data: [85, 82, 88, 90, 87, 92, 89], itemStyle: { color: '#10b981' }, areaStyle: { opacity: 0.15 } }],
    })
  } catch {}
})
onBeforeUnmount(() => chart?.dispose())
</script>
<style scoped>
.chart-card-body { width: 100%; height: 100%; }
</style>
