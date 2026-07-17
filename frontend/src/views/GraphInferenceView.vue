<template>
  <div class="gi-page">
    <div class="page-header">
      <h1>知识图谱推理引擎</h1>
      <p>基于拓扑图的智能推理 · 故障传播分析 · 根因定位 · 知识推荐</p>
    </div>

    <!-- Tab 切换 -->
    <div class="tab-bar">
      <button v-for="t in tabs" :key="t.key" :class="['tab-btn', { active: activeTab === t.key }]" @click="activeTab = t.key">
        <span class="tab-icon">{{ t.icon }}</span>
        <span class="tab-label">{{ t.label }}</span>
      </button>
    </div>

    <!-- ── Tab 1: 故障传播分析 ── -->
    <div v-if="activeTab === 'impact'" class="tab-panel">
      <div class="control-bar">
        <label class="ctrl-label">故障源资产</label>
        <select v-model="impactForm.asset_id" class="ctrl-select">
          <option :value="null" disabled>请选择资产</option>
          <option v-for="a in assetOptions" :key="a.id" :value="a.id">{{ a.name }} ({{ a.ci_type }})</option>
        </select>
        <label class="ctrl-label">传播深度</label>
        <select v-model="impactForm.depth" class="ctrl-select narrow">
          <option v-for="d in [1,2,3,4,5]" :key="d" :value="d">{{ d }} 层</option>
        </select>
        <button class="btn btn-primary" @click="runImpact" :disabled="impactLoading || !impactForm.asset_id">
          {{ impactLoading ? '分析中...' : '开始推理' }}
        </button>
      </div>

      <div v-if="impactResult" class="result-section">
        <div class="summary-cards">
          <div class="summary-card"><div class="sum-val">{{ impactResult.summary.total_impacted }}</div><div class="sum-label">受影响资产</div></div>
          <div class="summary-card"><div class="sum-val">{{ impactResult.summary.max_depth_reached }}</div><div class="sum-label">最大传播深度</div></div>
          <div class="summary-card warn"><div class="sum-val">{{ impactResult.summary.high_impact_count }}</div><div class="sum-label">高影响资产</div></div>
          <div class="summary-card danger"><div class="sum-val">{{ impactResult.summary.alert_triggered_count }}</div><div class="sum-label">已触发告警</div></div>
        </div>

        <div class="panel-grid">
          <div class="panel">
            <div class="panel-title">受影响资产列表</div>
            <div class="panel-body">
              <table class="data-table" v-if="impactResult.impacted_assets.length">
                <thead><tr><th>资产</th><th>类型</th><th>深度</th><th>影响概率</th><th>影响评分</th><th>告警</th></tr></thead>
                <tbody>
                  <tr v-for="imp in impactResult.impacted_assets" :key="imp.asset_id" :class="{ 'row-alert': imp.has_active_alert }">
                    <td class="cell-name">{{ imp.asset_name }}</td>
                    <td><span class="badge" :style="typeBadge(imp.ci_type)">{{ imp.ci_type }}</span></td>
                    <td>{{ imp.depth }}</td>
                    <td>{{ (imp.impact_probability * 100).toFixed(1) }}%</td>
                    <td class="score-cell"><div class="score-bar"><div class="score-fill" :style="{ width: (imp.impact_score * 100) + '%', background: scoreColor(imp.impact_score) }"></div></div><span class="score-text">{{ imp.impact_score }}</span></td>
                    <td><span v-if="imp.has_active_alert" class="alert-dot">{{ imp.active_alert_count }}</span><span v-else class="muted">-</span></td>
                  </tr>
                </tbody>
              </table>
              <div v-else class="empty">无受影响资产</div>
            </div>
          </div>

          <div class="panel">
            <div class="panel-title">传播路径可视化</div>
            <div class="panel-body">
              <div v-if="impactResult.propagation_paths.length" class="path-list">
                <div v-for="(p, i) in impactResult.propagation_paths.slice(0, 10)" :key="i" class="path-item">
                  <div class="path-flow">
                    <template v-for="(node, j) in p.path" :key="j">
                      <span :class="['path-node', { root: j === 0, leaf: j === p.path.length - 1 }]">{{ node }}</span>
                      <span v-if="j < p.path.length - 1" class="path-arrow">→</span>
                    </template>
                  </div>
                  <span class="path-depth">{{ p.length }} 跳</span>
                </div>
              </div>
              <div v-else class="empty">无传播路径</div>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-title">智能建议</div>
          <div class="panel-body">
            <ul class="rec-list">
              <li v-for="(r, i) in impactResult.recommendations" :key="i" class="rec-item">{{ r }}</li>
            </ul>
          </div>
        </div>
      </div>
      <div v-else-if="!impactLoading" class="placeholder">选择故障源资产后开始传播分析</div>
    </div>

    <!-- ── Tab 2: 根因定位 ── -->
    <div v-if="activeTab === 'rootcause'" class="tab-panel">
      <div class="control-bar">
        <label class="ctrl-label">告警 ID (逗号分隔)</label>
        <input v-model="rootForm.alert_ids_str" class="ctrl-input" placeholder="如: 1,2,3 (留空则取最近24h告警)" />
        <label class="ctrl-label">时间范围(小时)</label>
        <input v-model.number="rootForm.hours" type="number" min="1" max="168" class="ctrl-input narrow" />
        <button class="btn btn-primary" @click="runRootCause" :disabled="rootLoading">
          {{ rootLoading ? '推理中...' : '开始推理' }}
        </button>
      </div>

      <div v-if="rootResult" class="result-section">
        <div class="summary-cards">
          <div class="summary-card"><div class="sum-val">{{ rootResult.total_alerts_analyzed }}</div><div class="sum-label">分析告警数</div></div>
          <div class="summary-card"><div class="sum-val">{{ rootResult.total_assets_analyzed }}</div><div class="sum-label">涉及资产</div></div>
          <div class="summary-card"><div class="sum-val">{{ (rootResult.root_cause_candidates || []).length }}</div><div class="sum-label">根因候选</div></div>
        </div>

        <div class="panel">
          <div class="panel-title">根因候选排序 (融合评分)</div>
          <div class="panel-body">
            <table class="data-table" v-if="rootResult.root_cause_candidates.length">
              <thead><tr><th>排名</th><th>资产</th><th>类型</th><th>告警</th><th>PageRank</th><th>入度</th><th>传播</th><th>综合</th><th>置信度</th></tr></thead>
              <tbody>
                <tr v-for="c in rootResult.root_cause_candidates" :key="c.asset_id" :class="{ 'row-root': c.confidence === 'high', 'row-candidate': c.confidence === 'medium' }">
                  <td class="rank-cell">#{{ c.rank }}</td>
                  <td class="cell-name">{{ c.asset_name }}</td>
                  <td><span class="badge" :style="typeBadge(c.ci_type)">{{ c.ci_type }}</span></td>
                  <td>{{ c.alert_count }} <span class="muted">({{ c.alert_severity }})</span></td>
                  <td>{{ c.pagerank_score }}</td>
                  <td>{{ c.in_degree_score }}</td>
                  <td>{{ c.alert_propagation_score }}</td>
                  <td class="score-cell"><div class="score-bar"><div class="score-fill" :style="{ width: (c.combined_score * 100) + '%', background: scoreColor(c.combined_score) }"></div></div><span class="score-text">{{ c.combined_score }}</span></td>
                  <td><span :class="['conf-badge', c.confidence]">{{ confLabel(c.confidence) }}</span></td>
                </tr>
              </tbody>
            </table>
            <div v-else class="empty">无根因候选</div>
          </div>
        </div>

        <div class="panel-grid two">
          <div class="panel">
            <div class="panel-title">推理依据</div>
            <div class="panel-body">
              <ul class="rec-list">
                <li v-for="(r, i) in rootResult.reasoning" :key="i" class="rec-item">{{ r }}</li>
              </ul>
            </div>
          </div>
          <div class="panel">
            <div class="panel-title">拓扑传播路径</div>
            <div class="panel-body">
              <div v-if="rootResult.topology_paths.length" class="path-list">
                <div v-for="(p, i) in rootResult.topology_paths" :key="i" class="path-item">
                  <div class="path-flow">
                    <template v-for="(node, j) in p.path" :key="j">
                      <span :class="['path-node', { root: j === 0, leaf: j === p.path.length - 1 }]">{{ node }}</span>
                      <span v-if="j < p.path.length - 1" class="path-arrow">→</span>
                    </template>
                  </div>
                  <span class="path-depth">{{ p.length }} 跳</span>
                </div>
              </div>
              <div v-else class="empty">无拓扑路径 (资产可能无依赖关系)</div>
            </div>
          </div>
        </div>
      </div>
      <div v-else-if="!rootLoading" class="placeholder">输入告警 ID 或留空自动分析最近告警</div>
    </div>

    <!-- ── Tab 3: 知识推荐 ── -->
    <div v-if="activeTab === 'recommend'" class="tab-panel">
      <div class="control-bar">
        <label class="ctrl-label">告警 ID</label>
        <input v-model.number="recForm.alert_id" type="number" min="1" class="ctrl-input narrow" placeholder="告警ID" />
        <span class="ctrl-or">或</span>
        <label class="ctrl-label">资产 ID</label>
        <input v-model.number="recForm.asset_id" type="number" min="1" class="ctrl-input narrow" placeholder="资产ID" />
        <label class="ctrl-label">推荐数</label>
        <input v-model.number="recForm.limit" type="number" min="1" max="50" class="ctrl-input narrow" />
        <button class="btn btn-primary" @click="runRecommend" :disabled="recLoading || (!recForm.alert_id && !recForm.asset_id)">
          {{ recLoading ? '推理中...' : '开始推理' }}
        </button>
      </div>

      <div v-if="recResult" class="result-section">
        <div class="summary-cards">
          <div class="summary-card"><div class="sum-val">{{ recResult.recommendation_count }}</div><div class="sum-label">推荐条目</div></div>
          <div class="summary-card"><div class="sum-val">{{ recResult.graph_context.upstream_count }}</div><div class="sum-label">上游依赖</div></div>
          <div class="summary-card"><div class="sum-val">{{ recResult.graph_context.downstream_count }}</div><div class="sum-label">下游影响</div></div>
        </div>

        <div class="panel">
          <div class="panel-title">关联推理路径</div>
          <div class="panel-body">
            <div class="path-list">
              <div v-for="(p, i) in recResult.association_paths" :key="i" class="path-item">
                <div class="path-flow">
                  <template v-for="(node, j) in p.path" :key="j">
                    <span class="path-node">{{ node }}</span>
                    <span v-if="j < p.path.length - 1" class="path-arrow">→</span>
                  </template>
                </div>
                <span class="path-depth">{{ p.type }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-title">推荐结果 (按评分排序)</div>
          <div class="panel-body">
            <div v-if="recResult.recommendations.length" class="rec-cards">
              <div v-for="(r, i) in recResult.recommendations" :key="i" :class="['rec-card', r.type]">
                <div class="rec-card-header">
                  <span :class="['rec-type-badge', r.type]">{{ typeLabel(r.type) }}</span>
                  <span class="rec-score">评分: {{ r.score }}</span>
                </div>
                <div class="rec-title">{{ r.title }}</div>
                <div class="rec-reasons">
                  <span v-for="(reason, j) in r.match_reasons" :key="j" class="reason-tag">{{ reason }}</span>
                </div>
                <div v-if="r.root_cause" class="rec-detail"><strong>根因:</strong> {{ r.root_cause }}</div>
                <div v-if="r.solution" class="rec-detail"><strong>方案:</strong> {{ r.solution }}</div>
                <div class="rec-meta">
                  <span v-if="r.asset_type" class="meta-tag">类型: {{ r.asset_type }}</span>
                  <span v-if="r.severity" class="meta-tag">级别: {{ r.severity }}</span>
                  <span v-if="r.tags" class="meta-tag">标签: {{ r.tags }}</span>
                </div>
              </div>
            </div>
            <div v-else class="empty">无推荐结果</div>
          </div>
        </div>
      </div>
      <div v-else-if="!recLoading" class="placeholder">输入告警 ID 或资产 ID 后开始知识推荐</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const tabs = [
  { key: 'impact', label: '故障传播分析', icon: '🌐' },
  { key: 'rootcause', label: '根因定位推理', icon: '🎯' },
  { key: 'recommend', label: '知识推荐推理', icon: '📚' },
]
const activeTab = ref('impact')

const assetOptions = ref([])

// ── 故障传播 ──
const impactForm = ref({ asset_id: null, depth: 3 })
const impactLoading = ref(false)
const impactResult = ref(null)

// ── 根因定位 ──
const rootForm = ref({ alert_ids_str: '', hours: 24 })
const rootLoading = ref(false)
const rootResult = ref(null)

// ── 知识推荐 ──
const recForm = ref({ alert_id: null, asset_id: null, limit: 10 })
const recLoading = ref(false)
const recResult = ref(null)

const typeColorMap = {
  server: '#3b82f6', virtual_machine: '#06b6d4', vm: '#06b6d4', container: '#f59e0b',
  pod: '#f97316', service: '#22c55e', database: '#8b5cf6', middleware: '#ec4899',
  storage: '#14b8a6', network: '#64748b', cluster: '#6366f1', kubernetes_cluster: '#6366f1',
  namespace: '#a78bfa', deployment: '#34d399', node: '#94a3b8', application: '#f472b6',
  runbook: '#14b8a6', unknown: '#94a3b8',
}

function typeBadge(t) {
  const c = typeColorMap[t] || '#94a3b8'
  return { background: c + '22', color: c }
}

function scoreColor(s) {
  if (s >= 0.7) return '#ef4444'
  if (s >= 0.4) return '#f59e0b'
  return '#22c55e'
}

function confLabel(c) {
  return { high: '高置信', medium: '中置信', low: '低置信' }[c] || c
}

function typeLabel(t) {
  return { runbook: 'Runbook', knowledge: '知识库', historical_rca: '历史RCA', similar_fault: '相似故障' }[t] || t
}

async function loadAssets() {
  try {
    const data = await request.get('/assets/api/list', { params: { page: 1, page_size: 200 } })
    assetOptions.value = data.items || data.assets || []
  } catch (e) {
    // 降级尝试
    try {
      const data2 = await request.get('/assets/api/list')
      assetOptions.value = data2.items || data2.assets || []
    } catch (e2) {
      console.warn('加载资产列表失败', e2)
    }
  }
}

async function runImpact() {
  impactLoading.value = true
  impactResult.value = null
  try {
    const data = await request.get('/knowledge/graph/api/impact-analysis', {
      params: { asset_id: impactForm.value.asset_id, depth: impactForm.value.depth, include_alerts: true }
    })
    impactResult.value = data
  } catch (e) {
    ElMessage.error('故障传播分析失败: ' + (e.message || e))
  } finally {
    impactLoading.value = false
  }
}

async function runRootCause() {
  rootLoading.value = true
  rootResult.value = null
  try {
    const alertIds = rootForm.value.alert_ids_str
      .split(',').map(s => s.trim()).filter(Boolean).map(Number).filter(n => !isNaN(n) && n > 0)
    const payload = { hours: rootForm.value.hours }
    if (alertIds.length) payload.alert_ids = alertIds
    const data = await request.post('/knowledge/graph/api/root-cause', payload)
    rootResult.value = data
  } catch (e) {
    ElMessage.error('根因定位失败: ' + (e.message || e))
  } finally {
    rootLoading.value = false
  }
}

async function runRecommend() {
  recLoading.value = true
  recResult.value = null
  try {
    const params = { limit: recForm.value.limit }
    if (recForm.value.alert_id) params.alert_id = recForm.value.alert_id
    if (recForm.value.asset_id) params.asset_id = recForm.value.asset_id
    const data = await request.get('/knowledge/graph/api/recommend', { params })
    recResult.value = data
  } catch (e) {
    ElMessage.error('知识推荐失败: ' + (e.message || e))
  } finally {
    recLoading.value = false
  }
}

onMounted(loadAssets)
</script>

<style scoped>
.gi-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }

