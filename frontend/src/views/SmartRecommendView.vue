<template>
  <div class="sr-page">
    <div class="page-header">
      <h1>智能推荐</h1>
      <p>{{ tab === 'alert' ? '规则匹配 + RAG 语义检索 融合推荐' : tab === 'metric' ? '智能指标推荐 — 发掘资产缺失的观测指标' : '资产基线安全检查 — 按标准检测资产安全合规状态' }}</p>
    </div>

    <div class="tabs">
      <div class="tab" :class="{ active: tab === 'alert' }" @click="tab = 'alert'">告警推荐</div>
      <div class="tab" :class="{ active: tab === 'metric' }" @click="tab = 'metric'">指标推荐</div>
      <div class="tab" :class="{ active: tab === 'baseline' }" @click="tab = 'baseline'">基线检查</div>
    </div>

    <!-- ════════ 告警推荐 ════════ -->
    <template v-if="tab === 'alert'">
      <div class="toolbar">
        <input v-model="alertId" class="input search-input" placeholder="输入告警 ID" @keyup.enter="runRecommend">
        <input v-model.number="limit" class="input limit-input" type="number" min="1" max="20" placeholder="数量">
        <button class="btn btn-primary" @click="runRecommend" :disabled="loading">{{ loading ? '查询中...' : '查询推荐' }}</button>
        <button class="btn btn-accent" @click="aiAlertAnalyze" :disabled="alertAiLoading">{{ alertAiLoading ? '分析中...' : 'AI 分析' }}</button>
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
          </div>
          <div class="logic-section">
            <div class="logic-title">两路数据源</div>
            <div class="logic-row"><span class="logic-tag tag-rule">规则匹配</span> 故障知识库（knowledge_base 表）</div>
            <div class="logic-row"><span class="logic-tag tag-rag">RAG 语义</span> 知识库文档（kb_documents + Milvus）</div>
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

      <div v-if="alertAiResult" class="panel" style="margin-top:14px;">
        <div class="panel-head">
          AI 告警分析
          <span class="tag-mini" style="margin-left:8px;background:rgba(20,184,166,0.1);color:#14b8a6;">AI</span>
        </div>
        <div class="panel-body">
          <div class="bl-score-bar">
            <div class="alert-ai-sev badge" :class="sevClass(alertAiResult.severity_assessment)">{{ alertAiResult.severity_assessment }}</div>
          </div>
          <div class="ai-analysis-section">
            <div class="rec-label">根因分析</div>
            <div class="rec-text" style="margin-top:2px;">{{ alertAiResult.root_cause }}</div>
          </div>
          <div v-if="alertAiResult.impact" class="ai-analysis-section">
            <div class="rec-label">影响评估</div>
            <div class="rec-text" style="margin-top:2px;">{{ alertAiResult.impact }}</div>
          </div>
          <div class="ai-analysis-section">
            <div class="rec-label">修复建议</div>
            <div class="rec-text" style="margin-top:2px;">{{ alertAiResult.recommendation }}</div>
          </div>
          <div v-if="alertAiResult.suggested_runbooks && alertAiResult.suggested_runbooks.length" class="ai-analysis-section">
            <div class="rec-label">建议 Runbook</div>
            <div v-for="(rb, i) in alertAiResult.suggested_runbooks" :key="i" class="runbook-suggest">• {{ rb }}</div>
          </div>
        </div>
      </div>

      <div class="panel" style="margin-top:14px;">
        <div class="panel-head">推荐知识 · {{ recommendations.length }} 条</div>
        <div class="panel-body">
          <div v-if="loading" class="loading-state">查询中...</div>
          <div v-else-if="searched && !recommendations.length" class="empty-state"><div>暂无匹配推荐</div></div>
          <div v-else-if="!searched" class="empty-state"><div>输入告警 ID 查询智能推荐</div></div>
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
              <div v-if="r.content" class="rec-block"><span class="rec-label">RAG 片段</span><div class="rec-text rag-content">{{ r.content }}</div></div>
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
              <div v-if="rb.runbook.symptom" class="rec-block"><span class="rec-label">症状</span><div class="rec-text">{{ rb.runbook.symptom }}</div></div>
              <div v-if="rb.runbook.steps" class="rec-block"><span class="rec-label">操作步骤</span><div class="rec-text rb-steps">{{ rb.runbook.steps }}</div></div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- ════════ 指标推荐 ════════ -->
    <template v-if="tab === 'metric'">
      <div class="toolbar">
        <input v-model="assetId" class="input search-input" placeholder="输入资产 ID" @keyup.enter="loadGaps">
        <button class="btn btn-primary" @click="loadGaps" :disabled="metricLoading">{{ metricLoading ? '加载中...' : '查询缺口' }}</button>
        <button class="btn btn-accent" @click="aiRecommend" :disabled="aiLoading">{{ aiLoading ? 'AI 分析中...' : 'AI 智能推荐' }}</button>
      </div>

      <div class="panel" style="margin-top:14px;">
        <div class="panel-head">指标缺口 · {{ gaps.length }} 项</div>
        <div class="panel-body">
          <div v-if="metricLoading" class="loading-state">加载中...</div>
          <div v-else-if="!gaps.length && metricSearched" class="empty-state"><div>该资产暂无指标缺口（所有模板指标均已纳入观测）</div></div>
          <div v-else-if="!metricSearched" class="empty-state"><div>输入资产 ID 查询指标缺口</div></div>
          <div v-else class="gap-table-wrap">
            <table class="gap-table">
              <thead>
                <tr>
                  <th>指标</th>
                  <th>分类</th>
                  <th>采集方式</th>
                  <th>告警阈值(W/C)</th>
                  <th>状态</th>
                  <th style="width:130px;">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="g in gaps" :key="g.metric_key">
                  <td><div class="gap-name">{{ g.metric_name }}</div><div class="gap-key">{{ g.metric_key }}</div></td>
                  <td><span class="tag-mini">{{ g.category }}</span></td>
                  <td><span class="tag-mini">{{ g.collect_method }}</span></td>
                  <td class="threshold-cell">
                    <span v-if="g.default_threshold_warn != null">{{ g.default_threshold_warn }} / {{ g.default_threshold_critical }}</span>
                    <span v-else class="text-muted">-</span>
                  </td>
                  <td>
                    <span v-if="g.monitored" class="status-dot monitored" title="已观测">● 已观测</span>
                    <span v-else-if="g.recommendation_status === 'added'" class="status-dot added" title="已采纳">● 已采纳</span>
                    <span v-else-if="g.recommendation_status === 'dismissed'" class="status-dot dismissed" title="已忽略">● 已忽略</span>
                    <span v-else class="status-dot missing" title="缺失">● 缺失</span>
                  </td>
                  <td>
                    <template v-if="g.monitored">
                      <span class="text-muted text-small">无需操作</span>
                    </template>
                    <template v-else-if="g.recommendation_status === 'added'">
                      <button class="btn btn-sm btn-ghost" @click="dismissMetric(g)">取消采纳</button>
                    </template>
                    <template v-else-if="g.recommendation_status === 'dismissed'">
                      <button class="btn btn-sm btn-primary" @click="applyMetric(g)">重新采纳</button>
                    </template>
                    <template v-else>
                      <button class="btn btn-sm btn-primary" @click="applyMetric(g)">采纳</button>
                      <button class="btn btn-sm btn-ghost" style="margin-left:4px;" @click="dismissMetric(g)">忽略</button>
                    </template>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div v-if="aiRecs.length" class="panel" style="margin-top:14px;">
        <div class="panel-head">AI 智能推荐 · {{ aiRecs.length }} 条</div>
        <div class="panel-body">
          <div v-for="(r, i) in aiRecs" :key="i" class="rec-item" style="margin-bottom:8px;">
            <div class="rec-head">
              <span class="rec-rank">#{{ i + 1 }}</span>
              <span class="rec-title">{{ r.metric_name }}</span>
              <span class="tag-mini">{{ r.category }}</span>
              <span class="rec-score">AI</span>
            </div>
            <div v-if="r.reason" class="rec-block"><span class="rec-label">推荐理由</span><div class="rec-text">{{ r.reason }}</div></div>
            <div style="margin-top:6px;">
              <button class="btn btn-sm btn-primary" @click="applyAiMetric(r)">采纳</button>
              <button class="btn btn-sm btn-ghost" style="margin-left:4px;" @click="dismissAiMetric(r)">忽略</button>
            </div>
          </div>
        </div>
      </div>

      <div v-if="assetRecommendations.length" class="panel" style="margin-top:14px;">
        <div class="panel-head">已采纳/已忽略记录</div>
        <div class="panel-body">
          <div class="rec-list">
            <div v-for="r in assetRecommendations" :key="r.id" class="rec-item">
              <div class="rec-head">
                <span class="rec-title">{{ r.metric_name }}</span>
                <span class="tag-mini">{{ r.category }}</span>
                <span class="badge" :class="r.status === 'added' ? 'st-resolved' : 'st-other'">{{ r.status === 'added' ? '已采纳' : '已忽略' }}</span>
                <span class="text-small text-muted">{{ r.created_at }}</span>
              </div>
              <div class="rec-text" style="margin-top:4px;">{{ r.reason || r.metric_key }}</div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- ════════ 基线检查 ════════ -->
    <template v-if="tab === 'baseline'">
      <div class="toolbar">
        <input v-model="blAssetId" class="input search-input" placeholder="输入资产 ID" @keyup.enter="loadBaseline">
        <button class="btn btn-primary" @click="loadBaseline" :disabled="blLoading">{{ blLoading ? '加载中...' : '查询基线' }}</button>
        <button class="btn btn-accent" @click="runAllBaseline" :disabled="blRunning">{{ blRunning ? '检测中...' : '一键检测全部' }}</button>
        <button class="btn btn-accent" @click="aiAnalyzeBaseline" :disabled="blAiLoading">{{ blAiLoading ? '分析中...' : 'AI 安全分析' }}</button>
      </div>

      <div v-if="blAnalysis" class="panel" style="margin-bottom:14px;">
        <div class="panel-head">
          安全报告
          <span v-if="blAnalysis.ai_generated" class="tag-mini" style="margin-left:8px;background:rgba(168,85,247,0.1);color:#a855f7;">AI 生成</span>
        </div>
        <div class="panel-body">
          <div class="bl-score-bar">
            <div class="bl-score" :style="{color: scoreColor(blAnalysis.score)}">{{ blAnalysis.score }}<span class="bl-score-label">/100</span></div>
            <div class="bl-risk" :class="'risk-' + blAnalysis.risk_level">{{ riskLabel(blAnalysis.risk_level) }}</div>
          </div>
          <div class="bl-summary">{{ blAnalysis.summary }}</div>
          <div class="bl-stats">
            <span class="stat-item stat-pass">合规 {{ blAnalysis.pass_count }}</span>
            <span class="stat-item stat-fail">不合规 {{ blAnalysis.fail_count }}</span>
            <span class="stat-item stat-na">待确认 {{ blAnalysis.na_count }}</span>
          </div>
          <div v-if="blAnalysis.top_risks && blAnalysis.top_risks.length" style="margin-top:12px;">
            <div class="rec-label">主要风险项</div>
            <div v-for="(risk, i) in blAnalysis.top_risks" :key="i" class="risk-row">
              <span class="risk-num">#{{ i + 1 }}</span>
              <div style="flex:1;">
                <div class="risk-item-name">{{ risk.item }}</div>
                <div v-if="risk.risk" class="risk-value">检测值: {{ risk.risk }}</div>
                <div v-if="risk.suggestion" class="risk-suggestion">建议: {{ risk.suggestion }}</div>
              </div>
            </div>
          </div>
          <div v-if="blAnalysis.fix_priority && blAnalysis.fix_priority.length" style="margin-top:10px;">
            <div class="rec-label">优先修复</div>
            <div v-for="(fix, i) in blAnalysis.fix_priority" :key="i" class="fix-item">• {{ fix }}</div>
          </div>
        </div>
      </div>

      <div class="panel" style="margin-top:14px;">
        <div class="panel-head">基线检查项 · {{ blItems.length }} 项</div>
        <div class="panel-body">
          <div v-if="blLoading" class="loading-state">加载中...</div>
          <div v-else-if="!blItems.length && blSearched" class="empty-state"><div>该资产暂无基线模板</div></div>
          <div v-else-if="!blSearched" class="empty-state"><div>输入资产 ID 查询基线检查项</div></div>
          <div v-else class="gap-table-wrap">
            <table class="gap-table">
              <thead>
                <tr>
                  <th>检查项</th>
                  <th>分类</th>
                  <th>严重等级</th>
                  <th>检测方式</th>
                  <th>状态</th>
                  <th>检测值</th>
                  <th style="width:100px;">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in blItems" :key="item.check_key">
                  <td>
                    <div class="gap-name">{{ item.check_name }}</div>
                    <div class="gap-key">{{ item.check_key }}</div>
                    <div v-if="item.description" class="bl-desc">{{ item.description }}</div>
                  </td>
                  <td><span class="tag-mini">{{ item.category }}</span></td>
                  <td><span class="badge" :class="sevBlClass(item.severity)">{{ item.severity }}</span></td>
                  <td><span class="tag-mini">{{ item.check_method }}</span></td>
                  <td>
                    <span v-if="item.status === 'pass'" class="status-dot monitored" title="合规">● 合规</span>
                    <span v-else-if="item.status === 'fail'" class="status-dot missing" title="不合规">● 不合规</span>
                    <span v-else-if="item.status === 'na'" class="status-dot dismissed" title="无法检测">● 无法检测</span>
                    <span v-else class="status-dot" style="color:#94a3b8;" title="待检测">● 待检测</span>
                  </td>
                  <td class="bl-value">{{ item.actual_value || '-' }}</td>
                  <td>
                    <button v-if="item.check_method !== 'manual'" class="btn btn-sm btn-ghost" @click="runSingleBaseline(item)" :disabled="blRunning">检测</button>
                    <button class="btn btn-sm btn-ghost" @click="showManualModal(item)">标记</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div v-if="showManual" class="modal-overlay" @click.self="showManual = false">
        <div class="modal-box">
          <h3>手动标记: {{ manualItem?.check_name }}</h3>
          <div class="form-group">
            <label class="form-label">状态</label>
            <select v-model="manualStatus" class="input">
              <option value="pass">合规 (pass)</option>
              <option value="fail">不合规 (fail)</option>
              <option value="na">无法检测 (na)</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">检测值/说明</label>
            <input v-model="manualValue" class="input" placeholder="可选">
          </div>
          <div class="form-group">
            <label class="form-label">备注</label>
            <textarea v-model="manualReason" class="input" rows="2" placeholder="可选"></textarea>
          </div>
          <div class="modal-actions">
            <button class="btn" @click="showManual = false" style="margin-right:8px;">取消</button>
            <button class="btn btn-primary" @click="submitManual">保存</button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const tab = ref('alert')

