<template>
  <div class="sr-page">
    <div class="page-header">
      <h1>智能推荐</h1>
      <p>规则匹配 + RAG 语义检索 融合推荐</p>
    </div>

    <div class="toolbar">
      <input v-model="alertId" class="input search-input" placeholder="输入告警 ID" @keyup.enter="runRecommend">
      <input v-model.number="limit" class="input limit-input" type="number" min="1" max="20" placeholder="数量">
      <button class="btn btn-primary" @click="runRecommend" :disabled="loading">{{ loading ? '查询中...' : '查询推荐' }}</button>
      <button class="btn btn-help" @click="showLogic = true">逻辑说明</button>
    </div>

    <div v-if="showLogic" class="modal-overlay" @click.self="showLogic = false">
      <div class="modal-box">
        <h3>推荐算法逻辑说明</h3>
        <div class="logic-section">
          <div class="logic-title">数据源</div>
          <div class="logic-row"><span class="logic-tag tag-rule">规则匹配</span> 从 knowledge_base 表扫描所有知识条目，基于告警特征打分排序</div>
          <div class="logic-row"><span class="logic-tag tag-rag">RAG 语义</span> 用告警的指标名+消息作为 query，通过 BGE-small 向量 + BM25 关键词混合检索 Milvus 文档切片</div>
        </div>
        <div class="logic-section">
          <div class="logic-title">规则打分维度</div>
          <table class="logic-table">
            <tr><td class="lt-score">+5</td><td>指标名匹配知识标签（模糊匹配，如 cpu_usage 包含 cpu）</td></tr>
            <tr><td class="lt-score">+3</td><td>指标名出现在知识标题中</td></tr>
            <tr><td class="lt-score">+3</td><td>告警资产类型与知识资产类型一致</td></tr>
            <tr><td class="lt-score">+2</td><td>告警级别与知识级别完全一致</td></tr>
            <tr><td class="lt-score">+1</td><td>告警级别与知识级别相邻（如 critical vs warning）</td></tr>
            <tr><td class="lt-score">+0~4</td><td>告警消息与知识症状的关键词重叠比例</td></tr>
          </table>
        </div>
        <div class="logic-section">
          <div class="logic-title">融合策略</div>
          <div class="logic-row">规则分归一化到 0~1 后 × 0.5 权重</div>
          <div class="logic-row">RAG 语义分 × 0.5 权重</div>
          <div class="logic-row">同一标题命中两路时分数相加，上限 1.0（100%）</div>
        </div>
        <div class="logic-section">
          <div class="logic-title">来源标签</div>
          <div class="logic-row"><span class="logic-tag tag-rule">规则</span> 仅规则匹配命中</div>
          <div class="logic-row"><span class="logic-tag tag-rag">RAG</span> 仅语义检索命中</div>
          <div class="logic-row"><span class="logic-tag tag-both">融合</span> 两路同时命中，相关性最高</div>
        </div>
        <div class="modal-actions"><button class="btn" @click="showLogic = false">知道了</button></div>
      </div>
    </div>

    <div v-if="sources" class="source-bar">
      <span class="source-item">规则匹配 {{ sources.rule }} 条</span>
      <span class="source-sep">+</span>
      <span class="source-item">RAG 语义 {{ sources.rag }} 条</span>
    </div>

    <div v-if="alert" class="panel">
      <div class="panel-head">告警信息</div>
      <div class="panel-body">
        <div class="alert-grid">
          <div class="alert-field"><span class="alert-label">告警 ID</span><span class="alert-val">{{ alert.id }}</span></div>
          <div class="alert-field"><span class="alert-label">指标</span><span class="alert-val">{{ alert.metric_name || alert.metric || alert.name || '-' }}</span></div>
          <div class="alert-field"><span class="alert-label">当前值</span><span class="alert-val">{{ alert.current_value ?? alert.value ?? '-' }}</span></div>
          <div class="alert-field"><span class="alert-label">级别</span><span class="badge" :class="sevClass(alert.severity)">{{ alert.severity || '-' }}</span></div>
          <div class="alert-field"><span class="alert-label">状态</span><span class="badge" :class="statusClass(alert.status)">{{ alert.status || '-' }}</span></div>
          <div class="alert-field"><span class="alert-label">时间</span><span class="alert-val">{{ alert.triggered_at || alert.created_at || '-' }}</span></div>
        </div>
        <div v-if="alert.message" class="alert-msg">{{ alert.message }}</div>
      </div>
    </div>

    <div class="panel" style="margin-top:14px;">
      <div class="panel-head">推荐知识 · {{ recommendations.length }} 条</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">查询中...</div>
        <div v-else-if="searched && !recommendations.length" class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">🔍</div>
          <div>暂无匹配推荐</div>
        </div>
        <div v-else-if="!searched" class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">💡</div>
          <div>输入告警 ID 查询智能推荐</div>
        </div>
        <div v-else class="rec-list">
          <div v-for="(r, i) in recommendations" :key="i" class="rec-item">
            <div class="rec-head">
              <span class="rec-rank">#{{ i + 1 }}</span>
              <span class="rec-title">{{ r.kb?.title || r.title || '未命名' }}</span>
              <span class="source-tag" :class="'src-' + r.source">{{ sourceLabel(r.source) }}</span>
              <span class="rec-score">{{ (r.score * 100).toFixed(1) }}%</span>
              <span v-if="r.linked" class="badge linked">已关联</span>
            </div>
            <div v-if="r.kb?.severity || r.kb?.tags" class="rec-meta">
              <span v-if="r.kb.severity" class="badge" :class="sevClass(r.kb.severity)">{{ r.kb.severity }}</span>
              <span v-for="t in tagList(r.kb.tags)" :key="t" class="tag-mini">{{ t }}</span>
            </div>
            <div v-if="r.content" class="rec-block">
              <span class="rec-label">RAG 片段</span>
              <div class="rec-text rag-content">{{ r.content }}</div>
            </div>
            <div v-if="r.reasons && r.reasons.length" class="rec-reasons">
              <span v-for="(reason, ri) in r.reasons" :key="ri" class="reason-tag">{{ reasonLabel(reason) }}</span>
            </div>
            <div v-if="r.kb?.symptom" class="rec-block"><span class="rec-label">症状</span><div class="rec-text">{{ r.kb.symptom }}</div></div>
            <div v-if="r.kb?.root_cause" class="rec-block"><span class="rec-label">根因</span><div class="rec-text">{{ r.kb.root_cause }}</div></div>
            <div v-if="r.kb?.solution" class="rec-block"><span class="rec-label">解决方案</span><div class="rec-text">{{ r.kb.solution }}</div></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const searched = ref(false)
