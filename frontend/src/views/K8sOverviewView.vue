<template>
  <div class="k8s-overview-page">
    <div class="page-header">
      <div class="page-header-top">
        <h1>集群概览</h1>
        <button class="btn btn-guide" @click="showGuide = !showGuide">📖 操作说明</button>
      </div>
      <p>Kubernetes 多集群资源汇总 · 共 {{ summary.cluster_count || 0 }} 个集群（健康 {{ summary.healthy_clusters || 0 }}）</p>
    </div>

    <div class="stat-cards">
      <div class="stat-card stat-blue">
        <div class="stat-icon">☸️</div>
        <div class="stat-body"><div class="stat-value">{{ summary.cluster_count || 0 }}</div><div class="stat-label">集群总数</div></div>
      </div>
      <div class="stat-card stat-green">
        <div class="stat-icon">🖥️</div>
        <div class="stat-body"><div class="stat-value">{{ summary.total_nodes || 0 }}</div><div class="stat-label">节点（健康 {{ summary.total_healthy_nodes || 0 }}）</div></div>
      </div>
      <div class="stat-card stat-purple">
        <div class="stat-icon">📦</div>
        <div class="stat-body"><div class="stat-value">{{ summary.total_pods || 0 }}</div><div class="stat-label">Pod（运行 {{ summary.total_running_pods || 0 }}）</div></div>
      </div>
      <div class="stat-card stat-orange">
        <div class="stat-icon">🚀</div>
        <div class="stat-body"><div class="stat-value">{{ summary.total_deployments || 0 }}</div><div class="stat-label">Deployment</div></div>
      </div>
      <div class="stat-card stat-cyan">
        <div class="stat-icon">📂</div>
        <div class="stat-body"><div class="stat-value">{{ summary.total_namespaces || 0 }}</div><div class="stat-label">命名空间</div></div>
      </div>
      <div class="stat-card stat-pink">
        <div class="stat-icon">🌐</div>
        <div class="stat-body"><div class="stat-value">{{ summary.total_services || 0 }}</div><div class="stat-label">Service</div></div>
      </div>
    </div>

    <div v-if="errors.length" class="error-banner">
      <div v-for="(e, i) in errors" :key="i" class="error-line">⚠️ {{ e }}</div>
    </div>

    <div class="cluster-grid">
      <div v-for="(card, i) in cards" :key="card._ph ? '_ph' + i : card.name" class="cluster-card" :class="card._ph ? 'card-ph' : cardStatusClass(card)">
        <template v-if="card._ph">
          <div class="ph-head"><div class="ph-line ph-w40"></div><div class="ph-line ph-w60"></div></div>
          <div class="ph-body"><div class="ph-line ph-w80"></div><div class="ph-line ph-w50"></div></div>
        </template>
        <template v-else>
          <div class="cluster-head">
            <div class="cluster-title">
              <span class="status-dot" :class="card.probing ? 'status-dot-probing' : statusClass(card.status)"></span>
              <span class="cluster-name">{{ card.name }}</span>
              <span class="status-tag" :class="card.probing ? 'status-tag-probing' : statusClass(card.status)">{{ card.probing ? '探测中' : statusText(card.status) }}</span>
            </div>
            <div class="cluster-endpoint">{{ card.endpoint || '-' }}</div>
            <div class="cluster-time">{{ card.last_scraped_at ? '采集时间: ' + card.last_scraped_at : '-' }}</div>
          </div>

          <template v-if="card.probing">
            <div class="cluster-probing">
              <div class="mini-spinner"></div>
              <span>正在连接集群...</span>
            </div>
          </template>

          <template v-else-if="card.status === 'online'">
            <div class="cluster-stats">
              <div class="mini-stat"><div class="mini-val">{{ card.nodes }}</div><div class="mini-label">节点</div></div>
              <div class="mini-stat"><div class="mini-val">{{ card.pods }}</div><div class="mini-label">Pod</div></div>
              <div class="mini-stat"><div class="mini-val">{{ card.deployments }}</div><div class="mini-label">Deployment</div></div>
              <div class="mini-stat"><div class="mini-val">{{ card.namespaces }}</div><div class="mini-label">命名空间</div></div>
              <div class="mini-stat"><div class="mini-val">{{ card.services }}</div><div class="mini-label">Service</div></div>
            </div>
            <div class="progress-block">
              <div class="progress-row">
                <span class="progress-label">节点健康率</span>
                <span class="progress-val">{{ card.node_health_rate }}%</span>
              </div>
              <div class="progress-bar"><div class="progress-fill" :style="{ width: card.node_health_rate + '%', background: rateColor(card.node_health_rate) }"></div></div>
            </div>
            <div class="progress-block">
              <div class="progress-row">
                <span class="progress-label">Pod 运行率</span>
                <span class="progress-val">{{ card.pod_running_rate }}%</span>
              </div>
              <div class="progress-bar"><div class="progress-fill" :style="{ width: card.pod_running_rate + '%', background: rateColor(card.pod_running_rate) }"></div></div>
            </div>
          </template>

          <template v-else>
            <div class="cluster-error-body">
              <div class="cluster-error-icon">⚠️</div>
              <div class="cluster-error-text">集群不可达</div>
            </div>
          </template>
        </template>
      </div>
    </div>
  </div>

  <GuideDrawer v-model="showGuide" title="📖 K8s 集群概览 — 使用说明">
    <div class="guide-section">
      <h4>页面概览</h4>
      <p>本页面以<strong>多集群健康总览</strong>为核心，采用卡片式布局展示每一纳管 Kubernetes 集群的实时状态与核心指标，方便运维人员<strong>一屏掌握</strong>所有集群的健康水位。</p>
    </div>

    <div class="guide-section">
      <h4>顶部统计栏</h4>
      <p>页面顶部的渐变统计卡片汇总了所有集群的聚合数据：</p>
      <ul>
        <li><strong>集群总数</strong> — 已接入的全部 K8s 集群数量</li>
        <li><strong>节点</strong> — 所有集群的节点总和（含健康节点数）</li>
        <li><strong>Pod</strong> — 所有集群的 Pod 总和（含运行中 Pod 数）</li>
        <li><strong>Deployment</strong> — 所有集群的 Deployment 总数</li>
        <li><strong>命名空间</strong> — 所有集群的 Namespace 总数</li>
        <li><strong>Service</strong> — 所有集群的 Service 总数</li>
      </ul>
    </div>

    <div class="guide-section">
      <h4>集群卡片颜色说明</h4>
      <p>每张集群卡片左侧的颜色条代表该集群的整体状态：</p>
      <ul>
        <li><span class="tag-demo" style="background:rgba(34,197,94,0.12);color:#22c55e;">● 绿色</span> — 集群在线，数据正常采集</li>
        <li><span class="tag-demo" style="background:rgba(59,130,246,0.12);color:#3b82f6;">● 蓝色</span> — 集群正在探测中，数据尚未就绪</li>
        <li><span class="tag-demo" style="background:rgba(239,68,68,0.12);color:#ef4444;">● 红色</span> — 集群异常/不可达，需排查</li>
        <li><span class="tag-demo" style="background:rgba(148,163,184,0.12);color:#64748b;">● 灰色</span> — 集群状态未知</li>
      </ul>
    </div>

    <div class="guide-section">
      <h4>卡片核心指标</h4>
      <p>在线集群卡片展示以下实时指标：</p>
      <ul>
        <li><strong>节点</strong> — 集群中所有 Node 数量</li>
        <li><strong>Pod</strong> — 集群中所有 Pod 数量</li>
        <li><strong>Deployment</strong> — 集群中所有 Deployment 数量</li>
        <li><strong>命名空间</strong> — 集群中 Namespace 数量</li>
        <li><strong>Service</strong> — 集群中 Service 数量</li>
      </ul>
      <p>每个卡片还包含两条进度条：</p>
      <ul>
        <li><strong>节点健康率</strong> — 健康节点 / 总节点 × 100%</li>
        <li><strong>Pod 运行率</strong> — 运行中 Pod / 总 Pod × 100%</li>
      </ul>
    </div>

    <div class="guide-section">
      <h4>快速操作</h4>
      <p>每张在线集群卡片提供以下快捷入口（位于卡片底部操作栏）：</p>
      <ul>
        <li><strong>查看拓扑</strong> — 跳转至该集群的容器拓扑视图</li>
        <li><strong>查看 Pod</strong> — 查看集群内所有 Pod 列表及状态</li>
        <li><strong>查看 Deployment</strong> — 查看集群内所有 Deployment</li>
      </ul>
    </div>

    <div class="tip-box">
      <strong>💡 提示：</strong>页面每隔 30 秒自动刷新集群数据。若某个集群持续红色，请检查集群网络连通性或 kubelet 健康状态。点击右上角「刷新」按钮可手动强制刷新所有集群。
    </div>
  </GuideDrawer>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'
