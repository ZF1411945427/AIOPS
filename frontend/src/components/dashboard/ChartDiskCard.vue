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
    const data = d.vm_metrics?.disk_usage || []
    const latest = data.length ? data[data.length - 1]?.value || 0 : 0
    if (!data.length) {
      chart.setOption({ title: { text: '暂无磁盘数据', left: 'center', top: 'center', textStyle: { color: '#94a3b8', fontSize: 12 } } })
      return
    }
    chart.setOption({
      tooltip: { formatter: () => `磁盘使用率: ${latest}%` },
      series: [{
        type: 'gauge', center: ['50%', '55%'], radius: '72%',
        startAngle: 220, endAngle: -40, min: 0, max: 100,
        axisLine: { lineStyle: { width: 12, color: [[0.5, '#10b981'], [0.8, '#f59e0b'], [1, '#ef4444']] } },
        axisTick: { show: false },
        splitLine: { length: 6, lineStyle: { color: '#1e293b', width: 2 } },
        axisLabel: { color: '#94a3b8', fontSize: 9, distance: 12 },
        detail: { valueAnimation: true, formatter: '{value}%', color: '#e2e8f0', fontSize: 20, fontWeight: 700, offsetCenter: [0, '55%'] },
        title: { offsetCenter: [0, '78%'], fontSize: 11, color: '#94a3b8' },
        data: [{ value: latest, name: '磁盘' }],
      }],
    })
  } catch {}
})
onBeforeUnmount(() => chart?.dispose())
</script>
<style scoped>
.chart-card-body { width: 100%; height: 100%; }
</style>