const showLogic = ref(false)
const alertId = ref('')
const limit = ref(5)
const alert = ref(null)
const recommendations = ref([])
const sources = ref(null)

function sourceLabel(s) {
  const m = { rule: '规则', rag: 'RAG', both: '融合' }
  return m[s] || s
}

function reasonLabel(r) {
  if (!r) return ''
  if (r.startsWith('metric_tag:')) return '指标标签: ' + r.split(':')[1]
  if (r === 'metric_in_title') return '标题匹配'
  if (r === 'severity_exact') return '级别一致'
  if (r === 'severity_adjacent') return '级别相邻'
  if (r === 'asset_type_match') return '资产类型匹配'
  if (r.startsWith('text_overlap:')) return '关键词: ' + r.split(':')[1]
  if (r === 'rag_semantic') return '语义匹配'
  return r
}

function tagList(tags) {
  if (!tags) return []
  if (Array.isArray(tags)) return tags
  return String(tags).split(',').map(t => t.trim()).filter(Boolean)
}

function sevClass(s) {
  const m = { critical: 'sev-critical', high: 'sev-high', warning: 'sev-warning', info: 'sev-info' }
  return m[s] || 'sev-info'
}

function statusClass(s) {
  if (s === 'resolved') return 'st-resolved'
  if (s === 'acknowledged') return 'st-ack'
  if (s === 'triggered') return 'st-triggered'
  return 'st-other'
}

