<template>
  <div class="topology-page">
    <div class="page-header">
      <h1>拓扑视图</h1>
      <p>资产关系网络可视化 · {{ headerHint }}</p>
    </div>

    <!-- Tab 切换 -->
    <div class="tab-bar">
      <button class="tab-btn" :class="{ active: activeTab === 'asset' }" @click="switchTab('asset')">
        <span class="tab-icon">🖼️</span> 资产拓扑
      </button>
      <button class="tab-btn" :class="{ active: activeTab === 'network' }" @click="switchTab('network')">
        <span class="tab-icon">🌐</span> 网络拓扑
        <span class="tab-sub">{{ networkMode === 'devices' ? '设备关系' : 'IP 网段' }}</span>
      </button>
      <button class="tab-btn" :class="{ active: activeTab === 'service' }" @click="switchTab('service')">
        <span class="tab-icon">🔗</span> 服务调用
        <span class="tab-sub">{{ svcTotalServices }} 服务</span>
      </button>
    </div>

    <!-- ============ Tab1: 资产拓扑（K8s 按节点维度） ============ -->
    <div v-show="activeTab === 'asset'">
      <div class="stat-row">
        <div class="stat-card">
          <div class="stat-num">{{ displayNodeCount }}</div>
          <div class="stat-label">{{ showAbnormalOnly ? '筛选中节点' : '节点数' }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-num">{{ displayEdgeCount }}</div>
          <div class="stat-label">{{ showAbnormalOnly ? '筛选中关系' : '关系数' }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-num">{{ abnormalCount }}</div>
          <div class="stat-label">异常节点</div>
        </div>
        <div class="stat-card stat-muted" v-if="k8sHiddenCount > 0">
          <div class="stat-num">{{ k8sHiddenCount }}</div>
          <div class="stat-label">已收敛 K8s 子资源</div>
        </div>
      </div>

      <div class="toolbar">
        <select v-model="typeFilter" class="input type-select" @change="renderChart">
          <option value="">全部类型</option>
          <option v-for="t in typeList" :key="t" :value="t">{{ t }}</option>
        </select>
        <input v-model="searchText" class="input" placeholder="搜索节点名称" @input="renderChart" />
        <button class="btn" :class="{ 'btn-abnormal': showAbnormalOnly }" @click="toggleAbnormalFilter">
          <span class="filter-dot"></span>
          仅异常
          <span v-if="showAbnormalOnly && abnormalCount" class="filter-badge">{{ abnormalCount }}</span>
        </button>
        <button class="btn btn-primary" @click="openCreate">+ 新增关系</button>
        <button class="btn" @click="loadAll">刷新</button>
        <button class="btn btn-guide" @click="showGuide = true">📖 操作说明</button>
        <label class="auto-refresh-label">
          <input type="checkbox" v-model="autoRefresh" style="accent-color:var(--accent)" />
          自动刷新
        </label>
      </div>

      <div class="content-grid">
        <div class="panel chart-panel">
          <div class="panel-head">拓扑图</div>
          <div class="panel-body">
            <div v-if="loading" class="loading-state">加载中...</div>
            <div ref="chartRef" class="chart-box"></div>
          </div>
        </div>

        <div class="panel legend-panel">
          <div class="panel-head">图例</div>
          <div class="panel-body">
            <div class="legend-section">节点类型</div>
            <div v-for="t in typeList" :key="t" class="legend-item">
              <span class="legend-dot" :style="{ background: typeColors[t] || typeColors.default }"></span>{{ t }}
            </div>
            <div class="legend-section">状态</div>
            <div class="legend-item"><span class="legend-dot status-normal"></span>正常（无边框）</div>
            <div class="legend-item"><span class="legend-dot status-abnormal"></span>异常（红色边框）</div>

            <div v-if="selectedNode" class="node-detail">
              <div class="legend-section">节点详情</div>
              <div class="detail-row"><span class="dlabel">名称</span><span class="dvalue">{{ selectedNode.name }}</span></div>
              <div class="detail-row"><span class="dlabel">类型</span><span class="dvalue">{{ selectedNode.ci_type || selectedNode.type || '-' }}</span></div>
              <div class="detail-row"><span class="dlabel">状态</span><span class="dvalue">{{ selectedNode.status || '-' }}</span></div>
              <div class="detail-row"><span class="dlabel">IP</span><span class="dvalue">{{ selectedNode.ip || '-' }}</span></div>
              <div class="detail-row"><span class="dlabel">ID</span><span class="dvalue">{{ selectedNode.id }}</span></div>
              <div v-if="connectedNodes.length" class="legend-section" style="margin-top:10px;">关联资产 ({{ connectedNodes.length }})</div>
              <div v-for="cn in connectedNodes" :key="cn.id" class="related-item">
                <span class="related-dot" :class="{ 'related-abnormal': isAbnormal(cn) }"></span>
                <span class="related-name">{{ cn.name }}</span>
                <span class="related-status">{{ cn.status || '-' }}</span>
              </div>
              <button class="btn btn-sm" @click="clearSelection" style="margin-top:8px;">关闭</button>
            </div>
          </div>
        </div>
      </div>

      <div class="panel" style="margin-top:14px;">
        <div class="panel-head">关系列表</div>
        <div class="panel-body">
          <table v-if="relations.length" class="table">
            <thead>
              <tr><th>ID</th><th>源节点</th><th>目标节点</th><th>关系类型</th><th>操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="r in relations" :key="r.id">
                <td>{{ r.id }}</td>
                <td>{{ nodeName(r.source_id) }}</td>
                <td>{{ nodeName(r.target_id) }}</td>
                <td><span class="badge rel-type">{{ r.relation_type }}</span></td>
                <td><button class="btn btn-sm btn-danger" @click="deleteRelation(r)">删除</button></td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">🕸️</div><div>暂无关系</div></div>
        </div>
      </div>
    </div>

    <!-- ============ Tab2: 网络拓扑 ============ -->
    <div v-show="activeTab === 'network'">
      <div class="toolbar">
        <div class="mode-switch">
          <button class="mode-btn" :class="{ active: networkMode === 'devices' }" @click="switchNetworkMode('devices')">📡 网络设备关系</button>
          <button class="mode-btn" :class="{ active: networkMode === 'subnets' }" @click="switchNetworkMode('subnets')">🗂️ IP 网段拓扑</button>
        </div>
        <button class="btn" @click="loadNetwork">刷新</button>
        <button class="btn btn-guide" @click="showGuide = true">📖 操作说明</button>
        <label class="auto-refresh-label">
          <input type="checkbox" v-model="autoRefresh" style="accent-color:var(--accent)" />
          自动刷新
        </label>
      </div>

      <div class="stat-row">
        <div class="stat-card">
          <div class="stat-num">{{ networkStats.total || 0 }}</div>
          <div class="stat-label">{{ networkMode === 'devices' ? '网络设备数' : '总节点数' }}</div>
        </div>
        <div class="stat-card" v-if="networkMode === 'devices'">
          <div class="stat-num">{{ networkStats.edge_count || 0 }}</div>
          <div class="stat-label">连接关系数</div>
        </div>
        <div class="stat-card" v-if="networkMode === 'devices'">
          <div class="stat-num">{{ networkStats.abnormal_count || 0 }}</div>
          <div class="stat-label">异常设备</div>
        </div>
        <div class="stat-card" v-if="networkMode === 'subnets'">
          <div class="stat-num">{{ networkStats.subnet_count || 0 }}</div>
          <div class="stat-label">网段数</div>
        </div>
        <div class="stat-card" v-if="networkMode === 'subnets'">
          <div class="stat-num">{{ networkStats.asset_count || 0 }}</div>
          <div class="stat-label">资产数</div>
        </div>
      </div>

      <div class="content-grid">
        <div class="panel chart-panel">
          <div class="panel-head">{{ networkMode === 'devices' ? '网络设备关系拓扑' : 'IP 网段拓扑' }}</div>
          <div class="panel-body">
            <div v-if="networkLoading" class="loading-state">加载中...</div>
            <div v-if="networkError" class="loading-state" style="color:#ef4444">{{ networkError }}</div>
            <div ref="networkChartRef" class="chart-box"></div>
          </div>
        </div>

        <div class="panel legend-panel">
          <div class="panel-head">图例</div>
          <div class="panel-body">
            <template v-if="networkMode === 'devices'">
              <div class="legend-section">设备类型</div>
              <div v-for="t in networkTypeList" :key="t" class="legend-item">
                <span class="legend-dot" :style="{ background: networkTypeColors[t] || networkTypeColors.default }"></span>{{ t }}
              </div>
              <div class="legend-section">连接关系</div>
              <div class="legend-item"><span class="legend-line"></span>depends / 连接</div>
              <div class="legend-item"><span class="legend-dot status-abnormal"></span>异常设备</div>
            </template>
            <template v-else>
              <div class="legend-section">节点类型</div>
              <div class="legend-item"><span class="legend-dot subnet-dot"></span>网段 (/24)</div>
              <div class="legend-item"><span class="legend-dot" style="background:#3b82f6"></span>资产</div>
              <div class="legend-section">说明</div>
              <div class="legend-item" style="font-size:0.75rem;color:var(--text-secondary,#64748b);align-items:flex-start">
                按资产 IP 的 /24 网段自动聚类，网段为父节点，资产为叶子。
              </div>
            </template>

            <div v-if="selectedNetworkNode" class="node-detail">
              <div class="legend-section">节点详情</div>
              <div class="detail-row"><span class="dlabel">名称</span><span class="dvalue">{{ selectedNetworkNode.name }}</span></div>
              <div class="detail-row"><span class="dlabel">类型</span><span class="dvalue">{{ networkNodeLabel(selectedNetworkNode) }}</span></div>
              <div class="detail-row" v-if="selectedNetworkNode.ip"><span class="dlabel">IP</span><span class="dvalue">{{ selectedNetworkNode.ip }}</span></div>
              <div class="detail-row" v-if="selectedNetworkNode.status"><span class="dlabel">状态</span><span class="dvalue">{{ selectedNetworkNode.status }}</span></div>
              <div class="detail-row" v-if="selectedNetworkNode.is_subnet"><span class="dlabel">资产数</span><span class="dvalue">{{ selectedNetworkNode.item_count }}</span></div>
              <button class="btn btn-sm" @click="clearNetworkSelection" style="margin-top:8px;">关闭</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ============ Tab3: 服务调用拓扑 ============ -->
    <div v-show="activeTab === 'service'">
      <div class="toolbar">
        <div class="mode-switch">
          <button class="mode-btn" :class="{ active: svcHours === 1 }" @click="svcHours = 1; loadServiceCalls()">1h</button>
          <button class="mode-btn" :class="{ active: svcHours === 6 }" @click="svcHours = 6; loadServiceCalls()">6h</button>
          <button class="mode-btn" :class="{ active: svcHours === 24 }" @click="svcHours = 24; loadServiceCalls()">24h</button>
          <button class="mode-btn" :class="{ active: svcHours === 168 }" @click="svcHours = 168; loadServiceCalls()">7d</button>
          <button class="mode-btn" :class="{ active: svcHours === 0 }" @click="svcHours = 0; loadServiceCalls()">全部</button>
        </div>
        <button class="btn" @click="loadServiceCalls">刷新</button>
        <button class="btn btn-guide" @click="showGuide = true">📖 操作说明</button>
        <label class="auto-refresh-label">
          <input type="checkbox" v-model="autoRefresh" style="accent-color:var(--accent)" />
          自动刷新
        </label>
      </div>

      <div class="stat-row">
        <div class="stat-card">
          <div class="stat-num">{{ svcStats.total_services || 0 }}</div>
          <div class="stat-label">服务数</div>
        </div>
        <div class="stat-card">
          <div class="stat-num">{{ svcStats.total_edges || 0 }}</div>
          <div class="stat-label">调用关系</div>
        </div>
        <div class="stat-card">
          <div class="stat-num">{{ svcStats.total_calls || 0 }}</div>
          <div class="stat-label">总调用次数</div>
        </div>
        <div class="stat-card">
          <div class="stat-num">{{ svcStats.total_spans || 0 }}</div>
          <div class="stat-label">Span 数</div>
        </div>
      </div>

      <div class="content-grid">
        <div class="panel chart-panel">
          <div class="panel-head">服务调用拓扑图</div>
          <div class="panel-body">
            <div v-if="svcLoading" class="loading-state">加载中...</div>
            <div v-if="svcError" class="loading-state" style="color:#ef4444">{{ svcError }}</div>
            <div v-if="svcEmpty" class="empty-state">
              <div style="font-size:32px;margin-bottom:8px;">🔗</div>
              <div>暂无跨服务调用数据</div>
              <div style="font-size:0.8rem;margin-top:8px;color:var(--text-tertiary,#94a3b8)">
                需要应用通过 OpenTelemetry 上报含 parent_span_id 的跨服务 Span
              </div>
            </div>
            <div ref="svcChartRef" class="chart-box" v-show="!svcLoading && !svcEmpty"></div>
          </div>
        </div>

        <div class="panel legend-panel">
          <div class="panel-head">图例 / 节点详情</div>
          <div class="panel-body">
            <div class="legend-section">服务健康状态</div>
            <div class="legend-item"><span class="health-dot" style="background:#67C23A"></span>健康 (错误率 &lt; 5%)</div>
            <div class="legend-item"><span class="health-dot" style="background:#E6A23C"></span>警告 (错误率 5% ~ 30%)</div>
            <div class="legend-item"><span class="health-dot" style="background:#ef4444"></span>严重 (错误率 ≥ 30%)</div>
            <div class="legend-section">调用关系</div>
            <div class="legend-item"><span class="legend-line"></span>service_call (带箭头)</div>
            <div class="legend-item" style="font-size:0.75rem;color:var(--text-tertiary,#94a3b8);align-items:flex-start">
              边宽度 = 调用量, 颜色 = 错误率
            </div>

            <div v-if="selectedSvcNode" class="node-detail">
              <div class="legend-section">服务详情</div>
              <div class="detail-row"><span class="dlabel">服务名</span><span class="dvalue">{{ selectedSvcNode.name }}</span></div>
              <div class="detail-row"><span class="dlabel">Span 数</span><span class="dvalue">{{ selectedSvcNode.span_count }}</span></div>
              <div class="detail-row"><span class="dlabel">调用次数</span><span class="dvalue">{{ selectedSvcNode.call_count }}</span></div>
              <div class="detail-row"><span class="dlabel">错误数</span><span class="dvalue">{{ selectedSvcNode.error_count }}</span></div>
              <div class="detail-row"><span class="dlabel">错误率</span><span class="dvalue">{{ selectedSvcNode.error_rate }}%</span></div>
              <div class="detail-row"><span class="dlabel">平均耗时</span><span class="dvalue">{{ selectedSvcNode.avg_duration_ms }}ms</span></div>
              <div class="detail-row"><span class="dlabel">健康状态</span>
                <span class="dvalue">
                  <span class="health-badge" :class="'health-' + selectedSvcNode.health">{{ selectedSvcNode.health }}</span>
                </span>
              </div>
              <button class="btn btn-sm" @click="clearSvcSelection" style="margin-top:8px;">关闭</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 新增关系弹窗 -->
    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal-box">
        <h3>新增关系</h3>
        <div class="form-row"><label>源节点</label>
          <select v-model="createForm.source_id" class="input">
            <option v-for="n in nodes" :key="n.id" :value="n.id">{{ n.name }} ({{ n.ci_type || n.type || '-' }})</option>
          </select>
        </div>
        <div class="form-row"><label>目标节点</label>
          <select v-model="createForm.target_id" class="input">
            <option v-for="n in nodes" :key="n.id" :value="n.id">{{ n.name }} ({{ n.ci_type || n.type || '-' }})</option>
          </select>
        </div>
        <div class="form-row"><label>关系类型</label><input v-model="createForm.relation_type" class="input" placeholder="如: depends_on"></div>
        <div class="modal-actions">
          <button class="btn" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" @click="createRelation">确认</button>
        </div>
      </div>
    </div>
    <GuideDrawer v-model:visible="showGuide" title="拓扑视图操作说明" :sections="guideSections" />
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick, computed, watch } from 'vue'
import * as echarts from 'echarts'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'
import GuideDrawer from '@/components/GuideDrawer.vue'

// ===== Tab 状态 =====
const activeTab = ref('asset')
const networkMode = ref('devices')

// ===== Tab1: 资产拓扑 =====
const loading = ref(false)
const nodes = ref([])
const relations = ref([])
const selectedNode = ref(null)
const selectedNodeId = ref(null)
const showAbnormalOnly = ref(false)
const showCreate = ref(false)
const createForm = ref({ source_id: 0, target_id: 0, relation_type: 'depends_on' })
const showGuide = ref(false)
const typeFilter = ref('')
const searchText = ref('')
const k8sHiddenCount = ref(0)

const chartRef = ref(null)
let chart = null

const typeColors = {
  host: '#3b82f6',
  server: '#3b82f6',
  vm: '#06b6d4',
  virtual_machine: '#06b6d4',
  cloud_host: '#0ea5e9',
  service: '#8b5cf6',
  database: '#f59e0b',
  middleware: '#f97316',
  network: '#10b981',
  network_device: '#10b981',
  switch: '#14b8a6',
  router: '#0ea5e9',
  firewall: '#ef4444',
  loadbalancer: '#ec4899',
  load_balancer: '#ec4899',
  storage: '#64748b',
  storage_device: '#64748b',
  kubernetes_cluster: '#6366f1',
  cluster: '#6366f1',
  namespace: '#3b82f6',
  node: '#10b981',
  deployment: '#f59e0b',
  statefulset: '#f97316',
  daemonset: '#ea580c',
  pod: '#14b8a6',
  ingress: '#ec4899',
  pvc: '#64748b',
  pv: '#475569',
  configmap: '#06b6d4',
  secret: '#dc2626',
  default: '#909399',
}

function nodeColor(n) {
  const t = (n.ci_type || n.type || '').toLowerCase()
  return typeColors[t] || typeColors.default
}

function isAbnormal(n) {
  const s = (n.status || '').toLowerCase()
  return s === 'offline' || s === 'error' || s === 'critical' || s === 'down'
}

const abnormalCount = computed(() => nodes.value.filter(isAbnormal).length)

const typeList = computed(() => {
  const types = new Set(nodes.value.map(n => (n.ci_type || n.type || '')).filter(Boolean))
  return [...types].sort()
})

const guideSections = [
  { title: 'Tab 切换', content: '「资产拓扑」展示全资产关系，K8s 仅按节点维度呈现；「网络拓扑」展示网络设备关系或 IP 网段聚类；「服务调用」从链路追踪 Span 数据自动聚合服务间调用关系。' },
  { title: '筛选过滤', content: '资产拓扑支持类型下拉筛选、名称搜索、"仅异常"过滤（显示异常节点及其关联）。' },
  { title: '节点交互', content: '点击任一节点，右侧图例区显示详情和关联资产；选中节点高亮其所有关联关系。' },
  { title: '拓扑浏览', content: '节点可拖拽移动；鼠标滚轮缩放；选中节点后关联节点和边高亮。' },
  { title: '关系管理', content: '点击"+新增关系"创建资产间依赖关系；关系列表支持直接删除。' },
  { title: '网络拓扑模式', content: '网络设备关系：展示交换机/路由器/防火墙/负载均衡等网络设备及 AssetRelation 连接；IP 网段拓扑：按 /24 网段自动聚类有 IP 的资产。' },
  { title: '服务调用拓扑', content: '从 OpenTelemetry Span 表自动聚合跨服务调用关系（基于 trace_id + parent_span_id）。节点颜色=健康状态，边宽度=调用量，边颜色=错误率。支持 1h/6h/24h/7d/全部 时间范围切换。' },
  { title: '自动刷新', content: '开启"自动刷新"后每 30 秒拉取当前 Tab 的最新拓扑数据。' },
]

const connectedNodes = computed(() => {
  if (!selectedNode.value) return []
  const neighborIds = new Set()
  relations.value.forEach(r => {
    if (r.source_id === selectedNode.value.id) neighborIds.add(r.target_id)
    if (r.target_id === selectedNode.value.id) neighborIds.add(r.source_id)
  })
  return nodes.value.filter(n => neighborIds.has(n.id))
})

function toggleAbnormalFilter() {
  showAbnormalOnly.value = !showAbnormalOnly.value
  renderChart()
}

function clearSelection() {
  selectedNode.value = null
  selectedNodeId.value = null
  renderChart()
}

function isConnectedTo(id, targetId) {
  return relations.value.some(r =>
    (r.source_id === id && r.target_id === targetId) ||
    (r.source_id === targetId && r.target_id === id)
  )
}

function getDisplayData() {
  let dn = nodes.value
  let de = relations.value
  if (typeFilter.value) {
    const typeVal = typeFilter.value.toLowerCase()
    dn = dn.filter(n => (n.ci_type || n.type || '').toLowerCase() === typeVal)
  }
  if (searchText.value) {
    const q = searchText.value.toLowerCase()
    dn = dn.filter(n => (n.name || '').toLowerCase().includes(q))
  }
  if (typeFilter.value || searchText.value) {
    const keepIds = new Set(dn.map(n => n.id))
    de = de.filter(r => keepIds.has(r.source_id) && keepIds.has(r.target_id))
  }
  if (showAbnormalOnly.value) {
    const abnormalIds = new Set(dn.filter(isAbnormal).map(n => n.id))
    const connectedIds = new Set()
    de.forEach(r => {
      if (abnormalIds.has(r.source_id)) connectedIds.add(r.target_id)
      if (abnormalIds.has(r.target_id)) connectedIds.add(r.source_id)
    })
    const keepIds = new Set([...abnormalIds, ...connectedIds])
    dn = dn.filter(n => keepIds.has(n.id))
    de = de.filter(r => keepIds.has(r.source_id) && keepIds.has(r.target_id))
  }
  return { displayNodes: dn, displayEdges: de }
}

const displayNodeCount = computed(() => getDisplayData().displayNodes.length)
const displayEdgeCount = computed(() => getDisplayData().displayEdges.length)

const headerHint = computed(() => {
  if (activeTab.value === 'network') {
    return networkMode.value === 'devices' ? '网络设备关系拓扑' : 'IP 网段聚类拓扑'
  }
  if (activeTab.value === 'service') {
    return `服务调用拓扑 · ${svcStats.value.total_services || 0} 服务 · ${svcStats.value.total_edges || 0} 调用关系`
  }
  return `${nodes.value.length} 个节点 / ${relations.value.length} 条关系`
})

function nodeName(id) {
  const n = nodes.value.find(x => x.id === id)
  return n ? n.name : `#${id}`
}

async function loadAll() {
  loading.value = true
  try {
    const data = await request.get('/topology/api/asset-by-node')
    nodes.value = data.nodes || []
    relations.value = data.relations || data.edges || []
    k8sHiddenCount.value = data.stats?.k8s_hidden || 0
    await nextTick()
    renderChart()
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

function renderChart() {
  if (!chartRef.value) return
  if (!chart) chart = echarts.init(chartRef.value)
  const { displayNodes, displayEdges } = getDisplayData()
  const presentTypes = new Set(displayNodes.map(n => (n.ci_type || n.type || '').toLowerCase()).filter(Boolean))
  const categories = Object.keys(typeColors).filter(k => k !== 'default' && presentTypes.has(k))
  const graphNodes = displayNodes.map(n => {
    const abnormal = isAbnormal(n)
    const selected = selectedNodeId.value === n.id
    const connected = selectedNodeId.value && selectedNodeId.value !== n.id && isConnectedTo(n.id, selectedNodeId.value)
    const emph = showAbnormalOnly.value && abnormal
    return {
      id: String(n.id),
      name: n.name,
      symbolSize: emph ? 48 : (selected || connected ? 44 : 38),
      category: categories.indexOf((n.ci_type || n.type || '').toLowerCase()) >= 0
        ? (n.ci_type || n.type || '').toLowerCase() : 'default',
      itemStyle: {
        color: nodeColor(n),
        borderColor: abnormal ? '#ef4444' : (connected ? '#f59e0b' : 'transparent'),
        borderWidth: emph ? 5 : (abnormal ? 3 : (connected ? 3 : 0)),
        shadowBlur: emph ? 12 : 0,
        shadowColor: 'rgba(239,68,68,0.45)',
      },
      label: { show: true, position: 'bottom', fontSize: emph ? 11 : 10 },
      raw: n,
    }
  })
  const graphEdges = displayEdges.map(r => {
    const connected = selectedNodeId.value && (
      r.source_id === selectedNodeId.value || r.target_id === selectedNodeId.value
    )
    return {
      source: String(r.source_id),
      target: String(r.target_id),
      label: { show: false, formatter: r.relation_type, fontSize: 9 },
      lineStyle: connected
        ? { color: '#f59e0b', width: 3, curveness: 0.1 }
        : { color: '#aaa', curveness: 0.1 },
    }
  })
  chart.setOption({
    tooltip: {
      formatter: (p) => {
        if (p.dataType === 'node') {
          const n = p.data.raw
          return `<b>${n.name}</b><br/>类型: ${n.ci_type || n.type || '-'}<br/>状态: ${n.status || '-'}<br/>IP: ${n.ip || '-'}`
        }
        if (p.dataType === 'edge') {
          return `${nodeName(Number(p.data.source))} → ${nodeName(Number(p.data.target))}`
        }
        return ''
      },
    },
    legend: [{ data: categories, bottom: 0, textStyle: { fontSize: 10 } }],
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      data: graphNodes,
      links: graphEdges,
      categories: categories.map(c => ({ name: c })),
      force: { repulsion: 350, edgeLength: 180, gravity: 0.05, friction: 0.15 },
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: 8,
      lineStyle: { color: '#aaa', curveness: 0.1 },
      emphasis: { focus: 'adjacency', lineStyle: { width: 3 } },
    }],
  }, true)
  chart.off('click')
  chart.on('click', (p) => {
    if (p.dataType === 'node' && p.data.raw) {
      selectedNode.value = p.data.raw
      selectedNodeId.value = p.data.raw.id
      renderChart()
    }
  })
}

function openCreate() {
  if (!nodes.value.length) {
    ElMessage.warning('暂无节点可建立关系')
    return
  }
  createForm.value = {
    source_id: nodes.value[0].id,
    target_id: nodes.value[1]?.id || nodes.value[0].id,
    relation_type: 'depends_on',
  }
  showCreate.value = true
}

async function createRelation() {
  if (!createForm.value.source_id || !createForm.value.target_id) {
    ElMessage.warning('请选择源节点和目标节点')
    return
  }
  if (createForm.value.source_id === createForm.value.target_id) {
    ElMessage.warning('源节点与目标节点不能相同')
    return
  }
  try {
    const data = await request.post('/topology/api/relations/create', createForm.value)
    if (data.ok === false) {
      ElMessage.error(data.error || '创建失败')
      return
    }
    ElMessage.success('关系已创建')
    showCreate.value = false
    loadAll()
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.message || e))
  }
}

