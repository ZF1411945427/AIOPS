<template>
  <div class="stat-card" v-loading="loading">
    <div class="stat-row"><span class="stat-label">数据源</span><span class="stat-value" style="color:#3b82f6">{{ count }}</span></div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import request from '@/api/request'
const props = defineProps({ card: Object })
const loading = ref(false)
const count = ref(0)
onMounted(async () => {
  loading.value = true
  try { const d = await request.get('/api/dashboard/data'); count.value = d.stats.datasource_count || 0 } catch {} finally { loading.value = false }
})
</script>
<style scoped>
.stat-card { display: flex; flex-direction: column; gap: 8px; padding: 8px; height: 100%; justify-content: center; }
.stat-row { display: flex; justify-content: space-between; align-items: center; }
.stat-label { font-size: 13px; color: var(--text-secondary, #6b7280); }
.stat-value { font-size: 20px; font-weight: 700; }
</style>