// ── 告警推荐 ──
const loading = ref(false)
const searched = ref(false)
const showLogic = ref(false)
const alertId = ref('')
const limit = ref(5)
const alert = ref(null)
const recommendations = ref([])
const runbooks = ref([])
const sources = ref(null)
const alertAiLoading = ref(false)
const alertAiResult = ref(null)

const glossary = [
  { term: '召回率', en: 'Recall', desc: '搜出来的相关知识占所有相关知识的比例。' },
  { term: '准确率', en: 'Precision', desc: '搜出来的知识里，真正相关的比例。' },
  { term: '分片 / 切片', en: 'Chunk', desc: '一篇长文档被切成的一小段。' },
  { term: 'Embedding', en: 'Embedding', desc: '把一段文字转成一串数字（向量）。' },
  { term: '向量相似度', en: 'Cosine Similarity', desc: '两段文字转成向量后算它们的"夹角"。' },
  { term: '向量数据库', en: 'Vector DB (Milvus)', desc: '专门用来存和搜向量的数据库。' },
  { term: 'RAG', en: 'Retrieval-Augmented Generation', desc: '检索增强生成。' },
  { term: 'BM25', en: 'Best Matching 25', desc: '经典的关键词搜索算法。' },
  { term: '混合检索', en: 'Hybrid Search', desc: '同时用向量语义检索 + BM25关键词检索。' },
  { term: '归一化', en: 'Normalization', desc: '把不同范围的分数统一到0~1之间。' },
  { term: '权重', en: 'Weight', desc: '每个信号的重要程度。' },
  { term: '融合策略', en: 'Score Fusion', desc: '把多路检索的结果合并成一个排序。' },
  { term: 'Top-K', en: 'Top-K', desc: '只取分数最高的K条结果返回。' },
  { term: '冷启动', en: 'Cold Start', desc: '系统刚部署、数据很少时的状态。' },
]

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