async function deleteRelation(r) {
  try {
    await ElMessageBox.confirm(
      `确认删除关系「${nodeName(r.source_id)} → ${nodeName(r.target_id)}」?`,
      '删除确认',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    const data = await request.post(`/topology/api/relations/${r.id}/delete`)
    if (data.ok === false) {
      ElMessage.error(data.error || '删除失败')
      return
    }
    ElMessage.success('已删除')
    loadAll()
  } catch (e) {
    ElMessage.error('删除失败: ' + (e.message || e))
  }
}

// ===== Tab2: 网络拓扑 =====
const networkLoading = ref(false)
const networkError = ref('')
const networkNodes = ref([])
const networkEdges = ref([])
const networkStats = ref({})
const selectedNetworkNode = ref(null)
const selectedNetworkNodeId = ref(null)

const networkChartRef = ref(null)
let networkChart = null

const networkTypeColors = {
  network: '#10b981',
  network_device: '#10b981',
  switch: '#14b8a6',
  router: '#0ea5e9',
  firewall: '#ef4444',
  loadbalancer: '#ec4899',
  load_balancer: '#ec4899',
  storage: '#64748b',
  storage_device: '#64748b',
  subnet: '#6366f1',
  default: '#909399',
}

function networkNodeColor(n) {
  const t = (n.ci_type || '').toLowerCase()
  return networkTypeColors[t] || networkTypeColors.default
}

function networkNodeLabel(n) {
  if (n.is_subnet) return '网段 (/24)'
  return n.ci_type || '-'
}

function networkNodeAbnormal(n) {
  if (n.is_subnet) return false
  const s = (n.status || '').toLowerCase()
  return s === 'offline' || s === 'error' || s === 'critical' || s === 'down'
}

const networkTypeList = computed(() => {
  const types = new Set(networkNodes.value.map(n => (n.ci_type || '').toLowerCase()).filter(Boolean))
  return [...types].sort()
})

async function loadNetwork() {
  networkLoading.value = true
  networkError.value = ''
  try {
    const data = await request.get(`/topology/api/network?mode=${networkMode.value}`)
    networkNodes.value = data.nodes || []
    networkEdges.value = data.relations || data.edges || []
    networkStats.value = data.stats || {}
    await nextTick()
    renderNetworkChart()
  } catch (e) {
    networkError.value = '加载失败: ' + (e.message || e)
  } finally {
    networkLoading.value = false
  }
}

function renderNetworkChart() {
  if (!networkChartRef.value) return
  if (!networkChart) networkChart = echarts.init(networkChartRef.value)

  const graphNodes = networkNodes.value.map(n => {
    const isSubnet = !!n.is_subnet
    const abnormal = networkNodeAbnormal(n)
    const selected = selectedNetworkNodeId.value === n.id
    return {
      id: String(n.id),
      name: isSubnet ? `${n.name} (${n.item_count})` : n.name,
      symbolSize: isSubnet ? 56 : (selected ? 44 : 36),
      symbol: isSubnet ? 'roundRect' : 'circle',
      itemStyle: {
        color: isSubnet ? networkTypeColors.subnet : (networkMode.value === 'subnets' ? '#3b82f6' : networkNodeColor(n)),
        borderColor: abnormal ? '#ef4444' : (selected ? '#f59e0b' : 'transparent'),
        borderWidth: abnormal ? 3 : (selected ? 3 : 0),
        shadowBlur: abnormal ? 12 : 0,
        shadowColor: 'rgba(239,68,68,0.45)',
      },
      label: {
        show: true,
        position: isSubnet ? 'inside' : 'bottom',
        fontSize: isSubnet ? 11 : 10,
        color: isSubnet ? '#fff' : 'inherit',
        fontWeight: isSubnet ? 600 : 400,
      },
      raw: n,
    }
  })
  const graphEdges = networkEdges.value.map(r => {
    const connected = selectedNetworkNodeId.value && (
      r.source_id === selectedNetworkNodeId.value || r.target_id === selectedNetworkNodeId.value
    )
    return {
      source: String(r.source_id),
      target: String(r.target_id),
      label: { show: false, formatter: r.relation_type, fontSize: 9 },
      lineStyle: connected
        ? { color: '#f59e0b', width: 3, curveness: 0.1 }
        : { color: '#94a3b8', curveness: 0.15 },
    }
  })

  const presentNetTypes = new Set(networkNodes.value.map(n => (n.ci_type || '').toLowerCase()).filter(Boolean))
  const categories = networkMode.value === 'subnets'
    ? ['subnet']
    : Object.keys(networkTypeColors).filter(k => k !== 'default' && presentNetTypes.has(k))

  networkChart.setOption({
    tooltip: {
      formatter: (p) => {
        if (p.dataType === 'node') {
          const n = p.data.raw
          if (n.is_subnet) return `<b>网段 ${n.name}</b><br/>资产数: ${n.item_count}`
          return `<b>${n.name}</b><br/>类型: ${n.ci_type || '-'}<br/>状态: ${n.status || '-'}<br/>IP: ${n.ip || '-'}`
        }
        if (p.dataType === 'edge') {
          const sn = networkNodes.value.find(x => x.id === Number(p.data.source))
          const tn = networkNodes.value.find(x => x.id === Number(p.data.target))
          return `${sn ? sn.name : '#'+p.data.source} → ${tn ? tn.name : '#'+p.data.target}`
        }
        return ''
      },
    },
    legend: networkMode.value === 'subnets' ? { show: false } : [{ data: categories, bottom: 0, textStyle: { fontSize: 10 } }],
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      data: graphNodes,
      links: graphEdges,
      categories: categories.map(c => ({ name: c })),
      force: { repulsion: 400, edgeLength: 160, gravity: 0.04, friction: 0.15 },
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: 8,
      lineStyle: { color: '#94a3b8', curveness: 0.15 },
      emphasis: { focus: 'adjacency', lineStyle: { width: 3 } },
    }],
  }, true)
  networkChart.off('click')
  networkChart.on('click', (p) => {
    if (p.dataType === 'node' && p.data.raw) {
      selectedNetworkNode.value = p.data.raw
      selectedNetworkNodeId.value = p.data.raw.id
      renderNetworkChart()
    }
  })
}

