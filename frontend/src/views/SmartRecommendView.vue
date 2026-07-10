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
      <div class="modal-box modal-wide">
        <h3>推荐算法 · 通俗易懂版</h3>

        <div class="logic-section">
          <div class="logic-title">整体流程</div>
          <div class="logic-flow">
            <span class="flow-box flow-alert">告警进来</span>
            <span class="flow-arrow">→</span>
            <span class="flow-box flow-split">两路同时查</span>
            <span class="flow-arrow">→</span>
            <span class="flow-box flow-merge">合并排序</span>
            <span class="flow-arrow">→</span>
            <span class="flow-box flow-out">推荐结果</span>
          </div>
          <div class="logic-row" style="margin-top:8px;color:#64748b;font-size:0.78rem;">
            告警触发后，系统同时去两个地方找相关知识，然后把结果合并排序，挑出最相关的推荐给你。
          </div>
        </div>

        <div class="logic-section">
          <div class="logic-title">两路数据源</div>
          <div class="logic-row"><span class="logic-tag tag-rule">规则匹配</span> <b>故障知识库</b>（knowledge_base 表）—— 运维人员手动录入的结构化经验，每条包含：标题、故障症状、根因、解决方案、标签。系统逐条扫描，用规则给每条知识打分。</div>
          <div class="logic-row" style="margin-top:6px;"><span class="logic-tag tag-rag">RAG 语义</span> <b>知识库文档</b>（kb_documents + Milvus）—— 上传的 Markdown/TXT/PDF 文档，被切成小段落（切片），每段转成向量存入 Milvus 数据库。系统用告警信息作为搜索词，找出语义最相关的文档片段。</div>
        </div>

        <div class="logic-section">
          <div class="logic-title">规则打分维度</div>
          <table class="logic-table">
            <tr><td class="lt-score">+5</td><td><b>指标标签匹配</b>：告警的指标名（如 cpu_usage）和知识的标签（如 ["cpu","性能"]）模糊匹配</td></tr>
            <tr><td class="lt-score">+3</td><td><b>标题匹配</b>：告警指标名出现在知识标题中（如 cpu_usage 出现在"CPU 使用率过高排查"）</td></tr>
            <tr><td class="lt-score">+3</td><td><b>资产类型匹配</b>：告警所属资产类型和知识的目标资产类型一致</td></tr>
            <tr><td class="lt-score">+2</td><td><b>级别完全一致</b>：告警级别和知识级别相同（如都是 critical）</td></tr>
            <tr><td class="lt-score">+1</td><td><b>级别相邻</b>：级别差一级（如 critical 和 warning）</td></tr>
            <tr><td class="lt-score">+0~4</td><td><b>文本重叠</b>：告警消息和知识症状描述的关键词重叠越多分越高</td></tr>
          </table>
        </div>

        <div class="logic-section">
          <div class="logic-title">融合策略</div>
          <div class="logic-row">两路各占 50% 权重，最终得分 = 规则归一化分 × 0.5 + RAG 语义分 × 0.5</div>
          <div class="logic-row">同一条知识两路都命中时，分数相加（上限 100%），标记为「融合」</div>
          <div class="logic-row">排序优先级：融合 > 规则 > RAG（结构化知识排前面，文档片段补充在后面）</div>
        </div>

        <div class="logic-section">
          <div class="logic-title">来源标签</div>
          <div class="logic-row"><span class="logic-tag tag-rule">规则</span> 只在故障知识库中匹配到</div>
          <div class="logic-row"><span class="logic-tag tag-rag">RAG</span> 只在上传的文档中匹配到</div>
          <div class="logic-row"><span class="logic-tag tag-both">融合</span> 两路都匹配到，相关性最高</div>
        </div>

        <div class="logic-section">
          <div class="logic-title">术语表（点击查看解释）</div>
          <div class="glossary-grid">
            <div class="glossary-item" v-for="g in glossary" :key="g.term">
              <div class="gloss-term">{{ g.term }}</div>
              <div class="gloss-en" v-if="g.en">{{ g.en }}</div>
              <div class="gloss-desc">{{ g.desc }}</div>
            </div>
          </div>
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

    <div v-if="runbooks.length" class="panel" style="margin-top:14px;">
      <div class="panel-head">推荐操作流程 · {{ runbooks.length }} 条</div>
      <div class="panel-body">
        <div class="rec-list">
          <div v-for="(rb, i) in runbooks" :key="i" class="rec-item rb-item">
            <div class="rec-head">
              <span class="rec-rank rb-rank">RB#{{ rb.runbook.id }}</span>
              <span class="rec-title">{{ rb.runbook.title }}</span>
              <span class="source-tag src-runbook">Runbook</span>
              <span class="rec-score">{{ (rb.score * 100).toFixed(1) }}%</span>
            </div>
            <div class="rec-meta">
              <span class="badge" :class="sevClass(rb.runbook.severity)">{{ rb.runbook.severity }}</span>
              <span class="tag-mini">{{ rb.runbook.category }}</span>
              <span v-for="t in tagList(rb.runbook.tags)" :key="t" class="tag-mini">{{ t }}</span>
            </div>
            <div v-if="rb.reasons && rb.reasons.length" class="rec-reasons">
              <span v-for="(reason, ri) in rb.reasons" :key="ri" class="reason-tag">{{ reasonLabel(reason) }}</span>
            </div>
            <div v-if="rb.runbook.symptom" class="rec-block"><span class="rec-label">症状</span><div class="rec-text">{{ rb.runbook.symptom }}</div></div>
            <div v-if="rb.runbook.diagnosis" class="rec-block"><span class="rec-label">诊断</span><div class="rec-text">{{ rb.runbook.diagnosis }}</div></div>
            <div v-if="rb.runbook.steps" class="rec-block">
              <span class="rec-label">操作步骤</span>
              <div class="rec-text rb-steps">{{ rb.runbook.steps }}</div>
            </div>
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

