<template>
  <div class="effect-page">
    <div class="page-header">
      <h1>自愈效果分析</h1>
      <p>追踪自愈执行效果 · 统计成功率 · 推荐最佳规则</p>
    </div>

    <div class="toolbar">
      <label style="font-size:0.82rem;color:var(--text-secondary);">统计周期:</label>
      <select v-model.number="days" class="input" style="width:100px;" @change="loadStats">
        <option :value="7">近7天</option>
        <option :value="14">近14天</option>
        <option :value="30">近30天</option>
        <option :value="90">近90天</option>
      </select>
      <button class="btn" @click="loadStats">刷新</button>
    </div>

    <div v-if="stats" class="stats-grid">
      <div class="stat-card">
        <div class="stat-value" style="color:#6366f1;">{{ stats.total }}</div>
        <div class="stat-label">总执行次数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="color:#22c55e;">{{ stats.success_rate }}%</div>
        <div class="stat-label">完全恢复率</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="color:#14b8a6;">{{ stats.improve_rate }}%</div>
        <div class="stat-label">改善率</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="color:#ef4444;">{{ stats.no_change }}</div>
        <div class="stat-label">无效次数</div>
      </div>
    </div>

    <div class="effect-summary" v-if="stats">
      <div class="summary-bar">
        <div class="summary-fill" :style="{width: stats.success_rate + '%', background:'#22c55e'}"></div>
        <div class="summary-fill" :style="{width: (stats.improve_rate - stats.success_rate) + '%', background:'#14b8a6'}"></div>
        <div class="summary-fill" :style="{width: (100 - stats.improve_rate) + '%', background:'#94a3b8'}"></div>
      </div>
      <div class="summary-legend">
        <span class="legend-item"><span class="dot" style="background:#22c55e"></span>完全恢复 {{ stats.resolved }} 次</span>
        <span class="legend-item"><span class="dot" style="background:#14b8a6"></span>改善 {{ stats.improved }} 次</span>
        <span class="legend-item"><span class="dot" style="background:#94a3b8"></span>无变化 {{ stats.no_change }} 次</span>
      </div>
    </div>

    <div v-if="recommendations.length" class="panel">
      <div class="panel-head">规则推荐</div>
      <div class="panel-body">
        <div v-for="r in recommendations" :key="r.remediation_id" class="rec-rule">
          <div class="rec-rule-head">
            <span class="rec-rule-name">{{ r.name }}</span>
            <span class="rec-rule-rate">{{ r.success_rate }}%</span>
            <span class="rec-rule-badge">{{ r.recommendation }}</span>
          </div>
          <div class="rec-rule-meta">
            <span>动作: {{ r.action_type }}</span>
            <span>执行 {{ r.total_executions }} 次</span>
            <span>恢复 {{ r.resolved_count }} 次</span>
          </div>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head">各规则效果</div>
      <div class="panel-body">
        <div v-if="stats && stats.by_remediation.length" class="rem-table-wrap">
          <table class="gap-table">
            <thead>
              <tr>
                <th>规则名称</th><th>动作</th><th>总执行</th><th>恢复</th><th>成功率</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in stats.by_remediation" :key="r.remediation_id">
                <td><span class="rem-name">{{ r.name }}</span></td>
                <td><span class="tag-mini">{{ r.action_type }}</span></td>
                <td>{{ r.total }}</td>
                <td>{{ r.resolved }}</td>
                <td>
                  <span class="rate-badge" :class="rateClass(r.success_rate)">{{ r.success_rate }}%</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty-state">暂无执行数据</div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head">效果历史</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="!history.length" class="empty-state">暂无效果记录</div>
        <div v-else class="gap-table-wrap">
          <table class="gap-table">
            <thead>
              <tr>
                <th>时间</th><th>告警</th><th>效果</th><th>修复前</th><th>修复后</th><th>备注</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="e in history" :key="e.id">
                <td class="text-sm">{{ e.created_at }}</td>
                <td v-if="e.alert_id">#{{ e.alert_id }}</td>
                <td v-else>-</td>
                <td>
                  <span class="effect-badge" :class="'effect-' + e.effect">{{ effectLabel(e.effect) }}</span>
                </td>
                <td>{{ e.status_before || '-' }}</td>
                <td>{{ e.status_after || '-' }}</td>
                <td class="text-sm text-muted">{{ e.notes || '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const days = ref(30)
const stats = ref(null)
const history = ref([])
const recommendations = ref([])
const loading = ref(false)

function effectLabel(e) {
  const m = { resolved: '完全恢复', improved: '改善', no_change: '无变化', worsened: '恶化' }
  return m[e] || e
}

function rateClass(rate) {
  if (rate >= 80) return 'rate-high'
  if (rate >= 50) return 'rate-mid'
  return 'rate-low'
}

async function loadStats() {
  try {
    const [statsData, recsData] = await Promise.all([
      request.get('/remediation/api/effect-stats', { params: { days: days.value } }),
      request.get('/remediation/api/effect-recommendations', { params: { limit: 10 } }),
    ])
    stats.value = statsData
    recommendations.value = recsData.items || []
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.message || e))
  }
}

