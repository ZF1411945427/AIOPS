<template>
  <div class="topo-page">
    <div class="topo-hd">
      <h1>K8s 资源拓扑</h1>
      <div class="hd-right">
        <select v-model="clusterFilter" @change="doFilter" class="cs">
          <option value="">全部集群</option>
          <option v-for="c in clusterNames" :key="c" :value="c">{{ c }}</option>
        </select>
        <button class="btn btn-sm" @click="loadGraph">刷新</button>
      </div>
    </div>

    <div class="legend-bar">
      <span class="lg-title">图例：</span>
      <span class="lg-item"><span class="lg-dot" style="background:#6366f1"></span>集群</span>
      <span class="lg-item"><span class="lg-dot" style="background:#3b82f6"></span>命名空间</span>
      <span class="lg-item"><span class="lg-dot" style="background:#10b981"></span>节点</span>
      <span class="lg-item"><span class="lg-dot" style="background:#f59e0b"></span>工作负载</span>
      <span class="lg-item"><span class="lg-dot" style="background:#8b5cf6"></span>Service</span>
      <span class="lg-item"><span class="lg-dot" style="background:#ec4899"></span>Ingress</span>
      <span class="lg-item"><span class="lg-dot" style="background:#06b6d4"></span>ConfigMap</span>
      <span class="lg-item"><span class="lg-dot" style="background:#dc2626"></span>Secret</span>
      <span class="lg-item"><span class="lg-dot" style="background:#64748b"></span>PVC/PV</span>
      <span class="lg-divider"></span>
      <span class="lg-item lg-orphan"><span class="lg-warn">⚠</span>孤岛资源 {{ stats.orphan_count || 0 }}</span>
      <span class="lg-item lg-ref"><span class="lg-line refs"></span>引用关系 {{ refEdgeCount }}</span>
    </div>

    <div v-if="loading" class="loading">加载中...</div>
    <div v-if="errorMsg" class="error">{{ errorMsg }}</div>
    <div v-if="!loading && !errorMsg && !treeData.length" class="empty">暂无拓扑数据</div>

    <div class="topo-layout" v-if="treeData.length">
      <div class="topo-main">
        <div v-for="root in treeData" :key="root.id" class="cluster-card">
          <div class="cluster-head" @click="root._open = !root._open">
            <span class="arrow" :class="{ on: root._open }">▶</span>
            <span class="ch-icon" style="background:#6366f1">C</span>
            <span class="ch-name">{{ root.name }}</span>
            <span class="ch-tag">集群</span>
            <span class="ch-info">{{ root.children?.length || 0 }} 命名空间</span>
          </div>
          <div v-if="root._open" class="cluster-body">
            <div v-for="ns in root.children" :key="ns.id" v-show="ns.ci_type === 'namespace'" class="ns-card">
              <div class="ns-head" @click="ns._open = !ns._open">
                <span class="arrow" :class="{ on: ns._open }">▶</span>
                <span class="ns-icon" style="background:#3b82f6">N</span>
                <span class="ns-name">{{ ns.name }}</span>
                <span class="ns-tag">命名空间</span>
                <span class="ns-info">{{ ns.children?.length || 0 }} 资源</span>
              </div>
              <div v-if="ns._open" class="ns-body">
                <div v-for="item in ns.children" :key="item.id" class="res-row" :class="{ orphan: item.orphan }">
                  <!-- 工作负载：显示 pod_summary 概要（不再列 pod 子节点） -->
                  <div v-if="isWorkload(item.ci_type)" class="dep-card" :class="{ bad: item.abnormal }" @click="selectedNode = item">
                    <span class="dep-icon" :style="{ background: typeColor(item.ci_type) }">{{ wlIcon(item.ci_type) }}</span>
                    <span class="dep-name">{{ item.name }}</span>
                    <span class="dep-tag">{{ typeLabel(item.ci_type) }}</span>
                    <span class="pod-summary">
                      <span class="ps-total">{{ item.attrs?.pod_summary?.total || 0 }} Pod</span>
                      <span v-if="(item.attrs?.pod_summary?.running || 0) > 0" class="ps-run">运行 {{ item.attrs.pod_summary.running }}</span>
                      <span v-if="(item.attrs?.pod_summary?.pending || 0) > 0" class="ps-pend">等待 {{ item.attrs.pod_summary.pending }}</span>
                      <span v-if="(item.attrs?.pod_summary?.failed || 0) > 0" class="ps-fail">失败 {{ item.attrs.pod_summary.failed }}</span>
                      <span v-if="(item.attrs?.pod_summary?.restarts || 0) > 0" class="ps-restart">重启 {{ item.attrs.pod_summary.restarts }}</span>
                    </span>
                    <span v-if="item.abnormal" class="warn-badge">⚠</span>
                  </div>
                  <!-- Service / Ingress -->
                  <div v-else-if="item.ci_type === 'service' || item.ci_type === 'ingress'" class="svc-chip" @click="selectedNode = item">
                    <span class="s-icon" :style="{ background: typeColor(item.ci_type) }">{{ item.ci_type === 'service' ? 'S' : 'I' }}</span>
                    <span class="s-name">{{ item.name }}</span>
                    <span class="s-tag">{{ typeLabel(item.ci_type) }}</span>
                  </div>
                  <!-- 弱纳管 CI：ConfigMap/Secret/PVC，孤岛标记 -->
                  <div v-else-if="item.ci_type === 'configmap' || item.ci_type === 'secret' || item.ci_type === 'pvc'" class="weak-chip" :class="{ orphan: item.orphan }" @click="selectedNode = item">
                    <span class="w-icon" :style="{ background: typeColor(item.ci_type) }">{{ weakIcon(item.ci_type) }}</span>
                    <span class="w-name">{{ item.name }}</span>
                    <span class="w-tag">{{ typeLabel(item.ci_type) }}</span>
                    <span v-if="(item.attrs?.referenced_by || []).length" class="w-ref">引用 {{ item.attrs.referenced_by.length }}</span>
                    <span v-else class="w-orphan">孤岛</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="side-panel">
        <div class="panel-title">节点统计</div>
        <div class="stat-list">
          <div v-for="t in nodeTypeList" :key="t.type" class="stat-row">
            <span class="sdot" :style="{ background: t.color }"></span>
            <span>{{ typeLabel(t.type) }}</span>
            <span class="snum">{{ t.count }}</span>
          </div>
        </div>
        <div class="orphan-alert" v-if="(stats.orphan_count || 0) > 0">
          <span class="oa-icon">⚠</span>
          <span class="oa-text">{{ stats.orphan_count }} 个孤岛资源</span>
          <span class="oa-sub">未被任何 Pod 引用，疑似配置漂移</span>
        </div>
        <div v-if="selectedNode" class="detail-card">
          <div class="dc-name">{{ selectedNode.name }}</div>
          <div class="dc-badge" :style="{ background: typeColor(selectedNode.ci_type)+'22', color: typeColor(selectedNode.ci_type) }">{{ typeLabel(selectedNode.ci_type) }}</div>
          <div class="dc-row"><span class="dk">集群</span><span>{{ selectedNode.cluster || '-' }}</span></div>
          <div class="dc-row" v-if="selectedNode.attrs?.namespace"><span class="dk">命名空间</span><span>{{ selectedNode.attrs.namespace }}</span></div>
          <div class="dc-row" v-if="selectedNode.attrs?.pod_summary"><span class="dk">Pod 概要</span><span class="dc-obj">{{ formatPodSummary(selectedNode.attrs.pod_summary) }}</span></div>
          <div class="dc-row" v-if="selectedNode.attrs?.referenced_by"><span class="dk">被引用</span><span class="dc-obj">{{ selectedNode.attrs.referenced_by.join(', ') || '无' }}</span></div>
          <div class="dc-row" v-if="'orphan' in (selectedNode.attrs || {})"><span class="dk">孤岛</span><span :class="{ orphan: selectedNode.attrs.orphan }">{{ selectedNode.attrs.orphan ? '是 ⚠' : '否' }}</span></div>
          <div class="dc-row" v-if="selectedNode.attrs?.data_keys"><span class="dk">数据键</span><span class="dc-obj">{{ selectedNode.attrs.data_keys.join(', ') }}</span></div>
          <div class="dc-row" v-if="selectedNode.attrs?.replicas !== undefined"><span class="dk">副本</span><span>{{ selectedNode.attrs.replicas }} (就绪 {{ selectedNode.attrs.available }})</span></div>
          <div class="dc-row" v-if="selectedNode.attrs?.selector"><span class="dk">selector</span><span class="dc-obj">{{ JSON.stringify(selectedNode.attrs.selector) }}</span></div>
          <div class="dc-row" v-if="selectedNode.attrs?.cluster_ip"><span class="dk">ClusterIP</span><span>{{ selectedNode.attrs.cluster_ip }}</span></div>
        </div>
        <div v-else class="dc-empty">点击节点查看详情</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import request from '@/api/request'

