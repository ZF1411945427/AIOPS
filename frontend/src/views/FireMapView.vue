<template>
  <div class="firemap">
    <!-- ====== Domain Overview ====== -->
    <template v-if="mode === 'overview'">
      <div class="fm-header">
        <div class="fm-title-row">
          <div class="fm-title-icon">
            <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
          </div>
          <div>
            <h1 class="fm-title">架构巡检图</h1>
            <span class="fm-subtitle">全域 Entity 健康驾驶舱</span>
          </div>
        </div>
        <div class="fm-stats">
          <div class="fm-stat-card total">
            <div class="stat-value">{{ allStats.total }}</div>
            <div class="stat-label">总计</div>
          </div>
          <div class="fm-stat-card healthy">
            <div class="stat-value">{{ allStats.healthy }}</div>
            <div class="stat-label">健康</div>
          </div>
          <div class="fm-stat-card fault">
            <div class="stat-value">{{ allStats.fault }}</div>
            <div class="stat-label">故障</div>
          </div>
          <div class="fm-stat-card offline">
            <div class="stat-value">{{ allStats.offline }}</div>
            <div class="stat-label">离线</div>
          </div>
        </div>
      </div>

      <!-- Search bar -->
      <div class="fm-search-bar">
        <svg class="search-icon" viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="8.5" cy="8.5" r="5.5"/><path d="M12.5 12.5L17 17"/>
        </svg>
        <input v-model="domainQuery" class="search-input" placeholder="搜索业务域..." @input="filterDomains" />
      </div>

      <!-- Domain cards grid -->
      <div class="fm-domain-grid">
        <div
          v-for="d in filteredDomains"
          :key="d.name"
          class="fm-domain-card"
          :class="{ 'has-fault': d.fault > 0 }"
          @click="enterDomain(d)"
        >
          <div class="domain-card-top">
            <div class="domain-name">{{ d.name }}</div>
            <div class="domain-count">{{ d.total }} 实体</div>
          </div>
          <div class="domain-stats-row">
            <div class="domain-stat healthy">
              <span class="ds-value">{{ d.healthy }}</span>
              <span class="ds-label">健康</span>
            </div>
            <div class="domain-stat fault">
              <span class="ds-value">{{ d.fault }}</span>
              <span class="ds-label">故障</span>
            </div>
            <div class="domain-stat offline">
              <span class="ds-value">{{ d.offline }}</span>
              <span class="ds-label">离线</span>
            </div>
          </div>
          <div class="domain-bar">
            <div class="bar-segment healthy" :style="{ flex: d.healthy }"></div>
            <div class="bar-segment fault" :style="{ flex: d.fault || 0.01 }"></div>
            <div class="bar-segment offline" :style="{ flex: d.offline || 0.01 }"></div>
          </div>
          <div v-if="d.fault > 0" class="domain-alert-banner">{{ d.fault }} 个实体故障中</div>
        </div>
        <div v-if="!filteredDomains.length" class="domain-empty">无匹配业务域</div>
      </div>
    </template>

    <!-- ====== Domain Detail ====== -->
    <template v-else-if="mode === 'domain'">
      <div class="fm-domain-header">
        <button class="fm-back-btn" @click="exitDomain">
          <svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 4L6 10l6 6"/>
          </svg>
          返回业务域总览
        </button>
        <div class="domain-context">
          <span class="domain-context-name">{{ currentDomain.name }}</span>
          <span class="domain-context-meta">{{ currentDomain.total }} 实体 · {{ currentDomain.fault }} 故障 · {{ currentDomain.offline }} 离线</span>
        </div>
      </div>

      <div class="fm-header">
        <div class="fm-title-row">
          <div class="fm-title-icon">
            <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
          </div>
          <div>
            <h1 class="fm-title">{{ currentDomain.name }}</h1>
            <span class="fm-subtitle">架构巡检图 · 实体分层视图</span>
          </div>
        </div>
        <div class="fm-stats">
          <div class="fm-stat-card total">
            <div class="stat-value">{{ stats.total }}</div>
            <div class="stat-label">总计</div>
          </div>
          <div class="fm-stat-card healthy">
            <div class="stat-value">{{ stats.green }}</div>
            <div class="stat-label">健康</div>
          </div>
          <div class="fm-stat-card fault">
            <div class="stat-value">{{ stats.red }}</div>
            <div class="stat-label">故障</div>
          </div>
          <div class="fm-stat-card offline">
            <div class="stat-value">{{ stats.gray }}</div>
            <div class="stat-label">离线</div>
          </div>
        </div>
        <button class="fm-arch-btn" @click="openArchDialog" title="生成该业务域的系统架构图">
          <svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M9 3h2v4H9zM9 13h2v4H9zM3 9h4v2H3zM13 9h4v2h-4z"/>
            <path d="M5 5l2 2M15 5l-2 2M5 15l2-2M15 15l-2-2"/>
          </svg>
          生成架构图
        </button>
      </div>

      <!-- Search bar -->
      <div class="fm-search-bar">
        <svg class="search-icon" viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="8.5" cy="8.5" r="5.5"/><path d="M12.5 12.5L17 17"/>
        </svg>
        <span class="fm-search-label">业务域</span>
        <el-select v-model="currentDomain.name" size="small" style="width:180px" @change="onDomainSwitch">
          <el-option v-for="d in allDomains" :key="d.name" :value="d.name" :label="d.name" />
        </el-select>
        <span class="fm-search-divider"></span>
        <svg class="search-icon" viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="8.5" cy="8.5" r="5.5"/><path d="M12.5 12.5L17 17"/>
        </svg>
        <input v-model="entityQuery" class="search-input" placeholder="搜索实体名称 / ci_type..." />
      </div>

      <!-- ====== 架构拓扑(分层卡片 + 调用连线) ====== -->
      <div class="arch-topo-wrap">
        <div class="arch-topo-head">
          <span class="arch-topo-icon">🗺️</span>
          <span class="arch-topo-title">架构拓扑</span>
          <span class="arch-topo-sub">分层实体 · 调用连线 · 自动排版</span>
        </div>
        <div ref="archChartRef" class="arch-topo-chart"></div>
        <div class="arch-topo-legend">
          <span class="lg-label">健康:</span>
          <span class="lg-dot" style="background:#67C23A"></span>健康
          <span class="lg-dot" style="background:#E6A23C"></span>警告
          <span class="lg-dot" style="background:#ef4444"></span>严重
          <span class="lg-dot" style="background:#94a3b8"></span>离线
          <span class="lg-note">卡片边框/圆点=健康状态</span>
          <span class="lg-label" style="margin-left:16px">调用:</span>
          <span class="lg-line" style="background:#94a3b8"></span>低错误
          <span class="lg-line" style="background:#E6A23C"></span>警告
          <span class="lg-line" style="background:#ef4444"></span>严重
        </div>
      </div>
    </template>

