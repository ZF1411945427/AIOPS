<template>
  <div class="logs-page">
    <div class="page-header">
      <h1>日志中心</h1>
      <p>Elasticsearch 日志检索 · 共 {{ total }} 条</p>
    </div>

    <div class="toolbar">
      <select v-model="sourceId" @change="searchLogs">
        <option :value="0">选择数据源</option>
        <option v-for="s in sources" :key="s.id" :value="s.id">{{ s.name }}</option>
      </select>
      <input v-model="query" @keyup.enter="searchLogs" placeholder="搜索查询 (如 * 或 error)" class="search-input">
      <select v-model="timeRange" @change="searchLogs">
        <option value="15m">最近15分钟</option>
        <option value="30m">最近30分钟</option>
        <option value="1h">最近1小时</option>
        <option value="6h">最近6小时</option>
        <option value="24h">最近24小时</option>
        <option value="7d">最近7天</option>
      </select>
      <button class="btn btn-primary" @click="searchLogs">搜索</button>
    </div>

    <div v-if="error" class="error-bar">⚠ {{ error }}</div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">查询中...</div>
        <div v-else-if="logs.length" class="log-list">
          <div v-for="log in logs" :key="log.id" class="log-item">
            <div class="log-head">
              <span class="log-time">{{ formatTime(log.timestamp) }}</span>
              <span class="log-level" :class="(log.level || 'info').toLowerCase()">{{ log.level || 'info' }}</span>
              <span v-if="log.host" class="log-host">{{ log.host }}</span>
              <span v-if="log.service" class="log-svc">{{ log.service }}</span>
              <span class="log-index">{{ log.index }}</span>
            </div>
            <div class="log-msg">{{ log.message }}</div>
          </div>
        </div>
        <div v-else-if="sourceId > 0" class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">📭</div>
          <div>未查询到日志</div>
        </div>
        <div v-else class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">📖</div>
          <div>请选择一个 Elasticsearch 数据源开始查询</div>
        </div>
      </div>
    </div>

    <div v-if="totalPages > 1" class="pagination">
      <button class="btn btn-sm" :disabled="page <= 1" @click="goPage(page - 1)">上一页</button>
      <span class="page-info">第 {{ page }} / {{ totalPages }} 页</span>
      <button class="btn btn-sm" :disabled="page >= totalPages" @click="goPage(page + 1)">下一页</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const sources = ref([])
const logs = ref([])
const total = ref(0)
const totalPages = ref(1)
const error = ref(null)
const sourceId = ref(0)
const query = ref('*')
const timeRange = ref('1h')
const page = ref(1)
const size = 50

async function loadSources() {
  try {
    sources.value = await request.get('/logs/api/sources')
  } catch (e) {
    ElMessage.error('加载数据源失败: ' + e.message)
  }
}

async function searchLogs() {
  if (sourceId.value <= 0) {
    logs.value = []
    total.value = 0
    return
  }
  loading.value = true
  error.value = null
  try {
    const data = await request.get('/logs/api/search', {
      params: { source_id: sourceId.value, query: query.value, time_range: timeRange.value, page: page.value, size }
    })
    logs.value = data.logs || []
    total.value = data.total || 0
    totalPages.value = data.total_pages || 1
    error.value = data.error
  } catch (e) {
    ElMessage.error('查询失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function goPage(p) {
  page.value = p
  searchLogs()
}

function formatTime(s) {
  if (!s) return '-'
  return s.replace('T', ' ').substring(0, 19)
}

onMounted(loadSources)
</script>

<style scoped>
.logs-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.toolbar select { padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; }
.search-input { padding: 6px 12px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; flex: 1; min-width: 240px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; transition: all 0.2s; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.error-bar { background: rgba(239,68,68,0.1); color: #ef4444; padding: 10px 14px; border-radius: 6px; margin-bottom: 14px; font-size: 0.85rem; border: 1px solid rgba(239,68,68,0.3); }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.log-list { display: flex; flex-direction: column; gap: 8px; max-height: 600px; overflow-y: auto; }
.log-item { background: var(--bg-secondary, #f8fafc); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-left: 3px solid var(--accent, #6366f1); border-radius: 6px; padding: 10px 12px; }
.log-head { display: flex; gap: 10px; align-items: center; margin-bottom: 6px; flex-wrap: wrap; }
.log-time { font-size: 0.72rem; color: var(--text-secondary, #64748b); font-family: monospace; }
.log-level { font-size: 0.68rem; padding: 1px 7px; border-radius: 6px; font-weight: 600; }
.log-level.info, .log-level.debug { background: rgba(59,130,246,0.1); color: #3b82f6; }
.log-level.warn, .log-level.warning { background: rgba(245,158,11,0.1); color: #f59e0b; }
.log-level.error, .log-level.fatal, .log-level.critical { background: rgba(239,68,68,0.1); color: #ef4444; }
.log-host, .log-svc { font-size: 0.7rem; color: var(--text-secondary, #64748b); background: rgba(99,102,241,0.08); padding: 1px 6px; border-radius: 4px; }
.log-index { font-size: 0.65rem; color: var(--text-tertiary, #94a3b8); margin-left: auto; }
.log-msg { font-size: 0.82rem; color: var(--text, #1e293b); line-height: 1.6; word-break: break-word; font-family: 'JetBrains Mono', monospace; white-space: pre-wrap; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 10px; margin-top: 16px; }
.page-info { font-size: 0.82rem; color: var(--text-secondary, #64748b); }
</style>
