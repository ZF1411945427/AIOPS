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
            <h1 class="fm-title">灭火图</h1>
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
            <span class="fm-subtitle">灭火图 · 实体分层视图</span>
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
      </div>

      <!-- Search bar -->
      <div class="fm-search-bar">
        <svg class="search-icon" viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="8.5" cy="8.5" r="5.5"/><path d="M12.5 12.5L17 17"/>
        </svg>
        <input v-model="entityQuery" class="search-input" placeholder="搜索实体名称 / ci_type..." />
      </div>

      <!-- Layer cards -->
      <div class="fm-layers">
        <div v-for="layer in layers" :key="layer.key" class="fm-layer-card">
          <div class="layer-header">
            <div class="layer-title">{{ layer.name }}</div>
            <div class="layer-meta">
              <span class="layer-count">{{ visibleCount(layer) }}/{{ layer.count }} 个实体</span>
              <span v-if="layer.fault" class="layer-badge fault">{{ layer.fault }} 故障</span>
              <span v-if="layer.offline" class="layer-badge offline">{{ layer.offline }} 离线</span>
              <span v-if="layer.healthy === layer.count" class="layer-badge ok">全部健康</span>
            </div>
          </div>
          <div class="layer-entities">
            <div
              v-for="e in visibleEntities(layer)"
              :key="e.id"
              class="entity-node"
              :class="[`status-${e.health_status}`]"
              @click="openDetail(e)"
            >
              <div class="entity-status-dot">
                <svg viewBox="0 0 16 16" width="16" height="16">
                  <circle cx="8" cy="8" r="5" fill="currentColor"/>
                </svg>
              </div>
              <div class="entity-info">
                <div class="entity-name">{{ e.name }}</div>
                <div class="entity-meta">
                  <span class="entity-ci-type">{{ e.ci_type }}</span>
                  <span v-if="e.alert_count" class="entity-alert-badge">{{ e.alert_count }} 告警</span>
                </div>
              </div>
            </div>
            <div v-if="!layer.entities.length" class="layer-empty">该层暂无实体</div>
          </div>
          <button v-if="layer.count > SHOW_LIMIT" class="layer-toggle" @click="toggleLayer(layer.key)">
            {{ expandedLayers.has(layer.key) ? '收起' : `展开全部 ${layer.count} 个` }}
          </button>
        </div>
      </div>
    </template>

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
import { ref, reactive, computed, onMounted } from 'vue'
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

onMounted(loadDomains)
</script>

