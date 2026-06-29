<template>
  <div class="workbench-page-shell">
    <div class="section-toolbar">
      <div class="toolbar-head">
        <span class="toolbar-title">操作审计</span>
        <span class="toolbar-desc">系统所有用户操作日志记录</span>
      </div>
      <div class="workbench-card-actions">
        <el-button size="small" @click="loadData">刷新</el-button>
      </div>
    </div>

    <div class="workbench-card" style="flex:1;display:flex;flex-direction:column">
      <el-table :data="logs" v-loading="loading" style="width:100%" size="small" :max-height="600" empty-text="暂无操作日志">
        <el-table-column prop="time" label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.time) }}</template>
        </el-table-column>
        <el-table-column prop="user" label="用户" width="100" />
        <el-table-column prop="action" label="操作" width="120">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.action }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="target" label="目标" width="140" />
        <el-table-column prop="detail" label="详情" min-width="240">
          <template #default="{ row }">
            <div style="font-size:11px;color:var(--text-secondary)">{{ row.detail }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="ip" label="来源 IP" width="130" />
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import request from '@/api/request'

const loading = ref(false)
const logs = ref([])

function formatTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('zh-CN')
}

async function loadData() {
  loading.value = true
  try {
    const data = await request.get('/api/audit/logs')
    logs.value = Array.isArray(data) ? data : []
  } catch {
    logs.value = []
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>
