<template>
  <div class="bg-page">
    <div class="page-header">
      <h1>后台任务看板</h1>
      <p>实时监控所有后台定时任务的运行状态 · 共 {{ tasks.length }} 个任务 · 轮询周期 {{ intervalSeconds }}s</p>
    </div>

    <!-- 健康摘要卡片 -->
    <div class="summary-grid">
      <div class="summary-card">
        <div class="summary-label">总任务数</div>
        <div class="summary-value">{{ health.total_tasks || tasks.length }}</div>
      </div>
      <div class="summary-card" :class="{ warn: runningCount > 0 }">
        <div class="summary-label">运行中</div>
        <div class="summary-value">{{ runningCount }}</div>
      </div>
      <div class="summary-card" :class="{ danger: failedCount > 0 }">
        <div class="summary-label">失败</div>
        <div class="summary-value">{{ failedCount }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">已暂停</div>
        <div class="summary-value">{{ pausedCount }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">平均耗时</div>
        <div class="summary-value">{{ avgDuration }} ms</div>
      </div>
      <div class="summary-card" v-if="health.slowest_task">
        <div class="summary-label">最慢任务</div>
        <div class="summary-value-sm">{{ health.slowest_task.name }} ({{ health.slowest_task.duration_ms }}ms)</div>
      </div>
    </div>

    <!-- 任务列表 -->
    <div class="panel">
      <div class="panel-head">
        <span>任务清单</span>
        <div class="panel-actions">
          <button class="btn btn-sm" @click="load" :disabled="loading">{{ loading ? '刷新中...' : '刷新' }}</button>
          <label class="auto-refresh">
            <input type="checkbox" v-model="autoRefresh"> 自动刷新 (5s)
          </label>
        </div>
      </div>
      <div class="panel-body">
        <div v-if="loading && !tasks.length" class="loading-state">加载中...</div>
        <table v-else-if="tasks.length" class="table">
          <thead>
            <tr>
              <th>任务名</th>
              <th>描述</th>
              <th>状态</th>
              <th>上次运行</th>
              <th>耗时(ms)</th>
              <th>成功/失败</th>
              <th>失败率</th>
              <th>下次运行</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in tasks" :key="t.name" :class="{ 'row-failed': t.last_status === 'failed', 'row-paused': !t.enabled, 'row-running': t.last_status === 'running' }">
              <td class="task-name">{{ t.name }}</td>
              <td class="text-sm">{{ t.description || '-' }}</td>
              <td>
                <span class="badge" :class="statusBadgeClass(t)">
                  {{ statusBadgeText(t) }}
                </span>
              </td>
              <td class="text-sm">{{ formatTime(t.last_run_at) }}</td>
              <td class="text-sm">{{ t.last_duration_ms || '-' }}</td>
              <td class="text-sm">{{ t.success_count }} / {{ t.failure_count }}</td>
              <td class="text-sm" :class="{ 'text-danger': t.failure_rate > 0.3 }">
                {{ (t.failure_rate * 100).toFixed(0) }}%
              </td>
              <td class="text-sm">{{ t.next_run_at || '-' }}</td>
              <td>
                <button class="btn btn-sm" @click="triggerTask(t)" :disabled="t.last_status === 'running'">
                  {{ t.last_status === 'running' ? '运行中' : '触发' }}
                </button>
                <button class="btn btn-sm" @click="togglePause(t)">
                  {{ t.enabled ? '暂停' : '恢复' }}
                </button>
                <button class="btn btn-sm" @click="showHistory(t)" v-if="t.history_count > 0">历史 ({{ t.history_count }})</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">暂无任务数据（后端启动后会自动注册）</div>
      </div>
    </div>

    <!-- 历史记录弹窗 -->
    <div v-if="historyTask" class="modal-overlay" @click.self="historyTask = null">
      <div class="modal-box modal-lg">
        <h3>「{{ historyTask.name }}」执行历史</h3>
        <table class="table">
          <thead><tr><th>时间</th><th>状态</th><th>耗时(ms)</th><th>错误</th></tr></thead>
          <tbody>
            <tr v-for="(h, i) in historyList" :key="i">
              <td class="text-sm">{{ h.at }}</td>
              <td><span class="badge" :class="h.status === 'success' ? 'on' : 'danger'">{{ h.status }}</span></td>
              <td class="text-sm">{{ h.duration_ms }}</td>
              <td class="text-sm text-danger">{{ h.error || '-' }}</td>
            </tr>
          </tbody>
        </table>
        <div class="modal-actions">
          <button class="btn" @click="historyTask = null">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const tasks = ref([])
const health = ref({})
const intervalSeconds = ref(10)
const autoRefresh = ref(true)
const historyTask = ref(null)
const historyList = ref([])
let timer = null

const runningCount = computed(() => tasks.value.filter(t => t.last_status === 'running').length)
const failedCount = computed(() => tasks.value.filter(t => t.last_status === 'failed').length)
const pausedCount = computed(() => tasks.value.filter(t => !t.enabled).length)
const avgDuration = computed(() => {
  const valid = tasks.value.filter(t => t.avg_duration_ms > 0)
  if (!valid.length) return 0
  return Math.round(valid.reduce((s, t) => s + t.avg_duration_ms, 0) / valid.length)
})

function statusBadgeClass(t) {
  if (!t.enabled) return 'off'
  if (t.last_status === 'running') return 'warn'
  if (t.last_status === 'failed') return 'danger'
  if (t.last_status === 'success') return 'on'
  if (t.last_status === 'skipped') return 'off'
  return 'off'
}

function statusBadgeText(t) {
  if (!t.enabled) return '已暂停'
  if (t.last_status === 'running') return '运行中'
  if (t.last_status === 'failed') return '失败'
  if (t.last_status === 'success') return '成功'
  if (t.last_status === 'skipped') return '已跳过'
  return '待执行'
}

function formatTime(iso) {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch (e) {
    return iso
  }
}

async function load() {
  loading.value = true
  try {
    const data = await request.get('/api/admin/background-tasks')
    if (data.tasks) {
      tasks.value = data.tasks
      intervalSeconds.value = data.interval_seconds || 10
    } else if (data.warning) {
      ElMessage.warning(data.warning)
    }
  } catch (e) {
    // 静默失败：可能是未登录，由 axios 拦截器统一处理
    console.error('load background tasks:', e)
  } finally {
    loading.value = false
  }
}

async function loadHealth() {
  try {
    const data = await request.get('/api/admin/background-tasks/health')
    if (!data.warning) {
      health.value = data
    }
  } catch (e) {
    // 静默
  }
}

async function triggerTask(t) {
  try {
    const data = await request.post(`/api/admin/background-tasks/${t.name}/trigger`)
    if (data.ok) {
      ElMessage.success(data.message || `任务 ${t.name} 已触发`)
      setTimeout(load, 500)
    } else {
      ElMessage.warning(data.message || '触发失败')
    }
  } catch (e) {
    ElMessage.error('触发失败: ' + (e.message || e))
  }
}

async function togglePause(t) {
  try {
    const data = await request.post(`/api/admin/background-tasks/${t.name}/pause`)
    if (data.ok) {
      ElMessage.success(data.message)
      load()
    } else {
      ElMessage.warning(data.message || '操作失败')
    }
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.message || e))
  }
}

