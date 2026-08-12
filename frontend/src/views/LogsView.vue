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
      <button class="btn btn-ai" :disabled="!selectedLogs.length || aiLoading" @click="openAnalyze">
        {{ aiLoading ? '分析中...' : `AI 分析选中日志 (${selectedLogs.length})` }}
      </button>
      <button class="btn btn-history" @click="openHistory">🕘 历史</button>
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
          <div v-for="(log, idx) in logs" :key="log.id || idx" class="log-row" :class="{ expanded: expandedSet.has(idx), selected: selectedSet.has(idx) }" @click="toggleExpand(idx)">
            <input type="checkbox" class="log-check" :checked="selectedSet.has(idx)" @click.stop="toggleSelect(idx)">
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

    <!-- AI 分析结果抽屉 -->
    <div v-if="showAnalyze" class="ai-drawer-mask" @click.self="showAnalyze = false">
      <div class="ai-drawer">
        <div class="ai-drawer-head">
          <b>AI 日志分析</b>
          <span class="ai-drawer-meta">{{ analyzeMeta }}</span>
          <button class="btn btn-sm" @click="showAnalyze = false">关闭</button>
        </div>
        <textarea v-model="analyzeQuestion" class="ai-question" placeholder="附加分析诉求（可选），如：重点排查数据库连接错误" rows="2"></textarea>
        <button class="btn btn-primary btn-sm" @click="runAnalyze" :disabled="aiLoading">{{ aiLoading ? '分析中...' : '开始分析' }}</button>
        <div v-if="aiError" class="error-bar">⚠ {{ aiError }}</div>
        <div v-if="aiLoading" class="loading-state">AI 正在分析 {{ selectedLogs.length }} 条日志...</div>
        <div v-else-if="analysisText">
          <div v-if="clusterSummary && clusterSummary.length" class="cluster-panel">
            <div class="cp-head">📊 日志聚类摘要（{{ clusterSummary.length }} 组）</div>
            <div v-for="c in clusterSummary.slice(0, 10)" :key="c.service + '-' + c.level + '-' + c.error_type" class="cp-row">
              <span class="cp-level" :class="'lvl-' + c.level">{{ c.level }}</span>
              <span class="cp-svc">{{ c.service }}</span>
              <span v-if="c.host && c.host !== 'unknown'" class="cp-host">{{ c.host }}</span>
              <span v-if="c.error_type" class="cp-type">{{ c.error_type }}</span>
              <span class="cp-count">×{{ c.count }}</span>
            </div>
          </div>
          <div class="ai-result" v-html="analysisHtml"></div>
        </div>
        <div v-else class="empty-hint">点击"开始分析"调用大模型分析勾选的日志</div>
        <div v-if="analysisText && !aiLoading" class="ai-transfer-bar">
          <button class="btn-transfer" :disabled="transferring" @click="transferToAgent">
            {{ transferring ? '转交中...' : '转交执行 → 智能助手' }}
          </button>
          <span class="ai-transfer-tip">生成待确认动作，经你确认后才执行</span>
        </div>
      </div>
    </div>

    <div v-if="showHistory" class="modal-overlay" @click.self="closeHistory">
      <div class="modal-box" style="width:680px;max-height:80vh;overflow-y:auto">
        <div class="modal-head">
          <b>🕘 AI 日志分析历史</b>
          <button class="btn btn-sm" @click="closeHistory">关闭</button>
        </div>
        <div v-if="historyLoading" class="loading-state">加载中...</div>
        <div v-else-if="historyDetail" class="history-detail">
          <button class="btn btn-sm" @click="historyDetail = null" style="margin-bottom:10px">← 返回列表</button>
          <div class="history-title">{{ historyDetail.title }}</div>
          <div class="history-meta">{{ historyDetail.created_at }} · 评分: {{ historyDetail.score }}/100 · {{ historyDetail.provider }}</div>
          <div class="history-content" v-html="mdToHtml(historyDetail.analysis)"></div>
        </div>
        <div v-else>
          <div v-for="h in historyList" :key="h.id" class="history-item" @click="loadHistoryDetail(h.id)">
            <div class="hi-title">{{ h.title }}</div>
            <div class="hi-meta">{{ h.created_at }} · 评分{{ h.score }} · {{ h.provider }}</div>
            <div class="hi-preview">{{ h.analysis_preview }}</div>
            <button class="hi-del" @click.stop="deleteHistory(h.id)">删除</button>
          </div>
          <div v-if="!historyList.length" class="empty-hint">暂无历史分析记录</div>
        </div>
      </div>
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
const showFilters = ref(true)
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
const selectedSet = ref(new Set())