function clearNetworkSelection() {
  selectedNetworkNode.value = null
  selectedNetworkNodeId.value = null
  renderNetworkChart()
}

// ===== Tab3: 服务调用拓扑 =====
const svcLoading = ref(false)
const svcError = ref('')
const svcEmpty = ref(false)
const svcNodes = ref([])
const svcEdges = ref([])
const svcStats = ref({})
const svcHours = ref(24)
const selectedSvcNode = ref(null)
const selectedSvcNodeId = ref(null)
const svcChartRef = ref(null)
let svcChart = null

const svcTotalServices = computed(() => svcStats.value.total_services || 0)

function svcNodeColor(n) {
  if (n.health === 'critical') return '#ef4444'
  if (n.health === 'warning') return '#E6A23C'
  return '#67C23A'
}

function svcEdgeColor(e) {
  const er = e.error_rate || 0
  if (er >= 30) return '#ef4444'
  if (er >= 5) return '#E6A23C'
  return '#94a3b8'
}

async function loadServiceCalls() {
  svcLoading.value = true
  svcError.value = ''
  svcEmpty.value = false
  try {
    const data = await request.get(`/topology/api/service-calls?hours=${svcHours.value}&min_calls=1`)
    svcNodes.value = data.nodes || []
    svcEdges.value = data.edges || []
    svcStats.value = data.stats || {}
    svcEmpty.value = svcNodes.value.length === 0
    await nextTick()
    if (!svcEmpty.value) renderServiceChart()
  } catch (e) {
    svcError.value = '加载失败: ' + (e.message || e)
  } finally {
    svcLoading.value = false
  }
}