async function showHistory(t) {
  // 历史数据需要从详情接口拿，这里复用 snapshot（包含 history 字段需要后端扩展）
  // 简化：直接显示当前快照中已有的统计
  historyTask.value = t
  // 尝试从健康摘要中获取，但实际历史需要专门接口
  // 这里直接展示空列表 + 提示
  historyList.value = []
  ElMessage.info(`任务 ${t.name} 已执行 ${t.total_runs} 次（成功 ${t.success_count} / 失败 ${t.failure_count}）`)
}

function startAutoRefresh() {
  if (timer) clearInterval(timer)
  if (autoRefresh.value) {
    timer = setInterval(() => {
      load()
      loadHealth()
    }, 5000)
  }
}

onMounted(() => {
  load()
  loadHealth()
  startAutoRefresh()
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})

import { watch } from 'vue'
watch(autoRefresh, () => startAutoRefresh())
</script>

<style scoped>
.bg-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 16px; }
.summary-card { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; padding: 12px 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.summary-card.warn { border-left: 3px solid #f59e0b; }
.summary-card.danger { border-left: 3px solid #ef4444; }
.summary-label { font-size: 0.72rem; color: var(--text-secondary, #64748b); text-transform: uppercase; letter-spacing: 0.3px; margin-bottom: 4px; }
.summary-value { font-size: 1.4rem; font-weight: 700; color: var(--text, #1e293b); }
.summary-value-sm { font-size: 0.9rem; font-weight: 600; color: var(--text, #1e293b); }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); display: flex; justify-content: space-between; align-items: center; }
.panel-actions { display: flex; gap: 10px; align-items: center; }
.panel-body { padding: 16px 18px; }
.auto-refresh { font-size: 0.78rem; color: var(--text-secondary, #64748b); display: flex; align-items: center; gap: 4px; cursor: pointer; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.72rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; white-space: nowrap; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); white-space: nowrap; }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.table tr.row-failed td { background: rgba(239,68,68,0.04); }
.table tr.row-paused td { opacity: 0.7; }
.table tr.row-running td { background: rgba(245,158,11,0.04); }
.task-name { font-weight: 600; font-family: 'Consolas', monospace; font-size: 0.8rem; }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.text-danger { color: #ef4444; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.on { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.off { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.warn { background: rgba(245,158,11,0.1); color: #f59e0b; }
.badge.danger { background: rgba(239,68,68,0.1); color: #ef4444; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 420px; max-height: 86vh; overflow-y: auto; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-lg { min-width: 640px; }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; color: var(--text, #1e293b); }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
