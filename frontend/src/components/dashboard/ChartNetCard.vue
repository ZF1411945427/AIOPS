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
    const rx = d.vm_metrics?.network_rx_bytes || []
    const tx = d.vm_metrics?.network_tx_bytes || []
    if (!rx.length && !tx.length) {
      chart.setOption({ title: { text: '暂无网络数据', left: 'center', top: 'center', textStyle: { color: '#94a3b8', fontSize: 12 } } })
      return
    }
    const times = rx.length ? rx.map(x => (x.time || '').slice(5, 16)) : tx.map(x => (x.time || '').slice(5, 16))
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['接收', '发送'], textStyle: { color: '#94a3b8', fontSize: 10 }, top: 0, right: 0 },
      grid: { left: 46, right: 14, top: 32, bottom: 22 },
      xAxis: { type: 'category', data: times, axisLabel: { color: '#94a3b8', fontSize: 10, rotate: 30 } },
      yAxis: { type: 'value', axisLabel: { color: '#94a3b8', formatter: v => (v / 1024).toFixed(1) + 'KB' } },
      series: [
        { name: '接收', type: 'line', smooth: true, symbol: 'none', data: rx.map(x => x.value), lineStyle: { color: '#3b82f6', width: 2 }, areaStyle: { color: 'rgba(59,130,246,0.1)' } },
        { name: '发送', type: 'line', smooth: true, symbol: 'none', data: tx.map(x => x.value), lineStyle: { color: '#8b5cf6', width: 2 }, areaStyle: { color: 'rgba(139,92,246,0.1)' } },
      ],
    })
  } catch {}
})
onBeforeUnmount(() => chart?.dispose())
</script>
<style scoped>
.chart-card-body { width: 100%; height: 100%; }
</style>