async function aiAlertAnalyze() {
  if (!alertId.value) { ElMessage.warning('请先输入告警 ID'); return }
  alertAiLoading.value = true
  alertAiResult.value = null
  try {
    const data = await request.get('/smart-recommend/ai-analyze-alert/' + alertId.value)
    if (data.analysis) {
      alertAiResult.value = data.analysis
    } else {
      ElMessage.info(data.message || 'AI 未返回分析结果')
    }
  } catch (e) {
    ElMessage.error('AI 分析失败: ' + (e.message || e))
  } finally {
    alertAiLoading.value = false
  }
}

// ── 指标推荐 ──
const assetId = ref('')
const metricLoading = ref(false)
const metricSearched = ref(false)
const gaps = ref([])
const aiRecs = ref([])
const aiLoading = ref(false)
const assetRecommendations = ref([])

async function loadGaps() {
  if (!assetId.value) {
    ElMessage.warning('请输入资产 ID')
    return
  }
  metricLoading.value = true
  metricSearched.value = true
  aiRecs.value = []
  try {
    const [gapsData, recsData] = await Promise.all([
      request.get('/smart-recommend/gaps/' + assetId.value),
      request.get('/smart-recommend/recommendations/' + assetId.value),
    ])
    gaps.value = gapsData.gaps || []
    assetRecommendations.value = recsData.recommendations || []
  } catch (e) {
    ElMessage.error('查询失败: ' + (e.message || e))
    gaps.value = []
    assetRecommendations.value = []
  } finally {
    metricLoading.value = false
  }
}

