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
      <select v-model="clusterFilter" class="input" style="width:160px" @change="loadData">
        <option value="">所有集群</option>
        <option v-for="c in clusters" :key="c.name" :value="c.name">{{ c.name }}</option>
      </select>
      <input v-model="nsFilter" class="input" placeholder="命名空间过滤" style="width:140px" @keyup.enter="loadData" />
      <div class="slider-group">
        <label>CPU 目标利用率</label>
        <input v-model.number="targetCpu" type="range" min="30" max="90" step="5" class="slider" @change="loadData" />
        <span class="slider-val">{{ targetCpu }}%</span>
      </div>
      <div class="slider-group">
        <label>内存目标利用率</label>
        <input v-model.number="targetMem" type="range" min="30" max="90" step="5" class="slider" @change="loadData" />
        <span class="slider-val">{{ targetMem }}%</span>
      </div>
      <select v-model="windowFilter" class="input" style="width:100px" @change="loadData">
        <option value="5m">实时</option>
        <option value="1h">1 小时</option>
        <option value="6h">6 小时</option>
        <option value="24h">24 小时</option>
      </select>
      <button class="btn btn-primary" @click="loadData" :disabled="loading">{{ loading ? '分析中...' : '分析' }}</button>
    </div>

    <div class="panel">
      <div class="panel-head">Deployment HPA 推荐</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">分析中...</div>
        <div v-else-if="!items.length" class="empty-state" style="line-height:1.8">
          <div v-if="warning" class="empty-warning">⚠️ {{ warning }}</div>
          <div v-else>暂无 Deployment 数据</div>
        </div>
        <div v-else class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th>Deployment</th>
                <th>命名空间</th>
                <th>当前副本</th>
                <th>CPU 请求</th>
                <th>内存请求</th>
                <th>CPU 使用率</th>
                <th>内存使用率</th>
                <th>推荐最小副本</th>
                <th>推荐最大副本</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in items" :key="d.name + d.namespace" :class="{ 'needs-hpa': d.needs_hpa }">
                <td>{{ d.name }}</td>
                <td>{{ d.namespace }}</td>
                <td>{{ d.current_replicas }} ({{ d.available_replicas }} 就绪)</td>
                <td>{{ d.cpu_request_m }}m</td>
                <td>{{ d.mem_request_mb }} MB</td>
                <td><span :class="utilClass(d.cpu_util_pct)">{{ d.cpu_util_pct }}%</span></td>
                <td><span :class="utilClass(d.mem_util_pct)">{{ d.mem_util_pct }}%</span></td>
                <td><strong>{{ d.suggested_min_replicas }}</strong></td>
                <td><strong>{{ d.suggested_max_replicas }}</strong></td>
                <td><span class="badge" :class="d.needs_hpa ? 'critical' : 'ok'">{{ d.needs_hpa ? '建议配置HPA' : '正常' }}</span></td>
                <td><button class="btn btn-sm btn-apply" @click="openApply(d)">应用</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div v-if="applyDialog.visible" class="modal-overlay" @click.self="closeApply">
      <div class="modal-box apply-modal">
        <div class="modal-head">
          <h3>应用 HPA 配置 · {{ applyDialog.name }}</h3>
          <button class="modal-close" @click="closeApply">&times;</button>
        </div>
        <div class="modal-body">
          <div class="apply-form">
            <div class="form-row">
              <label>最小副本</label>
              <input v-model.number="applyDialog.min_replicas" type="number" min="1" class="input" style="width:80px" />
            </div>
            <div class="form-row">
              <label>最大副本</label>
              <input v-model.number="applyDialog.max_replicas" type="number" min="1" class="input" style="width:80px" />
            </div>
            <div class="form-row">
              <label>目标 CPU 利用率</label>
              <input v-model.number="applyDialog.target_cpu" type="number" min="10" max="100" class="input" style="width:80px" />%
            </div>
            <div class="form-row">
              <label>目标内存利用率</label>
              <input v-model.number="applyDialog.target_mem" type="number" min="10" max="100" class="input" style="width:80px" />%
            </div>
          </div>
          <div class="yaml-preview">
            <div class="yaml-label">HPA YAML 预览</div>
            <pre class="yaml-block">{{ applyDialog.yaml }}</pre>
          </div>
        </div>
        <div class="modal-foot">
          <button class="btn" @click="closeApply">取消</button>
          <button class="btn btn-primary" :disabled="applyDialog.saving" @click="confirmApply">{{ applyDialog.saving ? '创建中...' : '确认创建 HPA' }}</button>
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
        <p>系统分析 Deployment 的当前资源使用数据：</p>
        <ul>
          <li>统计 <strong>CPU 使用率</strong> 和 <strong>内存使用率</strong></li>
          <li>根据实际负载水平计算所需的最小/最大副本数</li>
          <li>结合 <strong>资源浪费</strong> 与 <strong>性能瓶颈</strong> 给出推荐配置</li>
        </ul>
        <div class="guide-code">推荐副本数 = ceil(当前负载 / 目标利用率阈值)</div>
      </div>
      <div class="guide-section">
        <h4>工具栏说明</h4>
        <ul>
          <li><strong>集群选择</strong> — 切换 K8s 集群</li>
          <li><strong>命名空间过滤</strong> — 按命名空间过滤 Deployment</li>
          <li><strong>目标利用率</strong> — 调节滑块改变 HPA 目标利用率阈值</li>
          <li><strong>时间窗口</strong> — 选择分析数据的时间范围</li>
        </ul>
      </div>
      <div class="guide-section">
        <h4>如何应用推荐</h4>
        <ol>
          <li>查看表格中标记 <span class="tag-demo" style="background:rgba(239,68,68,0.12);color:#ef4444;">建议配置HPA</span> 的 Deployment</li>
          <li>点击「应用」按钮，预览 HPA YAML 配置</li>
          <li>确认后点击「确认创建 HPA」直接创建到集群</li>
        </ol>
      </div>
    </GuideDrawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'
