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
const COLORS = { critical: '#ef4444', warning: '#f59e0b', info: '#3b82f6' }
onMounted(async () => {
  chart = echarts.init(chartEl.value)
  try {
    const d = await request.get('/api/dashboard/data')
    chart.setOption({
      tooltip: { trigger: 'item' },
      series: [{
        type: 'pie', radius: '60%',
        data: (d.severity_distribution || []).map(x => ({ name: x.severity, value: x.count, itemStyle: { color: COLORS[x.severity] || '#999' } })),
        label: { fontSize: 10 },
      }],
    })
  } catch {}
})
onBeforeUnmount(() => chart?.dispose())
</script>
<style scoped>
.chart-card-body { width: 100%; height: 100%; }
</style>