<!-- 生成架构图配置弹窗 -->
    <el-dialog v-model="archDialogVisible" title="生成系统架构图" width="520px" class="fm-arch-dialog">
      <div class="arch-dialog-body">
        <div class="arch-dialog-tip">根据当前业务域 <b>{{ currentDomain.name }}</b> 的资产与依赖关系，自动生成 draw.io 架构图（分层 + 父子归属 + 依赖连线）。</div>
        <div v-if="archMeta" class="arch-dialog-meta">
          <span>资产 {{ archMeta.asset_count }} 个</span>
          <span class="sep">|</span>
          <span>关系 {{ archMeta.relation_count }} 条</span>
          <span class="sep">|</span>
          <span>{{ archMeta.message }}</span>
        </div>
        <div class="arch-field">
          <label>导出格式</label>
          <el-select v-model="archFormat" style="width:100%">
            <el-option value="drawio" label=".drawio（可编辑源文件）" />
            <el-option value="png" label="PNG 图片" />
            <el-option value="svg" label="SVG 矢量图" />
            <el-option value="pdf" label="PDF 文档" />
          </el-select>
        </div>
        <div class="arch-field">
          <label class="arch-ai-toggle">
            <el-switch v-model="archAiLayout" size="small" />
            <span>AI 智能布局</span>
            <span class="arch-ai-badge">NEW</span>
          </label>
          <div class="arch-field-hint">AI 分析资产关系后优化节点排序，减少连线交叉。需 AI provider 在线。</div>
        </div>
        <div class="arch-field">
          <label>draw.io 本地安装路径</label>
          <el-input v-model="archDrawioPath" placeholder="如 D:\Apps\draw.io\draw.io.exe">
            <template #append>
              <el-button @click="browseDrawioPath">浏览</el-button>
            </template>
          </el-input>
          <div class="arch-field-hint">实时绘制、导出 PNG/SVG/PDF 都需要此路径。未填则仅生成 .drawio 文件。</div>
          <input ref="drawioFileInput" type="file" accept=".exe,.cmd,.bat" style="display:none" @change="onDrawioFilePick" />
        </div>
        <div class="arch-field">
          <label class="arch-ai-toggle">
            <el-switch v-model="archLiveDraw" size="small" :disabled="!archDrawioPath" />
            <span>实时绘制到 draw.io</span>
            <span class="arch-live-badge">LIVE</span>
          </label>
          <div class="arch-field-hint">启动 draw.io 桌面版，AI 逐步绘制节点和连线，您可实时观看绘制过程。</div>
        </div>
        <div v-if="archResult" class="arch-result" :class="{ error: !archResult.ok }">
          <template v-if="archResult.ok && archResult.drawio_download">
            <a :href="archResult.drawio_download" target="_blank" class="arch-dl">下载 .drawio</a>
            <a v-if="archResult.export_download" :href="archResult.export_download" target="_blank" class="arch-dl">下载导出文件</a>
          </template>
          <span>{{ archResult.message }} {{ archResult.export_message || '' }}</span>
          <div v-if="archResult.ai_analysis" class="arch-ai-result">
            <span class="arch-ai-label">AI 分析:</span> {{ archResult.ai_analysis }}
            <span v-if="archResult.ai_suggestions" class="arch-ai-sug">· {{ archResult.ai_suggestions }}</span>
          </div>
          <div v-if="archResult.ai_error" class="arch-ai-error">{{ archResult.ai_error }}</div>
        </div>
      </div>
      <template #footer>
        <el-button @click="archDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="archGenerating" @click="doGenerateArch">生成架构图</el-button>
      </template>
    </el-dialog>

    <!-- Entity detail drawer -->
    <el-drawer
      v-model="drawerVisible"
      :title="drawerEntity?.name || '实体详情'"
      size="420px"
      class="fm-drawer"
    >
      <template #header>
        <div class="drawer-header">
          <div class="drawer-status-icon" :class="`status-${drawerEntity?.health_status}`">
            <svg viewBox="0 0 16 16" width="14" height="14">
              <circle cx="8" cy="8" r="5" fill="currentColor"/>
            </svg>
          </div>
          <div>
            <div class="drawer-title">{{ drawerEntity?.name }}</div>
            <div class="drawer-ci-type">{{ drawerEntity?.ci_type }}</div>
          </div>
        </div>
      </template>
      <div v-if="drawerLoading" class="drawer-loading">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
      </div>
      <div v-else-if="drawerError" class="drawer-error">{{ drawerError }}</div>
      <div v-else class="drawer-body">
        <div class="detail-section">
          <h3 class="section-title">基础信息</h3>
          <div class="detail-grid">
            <div class="detail-item">
              <span class="detail-label">IP 地址</span>
              <span class="detail-value">{{ detail?.ip || '-' }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">运行状态</span>
              <span class="detail-value">
                <span class="status-tag" :class="detail?.status">{{ detail?.status || '-' }}</span>
              </span>
            </div>
            <div class="detail-item">
              <span class="detail-label">最后检测</span>
              <span class="detail-value">{{ detail?.last_checked_at ? formatTime(detail.last_checked_at) : '-' }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">延迟</span>
              <span class="detail-value">{{ detail?.latency_ms != null ? detail.latency_ms + 'ms' : '-' }}</span>
            </div>
          </div>
        </div>

        <div v-if="detail?.layer === 'api' && detail?.trace_info" class="detail-section">
          <h3 class="section-title">链路指标</h3>
          <div class="trace-info-grid">
            <div class="trace-metric">
              <div class="trace-metric-label">错误率</div>
              <div class="trace-metric-value" :class="{ 'is-danger': detail.trace_info.error_rate > (detail.trace_info.thresholds?.error_rate || 5) }">
                {{ detail.trace_info.error_rate }}%
              </div>
              <div class="trace-metric-threshold">阈值: {{ detail.trace_info.thresholds?.error_rate || 5 }}%</div>
            </div>
            <div class="trace-metric">
              <div class="trace-metric-label">P99 延迟</div>
              <div class="trace-metric-value" :class="{ 'is-danger': detail.trace_info.p99_ms > (detail.trace_info.thresholds?.latency_ms || 1000) }">
                {{ detail.trace_info.p99_ms }}ms
              </div>
              <div class="trace-metric-threshold">阈值: {{ detail.trace_info.thresholds?.latency_ms || 1000 }}ms</div>
            </div>
            <div class="trace-metric">
              <div class="trace-metric-label">平均延迟</div>
              <div class="trace-metric-value">{{ detail.trace_info.avg_latency_ms }}ms</div>
            </div>
            <div class="trace-metric">
              <div class="trace-metric-label">Span 数</div>
              <div class="trace-metric-value">{{ detail.trace_info.total_spans }}</div>
            </div>
          </div>
          <div v-if="detail.trace_info.matched_services?.length" class="trace-services">
            <span class="trace-services-label">关联服务:</span>
            <span v-for="s in detail.trace_info.matched_services" :key="s" class="trace-service-tag">{{ s }}</span>
          </div>
        </div>

        <div v-if="detail?.layer === 'infra' && detail?.infra_metrics" class="detail-section">
          <h3 class="section-title">基础设施指标</h3>
          <div v-if="!Object.keys(detail.infra_metrics.latest || {}).length" class="section-empty">暂无指标数据</div>
          <div v-for="(info, name) in (detail.infra_metrics.latest || {})" :key="name" class="infra-metric-bar">
            <div class="infra-metric-header">
              <span class="infra-metric-name">{{ name }}</span>
              <span class="infra-metric-value" :class="{ 'is-danger': info.value > ((detail.infra_metrics.thresholds || {})[name]?.threshold || 100) }">
                {{ info.value }}{{ info.unit || '%' }}
              </span>
            </div>
            <div class="infra-metric-track">
              <div
                class="infra-metric-fill"
                :class="{ 'is-danger': info.value > ((detail.infra_metrics.thresholds || {})[name]?.threshold || 100) }"
                :style="{ width: Math.min(info.value, 100) + '%' }"
              ></div>
              <div
                v-if="detail.infra_metrics.thresholds?.[name]"
                class="infra-metric-threshold-line"
                :style="{ left: detail.infra_metrics.thresholds[name].threshold + '%' }"
              ></div>
            </div>
            <div class="infra-metric-threshold-label">
              阈值: {{ detail.infra_metrics.thresholds[name].threshold }}{{ info.unit || '%' }}
            </div>
          </div>
        </div>

        <div v-if="detail?.parent" class="detail-section">
          <h3 class="section-title">父级实体</h3>
          <div class="entity-node mini" :class="`status-${detail.parent.health_status || 'green'}`" @click="openDetail(detail.parent)">
            <div class="entity-status-dot">
              <svg viewBox="0 0 16 16" width="14" height="14"><circle cx="8" cy="8" r="5" fill="currentColor"/></svg>
            </div>
            <div class="entity-info">
              <div class="entity-name">{{ detail.parent.name }}</div>
              <div class="entity-meta">{{ detail.parent.ci_type }}</div>
            </div>
          </div>
        </div>

        <div v-if="detail?.children?.length" class="detail-section">
          <h3 class="section-title">子级实体 ({{ detail.children.length }})</h3>
          <div v-for="c in detail.children" :key="c.id" class="entity-node mini" :class="`status-${c.health_status || 'green'}`" @click="openDetail(c)">
            <div class="entity-status-dot">
              <svg viewBox="0 0 16 16" width="14" height="14"><circle cx="8" cy="8" r="5" fill="currentColor"/></svg>
            </div>
            <div class="entity-info">
              <div class="entity-name">{{ c.name }}</div>
              <div class="entity-meta">{{ c.ci_type }}</div>
            </div>
          </div>
        </div>

        <div class="detail-section">
          <h3 class="section-title">活跃告警 ({{ detail?.alerts?.length || 0 }})</h3>
          <div v-if="!detail?.alerts?.length" class="section-empty">暂无活跃告警</div>
          <div v-for="a in (detail?.alerts || [])" :key="a.id" class="alert-item" :class="a.severity">
            <div class="alert-header">
              <span class="alert-severity-tag" :class="a.severity">{{ a.severity }}</span>
              <span class="alert-status-tag" :class="a.status">{{ a.status }}</span>
            </div>
            <div class="alert-message">{{ a.message || a.metric_name }}</div>
            <div class="alert-meta">
              <span>{{ a.metric_name }}</span>
              <span>实际: {{ a.actual_value }} / 阈值: {{ a.threshold }}</span>
              <span>{{ formatTime(a.created_at) }}</span>
            </div>
          </div>
        </div>

        <div class="detail-section">
          <h3 class="section-title">最近指标 ({{ detail?.metrics?.length || 0 }})</h3>
          <div v-if="!detail?.metrics?.length" class="section-empty">暂无指标数据</div>
          <div v-for="m in (detail?.metrics || [])" :key="m.name + m.timestamp" class="metric-item">
            <div class="metric-primary">
              <span class="metric-name">{{ m.name }}</span>
              <span class="metric-value">{{ m.value }}<span class="metric-unit">{{ m.unit }}</span></span>
            </div>
            <div class="metric-time">{{ formatTime(m.timestamp) }}</div>
          </div>
        </div>
      </div>
    </el-drawer>

    <!-- Refresh button -->
    <button class="fm-refresh" @click="refreshAll" title="刷新">
      <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" :class="{ spinning: refreshing }">
        <path d="M14.5 3.5A7.5 7.5 0 0117 10a7.5 7.5 0 01-7.5 7.5M5.5 16.5A7.5 7.5 0 013 10a7.5 7.5 0 017.5-7.5"/>
        <path d="M14.5 7.5V3.5h4M5.5 12.5v4h-4"/>
      </svg>
    </button>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import request from '@/api/request'
import { Loading } from '@element-plus/icons-vue'

const SHOW_LIMIT = 30

const mode = ref('overview') // 'overview' | 'domain'

const allDomains = ref([])
const domainQuery = ref('')
const filteredDomains = ref([])

const currentDomain = ref({ name: '', total: 0, fault: 0, offline: 0, healthy: 0 })

const stats = ref({ total: 0, green: 0, gray: 0, red: 0 })
const layers = ref([])
const entityQuery = ref('')
const expandedLayers = reactive(new Set())

const allStats = computed(() => {
  let total = 0, healthy = 0, fault = 0, offline = 0
  for (const d of allDomains.value) {
    total += d.total; healthy += d.healthy; fault += d.fault; offline += d.offline
  }
  return { total, healthy, fault, offline }
})

const refreshing = ref(false)

const drawerVisible = ref(false)
const drawerEntity = ref(null)
const drawerLoading = ref(false)
const drawerError = ref('')
const detail = ref(null)

// ====== 生成架构图对话框 ======
const archDialogVisible = ref(false)
const archGenerating = ref(false)
const archFormat = ref('drawio')
const archDrawioPath = ref('')
const archMeta = ref(null)
const archResult = ref(null)
const archAiLayout = ref(true)  // AI 智能布局开关(默认开启)
const archLiveDraw = ref(false)  // 实时绘制到 draw.io 桌面版
const drawioFileInput = ref(null)  // 文件选择器 ref

// ====== 架构拓扑(ECharts 分层卡片 + 调用连线) ======
const svcNodes = ref([])
const svcEdges = ref([])
const archChartRef = ref(null)
let archChart = null

async function loadServiceCalls() {
  try {
    const data = await request.get('/topology/api/service-calls', { params: { hours: 168, min_calls: 1 } })
    svcNodes.value = data.nodes || []
    svcEdges.value = data.edges || []
  } catch (e) {
    // silent
  }
}

function _edgeColor(er) {
  if (er >= 30) return '#ef4444'
  if (er >= 5) return '#E6A23C'
  return '#94a3b8'
}

function _healthColor(hs) {
  const h = (hs || '').toLowerCase()
  if (h === 'red' || h === 'critical') return '#ef4444'
  if (h === 'warning' || h === 'warn') return '#E6A23C'
  if (h === 'gray' || h === 'offline' || h === 'offline' || h === 'down') return '#94a3b8'
  return '#67C23A'
}

function _nameMatch(name) {
  return (name || '').replace(/-\d+$/, '').toLowerCase()
}

function renderDomainGraph() {
  if (!archChartRef.value || !layers.value.length) return
  if (archChart) { archChart.dispose(); archChart = null }
  archChart = echarts.init(archChartRef.value, null, { renderer: 'canvas', devicePixelRatio: 2 })

  const allEntities = []
  for (const layer of layers.value) {
    for (const e of layer.entities) {
      allEntities.push({ ...e, layerKey: layer.key, layerName: layer.name })
    }
  }

  const LAYER_STYLE = {
    '1': { bg: '#eef2ff', border: '#6366f1', label: '接入层', textColor: '#4338ca' },
    svc: { bg: '#e0f2fe', border: '#0284c7', label: '服务调用层', textColor: '#075985' },
    '2': { bg: '#f0fdf4', border: '#22c55e', label: '应用层', textColor: '#15803d' },
    '3-db': { bg: '#fff7ed', border: '#f97316', label: '数据库', textColor: '#c2410c' },
    '3-mq': { bg: '#ecfeff', border: '#06b6d4', label: '中间件', textColor: '#0e7490' },
    '4': { bg: '#f8fafc', border: '#64748b', label: '基础设施', textColor: '#475569' },
  }

  const chartW = archChartRef.value.clientWidth || 800
  const CARD_W = 160
  const CARD_H = 46
  const GAP_X = 28
  const ROW_H = 62

  const LAYER_ORDER = ['1', 'svc', '2', '3-db', '3-mq', '4']

  const nameToId = {}
  for (const e of allEntities) {
    nameToId[_nameMatch(e.name)] = e.id
    try {
      const attrs = typeof e.ci_attributes === 'string' ? JSON.parse(e.ci_attributes || '{}') : (e.ci_attributes || {})
      if (attrs.service) nameToId[_nameMatch(attrs.service)] = e.id
    } catch (e2) {}
  }

  const svcEntities = []
  for (const sn of svcNodes.value) {
    const mid = _nameMatch(sn.name)
    if (nameToId[mid]) continue
    svcEntities.push({
      id: 'svc-' + svcEntities.length,
      name: sn.name,
      ci_type: sn.service_type || 'service',
      health_status: sn.health_status || 'green',
      alert_count: 0,
      layerKey: 'svc',
      layerName: '服务调用层',
    })
  }

  for (const sn of svcEntities) {
    nameToId[_nameMatch(sn.name)] = sn.id
  }

  const finalEntities = allEntities.length > 0
    ? [...allEntities, ...svcEntities]
    : svcEntities

  const perRow = Math.max(1, Math.floor((chartW - 40) / (CARD_W + GAP_X)))
  const layerGroups = LAYER_ORDER.map(key => ({
    key,
    items: finalEntities.filter(e => e.layerKey === key),
  })).filter(g => g.items.length > 0)

  const rowsByKey = {}
  for (const g of layerGroups) {
    rowsByKey[g.key] = Math.ceil(g.items.length / perRow)
  }

  let yCursor = 30
  const layerYMap = {}
  for (const g of layerGroups) {
    layerYMap[g.key] = yCursor
    yCursor += rowsByKey[g.key] * ROW_H + 40
  }

  const layerXMap = {}
  for (const g of layerGroups) {
    const items = g.items
    const n = items.length
    const rows = rowsByKey[g.key]
    const rowStartY = layerYMap[g.key]
    items.forEach((e, i) => {
      const row = Math.floor(i / perRow)
      const inRow = n - row * perRow < perRow && row === rows - 1
        ? n - row * perRow
        : perRow
      const idxInRow = i % perRow
      const rowW = (inRow - 1) * (CARD_W + GAP_X)
      const x = (chartW - rowW) / 2 + idxInRow * (CARD_W + GAP_X)
      layerXMap[e.id] = { x, y: rowStartY + row * ROW_H + ROW_H * 0.35 }
    })
  }

  function _truncate(s, max) {
    return s && s.length > max ? s.slice(0, max - 1) + '…' : s
  }

  for (const sn of svcEntities) {
    nameToId[_nameMatch(sn.name)] = sn.id
  }

  const graphNodes = finalEntities.map(e => {
    const pos = layerXMap[e.id] || { x: chartW / 2, y: 100 }
    const style = LAYER_STYLE[e.layerKey] || LAYER_STYLE['4']
    const healthC = _healthColor(e.health_status)
    return {
      id: String(e.id),
      name: e.name,
      x: pos.x, y: pos.y,
      symbol: 'roundRect',
      symbolSize: [CARD_W, CARD_H],
      itemStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: '#ffffff' },
          { offset: 1, color: style.bg },
        ]),
        borderColor: healthC,
        borderWidth: 2,
        borderRadius: 10,
        shadowBlur: 6,
        shadowOffsetY: 2,
        shadowColor: 'rgba(15,23,42,0.10)',
      },
      label: {
        show: true, position: 'inside',
        formatter: `{dot|●} {name|${_truncate(e.name, 13)}}\n{type|${_truncate(e.ci_type || '', 14)}}`,
        rich: {
          dot: {
            fontSize: 10, color: healthC, width: 14, height: 16,
            align: 'left', verticalAlign: 'middle', padding: [0, 0, 0, 2],
          },
          name: { fontSize: 11, fontWeight: 700, color: '#1e293b', lineHeight: 17, width: 118, overflow: 'truncate' },
          type: { fontSize: 9, color: '#64748b', lineHeight: 13, width: 118, overflow: 'truncate', padding: [0, 0, 0, 16] },
        },
      },
      raw: e,
    }
  })

  const graphEdges = []
  const seen = new Set()
  for (const edge of svcEdges.value) {
    const srcId = nameToId[_nameMatch(edge.source)]
    const tgtId = nameToId[_nameMatch(edge.target)]
    if (!srcId || !tgtId) continue
    const key = `${srcId}-${tgtId}`
    if (seen.has(key)) continue
    seen.add(key)
    graphEdges.push({
      source: String(srcId), target: String(tgtId),
      lineStyle: { color: _edgeColor(edge.error_rate || 0), width: 2, curveness: 0.25, opacity: 0.85 },
      label: { show: edge.call_count > 3, formatter: `{c|${edge.call_count}次}`, rich: { c: { fontSize: 9, color: '#64748b', padding: [1, 4] } } },
      raw: edge,
    })
  }

  archChart.setOption({
    tooltip: {
      formatter: (p) => {
        if (p.dataType === 'node') {
          const e = p.data.raw
          let html = `<b>${e.name}</b><br/>类型: ${e.ci_type || '-'}<br/>状态: ${e.health_status || '-'}<br/>层: ${e.layerName || '-'}`
          if (e.alert_count) html += `<br/>告警: ${e.alert_count}`
          return html
        }
        if (p.dataType === 'edge') {
          const e = p.data.raw || {}
          const errRate = (e.error_rate != null ? e.error_rate : 0) + '%'
          const avgMs = e.avg_duration_ms != null ? e.avg_duration_ms + 'ms' : '-'
          return `<b>${e.source || p.data.source} → ${e.target || p.data.target}</b><br/>调用 ${e.call_count ?? 0} 次 · 错误 ${e.error_count ?? 0} 次<br/>错误率 ${errRate} · 平均 ${avgMs}`
        }
        return ''
      },
    },
    series: [{
      type: 'graph', layout: 'none',
      roam: true, draggable: true,
      data: graphNodes, links: graphEdges,
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: [0, 10],
      edgeLabel: { fontSize: 9, color: '#64748b' },
      emphasis: { focus: 'adjacency', lineStyle: { width: 3 } },
      lineStyle: { color: '#94a3b8' },
    }],
  }, true)

  archChart.off('click')
  archChart.on('click', (p) => {
    if (p.dataType === 'node' && p.data.raw) {
      openDetail(p.data.raw)
    }
  })

  setTimeout(() => {
    if (archChart) {
      const needH = yCursor + 40
      const targetH = Math.max(560, needH)
      archChartRef.value.style.height = targetH + 'px'
      archChart.resize()
    }
  }, 60)
}