async function aiRecommend() {
  if (!assetId.value) {
    ElMessage.warning('请先输入资产 ID 并查询缺口')
    return
  }
  aiLoading.value = true
  try {
    const data = await request.get('/smart-recommend/ai-recommend/' + assetId.value)
    aiRecs.value = data.recommendations || []
    if (!aiRecs.value.length) {
      ElMessage.info(data.message || 'AI 未返回推荐')
    }
  } catch (e) {
    ElMessage.error('AI 推荐失败: ' + (e.message || e))
  } finally {
    aiLoading.value = false
  }
}

async function applyMetric(g) {
  try {
    await request.post('/smart-recommend/apply', {
      asset_id: parseInt(assetId.value),
      metric_key: g.metric_key,
      metric_name: g.metric_name,
      category: g.category || '',
      unit: g.unit || '',
      source: g.source || 'template',
      reason: g.reason || '',
    })
    ElMessage.success('已采纳: ' + g.metric_name)
    await loadGaps()
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.message || e))
  }
}

async function dismissMetric(g) {
  try {
    await request.post('/smart-recommend/dismiss', {
      asset_id: parseInt(assetId.value),
      metric_key: g.metric_key,
    })
    ElMessage.success('已忽略: ' + g.metric_name)
    await loadGaps()
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.message || e))
  }
}

