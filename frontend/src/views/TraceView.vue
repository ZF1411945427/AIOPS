<template>
  <div class="workbench-page-shell">
    <div class="section-toolbar">
      <div class="toolbar-head">
        <span class="toolbar-title">链路追踪</span>
        <span class="toolbar-desc">分布式调用链查询与可视化</span>
      </div>
      <div class="workbench-card-actions">
        <button class="btn btn-guide" @click="showGuide = !showGuide">📖 操作说明</button>
        <el-button type="primary" size="small" @click="openAiAnalyze" :disabled="aiLoading || !traces.length">
          {{ aiLoading ? 'AI 分析中...' : 'AI 链路分析' }}
        </el-button>
        <el-button size="small" @click="openHistory">🕘 历史</el-button>
        <el-button size="small" @click="loadTraces" :loading="loading">刷新</el-button>
      </div>
    </div>

    <div class="stats-row">
      <div class="stat-card stat-total"><div class="stat-num">{{ totalCount }}</div><div class="stat-lbl">调用链</div></div>
      <div class="stat-card stat-svc"><div class="stat-num">{{ serviceList.length }}</div><div class="stat-lbl">服务</div></div>
      <div class="stat-card stat-dur"><div class="stat-num">{{ avgDuration }}ms</div><div class="stat-lbl">平均耗时</div></div>
      <div class="stat-card stat-err"><div class="stat-num">{{ errorRate }}%</div><div class="stat-lbl">错误率</div></div>
    </div>

    <div class="workbench-card filter-card">
      <div class="filter-row">
        <div class="filter-item">
          <label>业务域</label>
          <el-select v-model="filters.domain" clearable placeholder="全部" size="small" style="width:140px" @change="onDomainChange">
            <el-option v-for="d in domainList" :key="d" :value="d" :label="d" />
          </el-select>
        </div>
        <div class="filter-item">
          <label>服务</label>
          <el-select v-model="filters.service" clearable placeholder="全部" size="small" style="width:160px">
            <el-option v-for="s in serviceList" :key="s" :value="s" :label="s" />
          </el-select>
        </div>
        <div class="filter-item">
          <label>关键词</label>
          <el-input v-model="filters.keyword" placeholder="traceID/服务/操作" size="small" style="width:180px" clearable />
        </div>
        <div class="filter-item">
          <label>状态</label>
          <el-select v-model="filters.status" clearable placeholder="全部" size="small" style="width:110px">
            <el-option value="OK" label="正常" />
            <el-option value="ERROR" label="异常" />
          </el-select>
        </div>
        <div class="filter-item">
          <label>最小时长</label>
          <el-input v-model.number="filters.min_dur" placeholder="ms" size="small" style="width:90px" />
        </div>
        <div class="filter-item">
          <label>条数</label>
          <el-select v-model="filters.limit" size="small" style="width:90px">
            <el-option :value="20" label="20" />
            <el-option :value="50" label="50" />
            <el-option :value="100" label="100" />
          </el-select>
        </div>
        <div class="filter-item">
          <el-button type="primary" size="small" @click="loadTraces">查询</el-button>
        </div>
      </div>
    </div>

    <div class="trace-layout">
      <div class="workbench-card result-card">
        <div class="card-header">
          <span>查询结果 <span class="count-badge">{{ traces.length }}</span></span>
          <span class="header-hint">点击查看详情</span>
        </div>
        <div class="trace-list" ref="listRef">
          <div
            v-for="tr in traces"
            :key="tr.trace_id"
            class="trace-item"
            :class="{ active: selectedTrace?.trace_id === tr.trace_id }"
            @click="showDetail(tr)"
          >
            <div class="trace-main">
              <div class="trace-service">
                <span class="status-dot" :class="tr.worst_status === 'ERROR' ? 'dot-error' : 'dot-ok'" />
                <span class="svc-label">{{ tr.root_service }}</span>
                <span class="op-label">{{ tr.root_operation }}</span>
              </div>
              <div class="trace-meta">
                <span class="trace-id-label">{{ tr.trace_id }}</span>
                <span class="trace-time">{{ tr.started_at }}</span>
              </div>
            </div>
            <div class="trace-stats">
              <span class="stat-badge" :class="tr.worst_status === 'ERROR' ? 'badge-err' : 'badge-ok'">{{ tr.worst_status }}</span>
              <div class="dur-bar-wrap">
                <div class="dur-bar" :style="{ width: durPct(tr.total_duration_ms) + '%', background: durColor(tr.total_duration_ms) }" />
              </div>
              <span class="dur-text">{{ tr.total_duration_ms }}ms</span>
            </div>
          </div>
          <div v-if="!traces.length" class="empty-trace">暂无调用链数据</div>
        </div>
      </div>

      <div class="workbench-card detail-card">
        <template v-if="selectedTrace">
          <div class="card-header">
            <div class="detail-tabs">
              <span class="tab-btn" :class="{ active: detailTab === 'waterfall' }" @click="detailTab = 'waterfall'">瀑布图</span>
              <span class="tab-btn" :class="{ active: detailTab === 'topology' }" @click="detailTab = 'topology'">拓扑图</span>
              <span class="tab-btn" :class="{ active: detailTab === 'span-detail' }" @click="detailTab = 'span-detail'">Span详情</span>
            </div>
            <el-button size="small" text @click="selectedTrace = null; detailTab = 'waterfall'">关闭</el-button>
          </div>

          <div class="detail-summary">
            <div class="chip">根服务: <strong>{{ detailData.root_service }}</strong></div>
            <div class="chip">总耗时: <strong>{{ detailData.root_duration_ms }}ms</strong></div>
            <div class="chip">Spans: <strong>{{ detailData.total_spans }}</strong></div>
            <div class="chip">服务数: <strong>{{ detailData.services?.length || 0 }}</strong></div>
          </div>

          <!-- Waterfall View -->
          <div v-show="detailTab === 'waterfall'" class="waterfall-view">
            <div class="waterfall-header">
              <div class="wf-svc-h">服务 / 操作</div>
              <div class="wf-timeline-h">时间轴 <span class="wf-scale">{{ detailData.root_duration_ms }}ms</span></div>
              <div class="wf-dur-h">耗时</div>
            </div>
            <div class="waterfall-body" ref="wfBody">
              <div
                v-for="(s, idx) in detailData.spans"
                :key="s.span_id"
                class="wf-row"
                :class="{ 'wf-child': s.parent_span_id, 'wf-selected': selectedSpanId === s.span_id }"
                @click="selectedSpanId = s.span_id"
              >
                <div class="wf-svc">
                  <span class="wf-depth" v-for="n in depthLevel(s)" :key="n" />
                  <span class="wf-svc-name" :style="{ color: serviceColor(s.service_name) }">{{ s.service_name }}</span>
                  <span class="wf-op-name">{{ s.operation_name }}</span>
                  <span v-if="s.status === 'ERROR'" class="wf-error">ERROR</span>
                </div>
                <div class="wf-timeline">
                  <div class="wf-bar" :style="wfBarStyle(s)" :title="s.operation_name + ' | ' + s.duration_ms + 'ms'" />
                </div>
                <div class="wf-dur">{{ s.duration_ms }}ms</div>
              </div>
            </div>
            <div class="waterfall-colors">
              <span v-for="svc in detailData.services" :key="svc" class="color-chip">
                <span class="color-dot" :style="{ background: serviceColor(svc) }" />
                {{ svc }}
              </span>
            </div>
          </div>

          <!-- Topology View -->
          <div v-show="detailTab === 'topology'" class="topology-view">
            <svg ref="topoSvg" class="topo-svg" />
          </div>

          <!-- Span Detail View -->
          <div v-show="detailTab === 'span-detail'" class="span-detail-view">
            <div v-if="selectedSpan" class="span-meta">
              <div class="span-meta-row"><span class="meta-key">Span ID</span><span class="meta-val">{{ selectedSpan.span_id }}</span></div>
              <div class="span-meta-row"><span class="meta-key">父 Span</span><span class="meta-val">{{ selectedSpan.parent_span_id || '根Span' }}</span></div>
              <div class="span-meta-row"><span class="meta-key">服务</span><span class="meta-val">{{ selectedSpan.service_name }}</span></div>
              <div class="span-meta-row"><span class="meta-key">操作</span><span class="meta-val">{{ selectedSpan.operation_name }}</span></div>
              <div class="span-meta-row"><span class="meta-key">开始时间</span>                <span class="meta-val">{{ selectedSpan.started_at }}</span></div>
              <div class="span-meta-row"><span class="meta-key">耗时</span><span class="meta-val">{{ selectedSpan.duration_ms }}ms</span></div>
              <div class="span-meta-row"><span class="meta-key">状态</span><span class="meta-val">
                <el-tag :type="selectedSpan.status === 'OK' ? 'success' : 'danger'" size="small">{{ selectedSpan.status }}</el-tag>
              </span></div>
            </div>
            <div v-if="selectedSpan && hasTags(selectedSpan)" class="span-tags">
              <div class="tags-title">Tags</div>
              <div v-for="(v, k) in selectedSpan.tags" :key="k" class="tag-row">
                <span class="tag-key">{{ k }}</span>
                <span class="tag-val">{{ v }}</span>
              </div>
            </div>
            <div v-if="!selectedSpan" class="empty-trace">点击瀑布图中的 Span 查看详情</div>
          </div>
        </template>
        <template v-else>
          <div class="empty-detail">
            <div class="empty-icon">🔍</div>
            <div class="empty-text">点击左侧调用链查看详情</div>
          </div>
        </template>
      </div>
    </div>
  </div>

  <GuideDrawer v-model="showGuide" title="📖 链路追踪 · 操作说明">
    <section class="guide-section">
      <h4>1. 什么是链路追踪？</h4>
      <p>当用户请求一个 API 时，后端通常会<strong>调用多个服务</strong>才能返回结果（比如 网关→认证→订单→支付→库存）。<strong>链路追踪（Tracing）</strong>就是把这些调用串联起来，形成一个完整的<strong>调用链</strong>，让你一眼看出哪里慢、哪里出错。</p>
      <div class="tip-box">💡 类比：一个快递从发货到签收经过多个中转站。链路追踪就是给每个快递贴一张"追踪单"，记录每个中转站的到达和离开时间。</div>
    </section>
    <section class="guide-section">
      <h4>2. 核心概念</h4>
      <div class="key-value-list">
        <div class="kv-row">
          <span class="kv-key">Trace</span>
          <span class="kv-val">一次完整请求的<strong>调用链</strong>，包含所有经过的服务和耗时。每个 Trace 有一个唯一的 trace_id</span>
        </div>
        <div class="kv-row">
          <span class="kv-key">Span</span>
          <span class="kv-val">调用链中的<strong>一个步骤</strong>（比如"查数据库"这个操作就是一个 Span）。Span 会记录开始时间、结束时间、状态、标签等</span>
        </div>
        <div class="kv-row">
          <span class="kv-key">Waterfall（瀑布图）</span>
          <span class="kv-val">Span 的<strong>可视化展示</strong>，每个 Span 是一条横条，横条越长说明越慢。父 Span 在上，子 Span 在下缩进，形成瀑布一样的层次结构</span>
        </div>
      </div>
    </section>
    <section class="guide-section">
      <h4>3. 怎么看瀑布图？</h4>
      <ul>
        <li><strong>横条长度</strong> = 该操作的耗时，越长越慢</li>
        <li><strong>颜色</strong> = 不同服务用不同颜色区分</li>
        <li><strong>层级缩进</strong> = 调用深度，缩进越多说明调用链越长</li>
        <li><strong>红色横条</strong> = 该 Span 执行出错，需要重点关注</li>
        <li>把最长的横条和红色的横条找出来，就找到了性能瓶颈和错误点</li>
      </ul>
    </section>
    <section class="guide-section">
      <h4>4. 这个页面怎么用？</h4>
      <ul>
        <li><strong>过滤</strong> — 按服务名、关键词、状态、最小时长筛选关注的调用链</li>
        <li><strong>结果列表</strong> — 每条 Trace 显示根服务、操作名、耗时、状态。点开查看详情</li>
        <li><strong>瀑布图</strong> — 可视化展示每个 Span 的调用关系和耗时</li>
        <li><strong>服务拓扑</strong> — 展示服务之间的调用关系图，看哪些服务依赖哪些服务</li>
      </ul>
    </section>
  </GuideDrawer>

  <div v-if="aiDrawer.show" class="ai-drawer-mask" @click.self="closeAiDrawer">
    <div class="ai-drawer">
      <div class="ai-drawer-head">
        <div>
          <div class="ai-drawer-title">AI 链路分析</div>
          <div v-if="aiMeta" class="ai-drawer-meta">{{ aiMeta }}</div>
        </div>
        <button class="ai-drawer-close" @click="closeAiDrawer">&times;</button>
      </div>
      <div class="ai-drawer-body">
        <div class="ai-trace-note">
          将分析当前查询结果中的 <b>{{ traces.length }}</b> 条调用链（默认取异常/慢链路优先，自动裁剪 span 控制 token）。
        </div>
        <div class="ai-question-row">
          <input
            v-model="aiQuestion" class="ai-question-input"
            placeholder="可选：输入你想问的（如：哪个服务是瓶颈？）" @keyup.enter="runAiAnalyze"
          />
          <button class="btn-ai" :disabled="aiLoading" @click="runAiAnalyze">{{ aiLoading ? '分析中...' : '开始分析' }}</button>
        </div>
        <div v-if="aiError" class="ai-error-bar">{{ aiError }}</div>
        <div v-if="aiLoading" class="ai-loading">
          <div class="ai-spinner"></div>
          <span>AI 正在分析调用链...</span>
        </div>
        <div v-else-if="aiResult">
          <div v-if="bottleneckSvc && bottleneckSvc.length" class="bottleneck-panel">
            <div class="bn-head">📊 跨链路瓶颈聚合</div>
            <div v-for="s in bottleneckSvc.slice(0, 8)" :key="s.service" class="bn-row">
              <span class="bn-rank">#{{ bottleneckSvc.indexOf(s) + 1 }}</span>
              <span class="bn-svc">{{ s.service }}</span>
              <span class="bn-p90">P90 {{ s.p90_duration_ms }}ms</span>
              <span class="bn-err" :class="{ 'bn-err-high': s.error_rate > 10 }">错误率 {{ s.error_rate }}%</span>
              <div class="bn-bar-wrap"><div class="bn-bar" :style="{ width: Math.min(s.bottleneck_score * 10, 100) + '%' }"></div></div>
            </div>
          </div>
          <div v-if="aiKeyPoints && (aiKeyPoints.root_cause || aiKeyPoints.solution)" class="key-points">
            <div class="kp-title">📌 要点总结</div>
            <div v-if="aiKeyPoints.root_cause" class="kp-row"><span class="kp-tag">根因</span><span class="kp-text">{{ aiKeyPoints.root_cause }}</span></div>
            <div v-if="aiKeyPoints.solution" class="kp-row"><span class="kp-tag">方案</span><span class="kp-text">{{ aiKeyPoints.solution }}</span></div>
            <div v-if="aiKeyPoints.impact" class="kp-row"><span class="kp-tag">影响</span><span class="kp-text">{{ aiKeyPoints.impact }}</span></div>
          </div>
          <div class="ai-result" v-html="aiResult"></div>
        </div>
        <div v-else class="ai-empty">点击「开始分析」，AI 将基于当前查询结果做瓶颈定位与根因分析</div>
        <div v-if="aiResult && !aiLoading" class="ai-transfer-bar">
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
          <b>🕘 AI 链路分析历史</b>
          <button class="d-close" @click="closeHistory">&times;</button>
        </div>
        <div v-if="historyLoading" class="empty-trace">加载中...</div>
        <div v-else-if="historyDetail" class="history-detail">
          <button class="d-close" @click="historyDetail = null" style="position:static;display:inline-block;margin-bottom:10px;font-size:12px">← 返回列表</button>
          <div class="hi-title">{{ historyDetail.title }}</div>
          <div class="hi-meta">{{ historyDetail.created_at }} · 评分: {{ historyDetail.score }}/100 · {{ historyDetail.provider }}</div>
          <div class="hi-content" v-html="mdToHtml(historyDetail.analysis)"></div>
        </div>
        <div v-else>
          <div v-for="h in historyList" :key="h.id" class="hi-item" @click="loadHistoryDetail(h.id)">
            <div class="hi-title">{{ h.title }}</div>
            <div class="hi-meta">{{ h.created_at }} · 评分{{ h.score }} · {{ h.provider }}</div>
            <div class="hi-preview">{{ h.analysis_preview }}</div>
            <button class="hi-del" @click.stop="deleteHistory(h.id)">删除</button>
          </div>
          <div v-if="!historyList.length" class="empty-trace">暂无历史分析记录</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch, nextTick } from 'vue'
