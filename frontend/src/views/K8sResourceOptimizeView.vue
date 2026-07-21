<template>
  <div class="ro-page">
    <div class="page-header">
      <div class="page-header-row">
        <div>
          <h1>资源优化建议</h1>
          <p>Pod 资源请求/限制分析 · 超配 / 欠配检测</p>
        </div>
        <button class="btn btn-guide" @click="showGuide = true">📖 操作说明</button>
      </div>
    </div>
    <div class="toolbar">
      <input v-model="nsFilter" class="input" placeholder="命名空间过滤" @keyup.enter="loadData" />
      <select v-model="sevFilter" class="input" @change="filterItems">
        <option value="">全部级别</option>
        <option value="critical">Critical</option>
        <option value="warning">Warning</option>
        <option value="ok">OK</option>
      </select>
      <button class="btn btn-primary" @click="loadData">分析</button>
      <button class="btn" @click="loadData">刷新</button>
    </div>
    <div class="stats-grid" v-if="summary">
      <div class="stat-card"><div class="stat-value" style="color:#6366f1;">{{ summary.total }}</div><div class="stat-label">总计</div></div>
      <div class="stat-card"><div class="stat-value" style="color:#ef4444;">{{ summary.critical }}</div><div class="stat-label">严重</div></div>
      <div class="stat-card"><div class="stat-value" style="color:#d97706;">{{ summary.warning }}</div><div class="stat-label">警告</div></div>
      <div class="stat-card"><div class="stat-value" style="color:#22c55e;">{{ summary.ok }}</div><div class="stat-label">正常</div></div>
    </div>
    <div class="panel">
      <div class="panel-head">容器资源诊断</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">分析中...</div>
        <div v-else-if="!filtered.length" class="empty-state">暂无数据</div>
        <div v-else class="table-wrap">
          <table class="table">
            <thead><tr><th>Pod</th><th>命名空间</th><th>容器</th><th>CPU Request</th><th>CPU Limit</th><th>内存 Request</th><th>内存 Limit</th><th>问题</th><th>级别</th></tr></thead>
            <tbody>
              <tr v-for="s in filtered" :key="s.pod_name + s.container" :class="'sev-' + s.severity">
                <td class="pod-cell">{{ s.pod_name }}</td>
                <td>{{ s.namespace }}</td>
                <td>{{ s.container }}</td>
                <td>{{ s.cpu_request_m }}m</td>
                <td>{{ s.cpu_limit_m }}m</td>
                <td>{{ s.mem_request_mb }}Mi</td>
                <td>{{ s.mem_limit_mb }}Mi</td>
                <td><span v-for="iss in s.issues" :key="iss" class="issue-tag">{{ iss }}</span><span v-if="!s.issues.length" class="text-muted">无</span></td>
                <td><span class="badge" :class="s.severity">{{ s.severity }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <GuideDrawer v-model="showGuide" title="📖 资源优化操作说明">
    <div class="guide-section">
      <h4>页面功能</h4>
      <p>本页面分析集群中所有 Pod 的 <strong>资源请求（Requests）</strong> 与 <strong>资源限制（Limits）</strong> 配置，检测 <strong>超配（Over-Provisioning）</strong> 和 <strong>欠配（Under-Provisioning）</strong> 问题，并提供优化建议。</p>
    </div>
    <div class="guide-section">
      <h4>超配 vs 欠配</h4>
      <div class="key-value-list">
        <div class="kv-row">
          <span class="kv-key">超配</span>
          <span class="kv-val">Request/Limit 远高于实际使用，导致集群资源利用率低、浪费成本。</span>
        </div>
        <div class="kv-row">
          <span class="kv-key">欠配</span>
          <span class="kv-val">Request/Limit 不足，Pod 在负载高峰时可能被 OOM Kill 或限流，影响稳定性。</span>
        </div>
      </div>
    </div>
    <div class="guide-section">
      <h4>理解 Request 与 Limit</h4>
      <p>在 Kubernetes 中：</p>
      <ul>
        <li><strong>Request</strong> — 容器保证能获得的最低资源量，调度器据此分配节点</li>
        <li><strong>Limit</strong> — 容器最多能使用的资源上限，超过会被限流或杀死</li>
      </ul>
      <div class="tip-box">
        <strong>💡 最佳实践：</strong> 建议 Limit ≥ Request，且差距不宜过大。通常 Request = 实际使用 × 1.2~1.5，Limit = Request × 1.5~2。
      </div>
    </div>
    <div class="guide-section">
      <h4>如何阅读优化建议</h4>
      <p>每条建议按 <strong>严重级别</strong> 分类：</p>
      <ul>
        <li><span class="tag-demo" style="background:rgba(239,68,68,0.12);color:#ef4444;">Critical</span> — 严重欠配，可能导致 Pod 被杀死</li>
        <li><span class="tag-demo" style="background:rgba(217,119,6,0.12);color:#d97706;">Warning</span> — 资源设置不合理，建议调整</li>
        <li><span class="tag-demo" style="background:rgba(34,197,94,0.12);color:#22c55e;">OK</span> — 当前配置合理</li>
      </ul>
      <p>表格中 <strong>问题列</strong> 会标注具体检测到的问题类型（如 <code>CPU 超配</code>、<code>内存不足</code>）。</p>
    </div>
    <div class="guide-section">
      <h4>应用优化推荐</h4>
      <ol>
        <li>筛选 <strong>Critical</strong> / <strong>Warning</strong> 级别的条目优先处理</li>
        <li>根据问题描述调整对应容器的 <code>resources.requests</code> 和 <code>resources.limits</code></li>
        <li>修改 Deployment / StatefulSet YAML 后重新部署</li>
      </ol>
    </div>
    <div class="guide-section">
      <h4>成本节省潜力</h4>
      <p>通过合理配置资源请求/限制，您可以：</p>
      <ul>
        <li>消除超配导致的资源浪费，提高集群装箱密度</li>
        <li>减少因欠配引发的应用故障和运维介入成本</li>
        <li>在相同集群规模下承载更多业务，降低单位成本</li>
      </ul>
    </div>
  </GuideDrawer>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'
import GuideDrawer from '@/components/GuideDrawer.vue'
const showGuide = ref(false)
const items = ref([])
const filtered = ref([])
const summary = ref(null)
const loading = ref(false)
const nsFilter = ref('')
const sevFilter = ref('')
async function loadData() {
  loading.value = true
  try {
    const params = {}
    if (nsFilter.value) params.namespace = nsFilter.value
    const res = await request.get('/k8s/api/resource-optimization', { params })
    items.value = res.suggestions || []
    summary.value = res.summary
    filterItems()
  } catch (e) { ElMessage.error('分析失败: ' + (e.message || e)) }
  finally { loading.value = false }
}
function filterItems() {
  let list = items.value
  if (sevFilter.value) list = list.filter(s => s.severity === sevFilter.value)
  filtered.value = list
}
onMounted(loadData)
</script>
<style scoped>
.ro-page { padding: 4px; }
.page-header { margin-bottom: 12px; }
.page-header-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.page-header-row > div { flex: 1; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; margin: 0 0 4px; }
.page-header p { color: var(--text-secondary,#64748b); font-size: 0.85rem; margin: 0; }
.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 14px; }
.stat-card { background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; padding: 14px; text-align: center; }
.stat-value { font-size: 1.8rem; font-weight: 800; }
.stat-label { font-size: 0.75rem; color: var(--text-secondary,#64748b); margin-top: 4px; }
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong,rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid,#fff); cursor: pointer; font-size: 0.82rem; }
.btn-primary { background: var(--accent,#6366f1); color: #fff; border-color: var(--accent,#6366f1); }
.input { padding: 5px 10px; border: 1px solid var(--border,rgba(0,0,0,0.1)); border-radius: 6px; font-size: 0.82rem; outline: none; }
.panel { background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; margin-bottom: 14px; }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; }
.panel-body { padding: 16px 18px; }
.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.table th { text-align: left; padding: 8px 10px; border-bottom: 2px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; color: var(--text-secondary,#64748b); font-size: 0.75rem; text-transform: uppercase; }
.table td { padding: 10px 10px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.05)); }
.table tbody tr:hover { background: var(--bg-hover,rgba(0,0,0,0.02)); }
.pod-cell { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sev-critical { background: rgba(239,68,68,0.03); }
.sev-warning { background: rgba(217,119,6,0.03); }
.badge { padding: 2px 8px; border-radius: 6px; font-size: 0.72rem; font-weight: 600; }
.critical { background: rgba(239,68,68,0.12); color: #ef4444; }
.warning { background: rgba(217,119,6,0.12); color: #d97706; }
.ok { background: rgba(34,197,94,0.12); color: #22c55e; }
.issue-tag { display: inline-block; padding: 1px 5px; margin: 1px 2px; background: rgba(239,68,68,0.08); border-radius: 4px; font-size: 0.72rem; color: #ef4444; }
.text-muted { color: var(--text-tertiary,#94a3b8); font-size: 0.78rem; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary,#94a3b8); font-size: 0.9rem; }
</style>