async function applyAiMetric(r) {
  try {
    await request.post('/smart-recommend/apply', {
      asset_id: parseInt(assetId.value),
      metric_key: r.metric_key || r.metric_key,
      metric_name: r.metric_name || '',
      category: r.category || '',
      unit: r.unit || '',
      source: 'ai',
      reason: r.reason || 'AI 推荐',
    })
    ElMessage.success('已采纳: ' + (r.metric_name || r.metric_key))
    aiRecs.value = aiRecs.value.filter(x => x !== r)
    await loadGaps()
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.message || e))
  }
}

function dismissAiMetric(r) {
  aiRecs.value = aiRecs.value.filter(x => x !== r)
}

// ── 基线检查 ──
const blAssetId = ref('')
const blLoading = ref(false)
const blRunning = ref(false)
const blAiLoading = ref(false)
const blSearched = ref(false)
const blItems = ref([])
const blAnalysis = ref(null)
const showManual = ref(false)
const manualItem = ref(null)
const manualStatus = ref('pass')
const manualValue = ref('')
const manualReason = ref('')

function sevBlClass(s) {
  const m = { critical: 'sev-critical', high: 'sev-high', medium: 'sev-warning', low: 'sev-info' }
  return m[s] || 'sev-info'
}

function scoreColor(s) {
  if (s >= 90) return '#22c55e'
  if (s >= 70) return '#f59e0b'
  if (s >= 50) return '#f97316'
  return '#ef4444'
}

