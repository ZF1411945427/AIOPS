<template>
  <div class="caps-page">
    <div class="page-header">
      <h1>Agent 能力中心</h1>
      <p>工具注册表 · Agent 配置 · 安全策略一览</p>
    </div>

    <div v-if="loading" class="loading-state">加载中...</div>

    <template v-else-if="data">
      <div class="agent-overview">
        <div class="overview-card">
          <div class="card-title">Agent 配置</div>
          <div class="card-row">
            <span class="card-label">状态</span>
            <span class="badge" :class="data.agent_config?.is_enabled ? 'badge-green' : 'badge-gray'">
              {{ data.agent_config?.is_enabled ? '运行中' : '已停用' }}
            </span>
          </div>
          <div class="card-row">
            <span class="card-label">模型</span>
            <span class="card-value">{{ data.provider?.default_model || '未配置' }}</span>
          </div>
          <div class="card-row">
            <span class="card-label">Provider</span>
            <span class="card-value">{{ data.provider?.name || '未配置' }} ({{ data.provider?.provider_type || '-' }})</span>
          </div>
          <div class="card-row">
            <span class="card-label">动作执行</span>
            <span class="card-value">{{ data.agent_config?.allow_action_execution ? '允许' : '禁止' }}</span>
          </div>
          <div class="card-row">
            <span class="card-label">确认机制</span>
            <span class="card-value">{{ data.agent_config?.require_confirmation ? '需要确认' : '免确认' }}</span>
          </div>
          <div class="card-row">
            <span class="card-label">历史消息上限</span>
            <span class="card-value">{{ data.agent_config?.max_history_messages || 12 }} 条</span>
          </div>
        </div>

        <div class="overview-card">
          <div class="card-title">工具概览</div>
          <div class="stat-grid">
            <div class="stat-item">
              <div class="stat-num" style="color:#6366f1">{{ data.stats.total }}</div>
              <div class="stat-desc">全部工具</div>
            </div>
            <div class="stat-item">
              <div class="stat-num" style="color:#22c55e">{{ data.stats.llm_tools }}</div>
              <div class="stat-desc">LLM 可用</div>
            </div>
            <div class="stat-item">
              <div class="stat-num" style="color:#f59e0b">{{ data.stats.internal_tools }}</div>
              <div class="stat-desc">内部执行</div>
            </div>
          </div>
          <div class="meta-row">
            <div class="meta-chip meta-safe"><span class="meta-dot dot-safe"></span>安全 {{ data.stats.safe_count }}</div>
            <div class="meta-chip meta-unsafe"><span class="meta-dot dot-unsafe"></span>需审批 {{ data.stats.unsafe_count }}</div>
          </div>
          <div class="meta-row">
            <div class="meta-chip meta-cloud"><span class="meta-dot dot-cloud"></span>云端 {{ data.stats.location_counts?.cloud || 0 }}</div>
            <div class="meta-chip meta-edge"><span class="meta-dot dot-edge"></span>设备端 {{ data.stats.location_counts?.edge || 0 }}</div>
          </div>
          <div class="risk-bar">
            <div v-for="(count, level) in data.stats.risk_counts" :key="level"
                 class="risk-segment"
                 :class="'risk-' + level"
                 :style="{ width: (count / data.stats.total * 100) + '%' }"
                 :title="level + ': ' + count">
              <span v-if="count > 0">{{ count }}</span>
            </div>
          </div>
          <div class="risk-legend">
            <span v-for="(count, level) in data.stats.risk_counts" :key="level" class="legend-item">
              <span class="legend-dot" :class="'risk-' + level"></span>{{ level }} ({{ count }})
            </span>
          </div>
        </div>
      </div>

      <div class="caps-body">
        <aside class="cat-sidebar">
          <div class="cat-sidebar-title">分类</div>
          <div class="cat-item" :class="{ active: categoryFilter === '' }" @click="categoryFilter = ''">
            <span class="cat-name">全部</span>
            <span class="cat-count">{{ data.tools.length }}</span>
          </div>
          <div v-for="cat in categoryList" :key="cat.name" class="cat-item"
               :class="{ active: categoryFilter === cat.name }" @click="categoryFilter = cat.name">
            <span class="cat-name">{{ categoryLabel(cat.name) }}</span>
            <span class="cat-count">{{ cat.count }}</span>
          </div>
        </aside>

        <div class="panel caps-panel">
        <div class="panel-head">
          <span>工具清单 ({{ filteredTools.length }})</span>
          <div class="panel-actions">
            <input v-model="search" class="search-input" placeholder="搜索工具名/描述..." />
            <select v-model="riskFilter" class="filter-select">
              <option value="">全部风险等级</option>
              <option value="read_only">read_only</option>
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
              <option value="critical">critical</option>
              <option value="advisory">advisory</option>
            </select>
            <select v-model="locationFilter" class="filter-select">
              <option value="">全部位置</option>
              <option value="cloud">云端</option>
              <option value="edge">设备端</option>
              <option value="hybrid">混合</option>
            </select>
            <select v-model="safeFilter" class="filter-select">
              <option value="">全部安全级</option>
              <option value="safe">安全</option>
              <option value="unsafe">需审批</option>
            </select>
            <select v-model="scopeFilter" class="filter-select">
              <option value="">全部范围</option>
              <option value="llm">LLM 可用</option>
              <option value="internal">内部执行</option>
            </select>
          </div>
        </div>
        <div class="panel-body">
          <table class="gap-table">
            <thead>
              <tr>
                <th style="width:30px"></th>
                <th>中文名</th>
                <th>工具名称</th>
                <th>描述</th>
                <th>分类</th>
                <th>位置</th>
                <th>风险</th>
                <th>安全</th>
                <th>可见</th>
                <th>参数</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="tool in filteredTools" :key="tool.name">
                <tr class="tool-row" @click="toggleExpand(tool.name)">
                  <td class="expand-icon">{{ expandedSet.has(tool.name) ? '▼' : '▶' }}</td>
                  <td><span class="tool-display-name">{{ tool.display_name || tool.name }}</span></td>
                  <td><span class="tool-name">{{ tool.name }}</span></td>
                  <td class="tool-desc">{{ tool.description }}</td>
                  <td><span class="cat-badge" :class="'cat-' + tool.category">{{ categoryLabel(tool.category) }}</span></td>
                  <td><span class="loc-badge" :class="'loc-' + tool.location">{{ locationLabel(tool.location) }}</span></td>
                  <td><span class="risk-badge" :class="'risk-' + tool.risk_level">{{ tool.risk_level }}</span></td>
                  <td><span class="safe-badge" :class="tool.safe ? 'safe-yes' : 'safe-no'">{{ tool.safe ? '✓ 安全' : '⚠ 审批' }}</span></td>
                  <td>
                    <span class="scope-badge" :class="tool.expose_to_llm ? 'scope-llm' : 'scope-internal'">
                      {{ tool.expose_to_llm ? 'LLM' : 'Internal' }}
                    </span>
                  </td>
                  <td>{{ Object.keys(tool.input_schema?.properties || {}).length }}</td>
                </tr>
                <tr v-if="expandedSet.has(tool.name)" class="schema-row">
                  <td colspan="10">
                    <div class="schema-panel">
                      <div class="schema-meta">
                        <div class="meta-line"><strong>分类:</strong> {{ categoryLabel(tool.category) }} ({{ tool.category }})</div>
                        <div class="meta-line"><strong>运行位置:</strong> {{ locationLabel(tool.location) }} ({{ tool.location }})</div>
                        <div class="meta-line"><strong>风险等级:</strong> {{ tool.risk_level }}</div>
                        <div class="meta-line"><strong>安全工具:</strong> {{ tool.safe ? '是 — 可由 Agent 直接调用' : '否 — 需经提议-确认闭环' }}</div>
                        <div class="meta-line"><strong>只读工具:</strong> {{ tool.read_only ? '是 — 不变更系统状态' : '否 — 会变更系统状态' }}</div>
                        <div class="meta-line"><strong>AI 可见:</strong> {{ tool.ai_only ? '是 — LLM 可 function calling 调用' : '否 — 仅内部确认路径可调用' }}</div>
                      </div>
                      <div class="schema-title">input_schema</div>
                      <pre class="schema-code">{{ JSON.stringify(tool.input_schema, null, 2) }}</pre>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
          <div v-if="filteredTools.length === 0" class="empty-state">无匹配工具</div>
        </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">安全策略</div>
        <div class="panel-body">
          <div class="policy-grid">
            <div class="policy-item">
              <div class="policy-icon">🔒</div>
              <div class="policy-text">
                <strong>提议-确认闭环</strong>
                <p>LLM 只能调用 <code>propose_action</code> 提议操作，不能直接执行。用户通过「待确认动作」页面确认后才会真正执行。</p>
              </div>
            </div>
            <div class="policy-item">
              <div class="policy-icon">⬆️</div>
              <div class="policy-text">
                <strong>风险等级只升不降</strong>
                <p>提议操作时风险等级只能从登记值升级，不能降级，防止 LLM 诱导用户草率确认高风险操作。</p>
              </div>
            </div>
            <div class="policy-item">
              <div class="policy-icon">🛡️</div>
              <div class="policy-text">
                <strong>内部工具隔离</strong>
                <p><code>execute_*</code> 系列工具标记为 Internal，LLM 无法通过 function calling 直接调用，必须经 PendingAction 闭环。</p>
              </div>
            </div>
            <div class="policy-item">
              <div class="policy-icon">🎯</div>
              <div class="policy-text">
                <strong>幻觉检测</strong>
                <p>LLM 回复声称"已提议"但未实际调用 <code>propose_action</code> 时，自动重试最多 3 次纠正。</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import request from '@/api/request'