function toggleSelect(idx) {
  const s = new Set(selectedSet.value)
  if (s.has(idx)) s.delete(idx)
  else s.add(idx)
  selectedSet.value = s
}

const selectedLogs = computed(() => {
  return [...selectedSet.value].sort((a, b) => a - b).map(i => logs.value[i]).filter(Boolean)
})

function toggleExpand(idx) {
  const s = new Set(expandedSet.value)
  if (s.has(idx)) s.delete(idx)
  else s.add(idx)
  expandedSet.value = s
}

const showAnalyze = ref(false)
const aiLoading = ref(false)
const aiError = ref('')
const analysisText = ref('')
const analyzeQuestion = ref('')
const analyzeMeta = ref('')
const transferring = ref(false)
const clusterSummary = ref(null)
const showHistory = ref(false)
const historyList = ref([])
const historyLoading = ref(false)
const historyDetail = ref(null)

function openAnalyze() {
  if (!selectedLogs.value.length) { ElMessage.warning('请先勾选日志'); return }
  showAnalyze.value = true
  aiError.value = ''
  analyzeMeta.value = `数据源: ${currentSourceName} · 已选 ${selectedLogs.value.length} 条`
}

async function runAnalyze() {
  if (aiLoading.value) return
  aiLoading.value = true; aiError.value = ''
  clusterSummary.value = null
  try {
    const logsData = selectedLogs.value.map(l => ({
      timestamp: l.timestamp, level: l.level, host: l.host,
      service: l.service, message: l.message,
    }))
    const res = await request.post('/ai-insight/analyze', {
      source_type: 'logs',
      source_id: sourceId.value,
      logs: logsData,
      question: analyzeQuestion.value || '',
      title: `日志分析 #${Date.now().toString().slice(-6)}`,
    }, { timeout: 120000 })
    if (!res.ok) { aiError.value = res.error || '分析失败'; return }
    analysisText.value = res.analysis || ''
    const m = res.meta || {}
    analyzeMeta.value = `数据源: ${currentSourceName} · 已选 ${logsData.length} 条 · 聚类 ${m.cluster_count || 0} 组 · 模型: ${res.provider || '-'} · 记录 #${res.record_id || '-'}`
    if (res.enhanced && res.enhanced.clusters) {
      clusterSummary.value = res.enhanced.clusters
    }
  } catch (e) {
    aiError.value = e.response?.data?.error || e.message || '分析失败'
  } finally {
    aiLoading.value = false
  }
}

async function transferToAgent() {
  if (transferring.value || !analysisText.value) return
  transferring.value = true
  aiError.value = ''
  try {
    const res = await request.post('/agent/transfer-from-analysis', {
      source_type: 'logs',
      title: `日志异常转交 #${Date.now().toString().slice(-6)}`,
      analysis: analysisText.value || '',
      context: {
        source_id: sourceId.value,
        source_name: currentSourceName,
        log_count: selectedLogs.value.length,
        level_filter: filterLevel.value || '',
        host_filter: filterHost.value || '',
        sample_logs: selectedLogs.value.slice(0, 10).map(l =>
          `${l.timestamp || ''} [${l.level || ''}] ${l.host || ''} ${l.service || ''}: ${(l.message || '').slice(0, 120)}`
        ).join('\n'),
      },
      instruction: '',
    })
    if (res.session_id) {
      window._pendingAgentSessionId = res.session_id
      window._navigateTo && window._navigateTo('agent-chat')
    } else {
      aiError.value = res.error || '转交失败'
    }
  } catch (e) {
    aiError.value = '转交执行请求失败：' + (e.message || e)
  } finally {
    transferring.value = false
  }
}

