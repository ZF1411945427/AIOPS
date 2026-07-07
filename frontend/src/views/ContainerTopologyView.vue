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
                <div v-for="item in ns.children" :key="item.id">
                  <div v-if="item.ci_type === 'deployment' || item.ci_type === 'statefulset' || item.ci_type === 'daemonset'" class="dep-card">
                    <div class="dep-head" @click="item._open = !item._open">
                      <span class="arrow" :class="{ on: item._open }">▶</span>
                      <span class="dep-icon" style="background:#f59e0b">D</span>
                      <span class="dep-name">{{ item.name }}</span>
                      <span class="dep-tag">Deployment</span>
                      <span class="dep-info">{{ item.children?.length || 0 }} Pod</span>
                    </div>
                    <div v-if="item._open" class="dep-body">
                      <div v-for="pod in item.children" :key="pod.id" v-show="pod.ci_type === 'pod'"
                        class="pod-chip" :class="['pod-' + ((pod.attrs?.phase || 'running').toLowerCase()), { bad: pod.abnormal }]" @click="selectedNode = pod">
                        <span class="pname">{{ pod.name }}</span>
                        <span class="pmeta">{{ pod.attrs?.phase || 'Running' }}</span>
                        <span v-if="pod.abnormal" class="pwarn">⚠</span>
                      </div>
                    </div>
                  </div>
                  <div v-if="item.ci_type === 'service'" class="svc-chip">
                    <span class="s-icon" style="background:#8b5cf6">S</span>
                    <span class="s-name">{{ item.name }}</span>
                    <span class="s-tag">Service</span>
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
        <div v-if="selectedNode" class="detail-card">
          <div class="dc-name">{{ selectedNode.name }}</div>
          <div class="dc-badge" :style="{ background: typeColor(selectedNode.ci_type)+'22', color: typeColor(selectedNode.ci_type) }">{{ typeLabel(selectedNode.ci_type) }}</div>
          <div class="dc-row"><span class="dk">集群</span><span>{{ selectedNode.cluster || '-' }}</span></div>
          <div class="dc-row"><span class="dk">状态</span><span>{{ selectedNode.attrs?.phase || selectedNode.status || '-' }}</span></div>
          <div class="dc-row" v-for="(v,k) in selectedNode.attrs" :key="k"><span class="dk">{{ k }}</span><span>{{ formatVal(v) }}</span></div>
        </div>
        <div v-else class="dc-empty">点击 Pod 查看详情</div>
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

const TYPE_COLOR = {
  kubernetes_cluster:'#6366f1', cluster:'#6366f1', namespace:'#3b82f6',
  node:'#10b981', deployment:'#f59e0b', statefulset:'#f97316',
  daemonset:'#ea580c', pod:'#14b8a6', service:'#8b5cf6',
  ingress:'#ec4899', pvc:'#64748b',
}
const TYPE_LABEL = {
  kubernetes_cluster:'集群', cluster:'集群', namespace:'命名空间',
  node:'节点', deployment:'Deployment', statefulset:'StatefulSet',
  daemonset:'DaemonSet', pod:'Pod', service:'Service',
  ingress:'Ingress', pvc:'PVC',
}
const CI_ORDER = ['kubernetes_cluster','cluster','namespace','node','deployment','pod','service']

function typeColor(t) { return TYPE_COLOR[t] || '#94a3b8' }
function typeLabel(t) { return TYPE_LABEL[t] || t }
function formatVal(v) { if(v===null||v===undefined) return '-'; if(typeof v==='object') return JSON.stringify(v); return String(v) }

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

.dep-card { }
.dep-head { display: flex; align-items: center; gap: 6px; padding: 5px 10px; cursor: pointer; border-radius: 5px; user-select: none; background: rgba(245,158,11,0.06); border: 1px solid rgba(245,158,11,0.12); }
.dep-head:hover { background: rgba(245,158,11,0.1); }
.dep-icon { width: 16px; height: 16px; border-radius: 4px; color: #fff; font-size: 0.55rem; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.dep-name { font-size: 0.8rem; color: var(--text,#1e293b); }
.dep-tag { font-size: 0.58rem; padding: 1px 5px; border-radius: 3px; background: rgba(245,158,11,0.1); color: #f59e0b; }
.dep-info { font-size: 0.68rem; color: var(--text-tertiary,#94a3b8); margin-left: auto; }
.dep-body { display: flex; flex-wrap: wrap; gap: 4px; padding: 4px 0 6px 20px; }

.pod-chip { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; border-radius: 5px; cursor: pointer; font-size: 0.72rem; transition: all 0.1s; color: #fff; font-weight: 500; border: none; }
.pod-chip:hover { filter: brightness(1.1); box-shadow: 0 1px 4px rgba(0,0,0,0.15); }
.pod-chip.bad { outline: 2px solid #ef4444; outline-offset: 1px; }
.pod-chip.pod-running { background: #10b981; }
.pod-chip.pod-pending { background: #f59e0b; }
.pod-chip.pod-failed { background: #ef4444; }
.pod-chip.pod-succeeded { background: #3b82f6; }
.pod-chip.pod-unknown { background: #94a3b8; }
.pname { max-width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pmeta { font-size: 0.6rem; opacity: 0.85; padding: 0 4px; background: rgba(255,255,255,0.15); border-radius: 3px; }
.pwarn { color: #fff; font-size: 0.65rem; }

.svc-chip { display: inline-flex; align-items: center; gap: 5px; padding: 3px 8px; margin: 1px 0; }
.s-icon { width: 15px; height: 15px; border-radius: 3px; color: #fff; font-size: 0.55rem; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.s-name { font-size: 0.76rem; color: var(--text,#1e293b); }
.s-tag { font-size: 0.58rem; padding: 1px 5px; border-radius: 3px; background: rgba(139,92,246,0.1); color: #8b5cf6; }

.side-panel { width: 200px; display: flex; flex-direction: column; gap: 8px; padding: 12px; background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); height: fit-content; }
.panel-title { font-weight: 600; font-size: 0.78rem; color: var(--text,#1e293b); margin-bottom: 4px; }
.stat-list { display: flex; flex-direction: column; gap: 3px; }
.stat-row { display: flex; align-items: center; gap: 6px; font-size: 0.73rem; color: var(--text-secondary,#64748b); }
.sdot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.snum { margin-left: auto; font-weight: 600; color: var(--text,#1e293b); font-size: 0.7rem; }
.detail-card { margin-top: 6px; }
.dc-name { font-weight: 600; font-size: 0.82rem; color: var(--text,#1e293b); margin-bottom: 3px; }
.dc-badge { display: inline-block; padding: 1px 6px; border-radius: 6px; font-size: 0.64rem; font-weight: 600; margin-bottom: 4px; }
.dc-row { display: flex; gap: 5px; font-size: 0.7rem; line-height: 1.5; }
.dk { width: 55px; flex-shrink: 0; color: var(--text-tertiary,#94a3b8); }
.dc-empty { font-size: 0.72rem; color: var(--text-tertiary,#94a3b8); padding: 10px 0; text-align: center; }
</style>
