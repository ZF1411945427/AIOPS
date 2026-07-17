<template>
  <div class="list-card" v-loading="loading">
    <div v-for="a in alerts" :key="a.id" class="list-item">
      <el-tag :type="sevType(a.severity)" size="small">{{ a.severity }}</el-tag>
      <span class="list-text">{{ a.metric_name }}</span>
      <span class="list-asset">{{ a.asset_name }}</span>
    </div>
    <div v-if="!alerts.length" class="list-empty">暂无告警</div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import request from '@/api/request'
const props = defineProps({ card: Object })
const loading = ref(false)
const alerts = ref([])
function sevType(s) { return { critical: 'danger', warning: 'warning', info: 'info' }[s] || 'info' }
onMounted(async () => {
  loading.value = true
  try { const d = await request.get('/api/dashboard/data'); alerts.value = d.recent_alerts || [] } catch {} finally { loading.value = false }
})
</script>
<style scoped>
.list-card { display: flex; flex-direction: column; gap: 4px; padding: 4px; height: 100%; overflow: auto; }
.list-item { display: flex; align-items: center; gap: 6px; padding: 4px 0; border-bottom: 1px solid var(--border-color, #f0f0f0); font-size: 12px; }
.list-text { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-primary, #1f2937); }
.list-asset { color: var(--text-tertiary, #9ca3af); font-size: 11px; flex-shrink: 0; }
.list-empty { text-align: center; color: var(--text-tertiary, #9ca3af); padding: 20px; font-size: 12px; }
</style>