async function loadDomains() {
  try {
    allDomains.value = await request.get('/health-map/api/domains')
    filterDomains()
  } catch (e) {
    console.error('Failed to load domains:', e)
  }
}

function filterDomains() {
  const q = domainQuery.value.trim().toLowerCase()
  filteredDomains.value = q
    ? allDomains.value.filter(d => d.name.toLowerCase().includes(q))
    : [...allDomains.value]
}

async function enterDomain(d) {
  currentDomain.value = d
  mode.value = 'domain'
  entityQuery.value = ''
  expandedLayers.clear()
  await loadDomainDetail()
}

async function onDomainSwitch(domainName) {
  const d = allDomains.value.find(x => x.name === domainName)
  if (d) await enterDomain(d)
}

function exitDomain() {
  mode.value = 'overview'
}

async function loadDomainDetail() {
  refreshing.value = true
  try {
    const data = await request.get('/health-map/api/overview', {
      params: { domain: currentDomain.value.name }
    })
    stats.value = data.stats || { total: 0, green: 0, gray: 0, red: 0 }
    layers.value = data.layers || []
    await loadServiceCalls()
    await nextTick()
    renderDomainGraph()
  } catch (e) {
    console.error('Failed to load domain detail:', e)
  } finally {
    refreshing.value = false
  }
}

