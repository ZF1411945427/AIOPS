<template>
  <div class="stat-card" v-loading="loading">
    <div class="stat-row" v-for="s in stats" :key="s.label">
      <span class="stat-label">{{ s.label }}</span>
      <span class="stat-value" :style="{ color: s.color }">{{ s.value }}</span>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import request from '@/api/request'
const props = defineProps({ card: Object })
const loading = ref(false)
const stats = ref([])
onMounted(async () => {
  loading.value = true
  try {
    const d = await request.get('/api/dashboard/data')
    stats.value = [
      { label: '总数', value: d.stats.asset_total, color: '#6366f1' },
      { label: '在线', value: d.stats.asset_online, color: '#10b981' },
      { label: '离线', value: d.stats.asset_total - d.stats.asset_online, color: '#ef4444' },
    ]
  } catch {} finally { loading.value = false }
})
</script>
<style scoped>
.stat-card { display: flex; flex-direction: column; gap: 8px; padding: 8px; height: 100%; justify-content: center; }
.stat-row { display: flex; justify-content: space-between; align-items: center; }
.stat-label { font-size: 13px; color: var(--text-secondary, #6b7280); }
.stat-value { font-size: 20px; font-weight: 700; }
</style>
