<template>
  <div class="stat-health" v-loading="loading">
    <div class="health-ring" :style="ringStyle">
      <span class="health-num">{{ score }}</span>
    </div>
    <div class="health-status">{{ status }}</div>
  </div>
</template>
<script setup>
import { ref, onMounted, computed } from 'vue'
import request from '@/api/request'
const props = defineProps({ card: Object })
const loading = ref(false)
const score = ref(0)
const status = ref('')
const ringStyle = computed(() => {
  const c = score.value >= 80 ? '#10b981' : score.value >= 60 ? '#f59e0b' : '#ef4444'
  return { background: `conic-gradient(${c} ${score.value * 3.6}deg, var(--border-color, #e5e7eb) 0deg)` }
})
onMounted(async () => {
  loading.value = true
  try {
    const d = await request.get('/api/dashboard/data')
    score.value = d.stats.health_score || 0
    status.value = d.stats.health_status || '-'
  } catch {} finally { loading.value = false }
})
</script>
<style scoped>
.stat-health { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 8px; }
.health-ring { width: 64px; height: 64px; border-radius: 50%; display: flex; align-items: center; justify-content: center; }
.health-ring::before { content: ''; position: absolute; width: 50px; height: 50px; border-radius: 50%; background: var(--bg-card, #fff); }
.health-num { position: relative; font-size: 20px; font-weight: 700; }
.health-status { font-size: 12px; color: var(--text-secondary, #6b7280); }
</style>