function visibleEntities(layer) {
  let list = layer.entities
  const q = entityQuery.value.trim().toLowerCase()
  if (q) {
    list = list.filter(e => e.name.toLowerCase().includes(q) || (e.ci_type || '').toLowerCase().includes(q))
  }
  if (expandedLayers.has(layer.key)) return list
  return list.slice(0, SHOW_LIMIT)
}

function visibleCount(layer) {
  let list = layer.entities
  const q = entityQuery.value.trim().toLowerCase()
  if (q) {
    list = list.filter(e => e.name.toLowerCase().includes(q) || (e.ci_type || '').toLowerCase().includes(q))
  }
  if (expandedLayers.has(layer.key)) return list.length
  return Math.min(list.length, SHOW_LIMIT)
}

function toggleLayer(key) {
  if (expandedLayers.has(key)) expandedLayers.delete(key)
  else expandedLayers.add(key)
}

async function openDetail(entity) {
  drawerEntity.value = entity
  drawerVisible.value = true
  drawerLoading.value = true
  drawerError.value = ''
  detail.value = null
  try {
    const data = await request.get(`/health-map/api/entity/${entity.id}`)
    detail.value = data
  } catch (e) {
    drawerError.value = '加载详情失败: ' + (e.message || '')
  } finally {
    drawerLoading.value = false
  }
}

