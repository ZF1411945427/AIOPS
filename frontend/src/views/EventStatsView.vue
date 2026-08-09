<template>
  <div class="event-stats-page">
    <div class="page-header">
      <h1>事件统计与收敛分析</h1>
      <p>K8s 集群事件统计 + 告警聚类 · 关联拓扑 · 根因推荐</p>
    </div>

    <div class="tab-bar">
      <button v-for="t in pageTabs" :key="t.key" class="tab" :class="{ active: activePage === t.key }" @click="activePage = t.key">
        {{ t.label }}
      </button>
    </div>

    <!-- ========== 事件统计 Tab ========== -->
    <template v-if="activePage === 'stats'">
      <div class="stat-cards">
        <div class="stat-card">
          <div class="stat-icon blue">📊</div>
          <div class="stat-body"><div class="stat-value">{{ stats.total || 0 }}</div><div class="stat-label">总事件数</div></div>
        </div>
        <div class="stat-card warning">
          <div class="stat-icon yellow">⚠️</div>
          <div class="stat-body"><div class="stat-value">{{ stats.warnings || 0 }}</div><div class="stat-label">警告事件</div></div>
        </div>
        <div class="stat-card danger">
          <div class="stat-icon red">🔴</div>
          <div class="stat-body"><div class="stat-value">{{ stats.criticals || 0 }}</div><div class="stat-label">严重事件</div></div>
        </div>
        <div class="stat-card">
          <div class="stat-icon gray">ℹ️</div>
          <div class="stat-body"><div class="stat-value">{{ stats.infos || 0 }}</div><div class="stat-label">普通事件</div></div>
        </div>
      </div>

      <div class="grid-2">
        <div class="panel">
          <div class="panel-header"><h3>按资源类型分布 (Top 10)</h3></div>
          <div class="panel-body">
            <div v-if="loading" class="loading-state">加载中...</div>
            <table v-else-if="stats.by_kind && stats.by_kind.length" class="table">
              <thead><tr><th>资源类型</th><th>数量</th><th>占比</th></tr></thead>
              <tbody>
                <tr v-for="item in stats.by_kind" :key="item.kind">
                  <td>{{ item.kind }}</td>
                  <td>{{ item.count }}</td>
                  <td>
                    <div class="bar-wrap">
                      <div class="bar-fill blue" :style="{ width: barWidth(item.count, stats.total) + '%' }"></div>
                      <span class="bar-text">{{ pct(item.count, stats.total) }}%</span>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-else class="empty-state">暂无数据</div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header"><h3>按原因分布 (Top 10)</h3></div>
          <div class="panel-body">
            <div v-if="loading" class="loading-state">加载中...</div>
            <table v-else-if="stats.by_reason && stats.by_reason.length" class="table">
              <thead><tr><th>原因</th><th>数量</th><th>占比</th></tr></thead>
              <tbody>
                <tr v-for="item in stats.by_reason" :key="item.reason">
                  <td>{{ item.reason }}</td>
                  <td>{{ item.count }}</td>
                  <td>
                    <div class="bar-wrap">
                      <div class="bar-fill orange" :style="{ width: barWidth(item.count, stats.total) + '%' }"></div>
                      <span class="bar-text">{{ pct(item.count, stats.total) }}%</span>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-else class="empty-state">暂无数据</div>
          </div>
        </div>
      </div>
    </template>

    <!-- ========== 告警收敛闭环 Tab ========== -->
    <template v-if="activePage === 'correlation'">
      <div class="summary-grid" v-if="summary">
        <div class="summary-card" :class="{ danger: sevCritical > 0 }">
          <div class="summary-label">活跃告警</div>
          <div class="summary-value">{{ summary.total_alerts }}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">涉及资产</div>
          <div class="summary-value">{{ summary.total_assets }}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">服务聚类</div>
          <div class="summary-value">{{ summary.service_cluster_count }}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">时间窗聚类</div>
          <div class="summary-value">{{ summary.time_cluster_count }}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">拓扑聚类</div>
          <div class="summary-value">{{ summary.topology_cluster_count }}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">分析耗时</div>
          <div class="summary-value">{{ summary.elapsed_ms }} ms</div>
        </div>
      </div>

      <div class="panel" v-if="summary && summary.severity_distribution">
        <div class="panel-head"><span>严重度分布</span></div>
        <div class="panel-body">
          <div class="sev-row">
            <span v-for="(count, sev) in summary.severity_distribution" :key="sev" class="sev-chip" :class="'sev-' + sev">
              {{ sevLabel(sev) }}: {{ count }}
            </span>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <span>聚类明细</span>
          <div class="panel-actions">
            <button class="btn btn-sm" @click="loadCorrelation" :disabled="corrLoading">{{ corrLoading ? '分析中...' : '刷新' }}</button>
            <button class="btn btn-sm" @click="forceRefresh">强制刷新缓存</button>
          </div>
        </div>
        <div class="tab-bar sub">
          <button v-for="t in corrTabs" :key="t.key" class="tab" :class="{ active: activeCorrTab === t.key }" @click="activeCorrTab = t.key">
            {{ t.label }} <span class="tab-count">{{ corrTabList(t.key).length }}</span>
          </button>
        </div>
        <div class="panel-body">
          <div v-if="corrLoading && !summary" class="loading-state">分析中...</div>
          <div v-else-if="corrWarning" class="empty-state text-danger">{{ corrWarning }}</div>
          <div v-else-if="!currentCorrList.length" class="empty-state">暂无聚类（当前无活跃告警）</div>
          <table v-else class="table">
            <thead>
              <tr>
                <th>Cluster ID</th>
                <th>类型</th>
                <th>告警数</th>
                <th>资产数</th>
                <th>主严重度</th>
                <th>关键资产</th>
                <th>涉及服务</th>
                <th>最早</th>
                <th>最新</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in currentCorrList" :key="c.cluster_id" :class="{ 'row-critical': c.dominant_severity === 'critical' }">
                <td class="text-mono">{{ c.cluster_id }}</td>
                <td><span class="badge" :class="typeClass(c.cluster_type)">{{ typeLabel(c.cluster_type) }}</span></td>
                <td>{{ c.alert_count }}</td>
                <td>{{ c.asset_count }}</td>
                <td><span class="badge" :class="sevClass(c.dominant_severity)">{{ sevLabel(c.dominant_severity) }}</span></td>
                <td class="text-sm">{{ c.key_asset_name || '-' }}</td>
                <td class="text-sm">{{ (c.services || []).join(', ') || '-' }}</td>
                <td class="text-sm">{{ c.earliest_at }}</td>
                <td class="text-sm">{{ c.latest_at }}</td>
                <td><button class="btn btn-sm" @click="showDetail(c.cluster_id)">详情</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="detail" class="modal-overlay" @click.self="detail = null">
        <div class="modal-box modal-lg">
          <h3>Cluster「{{ detail.cluster?.cluster_id }}」详情</h3>
          <div v-if="detail.warning" class="text-danger">{{ detail.warning }}</div>
          <template v-else>
            <div class="detail-section">
              <h4>基本信息</h4>
              <div class="kv-grid">
                <div><span class="kv-label">类型：</span>{{ typeLabel(detail.cluster?.cluster_type) }}</div>
                <div><span class="kv-label">告警数：</span>{{ detail.cluster?.alert_count }}</div>
                <div><span class="kv-label">资产数：</span>{{ detail.cluster?.asset_count }}</div>
                <div><span class="kv-label">主严重度：</span>{{ sevLabel(detail.cluster?.dominant_severity) }}</div>
                <div><span class="kv-label">关键资产：</span>{{ detail.cluster?.key_asset_name || '-' }}</div>
                <div><span class="kv-label">涉及服务：</span>{{ (detail.cluster?.services || []).join(', ') || '-' }}</div>
              </div>
            </div>
            <div class="detail-section">
              <h4>根因推荐</h4>
              <pre class="code-block">{{ formatJson(detail.root_cause) }}</pre>
            </div>
            <div class="detail-section">
              <h4>影响分析</h4>
              <pre class="code-block">{{ formatJson(detail.impact_analysis) }}</pre>
            </div>
            <div class="detail-section">
              <h4>告警列表 (前 20)</h4>
              <table class="table">
                <thead><tr><th>ID</th><th>资产</th><th>指标</th><th>严重度</th><th>消息</th><th>时间</th></tr></thead>
                <tbody>
                  <tr v-for="a in (detail.cluster?.alerts || [])" :key="a.id">
                    <td class="text-mono">{{ a.id }}</td>
                    <td class="text-sm">{{ a.asset_name || '-' }}</td>
                    <td class="text-mono">{{ a.metric_name }}</td>
                    <td><span class="badge" :class="sevClass(a.severity)">{{ sevLabel(a.severity) }}</span></td>
                    <td class="text-sm">{{ a.message }}</td>
                    <td class="text-sm">{{ a.created_at }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
          <div class="modal-actions">
            <button class="btn" @click="detail = null">关闭</button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const activePage = ref('stats')

const pageTabs = [
  { key: 'stats', label: '事件统计' },
  { key: 'correlation', label: '告警收敛闭环' },
]

// --- 事件统计 ---
const loading = ref(false)
const stats = ref({})

async function loadStats() {
  loading.value = true
  try {
    const data = await request.get('/events/api/stats')
    stats.value = data
  } catch (e) {
    ElMessage.error('加载统计失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function pct(count, total) {
  if (!total) return 0
  return ((count / total) * 100).toFixed(1)
}
function barWidth(count, total) {
  return Math.max(2, pct(count, total))
}

// --- 告警收敛闭环 ---
const corrLoading = ref(false)
const corrWarning = ref('')
const summary = ref(null)
const serviceClusters = ref([])
const timeClusters = ref([])
const topologyClusters = ref([])
const activeCorrTab = ref('service')
const detail = ref(null)

const corrTabs = [
  { key: 'service', label: '服务聚类' },
  { key: 'time', label: '时间窗聚类' },
  { key: 'topology', label: '拓扑聚类' },
]

const currentCorrList = computed(() => corrTabList(activeCorrTab.value))

function corrTabList(key) {
  if (key === 'service') return serviceClusters.value
  if (key === 'time') return timeClusters.value
  if (key === 'topology') return topologyClusters.value
  return []
}

const sevCritical = computed(() => (summary.value?.severity_distribution?.critical) || 0)

function sevLabel(s) {
  return { critical: '严重', high: '高', warning: '警告', medium: '中', info: '信息', low: '低' }[s] || s || '-'
}
function sevClass(s) {
  return { critical: 'danger', high: 'danger', warning: 'warn', medium: 'warn', info: 'off', low: 'off' }[s] || 'off'
}
function typeLabel(t) {
  return { service: '服务', time_window: '时间窗', topology: '拓扑' }[t] || t
}
function typeClass(t) {
  return { service: 'on', time_window: 'warn', topology: 'off' }[t] || 'off'
}
function formatJson(obj) {
  if (!obj) return '(无数据)'
  try { return JSON.stringify(obj, null, 2) } catch (e) { return String(obj) }
}

async function loadCorrelation() {
  corrLoading.value = true
  corrWarning.value = ''
  try {
    const data = await request.get('/api/alert-correlation/clusters')
    if (data.warning) {
      corrWarning.value = data.warning
      ElMessage.warning(data.warning)
    } else {
      summary.value = data.summary
      serviceClusters.value = data.service_clusters || []
      timeClusters.value = data.time_clusters || []
      topologyClusters.value = data.topology_clusters || []
    }
  } catch (e) {
    console.error('alert-correlation:', e)
  } finally {
    corrLoading.value = false
  }
}

async function forceRefresh() {
  try {
    await request.post('/api/alert-correlation/refresh')
    ElMessage.success('已强制刷新聚类缓存')
    loadCorrelation()
  } catch (e) {
    ElMessage.error('刷新失败: ' + (e.message || e))
  }
}

async function showDetail(id) {
  detail.value = { loading: true }
  try {
    const data = await request.get(`/api/alert-correlation/clusters/${id}`)
    detail.value = data
  } catch (e) {
    ElMessage.error('加载详情失败: ' + (e.message || e))
    detail.value = null
  }
}

onMounted(() => {
  loadStats()
  loadCorrelation()
})
</script>

<style scoped>
.event-stats-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.tab-bar { display: flex; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); margin-bottom: 16px; }
.tab-bar.sub { margin-bottom: 0; border-bottom: none; padding: 0; }
.tab { padding: 10px 16px; border: none; background: transparent; color: var(--text-secondary, #64748b); cursor: pointer; font-size: 0.85rem; border-bottom: 2px solid transparent; }
.tab.active { color: var(--text, #1e293b); border-bottom-color: #3b82f6; font-weight: 600; }
.tab-count { display: inline-block; min-width: 18px; padding: 1px 5px; border-radius: 8px; background: rgba(100,116,139,0.15); color: #64748b; font-size: 0.7rem; margin-left: 4px; }
.stat-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 16px; }
.stat-card { display: flex; align-items: center; gap: 12px; background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.stat-icon { width: 38px; height: 38px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px; background: rgba(99,102,241,0.1); }
.stat-icon.blue { background: rgba(59,130,246,0.1); }
.stat-icon.red { background: rgba(239,68,68,0.1); }
.stat-icon.yellow { background: rgba(245,158,11,0.1); }
.stat-icon.gray { background: rgba(100,116,139,0.1); }
.stat-value { font-size: 1.3rem; font-weight: 700; color: var(--text, #1e293b); }
.stat-label { font-size: 0.72rem; color: var(--text-secondary, #64748b); }
.grid-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-top: 12px; }
.panel:first-child { margin-top: 0; }
.panel-header { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.panel-header h3 { margin: 0; font-size: 0.95rem; color: var(--text, #1e293b); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); display: flex; justify-content: space-between; align-items: center; }
.panel-actions { display: flex; gap: 10px; align-items: center; }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.table tr.row-critical td { background: rgba(239,68,68,0.04); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.text-mono { font-family: 'Consolas', monospace; font-size: 0.8rem; }
.text-danger { color: #ef4444; }
.bar-wrap { display: flex; align-items: center; gap: 8px; min-width: 120px; }
.bar-fill { height: 8px; border-radius: 4px; min-width: 2px; }
.bar-fill.blue { background: linear-gradient(90deg, #3b82f6, #60a5fa); }
.bar-fill.orange { background: linear-gradient(90deg, #f59e0b, #fbbf24); }
.bar-text { font-size: 0.72rem; color: var(--text-secondary, #64748b); white-space: nowrap; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.on { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.off { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.warn { background: rgba(245,158,11,0.1); color: #f59e0b; }
.badge.danger { background: rgba(239,68,68,0.1); color: #ef4444; }
.sev-row { display: flex; flex-wrap: wrap; gap: 8px; }
.sev-chip { padding: 4px 10px; border-radius: 14px; font-size: 0.78rem; font-weight: 600; }
.sev-critical { background: rgba(239,68,68,0.12); color: #ef4444; }
.sev-high { background: rgba(249,115,22,0.12); color: #f97316; }
.sev-warning, .sev-medium { background: rgba(245,158,11,0.12); color: #f59e0b; }
.sev-info, .sev-low { background: rgba(100,116,139,0.12); color: #64748b; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 16px; }
.summary-card { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; padding: 12px 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.summary-card.danger { border-left: 3px solid #ef4444; }
.summary-label { font-size: 0.72rem; color: var(--text-secondary, #64748b); text-transform: uppercase; letter-spacing: 0.3px; margin-bottom: 4px; }
.summary-value { font-size: 1.4rem; font-weight: 700; color: var(--text, #1e293b); }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 420px; max-height: 86vh; overflow-y: auto; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-lg { min-width: 820px; }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; color: var(--text, #1e293b); }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.detail-section { margin-bottom: 16px; }
.detail-section h4 { font-size: 0.85rem; font-weight: 600; margin: 0 0 8px; color: var(--text, #1e293b); }
.kv-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 6px; font-size: 0.82rem; }
.kv-label { color: var(--text-secondary, #64748b); }
.code-block { background: var(--bg-code, #1e293b); color: #e2e8f0; padding: 12px; border-radius: 6px; font-family: 'Consolas', monospace; font-size: 0.78rem; max-height: 280px; overflow: auto; white-space: pre-wrap; }
</style>