const loading = ref(false)
const errorMsg = ref('')
const rawTrees = ref([])
const treeData = ref([])
const clusterFilter = ref('')
const selectedNode = ref(null)
const nodeTypeList = ref([])
const stats = ref({})
const refEdgeCount = ref(0)

const TYPE_COLOR = {
  kubernetes_cluster:'#6366f1', cluster:'#6366f1', namespace:'#3b82f6',
  node:'#10b981', deployment:'#f59e0b', statefulset:'#f97316',
  daemonset:'#ea580c', pod:'#14b8a6', service:'#8b5cf6',
  ingress:'#ec4899', pvc:'#64748b', pv:'#475569',
  configmap:'#06b6d4', secret:'#dc2626',
}
const TYPE_LABEL = {
  kubernetes_cluster:'集群', cluster:'集群', namespace:'命名空间',
  node:'节点', deployment:'Deployment', statefulset:'StatefulSet',
  daemonset:'DaemonSet', pod:'Pod', service:'Service',
  ingress:'Ingress', pvc:'PVC', pv:'PV',
  configmap:'ConfigMap', secret:'Secret',
}
const CI_ORDER = ['kubernetes_cluster','namespace','node','deployment','statefulset','daemonset','service','ingress','configmap','secret','pvc','pv']

function typeColor(t) { return TYPE_COLOR[t] || '#94a3b8' }
function typeLabel(t) { return TYPE_LABEL[t] || t }
function isWorkload(t) { return t === 'deployment' || t === 'statefulset' || t === 'daemonset' }
function wlIcon(t) { return t === 'deployment' ? 'D' : (t === 'statefulset' ? 'S' : 'A') }
function weakIcon(t) { return t === 'configmap' ? 'C' : (t === 'secret' ? 'K' : 'P') }
function formatVal(v) { if(v===null||v===undefined) return '-'; if(typeof v==='object') return JSON.stringify(v); return String(v) }
function formatPodSummary(ps) {
  if (!ps) return '-'
  return `共${ps.total} 运行${ps.running} 等待${ps.pending} 失败${ps.failed} 重启${ps.restarts}`
}