const analysisHtml = computed(() => {
  if (!analysisText.value) return ''
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const md = esc(analysisText.value)
  return md
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => `<pre class="ai-code">${code.trim()}</pre>`)
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h4>$1</h4>')
    .replace(/^# (.+)$/gm, '<h4>$1</h4>')
    .replace(/^\*\*(.+)\*\*$/gm, '<p><b>$1</b></p>')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/^\s*[-*] (.+)$/gm, '<li>$1</li>')
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/\n/g, '<br>')
    .replace(/<li>([\s\S]*?)<br>/g, '<li>$1')
    .replace(/<p>/g, '<p style="margin:6px 0">')
    .replace(/(^|<\/li>)(<li>)/g, '$1$2')
    .replace(/<br><li>/g, '</li><li>')
    .replace(/<li>([\s\S]*?)<\/li>/g, '<li style="margin-left:14px">$1</li>')
})

const rules = ref([])
const showNewRule = ref(false)
const newRule = ref({ name: '', keyword: '', log_level: 'error', threshold: 1, window_minutes: 5, severity: 'warning' })

const isLokiSource = computed(() => {
  const s = sources.value.find(x => x.id === sourceId.value)
  return s && s.type === 'loki'
})

const currentSourceName = computed(() => {
  const s = sources.value.find(x => x.id === sourceId.value)
  return s ? s.name : ''
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
  selectedSet.value = new Set(); analysisText.value = ''; showAnalyze.value = false
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

async function openHistory() {
  showHistory.value = true
  historyDetail.value = null
  historyLoading.value = true
  try {
    historyList.value = await request.get('/ai-insight/history', { params: { source_type: 'logs', limit: 50 } })
  } catch (e) { /* ignore */ }
  finally { historyLoading.value = false }
}

async function loadHistoryDetail(id) {
  try { historyDetail.value = await request.get(`/ai-insight/history/${id}`) } catch (e) { /* ignore */ }
}

async function deleteHistory(id) {
  try {
    await request.delete(`/ai-insight/history/${id}`)
    historyList.value = historyList.value.filter(h => h.id !== id)
    ElMessage.success('已删除')
  } catch (e) { /* ignore */ }
}

function closeHistory() { showHistory.value = false; historyDetail.value = null }

function mdToHtml(text) {
  if (!text) return ''
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc(text).replace(/\n/g, '<br>')
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
.btn-ai { color: #fff; background: linear-gradient(135deg, #6366f1, #8b5cf6); border-color: transparent; }
.btn-ai:hover { filter: brightness(1.08); }
.btn-ai:disabled { opacity: 0.4; cursor: not-allowed; filter: none; }
.btn-history { color: var(--text-secondary, #64748b); }
.btn-history:hover { border-color: var(--accent, #6366f1); color: var(--accent, #6366f1); }
.cluster-panel {
  background: var(--bg-secondary, #f8fafc); border: 1px solid rgba(148,163,184,0.12);
  border-radius: 8px; padding: 10px 12px; margin-bottom: 12px;
}
.cp-head { font-size: 0.82rem; font-weight: 700; margin-bottom: 8px; color: var(--text, #1e293b); }
.cp-row { display: flex; gap: 8px; align-items: center; padding: 3px 0; font-size: 0.78rem; flex-wrap: wrap; }
.cp-level { font-size: 0.68rem; font-weight: 700; padding: 1px 6px; border-radius: 4px; }
.cp-level.lvl-error, .cp-level.lvl-critical, .cp-level.lvl-fatal { background: rgba(239,68,68,0.1); color: #ef4444; }
.cp-level.lvl-warning, .cp-level.lvl-warn { background: rgba(245,158,11,0.1); color: #d97706; }
.cp-level.lvl-info { background: rgba(59,130,246,0.1); color: #3b82f6; }
.cp-svc { font-weight: 600; color: var(--text, #1e293b); }
.cp-host { font-size: 0.7rem; color: var(--text-secondary, #64748b); }
.cp-type { font-size: 0.7rem; padding: 1px 6px; border-radius: 4px; background: rgba(99,102,241,0.1); color: #6366f1; }
.cp-count { margin-left: auto; font-size: 0.72rem; font-weight: 700; color: #6366f1; }
.modal-overlay {
  position: fixed; inset: 0; z-index: 2000; background: rgba(0,0,0,0.45);
  display: flex; align-items: center; justify-content: center; padding: 20px;
}
.modal-box { background: var(--bg-card, #fff); border-radius: 12px; padding: 18px 20px; width: 560px; max-width: 92vw; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
.modal-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.loading-state, .empty-hint { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.85rem; }
.history-item { padding: 10px 12px; border-bottom: 1px solid rgba(148,163,184,0.1); cursor: pointer; transition: background 0.15s; position: relative; }
.history-item:hover { background: rgba(99,102,241,0.04); }
.hi-title { font-size: 0.85rem; font-weight: 600; color: var(--text, #1e293b); }
.hi-meta { font-size: 0.72rem; color: var(--text-tertiary, #94a3b8); margin: 2px 0; }
.hi-preview { font-size: 0.78rem; color: var(--text-secondary, #64748b); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hi-del { position: absolute; top: 10px; right: 10px; font-size: 0.7rem; color: #ef4444; background: none; border: 1px solid rgba(239,68,68,0.2); border-radius: 4px; padding: 2px 8px; cursor: pointer; }
.history-detail { padding: 8px 0; }
.history-title { font-size: 0.95rem; font-weight: 700; color: var(--text, #1e293b); }
.history-meta { font-size: 0.75rem; color: var(--text-tertiary, #94a3b8); margin: 4px 0 10px; }
.history-content { font-size: 0.85rem; line-height: 1.7; color: var(--text, #1e293b); }
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
.log-row.selected { background: rgba(139,92,246,0.12); }
.log-check { flex-shrink: 0; width: 14px; height: 14px; margin: 0; cursor: pointer; accent-color: #6366f1; align-self: center; }
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
.ai-drawer-mask { position: fixed; inset: 0; background: rgba(15,23,42,0.45); z-index: 100; display: flex; justify-content: flex-end; }
.ai-drawer { width: 720px; max-width: 92vw; height: 100%; background: var(--bg-card, #fff); box-shadow: -8px 0 24px rgba(0,0,0,0.15); display: flex; flex-direction: column; padding: 16px 20px; gap: 10px; overflow-y: auto; }
.ai-drawer-head { display: flex; align-items: center; gap: 10px; font-size: 1rem; }
.ai-drawer-meta { flex: 1; color: var(--text-secondary, #64748b); font-size: 0.78rem; }
.ai-question { width: 100%; padding: 8px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; font-size: 0.82rem; resize: vertical; font-family: inherit; }
.ai-result { background: var(--bg-secondary, #f8fafc); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; padding: 14px 16px; font-size: 0.86rem; line-height: 1.7; color: var(--text, #1e293b); }
.ai-code { background: #0f172a; color: #e2e8f0; padding: 10px 12px; border-radius: 6px; font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; overflow-x: auto; white-space: pre-wrap; }
.ai-transfer-bar {
  display: flex; align-items: center; gap: 10px; margin-top: 6px;
  padding-top: 12px; border-top: 1px dashed rgba(148,163,184,0.3);
}
.btn-transfer {
  padding: 7px 16px; border-radius: 6px; border: none; cursor: pointer;
  background: linear-gradient(135deg, #0ea5e9, #6366f1);
  color: #fff; font-size: 13px; font-weight: 600; font-family: inherit;
}
.btn-transfer:disabled { opacity: 0.5; cursor: not-allowed; }
.ai-transfer-tip { font-size: 11px; color: #909399; }
</style>
