<template>
  <div class="logs-page">
    <div class="page-header">
      <h1>日志中心</h1>
      <p>Elasticsearch 日志检索 · 索引 <b>{{ currentIndex || '全部' }}</b> · 共 {{ total }} 条</p>
    </div>

    <!-- 基础工具栏 -->
    <div class="toolbar">
      <select v-model="sourceId" @change="onSourceChange">
        <option :value="0">选择数据源</option>
        <option v-for="s in sources" :key="s.id" :value="s.id">{{ s.name }}</option>
      </select>
      <input v-model="query" @keyup.enter="searchLogs" placeholder="搜索查询 (ES query_string 语法)" class="search-input">
      <select v-model="timeRange" @change="searchLogs">
        <option value="15m">最近15分钟</option>
        <option value="30m">最近30分钟</option>
        <option value="1h">最近1小时</option>
        <option value="6h">最近6小时</option>
        <option value="24h">最近24小时</option>
        <option value="7d">最近7天</option>
      </select>
      <label class="dedup-toggle" title="默认折叠相邻相同日志，勾选后显示原始日志">
        <input type="checkbox" v-model="showOriginal" @change="searchLogs">
        显示原日志<span v-if="!showOriginal" class="dedup-badge">降噪中</span>
      </label>
      <button class="btn btn-primary" @click="searchLogs">搜索</button>
      <button class="btn" @click="showFilters = !showFilters">{{ showFilters ? '收起' : '展开' }}过滤</button>
      <button class="btn" @click="showRules = !showRules">{{ showRules ? '收起' : '告警规则' }}</button>
    </div>

    <!-- 高级过滤 -->
    <div v-if="showFilters" class="filter-bar">
      <label>业务域: <select v-model="filterDomain" class="filter-select" @change="onDomainChange">
        <option value="">全部</option>
        <option v-for="d in domainList" :key="d" :value="d">{{ d }}</option>
      </select></label>
      <label v-if="!isLokiSource">索引: <select v-model="filterIndex" class="filter-select">
        <option value="">全部</option>
        <option v-for="ix in indices" :key="ix.name" :value="ix.name">{{ ix.name }} ({{ ix.docs }} 条)</option>
      </select></label>
      <label>级别: <select v-model="filterLevel" class="filter-select">
        <option value="">全部</option>
        <option value="error">error</option>
        <option value="warning">warning</option>
        <option value="info">info</option>
        <option value="debug">debug</option>
      </select></label>
      <label>主机: <input v-model="filterHost" placeholder="主机名" class="filter-input"></label>
      <label>服务:
        <select v-if="isLokiSource" v-model="filterService" class="filter-select">
          <option value="">全部</option>
          <option v-for="s in services" :key="s" :value="s">{{ s }}</option>
        </select>
        <input v-else v-model="filterService" placeholder="服务名" class="filter-input">
      </label>
      <button class="btn btn-sm btn-primary" @click="searchLogs">应用</button>
    </div>

    <!-- 告警规则管理 -->
    <div v-if="showRules" class="rules-panel panel">
      <div class="panel-head"><b>日志告警规则</b><button class="btn btn-sm btn-primary" @click="showNewRule = !showNewRule">+ 新建</button></div>
      <div v-if="showNewRule" class="new-rule-form">
        <div class="rule-row">
          <input v-model="newRule.name" placeholder="规则名称" class="filter-input">
          <input v-model="newRule.keyword" placeholder="关键词 (留空=匹配全部)" class="filter-input">
          <select v-model="newRule.log_level" class="filter-select"><option value="">级别不限</option><option value="error">error</option><option value="warning">warning</option><option value="info">info</option></select>
          <input v-model.number="newRule.threshold" type="number" placeholder="阈值" class="filter-input" style="width:70px">
          <input v-model.number="newRule.window_minutes" type="number" placeholder="窗口(min)" class="filter-input" style="width:80px">
          <select v-model="newRule.severity" class="filter-select"><option value="warning">warning</option><option value="critical">critical</option></select>
          <button class="btn btn-sm btn-primary" @click="createRule">创建</button>
        </div>
      </div>
      <div class="rule-list">
        <div v-for="r in rules" :key="r.id" class="rule-item">
          <span :class="{'rule-enabled': r.enabled, 'rule-disabled': !r.enabled}">{{ r.enabled ? '●' : '○' }}</span>
          <b>{{ r.name }}</b>
          <span class="rule-tag">{{ r.source }}</span>
          <span v-if="r.log_level" class="rule-tag level-{{ r.log_level }}">{{ r.log_level }}</span>
          <span v-if="r.keyword" class="rule-tag">{{ r.keyword }}</span>
          <span class="rule-meta">阈值={{ r.threshold }} 窗口={{ r.window_minutes }}min</span>
          <span class="rule-sev" :class="r.severity === 'critical' ? 'sev-critical' : ''">{{ r.severity }}</span>
          <button class="btn btn-sm" @click="toggleRule(r)">{{ r.enabled ? '禁用' : '启用' }}</button>
          <button class="btn btn-sm btn-del" @click="deleteRule(r.id)">删除</button>
        </div>
        <div v-if="!rules.length" class="empty-hint">暂无告警规则，点击 "+ 新建" 创建</div>
      </div>
    </div>

    <div v-if="error" class="error-bar">⚠ {{ error }}</div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">查询中...</div>
        <div v-else-if="logs.length" class="log-list">
          <div v-for="(log, idx) in logs" :key="log.id || idx" class="log-row" :class="{ expanded: expandedSet.has(idx) }" @click="toggleExpand(idx)">
            <span class="log-time">{{ formatTime(log.timestamp) }}</span>
            <span v-if="log.repeat > 1 && log.time_end" class="log-time-range">~{{ formatTimeShort(log.time_end) }}</span>
            <span class="log-lvl" :class="(log.level || 'info').toLowerCase()">{{ (log.level || 'info').charAt(0).toUpperCase() }}</span>
            <span v-if="log.host" class="log-host">{{ log.host }}</span>
            <span v-if="log.service" class="log-svc">{{ log.service }}</span>
            <span class="log-msg" :class="{ collapsed: !expandedSet.has(idx) }" :title="log.message">{{ log.message }}</span>
            <span v-if="log.repeat > 1" class="log-repeat">×{{ log.repeat }}</span>
          </div>
        </div>
        <div v-else-if="sourceId > 0" class="empty-state"><div>未查询到日志</div></div>
        <div v-else class="empty-state"><div>请选择一个 Elasticsearch 数据源开始查询</div></div>
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
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const sources = ref([])
const services = ref([])
const indices = ref([])
const logs = ref([])
const total = ref(0)
const totalPages = ref(1)
const error = ref(null)
const sourceId = ref(0)
const query = ref('*')
const timeRange = ref('1h')
const page = ref(1)
const size = 50
const showFilters = ref(false)
const showRules = ref(false)
const filterDomain = ref('')
const domainList = ref([])
const filterIndex = ref('')
const filterLevel = ref('')
const filterHost = ref('')
const filterService = ref('')
const currentIndex = ref('')
const showOriginal = ref(false)
const expandedSet = ref(new Set())

