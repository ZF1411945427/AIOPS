<template>
  <div class="workbench-page-shell">
    <div class="section-toolbar">
      <div class="toolbar-head">
        <span class="toolbar-title">链路追踪</span>
        <span class="toolbar-desc">分布式调用链查询与可视化</span>
      </div>
      <div class="workbench-card-actions">
        <button class="btn btn-guide" @click="showGuide = !showGuide">📖 操作说明</button>
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
                <span class="trace-time">{{ tr.start_time }}</span>
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
              <div class="span-meta-row"><span class="meta-key">开始时间</span><span class="meta-val">{{ selectedSpan.start_time }}</span></div>
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
const selectedTrace = ref(null)
const selectedSpanId = ref('')
const detailData = ref({ spans: [], services: [], root_duration_ms: 0, topology: { services: [], edges: [] } })
const detailTab = ref('waterfall')
const wfBody = ref(null)
const topoSvg = ref(null)
const listRef = ref(null)

const filters = reactive({
  service: '', keyword: '', status: '', min_dur: 0, limit: 50,
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
  if (!rootSpan || !rootSpan.start_time) return { width: '4px', left: '0%' }
  const rootStart = new Date(rootSpan.start_time).getTime()
  const spanStart = new Date(span.start_time).getTime()
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

onMounted(loadTraces)
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
</style>