async function refreshAll() {
  if (mode.value === 'overview') {
    await loadDomains()
  } else {
    await loadDomainDetail()
  }
}

function formatTime(ts) {
  if (!ts) return '-'
  try {
    const d = new Date(ts)
    const pad = (n) => String(n).padStart(2, '0')
    return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch {
    return ts
  }
}

async function openArchDialog() {
  archDialogVisible.value = true
  archGenerating.value = false
  archResult.value = null
  archMeta.value = null
  try {
    const data = await request.get('/api/arch-diagram/meta', { params: { domain: currentDomain.value.name } })
    archMeta.value = data
  } catch (e) {
    archMeta.value = { message: '加载域信息失败: ' + (e.message || '') }
  }
}

async function doGenerateArch() {
  archGenerating.value = true
  archResult.value = null
  try {
    archResult.value = await request.post('/api/arch-diagram/generate', {
      domain: currentDomain.value.name,
      drawio_path: archDrawioPath.value || null,
      format: archFormat.value,
      ai_layout: archAiLayout.value,
      live_draw: archLiveDraw.value,
    })
  } catch (e) {
    archResult.value = { ok: false, message: '生成失败: ' + (e.message || '') }
  } finally {
    archGenerating.value = false
  }
}

function browseDrawioPath() {
  const el = drawioFileInput.value
  if (el) el.click()
}

function onDrawioFilePick(e) {
  const file = e.target.files && e.target.files[0]
  if (file) {
    archDrawioPath.value = file.path || file.name
  }
  e.target.value = ''
}

onMounted(loadDomains)
</script>

<style scoped src="./FireMapView.style.css"></style>