import request from '@/api/request'
import GuideDrawer from '@/components/GuideDrawer.vue'

const showGuide = ref(false)
const loading = ref(false)
const traces = ref([])
const totalCount = ref(0)
const serviceList = ref([])
const domainList = ref([])
const selectedTrace = ref(null)
const selectedSpanId = ref('')
const detailData = ref({ spans: [], services: [], root_duration_ms: 0, topology: { services: [], edges: [] } })
const detailTab = ref('waterfall')
const wfBody = ref(null)
const topoSvg = ref(null)
const listRef = ref(null)
const aiDrawer = ref({ show: false })
const aiQuestion = ref('')
const aiLoading = ref(false)
const aiError = ref('')
const aiResult = ref('')
const aiResultRaw = ref('')
const aiKeyPoints = ref(null)
const aiMeta = ref('')
const transferring = ref(false)
const bottleneckSvc = ref([])
const showHistory = ref(false)
const historyList = ref([])
const historyLoading = ref(false)
const historyDetail = ref(null)

const filters = reactive({
  domain: '', service: '', keyword: '', status: '', min_dur: 0, limit: 50,
})

const SERVICE_COLORS = [
  '#6366f1','#10b981','#f59e0b','#ef4444','#8b5cf6',
  '#06b6d4','#ec4899','#14b8a6','#f97316','#6b7280',
]