async function runRecommend() {
  if (!alertId.value) {
    ElMessage.warning('请输入告警 ID')
    return
  }
  loading.value = true
  searched.value = true
  try {
    const params = { alert_id: alertId.value }
    if (limit.value) params.limit = limit.value
    const data = await request.get('/smart-recommend/api/recommend', { params })
    alert.value = data.alert || null
    recommendations.value = data.recommendations || []
    sources.value = data.sources || null
  } catch (e) {
    ElMessage.error('查询失败: ' + (e.message || e))
    alert.value = null
    recommendations.value = []
    sources.value = null
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.sr-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; }
.search-input { min-width: 240px; }
.limit-input { width: 100px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.source-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; padding: 8px 14px; background: rgba(99,102,241,0.06); border-radius: 8px; font-size: 0.82rem; color: var(--accent, #6366f1); font-weight: 500; }
.source-sep { color: var(--text-tertiary, #94a3b8); }
.source-item { font-weight: 600; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); }
.panel-body { padding: 16px 18px; }
.alert-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.alert-field { display: flex; flex-direction: column; gap: 4px; padding: 8px 10px; background: var(--bg-hover, rgba(0,0,0,0.03)); border-radius: 6px; }
.alert-label { font-size: 0.72rem; color: var(--text-secondary, #64748b); }
.alert-val { font-size: 0.85rem; color: var(--text, #1e293b); font-weight: 500; }
.alert-msg { margin-top: 10px; padding: 10px; background: rgba(245,158,11,0.06); border-left: 3px solid #f59e0b; border-radius: 4px; font-size: 0.82rem; color: var(--text, #1e293b); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.sev-critical { background: rgba(239,68,68,0.12); color: #ef4444; }
.sev-high { background: rgba(249,115,22,0.12); color: #f97316; }
.sev-warning { background: rgba(245,158,11,0.12); color: #d97706; }
.sev-info { background: rgba(59,130,246,0.12); color: #3b82f6; }
.st-resolved { background: rgba(34,197,94,0.12); color: #22c55e; }
.st-ack { background: rgba(245,158,11,0.12); color: #d97706; }
.st-triggered { background: rgba(239,68,68,0.12); color: #ef4444; }
.st-other { background: rgba(148,163,184,0.12); color: #64748b; }
.badge.linked { background: rgba(34,197,94,0.12); color: #22c55e; }
.rec-list { display: flex; flex-direction: column; gap: 12px; }
.rec-item { padding: 12px 14px; border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; background: var(--bg-hover, rgba(0,0,0,0.02)); }
.rec-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.rec-rank { font-size: 0.78rem; font-weight: 700; color: var(--accent, #6366f1); background: rgba(99,102,241,0.1); padding: 2px 8px; border-radius: 8px; }
.rec-title { font-size: 0.92rem; font-weight: 600; color: var(--text, #1e293b); flex: 1; }
.rec-score { font-size: 0.72rem; font-weight: 700; color: #22c55e; background: rgba(34,197,94,0.1); padding: 2px 8px; border-radius: 8px; }
.source-tag { font-size: 0.68rem; font-weight: 600; padding: 2px 6px; border-radius: 4px; }
.src-rule { background: rgba(59,130,246,0.1); color: #3b82f6; }
.src-rag { background: rgba(168,85,247,0.1); color: #a855f7; }
.src-both { background: rgba(34,197,94,0.1); color: #22c55e; }
.rec-meta { display: flex; gap: 6px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.tag-mini { display: inline-block; padding: 1px 6px; border-radius: 4px; background: rgba(99,102,241,0.08); color: var(--accent, #6366f1); font-size: 0.7rem; margin-right: 4px; }
.rec-block { margin-top: 6px; }
.rec-label { font-size: 0.72rem; color: var(--text-secondary, #64748b); font-weight: 600; }
.rec-text { margin-top: 4px; font-size: 0.82rem; color: var(--text, #1e293b); line-height: 1.5; white-space: pre-wrap; }
.rag-content { background: rgba(168,85,247,0.04); border-left: 3px solid #a855f7; padding: 8px 10px; border-radius: 0 6px 6px 0; font-size: 0.8rem; color: #475569; }
.rec-reasons { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 6px; }
.reason-tag { font-size: 0.68rem; padding: 1px 6px; border-radius: 4px; background: rgba(59,130,246,0.08); color: #3b82f6; font-weight: 500; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.btn-help { border-color: rgba(99,102,241,0.3); color: var(--accent, #6366f1); }
.btn-help:hover { background: rgba(99,102,241,0.06); }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 12px; padding: 24px 28px; min-width: 520px; max-width: 600px; max-height: 80vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.15); }
.modal-box h3 { margin: 0 0 16px; font-size: 1.05rem; font-weight: 600; color: var(--text, #1e293b); }
.modal-actions { margin-top: 18px; display: flex; justify-content: flex-end; }
.logic-section { margin-bottom: 16px; }
.logic-title { font-size: 0.82rem; font-weight: 700; color: var(--accent, #6366f1); margin-bottom: 6px; padding-bottom: 4px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.logic-row { font-size: 0.8rem; color: var(--text, #1e293b); line-height: 1.6; padding: 3px 0; }
.logic-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
.logic-table td { padding: 4px 8px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.04)); vertical-align: top; }
.lt-score { font-weight: 700; color: var(--accent, #6366f1); white-space: nowrap; width: 36px; }
.logic-tag { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; margin-right: 4px; }
.tag-rule { background: rgba(59,130,246,0.1); color: #3b82f6; }
.tag-rag { background: rgba(168,85,247,0.1); color: #a855f7; }
.tag-both { background: rgba(34,197,94,0.1); color: #22c55e; }
</style>