const loading = ref(true)
const data = ref(null)
const search = ref('')
const riskFilter = ref('')
const scopeFilter = ref('')
const locationFilter = ref('')
const safeFilter = ref('')
const categoryFilter = ref('')
const expandedSet = ref(new Set())

const CATEGORY_LABELS = {
  alert: '告警', asset: '资产', metric: '指标', incident: '故障',
  change: '变更', knowledge: '知识', k8s: 'K8s', rca: 'RCA',
  execute_host: '主机执行', workflow: '工作流', task: '任务',
  propose: '提议', log: '日志', trace: '链路', mysql: 'MySQL',
  general: '通用',
}
const LOCATION_LABELS = { cloud: '云端', edge: '设备端', hybrid: '混合' }

function categoryLabel(c) { return CATEGORY_LABELS[c] || c }
function locationLabel(l) { return LOCATION_LABELS[l] || l }

const categoryList = computed(() => {
  if (!data.value) return []
  const counts = data.value.stats.category_counts || {}
  return Object.entries(counts).map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count)
})

const filteredTools = computed(() => {
  if (!data.value) return []
  return data.value.tools.filter(t => {
    if (search.value) {
      const q = search.value.toLowerCase()
      const cn = (t.display_name || '').toLowerCase()
      if (!t.name.toLowerCase().includes(q) && !t.description.toLowerCase().includes(q) && !cn.includes(q)) return false
    }
    if (riskFilter.value && t.risk_level !== riskFilter.value) return false
    if (scopeFilter.value === 'llm' && !t.expose_to_llm) return false
    if (scopeFilter.value === 'internal' && t.expose_to_llm) return false
    if (locationFilter.value && t.location !== locationFilter.value) return false
    if (safeFilter.value === 'safe' && !t.safe) return false
    if (safeFilter.value === 'unsafe' && t.safe) return false
    if (categoryFilter.value && t.category !== categoryFilter.value) return false
    return true
  })
})