import GuideDrawer from '@/components/GuideDrawer.vue'

const cards = reactive([])
const errors = ref([])
const showGuide = ref(false)

function pushPlaceholders(n) {
  for (let i = 0; i < n; i++) cards.push({ _ph: true })
}
const summary = reactive({
  cluster_count: 0, healthy_clusters: 0,
  total_nodes: 0, total_healthy_nodes: 0,
  total_pods: 0, total_running_pods: 0,
  total_deployments: 0, total_namespaces: 0, total_services: 0,
  node_health_rate: 0, pod_running_rate: 0,
})

function recomputeSummary() {
  const done = cards.filter(c => !c.probing)
  const s = { cluster_count: cards.length, healthy_clusters: 0, total_nodes: 0, total_healthy_nodes: 0, total_pods: 0, total_running_pods: 0, total_deployments: 0, total_namespaces: 0, total_services: 0 }
  for (const c of done) {
    if (c.status === 'online') s.healthy_clusters++
    s.total_nodes += c.nodes || 0
    s.total_healthy_nodes += c.healthy_nodes || 0
    s.total_pods += c.pods || 0
    s.total_running_pods += c.running_pods || 0
    s.total_deployments += c.deployments || 0
    s.total_namespaces += c.namespaces || 0
    s.total_services += c.services || 0
  }
  s.node_health_rate = s.total_nodes ? Math.round(s.total_healthy_nodes / s.total_nodes * 100 * 10) / 10 : 0
  s.pod_running_rate = s.total_pods ? Math.round(s.total_running_pods / s.total_pods * 100 * 10) / 10 : 0
  Object.assign(summary, s)
}

