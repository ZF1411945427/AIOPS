<template>
  <div class="workbench-page-shell">
    <div class="section-toolbar">
      <div class="toolbar-head">
        <span class="toolbar-title">智能体审计</span>
        <span class="toolbar-desc">AI 智能体的工具调用记录与执行审计</span>
      </div>
      <div class="workbench-card-actions">
        <el-button size="small" @click="loadData">刷新</el-button>
      </div>
    </div>

    <div class="workbench-card" style="flex:1;display:flex;flex-direction:column">
      <el-table :data="invocations" v-loading="loading" style="width:100%" size="small" :max-height="600">
        <el-table-column prop="created_at" label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="tool_name" label="工具" width="140">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.tool_name }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'" size="small">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="latency_ms" label="耗时" width="80">
          <template #default="{ row }">{{ row.latency_ms }}ms</template>
        </el-table-column>
        <el-table-column prop="request_payload" label="请求参数" min-width="200">
          <template #default="{ row }">
            <div style="font-size:11px;font-family:monospace;max-height:60px;overflow-y:auto;white-space:pre-wrap">{{ formatJson(row.request_payload) }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="response_summary" label="响应摘要" min-width="200">
          <template #default="{ row }">
            <div style="font-size:11px;font-family:monospace;max-height:60px;overflow-y:auto;white-space:pre-wrap">{{ formatJson(row.response_summary) }}</div>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!loading && !invocations.length" style="text-align:center;padding:40px;color:var(--text-muted);font-size:13px">
        暂无工具调用记录
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import request from '@/api/request'

const loading = ref(false)
const invocations = ref([])

function formatTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('zh-CN')
}

function formatJson(obj) {
  if (!obj) return ''
  try {
    return typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2)
  } catch { return '' }
}

async function loadData() {
  loading.value = true
  try {
    const data = await request.get('/agent/invocations')
    invocations.value = Array.isArray(data) ? data : []
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>