.tab-bar { display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 2px solid var(--border, rgba(0,0,0,0.07)); }
.tab-btn { display: flex; align-items: center; gap: 6px; padding: 10px 18px; border: none; background: none; cursor: pointer; font-size: 0.88rem; color: var(--text-secondary, #64748b); border-bottom: 2px solid transparent; margin-bottom: -2px; transition: all 0.2s; }
.tab-btn:hover { color: var(--text, #1e293b); }
.tab-btn.active { color: #3b82f6; border-bottom-color: #3b82f6; font-weight: 600; }
.tab-icon { font-size: 1rem; }

.tab-panel { animation: fadeIn 0.3s ease; }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

.control-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; padding: 14px 16px; background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; }
.ctrl-label { font-size: 0.82rem; color: var(--text-secondary, #64748b); white-space: nowrap; }
.ctrl-select, .ctrl-input { padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.85rem; }
.ctrl-select { min-width: 200px; }
.ctrl-select.narrow, .ctrl-input.narrow { min-width: 90px; width: 90px; }
.ctrl-input { min-width: 180px; }
.ctrl-or { color: var(--text-tertiary, #94a3b8); font-size: 0.8rem; }
.btn { padding: 7px 16px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.85rem; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: #3b82f6; color: #fff; border-color: #3b82f6; }
.btn-primary:hover:not(:disabled) { background: #2563eb; }

.result-section { display: flex; flex-direction: column; gap: 12px; }
.summary-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.summary-card { padding: 14px 16px; background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; text-align: center; }
.summary-card.warn { border-color: #f59e0b44; }
.summary-card.danger { border-color: #ef444444; }
.sum-val { font-size: 1.5rem; font-weight: 700; color: var(--text, #1e293b); }
.sum-label { font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-top: 4px; }

.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.panel-title { padding: 12px 16px; font-size: 0.88rem; font-weight: 600; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.panel-body { padding: 14px 16px; }
.panel-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.panel-grid.two { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 900px) { .panel-grid, .panel-grid.two { grid-template-columns: 1fr; } .summary-cards { grid-template-columns: repeat(2, 1fr); } }

.data-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.data-table th { text-align: left; padding: 8px 10px; color: var(--text-secondary, #64748b); font-weight: 600; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-size: 0.78rem; }
.data-table td { padding: 8px 10px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.04)); }
.data-table tr:hover { background: var(--bg-hover, rgba(0,0,0,0.02)); }
.cell-name { font-weight: 500; color: var(--text, #1e293b); }
.row-alert { background: rgba(239,68,68,0.04); }
.row-root { background: rgba(239,68,68,0.08); }
.row-candidate { background: rgba(245,158,11,0.05); }
.rank-cell { font-weight: 700; color: #3b82f6; }
.muted { color: var(--text-tertiary, #94a3b8); font-size: 0.75rem; }
.alert-dot { display: inline-flex; align-items: center; justify-content: center; min-width: 20px; height: 20px; background: #ef4444; color: #fff; border-radius: 10px; font-size: 0.72rem; font-weight: 600; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.72rem; font-weight: 600; }
.conf-badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.72rem; font-weight: 600; }
.conf-badge.high { background: rgba(239,68,68,0.15); color: #ef4444; }
.conf-badge.medium { background: rgba(245,158,11,0.15); color: #f59e0b; }
.conf-badge.low { background: rgba(148,163,184,0.15); color: #94a3b8; }

.score-cell { display: flex; align-items: center; gap: 6px; }
.score-bar { flex: 1; height: 6px; background: var(--bg-hover, rgba(0,0,0,0.06)); border-radius: 3px; overflow: hidden; min-width: 60px; }
.score-fill { height: 100%; border-radius: 3px; transition: width 0.4s; }
.score-text { font-size: 0.75rem; font-weight: 600; min-width: 36px; }

.path-list { display: flex; flex-direction: column; gap: 8px; }
.path-item { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 10px; background: var(--bg-hover, rgba(0,0,0,0.02)); border-radius: 6px; }
.path-flow { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; font-size: 0.82rem; }
.path-node { padding: 3px 8px; background: var(--bg-card-solid, #fff); border: 1px solid var(--border, rgba(0,0,0,0.1)); border-radius: 4px; font-size: 0.78rem; }
.path-node.root { background: rgba(239,68,68,0.1); border-color: #ef4444; color: #ef4444; font-weight: 600; }
.path-node.leaf { background: rgba(59,130,246,0.1); border-color: #3b82f6; color: #3b82f6; }
.path-arrow { color: var(--text-tertiary, #94a3b8); font-size: 0.75rem; }
.path-depth { font-size: 0.72rem; color: var(--text-secondary, #64748b); white-space: nowrap; }

.rec-list { list-style: none; padding: 0; margin: 0; }
.rec-item { padding: 8px 12px; margin-bottom: 6px; background: var(--bg-hover, rgba(0,0,0,0.02)); border-radius: 6px; font-size: 0.82rem; color: var(--text, #1e293b); border-left: 3px solid #3b82f6; }

.rec-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 12px; }
.rec-card { padding: 14px 16px; background: var(--bg-hover, rgba(0,0,0,0.02)); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; border-left: 4px solid #3b82f6; }
.rec-card.runbook { border-left-color: #14b8a6; }
.rec-card.knowledge { border-left-color: #6366f1; }
.rec-card.historical_rca { border-left-color: #f59e0b; }
.rec-card.similar_fault { border-left-color: #8b5cf6; }
.rec-card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.rec-type-badge { padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.rec-type-badge.runbook { background: rgba(20,184,166,0.15); color: #14b8a6; }
.rec-type-badge.knowledge { background: rgba(99,102,241,0.15); color: #6366f1; }
.rec-type-badge.historical_rca { background: rgba(245,158,11,0.15); color: #f59e0b; }
.rec-type-badge.similar_fault { background: rgba(139,92,246,0.15); color: #8b5cf6; }
.rec-score { font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); }
.rec-title { font-size: 0.88rem; font-weight: 600; color: var(--text, #1e293b); margin-bottom: 8px; }
.rec-reasons { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.reason-tag { padding: 2px 6px; background: var(--bg-card-solid, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 4px; font-size: 0.72rem; color: var(--text-secondary, #64748b); }
.rec-detail { font-size: 0.8rem; color: var(--text, #1e293b); margin-top: 6px; line-height: 1.5; }
.rec-meta { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
.meta-tag { font-size: 0.72rem; padding: 1px 6px; background: var(--bg-hover, rgba(0,0,0,0.04)); border-radius: 4px; color: var(--text-secondary, #64748b); }

.empty, .placeholder { text-align: center; padding: 40px; color: var(--text-tertiary, #94a3b8); font-size: 0.88rem; }
.placeholder { padding: 60px 20px; }
</style>