async function loadClusters() {
  try {
    const res = await request.get('/k8s/api/overview')
    const list = (res.clusters || [])
    cards.splice(0, cards.length)
    for (const c of list) {
      cards.push({
        name: c.name,
        endpoint: c.endpoint,
        status: c.status,
        last_scraped_at: c.last_scraped_at,
        probing: true,
      })
    }
    recomputeSummary()
    list.forEach(c => probeCluster(c.name))
  } catch (e) {
    cards.splice(0, cards.length)
    ElMessage.error('加载集群列表失败: ' + (e.message || e))
  }
}

async function probeCluster(name) {
  try {
    const res = await request.get('/k8s/api/cluster/' + encodeURIComponent(name) + '/probe')
    const card = cards.find(c => c.name === name)
    if (!card) return
    if (res.status === 'online') {
      card.probing = false
      card.status = 'online'
      card.nodes = res.nodes
      card.healthy_nodes = res.healthy_nodes
      card.node_health_rate = res.node_health_rate
      card.pods = res.pods
      card.running_pods = res.running_pods
      card.pod_running_rate = res.pod_running_rate
      card.deployments = res.deployments
      card.namespaces = res.namespaces
      card.services = res.services
      card.last_scraped_at = res.last_scraped_at
    } else {
      card.probing = false
      card.status = 'error'
      card.nodes = 0; card.healthy_nodes = 0; card.node_health_rate = 0
      card.pods = 0; card.running_pods = 0; card.pod_running_rate = 0
      card.deployments = 0; card.namespaces = 0; card.services = 0
      errors.value.push(name + ': ' + (res.error || '探测失败'))
    }
    recomputeSummary()
  } catch (e) {
    const card = cards.find(c => c.name === name)
    if (card) {
      card.probing = false
      card.status = 'error'
    }
    errors.value.push(name + ': ' + (e.message || e))
    recomputeSummary()
  }
}