const clusterNames = computed(() => {
  const s = new Set()
  function walk(n) { if(n.cluster) s.add(n.cluster); (n.children||[]).forEach(walk) }
  rawTrees.value.forEach(walk)
  rawTrees.value.forEach(r => { if(r.name) s.add(r.name) })
  return [...s]
})

function expandAll(list) { list.forEach(n => { n._open = true; if(n.children) expandAll(n.children) }) }

function doFilter() {
  if(clusterFilter.value) {
    treeData.value = rawTrees.value.filter(r => r.cluster === clusterFilter.value || r.name === clusterFilter.value)
  } else {
    treeData.value = rawTrees.value
  }
  expandAll(treeData.value)
}

function buildTypeList() {
  const bt = stats.value.by_type || {}
  nodeTypeList.value = CI_ORDER.filter(t => bt[t]).map(t => ({ type: t, color: typeColor(t), count: bt[t] }))
}

async function loadGraph() {
  loading.value = true; errorMsg.value = ''
  try {
    const data = await request.get('/containers/topology/graph')
    rawTrees.value = data.trees || []
    stats.value = data.stats || {}
    // 统计孤岛数与引用边数
    let orphanCnt = 0
    function countOrphan(n) {
      if (n.orphan) orphanCnt++
      ;(n.children||[]).forEach(countOrphan)
    }
    rawTrees.value.forEach(countOrphan)
    stats.value.orphan_count = orphanCnt
    refEdgeCount.value = (data.links || []).filter(l => l.type === 'references').length
    treeData.value = rawTrees.value
    expandAll(treeData.value)
    buildTypeList()
  } catch(e) { errorMsg.value = '加载失败: ' + (e.message || e) }
  finally { loading.value = false }
}

