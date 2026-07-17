<template>
  <div class="rag-page">
    <div class="page-header">
      <h1>RAG 检索精度提升</h1>
      <p>两阶段检索：向量 + BM25 召回 → Reranker 重排 · 提升知识命中精准度</p>
    </div>

    <div class="toolbar">
      <input v-model="query" class="input search-input" placeholder="输入检索 query" @keyup.enter="doSearch">
      <select v-model="rerankMode" class="input" style="width:120px;">
        <option value="none">不重排</option>
        <option value="classic">经典重排</option>
        <option value="smart">智能重排 (GPU)</option>
      </select>
      <button class="btn btn-primary" @click="doSearch" :disabled="searchLoading">{{ searchLoading ? '检索中...' : '检索' }}</button>
    </div>

    <div v-if="results.length" class="panel">
      <div class="panel-head">检索结果 · {{ results.length }} 条 · 当前模式: {{ rerankMode }}</div>
      <div class="panel-body">
        <div v-for="(r, i) in results" :key="i" class="result-item">
          <div class="result-head">
            <span class="result-rank">#{{ i + 1 }}</span>
            <span class="result-title">{{ r.doc_title || r.title || '无标题' }}</span>
            <span class="result-score">{{ r.score?.toFixed(4) || r.rerank_score?.toFixed(4) || '-' }}</span>
            <span v-if="r.rerank_method" class="rerank-tag">{{ r.rerank_method }}</span>
          </div>
          <div class="result-content">{{ r.content }}</div>
          <div class="result-meta">
            <span>向量分: {{ r.vector_score?.toFixed(4) || '-' }}</span>
            <span>BM25: {{ r.bm25_score?.toFixed(4) || '-' }}</span>
            <span v-if="r.rerank_score">重排分: {{ r.rerank_score?.toFixed(4) }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="panel" style="margin-top:14px;">
      <div class="panel-head">Reranker 说明</div>
      <div class="panel-body">
        <div class="mode-grid">
          <div class="mode-card">
            <div class="mode-name">经典重排 (classic)</div>
            <div class="mode-desc">多特征混合评分：关键词覆盖 40% + 向量相似度 30% + BM25 20% + 长度归一化 10% · CPU 运行，零开销</div>
          </div>
          <div class="mode-card">
            <div class="mode-name">智能重排 (smart)</div>
            <div class="mode-desc">AuroraX-Reranker (ModernBERT 300M) 神经网络重排 · 需要 GPU + CUDA · 精度更高</div>
          </div>
          <div class="mode-card">
            <div class="mode-name">不重排 (none)</div>
            <div class="mode-desc">直接返回混合召回结果（向量 70% + BM25 30%）· 最快</div>
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

const query = ref('')
const rerankMode = ref('classic')
const results = ref([])
const searchLoading = ref(false)

async function doSearch() {
  if (!query.value.trim()) { ElMessage.warning('请输入 query'); return }
  searchLoading.value = true
  try {
    const data = await request.get('/knowledge/v2/search', { params: { query: query.value, top_k: 5, rerank_mode: rerankMode.value } })
    results.value = data.results || data.items || []
  } catch (e) {
    ElMessage.error('检索失败: ' + (e.message || e))
  } finally {
    searchLoading.value = false
  }
}
</script>

<style scoped>
.rag-page { padding: 4px; }
.page-header { margin-bottom: 12px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; margin: 0 0 4px; }
.page-header p { color: var(--text-secondary,#64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; }
.search-input { min-width: 300px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong,rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid,#fff); cursor: pointer; font-size: 0.82rem; }
.btn-primary { background: var(--accent,#6366f1); color: #fff; border-color: var(--accent,#6366f1); }
.input { padding: 5px 10px; border: 1px solid var(--border,rgba(0,0,0,0.1)); border-radius: 6px; font-size: 0.82rem; }
.panel { background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; }
.panel-body { padding: 16px 18px; }
.result-list { display: flex; flex-direction: column; gap: 10px; }
.result-item { border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 8px; padding: 12px; }
.result-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.result-rank { font-size: 0.72rem; font-weight: 700; background: rgba(99,102,241,0.1); color: #6366f1; padding: 2px 6px; border-radius: 6px; }
.result-title { font-weight: 600; font-size: 0.88rem; flex: 1; }
.result-score { font-size: 0.78rem; font-weight: 700; color: #22c55e; }
.rerank-tag { font-size: 0.68rem; background: rgba(168,85,247,0.1); color: #a855f7; padding: 1px 6px; border-radius: 4px; }
.result-content { font-size: 0.82rem; color: var(--text,#1e293b); line-height: 1.5; margin-bottom: 6px; white-space: pre-wrap; }
.result-meta { display: flex; gap: 12px; font-size: 0.72rem; color: var(--text-secondary,#64748b); }
.mode-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.mode-card { border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 8px; padding: 12px; }
.mode-name { font-weight: 600; font-size: 0.85rem; margin-bottom: 6px; }
.mode-desc { font-size: 0.78rem; color: var(--text-secondary,#64748b); line-height: 1.5; }
</style>
