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
    const d = await request.get('/api/ops-analytics/mtta-mttr', { params: { days: 30 } })
    chart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 30, right: 10, top: 10, bottom: 20 },
      xAxis: { type: 'category', data: d.daily?.map(x => x.date) || [], axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value', name: '分钟' },
      series: [{ type: 'bar', data: d.daily?.map(x => x.mttr_min) || [], itemStyle: { color: '#6366f1', borderRadius: [4, 4, 0, 0] } }],
    })
  } catch {}
})
onBeforeUnmount(() => chart?.dispose())
</script>
<style scoped>
.chart-card-body { width: 100%; height: 100%; }
</style>
