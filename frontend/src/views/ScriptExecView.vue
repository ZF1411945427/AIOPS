<template>
  <div class="script-page">
    <div class="page-header">
      <h1>远程脚本执行</h1>
      <p>通过 SSH 在目标主机执行 Shell 脚本 · 共 {{ historyTotal }} 条历史</p>
    </div>

    <div class="panel">
      <div class="panel-header"><h3>执行脚本</h3></div>
      <div class="panel-body">
        <div class="form-grid">
          <div class="form-group">
            <label>目标主机</label>
            <select v-model="form.target_id" :disabled="!targets.length">
              <option v-for="t in targets" :key="t.id" :value="t.id">{{ t.name }} ({{ t.host || 'local' }})</option>
            </select>
            <p v-if="!targets.length" class="form-tip danger">无可用 SSH 目标主机，请先在数据源管理添加 SSH 类型数据源</p>
          </div>
          <div class="form-group">
            <label>超时(秒)</label>
            <input v-model.number="form.timeout" type="number" min="1" max="600" />
          </div>
          <div class="form-group full">
            <label>脚本内容</label>
            <textarea v-model="form.script_content" rows="8" class="mono" placeholder="#!/bin/bash&#10;uptime&#10;df -h"></textarea>
          </div>
        </div>
        <div class="form-actions">
          <button class="btn btn-primary" @click="executeScript" :disabled="executing || !form.target_id">
            {{ executing ? '执行中...' : '执行' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="lastOutput !== null || lastError" class="panel">
      <div class="panel-header"><h3>最新执行结果</h3></div>
      <div class="panel-body">
        <div v-if="lastOutput" class="result-block">
          <div class="result-label">STDOUT</div>
          <pre class="output-pre dark">{{ lastOutput }}</pre>
        </div>
        <div v-if="lastError" class="result-block">
          <div class="result-label danger">STDERR</div>
          <pre class="output-pre danger">{{ lastError }}</pre>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header"><h3>历史记录</h3></div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="history.length" class="history-list">
          <div v-for="h in history" :key="h.id" class="history-card">
            <div class="history-head" @click="toggleHistory(h.id)">
              <div class="history-info">
                <strong>{{ h.target_name }}</strong>
                <span class="text-sm">{{ formatTime(h.created_at) }}</span>
              </div>
              <div class="history-meta">
                <span class="badge" :class="h.exit_code === 0 ? 'resolved' : 'critical'">exit: {{ h.exit_code }}</span>
                <button class="btn btn-sm">{{ expanded === h.id ? '收起' : '查看' }}</button>
              </div>
            </div>
            <div v-if="expanded === h.id" class="history-body">
              <div class="result-label">脚本</div>
              <pre class="output-pre script">{{ h.script_content }}</pre>
              <div v-if="h.output" class="result-label">STDOUT</div>
              <pre v-if="h.output" class="output-pre dark">{{ h.output }}</pre>
              <div v-if="h.error" class="result-label danger">STDERR</div>
              <pre v-if="h.error" class="output-pre danger">{{ h.error }}</pre>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">📜</div>
          <div>暂无执行历史</div>
        </div>
        <div v-if="totalPages > 1" class="pagination">
          <button class="btn btn-sm" :disabled="currentPage <= 1" @click="goPage(1)">首页</button>
          <button class="btn btn-sm" :disabled="currentPage <= 1" @click="goPage(currentPage - 1)">上一页</button>
          <span v-for="p in pageNumbers" :key="p" class="page-num" :class="{ active: p === currentPage }" @click="goPage(p)">{{ p }}</span>
          <button class="btn btn-sm" :disabled="currentPage >= totalPages" @click="goPage(currentPage + 1)">下一页</button>
          <button class="btn btn-sm" :disabled="currentPage >= totalPages" @click="goPage(totalPages)">末页</button>
          <span class="page-jump">跳转 <input type="number" class="page-input" v-model.number="jumpPage" min="1" :max="totalPages" @keyup.enter="goPage(jumpPage)" /> 页</span>
          <span class="page-info">共 {{ historyTotal }} 条 / {{ totalPages }} 页</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const executing = ref(false)
const targets = ref([])
const history = ref([])
const historyTotal = ref(0)
const expanded = ref(null)
const lastOutput = ref(null)
const lastError = ref('')
const form = reactive({ target_id: null, script_content: '', timeout: 30 })

const currentPage = ref(1)
const pageSize = ref(20)
const totalPages = ref(1)
const jumpPage = ref(1)
const pageNumbers = computed(() => {
  const pages = []
  const cur = currentPage.value
  const tp = totalPages.value
  if (tp <= 7) {
    for (let i = 1; i <= tp; i++) pages.push(i)
  } else {
    pages.push(1)
    if (cur > 4) pages.push('...')
    const start = Math.max(2, cur - 1)
    const end = Math.min(tp - 1, cur + 1)
    for (let i = start; i <= end; i++) pages.push(i)
    if (cur < tp - 3) pages.push('...')
    pages.push(tp)
  }
  return pages
})
function goPage(p) {
  if (p < 1 || p > totalPages.value || p === currentPage.value) return
  currentPage.value = p
  loadHistory()
}

async function loadTargets() {
  try {
    const data = await request.get('/script/api/targets')
    targets.value = data.targets || []
    if (targets.value.length && !form.target_id) form.target_id = targets.value[0].id
  } catch (e) {
    ElMessage.error('加载目标主机失败: ' + e.message)
  }
}

async function loadHistory() {
  loading.value = true
  try {
    const data = await request.get('/script/api/history', { params: { page: currentPage.value, per_page: pageSize.value } })
    history.value = data.history || []
    historyTotal.value = data.total || 0
    totalPages.value = data.total_pages || 1
  } catch (e) {
    ElMessage.error('加载历史失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

async function executeScript() {
  if (!form.target_id) { ElMessage.warning('请选择目标主机'); return }
  if (!form.script_content.trim()) { ElMessage.warning('请输入脚本内容'); return }
  executing.value = true
  lastOutput.value = null
  lastError.value = ''
  try {
    const fd = new FormData()
    fd.append('target_id', form.target_id)
    fd.append('script_content', form.script_content)
    fd.append('timeout', form.timeout)
    const data = await request.post('/script/api/execute', fd)
    lastOutput.value = data.output || ''
    lastError.value = data.error || ''
    if (data.exit_code === 0 && !data.error) {
      ElMessage.success('执行完成')
    } else {
      ElMessage.warning('执行完成（有错误输出）')
    }
    currentPage.value = 1
    loadHistory()
  } catch (e) {
    ElMessage.error('执行失败: ' + (e.response?.data?.error || e.message))
  } finally {
    executing.value = false
  }
}

function toggleHistory(id) {
  expanded.value = expanded.value === id ? null : id
}

function formatTime(s) {
  if (!s) return '-'
  return s.substring(5, 16)
}

onMounted(() => {
  loadTargets()
  loadHistory()
})
</script>

<style scoped>
.script-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 16px; }
.panel-header { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.panel-header h3 { margin: 0; font-size: 0.95rem; }
.panel-body { padding: 16px 18px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.form-group { display: flex; flex-direction: column; gap: 4px; }
.form-group.full { grid-column: 1 / -1; }
.form-group label { font-size: 0.8rem; color: var(--text-secondary, #64748b); }
.form-group input, .form-group select, .form-group textarea { width: 100%; padding: 8px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.85rem; box-sizing: border-box; }
.form-group textarea { font-family: 'Consolas', 'Monaco', monospace; resize: vertical; }
.form-group textarea.mono { font-family: 'Consolas', 'Monaco', monospace; }
.form-tip { font-size: 0.72rem; color: var(--text-tertiary, #94a3b8); margin: 2px 0 0; }
.form-tip.danger { color: #ef4444; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; transition: all 0.2s; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.result-block { margin-bottom: 12px; }
.result-block:last-child { margin-bottom: 0; }
.result-label { font-size: 0.72rem; color: var(--text-secondary, #64748b); text-transform: uppercase; letter-spacing: 0.3px; margin-bottom: 4px; }
.result-label.danger { color: #ef4444; }
.output-pre { margin: 0; padding: 12px; border-radius: 6px; font-family: 'Consolas', 'Monaco', monospace; font-size: 0.78rem; white-space: pre-wrap; word-break: break-word; max-height: 300px; overflow: auto; }
.output-pre.dark { background: #1e293b; color: #e2e8f0; }
.output-pre.danger { background: #7f1d1d; color: #fecaca; }
.output-pre.script { background: var(--bg-hover, rgba(0,0,0,0.03)); color: var(--text, #1e293b); }
.history-list { display: flex; flex-direction: column; gap: 8px; }
.history-card { border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; overflow: hidden; }
.history-head { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; cursor: pointer; }
.history-head:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.history-info { display: flex; align-items: center; gap: 10px; }
.history-meta { display: flex; align-items: center; gap: 8px; }
.history-body { padding: 12px 14px; border-top: 1px solid var(--border, rgba(0,0,0,0.07)); background: var(--bg-hover, rgba(0,0,0,0.02)); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.resolved { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.critical { background: rgba(239,68,68,0.1); color: #ef4444; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 6px; margin-top: 16px; flex-wrap: wrap; }
.page-info { font-size: 0.82rem; color: var(--text-secondary, #64748b); }
.page-num { display: inline-flex; align-items: center; justify-content: center; min-width: 30px; height: 30px; padding: 0 6px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.8rem; cursor: pointer; transition: all 0.2s; user-select: none; }
.page-num:hover { background: var(--bg-hover, rgba(99,102,241,0.08)); border-color: var(--accent, #6366f1); }
.page-num.active { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); font-weight: 600; }
.page-jump { font-size: 0.8rem; color: var(--text-secondary, #64748b); display: flex; align-items: center; gap: 4px; }
.page-input { width: 50px; padding: 3px 6px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; text-align: center; font-size: 0.8rem; }
</style>