onMounted(() => loadGraph())
</script>

<style scoped>
.topo-page { padding: 4px; }
.topo-hd { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.topo-hd h1 { font-size: 1.1rem; font-weight: 600; color: var(--text, #1e293b); margin: 0; }
.hd-right { display: flex; gap: 6px; align-items: center; }
.cs { padding: 4px 8px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 5px; background: var(--bg-card-solid,#fff); color: var(--text,#1e293b); font-size: 0.78rem; }
.btn { padding: 4px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid,#fff); color: var(--text,#1e293b); cursor: pointer; font-size: 0.78rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-sm { padding: 3px 8px; font-size: 0.72rem; }
.loading, .error, .empty { text-align: center; padding: 60px 20px; color: var(--text-secondary,#64748b); font-size: 0.85rem; }
.error { color: #ef4444; }
.topo-layout { display: flex; gap: 14px; }
.topo-main { flex: 1; display: flex; flex-direction: column; gap: 12px; }

.legend-bar { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; padding: 6px 10px; margin-bottom: 10px; background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 8px; font-size: 0.72rem; color: var(--text-secondary,#64748b); }
.lg-title { font-weight: 600; color: var(--text,#1e293b); }
.lg-item { display: inline-flex; align-items: center; gap: 4px; }
.lg-dot { width: 8px; height: 8px; border-radius: 2px; }
.lg-divider { width: 1px; height: 14px; background: var(--border,rgba(0,0,0,0.1)); margin: 0 4px; }
.lg-orphan { color: #ef4444; }
.lg-warn { color: #ef4444; font-size: 0.8rem; }
.lg-ref { color: #06b6d4; }
.lg-line { width: 14px; height: 2px; }
.lg-line.refs { background: #06b6d4; border-top: 1px dashed #06b6d4; height: 0; }

.cluster-card { background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.cluster-head { display: flex; align-items: center; gap: 8px; padding: 10px 14px; background: linear-gradient(135deg, rgba(99,102,241,0.08), rgba(99,102,241,0.03)); cursor: pointer; user-select: none; }
.arrow { font-size: 0.5rem; color: var(--text-tertiary,#94a3b8); width: 10px; text-align: center; transition: transform 0.12s; flex-shrink: 0; }
.arrow.on { transform: rotate(90deg); }
.ch-icon { width: 24px; height: 24px; border-radius: 6px; color: #fff; font-size: 0.7rem; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.ch-name { font-weight: 600; font-size: 0.88rem; color: var(--text,#1e293b); }
.ch-tag { font-size: 0.6rem; padding: 1px 6px; border-radius: 4px; background: rgba(99,102,241,0.15); color: #6366f1; font-weight: 600; }
.ch-info { font-size: 0.7rem; color: var(--text-tertiary,#94a3b8); margin-left: auto; }
.cluster-body { padding: 4px 0 8px 16px; display: flex; flex-direction: column; gap: 4px; }

.ns-card { }
.ns-head { display: flex; align-items: center; gap: 6px; padding: 6px 10px; cursor: pointer; border-radius: 6px; user-select: none; }
.ns-head:hover { background: rgba(59,130,246,0.04); }
.ns-icon { width: 18px; height: 18px; border-radius: 4px; color: #fff; font-size: 0.6rem; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.ns-name { font-weight: 500; font-size: 0.82rem; color: var(--text,#1e293b); }
.ns-tag { font-size: 0.58rem; padding: 1px 5px; border-radius: 3px; background: rgba(59,130,246,0.1); color: #3b82f6; }
.ns-info { font-size: 0.68rem; color: var(--text-tertiary,#94a3b8); margin-left: auto; }
.ns-body { padding: 2px 0 4px 20px; display: flex; flex-direction: column; gap: 3px; }

.res-row { }
.dep-card { display: flex; align-items: center; gap: 6px; padding: 5px 10px; cursor: pointer; border-radius: 5px; user-select: none; background: rgba(245,158,11,0.06); border: 1px solid rgba(245,158,11,0.12); margin: 2px 0; }
.dep-card:hover { background: rgba(245,158,11,0.1); }
.dep-card.bad { border-color: #ef4444; background: rgba(239,68,68,0.06); }
.dep-icon { width: 16px; height: 16px; border-radius: 4px; color: #fff; font-size: 0.55rem; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.dep-name { font-size: 0.8rem; color: var(--text,#1e293b); }
.dep-tag { font-size: 0.58rem; padding: 1px 5px; border-radius: 3px; background: rgba(245,158,11,0.1); color: #f59e0b; }
.dep-info { font-size: 0.68rem; color: var(--text-tertiary,#94a3b8); margin-left: auto; }
.pod-summary { margin-left: auto; display: flex; gap: 5px; font-size: 0.66rem; }
.ps-total { color: var(--text-tertiary,#94a3b8); }
.ps-run { color: #10b981; font-weight: 600; }
.ps-pend { color: #f59e0b; font-weight: 600; }
.ps-fail { color: #ef4444; font-weight: 600; }
.ps-restart { color: #f97316; }
.warn-badge { color: #ef4444; font-size: 0.7rem; }

.svc-chip { display: inline-flex; align-items: center; gap: 5px; padding: 3px 8px; margin: 1px 0; cursor: pointer; border-radius: 4px; }
.svc-chip:hover { background: rgba(139,92,246,0.06); }
.s-icon { width: 15px; height: 15px; border-radius: 3px; color: #fff; font-size: 0.55rem; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.s-name { font-size: 0.76rem; color: var(--text,#1e293b); }
.s-tag { font-size: 0.58rem; padding: 1px 5px; border-radius: 3px; background: rgba(139,92,246,0.1); color: #8b5cf6; }

.weak-chip { display: flex; align-items: center; gap: 5px; padding: 3px 8px; margin: 1px 0; cursor: pointer; border-radius: 4px; border: 1px solid transparent; }
.weak-chip:hover { background: rgba(6,182,212,0.06); }
.weak-chip.orphan { border-color: rgba(239,68,68,0.3); background: rgba(239,68,68,0.04); }
.w-icon { width: 15px; height: 15px; border-radius: 3px; color: #fff; font-size: 0.55rem; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.w-name { font-size: 0.74rem; color: var(--text,#1e293b); }
.w-tag { font-size: 0.56rem; padding: 1px 4px; border-radius: 3px; }
.w-ref { margin-left: auto; font-size: 0.62rem; color: #06b6d4; font-weight: 600; }
.w-orphan { margin-left: auto; font-size: 0.62rem; color: #ef4444; font-weight: 600; }

.side-panel { width: 220px; display: flex; flex-direction: column; gap: 8px; padding: 12px; background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); height: fit-content; }
.panel-title { font-weight: 600; font-size: 0.78rem; color: var(--text,#1e293b); margin-bottom: 4px; }
.stat-list { display: flex; flex-direction: column; gap: 3px; }
.stat-row { display: flex; align-items: center; gap: 6px; font-size: 0.73rem; color: var(--text-secondary,#64748b); }
.sdot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.snum { margin-left: auto; font-weight: 600; color: var(--text,#1e293b); font-size: 0.7rem; }
.orphan-alert { margin-top: 6px; padding: 8px; background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.2); border-radius: 6px; display: flex; flex-direction: column; gap: 2px; }
.oa-icon { color: #ef4444; font-size: 0.9rem; }
.oa-text { font-size: 0.75rem; font-weight: 600; color: #ef4444; }
.oa-sub { font-size: 0.62rem; color: var(--text-tertiary,#94a3b8); }
.detail-card { margin-top: 6px; }
.dc-name { font-weight: 600; font-size: 0.82rem; color: var(--text,#1e293b); margin-bottom: 3px; }
.dc-badge { display: inline-block; padding: 1px 6px; border-radius: 6px; font-size: 0.64rem; font-weight: 600; margin-bottom: 4px; }
.dc-row { display: flex; gap: 5px; font-size: 0.7rem; line-height: 1.5; }
.dk { width: 60px; flex-shrink: 0; color: var(--text-tertiary,#94a3b8); }
.dc-obj { word-break: break-all; }
.orphan { color: #ef4444; font-weight: 600; }
.dc-empty { font-size: 0.72rem; color: var(--text-tertiary,#94a3b8); padding: 10px 0; text-align: center; }
</style>