const selectedSpan = computed(() => {
  if (!selectedSpanId.value) return null
  return detailData.value.spans?.find(s => s.span_id === selectedSpanId.value) || null
})

const avgDuration = computed(() => {
  if (!traces.value.length) return 0
  return Math.round(traces.value.reduce((a, t) => a + t.total_duration_ms, 0) / traces.value.length)
})

const errorRate = computed(() => {
  if (!traces.value.length) return 0
  const errs = traces.value.filter(t => t.worst_status === 'ERROR').length
  return Math.round((errs / traces.value.length) * 100)
})

function durPct(dur) {
  if (!traces.value.length) return 50
  const max = Math.max(...traces.value.map(t => t.total_duration_ms))
  return max > 0 ? (dur / max) * 100 : 50
}

function durColor(dur) {
  if (dur >= 800) return '#ef4444'
  if (dur >= 300) return '#f59e0b'
  return '#10b981'
}

function serviceColor(svc) {
  let hash = 0
  for (let i = 0; i < svc.length; i++) hash = svc.charCodeAt(i) + ((hash << 5) - hash)
  return SERVICE_COLORS[Math.abs(hash) % SERVICE_COLORS.length]
}

function depthLevel(span) {
  if (!span.parent_span_id) return 0
  let depth = 0
  let s = span
  while (s.parent_span_id) {
    depth++
    s = detailData.value.spans?.find(sp => sp.span_id === s.parent_span_id)
    if (!s) break
  }
  return Math.min(depth, 4)
}

