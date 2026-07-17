<template>
  <div class="bench-page">
    <div class="page-header">
      <h1>异常检测基准评估</h1>
      <p>Precision / Recall / F1 追踪 · 算法选择推荐 · 基准数据集管理</p>
    </div>

    <div class="toolbar">
      <select v-model.number="days" class="input" style="width:100px;" @change="loadStats">
        <option :value="30">近30天</option>
        <option :value="90">近90天</option>
      </select>
      <button class="btn btn-primary" @click="showRecord = true">+ 录入基准</button>
      <button class="btn" @click="loadStats">刷新</button>
    </div>

    <div v-if="stats" class="stats-grid">
      <div class="stat-card">
        <div class="stat-value">{{ stats.total_records }}</div>
        <div class="stat-label">基准记录</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="color:#22c55e;">{{ stats.best_algorithm || '-' }}</div>
        <div class="stat-label">最优算法</div>
      </div>
    </div>

    <div v-if="stats && stats.by_algorithm.length" class="panel">
      <div class="panel-head">各算法效果对比</div>
      <div class="panel-body">
        <table class="gap-table">
          <thead><tr><th>算法</th><th>样本数</th><th>平均 Precision</th><th>平均 Recall</th><th>平均 F1</th></tr></thead>
          <tbody>
            <tr v-for="a in stats.by_algorithm" :key="a.algorithm" :class="a.algorithm === stats.best_algorithm ? 'best-row' : ''">
              <td><span class="alg-name">{{ a.algorithm }}</span></td>
              <td>{{ a.count }}</td>
              <td>{{ a.avg_precision?.toFixed(3) }}</td>
              <td>{{ a.avg_recall?.toFixed(3) }}</td>
              <td><span class="f1-high" v-if="a.avg_f1 >= 0.8">{{ a.avg_f1?.toFixed(3) }}</span><span v-else-if="a.avg_f1 >= 0.6" class="f1-mid">{{ a.avg_f1?.toFixed(3) }}</span><span v-else class="f1-low">{{ a.avg_f1?.toFixed(3) }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head">算法推荐</div>
      <div class="panel-body">
        <div v-if="recommend" class="rec-box">
          <div class="rec-alg">{{ recommend.recommended }}</div>
          <div class="rec-info">置信度: <span class="conf-badge" :class="recommend.confidence">{{ recommend.confidence }}</span></div>
          <div class="rec-reason">{{ recommend.reason }}</div>
          <div v-if="recommend.avg_f1" class="rec-f1">F1: {{ recommend.avg_f1 }}</div>
        </div>
        <div v-else class="empty-state">加载中...</div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head">基准记录</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="!records.length" class="empty-state">暂无基准数据</div>
        <div v-else class="gap-table-wrap">
          <table class="gap-table">
            <thead><tr><th>时间</th><th>资产</th><th>指标</th><th>算法</th><th>F1</th><th>Precision</th><th>Recall</th></tr></thead>
            <tbody>
              <tr v-for="r in records" :key="r.id">
                <td class="text-sm">{{ r.created_at }}</td>
                <td>{{ r.asset_id || '-' }}</td>
                <td>{{ r.metric_name }}</td>
                <td><span class="alg-name">{{ r.algorithm }}</span></td>
                <td>{{ r.f1_score?.toFixed(3) || '-' }}</td>
                <td>{{ r.precision?.toFixed(3) || '-' }}</td>
                <td>{{ r.recall?.toFixed(3) || '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div v-if="showRecord" class="modal-overlay" @click.self="showRecord = false">
      <div class="modal-box">
        <h3>录入基准数据</h3>
        <div class="form-group">
          <label class="form-label">算法</label>
          <select v-model="recForm.algorithm" class="input">
            <option value="isolation_forest">Isolation Forest</option>
            <option value="luminol">Luminol</option>
            <option value="mad">MAD</option>
            <option value="ewma">EWMA</option>
            <option value="prophet">Prophet</option>
            <option value="diff">Diff</option>
            <option value="seasonal_decompose">Seasonal Decompose</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Precision (0~1)</label>
          <input v-model.number="recForm.precision" type="number" step="0.01" min="0" max="1" class="input">
        </div>
        <div class="form-group">
          <label class="form-label">Recall (0~1)</label>
          <input v-model.number="recForm.recall" type="number" step="0.01" min="0" max="1" class="input">
        </div>
        <div class="form-group">
          <label class="form-label">F1 Score (0~1)</label>
          <input v-model.number="recForm.f1_score" type="number" step="0.01" min="0" max="1" class="input">
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showRecord = false">取消</button>
          <button class="btn btn-primary" @click="submitRecord">提交</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const days = ref(90)
const stats = ref(null)
const records = ref([])
const recommend = ref(null)
const loading = ref(false)
const showRecord = ref(false)
const recForm = ref({ algorithm: 'isolation_forest', precision: 0.8, recall: 0.75, f1_score: 0.77, asset_id: null, metric_name: '' })

async function loadStats() {
  try {
    const [statsData, recordsData, recommendData] = await Promise.all([
      request.get('/anomaly/api/benchmark/stats', { params: { days: days.value } }),
      request.get('/anomaly/api/benchmark', { params: { page: 1, per_page: 50 } }),
      request.get('/anomaly/api/benchmark/recommend', { params: {} }),
    ])
    stats.value = statsData
    records.value = recordsData.items || []
    recommend.value = recommendData
  } catch (e) { ElMessage.error('加载失败: ' + (e.message || e)) }
}

async function submitRecord() {
  try {
    await request.post('/anomaly/api/benchmark', recForm.value)
    ElMessage.success('已录入')
    showRecord.value = false
    loadStats()
  } catch (e) { ElMessage.error('提交失败: ' + (e.message || e)) }
}

onMounted(() => loadStats())
</script>

<style scoped>
.bench-page { padding: 4px; }
.page-header { margin-bottom: 12px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; margin: 0 0 4px; }
.page-header p { color: var(--text-secondary,#64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong,rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid,#fff); cursor: pointer; font-size: 0.82rem; }
.btn-primary { background: var(--accent,#6366f1); color: #fff; border-color: var(--accent,#6366f1); }
.input { padding: 5px 10px; border: 1px solid var(--border,rgba(0,0,0,0.1)); border-radius: 6px; font-size: 0.82rem; }
.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 14px; }
.stat-card { background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; padding: 14px; text-align: center; }
.stat-value { font-size: 1.8rem; font-weight: 800; }
.stat-label { font-size: 0.75rem; color: var(--text-secondary,#64748b); margin-top: 4px; }
.panel { background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; margin-bottom: 14px; }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; }
.panel-body { padding: 16px 18px; }
.gap-table-wrap { overflow-x: auto; }
.gap-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.gap-table th { text-align: left; padding: 8px 10px; border-bottom: 2px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; color: var(--text-secondary,#64748b); font-size: 0.75rem; text-transform: uppercase; }
.gap-table td { padding: 10px 10px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.05)); vertical-align: middle; }
.gap-table tbody tr:hover { background: var(--bg-hover,rgba(0,0,0,0.02)); }
.best-row { background: rgba(34,197,94,0.04); }
.alg-name { font-weight: 600; font-size: 0.78rem; background: rgba(99,102,241,0.08); padding: 1px 6px; border-radius: 4px; }
.f1-high { color: #22c55e; font-weight: 700; }
.f1-mid { color: #d97706; font-weight: 700; }
.f1-low { color: #ef4444; }
.rec-box { border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 8px; padding: 14px; }
.rec-alg { font-size: 1.1rem; font-weight: 800; color: #6366f1; margin-bottom: 6px; }
.rec-info { font-size: 0.82rem; margin-bottom: 4px; }
.conf-badge { padding: 1px 6px; border-radius: 6px; font-size: 0.72rem; font-weight: 600; }
.high { background: rgba(34,197,94,0.12); color: #22c55e; }
.medium { background: rgba(245,158,11,0.12); color: #d97706; }
.low { background: rgba(148,163,184,0.12); color: #64748b; }
.rec-reason { font-size: 0.82rem; color: var(--text-secondary,#64748b); margin-bottom: 4px; }
.rec-f1 { font-size: 0.82rem; color: #22c55e; font-weight: 600; }
.text-sm { font-size: 0.78rem; }
.form-group { margin-bottom: 10px; }
.form-label { display: block; font-size: 0.78rem; font-weight: 600; color: var(--text-secondary,#64748b); margin-bottom: 4px; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid,#fff); border-radius: 12px; padding: 24px; min-width: 380px; box-shadow: 0 8px 32px rgba(0,0,0,0.15); }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; font-weight: 600; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary,#94a3b8); font-size: 0.9rem; }
</style>
