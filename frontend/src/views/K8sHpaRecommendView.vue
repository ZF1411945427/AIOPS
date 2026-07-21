<template>
  <div class="hpa-page">
    <div class="page-header">
      <div class="page-header-row">
        <div>
          <h1>HPA 配置推荐</h1>
          <p>基于当前资源使用率建议弹性伸缩策略 · 自动扩容建议</p>
        </div>
        <button class="btn btn-guide" @click="showGuide = true">📖 操作说明</button>
      </div>
    </div>
    <div class="toolbar">
      <input v-model="nsFilter" class="input" placeholder="命名空间过滤" @keyup.enter="loadData" />
      <button class="btn btn-primary" @click="loadData">分析</button>
      <button class="btn" @click="loadData">刷新</button>
    </div>
    <div class="panel">
      <div class="panel-head">Deployment HPA 推荐</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">分析中...</div>
        <div v-else-if="!items.length" class="empty-state">暂无 Deployment 数据</div>
        <div v-else class="table-wrap">
          <table class="table">
            <thead><tr><th>Deployment</th><th>命名空间</th><th>当前副本</th><th>CPU 使用率</th><th>内存使用率</th><th>推荐最小副本</th><th>推荐最大副本</th><th>状态</th></tr></thead>
            <tbody>
              <tr v-for="d in items" :key="d.name + d.namespace" :class="{ 'needs-hpa': d.needs_hpa }">
                <td>{{ d.name }}</td>
                <td>{{ d.namespace }}</td>
                <td>{{ d.current_replicas }} ({{ d.available_replicas }} 就绪)</td>
                <td><span :class="utilClass(d.cpu_util_pct)">{{ d.cpu_util_pct }}%</span></td>
                <td><span :class="utilClass(d.mem_util_pct)">{{ d.mem_util_pct }}%</span></td>
                <td><strong>{{ d.suggested_min_replicas }}</strong></td>
                <td><strong>{{ d.suggested_max_replicas }}</strong></td>
                <td><span class="badge" :class="d.needs_hpa ? 'critical' : 'ok'">{{ d.needs_hpa ? '建议配置HPA' : '正常' }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <GuideDrawer v-model="showGuide" title="📖 HPA 配置推荐操作说明">
    <div class="guide-section">
      <h4>什么是 HPA？</h4>
      <p><strong>HPA（Horizontal Pod Autoscaler）</strong> 是 Kubernetes 的横向 Pod 自动伸缩机制。它根据 CPU、内存等资源使用率，自动调整 Deployment 的副本数量，在流量高峰时扩容、低谷时缩容，实现资源与成本的平衡。</p>
    </div>
    <div class="guide-section">
      <h4>推荐引擎原理</h4>
      <p>系统分析 Deployment 在选定时间窗口内的历史监控数据：</p>
      <ul>
        <li>统计 <strong>CPU 使用率</strong> 和 <strong>内存使用率</strong> 的平均值与峰值</li>
        <li>根据实际负载水平计算所需的最小/最大副本数</li>
        <li>结合 <strong>资源浪费</strong> 与 <strong>性能瓶颈</strong> 给出推荐配置</li>
      </ul>
      <div class="guide-code">推荐副本数 = ceil(当前负载 / 目标利用率阈值)</div>
    </div>
    <div class="guide-section">
      <h4>推荐 vs 当前副本</h4>
      <p>表格中每行展示一个 Deployment：</p>
      <ul>
        <li><strong>当前副本</strong> — Deployment 当前运行时副本数（含就绪数）</li>
        <li><strong>CPU / 内存使用率</strong> — 颜色标识：<span class="tag-demo" style="background:rgba(34,197,94,0.12);color:#22c55e;">低</span> <span class="tag-demo" style="background:rgba(217,119,6,0.12);color:#d97706;">中</span> <span class="tag-demo" style="background:rgba(239,68,68,0.12);color:#ef4444;">高</span></li>
        <li><strong>推荐最小/最大副本</strong> — 系统建议的 HPA 边界值</li>
        <li><strong>状态</strong> — 标识当前是否需要配置 HPA</li>
      </ul>
    </div>
    <div class="guide-section">
      <h4>如何应用推荐</h4>
      <ol>
        <li>查看表格中标记 <span class="tag-demo" style="background:rgba(239,68,68,0.12);color:#ef4444;">建议配置HPA</span> 的 Deployment</li>
        <li>参考推荐的最小/最大副本数，创建或更新 HPA 配置</li>
        <li>可通过 <code>kubectl autoscale</code> 命令快速创建 HPA</li>
      </ol>
      <div class="tip-box">
        <strong>💡 提示：</strong> 建议为生产环境的 Deployment 均配置 HPA，目标 CPU 利用率通常设为 60%-80%。
      </div>
    </div>
    <div class="guide-section">
      <h4>目标利用率概念</h4>
      <div class="key-value-list">
        <div class="kv-row">
          <span class="kv-key">目标 CPU 利用率</span>
          <span class="kv-val">HPA 期望 Pod 的 CPU 平均使用率。过高可能导致扩容滞后，过低则浪费资源。</span>
        </div>
        <div class="kv-row">
          <span class="kv-key">目标内存利用率</span>
          <span class="kv-val">HPA 期望 Pod 的内存平均使用率。内存密集型应用需重点关注。</span>
        </div>
      </div>
    </div>
  </GuideDrawer>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'
import GuideDrawer from '@/components/GuideDrawer.vue'
const showGuide = ref(false)
const items = ref([])
const loading = ref(false)
const nsFilter = ref('')
async function loadData() {
  loading.value = true
  try {
    const params = {}
    if (nsFilter.value) params.namespace = nsFilter.value
    const res = await request.get('/k8s/api/hpa/recommend', { params })
    items.value = (res.items || []).filter(d => !nsFilter.value || d.namespace === nsFilter.value)
  } catch (e) { ElMessage.error('分析失败: ' + (e.message || e)) }
  finally { loading.value = false }
}
function utilClass(pct) {
  if (pct > 80) return 'util-high'
  if (pct > 50) return 'util-mid'
  return 'util-low'
}
onMounted(loadData)
</script>
<style scoped>
.hpa-page { padding: 4px; }
.page-header { margin-bottom: 12px; }
.page-header-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.page-header-row > div { flex: 1; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; margin: 0 0 4px; }
.page-header p { color: var(--text-secondary,#64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong,rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid,#fff); cursor: pointer; font-size: 0.82rem; }
.btn-primary { background: var(--accent,#6366f1); color: #fff; border-color: var(--accent,#6366f1); }
.input { padding: 5px 10px; border: 1px solid var(--border,rgba(0,0,0,0.1)); border-radius: 6px; font-size: 0.82rem; }
.panel { background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; margin-bottom: 14px; }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; }
.panel-body { padding: 16px 18px; }
.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.table th { text-align: left; padding: 8px 10px; border-bottom: 2px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; color: var(--text-secondary,#64748b); font-size: 0.75rem; text-transform: uppercase; }
.table td { padding: 10px 10px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.05)); }
.table tbody tr:hover { background: var(--bg-hover,rgba(0,0,0,0.02)); }
.needs-hpa { background: rgba(239,68,68,0.04); }
.badge { padding: 2px 8px; border-radius: 6px; font-size: 0.72rem; font-weight: 600; }
.critical { background: rgba(239,68,68,0.12); color: #ef4444; }
.ok { background: rgba(34,197,94,0.12); color: #22c55e; }
.util-high { color: #ef4444; font-weight: 700; }
.util-mid { color: #d97706; font-weight: 600; }
.util-low { color: #22c55e; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary,#94a3b8); font-size: 0.9rem; }
</style>
