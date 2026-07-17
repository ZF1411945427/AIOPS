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
      { label: '活跃', value: d.stats.alert_active, color: '#ef4444' },
      { label: '规则数', value: d.stats.rule_count, color: '#f59e0b' },
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