import GuideDrawer from '@/components/GuideDrawer.vue'

const showGuide = ref(false)
const items = ref([])
const clusters = ref([])
const loading = ref(false)
const warning = ref('')
const clusterFilter = ref('')
const nsFilter = ref('')
const targetCpu = ref(50)
const targetMem = ref(50)
const windowFilter = ref('5m')

const applyDialog = ref({
  visible: false,
  name: '',
  namespace: '',
  cluster: '',
  min_replicas: 1,
  max_replicas: 3,
  target_cpu: 50,
  target_mem: 50,
  yaml: '',
  saving: false,
})

async function loadData() {
  loading.value = true
  try {
    const params = {
      target_cpu: targetCpu.value,
      target_mem: targetMem.value,
      window: windowFilter.value,
    }
    if (clusterFilter.value) params.cluster = clusterFilter.value
    if (nsFilter.value) params.namespace = nsFilter.value
    const res = await request.get('/k8s/api/hpa/recommend', { params })
    items.value = res.items || []
    warning.value = res.warning || ''
    if (res.clusters && res.clusters.length > 0) {
      clusters.value = res.clusters
    }
  } catch (e) {
    ElMessage.error('分析失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

async function openApply(d) {
  applyDialog.value.visible = true
  applyDialog.value.name = d.name
  applyDialog.value.namespace = d.namespace
  applyDialog.value.cluster = d.cluster || clusterFilter.value
  applyDialog.value.min_replicas = d.suggested_min_replicas
  applyDialog.value.max_replicas = d.suggested_max_replicas
  applyDialog.value.target_cpu = targetCpu.value
  applyDialog.value.target_mem = targetMem.value
  applyDialog.value.yaml = '正在生成...'
  applyDialog.value.saving = false
  try {
    const res = await request.post('/k8s/api/hpa/recommend/apply', {
      cluster: applyDialog.value.cluster,
      namespace: d.namespace,
      name: d.name,
      min_replicas: d.suggested_min_replicas,
      max_replicas: d.suggested_max_replicas,
      target_cpu: targetCpu.value,
      target_mem: targetMem.value,
      dry_run: true,
    })
    applyDialog.value.yaml = res.yaml || '生成失败'
  } catch (e) {
    applyDialog.value.yaml = '生成失败: ' + (e.message || e)
  }
}

function closeApply() {
  applyDialog.value.visible = false
}

async function confirmApply() {
  applyDialog.value.saving = true
  try {
    const res = await request.post('/k8s/api/hpa/recommend/apply', {
      cluster: applyDialog.value.cluster,
      namespace: applyDialog.value.namespace,
      name: applyDialog.value.name,
      min_replicas: applyDialog.value.min_replicas,
      max_replicas: applyDialog.value.max_replicas,
      target_cpu: applyDialog.value.target_cpu,
      target_mem: applyDialog.value.target_mem,
      dry_run: false,
    })
    if (res.ok) {
      ElMessage.success(`HPA ${res.name} 创建成功`)
      closeApply()
      loadData()
    } else {
      ElMessage.error('创建失败: ' + (res.message || '未知错误'))
    }
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.message || e))
  } finally {
    applyDialog.value.saving = false
  }
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
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; flex-wrap: wrap; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong,rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid,#fff); cursor: pointer; font-size: 0.82rem; }
.btn-primary { background: var(--accent,#6366f1); color: #fff; border-color: var(--accent,#6366f1); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-sm { padding: 3px 10px; font-size: 0.75rem; }
.btn-apply { background: var(--accent,#6366f1); color: #fff; border-color: var(--accent,#6366f1); }
.input { padding: 5px 10px; border: 1px solid var(--border,rgba(0,0,0,0.1)); border-radius: 6px; font-size: 0.82rem; background: var(--bg-card-solid,#fff); color: inherit; }
.slider-group { display: flex; align-items: center; gap: 6px; font-size: 0.75rem; color: var(--text-secondary,#64748b); }
.slider { width: 80px; height: 4px; cursor: pointer; }
.slider-val { font-weight: 600; color: var(--text,#1e293b); min-width: 30px; }
.alert-banner { padding: 10px 14px; margin-bottom: 12px; border-radius: 8px; background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.2); color: #ef4444; font-size: 0.82rem; }
.panel { background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; margin-bottom: 14px; }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; }
.panel-body { padding: 16px 18px; }
.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.table th { text-align: left; padding: 8px 10px; border-bottom: 2px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; color: var(--text-secondary,#64748b); font-size: 0.75rem; text-transform: uppercase; white-space: nowrap; }
.table td { padding: 10px 10px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.05)); white-space: nowrap; }
.table tbody tr:hover { background: var(--bg-hover,rgba(0,0,0,0.02)); }
.needs-hpa { background: rgba(239,68,68,0.04); }
.badge { padding: 2px 8px; border-radius: 6px; font-size: 0.72rem; font-weight: 600; white-space: nowrap; }
.critical { background: rgba(239,68,68,0.12); color: #ef4444; }
.ok { background: rgba(34,197,94,0.12); color: #22c55e; }
.util-high { color: #ef4444; font-weight: 700; }
.util-mid { color: #d97706; font-weight: 600; }
.util-low { color: #22c55e; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary,#94a3b8); font-size: 0.9rem; }
.empty-warning { color: #ef4444; font-size: 0.95rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card,#fff); border-radius: 12px; min-width: 500px; max-width: 680px; max-height: 80vh; display: flex; flex-direction: column; box-shadow: 0 12px 40px rgba(0,0,0,0.15); }
.apply-modal { min-width: 560px; }
.modal-head { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.07)); }
.modal-head h3 { margin: 0; font-size: 1rem; font-weight: 600; }
.modal-close { background: none; border: none; font-size: 1.4rem; cursor: pointer; color: var(--text-secondary,#64748b); padding: 0 4px; }
.modal-body { padding: 16px 20px; overflow-y: auto; flex: 1; }
.modal-foot { padding: 12px 20px; border-top: 1px solid var(--border,rgba(0,0,0,0.07)); display: flex; justify-content: flex-end; gap: 8px; }
.apply-form { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 14px; }
.form-row { display: flex; align-items: center; gap: 8px; font-size: 0.82rem; }
.form-row label { min-width: 90px; color: var(--text-secondary,#64748b); }
.yaml-preview { margin-top: 4px; }
.yaml-label { font-size: 0.8rem; font-weight: 600; margin-bottom: 6px; color: var(--text-secondary,#64748b); }
.yaml-block { background: #1e293b; color: #e2e8f0; padding: 14px; border-radius: 8px; font-size: 0.75rem; line-height: 1.5; overflow-x: auto; white-space: pre; font-family: 'Cascadia Code', 'Fira Code', monospace; max-height: 300px; overflow-y: auto; }
</style>