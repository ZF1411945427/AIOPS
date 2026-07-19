<template>
  <div class="am-page">
    <div class="page-header">
      <h1>审计覆盖矩阵</h1>
      <p>所有写操作自动记录到 audit_logs · 矩阵：写端点 × 是否记审计 × 实际记录数 · 密码字段已脱敏</p>
    </div>

    <!-- 概览卡片 -->
    <div class="summary-grid" v-if="summary && !warning">
      <div class="summary-card ok">
        <div class="summary-label">写端点总数</div>
        <div class="summary-value">{{ summary.total_write_endpoints }}</div>
      </div>
      <div class="summary-card ok">
        <div class="summary-label">能力覆盖率</div>
        <div class="summary-value">{{ (summary.capability_coverage_rate * 100).toFixed(1) }}%</div>
        <div class="summary-sub">中间件可拦截（{{ summary.capability_endpoint_count }}/{{ summary.total_write_endpoints }}）</div>
      </div>
      <div class="summary-card" :class="{ ok: summary.coverage_rate >= 0.8, danger: summary.coverage_rate < 0.5 }">
        <div class="summary-label">实际覆盖率（精确）</div>
        <div class="summary-value">{{ (summary.coverage_rate * 100).toFixed(1) }}%</div>
        <div class="summary-sub">已记录端点（{{ summary.audited_endpoint_count }}/{{ summary.total_write_endpoints }}）</div>
      </div>
      <div class="summary-card" :class="{ ok: summary.type_action_coverage_rate >= 0.8 }">
        <div class="summary-label">类型/动作覆盖</div>
        <div class="summary-value">{{ (summary.type_action_coverage_rate * 100).toFixed(1) }}%</div>
        <div class="summary-sub">同 type/action 有记录（{{ summary.type_action_endpoint_count }}/{{ summary.total_write_endpoints }}）</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">审计日志总数</div>
        <div class="summary-value">{{ summary.total_audit_logs }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">分析时间</div>
        <div class="summary-value-sm">{{ summary.analyzed_at }}</div>
      </div>
    </div>

    <!-- Tab -->
    <div class="panel">
      <div class="panel-head">
        <span>审计明细</span>
        <div class="panel-actions">
          <button class="btn btn-sm" @click="loadMatrix" :disabled="loadingMatrix">{{ loadingMatrix ? '扫描中...' : '重新扫描' }}</button>
        </div>
      </div>
      <div class="tab-bar">
        <button v-for="t in tabs" :key="t.key" class="tab" :class="{ active: activeTab === t.key }" @click="activeTab = t.key">
          {{ t.label }}
          <span class="tab-count">{{ tabCount(t.key) }}</span>
        </button>
      </div>
      <div class="panel-body">
        <div v-if="loadingMatrix && !summary" class="loading-state">扫描所有写端点中...</div>
        <div v-else-if="warning" class="empty-state text-danger">{{ warning }}</div>

        <!-- 矩阵 Tab -->
        <template v-else-if="activeTab === 'matrix'">
          <div class="filter-bar">
            <label class="text-sm">目标类型:
              <select v-model="filterType" class="select-sm">
                <option value="">全部</option>
                <option v-for="t in targetTypes" :key="t" :value="t">{{ t }}</option>
              </select>
            </label>
            <label class="text-sm">仅未精确审计:
              <input type="checkbox" v-model="onlyUnaudited">
            </label>
          </div>
          <table v-if="filteredMatrix.length" class="table">
            <thead>
              <tr><th>方法</th><th>路径</th><th>目标类型</th><th>动作</th><th>精确审计</th><th>类型覆盖</th><th>能力覆盖</th><th>记录数</th></tr>
            </thead>
            <tbody>
              <tr v-for="(m, i) in filteredMatrix" :key="i" :class="{ 'row-warn': !m.audited && m.type_action_covered, 'row-danger': !m.capability_covered }">
                <td><span class="badge" :class="methodClass(m.method)">{{ m.method }}</span></td>
                <td class="text-mono">{{ m.path }}</td>
                <td><span class="badge off">{{ m.target_type }}</span></td>
                <td class="text-sm">{{ m.action }}</td>
                <td>
                  <span v-if="m.audited" class="badge on">是</span>
                  <span v-else class="badge danger">否</span>
                </td>
                <td>
                  <span v-if="m.type_action_covered" class="badge on">是</span>
                  <span v-else class="badge off">否</span>
                </td>
                <td>
                  <span v-if="m.capability_covered" class="badge on">是</span>
                  <span v-else class="badge danger">否</span>
                </td>
                <td>{{ m.records_count }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-state">无匹配项</div>
        </template>

        <!-- 日志 Tab -->
        <template v-else-if="activeTab === 'logs'">
          <div class="filter-bar">
            <label class="text-sm">动作:
              <select v-model="logFilterAction" class="select-sm" @change="loadLogs">
                <option value="">全部</option>
                <option v-for="a in actionList" :key="a" :value="a">{{ a }}</option>
              </select>
            </label>
            <label class="text-sm">用户:
              <input v-model="logFilterUser" class="input-sm" placeholder="用户名" @keyup.enter="loadLogs">
            </label>
            <label class="text-sm">条数:
              <select v-model.number="logLimit" class="select-sm" @change="loadLogs">
                <option :value="50">50</option>
                <option :value="100">100</option>
                <option :value="200">200</option>
              </select>
            </label>
            <button class="btn btn-sm" @click="loadLogs" :disabled="loadingLogs">{{ loadingLogs ? '查询中...' : '查询' }}</button>
          </div>
          <table v-if="logs.length" class="table">
            <thead>
              <tr><th>ID</th><th>用户</th><th>方法</th><th>路径</th><th>动作</th><th>目标</th><th>状态码</th><th>IP</th><th>耗时</th><th>时间</th></tr>
            </thead>
            <tbody>
              <tr v-for="l in logs" :key="l.id">
                <td class="text-mono">{{ l.id }}</td>
                <td class="text-sm">{{ l.username || '-' }}</td>
                <td><span class="badge" :class="methodClass(l.method)">{{ l.method }}</span></td>
                <td class="text-mono">{{ l.path }}</td>
                <td class="text-sm">{{ l.action }}</td>
                <td class="text-sm">{{ l.target_type }}</td>
                <td class="text-mono">{{ l.status_code }}</td>
                <td class="text-sm">{{ l.ip }}</td>
                <td class="text-sm">{{ l.duration_ms }} ms</td>
                <td class="text-sm">{{ l.created_at }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-state">暂无审计日志（写操作会自动记录）</div>
        </template>

        <!-- 分组统计 Tab -->
        <template v-else-if="activeTab === 'group'">
          <div class="group-grid" v-if="summary">
            <div class="group-card">
              <h4>按目标类型（端点数）</h4>
              <table class="table">
                <thead><tr><th>类型</th><th>端点数</th><th>已记录</th></tr></thead>
                <tbody>
                  <tr v-for="(c, t) in summary.by_target_type" :key="t">
                    <td class="text-mono">{{ t }}</td>
                    <td>{{ c }}</td>
                    <td>{{ summary.type_recorded[t] || 0 }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="group-card">
              <h4>按动作（端点数）</h4>
              <table class="table">
                <thead><tr><th>动作</th><th>端点数</th><th>已记录</th></tr></thead>
                <tbody>
                  <tr v-for="(c, a) in summary.by_action" :key="a">
                    <td class="text-mono">{{ a }}</td>
                    <td>{{ c }}</td>
                    <td>{{ summary.action_recorded[a] || 0 }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>

        <!-- 最近样本 Tab -->
        <template v-else-if="activeTab === 'recent'">
          <table v-if="summary && summary.recent_sample.length" class="table">
            <thead><tr><th>用户</th><th>方法</th><th>路径</th><th>动作</th><th>时间</th></tr></thead>
            <tbody>
              <tr v-for="(r, i) in summary.recent_sample" :key="i">
                <td class="text-sm">{{ r.username || '-' }}</td>
                <td><span class="badge" :class="methodClass(r.method)">{{ r.method }}</span></td>
                <td class="text-mono">{{ r.path }}</td>
                <td class="text-sm">{{ r.action }}</td>
                <td class="text-sm">{{ r.created_at }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-state">暂无样本</div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loadingMatrix = ref(false)
const loadingLogs = ref(false)
const warning = ref('')
const summary = ref(null)
const matrix = ref([])
const logs = ref([])
const activeTab = ref('matrix')

const filterType = ref('')
const onlyUnaudited = ref(false)
const logFilterAction = ref('')
const logFilterUser = ref('')
const logLimit = ref(100)

const tabs = [
  { key: 'matrix', label: '审计矩阵' },
  { key: 'logs', label: '审计日志' },
  { key: 'group', label: '分组统计' },
  { key: 'recent', label: '最近样本' },
]

const targetTypes = computed(() => {
  const s = new Set()
  matrix.value.forEach(m => s.add(m.target_type))
  return Array.from(s).sort()
})

const actionList = computed(() => {
  if (!summary.value) return []
  return Object.keys(summary.value.by_action || {}).sort()
})

const filteredMatrix = computed(() => {
  return matrix.value.filter(m => {
    if (filterType.value && m.target_type !== filterType.value) return false
    if (onlyUnaudited.value && m.audited) return false
    return true
  })
})

function tabCount(key) {
  if (key === 'matrix') return matrix.value.length
  if (key === 'logs') return logs.value.length
  if (key === 'group') return summary.value ? Object.keys(summary.value.by_target_type || {}).length : 0
  if (key === 'recent') return summary.value?.recent_sample?.length || 0
  return 0
}

function methodClass(m) {
  return { POST: 'on', PUT: 'warn', PATCH: 'warn', DELETE: 'danger' }[m] || 'off'
}

async function loadMatrix() {
  loadingMatrix.value = true
  warning.value = ''
  try {
    const data = await request.get('/api/admin/audit-matrix')
    if (data.warning) {
      warning.value = data.warning
      ElMessage.warning(data.warning)
    } else {
      summary.value = data.summary
      matrix.value = data.matrix || []
    }
  } catch (e) {
    console.error('audit-matrix:', e)
  } finally {
    loadingMatrix.value = false
  }
}

async function loadLogs() {
  loadingLogs.value = true
  try {
    const params = { limit: logLimit.value }
    if (logFilterAction.value) params.action = logFilterAction.value
    if (logFilterUser.value) params.user = logFilterUser.value
    const data = await request.get('/api/admin/audit-logs', { params })
    if (data.warning) {
      ElMessage.warning(data.warning)
      logs.value = []
    } else {
      logs.value = data.logs || []
    }
  } catch (e) {
    console.error('audit-logs:', e)
  } finally {
    loadingLogs.value = false
  }
}

onMounted(() => {
  loadMatrix()
  loadLogs()
})
</script>

<style scoped>
.am-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 16px; }
.summary-card { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; padding: 12px 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.summary-card.danger { border-left: 3px solid #ef4444; }
.summary-card.ok { border-left: 3px solid #22c55e; }
.summary-card.danger { border-left: 3px solid #ef4444; }
.summary-label { font-size: 0.72rem; color: var(--text-secondary, #64748b); text-transform: uppercase; letter-spacing: 0.3px; margin-bottom: 4px; }
.summary-value { font-size: 1.4rem; font-weight: 700; color: var(--text, #1e293b); }
.summary-value-sm { font-size: 0.9rem; font-weight: 600; color: var(--text, #1e293b); }
.summary-sub { font-size: 0.7rem; color: var(--text-tertiary, #94a3b8); margin-top: 2px; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); display: flex; justify-content: space-between; align-items: center; }
.panel-actions { display: flex; gap: 10px; align-items: center; }
.panel-body { padding: 16px 18px; }
.tab-bar { display: flex; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); padding: 0 18px; }
.tab { padding: 10px 14px; border: none; background: transparent; color: var(--text-secondary, #64748b); cursor: pointer; font-size: 0.85rem; border-bottom: 2px solid transparent; }
.tab.active { color: var(--text, #1e293b); border-bottom-color: #3b82f6; font-weight: 600; }
.tab-count { display: inline-block; min-width: 18px; padding: 1px 5px; border-radius: 8px; background: rgba(100,116,139,0.15); color: #64748b; font-size: 0.7rem; margin-left: 4px; }
.filter-bar { display: flex; gap: 14px; align-items: center; margin-bottom: 14px; flex-wrap: wrap; }
.select-sm, .input-sm { padding: 4px 8px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 4px; font-size: 0.78rem; background: var(--bg-card-solid, #fff); }
.input-sm { min-width: 120px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.72rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; white-space: nowrap; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.table tr.row-warn td { background: rgba(245,158,11,0.04); }
.table tr.row-danger td { background: rgba(239,68,68,0.06); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.text-mono { font-family: 'Consolas', monospace; font-size: 0.8rem; }
.text-danger { color: #ef4444; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.on { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.off { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.warn { background: rgba(245,158,11,0.1); color: #f59e0b; }
.badge.danger { background: rgba(239,68,68,0.1); color: #ef4444; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.group-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 16px; }
.group-card { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; padding: 12px; }
.group-card h4 { margin: 0 0 8px; font-size: 0.85rem; color: var(--text, #1e293b); }
</style>
