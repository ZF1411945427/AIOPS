<template>
  <div class="rules-page">
    <div class="page-header">
      <h1>告警规则</h1>
      <p>配置指标阈值告警规则 · 采集到的指标满足条件时自动触发告警 · 共 {{ total }} 条规则</p>
    </div>

    <div class="compare-banner">
      <span class="compare-banner-icon">💡</span>
      <div class="compare-banner-body">
        <div class="compare-banner-title">本页是「静态阈值告警」—— 你设一个固定数字，指标超过就报</div>
        <div class="compare-banner-desc">
          适合"我知道 CPU 超 80% 就有问题"这种有明确危险线的场景。如果不知道正常值多少、想抓行为反常，请用
          <span class="compare-banner-link" @click="goAnomaly">异常检测 →</span>
        </div>
      </div>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="openCreate">+ 新增规则</button>
      <button class="btn" @click="loadRules">刷新</button>
      <span class="toolbar-hint">已采集指标 {{ metrics.length }} 个</span>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="rules.length" class="table">
          <thead>
            <tr>
              <th>ID</th><th>规则名称</th><th>类型</th><th>指标</th><th>条件</th><th>阈值</th>
              <th>级别</th><th>状态</th><th>创建时间</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rules" :key="r.id">
              <td>{{ r.id }}</td>
              <td>{{ r.name }}</td>
              <td><span class="badge kind-{{ r.kind }}">{{ kindLabel(r.kind) }}</span></td>
              <td><code class="metric-code">{{ r.metric_name }}</code></td>
              <td><span class="cond">{{ formatCondition(r.condition) }}</span></td>
              <td><strong>{{ r.threshold }}</strong></td>
              <td><span class="badge" :class="r.severity">{{ severityLabel(r.severity) }}</span></td>
              <td><span class="badge" :class="r.enabled ? 'resolved' : 'info'">{{ r.enabled ? '运行中' : '已禁用' }}</span></td>
              <td class="muted">{{ r.created_at || '-' }}</td>
              <td class="ops">
                <button class="btn btn-sm" @click="toggleRule(r)">{{ r.enabled ? '禁用' : '启用' }}</button>
                <button class="btn btn-sm" @click="openEdit(r)">编辑</button>
                <button class="btn btn-sm btn-danger" @click="deleteRule(r)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">🔔</div>
          <div>暂无告警规则，点击「新增规则」添加</div>
          <div class="empty-hint">提示：规则匹配采集到的指标名（如 cpu_usage、memory_usage、disk_usage），满足条件时触发告警</div>
        </div>
      </div>
    </div>

    <div class="info-cards">
      <div class="info-card">
        <h4>阈值告警</h4>
        <p>当指标值满足「条件 + 阈值」时触发告警。支持 &gt; / &gt;= / &lt; / &lt;= / = 五种条件。</p>
      </div>
      <div class="info-card">
        <h4>告警级别</h4>
        <p><span class="badge critical">critical</span> 严重需立即处理 · <span class="badge warning">warning</span> 警告需关注 · <span class="badge info">info</span> 信息记录</p>
      </div>
      <div class="info-card">
        <h4>规则启停</h4>
        <p>禁用规则后不再触发新告警，但已产生的告警不受影响。可随时重新启用。</p>
      </div>
      <div class="info-card">
        <h4>采集指标</h4>
        <p>规则匹配的指标名来自采集任务（每 60 秒采集一次）。可选指标见新增表单下拉框。</p>
      </div>
    </div>

    <div v-if="formVisible" class="modal-overlay">
      <div class="modal-box">
        <div class="modal-header">
          <h3>{{ formMode === 'create' ? '新增告警规则' : '编辑告警规则' }}</h3>
          <button class="modal-close" @click="formVisible = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>规则类型 *</label>
            <select v-model="form.kind" class="input">
              <option value="metric_raw">metric_raw · 静态阈值（当前值 vs 阈值）</option>
              <option value="anomaly">anomaly · 统计偏离（均值 ± z·σ）</option>
              <option value="forecast">forecast · 趋势预测（外推未来点是否穿越阈值）</option>
              <option value="burn_rate">burn_rate · 燃尽率（错误预算消耗速率）</option>
              <option value="trace_latency">trace_latency · 链路延迟(avg/p99 per service)</option>
              <option value="trace_error_rate">trace_error_rate · 链路错误率(per service)</option>
              <option value="log_match">log_match · 日志关键字命中数</option>
              <option value="log_volume">log_volume · 日志量突增(前后窗口倍数)</option>
            </select>
          </div>
          <div class="form-group">
            <label>规则名称 *</label>
            <input v-model="form.name" class="input" placeholder="如：CPU使用率过高">
          </div>
          <div class="form-row-2">
            <div class="form-group">
              <label>指标名 *</label>
              <select v-model="form.metric_name" class="input">
                <option value="" disabled>请选择</option>
                <option v-for="m in metrics" :key="m" :value="m">{{ m }}</option>
                <option v-if="!metrics.includes(form.metric_name) && form.metric_name" :value="form.metric_name">{{ form.metric_name }}（当前）</option>
              </select>
            </div>
            <div class="form-group">
              <label>条件 *</label>
              <select v-model="form.condition" class="input">
                <option value=">">大于 (&gt;)</option>
                <option value=">=">大于等于 (&gt;=)</option>
                <option value="<">小于 (&lt;)</option>
                <option value="<=">小于等于 (&lt;=)</option>
                <option value="=">等于 (=)</option>
              </select>
            </div>
          </div>
          <div class="form-row-2">
            <div class="form-group">
              <label>阈值 *</label>
              <input v-model.number="form.threshold" class="input" type="number" step="0.1" placeholder="如：90">
            </div>
            <div class="form-group">
              <label>级别 *</label>
              <select v-model="form.severity" class="input">
                <option value="critical">critical（严重）</option>
                <option value="warning">warning（警告）</option>
                <option value="info">info（信息）</option>
              </select>
            </div>
          </div>
          <div class="form-group">
            <label>状态</label>
            <select v-model="form.enabled" class="input">
              <option :value="true">启用</option>
              <option :value="false">禁用</option>
            </select>
          </div>
        </div>
        <div class="form-actions">
          <button class="btn" @click="formVisible = false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="saveRule">{{ saving ? '保存中...' : '保存' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const saving = ref(false)
