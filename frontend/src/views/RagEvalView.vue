<template>
  <div class="re-page">
    <div class="page-header">
      <h1>RAG 检索质量评估</h1>
      <p>从 knowledge_base 自动构造标注集 · 量化指标：recall@k / MRR / nDCG@k / 平均延迟 · 60s 缓存</p>
    </div>

    <!-- 概览卡片 -->
    <div class="summary-grid" v-if="summary">
      <div class="summary-card">
        <div class="summary-label">评估样本</div>
        <div class="summary-value">{{ summary.sample_count }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">成功检索</div>
        <div class="summary-value">{{ summary.success_count }}</div>
      </div>
      <div class="summary-card" :class="{ danger: summary.recall_at_k < 0.5, ok: summary.recall_at_k >= 0.7 }">
        <div class="summary-label">recall@{{ summary.top_k }}</div>
        <div class="summary-value">{{ (summary.recall_at_k * 100).toFixed(1) }}%</div>
      </div>
      <div class="summary-card" :class="{ danger: summary.mrr < 0.3, ok: summary.mrr >= 0.5 }">
        <div class="summary-label">MRR</div>
        <div class="summary-value">{{ summary.mrr.toFixed(4) }}</div>
      </div>
      <div class="summary-card" :class="{ danger: summary.ndcg_at_k < 0.3, ok: summary.ndcg_at_k >= 0.5 }">
        <div class="summary-label">nDCG@{{ summary.top_k }}</div>
        <div class="summary-value">{{ summary.ndcg_at_k.toFixed(4) }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">平均延迟</div>
        <div class="summary-value">{{ summary.avg_latency_ms }} ms</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">总耗时</div>
        <div class="summary-value">{{ summary.elapsed_ms }} ms</div>
      </div>
    </div>

    <!-- 操作 -->
    <div class="panel">
      <div class="panel-head">
        <span>样本明细</span>
        <div class="panel-actions">
          <label class="text-sm">top_k:
            <select v-model.number="topK" @change="load" class="select-sm">
              <option :value="3">3</option>
              <option :value="5">5</option>
              <option :value="10">10</option>
            </select>
          </label>
          <label class="text-sm">limit:
            <select v-model.number="limit" @change="load" class="select-sm">
              <option :value="20">20</option>
              <option :value="50">50</option>
              <option :value="100">100</option>
            </select>
          </label>
          <button class="btn btn-sm" @click="load" :disabled="loading">{{ loading ? '评估中...' : '刷新' }}</button>
          <button class="btn btn-sm" @click="runEval" :disabled="running">{{ running ? '重跑中...' : '强制重跑' }}</button>
          <button class="btn btn-sm" @click="showDataset">查看数据集</button>
        </div>
      </div>
      <div class="panel-body">
        <div v-if="loading && !summary" class="loading-state">评估中（每个样本跑 hybrid_search）...</div>
        <div v-else-if="warning" class="empty-state text-danger">{{ warning }}</div>
        <div v-else-if="!samples.length" class="empty-state">暂无样本（需 knowledge_base 有关联的 KbDocument）</div>
        <table v-else class="table">
          <thead>
            <tr>
              <th>Query</th>
              <th>知识 ID</th>
              <th>相关文档</th>
              <th>检索文档数</th>
              <th>recall@k</th>
              <th>MRR</th>
              <th>nDCG@k</th>
              <th>延迟</th>
              <th>错误</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(s, i) in samples" :key="i" :class="{ 'row-failed': s.error }">
              <td class="text-sm" style="max-width: 260px;">{{ s.query }}</td>
              <td class="text-mono">{{ s.kb_id }}</td>
              <td class="text-mono text-sm">{{ (s.relevant_doc_ids || []).join(',') }}</td>
              <td>{{ s.retrieved_count || 0 }}</td>
              <td :class="metricClass(s.recall_at_k)">{{ (s.recall_at_k * 100).toFixed(0) }}%</td>
              <td :class="metricClass(s.mrr)">{{ s.mrr.toFixed(3) }}</td>
              <td :class="metricClass(s.ndcg_at_k)">{{ s.ndcg_at_k.toFixed(3) }}</td>
              <td class="text-sm">{{ s.latency_ms }} ms</td>
              <td class="text-sm text-danger">{{ s.error || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 数据集弹窗 -->
    <div v-if="dataset" class="modal-overlay" @click.self="dataset = null">
      <div class="modal-box modal-lg">
        <h3>评估数据集（{{ dataset.total }} 条）</h3>
        <table class="table">
          <thead><tr><th>Query</th><th>知识 ID</th><th>相关文档</th><th>标签</th><th>资产类型</th></tr></thead>
          <tbody>
            <tr v-for="(s, i) in dataset.samples" :key="i">
              <td class="text-sm" style="max-width: 240px;">{{ s.query }}</td>
              <td class="text-mono">{{ s.kb_id }}</td>
              <td class="text-mono text-sm">{{ (s.relevant_doc_ids || []).join(',') }}</td>
              <td class="text-sm">{{ s.tags }}</td>
              <td class="text-sm">{{ s.asset_type }}</td>
            </tr>
          </tbody>
        </table>
        <div class="modal-actions"><button class="btn" @click="dataset = null">关闭</button></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const running = ref(false)
const warning = ref('')
const summary = ref(null)
const samples = ref([])
const topK = ref(5)
const limit = ref(50)
const dataset = ref(null)

function metricClass(v) {
  if (v == null) return ''
  if (v >= 0.7) return 'text-success'
  if (v >= 0.4) return 'text-warn'
  return 'text-danger'
}

async function load() {
  loading.value = true
  warning.value = ''
  try {
    const data = await request.get('/api/rag/eval', { params: { top_k: topK.value, limit: limit.value } })
    if (data.warning) {
      warning.value = data.warning
      ElMessage.warning(data.warning)
    } else {
      summary.value = data.summary
      samples.value = data.samples || []
    }
  } catch (e) {
    console.error('rag eval:', e)
  } finally {
    loading.value = false
  }
}

async function runEval() {
  running.value = true
  try {
    const data = await request.post('/api/rag/eval/run', null, { params: { top_k: topK.value, limit: limit.value } })
    if (data.ok) {
      ElMessage.success(`重跑完成，样本数 ${data.sample_count}`)
      load()
    } else {
      ElMessage.warning(data.message || '重跑失败')
    }
  } catch (e) {
    ElMessage.error('重跑失败: ' + (e.message || e))
  } finally {
    running.value = false
  }
}

async function showDataset() {
  try {
    const data = await request.get('/api/rag/eval/dataset', { params: { limit: limit.value } })
    dataset.value = data
  } catch (e) {
    ElMessage.error('加载数据集失败: ' + (e.message || e))
  }
}

onMounted(load)
</script>

<style scoped>
.re-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 16px; }
.summary-card { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; padding: 12px 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.summary-card.danger { border-left: 3px solid #ef4444; }
.summary-card.ok { border-left: 3px solid #22c55e; }
.summary-label { font-size: 0.72rem; color: var(--text-secondary, #64748b); text-transform: uppercase; letter-spacing: 0.3px; margin-bottom: 4px; }
.summary-value { font-size: 1.4rem; font-weight: 700; color: var(--text, #1e293b); }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); display: flex; justify-content: space-between; align-items: center; }
.panel-actions { display: flex; gap: 10px; align-items: center; }
.panel-body { padding: 16px 18px; }
.select-sm { padding: 3px 6px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 4px; font-size: 0.78rem; background: var(--bg-card-solid, #fff); }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.72rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; white-space: nowrap; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.table tr.row-failed td { background: rgba(239,68,68,0.04); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.text-mono { font-family: 'Consolas', monospace; font-size: 0.8rem; }
.text-danger { color: #ef4444; }
.text-success { color: #22c55e; }
.text-warn { color: #f59e0b; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 420px; max-height: 86vh; overflow-y: auto; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-lg { min-width: 820px; }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; color: var(--text, #1e293b); }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
