<template>
  <div class="cc-page">
    <div class="page-header">
      <h1>字段契约检测</h1>
      <p>CONTRACT.md 字段漂移检测：扫描 models.py + routers/*.py 对照契约输出 diff 报告 · 杜绝静默数据丢失</p>
    </div>

    <!-- 概览卡片 -->
    <div class="summary-grid" v-if="summary">
      <div class="summary-card" :class="{ danger: summary.high_confidence_count > 0 }">
        <div class="summary-label">高置信违规</div>
        <div class="summary-value">{{ summary.high_confidence_count }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">违规总数</div>
        <div class="summary-value">{{ summary.total_violations }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">契约表数</div>
        <div class="summary-value">{{ summary.total_tables_in_contract }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">模型表数</div>
        <div class="summary-value">{{ summary.total_tables_in_models }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">契约违规</div>
        <div class="summary-value">{{ summary.contract_violations_count }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">废弃字段</div>
        <div class="summary-value">{{ summary.deprecated_usage_count }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">命名违规</div>
        <div class="summary-value">{{ summary.naming_violations_count }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">长度违规</div>
        <div class="summary-value">{{ summary.length_violations_count }}</div>
      </div>
      <div class="summary-card" :class="{ ok: summary.passed, danger: !summary.passed }">
        <div class="summary-label">检测结论</div>
        <div class="summary-value-sm">{{ summary.passed ? '通过 ✅' : '需修复 ❌' }}</div>
      </div>
    </div>

    <!-- Tab 切换 -->
    <div class="panel">
      <div class="panel-head">
        <span>违规明细</span>
        <div class="panel-actions">
          <button class="btn btn-sm" @click="load" :disabled="loading">{{ loading ? '扫描中...' : '重新扫描' }}</button>
        </div>
      </div>
      <div class="tab-bar">
        <button v-for="t in tabs" :key="t.key" class="tab" :class="{ active: activeTab === t.key }" @click="activeTab = t.key">
          {{ t.label }} <span class="tab-count">{{ tabCount(t.key) }}</span>
        </button>
      </div>
      <div class="panel-body">
        <div v-if="loading && !summary" class="loading-state">扫描中（解析 CONTRACT.md + models.py + routers/*.py）...</div>
        <div v-else-if="warning" class="empty-state text-danger">{{ warning }}</div>
        <div v-else-if="!currentList.length" class="empty-state">该类别无违规</div>
        <table v-else class="table">
          <thead>
            <tr>
              <th>表</th>
              <th>字段</th>
              <th v-if="activeTab === 'contract'">应改为</th>
              <th v-if="activeTab === 'deprecated'">替换为</th>
              <th v-if="activeTab === 'naming'">规则</th>
              <th v-if="activeTab === 'length'">实际/期望</th>
              <th>来源</th>
              <th>置信度</th>
              <th v-if="activeTab === 'contract' || activeTab === 'deprecated'">原因</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(v, i) in currentList" :key="i">
              <td class="text-mono">{{ v.table }}</td>
              <td class="text-mono text-danger">{{ v.field }}</td>
              <td v-if="activeTab === 'contract'" class="text-mono text-success">{{ v.should_be }}</td>
              <td v-if="activeTab === 'deprecated'" class="text-mono text-success">{{ v.replace_with }}</td>
              <td v-if="activeTab === 'naming'" class="text-sm">{{ v.rule }}</td>
              <td v-if="activeTab === 'length'" class="text-mono">{{ v.actual }} / {{ v.expected }}</td>
              <td class="text-sm">
                <span v-if="v.in_models" class="badge on">models.py</span>
                <span v-if="v.router_files && v.router_files.length" class="badge off">
                  {{ v.router_files.join(', ') }}
                </span>
              </td>
              <td>
                <span class="badge" :class="confClass(v.confidence)">{{ v.confidence }}</span>
              </td>
              <td v-if="activeTab === 'contract' || activeTab === 'deprecated'" class="text-sm">{{ v.reason }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const warning = ref('')
const summary = ref(null)
const contractViolations = ref([])
const deprecatedUsage = ref([])
const namingViolations = ref([])
const lengthViolations = ref([])
const activeTab = ref('contract')

const tabs = [
  { key: 'contract', label: '契约违规' },
  { key: 'deprecated', label: '废弃字段' },
  { key: 'naming', label: '命名违规' },
  { key: 'length', label: '长度违规' },
]

const currentList = computed(() => {
  switch (activeTab.value) {
    case 'contract': return contractViolations.value
    case 'deprecated': return deprecatedUsage.value
    case 'naming': return namingViolations.value
    case 'length': return lengthViolations.value
    default: return []
  }
})

function tabCount(key) {
  switch (key) {
    case 'contract': return contractViolations.value.length
    case 'deprecated': return deprecatedUsage.value.length
    case 'naming': return namingViolations.value.length
    case 'length': return lengthViolations.value.length
    default: return 0
  }
}

function confClass(c) {
  if (c === 'high') return 'danger'
  if (c === 'medium') return 'warn'
  return 'off'
}

async function load() {
  loading.value = true
  warning.value = ''
  try {
    const data = await request.get('/api/admin/contract-check')
    if (data.warning) {
      warning.value = data.warning
      ElMessage.warning(data.warning)
    } else {
      summary.value = data.summary
      contractViolations.value = data.contract_violations || []
      deprecatedUsage.value = data.deprecated_usage || []
      namingViolations.value = data.naming_violations || []
      lengthViolations.value = data.length_violations || []
    }
  } catch (e) {
    console.error('contract-check:', e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.cc-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 16px; }
.summary-card { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; padding: 12px 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.summary-card.danger { border-left: 3px solid #ef4444; }
.summary-card.ok { border-left: 3px solid #22c55e; }
.summary-label { font-size: 0.72rem; color: var(--text-secondary, #64748b); text-transform: uppercase; letter-spacing: 0.3px; margin-bottom: 4px; }
.summary-value { font-size: 1.4rem; font-weight: 700; color: var(--text, #1e293b); }
.summary-value-sm { font-size: 0.9rem; font-weight: 600; color: var(--text, #1e293b); }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); display: flex; justify-content: space-between; align-items: center; }
.panel-actions { display: flex; gap: 10px; align-items: center; }
.panel-body { padding: 16px 18px; }
.tab-bar { display: flex; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); padding: 0 18px; }
.tab { padding: 10px 14px; border: none; background: transparent; color: var(--text-secondary, #64748b); cursor: pointer; font-size: 0.85rem; border-bottom: 2px solid transparent; }
.tab.active { color: var(--text, #1e293b); border-bottom-color: #3b82f6; font-weight: 600; }
.tab-count { display: inline-block; min-width: 18px; padding: 1px 5px; border-radius: 8px; background: rgba(100,116,139,0.15); color: #64748b; font-size: 0.7rem; margin-left: 4px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.72rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; white-space: nowrap; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.text-mono { font-family: 'Consolas', monospace; font-size: 0.8rem; }
.text-danger { color: #ef4444; }
.text-success { color: #22c55e; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; margin-right: 4px; }
.badge.on { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.off { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.warn { background: rgba(245,158,11,0.1); color: #f59e0b; }
.badge.danger { background: rgba(239,68,68,0.1); color: #ef4444; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
</style>