const rules = ref([])
const total = ref(0)
const metrics = ref([])
const formVisible = ref(false)
const formMode = ref('create')
const editingId = ref(null)
const form = reactive({
  name: '', metric_name: '', condition: '>', threshold: 90,
  severity: 'warning', enabled: true, kind: 'metric_raw',
})

async function loadMetrics() {
  try {
    const data = await request.get('/alerts/api/rules/metrics')
    metrics.value = data.items || []
  } catch (e) {
    metrics.value = ['cpu_usage', 'memory_usage', 'disk_usage', 'swap_usage',
      'cpu_iowait', 'loadavg_1min', 'loadavg_5min', 'loadavg_15min',
      'process_count', 'zombie_process', 'ssh_connections', 'tcp_established',
      'pod_restarts', 'pod_containers', 'deployment_replicas', 'deployment_available',
      'node_cpu_capacity', 'node_memory_capacity']
  }
}

async function loadRules() {
  loading.value = true
  try {
    const data = await request.get('/alerts/api/rules/list')
    rules.value = data.items || []
    total.value = data.total || 0
  } catch (e) {
    ElMessage.error('加载规则失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  formMode.value = 'create'
  editingId.value = null
  Object.assign(form, {
    name: '', metric_name: metrics.value[0] || 'cpu_usage',
    condition: '>', threshold: 90, severity: 'warning', enabled: true, kind: 'metric_raw',
  })
  formVisible.value = true
}

function openEdit(r) {
  formMode.value = 'edit'
  editingId.value = r.id
  Object.assign(form, {
    name: r.name, metric_name: r.metric_name, condition: r.condition,
    threshold: r.threshold, severity: r.severity, enabled: r.enabled,
    kind: r.kind || 'metric_raw',
  })
  formVisible.value = true
}

async function saveRule() {
  if (!form.name.trim()) { ElMessage.warning('请填写规则名称'); return }
  if (!form.metric_name) { ElMessage.warning('请选择指标'); return }
  if (form.threshold === '' || form.threshold === null || Number.isNaN(form.threshold)) {
    ElMessage.warning('请填写阈值'); return
  }
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(), metric_name: form.metric_name,
      condition: form.condition, threshold: Number(form.threshold),
      severity: form.severity, enabled: form.enabled, kind: form.kind,
    }
    if (formMode.value === 'create') {
      await request.post('/alerts/api/rules/create', payload)
    } else {
      await request.post(`/alerts/api/rules/${editingId.value}/update`, payload)
    }
    ElMessage.success(formMode.value === 'create' ? '创建成功' : '更新成功')
    formVisible.value = false
    loadRules()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.message || e))
  } finally {
    saving.value = false
  }
}