function toggleExpand(idx) {
  const s = new Set(expandedSet.value)
  if (s.has(idx)) s.delete(idx)
  else s.add(idx)
  expandedSet.value = s
}

const rules = ref([])
const showNewRule = ref(false)
const newRule = ref({ name: '', keyword: '', log_level: 'error', threshold: 1, window_minutes: 5, severity: 'warning' })

const isLokiSource = computed(() => {
  const s = sources.value.find(x => x.id === sourceId.value)
  return s && s.type === 'loki'
})

async function loadSources() {
  try { sources.value = await request.get('/logs/api/sources') } catch (e) { ElMessage.error('加载数据源失败') }
}

async function loadJobs() {
  services.value = []
  if (!isLokiSource.value) return
  try {
    const list = await request.get('/logs/api/services', { params: { source_id: sourceId.value } })
    services.value = Array.isArray(list) ? list : []
  } catch (e) { services.value = [] }
}

async function loadIndices() {
  indices.value = []
  if (isLokiSource.value) return
  if (sourceId.value <= 0) return
  try {
    const list = await request.get('/logs/api/indices', { params: { source_id: sourceId.value } })
    indices.value = Array.isArray(list) ? list : []
  } catch (e) { indices.value = [] }
}

async function loadRules() {
  try {
    const data = await request.get('/log-anomaly/rules')
    rules.value = data.rules || []
  } catch (e) { /* ignore */ }
}