async function loadHistory() {
  loading.value = true
  try {
    const data = await request.get('/remediation/api/effects', { params: { page: 1, per_page: 50 } })
    history.value = data.items || []
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadStats()
  loadHistory()
})
</script>

<style scoped>
.effect-page { padding: 4px; }
.page-header { margin-bottom: 12px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }

.toolbar { display: flex; gap: 8px; margin-bottom: 14px; align-items: center; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.input { padding: 5px 10px; border: 1px solid var(--border, rgba(0,0,0,0.1)); border-radius: 6px; font-size: 0.82rem; }

.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 14px; }
.stat-card { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; padding: 16px; text-align: center; }
.stat-value { font-size: 2rem; font-weight: 800; line-height: 1.2; }
.stat-label { font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-top: 4px; }

.effect-summary { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; padding: 14px; margin-bottom: 14px; }
.summary-bar { display: flex; height: 8px; border-radius: 4px; overflow: hidden; gap: 2px; }
.summary-fill { height: 100%; transition: width 0.3s; }
.summary-legend { display: flex; gap: 16px; margin-top: 8px; font-size: 0.78rem; color: var(--text-secondary); }
.legend-item { display: flex; align-items: center; gap: 4px; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }

.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 14px; }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); }
.panel-body { padding: 16px 18px; }

.rec-rule { padding: 10px 12px; border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; margin-bottom: 8px; }
.rec-rule-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.rec-rule-name { font-weight: 600; font-size: 0.88rem; flex: 1; }
.rec-rule-rate { font-size: 1rem; font-weight: 800; color: #22c55e; }
.rec-rule-badge { font-size: 0.7rem; background: rgba(34,197,94,0.1); color: #22c55e; padding: 2px 8px; border-radius: 8px; font-weight: 600; }
.rec-rule-meta { display: flex; gap: 12px; font-size: 0.75rem; color: var(--text-secondary); }

.gap-table-wrap { overflow-x: auto; }
.gap-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.gap-table th { text-align: left; padding: 8px 10px; border-bottom: 2px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; color: var(--text-secondary, #64748b); font-size: 0.75rem; text-transform: uppercase; }
.gap-table td { padding: 10px 10px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.05)); vertical-align: middle; }
.gap-table tbody tr:hover { background: var(--bg-hover, rgba(0,0,0,0.02)); }
.rem-name { font-weight: 600; }
.tag-mini { display: inline-block; padding: 1px 6px; border-radius: 4px; background: rgba(99,102,241,0.08); color: var(--accent, #6366f1); font-size: 0.7rem; }
.rate-badge { font-size: 0.78rem; font-weight: 700; padding: 2px 8px; border-radius: 8px; }
.rate-high { background: rgba(34,197,94,0.12); color: #22c55e; }
.rate-mid { background: rgba(245,158,11,0.12); color: #d97706; }
.rate-low { background: rgba(239,68,68,0.12); color: #ef4444; }

.effect-badge { font-size: 0.75rem; font-weight: 600; padding: 2px 8px; border-radius: 8px; }
.effect-resolved { background: rgba(34,197,94,0.12); color: #22c55e; }
.effect-improved { background: rgba(20,184,166,0.12); color: #14b8a6; }
.effect-no_change { background: rgba(148,163,184,0.12); color: #64748b; }
.effect-worsened { background: rgba(239,68,68,0.12); color: #ef4444; }

.text-sm { font-size: 0.78rem; }
.text-muted { color: var(--text-tertiary, #94a3b8); }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
</style>