function renderServiceChart() {
  if (!svcChartRef.value) return
  if (!svcChart) svcChart = echarts.init(svcChartRef.value)

  const nodeMap = {}
  svcNodes.value.forEach(n => { nodeMap[n.id] = n })

  const graphNodes = svcNodes.value.map(n => {
    const selected = selectedSvcNodeId.value === n.id
    const color = svcNodeColor(n)
    return {
      id: n.id,
      name: n.name,
      symbolSize: selected ? 56 : 48,
      itemStyle: {
        color: color,
        borderColor: selected ? '#6366f1' : 'transparent',
        borderWidth: selected ? 3 : 0,
        shadowBlur: selected ? 12 : 0,
        shadowColor: 'rgba(99,102,241,0.45)',
      },
      label: { show: true, position: 'bottom', fontSize: 12, fontWeight: selected ? 600 : 400 },
      raw: n,
    }
  })
  const maxCalls = Math.max(...svcEdges.value.map(e => e.call_count), 1)
  const graphEdges = svcEdges.value.map(e => {
    const connected = selectedSvcNodeId.value && (
      e.source === selectedSvcNodeId.value || e.target === selectedSvcNodeId.value
    )
    const width = 1 + (e.call_count / maxCalls) * 5
    return {
      source: e.source,
      target: e.target,
      label: { show: true, formatter: `${e.call_count}次`, fontSize: 9 },
      lineStyle: {
        color: connected ? '#6366f1' : svcEdgeColor(e),
        width: connected ? Math.max(width, 3) : width,
        curveness: 0.15,
        opacity: connected ? 1 : 0.7,
      },
    }
  })

  svcChart.setOption({
    tooltip: {
      formatter: (p) => {
        if (p.dataType === 'node') {
          const n = p.data.raw
          return `<b>${n.name}</b><br/>Span: ${n.span_count} | 调用: ${n.call_count}<br/>错误: ${n.error_count} (${n.error_rate}%)<br/>平均耗时: ${n.avg_duration_ms}ms<br/>健康: ${n.health}`
        }
        if (p.dataType === 'edge') {
          const e = p.data
          return `<b>${e.source} → ${e.target}</b><br/>调用 ${e.call_count} 次, 错误 ${e.error_count} 次 (${e.error_rate}%)<br/>平均耗时: ${e.avg_duration_ms}ms`
        }
        return ''
      },
    },
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      data: graphNodes,
      links: graphEdges,
      categories: [{ name: 'service' }],
      force: { repulsion: 500, edgeLength: 250, gravity: 0.03, friction: 0.12 },
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: 10,
      emphasis: { focus: 'adjacency', lineStyle: { width: 4 } },
    }],
  }, true)
  svcChart.off('click')
  svcChart.on('click', (p) => {
    if (p.dataType === 'node' && p.data.raw) {
      selectedSvcNode.value = p.data.raw
      selectedSvcNodeId.value = p.data.raw.id
      renderServiceChart()
    }
  })
}