<style scoped>
.firemap {
  position: relative;
  min-height: calc(100vh - 80px);
  padding: 24px 28px;
  background: var(--content-bg, #f1f5f9);
  color: var(--text-primary, #1e293b);
}
html[data-theme="dark"] .firemap {
  background: radial-gradient(ellipse at 20% 20%, #0b1120 0%, #030712 100%);
  color: #e2e8f0;
}

/* ── Header ── */
.fm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 16px;
}
.fm-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.fm-title-icon {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: color-mix(in srgb, var(--primary, #6366f1) 18%, transparent);
  color: var(--primary, #6366f1);
  border: 1px solid color-mix(in srgb, var(--primary, #6366f1) 20%, transparent);
}
.fm-title {
  font-size: 22px;
  font-weight: 700;
  margin: 0;
  letter-spacing: 1px;
  color: var(--text-primary, #1e293b);
}
html[data-theme="dark"] .fm-title {
  background: linear-gradient(135deg, #f0f0ff, #818cf8);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.fm-subtitle {
  font-size: 12px;
  color: var(--text-muted, #94a3b8);
  letter-spacing: 2px;
  text-transform: uppercase;
}

.fm-stats {
  display: flex;
  gap: 12px;
}
.fm-stat-card {
  min-width: 80px;
  padding: 12px 20px;
  border-radius: 12px;
  background: var(--card-bg, #ffffff);
  border: 1px solid color-mix(in srgb, var(--text-muted, #94a3b8) 20%, transparent);
  text-align: center;
}
html[data-theme="dark"] .fm-stat-card {
  background: rgba(15,23,42,0.7);
  border: 1px solid rgba(51,65,85,0.4);
  backdrop-filter: blur(8px);
}
.fm-stat-card .stat-value {
  font-size: 26px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.fm-stat-card .stat-label {
  font-size: 11px;
  color: var(--text-muted, #94a3b8);
  margin-top: 2px;
  letter-spacing: 1px;
  text-transform: uppercase;
}
.fm-stat-card.total .stat-value { color: var(--text-primary, #1e293b); }
html[data-theme="dark"] .fm-stat-card.total .stat-value { color: #e2e8f0; }
.fm-stat-card.healthy .stat-value { color: var(--success, #10b981); }
.fm-stat-card.fault .stat-value { color: var(--danger, #ef4444); }
.fm-stat-card.offline .stat-value { color: var(--text-muted, #94a3b8); }

/* ── Search ── */
.fm-search-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 10px;
  background: var(--card-bg, #ffffff);
  border: 1px solid color-mix(in srgb, var(--text-muted, #94a3b8) 20%, transparent);
  margin-bottom: 20px;
  transition: border-color 0.2s;
}
html[data-theme="dark"] .fm-search-bar {
  background: rgba(15,23,42,0.5);
  border: 1px solid rgba(51,65,85,0.3);
}
.fm-search-bar:focus-within {
  border-color: color-mix(in srgb, var(--primary, #6366f1) 50%, transparent);
}
html[data-theme="dark"] .fm-search-bar:focus-within {
  border-color: rgba(99,102,241,0.4);
}
.search-icon {
  flex-shrink: 0;
  color: var(--text-muted, #94a3b8);
}
.search-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: 13px;
  color: var(--text-primary, #1e293b);
}
html[data-theme="dark"] .search-input {
  color: #e2e8f0;
}
.search-input::placeholder {
  color: var(--text-muted, #94a3b8);
}

/* ── Domain Cards ── */
.fm-domain-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}
.fm-domain-card {
  padding: 20px;
  border-radius: 14px;
  background: var(--card-bg, #ffffff);
  border: 1px solid color-mix(in srgb, var(--text-muted, #94a3b8) 18%, transparent);
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
  overflow: hidden;
}
html[data-theme="dark"] .fm-domain-card {
  background: rgba(15,23,42,0.6);
  border: 1px solid rgba(51,65,85,0.3);
  backdrop-filter: blur(6px);
}
.fm-domain-card:hover {
  transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--primary, #6366f1) 35%, transparent);
  box-shadow: 0 4px 16px rgba(0,0,0,0.06);
}
html[data-theme="dark"] .fm-domain-card:hover {
  border-color: rgba(99,102,241,0.25);
  box-shadow: 0 4px 20px rgba(0,0,0,0.3);
}
.fm-domain-card.has-fault {
  border-color: color-mix(in srgb, var(--danger, #ef4444) 35%, transparent);
}
html[data-theme="dark"] .fm-domain-card.has-fault {
  border-color: rgba(239,68,68,0.25);
}

.domain-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.domain-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary, #1e293b);
}
html[data-theme="dark"] .domain-name { color: #e2e8f0; }
.domain-count {
  font-size: 12px;
  color: var(--text-muted, #94a3b8);
}

.domain-stats-row {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
}
.domain-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 48px;
}
.domain-stat .ds-value {
  font-size: 20px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.domain-stat .ds-label {
  font-size: 10px;
  color: var(--text-muted, #94a3b8);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-top: 1px;
}
.domain-stat.healthy .ds-value { color: var(--success, #10b981); }
.domain-stat.fault .ds-value { color: var(--danger, #ef4444); }
.domain-stat.offline .ds-value { color: var(--text-muted, #94a3b8); }

.domain-bar {
  display: flex;
  height: 4px;
  border-radius: 2px;
  overflow: hidden;
  background: color-mix(in srgb, var(--text-muted, #94a3b8) 10%, transparent);
  margin-bottom: 10px;
}
html[data-theme="dark"] .domain-bar {
  background: rgba(51,65,85,0.3);
}
.bar-segment.healthy { background: var(--success, #10b981); }
.bar-segment.fault { background: var(--danger, #ef4444); }
.bar-segment.offline { background: var(--text-muted, #94a3b8); }

.domain-alert-banner {
  font-size: 11px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--danger, #ef4444) 12%, transparent);
  color: var(--danger, #ef4444);
  display: inline-block;
}
html[data-theme="dark"] .domain-alert-banner {
  background: rgba(239,68,68,0.15);
  color: #fca5a5;
}

.domain-empty {
  grid-column: 1 / -1;
  text-align: center;
  padding: 48px 0;
  color: var(--text-muted, #94a3b8);
  font-size: 14px;
}

/* ── Domain Header (detail mode) ── */
.fm-domain-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  border-radius: 12px;
  background: color-mix(in srgb, var(--primary, #6366f1) 6%, transparent);
  border: 1px solid color-mix(in srgb, var(--primary, #6366f1) 15%, transparent);
  margin-bottom: 20px;
}
html[data-theme="dark"] .fm-domain-header {
  background: rgba(99,102,241,0.08);
  border-color: rgba(99,102,241,0.15);
}
.fm-back-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 13px;
  color: var(--primary, #6366f1);
  padding: 4px 10px;
  border-radius: 6px;
  white-space: nowrap;
  transition: background 0.15s;
}
.fm-back-btn:hover {
  background: color-mix(in srgb, var(--primary, #6366f1) 10%, transparent);
}
html[data-theme="dark"] .fm-back-btn:hover {
  background: rgba(99,102,241,0.12);
}
.domain-context {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.domain-context-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary, #1e293b);
}
html[data-theme="dark"] .domain-context-name { color: #e2e8f0; }
.domain-context-meta {
  font-size: 11px;
  color: var(--text-muted, #94a3b8);
}

/* ── Layer Cards ── */
.fm-layers {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.fm-layer-card {
  background: var(--card-bg, #ffffff);
  border: 1px solid color-mix(in srgb, var(--text-muted, #94a3b8) 20%, transparent);
  border-radius: 16px;
  overflow: hidden;
  transition: border-color 0.2s;
}
html[data-theme="dark"] .fm-layer-card {
  background: rgba(15,23,42,0.6);
  border: 1px solid rgba(51,65,85,0.3);
  backdrop-filter: blur(6px);
}
.fm-layer-card:hover {
  border-color: color-mix(in srgb, var(--primary, #6366f1) 40%, transparent);
}
html[data-theme="dark"] .fm-layer-card:hover {
  border-color: rgba(99,102,241,0.25);
}

.layer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  background: color-mix(in srgb, var(--text-muted, #94a3b8) 6%, transparent);
  border-bottom: 1px solid color-mix(in srgb, var(--text-muted, #94a3b8) 15%, transparent);
}
html[data-theme="dark"] .layer-header {
  background: rgba(30,41,59,0.4);
  border-bottom: 1px solid rgba(51,65,85,0.2);
}
.layer-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #1e293b);
}
html[data-theme="dark"] .layer-title { color: #e2e8f0; }
.layer-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}
.layer-count {
  font-size: 12px;
  color: var(--text-muted, #94a3b8);
}
.layer-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}
.layer-badge.fault { background: color-mix(in srgb, var(--danger, #ef4444) 15%, transparent); color: var(--danger, #ef4444); }
html[data-theme="dark"] .layer-badge.fault { background: rgba(239,68,68,0.15); color: #fca5a5; }
.layer-badge.offline { background: color-mix(in srgb, var(--text-muted, #94a3b8) 15%, transparent); color: var(--text-muted, #94a3b8); }
html[data-theme="dark"] .layer-badge.offline { background: rgba(107,114,128,0.15); color: #9ca3af; }
.layer-badge.ok { background: color-mix(in srgb, var(--success, #10b981) 15%, transparent); color: var(--success, #10b981); }
html[data-theme="dark"] .layer-badge.ok { background: rgba(16,185,129,0.15); color: #6ee7b7; }

.layer-entities {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 14px 20px;
}
.layer-toggle {
  display: block;
  width: calc(100% - 40px);
  margin: 0 20px 12px;
  padding: 8px;
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--text-muted, #94a3b8) 15%, transparent);
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-muted, #94a3b8);
  text-align: center;
  transition: all 0.15s;
}
html[data-theme="dark"] .layer-toggle {
  border-color: rgba(51,65,85,0.3);
}
.layer-toggle:hover {
  background: color-mix(in srgb, var(--text-muted, #94a3b8) 5%, transparent);
  color: var(--text-primary, #1e293b);
}
html[data-theme="dark"] .layer-toggle:hover {
  background: rgba(30,41,59,0.3);
  color: #e2e8f0;
}

/* ── Entity Nodes ── */
.entity-node {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--text-muted, #94a3b8) 4%, transparent);
  border: 1px solid color-mix(in srgb, var(--text-muted, #94a3b8) 12%, transparent);
  cursor: pointer;
  transition: all 0.18s;
  min-width: 180px;
  flex: 0 1 auto;
}
html[data-theme="dark"] .entity-node {
  background: rgba(30,41,59,0.3);
  border: 1px solid rgba(51,65,85,0.2);
}
.entity-node:hover {
  background: color-mix(in srgb, var(--primary, #6366f1) 6%, transparent);
  border-color: color-mix(in srgb, var(--primary, #6366f1) 30%, transparent);
  transform: translateY(-1px);
}
html[data-theme="dark"] .entity-node:hover {
  background: rgba(30,41,59,0.6);
  border-color: rgba(99,102,241,0.3);
}
.entity-node.mini {
  padding: 8px 12px;
  gap: 8px;
  min-width: auto;
  width: 100%;
}
.entity-status-dot {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
}
.entity-node.status-green .entity-status-dot { color: var(--success, #10b981); }
.entity-node.status-gray .entity-status-dot { color: var(--text-muted, #94a3b8); }
.entity-node.status-red .entity-status-dot { color: var(--danger, #ef4444); }
.entity-info { min-width: 0; }
.entity-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #1e293b);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 160px;
}
html[data-theme="dark"] .entity-name { color: #e2e8f0; }
.entity-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
}
.entity-ci-type {
  font-size: 11px;
  color: var(--text-muted, #94a3b8);
}
.entity-alert-badge {
  font-size: 10px;
  padding: 0 6px;
  background: color-mix(in srgb, var(--danger, #ef4444) 20%, transparent);
  color: var(--danger, #ef4444);
  border-radius: 8px;
  font-weight: 600;
}
html[data-theme="dark"] .entity-alert-badge {
  background: rgba(239,68,68,0.2);
  color: #fca5a5;
}
.layer-empty {
  width: 100%;
  padding: 24px;
  text-align: center;
  color: var(--text-muted, #94a3b8);
  font-size: 13px;
}

/* ── Drawer ── */
.fm-drawer :deep(.el-drawer) {
  background: var(--card-bg, #ffffff);
  color: var(--text-primary, #1e293b);
}
html[data-theme="dark"] .fm-drawer :deep(.el-drawer) {
  background: #1a1f2e;
  color: #e2e8f0;
}
.fm-drawer :deep(.el-drawer__header) { margin-bottom: 4px; padding: 20px 20px 0; }
.fm-drawer :deep(.el-drawer__body) { padding: 0 20px 20px; }
.drawer-header {
  display: flex;
  align-items: center;
  gap: 10px;
}
.drawer-status-icon {
  width: 32px; height: 32px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%;
  background: color-mix(in srgb, var(--text-muted, #94a3b8) 8%, transparent);
}
html[data-theme="dark"] .drawer-status-icon { background: rgba(30,41,59,0.5); }
.drawer-status-icon.status-green { color: var(--success, #10b981); }
.drawer-status-icon.status-gray { color: var(--text-muted, #94a3b8); }
.drawer-status-icon.status-red { color: var(--danger, #ef4444); }
.drawer-title {
  font-size: 15px; font-weight: 700;
  color: var(--text-primary, #1e293b);
}
html[data-theme="dark"] .drawer-title { color: #e2e8f0; }
.drawer-ci-type {
  font-size: 11px;
  color: var(--text-muted, #94a3b8);
  margin-top: 1px;
}
.drawer-loading {
  display: flex; justify-content: center; padding: 60px 0;
  color: var(--primary, #6366f1);
}
.drawer-error {
  color: var(--danger, #ef4444); text-align: center; padding: 40px 0; font-size: 13px;
}
html[data-theme="dark"] .drawer-error { color: #fca5a5; }
.drawer-body { padding-bottom: 24px; }
.detail-section { margin-top: 20px; }
.section-title {
  font-size: 13px; font-weight: 600;
  color: var(--text-muted, #94a3b8);
  margin: 0 0 10px; letter-spacing: 0.5px; text-transform: uppercase;
}
.section-empty {
  color: var(--text-muted, #94a3b8); font-size: 12px; padding: 8px 0;
}
.detail-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 8px;
}
.detail-item {
  padding: 10px 12px;
  background: color-mix(in srgb, var(--text-muted, #94a3b8) 4%, transparent);
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--text-muted, #94a3b8) 12%, transparent);
}
html[data-theme="dark"] .detail-item {
  background: rgba(30,41,59,0.3);
  border: 1px solid rgba(51,65,85,0.15);
}
.detail-label {
  display: block; font-size: 10px; color: var(--text-muted, #94a3b8);
  text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px;
}
.detail-value {
  font-size: 13px; font-weight: 600;
  color: var(--text-primary, #1e293b);
}
html[data-theme="dark"] .detail-value { color: #e2e8f0; }
.status-tag {
  display: inline-block; font-size: 11px; padding: 1px 8px;
  border-radius: 6px; font-weight: 600;
}
.status-tag.online { background: color-mix(in srgb, var(--success, #10b981) 15%, transparent); color: var(--success, #10b981); }
html[data-theme="dark"] .status-tag.online { background: rgba(16,185,129,0.15); color: #6ee7b7; }
.status-tag.offline { background: color-mix(in srgb, var(--text-muted, #94a3b8) 15%, transparent); color: var(--text-muted, #94a3b8); }
html[data-theme="dark"] .status-tag.offline { background: rgba(107,114,128,0.15); color: #9ca3af; }
.status-tag.error { background: color-mix(in srgb, var(--danger, #ef4444) 15%, transparent); color: var(--danger, #ef4444); }
html[data-theme="dark"] .status-tag.error { background: rgba(239,68,68,0.15); color: #fca5a5; }

.alert-item {
  padding: 10px 12px;
  background: color-mix(in srgb, var(--text-muted, #94a3b8) 4%, transparent);
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--text-muted, #94a3b8) 12%, transparent);
  margin-bottom: 6px;
}
html[data-theme="dark"] .alert-item {
  background: rgba(30,41,59,0.3);
  border: 1px solid rgba(51,65,85,0.15);
}
.alert-item.critical { border-left: 3px solid var(--danger, #ef4444); }
.alert-item.warning { border-left: 3px solid var(--warning, #f59e0b); }
.alert-item.info { border-left: 3px solid var(--info, #3b82f6); }
.alert-header {
  display: flex; align-items: center; gap: 6px; margin-bottom: 4px;
}
.alert-severity-tag {
  font-size: 10px; font-weight: 700; padding: 1px 6px;
  border-radius: 4px; text-transform: uppercase;
}
.alert-severity-tag.critical { background: color-mix(in srgb, var(--danger, #ef4444) 20%, transparent); color: var(--danger, #ef4444); }
.alert-severity-tag.warning { background: color-mix(in srgb, var(--warning, #f59e0b) 20%, transparent); color: var(--warning, #f59e0b); }
.alert-severity-tag.info { background: color-mix(in srgb, var(--info, #3b82f6) 20%, transparent); color: var(--info, #3b82f6); }
html[data-theme="dark"] .alert-severity-tag.critical { background: rgba(239,68,68,0.2); color: #fca5a5; }
html[data-theme="dark"] .alert-severity-tag.warning { background: rgba(245,158,11,0.2); color: #fcd34d; }
html[data-theme="dark"] .alert-severity-tag.info { background: rgba(59,130,246,0.2); color: #93c5fd; }
.alert-status-tag { font-size: 10px; color: var(--text-muted, #94a3b8); }
.alert-message {
  font-size: 12px; color: var(--text-primary, #1e293b); margin-bottom: 4px;
}
html[data-theme="dark"] .alert-message { color: #e2e8f0; }
.alert-meta {
  display: flex; gap: 10px; font-size: 10px;
  color: var(--text-muted, #94a3b8); flex-wrap: wrap;
}

.metric-item {
  padding: 8px 12px;
  background: color-mix(in srgb, var(--text-muted, #94a3b8) 3%, transparent);
  border-radius: 6px; margin-bottom: 4px;
  border: 1px solid color-mix(in srgb, var(--text-muted, #94a3b8) 8%, transparent);
}
html[data-theme="dark"] .metric-item {
  background: rgba(30,41,59,0.2);
  border: 1px solid rgba(51,65,85,0.1);
}
.metric-primary {
  display: flex; justify-content: space-between; align-items: center;
}
.metric-name { font-size: 12px; color: var(--text-muted, #94a3b8); }
.metric-value {
  font-size: 14px; font-weight: 700;
  color: var(--text-primary, #1e293b);
  font-variant-numeric: tabular-nums;
}
html[data-theme="dark"] .metric-value { color: #e2e8f0; }
.metric-unit { font-size: 10px; color: var(--text-muted, #94a3b8); margin-left: 2px; font-weight: 400; }
.metric-time { font-size: 10px; color: var(--text-muted, #94a3b8); margin-top: 2px; }

/* ── Trace Info (API layer) ── */
.trace-info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.trace-metric {
  padding: 10px 12px;
  background: color-mix(in srgb, var(--text-muted, #94a3b8) 4%, transparent);
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--text-muted, #94a3b8) 12%, transparent);
}
html[data-theme="dark"] .trace-metric {
  background: rgba(30,41,59,0.3);
  border: 1px solid rgba(51,65,85,0.15);
}
.trace-metric-label {
  font-size: 10px;
  color: var(--text-muted, #94a3b8);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}
.trace-metric-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--success, #10b981);
  font-variant-numeric: tabular-nums;
}
html[data-theme="dark"] .trace-metric-value { color: #6ee7b7; }
.trace-metric-value.is-danger {
  color: var(--danger, #ef4444);
}
html[data-theme="dark"] .trace-metric-value.is-danger { color: #fca5a5; }
.trace-metric-threshold {
  font-size: 10px;
  color: var(--text-muted, #94a3b8);
  margin-top: 2px;
}
.trace-services {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 10px;
}
.trace-services-label {
  font-size: 11px;
  color: var(--text-muted, #94a3b8);
}
.trace-service-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--primary, #6366f1) 12%, transparent);
  color: var(--primary, #6366f1);
  font-weight: 500;
}
html[data-theme="dark"] .trace-service-tag {
  background: rgba(99,102,241,0.15);
  color: #a5b4fc;
}

/* ── Infra Metrics ── */
.infra-metric-bar {
  margin-bottom: 12px;
}
.infra-metric-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.infra-metric-name {
  font-size: 12px;
  color: var(--text-muted, #94a3b8);
  font-weight: 500;
}
.infra-metric-value {
  font-size: 13px;
  font-weight: 700;
  color: var(--success, #10b981);
  font-variant-numeric: tabular-nums;
}
html[data-theme="dark"] .infra-metric-value { color: #6ee7b7; }
.infra-metric-value.is-danger {
  color: var(--danger, #ef4444);
}
html[data-theme="dark"] .infra-metric-value.is-danger { color: #fca5a5; }
.infra-metric-track {
  position: relative;
  height: 6px;
  border-radius: 3px;
  background: color-mix(in srgb, var(--text-muted, #94a3b8) 10%, transparent);
  overflow: visible;
}
html[data-theme="dark"] .infra-metric-track {
  background: rgba(51,65,85,0.3);
}
.infra-metric-fill {
  height: 100%;
  border-radius: 3px;
  background: var(--success, #10b981);
  transition: width 0.3s ease;
}
html[data-theme="dark"] .infra-metric-fill { background: #10b981; }
.infra-metric-fill.is-danger {
  background: var(--danger, #ef4444);
}
html[data-theme="dark"] .infra-metric-fill.is-danger { background: #ef4444; }
.infra-metric-threshold-line {
  position: absolute;
  top: -2px;
  width: 2px;
  height: 10px;
  background: var(--warning, #f59e0b);
  border-radius: 1px;
}
html[data-theme="dark"] .infra-metric-threshold-line { background: #f59e0b; }
.infra-metric-threshold-label {
  font-size: 10px;
  color: var(--text-muted, #94a3b8);
  margin-top: 2px;
}

/* Refresh button */
.fm-refresh {
  position: fixed; bottom: 28px; right: 28px;
  width: 44px; height: 44px; border-radius: 50%;
  border: 1px solid color-mix(in srgb, var(--primary, #6366f1) 25%, transparent);
  background: var(--card-bg, #ffffff);
  color: var(--primary, #6366f1);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all 0.2s; z-index: 10;
}
html[data-theme="dark"] .fm-refresh {
  background: rgba(15,23,42,0.85);
  border: 1px solid rgba(99,102,241,0.25);
  backdrop-filter: blur(8px);
}
.fm-refresh:hover {
  background: color-mix(in srgb, var(--primary, #6366f1) 8%, transparent);
  border-color: color-mix(in srgb, var(--primary, #6366f1) 50%, transparent);
  transform: scale(1.05);
}
html[data-theme="dark"] .fm-refresh:hover {
  background: rgba(30,41,59,0.9);
  border-color: rgba(99,102,241,0.5);
}
.spinning { animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