function riskLabel(r) {
  const m = { critical: '严重', high: '高危', medium: '中危', low: '低危' }
  return m[r] || r
}

async function loadBaseline() {
  if (!blAssetId.value) { ElMessage.warning('请输入资产 ID'); return }
  blLoading.value = true
  blSearched.value = true
  try {
    const data = await request.get('/baseline/checks/' + blAssetId.value)
    blItems.value = data.items || []
    blAnalysis.value = null
  } catch (e) {
    ElMessage.error('查询失败: ' + (e.message || e))
    blItems.value = []
  } finally {
    blLoading.value = false
  }
}

async function runSingleBaseline(item) {
  blRunning.value = true
  try {
    const data = await request.post('/baseline/check/' + blAssetId.value + '/' + item.template_id)
    ElMessage.success(item.check_name + ': ' + (data.status === 'pass' ? '合规' : data.status === 'fail' ? '不合规' : data.status))
    await loadBaseline()
  } catch (e) {
    ElMessage.error('检测失败: ' + (e.message || e))
  } finally {
    blRunning.value = false
  }
}

async function runAllBaseline() {
  blRunning.value = true
  try {
    const data = await request.post('/baseline/check-all/' + blAssetId.value)
    ElMessage.success('检测完成: 共 ' + data.total + ' 项')
    await loadBaseline()
  } catch (e) {
    ElMessage.error('检测失败: ' + (e.message || e))
  } finally {
    blRunning.value = false
  }
}

async function aiAnalyzeBaseline() {
  if (!blItems.value.length) {
    ElMessage.warning('请先查询基线')
    return
  }
  blAiLoading.value = true
  try {
    const data = await request.get('/baseline/analyze/' + blAssetId.value)
    blAnalysis.value = data.analysis || null
    blItems.value = data.items || []
  } catch (e) {
    ElMessage.error('分析失败: ' + (e.message || e))
  } finally {
    blAiLoading.value = false
  }
}

function showManualModal(item) {
  manualItem.value = item
  manualStatus.value = item.status === 'pass' || item.status === 'fail' ? item.status : 'pass'
  manualValue.value = item.actual_value || ''
  manualReason.value = ''
  showManual.value = true
}

async function submitManual() {
  if (!manualItem.value) return
  try {
    await request.post('/baseline/checks/manual', {
      asset_id: parseInt(blAssetId.value),
      template_id: manualItem.value.template_id,
      status: manualStatus.value,
      actual_value: manualValue.value,
      reason: manualReason.value,
    })
    ElMessage.success('已标记: ' + manualItem.value.check_name)
    showManual.value = false
    await loadBaseline()
  } catch (e) {
    ElMessage.error('标记失败: ' + (e.message || e))
  }
}
</script>