function clearSvcSelection() {
  selectedSvcNode.value = null
  selectedSvcNodeId.value = null
  renderServiceChart()
}

function switchTab(tab) {
  activeTab.value = tab
  nextTick(() => {
    if (tab === 'asset') {
      if (chart) chart.resize()
    } else if (tab === 'network') {
      if (!networkNodes.value.length) loadNetwork()
      else if (networkChart) networkChart.resize()
    } else if (tab === 'service') {
      if (!svcNodes.value.length) loadServiceCalls()
      else if (svcChart) svcChart.resize()
    }
  })
}

function switchNetworkMode(mode) {
  if (networkMode.value === mode) return
  networkMode.value = mode
  selectedNetworkNode.value = null
  selectedNetworkNodeId.value = null
  loadNetwork()
}

// ===== 自动刷新 =====
const autoRefresh = ref(false)
let refreshTimer = null
watch(autoRefresh, (val) => {
  if (refreshTimer) clearInterval(refreshTimer)
  if (val) {
    refreshTimer = setInterval(() => {
      if (activeTab.value === 'asset') loadAll()
      else if (activeTab.value === 'network') loadNetwork()
      else loadServiceCalls()
    }, 30000)
  }
})

function handleResize() {
  if (chart) chart.resize()
  if (networkChart) networkChart.resize()
  if (svcChart) svcChart.resize()
}