const glossary = [
  { term: '召回率', en: 'Recall', desc: '搜出来的相关知识占所有相关知识的比例。比如知识库里有10条相关知识，系统搜出来7条，召回率就是70%。召回率低 = 漏推了。' },
  { term: '准确率', en: 'Precision', desc: '搜出来的知识里，真正相关的比例。系统推荐了5条，其中4条确实有用，准确率就是80%。准确率低 = 推了一堆没用的。' },
  { term: '分片 / 切片', en: 'Chunk', desc: '一篇长文档被切成的一小段。比如一份10000字的排查手册，按2000字一段切成5个切片，每段独立做向量检索。' },
  { term: '切片长度', en: 'max_chars', desc: '每个切片最多保留多少个字符。太短会丢失上下文，太长会混入无关内容。当前设为2000字符。' },
  { term: '重叠', en: 'Overlap', desc: '相邻切片之间重复的内容。当前设为200字，目的是避免在段落中间硬切断导致信息丢失。' },
  { term: 'Embedding', en: 'Embedding', desc: '把一段文字转成一串数字（向量），比如"CPU使用率过高"变成 [0.12, -0.34, 0.56, ...]。语义相近的文字，数字也相近，计算机就能算出"谁和谁像"。' },
  { term: '向量相似度', en: 'Cosine Similarity', desc: '两段文字转成向量后，算它们之间的"夹角"。夹角越小越相似，分值0~1。比如"CPU占用高"和"CPU使用率过高"相似度可能0.95。' },
  { term: '向量数据库', en: 'Vector DB (Milvus)', desc: '专门用来存和搜向量的数据库。普通数据库搜"文字完全一样"，向量数据库搜"意思差不多"。当前用的是Milvus Lite（本地轻量版）。' },
  { term: 'RAG', en: 'Retrieval-Augmented Generation', desc: '检索增强生成。先从知识库里检索（Retrieval）相关文档，再用这些文档辅助回答问题。本系统只做了"检索"部分，还没接大模型"生成"。' },
  { term: 'BM25', en: 'Best Matching 25', desc: '经典的关键词搜索算法。搜"CPU使用率"就找包含这几个字的文档，字面匹配。优点是精确，缺点是不懂同义词（"负载高"搜不到"CPU占用高"）。' },
  { term: '混合检索', en: 'Hybrid Search', desc: '同时用向量语义检索 + BM25关键词检索，两路结果合并。语义检索懂意思但可能跑偏，关键词检索精确但不懂同义词，互补。' },
  { term: 'Reranker', en: 'Reranker', desc: '重排序模型。先粗搜出一批候选结果，再用更精确的模型重新打分排序。当前暂未启用（模型文件不完整）。' },
  { term: '归一化', en: 'Normalization', desc: '把不同范围的分数统一到0~1之间。比如规则分满分6.33分，RAG分满分0.61分，归一化后都是0~1，才能公平比较。' },
  { term: '权重', en: 'Weight', desc: '每个信号的重要程度。当前规则和RAG各占0.5（50%），意味着两路同等重要。' },
  { term: '融合策略', en: 'Score Fusion', desc: '把多路检索的结果合并成一个排序。当前用的是加权求和：最终分 = 规则分×0.5 + RAG分×0.5。' },
  { term: 'Top-K', en: 'Top-K', desc: '只取分数最高的K条结果返回。当前默认K=5，即推荐5条最相关的知识。' },
  { term: '随机噪声', en: 'Random Noise', desc: '打分结果中没有实际意义的噪音数据。比如之前的规则bug导致所有知识得分都是0，排序完全随机——这就是随机噪声。' },
  { term: '召回', en: 'Recall', desc: '系统能搜到相关知识的能力。召回高 = 搜得全，不容易漏。和"召回率"意思一样。' },
  { term: '冷启动', en: 'Cold Start', desc: '系统刚部署、数据很少时的状态。比如故障知识库只有3条知识，很多告警都匹配不到，这就是冷启动问题。' },
]
const limit = ref(5)
const alert = ref(null)
const recommendations = ref([])
const runbooks = ref([])
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
    runbooks.value = data.runbooks || []
    sources.value = data.sources || null
  } catch (e) {
    ElMessage.error('查询失败: ' + (e.message || e))
    alert.value = null
    recommendations.value = []
    runbooks.value = []
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
.src-runbook { background: rgba(20,184,166,0.1); color: #14b8a6; }
.rb-item { border-left: 3px solid #14b8a6; }
.rb-rank { background: rgba(20,184,166,0.1); color: #14b8a6; }
.rb-steps { background: rgba(20,184,166,0.04); border-left: 3px solid #14b8a6; padding: 8px 10px; border-radius: 0 6px 6px 0; font-size: 0.8rem; color: #475569; line-height: 1.6; }
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
.modal-wide { min-width: 640px; max-width: 720px; }
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
.logic-flow { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.flow-box { padding: 5px 10px; border-radius: 6px; font-size: 0.78rem; font-weight: 600; white-space: nowrap; }
.flow-alert { background: rgba(239,68,68,0.1); color: #ef4444; }
.flow-split { background: rgba(245,158,11,0.1); color: #d97706; }
.flow-merge { background: rgba(99,102,241,0.1); color: #6366f1; }
.flow-out { background: rgba(34,197,94,0.1); color: #22c55e; }
.flow-arrow { color: #94a3b8; font-size: 0.9rem; }
.glossary-grid { display: flex; flex-direction: column; gap: 8px; }
.glossary-item { padding: 8px 10px; border-left: 3px solid var(--border, rgba(0,0,0,0.07)); background: var(--bg-hover, rgba(0,0,0,0.02)); border-radius: 0 6px 6px 0; }
.gloss-term { font-size: 0.85rem; font-weight: 700; color: var(--text, #1e293b); }
.gloss-en { font-size: 0.7rem; color: var(--accent, #6366f1); font-weight: 500; margin-top: 1px; }
.gloss-desc { font-size: 0.78rem; color: #475569; line-height: 1.5; margin-top: 3px; }
</style>