function toggleExpand(name) {
  const s = new Set(expandedSet.value)
  if (s.has(name)) s.delete(name)
  else s.add(name)
  expandedSet.value = s
}

onMounted(async () => {
  try {
    data.value = await request.get('/agent/api/capabilities')
  } catch (e) {
    console.error('Failed to load capabilities:', e)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.caps-page { padding: 20px; }
.page-header { margin-bottom: 24px; }
.page-header h1 { font-size: 1.4rem; font-weight: 700; margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #888); font-size: 0.85rem; margin: 0; }

.loading-state { text-align: center; padding: 60px; color: var(--text-secondary, #888); }

.agent-overview { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }
.overview-card {
  background: var(--bg-card, #fff); border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px; padding: 20px;
}
.card-title { font-size: 0.9rem; font-weight: 600; margin-bottom: 14px; color: var(--text-primary, #111); }
.card-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-light, #f0f0f0); }
.card-label { font-size: 0.82rem; color: var(--text-secondary, #888); }
.card-value { font-size: 0.82rem; font-weight: 500; }

.badge { padding: 2px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
.badge-green { background: #dcfce7; color: #166534; }
.badge-gray { background: #f3f4f6; color: #6b7280; }

.stat-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; margin-bottom: 16px; }
.stat-item { text-align: center; }
.stat-num { font-size: 1.6rem; font-weight: 700; }
.stat-desc { font-size: 0.75rem; color: var(--text-secondary, #888); }

.risk-bar { display: flex; height: 8px; border-radius: 4px; overflow: hidden; margin-bottom: 8px; }
.risk-segment { display: flex; align-items: center; justify-content: center; font-size: 0; min-width: 0; transition: all 0.3s; }
.risk-segment:hover { min-width: 30px; }
.risk-segment span { font-size: 0.65rem; color: #fff; font-weight: 600; }
.risk-read_only { background: #22c55e; }
.risk-low { background: #3b82f6; }
.risk-medium { background: #f59e0b; }
.risk-high { background: #ef4444; }
.risk-critical { background: #7c3aed; }
.risk-advisory { background: #8b5cf6; }

.risk-legend { display: flex; flex-wrap: wrap; gap: 10px; }
.legend-item { display: flex; align-items: center; gap: 4px; font-size: 0.75rem; color: var(--text-secondary, #888); }
.legend-dot { width: 8px; height: 8px; border-radius: 50%; }

.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, #e5e7eb); border-radius: 10px; margin-bottom: 16px; }
.panel-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 20px; border-bottom: 1px solid var(--border, #e5e7eb);
  font-weight: 600; font-size: 0.9rem;
}
.panel-actions { display: flex; gap: 8px; }
.search-input {
  padding: 6px 12px; border: 1px solid var(--border, #d1d5db); border-radius: 6px;
  font-size: 0.82rem; width: 200px; background: var(--bg-input, #f9fafb);
}
.filter-select {
  padding: 6px 10px; border: 1px solid var(--border, #d1d5db); border-radius: 6px;
  font-size: 0.82rem; background: var(--bg-input, #f9fafb);
}
.panel-body { padding: 0; }

.gap-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.gap-table th {
  text-align: left; padding: 10px 14px; background: var(--bg-table-head, #f8fafc);
  font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border, #e5e7eb);
}
.gap-table td { padding: 10px 14px; border-bottom: 1px solid var(--border-light, #f1f5f9); }

.tool-row { cursor: pointer; transition: background 0.15s; }
.tool-row:hover { background: var(--bg-hover, #f8fafc); }
.expand-icon { color: var(--text-secondary, #94a3b8); font-size: 0.7rem; text-align: center; }
.tool-name { font-weight: 600; color: #6366f1; font-family: 'Fira Code', monospace; font-size: 0.8rem; }
.tool-display-name { font-weight: 600; color: #1e293b; font-size: 0.85rem; }
.tool-desc { color: var(--text-secondary, #64748b); max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.risk-badge {
  padding: 2px 8px; border-radius: 10px; font-size: 0.7rem; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.02em;
}
.risk-read_only { background: #dcfce7; color: #166534; }
.risk-low { background: #dbeafe; color: #1e40af; }
.risk-medium { background: #fef3c7; color: #92400e; }
.risk-high { background: #fee2e2; color: #991b1b; }
.risk-critical { background: #ede9fe; color: #5b21b6; }
.risk-advisory { background: #f3e8ff; color: #6b21a8; }

.scope-badge { padding: 2px 8px; border-radius: 10px; font-size: 0.7rem; font-weight: 600; }
.scope-llm { background: #e0f2fe; color: #075985; }
.scope-internal { background: #fef9c3; color: #854d0e; }

.schema-row td { padding: 0 14px 10px; background: var(--bg-hover, #fafbfc); }
.schema-panel { margin-top: 4px; }
.schema-title { font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); margin-bottom: 6px; }
.schema-code {
  background: #1e293b; color: #e2e8f0; padding: 14px; border-radius: 8px;
  font-size: 0.75rem; overflow-x: auto; margin: 0; line-height: 1.5;
  font-family: 'Fira Code', 'Consolas', monospace;
}

.empty-state { text-align: center; padding: 40px; color: var(--text-secondary, #94a3b8); }

.policy-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 20px; }
.policy-item { display: flex; gap: 12px; padding: 14px; border-radius: 8px; background: var(--bg-hover, #f8fafc); }
.policy-icon { font-size: 1.4rem; flex-shrink: 0; }
.policy-text strong { font-size: 0.85rem; display: block; margin-bottom: 4px; }
.policy-text p { margin: 0; font-size: 0.78rem; color: var(--text-secondary, #64748b); line-height: 1.5; }
.policy-text code { background: #e0e7ff; color: #4338ca; padding: 1px 5px; border-radius: 4px; font-size: 0.73rem; }

@media (max-width: 900px) {
  .agent-overview { grid-template-columns: 1fr; }
  .policy-grid { grid-template-columns: 1fr; }
  .panel-actions { flex-wrap: wrap; }
  .search-input { width: 100%; }
  .caps-body { flex-direction: column; }
  .cat-sidebar { width: 100%; flex-direction: row; overflow-x: auto; }
}

/* ─── Capability Metadata 新增样式 ─── */
.caps-body { display: flex; gap: 16px; margin-bottom: 16px; }
.cat-sidebar {
  width: 180px; flex-shrink: 0; background: var(--bg-card, #fff);
  border: 1px solid var(--border, #e5e7eb); border-radius: 10px; padding: 12px;
  align-self: flex-start;
}
.cat-sidebar-title { font-size: 0.78rem; font-weight: 600; color: var(--text-secondary, #888); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.04em; }
.cat-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 7px 10px; border-radius: 6px; cursor: pointer; font-size: 0.82rem;
  transition: all 0.15s; margin-bottom: 2px;
}
.cat-item:hover { background: var(--bg-hover, #f1f5f9); }
.cat-item.active { background: #eef2ff; color: #4338ca; font-weight: 600; }
.cat-count { font-size: 0.72rem; background: var(--bg-hover, #f1f5f9); padding: 1px 8px; border-radius: 10px; color: var(--text-secondary, #64748b); }
.cat-item.active .cat-count { background: #c7d2fe; color: #3730a3; }
.caps-panel { flex: 1; margin-bottom: 0; min-width: 0; }

.meta-row { display: flex; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
.meta-chip { display: flex; align-items: center; gap: 5px; font-size: 0.75rem; padding: 3px 10px; border-radius: 12px; font-weight: 500; }
.meta-safe { background: #dcfce7; color: #166534; }
.meta-unsafe { background: #fee2e2; color: #991b1b; }
.meta-cloud { background: #e0f2fe; color: #075985; }
.meta-edge { background: #fef3c7; color: #92400e; }
.meta-dot { width: 7px; height: 7px; border-radius: 50%; }
.dot-safe { background: #22c55e; }
.dot-unsafe { background: #ef4444; }
.dot-cloud { background: #0ea5e9; }
.dot-edge { background: #f59e0b; }

.cat-badge { padding: 2px 8px; border-radius: 10px; font-size: 0.7rem; font-weight: 600; white-space: nowrap; }
.cat-alert { background: #fee2e2; color: #991b1b; }
.cat-asset { background: #e0f2fe; color: #075985; }
.cat-metric { background: #f0fdf4; color: #166534; }
.cat-incident { background: #fef3c7; color: #92400e; }
.cat-change { background: #f3e8ff; color: #6b21a8; }
.cat-knowledge { background: #dbeafe; color: #1e40af; }
.cat-k8s { background: #ede9fe; color: #5b21b6; }
.cat-rca { background: #ffedd5; color: #9a3412; }
.cat-execute_host { background: #fecaca; color: #991b1b; }
.cat-workflow { background: #cffafe; color: #155e75; }
.cat-task { background: #f1f5f9; color: #475569; }
.cat-propose { background: #e0e7ff; color: #4338ca; }
.cat-log { background: #ecfeff; color: #155e75; }
.cat-trace { background: #fae8ff; color: #86198f; }
.cat-mysql { background: #fff7ed; color: #9a3412; }
.cat-general { background: #f3f4f6; color: #6b7280; }

.loc-badge { padding: 2px 8px; border-radius: 10px; font-size: 0.7rem; font-weight: 600; white-space: nowrap; }
.loc-cloud { background: #e0f2fe; color: #075985; }
.loc-edge { background: #fef3c7; color: #92400e; }
.loc-hybrid { background: #f3e8ff; color: #6b21a8; }

.safe-badge { padding: 2px 8px; border-radius: 10px; font-size: 0.7rem; font-weight: 600; white-space: nowrap; }
.safe-yes { background: #dcfce7; color: #166534; }
.safe-no { background: #fee2e2; color: #991b1b; }

.schema-meta { background: var(--bg-hover, #f8fafc); border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; }
.meta-line { font-size: 0.78rem; color: var(--text-secondary, #64748b); padding: 3px 0; }
.meta-line strong { color: var(--text-primary, #1e293b); }

</style>