async function onSourceChange() {
  currentIndex.value = ''
  filterIndex.value = ''
  filterService.value = ''
  filterDomain.value = ''
  await loadJobs()
  await loadIndices()
  await searchLogs()
}

async function loadDomains() {
  try {
    const res = await request.get('/api/traces/domains')
    domainList.value = res || []
  } catch (e) { /* ignore */ }
}

async function onDomainChange() {
  filterService.value = ''
  if (!isLokiSource.value || !filterDomain.value) return
  try {
    const res = await request.get('/api/traces/services', { params: { domain: filterDomain.value } })
    services.value = res || []
  } catch (e) { /* ignore */ }
}

async function searchLogs() {
  if (sourceId.value <= 0) { logs.value = []; total.value = 0; return }
  loading.value = true; error.value = null; expandedSet.value = new Set()
  try {
    const data = await request.get('/logs/api/search', {
      params: {
        source_id: sourceId.value, query: query.value, time_range: timeRange.value,
        page: page.value, size,
        index: filterIndex.value, level: filterLevel.value,
        host: filterHost.value, service: filterService.value,
        dedup: showOriginal.value ? 0 : 1,
      }
    })
    logs.value = data.logs || []
    total.value = data.total || 0
    totalPages.value = data.total_pages || 1
    error.value = data.error
    currentIndex.value = filterIndex.value
  } catch (e) { ElMessage.error('查询失败: ' + e.message) }
  finally { loading.value = false }
}

function goPage(p) { page.value = p; searchLogs() }

function formatTime(s) { if (!s) return '-'; return s.replace('T', ' ').substring(0, 19) }
function formatTimeShort(s) { if (!s) return ''; return s.replace('T', ' ').substring(11, 19) }

async function createRule() {
  if (!newRule.value.name) { ElMessage.warning('请输入规则名称'); return }
  try {
    await request.post('/log-anomaly/rules', {
      name: newRule.value.name,
      source: `es:${sourceId.value || 12}`,
      keyword: newRule.value.keyword || '',
      log_level: newRule.value.log_level || '',
      threshold: newRule.value.threshold || 1,
      window_minutes: newRule.value.window_minutes || 5,
      severity: newRule.value.severity || 'warning',
      enabled: true,
    })
    ElMessage.success('规则已创建')
    showNewRule.value = false
    newRule.value = { name: '', keyword: '', log_level: 'error', threshold: 1, window_minutes: 5, severity: 'warning' }
    await loadRules()
  } catch (e) { ElMessage.error('创建失败: ' + e.message) }
}

async function toggleRule(r) {
  try {
    await request.put(`/log-anomaly/rules/${r.id}`, {
      name: r.name, source: r.source, keyword: r.keyword, log_level: r.log_level,
      threshold: r.threshold, window_minutes: r.window_minutes, severity: r.severity, enabled: !r.enabled,
    })
    r.enabled = !r.enabled
    ElMessage.success(r.enabled ? '已启用' : '已禁用')
  } catch (e) { ElMessage.error('操作失败') }
}