async function toggleRule(r) {
  try {
    await request.post(`/alerts/api/rules/${r.id}/toggle`, { enabled: !r.enabled })
    ElMessage.success(r.enabled ? '已禁用' : '已启用')
    loadRules()
  } catch (e) {
    ElMessage.error('操作失败: ' + e.message)
  }
}

async function deleteRule(r) {
  try {
    await ElMessageBox.confirm(`确认删除规则「${r.name}」？删除后不可恢复，但已产生的告警不受影响。`, '删除确认', { type: 'warning' })
    await request.post(`/alerts/api/rules/${r.id}/delete`)
    ElMessage.success('已删除')
    loadRules()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

function formatCondition(c) {
  const map = { '>': '>', '>=': '≥', '<': '<', '<=': '≤', '=': '=' }
  return map[c] || c
}

function severityLabel(s) {
  return ({ critical: 'critical', warning: 'warning', info: 'info' })[s] || s
}

function kindLabel(k) {
  return { metric_raw: 'metric_raw', anomaly: 'anomaly', forecast: 'forecast', burn_rate: 'burn_rate',
           trace_latency: 'trace_latency', trace_error_rate: 'trace_error_rate',
           log_match: 'log_match', log_volume: 'log_volume' }[k] || k
}

function goAnomaly() {
  if (window._navigateTo) window._navigateTo('anomaly')
}

onMounted(() => {
  loadRules()
  loadMetrics()
})
</script>

<style scoped>
.rules-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.compare-banner { display: flex; gap: 10px; align-items: flex-start; background: rgba(99,102,241,0.06); border: 1px solid rgba(99,102,241,0.18); border-left: 3px solid var(--accent, #6366f1); border-radius: 8px; padding: 10px 14px; margin-bottom: 16px; }
.compare-banner-icon { font-size: 1.1rem; line-height: 1.4; }
.compare-banner-body { flex: 1; }
.compare-banner-title { font-size: 0.85rem; font-weight: 600; color: var(--text, #1e293b); margin-bottom: 2px; }
.compare-banner-desc { font-size: 0.78rem; color: var(--text-secondary, #64748b); line-height: 1.5; }
.compare-banner-link { color: var(--accent, #6366f1); cursor: pointer; font-weight: 600; }
.compare-banner-link:hover { text-decoration: underline; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.toolbar-hint { color: var(--text-secondary, #64748b); font-size: 0.78rem; margin-left: 8px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; transition: all 0.2s; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.btn-danger { color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-danger:hover { background: rgba(239,68,68,0.08); }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 16px; }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.table td.ops { white-space: nowrap; }
.table td.ops .btn { margin-right: 4px; }
.metric-code { background: rgba(99,102,241,0.08); color: #6366f1; padding: 2px 6px; border-radius: 4px; font-size: 0.78rem; font-family: 'SF Mono', Consolas, monospace; }
.cond { font-weight: 600; color: var(--accent, #6366f1); padding: 0 4px; }
.muted { color: var(--text-tertiary, #94a3b8); font-size: 0.78rem; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.kind-metric_raw { background: rgba(100,116,139,0.12); color: #64748b; }
.badge.kind-anomaly { background: rgba(139,92,246,0.12); color: #8b5cf6; }
.badge.kind-forecast { background: rgba(59,130,246,0.12); color: #3b82f6; }
.badge.kind-burn_rate { background: rgba(249,115,22,0.12); color: #f97316; }
.badge.critical { background: rgba(239,68,68,0.1); color: #ef4444; }
.badge.warning { background: rgba(245,158,11,0.1); color: #f59e0b; }
.badge.info { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.resolved { background: rgba(34,197,94,0.1); color: #22c55e; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.empty-hint { margin-top: 8px; font-size: 0.78rem; color: var(--text-tertiary, #94a3b8); }
.info-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin-top: 16px; }
.info-card { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; padding: 14px; }
.info-card h4 { margin: 0 0 6px; font-size: 0.9rem; color: var(--accent, #6366f1); }
.info-card p { margin: 0; font-size: 0.78rem; color: var(--text-secondary, #64748b); line-height: 1.5; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 12px; width: 90%; max-width: 560px; max-height: 85vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.2); }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.modal-header h3 { margin: 0; font-size: 1.1rem; }
.modal-close { background: none; border: none; font-size: 24px; cursor: pointer; color: var(--text-secondary, #64748b); line-height: 1; }
.modal-body { padding: 20px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 0.8rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 8px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.85rem; box-sizing: border-box; }
.form-row-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 20px; border-top: 1px solid var(--border, rgba(0,0,0,0.07)); }
</style>