function hasTags(span) {
  return span.tags && Object.keys(span.tags).length > 0
}

function wfBarStyle(span) {
  const rootSpan = detailData.value.spans?.find(s => !s.parent_span_id)
  if (!rootSpan || !rootSpan.started_at) return { width: '4px', left: '0%' }
  const rootStart = new Date(rootSpan.started_at).getTime()
  const spanStart = new Date(span.started_at).getTime()
  const offset = Math.max(0, spanStart - rootStart)
  const rootDur = rootSpan.duration_ms || 1
  const leftPct = (offset / rootDur) * 100
  const widthPct = Math.max(3, (span.duration_ms / rootDur) * 100)
  return {
    position: 'absolute', left: Math.min(leftPct, 98) + '%',
    width: widthPct + '%', minWidth: '4px', height: '12px',
    borderRadius: '4px', top: '3px',
    background: serviceColor(span.service_name),
    opacity: selectedSpanId.value && selectedSpanId.value !== span.span_id ? 0.4 : 0.9,
    transition: 'opacity 0.15s, left 0.2s',
  }
}

function drawTopology() {
  nextTick(() => {
    const svg = topoSvg.value
    if (!svg || !detailData.value.topology) return
    const { services, edges } = detailData.value.topology
    if (!services || services.length < 2) {
      svg.innerHTML = ''
      return
    }
    const W = 440, H = 340, cx = W / 2, cy = H / 2, R = Math.min(W, H) / 2 - 50
    const angleStep = (2 * Math.PI) / services.length
    const positions = services.map((svc, i) => ({
      svc,
      x: cx + R * Math.cos(angleStep * i - Math.PI / 2),
      y: cy + R * Math.sin(angleStep * i - Math.PI / 2),
    }))
    let html = `<defs><marker id="arrow" markerWidth="8" markerHeight="6" refX="20" refY="3" orient="auto"><path d="M0,0 L8,3 L0,6" fill="#94a3b8"/></marker></defs>`
    html += `<rect x="0" y="0" width="${W}" height="${H}" fill="none" rx="12"/>`
    const seenEdges = new Set()
    for (const e of edges) {
      const key = e.source + '→' + e.target
      if (seenEdges.has(key)) continue
      seenEdges.add(key)
      const src = positions.find(p => p.svc === e.source)
      const dst = positions.find(p => p.svc === e.target)
      if (!src || !dst) continue
      html += `<line x1="${src.x}" y1="${src.y}" x2="${dst.x}" y2="${dst.y}" stroke="#94a3b8" stroke-width="1.5" marker-end="url(#arrow)" opacity="0.6"/>`
    }
    for (const p of positions) {
      html += `<circle cx="${p.x}" cy="${p.y}" r="22" fill="${serviceColor(p.svc)}" opacity="0.9"/>`
      html += `<text x="${p.x}" y="${p.y + 4}" text-anchor="middle" fill="#fff" font-size="11" font-weight="600">${p.svc.substring(0, 8)}</text>`
    }
    svg.innerHTML = html
  })
}