async function deleteRule(id) {
  try {
    await ElMessageBox.confirm('确认删除此规则？', '提示')
    await request.delete(`/log-anomaly/rules/${id}`)
    ElMessage.success('已删除')
    await loadRules()
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败') }
}

async function loadDefaultSource() {
  try {
    const data = await request.get('/datasources/api/log-default')
    const sid = data.source_id || 0
    if (sid > 0 && sources.value.some(s => s.id === sid)) {
      sourceId.value = sid
      await onSourceChange()
    }
  } catch (e) { /* ignore */ }
}

onMounted(async () => {
  await loadSources()
  loadRules()
  loadDomains()
  await loadDefaultSource()
})
</script>

<style scoped>
.logs-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.toolbar select { padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; }
.search-input { padding: 6px 12px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; flex: 1; min-width: 120px; }
.filter-bar { display: flex; gap: 10px; align-items: center; padding: 10px 14px; background: var(--bg-secondary, #f8fafc); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; margin-bottom: 8px; flex-wrap: wrap; font-size: 0.82rem; }
.filter-bar label { display: flex; align-items: center; gap: 4px; }
.filter-input { padding: 4px 8px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 4px; font-size: 0.8rem; width: 140px; }
.filter-select { padding: 4px 6px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 4px; font-size: 0.8rem; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.btn-del { color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-del:hover { background: rgba(239,68,68,0.08); }
.error-bar { background: rgba(239,68,68,0.1); color: #ef4444; padding: 10px 14px; border-radius: 6px; margin-bottom: 14px; font-size: 0.85rem; border: 1px solid rgba(239,68,68,0.3); }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 12px; }
.panel-head { padding: 12px 16px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); display: flex; justify-content: space-between; align-items: center; }
.panel-body { padding: 16px 18px; }
.rules-panel { margin-bottom: 12px; }
.new-rule-form { padding: 12px 16px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); background: var(--bg-secondary, #f8fafc); }
.rule-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.rule-list { padding: 8px 12px; }
.rule-item { display: flex; gap: 8px; align-items: center; padding: 6px 0; border-bottom: 1px solid var(--border, rgba(0,0,0,0.05)); font-size: 0.82rem; flex-wrap: wrap; }
.rule-item:last-child { border-bottom: none; }
.rule-enabled { color: #22c55e; }
.rule-disabled { color: #94a3b8; }
.rule-tag { font-size: 0.7rem; padding: 1px 6px; border-radius: 4px; background: rgba(99,102,241,0.08); color: var(--text-secondary, #64748b); }
.rule-meta { color: var(--text-tertiary, #94a3b8); font-size: 0.75rem; }
.rule-sev { font-size: 0.72rem; font-weight: 600; padding: 1px 6px; border-radius: 4px; background: rgba(245,158,11,0.1); color: #f59e0b; }
.sev-critical { background: rgba(239,68,68,0.1); color: #ef4444; }
.empty-hint { color: var(--text-tertiary, #94a3b8); font-size: 0.82rem; text-align: center; padding: 12px; }
.log-list { max-height: 600px; overflow-y: auto; border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 6px; }
.log-row { display: flex; gap: 8px; align-items: baseline; padding: 3px 10px; font-size: 0.8rem; cursor: pointer; line-height: 1.5; }
.log-row:nth-child(odd) { background: var(--bg-hover, rgba(0,0,0,0.02)); }
.log-row:hover { background: rgba(99,102,241,0.06); }
.log-row.expanded { background: rgba(99,102,241,0.08); }
.log-time { flex-shrink: 0; font-size: 0.72rem; color: var(--text-secondary, #64748b); font-family: monospace; }
.log-time-range { flex-shrink: 0; font-size: 0.72rem; color: var(--accent, #6366f1); font-family: monospace; }
.log-lvl { flex-shrink: 0; width: 14px; text-align: center; font-size: 0.7rem; font-weight: 700; }
.log-lvl.info, .log-lvl.debug { color: #3b82f6; }
.log-lvl.warn, .log-lvl.warning { color: #f59e0b; }
.log-lvl.error, .log-lvl.fatal, .log-lvl.critical { color: #ef4444; }
.log-host, .log-svc { flex-shrink: 0; font-size: 0.7rem; color: var(--text-secondary, #64748b); }
.log-svc::before { content: '· '; }
.log-msg { flex: 1; min-width: 0; color: var(--text, #1e293b); font-family: 'JetBrains Mono', monospace; word-break: break-all; white-space: pre-wrap; }
.log-msg.collapsed { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.log-repeat { flex-shrink: 0; font-size: 0.68rem; font-weight: 700; color: #6366f1; }
.dedup-toggle { display: inline-flex; align-items: center; gap: 4px; font-size: 0.82rem; color: var(--text-secondary, #64748b); cursor: pointer; white-space: nowrap; user-select: none; }
.dedup-toggle input { cursor: pointer; }
.dedup-badge { display: inline-block; margin-left: 2px; padding: 0 5px; font-size: 0.65rem; font-weight: 700; color: #6366f1; background: rgba(99,102,241,0.1); border-radius: 4px; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 10px; margin-top: 16px; }
.page-info { font-size: 0.82rem; color: var(--text-secondary, #64748b); }
</style>