function statusClass(s) {
  if (s === 'online') return 'green'
  if (s === 'error') return 'red'
  return 'gray'
}

function cardStatusClass(card) {
  if (card.probing) return 'card-probing'
  if (card.status === 'online') return 'card-online'
  if (card.status === 'error') return 'card-error'
  return 'card-unknown'
}

function statusText(s) {
  if (s === 'online') return '在线'
  if (s === 'error') return '异常'
  if (s === 'unknown') return '未知'
  return s || '-'
}

function rateColor(v) {
  if (v >= 90) return 'linear-gradient(90deg,#22c55e,#16a34a)'
  if (v >= 60) return 'linear-gradient(90deg,#f59e0b,#d97706)'
  return 'linear-gradient(90deg,#ef4444,#dc2626)'
}

onMounted(() => {
  pushPlaceholders(6)
  loadClusters()
})
</script>

<style scoped>
.k8s-overview-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.stat-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 16px; }
.stat-card { display: flex; align-items: center; gap: 12px; border-radius: 10px; padding: 14px 16px; color: #fff; box-shadow: 0 2px 6px rgba(0,0,0,0.08); }
.stat-icon { width: 40px; height: 40px; border-radius: 10px; background: rgba(255,255,255,0.2); display: flex; align-items: center; justify-content: center; font-size: 20px; }
.stat-value { font-size: 1.4rem; font-weight: 700; }
.stat-label { font-size: 0.72rem; opacity: 0.92; }
.stat-blue { background: linear-gradient(135deg, #3b82f6, #1d4ed8); }
.stat-green { background: linear-gradient(135deg, #22c55e, #15803d); }
.stat-purple { background: linear-gradient(135deg, #8b5cf6, #6d28d9); }
.stat-orange { background: linear-gradient(135deg, #f97316, #c2410c); }
.stat-cyan { background: linear-gradient(135deg, #06b6d4, #0e7490); }
.stat-pink { background: linear-gradient(135deg, #ec4899, #be185d); }
.error-banner { background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.25); border-radius: 8px; padding: 10px 14px; margin-bottom: 14px; }
.error-line { color: #ef4444; font-size: 0.8rem; line-height: 1.6; }
.cluster-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 14px; }
.cluster-card { position: relative; background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); border-left: 4px solid transparent; transition: border-color 0.3s; }
.card-ph { border-left-color: transparent; }
.ph-head { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.ph-body { display: flex; flex-direction: column; gap: 8px; padding-top: 12px; border-top: 1px solid var(--border, rgba(0,0,0,0.07)); }
.ph-line { height: 14px; border-radius: 4px; background: linear-gradient(90deg, var(--bg-hover, rgba(0,0,0,0.04)) 25%, rgba(0,0,0,0.08) 50%, var(--bg-hover, rgba(0,0,0,0.04)) 75%); background-size: 200% 100%; animation: phShimmer 1.5s infinite; }
.ph-w40 { width: 40%; } .ph-w50 { width: 50%; } .ph-w60 { width: 60%; } .ph-w80 { width: 80%; }
@keyframes phShimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
.card-online { border-left-color: #22c55e; background: linear-gradient(to right, rgba(34,197,94,0.03), transparent); }
.card-error { border-left-color: #ef4444; background: linear-gradient(to right, rgba(239,68,68,0.03), transparent); }
.card-unknown { border-left-color: #94a3b8; }
.card-probing { border-left-color: #3b82f6; }
.cluster-head { margin-bottom: 12px; }
.cluster-title { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.cluster-name { font-weight: 600; font-size: 0.95rem; color: var(--text, #1e293b); }
.status-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; flex-shrink: 0; }
.status-dot.green { background: #22c55e; box-shadow: 0 0 6px rgba(34,197,94,0.5); }
.status-dot.red { background: #ef4444; box-shadow: 0 0 6px rgba(239,68,68,0.5); }
.status-dot.gray { background: #94a3b8; }
.status-dot-probing { background: #94a3b8; animation: pulse 1.4s infinite; }
@keyframes pulse { 0%,100% { opacity: 0.4; } 50% { opacity: 1; } }
.status-tag { font-size: 0.7rem; padding: 1px 8px; border-radius: 8px; font-weight: 600; flex-shrink: 0; }
.status-tag.green { background: rgba(34,197,94,0.1); color: #22c55e; }
.status-tag.red { background: rgba(239,68,68,0.1); color: #ef4444; }
.status-tag.gray { background: rgba(100,116,139,0.1); color: #64748b; }
.status-tag-probing { background: rgba(100,116,139,0.1); color: #64748b; animation: pulse 1.4s infinite; }
.cluster-endpoint { font-size: 0.75rem; color: var(--text-secondary, #64748b); font-family: ui-monospace, monospace; word-break: break-all; }
.cluster-time { font-size: 0.72rem; color: var(--text-tertiary, #94a3b8); margin-top: 2px; }
.cluster-stats { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin: 12px 0; padding: 10px 0; border-top: 1px solid var(--border, rgba(0,0,0,0.07)); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.mini-stat { text-align: center; }
.mini-val { font-size: 1.1rem; font-weight: 700; color: var(--text, #1e293b); }
.mini-label { font-size: 0.68rem; color: var(--text-secondary, #64748b); margin-top: 2px; }
.progress-block { margin-bottom: 10px; }
.progress-row { display: flex; justify-content: space-between; font-size: 0.75rem; margin-bottom: 4px; }
.progress-label { color: var(--text-secondary, #64748b); }
.progress-val { font-weight: 600; color: var(--text, #1e293b); }
.progress-bar { height: 6px; border-radius: 3px; background: var(--bg-hover, rgba(0,0,0,0.06)); overflow: hidden; }
.progress-fill { height: 100%; border-radius: 3px; transition: width 0.4s; }
.cluster-probing { display: flex; align-items: center; justify-content: center; gap: 10px; padding: 28px 0; color: var(--text-tertiary, #94a3b8); font-size: 0.85rem; }
.mini-spinner { width: 20px; height: 20px; border: 2px solid var(--border, rgba(0,0,0,0.07)); border-top-color: #3b82f6; border-radius: 50%; animation: spin 0.8s linear infinite; flex-shrink: 0; }
@keyframes spin { to { transform: rotate(360deg); } }
.cluster-error-body { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 24px 0; color: var(--text-tertiary, #94a3b8); font-size: 0.85rem; }
.cluster-error-icon { font-size: 1.1rem; }
.cluster-error-text { color: var(--text-secondary, #64748b); }
.page-header-top { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.btn-guide {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 5px 12px; font-size: 0.78rem; font-weight: 500;
  border: 1px solid var(--border, rgba(0,0,0,0.12));
  border-radius: 6px; background: var(--bg-card, #fff);
  color: var(--text-secondary, #64748b); cursor: pointer;
  white-space: nowrap; transition: all 0.2s;
}
.btn-guide:hover {
  border-color: #6366f1; color: #6366f1;
  background: rgba(99,102,241,0.05);
}
</style>