watch(detailTab, (tab) => {
  if (tab === 'topology') drawTopology()
})

async function loadTraces() {
  loading.value = true
  try {
    const params = {}
    if (filters.domain) params.domain = filters.domain
    if (filters.service) params.service = filters.service
    if (filters.keyword) params.keyword = filters.keyword
    if (filters.status) params.status = filters.status
    if (filters.min_dur > 0) params.min_dur = filters.min_dur
    params.limit = filters.limit
    const res = await request.get('/api/traces', { params })
    traces.value = res.traces || []
    totalCount.value = res.total || 0
    serviceList.value = res.services || []
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

async function loadDomains() {
  try {
    const res = await request.get('/api/traces/domains')
    domainList.value = res || []
  } catch (e) { console.error(e) }
}

async function onDomainChange() {
  filters.service = ''
  try {
    const params = {}
    if (filters.domain) params.domain = filters.domain
    const res = await request.get('/api/traces/services', { params })
    serviceList.value = res || []
  } catch (e) { console.error(e) }
  loadTraces()
}

async function showDetail(tr) {
  selectedTrace.value = tr
  selectedSpanId.value = ''
  detailTab.value = 'waterfall'
  try {
    const res = await request.get(`/api/traces/${tr.trace_id}`)
    detailData.value = {
      ...res,
      root_service: res.spans?.find(s => !s.parent_span_id)?.service_name || '',
    }
  } catch (e) { console.error(e) }
}

async function openHistory() {
  showHistory.value = true
  historyDetail.value = null
  historyLoading.value = true
  try {
    historyList.value = await request.get('/ai-insight/history', { params: { source_type: 'traces', limit: 50 } })
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
  } catch (e) { /* ignore */ }
}
function closeHistory() { showHistory.value = false; historyDetail.value = null }

onMounted(() => {
  loadDomains()
  loadTraces()
})

function mdToHtml(text) {
  const esc = t => String(t)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const lines = esc(text).split('\n')
  const html = []
  for (const line of lines) {
    const m = line.match(/^(\s*)([-*]|\d+[.、)])\s+(.*)$/)
    if (m) {
      html.push(`<div class="ai-li">${m[1] ? '<span class="ai-li-indent"></span>' : ''}<span class="ai-li-mark">${m[2]}</span> ${m[3]}</div>`)
    } else if (/^#{1,4}\s/.test(line)) {
      html.push(`<div class="ai-h">${line.replace(/^#{1,4}\s*/, '')}</div>`)
    } else if (line.trim() === '') {
      html.push('')
    } else {
      html.push(`<div class="ai-p">${line}</div>`)
    }
  }
  return html.join('\n')
}

async function openAiAnalyze() {
  if (!traces.value.length) return
  aiDrawer.value = { show: true }
  aiQuestion.value = ''
  aiError.value = ''
  aiResult.value = ''
  aiResultRaw.value = ''
  aiMeta.value = `当前查询结果 ${traces.value.length} 条调用链 · 将自动裁剪 span 明细`
}

function closeAiDrawer() {
  if (aiLoading.value) return
  aiDrawer.value = { show: false }
}

async function runAiAnalyze() {
  const target = [...traces.value]
    .sort((a, b) => {
      const ea = a.worst_status === 'ERROR' ? 1 : 0
      const eb = b.worst_status === 'ERROR' ? 1 : 0
      if (ea !== eb) return eb - ea
      return (b.total_duration_ms || 0) - (a.total_duration_ms || 0)
    })
    .slice(0, 20)
  if (!target.length) return
  aiLoading.value = true
  aiError.value = ''
  aiResult.value = ''
  aiKeyPoints.value = null
  bottleneckSvc.value = []
  try {
    const enriched = []
    for (const tr of target.slice(0, 10)) {
      let spans = []
      try {
        const detail = await request.get(`/api/traces/${tr.trace_id}`)
        spans = (detail.spans || []).map(s => ({
          service_name: s.service_name, operation_name: s.operation_name,
          duration_ms: s.duration_ms, status: s.status,
        }))
      } catch (e) { /* 单条详情失败不阻塞整体分析 */ }
      enriched.push({
        trace_id: tr.trace_id, root_service: tr.root_service, root_operation: tr.root_operation,
        total_duration_ms: tr.total_duration_ms, worst_status: tr.worst_status, started_at: tr.started_at,
        spans,
      })
    }
    const res = await request.post('/ai-insight/analyze', {
      source_type: 'traces',
      traces: enriched,
      question: aiQuestion.value.trim(),
      title: `链路分析 #${Date.now().toString().slice(-6)}`,
    }, { timeout: 120000 })
    if (res.ok) {
      aiResult.value = mdToHtml(res.analysis || '')
      aiResultRaw.value = res.analysis || ''
      aiKeyPoints.value = res.key_points || null
      const m = res.meta || {}
      aiMeta.value = `分析 ${m.trace_count || enriched.length} 条调用链 · ${m.service_count || 0} 个服务 · 模型: ${res.provider || '-'} · 记录 #${res.record_id || '-'}`
      if (res.enhanced && res.enhanced.aggregation && res.enhanced.aggregation.services) {
        bottleneckSvc.value = res.enhanced.aggregation.services
      }
    } else {
      aiError.value = res.error || 'AI 分析失败'
    }
  } catch (e) {
    aiError.value = 'AI 分析请求失败：' + (e.message || e)
  } finally {
    aiLoading.value = false
  }
}

async function transferToAgent() {
  if (transferring.value || !aiResult.value) return
  transferring.value = true
  aiError.value = ''
  const top = [...traces.value]
    .sort((a, b) => (b.total_duration_ms || 0) - (a.total_duration_ms || 0))
    .slice(0, 5)
  try {
    const res = await request.post('/agent/transfer-from-analysis', {
      source_type: 'traces',
      title: `链路瓶颈转交 #${Date.now().toString().slice(-6)}`,
      analysis: aiResultRaw.value || '',
      context: {
        trace_count: traces.value.length,
        top_slow: top.map(t => `${t.root_service}/${t.root_operation} ${t.total_duration_ms}ms(${t.worst_status})`).join('; '),
        span_detail_fetched: true,
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
</script>

<style scoped>
.stats-row { display: flex; gap: 10px; margin-bottom: 10px; }
.stat-card {
  flex: 1; border-radius: 10px; padding: 12px; text-align: center;
  border: 1px solid rgba(148,163,184,0.12);
}
.stat-num { font-size: 22px; font-weight: 800; }
.stat-lbl { font-size: 10px; color: var(--text-secondary); margin-top: 2px; }
.stat-total .stat-num { color: #6366f1; }
.stat-svc .stat-num { color: #06b6d4; }
.stat-dur .stat-num { color: #f59e0b; }
.stat-err .stat-num { color: #ef4444; }

.filter-card { padding: 12px 16px; }
.filter-row { display: flex; gap: 16px; align-items: flex-end; flex-wrap: wrap; }
.filter-item { display: flex; flex-direction: column; gap: 3px; }
.filter-item label { font-size: 10px; color: var(--text-secondary); }

.trace-layout { display: flex; gap: 12px; margin-top: 10px; }
.result-card { flex: 1; padding: 0; overflow: hidden; min-width: 0; }
.detail-card { width: 500px; padding: 0; flex-shrink: 0; max-height: calc(100vh - 220px); overflow-y: auto; position: relative; }

.card-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px; border-bottom: 1px solid rgba(148,163,184,0.12);
  font-size: 13px; font-weight: 600;
}
.count-badge {
  background: var(--primary); color: #fff; font-size: 10px; padding: 1px 7px;
  border-radius: 10px; margin-left: 6px;
}
.header-hint { font-size: 11px; color: var(--text-muted); font-weight: 400; }

.detail-tabs { display: flex; gap: 4px; }
.tab-btn {
  font-size: 12px; font-weight: 500; padding: 4px 12px; border-radius: 6px;
  cursor: pointer; color: var(--text-muted); transition: all 0.15s;
}
.tab-btn:hover { background: rgba(99,102,241,0.06); }
.tab-btn.active { background: var(--primary); color: #fff; }

.trace-list { padding: 4px; max-height: calc(100vh - 340px); overflow-y: auto; }
.trace-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px; border-radius: 6px; cursor: pointer;
  transition: background 0.15s; border-bottom: 1px solid rgba(148,163,184,0.06);
}
.trace-item:hover { background: rgba(99,102,241,0.04); }
.trace-item.active { background: rgba(99,102,241,0.08); }
.trace-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.trace-service { display: flex; align-items: center; gap: 6px; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot-ok { background: #10b981; }
.dot-error { background: #ef4444; }
.svc-label { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.op-label { font-size: 11px; color: var(--text-muted); }
.trace-meta { display: flex; gap: 12px; font-size: 10px; color: var(--text-muted); align-items: center; }
.trace-id-label { font-family: monospace; font-size: 9px; background: rgba(148,163,184,0.1); padding: 1px 5px; border-radius: 3px; }
.trace-stats { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.stat-badge { font-size: 9px; font-weight: 700; padding: 1px 6px; border-radius: 4px; }
.badge-ok { background: #ecfdf5; color: #059669; }
.badge-err { background: #fef2f2; color: #dc2626; }
.dur-bar-wrap { width: 60px; height: 4px; background: #f1f5f9; border-radius: 2px; overflow: hidden; }
.dur-bar { height: 100%; border-radius: 2px; transition: width 0.3s; }
.dur-text { font-size: 11px; color: var(--text-secondary); min-width: 40px; text-align: right; }
.empty-trace { text-align: center; padding: 40px; color: var(--text-muted); }
.empty-detail {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  height: 300px; color: var(--text-muted);
}
.empty-icon { font-size: 32px; margin-bottom: 8px; }
.empty-text { font-size: 13px; }

.detail-summary {
  display: flex; gap: 8px; padding: 10px 14px; flex-wrap: wrap;
  border-bottom: 1px solid rgba(148,163,184,0.08);
}
.chip {
  font-size: 11px; background: rgba(99,102,241,0.06); padding: 3px 10px;
  border-radius: 6px; color: var(--text-secondary);
}
.chip strong { color: var(--text-primary); }

.waterfall-header {
  display: grid; grid-template-columns: 1fr auto 50px;
  padding: 6px 12px; font-size: 10px; color: var(--text-muted);
  border-bottom: 1px solid rgba(148,163,184,0.08);
}
.wf-scale { margin-left: 4px; color: var(--text-muted); font-weight: 500; }
.waterfall-body { padding: 0; max-height: 400px; overflow-y: auto; }
.wf-row {
  display: grid; grid-template-columns: 1fr 200px 50px;
  padding: 3px 12px; border-bottom: 1px solid rgba(148,163,184,0.04);
  align-items: center; cursor: pointer; transition: background 0.1s;
}
.wf-row:hover { background: rgba(99,102,241,0.04); }
.wf-row.wf-selected { background: rgba(99,102,241,0.06); }
.wf-row.wf-child .wf-svc { padding-left: 0; }
.wf-svc { display: flex; align-items: center; gap: 4px; overflow: hidden; }
.wf-depth { width: 16px; flex-shrink: 0; }
.wf-svc-name { font-size: 11px; font-weight: 600; white-space: nowrap; flex-shrink: 0; }
.wf-op-name { font-size: 10px; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wf-timeline { position: relative; height: 18px; }
.wf-bar { cursor: pointer; }
.wf-bar:hover { filter: brightness(1.2); }
.wf-dur { font-size: 10px; color: var(--text-secondary); text-align: right; }
.wf-error { font-size: 9px; background: #fef2f2; color: #ef4444; padding: 0 5px; border-radius: 3px; }

.waterfall-colors {
  display: flex; gap: 8px; padding: 8px 12px; flex-wrap: wrap;
  border-top: 1px solid rgba(148,163,184,0.08);
}
.color-chip { display: flex; align-items: center; gap: 4px; font-size: 10px; color: var(--text-muted); }
.color-dot { width: 8px; height: 8px; border-radius: 2px; }

.topology-view { padding: 20px; min-height: 300px; display: flex; align-items: center; justify-content: center; }
.topo-svg { width: 100%; max-width: 460px; height: 360px; }

.span-detail-view { padding: 12px 14px; }
.span-meta { display: flex; flex-direction: column; gap: 6px; }
.span-meta-row { display: flex; align-items: center; gap: 12px; padding: 4px 0; border-bottom: 1px solid rgba(148,163,184,0.06); }
.meta-key { font-size: 11px; color: var(--text-muted); min-width: 70px; }
.meta-val { font-size: 12px; color: var(--text-primary); font-weight: 500; }
.span-tags { margin-top: 16px; }
.tags-title { font-size: 12px; font-weight: 600; margin-bottom: 8px; color: var(--text-primary); }
.tag-row { display: flex; gap: 12px; padding: 4px 0; font-size: 11px; border-bottom: 1px solid rgba(148,163,184,0.04); }
.tag-key { color: #6366f1; font-weight: 500; min-width: 100px; }
.tag-val { color: var(--text-primary); word-break: break-all; }

.btn-ai {
  padding: 6px 14px; border-radius: 6px; border: none;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff; font-size: 12px; font-weight: 600; cursor: pointer; font-family: inherit;
}
.btn-ai:disabled { opacity: 0.5; cursor: not-allowed; }
.bottleneck-panel {
  background: #f5f3ff; border: 1px solid #ddd6fe; border-radius: 8px;
  padding: 12px; margin-bottom: 12px;
}
.bn-head { font-size: 13px; font-weight: 700; color: #5b21b6; margin-bottom: 10px; }
.bn-row { display: flex; gap: 8px; align-items: center; padding: 4px 0; font-size: 12px; }
.bn-rank { font-size: 10px; font-weight: 700; color: #8b5cf6; width: 20px; }
.bn-svc { font-weight: 600; color: #1e293b; min-width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bn-p90 { color: #64748b; font-size: 11px; min-width: 70px; }
.bn-err { font-size: 11px; color: #059669; min-width: 70px; }
.bn-err-high { color: #dc2626; }
.bn-bar-wrap { flex: 1; height: 4px; background: rgba(139,92,246,0.1); border-radius: 2px; overflow: hidden; }
.bn-bar { height: 100%; background: linear-gradient(90deg, #8b5cf6, #6366f1); border-radius: 2px; }
.modal-overlay {
  position: fixed; inset: 0; z-index: 2000; background: rgba(0,0,0,0.45);
  display: flex; align-items: center; justify-content: center; padding: 20px;
}
.modal-box { background: #fff; border-radius: 12px; padding: 18px 20px; width: 560px; max-width: 92vw; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
.modal-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.hi-item { padding: 10px 12px; border-bottom: 1px solid rgba(148,163,184,0.1); cursor: pointer; transition: background 0.15s; position: relative; }
.hi-item:hover { background: rgba(99,102,241,0.04); }
.hi-title { font-size: 13px; font-weight: 600; color: #1e293b; }
.hi-meta { font-size: 11px; color: #94a3b8; margin: 2px 0; }
.hi-preview { font-size: 12px; color: #64748b; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hi-del { position: absolute; top: 10px; right: 10px; font-size: 11px; color: #ef4444; background: none; border: 1px solid rgba(239,68,68,0.2); border-radius: 4px; padding: 2px 8px; cursor: pointer; }
.history-detail { padding: 8px 0; }
.hi-content { font-size: 13px; line-height: 1.7; color: #1e293b; }

.ai-drawer-mask {
  position: fixed; inset: 0; z-index: 2000;
  background: rgba(0,0,0,0.45);
  display: flex; justify-content: flex-end;
}
.ai-drawer {
  width: 460px; max-width: 92vw; height: 100%;
  background: #fff; display: flex; flex-direction: column;
  box-shadow: -4px 0 24px rgba(0,0,0,0.15);
  animation: aiSlideIn 0.25s ease;
}
@keyframes aiSlideIn { from { transform: translateX(60px); opacity: 0 } to { transform: translateX(0); opacity: 1 } }
.ai-drawer-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid #ebeef5;
}
.ai-drawer-title { font-size: 16px; font-weight: 700; color: #303133; }
.ai-drawer-meta { font-size: 12px; color: #909399; margin-top: 4px; }
.ai-drawer-close { border: none; background: none; font-size: 22px; color: #909399; cursor: pointer; line-height: 1; }
.ai-drawer-body { flex: 1; overflow-y: auto; padding: 16px 20px; }
.ai-trace-note {
  background: #f5f3ff; color: #5b21b6; border: 1px solid #ddd6fe;
  border-radius: 6px; padding: 10px 12px; font-size: 12px; line-height: 1.6; margin-bottom: 12px;
}
.ai-question-row { display: flex; gap: 8px; margin-bottom: 12px; }
.ai-question-input {
  flex: 1; padding: 8px 12px; border-radius: 8px;
  border: 1px solid rgba(148,163,184,0.3); font-size: 13px; font-family: inherit;
}
.ai-error-bar {
  background: #fef0f0; color: #f56c6c; border: 1px solid #fbc4c4;
  border-radius: 6px; padding: 10px 12px; font-size: 13px; margin-bottom: 10px;
}
.ai-loading { display: flex; align-items: center; gap: 10px; color: #909399; font-size: 13px; padding: 24px 0; }
.ai-spinner {
  width: 18px; height: 18px; border: 2px solid #e0e7ff; border-top-color: #6366f1;
  border-radius: 50%; animation: aiSpin 0.8s linear infinite;
}
@keyframes aiSpin { to { transform: rotate(360deg) } }
.ai-result { font-size: 13px; line-height: 1.8; color: #303133; }
.ai-result .ai-h { font-weight: 700; color: #4f46e5; margin: 12px 0 6px; font-size: 14px; }
.ai-result .ai-p { margin: 4px 0; }
.ai-result .ai-li { margin: 3px 0; }
.ai-result .ai-li-mark { color: #6366f1; font-weight: 600; }
.ai-empty { color: #909399; font-size: 13px; text-align: center; padding: 40px 0; }
.ai-transfer-bar {
  display: flex; align-items: center; gap: 10px; margin-top: 14px;
  padding-top: 14px; border-top: 1px dashed rgba(148,163,184,0.3);
}
.btn-transfer {
  padding: 7px 16px; border-radius: 6px; border: none; cursor: pointer;
  background: linear-gradient(135deg, #0ea5e9, #6366f1);
  color: #fff; font-size: 13px; font-weight: 600; font-family: inherit;
}
.btn-transfer:disabled { opacity: 0.5; cursor: not-allowed; }
.ai-transfer-tip { font-size: 11px; color: #909399; }
</style>