<style scoped>
.sr-page { padding: 4px; }
.page-header { margin-bottom: 12px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }

.tabs { display: flex; gap: 0; margin-bottom: 14px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.tab { padding: 8px 20px; font-size: 0.85rem; font-weight: 500; color: var(--text-secondary, #64748b); cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.15s; }
.tab:hover { color: var(--text, #1e293b); }
.tab.active { color: var(--accent, #6366f1); border-bottom-color: var(--accent, #6366f1); font-weight: 600; }

.toolbar { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; flex-wrap: wrap; }
.search-input { min-width: 240px; }
.limit-input { width: 100px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-accent { background: #14b8a6; color: #fff; border-color: #14b8a6; }
.btn-accent:hover { background: #0d9488; }
.btn-sm { padding: 3px 10px; font-size: 0.75rem; }
.btn-ghost { background: transparent; border-color: var(--border-strong, rgba(0,0,0,0.12)); color: var(--text-secondary, #64748b); }
.btn-ghost:hover { background: var(--bg-hover, rgba(0,0,0,0.04)); color: var(--text, #1e293b); }
.btn-help { border-color: rgba(99,102,241,0.3); color: var(--accent, #6366f1); }
.btn-help:hover { background: rgba(99,102,241,0.06); }

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
.rb-steps { background: rgba(20,184,166,0.04); border-left: 3px solid #14b8a6; padding: 8px 10px; border-radius: 0 6px 6px 0; font-size: 0.8rem; line-height: 1.6; }
.rec-meta { display: flex; gap: 6px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.tag-mini { display: inline-block; padding: 1px 6px; border-radius: 4px; background: rgba(99,102,241,0.08); color: var(--accent, #6366f1); font-size: 0.7rem; }
.rec-block { margin-top: 6px; }
.rec-label { font-size: 0.72rem; color: var(--text-secondary, #64748b); font-weight: 600; }
.rec-text { margin-top: 4px; font-size: 0.82rem; color: var(--text, #1e293b); line-height: 1.5; white-space: pre-wrap; }
.rag-content { background: rgba(168,85,247,0.04); border-left: 3px solid #a855f7; padding: 8px 10px; border-radius: 0 6px 6px 0; font-size: 0.8rem; }
.rec-reasons { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 6px; }
.reason-tag { font-size: 0.68rem; padding: 1px 6px; border-radius: 4px; background: rgba(59,130,246,0.08); color: #3b82f6; font-weight: 500; }

.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }

.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 12px; padding: 24px 28px; min-width: 520px; max-width: 600px; max-height: 80vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.15); }
.modal-wide { min-width: 640px; max-width: 720px; }
.modal-box h3 { margin: 0 0 16px; font-size: 1.05rem; font-weight: 600; color: var(--text, #1e293b); }
.modal-actions { margin-top: 18px; display: flex; justify-content: flex-end; }
.logic-section { margin-bottom: 16px; }
.logic-title { font-size: 0.82rem; font-weight: 700; color: var(--accent, #6366f1); margin-bottom: 6px; padding-bottom: 4px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.logic-row { font-size: 0.8rem; color: var(--text, #1e293b); line-height: 1.6; padding: 3px 0; }
.logic-tag { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; margin-right: 4px; }
.tag-rule { background: rgba(59,130,246,0.1); color: #3b82f6; }
.tag-rag { background: rgba(168,85,247,0.1); color: #a855f7; }
.logic-flow { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.flow-box { padding: 5px 10px; border-radius: 6px; font-size: 0.78rem; font-weight: 600; white-space: nowrap; }
.flow-alert { background: rgba(239,68,68,0.1); color: #ef4444; }
.flow-split { background: rgba(245,158,11,0.1); color: #d97706; }
.flow-merge { background: rgba(99,102,241,0.1); color: #6366f1; }
.flow-out { background: rgba(34,197,94,0.1); color: #22c55e; }
.flow-arrow { color: #94a3b8; font-size: 0.9rem; }

.gap-table-wrap { overflow-x: auto; }
.gap-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.gap-table th { text-align: left; padding: 8px 10px; border-bottom: 2px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; color: var(--text-secondary, #64748b); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; white-space: nowrap; }
.gap-table td { padding: 10px 10px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.05)); vertical-align: middle; }
.gap-table tbody tr:hover { background: var(--bg-hover, rgba(0,0,0,0.02)); }
.gap-name { font-weight: 600; color: var(--text, #1e293b); }
.gap-key { font-size: 0.7rem; color: var(--text-tertiary, #94a3b8); margin-top: 1px; }
.threshold-cell { font-size: 0.78rem; color: var(--text, #1e293b); }
.status-dot { font-size: 0.75rem; font-weight: 500; }
.status-dot.monitored { color: #22c55e; }
.status-dot.added { color: #3b82f6; }
.status-dot.dismissed { color: #94a3b8; }
.status-dot.missing { color: #ef4444; }
.text-muted { color: var(--text-tertiary, #94a3b8); }
.text-small { font-size: 0.75rem; }

/* ── 基线检查 ── */
.bl-score-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 10px; }
.bl-score { font-size: 2.2rem; font-weight: 800; line-height: 1; }
.bl-score-label { font-size: 0.85rem; font-weight: 400; color: var(--text-tertiary, #94a3b8); margin-left: 4px; }
.bl-risk { font-size: 0.78rem; font-weight: 700; padding: 3px 12px; border-radius: 12px; }
.risk-critical { background: rgba(239,68,68,0.12); color: #ef4444; }
.risk-high { background: rgba(249,115,22,0.12); color: #f97316; }
.risk-medium { background: rgba(245,158,11,0.12); color: #d97706; }
.risk-low { background: rgba(34,197,94,0.12); color: #22c55e; }
.bl-summary { font-size: 0.85rem; color: var(--text, #1e293b); line-height: 1.6; margin-bottom: 10px; }
.bl-stats { display: flex; gap: 12px; }
.stat-item { font-size: 0.78rem; font-weight: 600; padding: 4px 10px; border-radius: 6px; }
.stat-pass { background: rgba(34,197,94,0.1); color: #22c55e; }
.stat-fail { background: rgba(239,68,68,0.1); color: #ef4444; }
.stat-na { background: rgba(148,163,184,0.1); color: #64748b; }
.risk-row { display: flex; gap: 8px; padding: 8px 10px; border-left: 3px solid #ef4444; background: rgba(239,68,68,0.04); border-radius: 0 6px 6px 0; margin-top: 6px; }
.risk-num { font-weight: 700; color: #ef4444; font-size: 0.78rem; min-width: 20px; }
.risk-item-name { font-size: 0.82rem; font-weight: 600; color: var(--text, #1e293b); }
.risk-value { font-size: 0.72rem; color: var(--text-secondary, #64748b); margin-top: 2px; }
.risk-suggestion { font-size: 0.75rem; color: #0d9488; margin-top: 2px; }
.fix-item { font-size: 0.8rem; color: #475569; line-height: 1.6; padding: 2px 0; }
.bl-desc { font-size: 0.7rem; color: var(--text-tertiary, #94a3b8); margin-top: 2px; }
.bl-value { font-size: 0.78rem; color: var(--text-secondary, #64748b); max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.form-group { margin-bottom: 12px; }
.form-label { display: block; font-size: 0.78rem; font-weight: 600; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.form-group .input { width: 100%; box-sizing: border-box; }
.ai-analysis-section { margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--border, rgba(0,0,0,0.05)); }
.runbook-suggest { font-size: 0.82rem; color: #14b8a6; line-height: 1.6; padding: 2px 0; }
.alert-ai-sev { font-size: 0.8rem; padding: 3px 12px; }
</style>
