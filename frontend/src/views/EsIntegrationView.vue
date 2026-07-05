<template>
  <div class="es-page">
    <div class="page-header">
      <h1>集成管理</h1>
      <p>Elasticsearch 数据源集成 · 共 {{ sources.length }} 个 ES 数据源</p>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="sources.length" class="card-grid">
          <div v-for="s in sources" :key="s.id" class="es-card">
            <div class="card-top">
              <span class="es-name">{{ s.name }}</span>
              <span class="badge" :class="s.enabled ? 'on' : 'off'">{{ s.enabled ? '启用' : '禁用' }}</span>
            </div>
            <div class="card-meta">
              <div><span class="meta-label">Endpoint</span><span class="text-sm">{{ s.endpoint || '-' }}</span></div>
              <div><span class="meta-label">状态</span><span class="badge" :class="statusClass(s.last_status)">{{ s.last_status || '未测试' }}</span></div>
            </div>
            <div class="card-actions">
              <button class="btn btn-sm btn-primary" @click="syncEvents(s)" :disabled="syncing === s.id">
                {{ syncing === s.id ? '同步中...' : '同步 K8s 事件' }}
              </button>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">🔌</div>
          <div>暂无 Elasticsearch 数据源</div>
          <div class="text-sm" style="margin-top:6px;">请先在「数据源管理」中添加 ES 类型数据源</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const sources = ref([])
const syncing = ref(0)

function statusClass(s) {
  if (!s) return 'off'
  if (s === 'ok' || s === 'success' || s === 'online') return 'on'
  if (s === 'error' || s === 'failed') return 'err'
  return 'off'
}

async function loadSources() {
  loading.value = true
  try {
    const data = await request.get('/es-integration/api/list')
    sources.value = data.sources || []
  } catch (e) {
    ElMessage.error('加载失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

async function syncEvents(s) {
  syncing.value = s.id
  try {
    const data = await request.post(`/es-integration/api/sync-events/${s.id}`)
    if (data.status === 'ok') {
      ElMessage.success(`同步成功，已写入 ${data.synced} 条事件`)
    } else {
      ElMessage.error(data.message || '同步失败')
    }
  } catch (e) {
    ElMessage.error('同步失败: ' + (e.message || e))
  } finally {
    syncing.value = 0
  }
}

onMounted(loadSources)
</script>

<style scoped>
.es-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
.es-card { border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; padding: 14px; background: var(--bg-card-solid, #fff); }
.card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.es-name { font-weight: 600; font-size: 0.95rem; color: var(--text, #1e293b); }
.card-meta { font-size: 0.8rem; display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }
.card-meta > div { display: flex; gap: 8px; }
.meta-label { color: var(--text-secondary, #64748b); min-width: 64px; }
.card-actions { display: flex; gap: 8px; }
.text-sm { font-size: 0.75rem; color: var(--text-secondary, #64748b); word-break: break-all; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.on { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.off { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.err { background: rgba(239,68,68,0.1); color: #ef4444; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
</style>
