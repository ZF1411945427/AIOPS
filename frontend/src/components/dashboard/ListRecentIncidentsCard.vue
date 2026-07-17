<template>
  <div class="list-card" v-loading="loading">
    <div v-for="i in incidents" :key="i.id" class="list-item">
      <el-tag :type="i.status === 'open' ? 'danger' : 'success'" size="small">{{ i.status }}</el-tag>
      <span class="list-text">{{ i.title }}</span>
    </div>
    <div v-if="!incidents.length" class="list-empty">暂无故障</div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import request from '@/api/request'
const props = defineProps({ card: Object })
const loading = ref(false)
const incidents = ref([])
onMounted(async () => {
  loading.value = true
  try {
    const d = await request.get('/api/dashboard/data')
    const incStatus = d.incident_status || []
    // Use incident API for list
  } catch {} finally { loading.value = false }
  try {
    const list = await request.get('/incidents/api/list', { params: { limit: 5 } })
    incidents.value = list.incidents || list || []
  } catch {}
})
</script>
<style scoped>
.list-card { display: flex; flex-direction: column; gap: 4px; padding: 4px; height: 100%; overflow: auto; }
.list-item { display: flex; align-items: center; gap: 6px; padding: 4px 0; border-bottom: 1px solid var(--border-color, #f0f0f0); font-size: 12px; }
.list-text { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-primary, #1f2937); }
.list-empty { text-align: center; color: var(--text-tertiary, #9ca3af); padding: 20px; font-size: 12px; }
</style>
