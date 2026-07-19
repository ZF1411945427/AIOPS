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
      <button class="btn btn-guide" @click="showGuide = !showGuide">📖 操作说明</button>
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
    <GuideDrawer v-model="showGuide" title="📖 异常检测基准评估 · 操作说明">
      <section class="guide-section">
        <h4>1. 这个页面是干嘛的？</h4>
        <p>简单说：<strong>给"异常检测算法"打分</strong>，帮你选出最准的算法。</p>
        <p>系统里有多种异常检测算法（Isolation Forest、Luminol、MAD、EWMA、Prophet 等），但哪个算法对你自己的数据最准？光看理论说不清，得用<strong>真实数据测一遍</strong>。</p>
        <p>这个页面就是让你<strong>录入测试结果</strong>（某个算法在某指标上的表现），系统帮你统计对比，推荐最优算法。</p>
      </section>
      <section class="guide-section">
        <h4>2. 核心概念：三个评分指标</h4>
        <p>每个算法测试后会得到三个分数（都在 0~1 之间，越接近 1 越好）：</p>
        <div class="key-value-list">
          <div class="kv-row">
            <span class="kv-key">Precision<br>(精确率)</span>
            <span class="kv-val">算法报的异常里，<strong>真异常</strong>占多少。<br>例：算法报了 10 个异常，其中 8 个是真的 → Precision = 0.8<br>⚠️ Precision 低 = 误报多（狼来了）</span>
          </div>
          <div class="kv-row">
            <span class="kv-key">Recall<br>(召回率)</span>
            <span class="kv-val">真实的异常里，<strong>算法抓到了多少</strong>。<br>例：实际有 10 个异常，算法抓到 7 个 → Recall = 0.7<br>⚠️ Recall 低 = 漏报多（漏检）</span>
          </div>
          <div class="kv-row">
            <span class="kv-key">F1 Score<br>(综合分)</span>
            <span class="kv-val">Precision 和 Recall 的<strong>平衡分</strong>，是综合评价。<br>F1 = 2 × P × R / (P + R)<br>💡 选算法时主要看 F1，越高越好</span>
          </div>
        </div>
        <div class="tip-box">💡 没有完美算法：Precision 高的往往 Recall 低，反之亦然。F1 是平衡点。比如告警场景怕漏报，可侧重 Recall；怕误报烦人，可侧重 Precision。</div>
      </section>
      <section class="guide-section">
        <h4>3. 页面三个区域</h4>
        <ul>
          <li><strong>统计卡片</strong> — 显示总记录数、最优算法（F1 最高的）</li>
          <li><strong>各算法效果对比表</strong> — 每个算法的平均 P/R/F1，绿色高亮最优算法</li>
          <li><strong>算法推荐</strong> — 系统基于历史数据自动推荐最优算法 + 置信度 + 理由</li>
          <li><strong>基准记录表</strong> — 你录入的所有测试记录明细</li>
        </ul>
        <p>F1 颜色含义：<span class="tag-demo" style="background:rgba(34,197,94,0.12);color:#22c55e;">≥0.8 绿</span>（优秀）/ <span class="tag-demo" style="background:rgba(245,158,11,0.12);color:#d97706;">≥0.6 橙</span>（及格）/ <span class="tag-demo" style="background:rgba(239,68,68,0.12);color:#ef4444;">&lt;0.6 红</span>（较差）</p>
      </section>
      <section class="guide-section">
        <h4>4. 怎么操作？</h4>
        <h5>步骤 1：跑算法测试（页面外）</h5>
        <p>先在你的数据上跑一遍某个异常检测算法，拿到测试结果。比如对 CPU 使用率指标跑 Isolation Forest 算法，得到 Precision=0.85、Recall=0.75、F1=0.80。</p>
        <h5>步骤 2：录入基准</h5>
        <ul>
          <li>点击右上角 <code>+ 录入基准</code> 按钮</li>
          <li>选择算法（如 Isolation Forest）</li>
          <li>填入 Precision / Recall / F1（0~1 之间的小数）</li>
          <li>点"提交"</li>
        </ul>
        <h5>步骤 3：查看对比和推荐</h5>
        <p>录入后页面自动刷新，对比表会显示该算法的平均分，推荐区会基于历史数据推荐最优算法。多次录入不同算法后，对比效果更明显。</p>
      </section>
      <section class="guide-section">
        <h4>5. 实战例子</h4>
        <p>假设你管理 10 台服务器的 CPU 监控，想找出最准的异常检测算法：</p>
        <ul>
          <li>第 1 周：跑 Isolation Forest，录入 P=0.85, R=0.75, F1=0.80</li>
          <li>第 2 周：跑 MAD，录入 P=0.70, R=0.90, F1=0.79</li>
          <li>第 3 周：跑 EWMA，录入 P=0.60, R=0.95, F1=0.74</li>
        </ul>
        <p>系统对比后推荐 Isolation Forest（F1 最高 0.80），你就可以在「异常检测配置」页选它做主算法。</p>
        <div class="tip-box">💡 这就像买手机：看评测（录入基准）→ 对比参数（对比表）→ 选最高性价比（推荐算法）。区别是这里评测的是算法，不是手机。</div>
      </section>
    </GuideDrawer>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'
import GuideDrawer from '@/components/GuideDrawer.vue'

const days = ref(90)
const stats = ref(null)
const records = ref([])
const recommend = ref(null)
const loading = ref(false)
const showRecord = ref(false)
const showGuide = ref(false)
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