onMounted(() => {
  loadAll()
  window.addEventListener('resize', handleResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (refreshTimer) clearInterval(refreshTimer)
  if (chart) { chart.dispose(); chart = null }
  if (networkChart) { networkChart.dispose(); networkChart = null }
  if (svcChart) { svcChart.dispose(); svcChart = null }
})
</script>

<style scoped>
.topology-page { padding: 4px; }
.page-header { margin-bottom: 12px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }

/* Tab 切换条 */
.tab-bar { display: flex; gap: 6px; margin-bottom: 16px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); padding-bottom: 0; }
.tab-btn { display: flex; align-items: center; gap: 6px; padding: 8px 18px; border: 1px solid transparent; border-bottom: none; border-radius: 8px 8px 0 0; background: transparent; color: var(--text-secondary, #64748b); cursor: pointer; font-size: 0.88rem; font-weight: 500; position: relative; top: 1px; }
.tab-btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); color: var(--text, #1e293b); }
.tab-btn.active { background: var(--bg-card, #fff); color: var(--accent, #6366f1); border-color: var(--border, rgba(0,0,0,0.07)); font-weight: 600; box-shadow: 0 -2px 0 var(--accent, #6366f1) inset; }
.tab-icon { font-size: 1rem; }
.tab-sub { font-size: 0.7rem; color: var(--text-tertiary, #94a3b8); font-weight: 400; }
.tab-btn.active .tab-sub { color: var(--accent, #6366f1); }

/* 模式切换 */
.mode-switch { display: inline-flex; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; overflow: hidden; }
.mode-btn { padding: 6px 14px; border: none; background: var(--bg-card-solid, #fff); color: var(--text-secondary, #64748b); cursor: pointer; font-size: 0.82rem; }
.mode-btn:not(:last-child) { border-right: 1px solid var(--border-strong, rgba(0,0,0,0.12)); }
.mode-btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); color: var(--text, #1e293b); }
.mode-btn.active { background: var(--accent, #6366f1); color: #fff; }

.stat-row { display: flex; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.stat-card { flex: 1; min-width: 120px; background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.stat-muted { opacity: 0.75; }
.stat-num { font-size: 1.5rem; font-weight: 700; color: var(--accent, #6366f1); }
.stat-label { font-size: 0.75rem; color: var(--text-secondary, #64748b); margin-top: 2px; }
.toolbar { display: flex; gap: 8px; margin-bottom: 14px; align-items: center; flex-wrap: wrap; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.btn-guide { background: rgba(99,102,241,0.08); color: var(--accent, #6366f1); border-color: rgba(99,102,241,0.2); }
.auto-refresh-label { display: inline-flex; align-items: center; gap: 4px; font-size: 0.75rem; cursor: pointer; color: var(--text-secondary, #64748b); margin-left: 8px; }
.content-grid { display: grid; grid-template-columns: 1fr 280px; gap: 14px; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); }
.panel-body { padding: 16px 18px; }
.chart-box { width: 100%; height: 600px; }
.legend-section { font-size: 0.78rem; font-weight: 600; color: var(--text-secondary, #64748b); margin: 10px 0 6px; text-transform: uppercase; letter-spacing: 0.3px; }
.legend-section:first-child { margin-top: 0; }
.legend-item { display: flex; align-items: center; gap: 8px; font-size: 0.82rem; color: var(--text, #1e293b); padding: 3px 0; }
.legend-dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; flex-shrink: 0; }
.legend-dot.subnet-dot { background: #6366f1; border-radius: 3px; }
.legend-dot.green { background: #67C23A; }
.legend-dot.status-normal { background: #ccc; border: 2px dashed #aaa; }
.legend-dot.status-abnormal { background: #fff; border: 2px solid #ef4444; }
.legend-line { width: 18px; height: 2px; background: #94a3b8; display: inline-block; flex-shrink: 0; }
.node-detail { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border, rgba(0,0,0,0.07)); }
.detail-row { display: flex; justify-content: space-between; font-size: 0.8rem; padding: 3px 0; }
.dlabel { color: var(--text-secondary, #64748b); }
.dvalue { color: var(--text, #1e293b); font-weight: 500; word-break: break-all; text-align: right; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.badge.rel-type { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.72rem; font-weight: 600; background: rgba(99,102,241,0.1); color: var(--accent, #6366f1); }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 380px; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; color: var(--text, #1e293b); }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.btn-abnormal { background: rgba(239,68,68,0.12); color: #ef4444; border-color: rgba(239,68,68,0.35); }
.type-select { max-width: 160px; }
.btn-abnormal:hover { background: rgba(239,68,68,0.22); }
.filter-dot { width: 8px; height: 8px; border-radius: 50%; background: #ef4444; display: inline-block; margin-right: 4px; }
.filter-badge { background: #ef4444; color: #fff; border-radius: 8px; padding: 0 6px; font-size: 0.7rem; font-weight: 700; line-height: 1.5; margin-left: 4px; }
.related-item { display: flex; align-items: center; gap: 6px; font-size: 0.8rem; padding: 3px 0; }
.related-dot { width: 8px; height: 8px; border-radius: 50%; background: #94a3b8; flex-shrink: 0; }
.related-dot.related-abnormal { background: #ef4444; box-shadow: 0 0 4px rgba(239,68,68,0.5); }
.related-name { color: var(--text, #1e293b); font-weight: 500; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.related-status { color: var(--text-secondary, #64748b); font-size: 0.7rem; margin-left: auto; }
.health-dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; flex-shrink: 0; }
.health-badge { display: inline-block; padding: 1px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.health-badge.health-healthy { background: rgba(103,194,58,0.15); color: #67C23A; }
.health-badge.health-warning { background: rgba(230,162,60,0.15); color: #E6A23C; }
.health-badge.health-critical { background: rgba(239,68,68,0.15); color: #ef4444; }
</style>
