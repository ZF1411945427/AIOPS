<template>
  <div class="k8s-overview-page">
    <div class="page-header">
      <h1>集群概览</h1>
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

    <div v-if="loading" class="panel"><div class="panel-body"><div class="loading-state">加载中...</div></div></div>

    <div v-else-if="overviews.length" class="cluster-grid">
      <div v-for="o in overviews" :key="o.name" class="cluster-card">
        <div class="cluster-head">
          <div class="cluster-title">
            <span class="status-dot" :class="statusClass(o.status)"></span>
            <span class="cluster-name">{{ o.name }}</span>
            <span class="status-tag" :class="statusClass(o.status)">{{ statusText(o.status) }}</span>
          </div>
          <div class="cluster-endpoint">{{ o.endpoint || '-' }}</div>
          <div class="cluster-time">采集时间: {{ o.last_scrape || '-' }}</div>
        </div>
        <div class="cluster-stats">
          <div class="mini-stat"><div class="mini-val">{{ o.nodes }}</div><div class="mini-label">节点</div></div>
          <div class="mini-stat"><div class="mini-val">{{ o.pods }}</div><div class="mini-label">Pod</div></div>
          <div class="mini-stat"><div class="mini-val">{{ o.deployments }}</div><div class="mini-label">Deployment</div></div>
          <div class="mini-stat"><div class="mini-val">{{ o.namespaces }}</div><div class="mini-label">命名空间</div></div>
          <div class="mini-stat"><div class="mini-val">{{ o.services }}</div><div class="mini-label">Service</div></div>
        </div>
        <div class="progress-block">
          <div class="progress-row">
            <span class="progress-label">节点健康率</span>
            <span class="progress-val">{{ o.node_health_rate }}%</span>
          </div>
          <div class="progress-bar"><div class="progress-fill" :style="{ width: o.node_health_rate + '%', background: rateColor(o.node_health_rate) }"></div></div>
        </div>
        <div class="progress-block">
          <div class="progress-row">
            <span class="progress-label">Pod 运行率</span>
            <span class="progress-val">{{ o.pod_running_rate }}%</span>
          </div>
          <div class="progress-bar"><div class="progress-fill" :style="{ width: o.pod_running_rate + '%', background: rateColor(o.pod_running_rate) }"></div></div>
        </div>
      </div>
    </div>

    <div v-else class="panel">
      <div class="panel-body">
        <div class="empty-state">
          <div style="font-size:36px;margin-bottom:8px;">☸️</div>
          <div>暂无 K8s 集群数据</div>
          <div class="text-muted" style="margin-top:4px;">请在数据源管理中添加 Kubernetes 类型数据源</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const overviews = ref([])
const errors = ref([])
const summary = ref({})

async function loadOverview() {
  loading.value = true
  try {
    const data = await request.get('/k8s/api/overview')
    overviews.value = data.overviews || []
    errors.value = data.errors || []
    summary.value = data.summary || {}
  } catch (e) {
    ElMessage.error('加载集群概览失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

function statusClass(s) {
  if (s === 'online') return 'green'
  if (s === 'error') return 'red'
  return 'gray'
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

onMounted(loadOverview)
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
.cluster-card { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.cluster-head { margin-bottom: 12px; }
.cluster-title { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.cluster-name { font-weight: 600; font-size: 0.95rem; color: var(--text, #1e293b); }
.status-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.status-dot.green { background: #22c55e; box-shadow: 0 0 6px rgba(34,197,94,0.5); }
.status-dot.red { background: #ef4444; box-shadow: 0 0 6px rgba(239,68,68,0.5); }
.status-dot.gray { background: #94a3b8; }
.status-tag { font-size: 0.7rem; padding: 1px 8px; border-radius: 8px; font-weight: 600; }
.status-tag.green { background: rgba(34,197,94,0.1); color: #22c55e; }
.status-tag.red { background: rgba(239,68,68,0.1); color: #ef4444; }
.status-tag.gray { background: rgba(100,116,139,0.1); color: #64748b; }
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
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.text-muted { color: var(--text-tertiary, #94a3b8); font-size: 0.78rem; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
</style>
