<template>
  <div class="eval-page">
    <div class="page-header">
      <h1>Agent 评估看板</h1>
      <p>AI 智能体质量追踪 · 工具成功率 / 任务完成率 / 幻觉率 / 轮次效率</p>
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
        <div class="stat-value" style="color:#6366f1;">{{ stats.total_evals }}</div>
        <div class="stat-label">评估总数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="color:#22c55e;">{{ stats.success_rate }}%</div>
        <div class="stat-label">任务成功率</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="color:#ef4444;">{{ stats.hallucination_rate }}%</div>
        <div class="stat-label">幻觉率</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="color:#14b8a6;">{{ stats.avg_latency_ms }}ms</div>
        <div class="stat-label">平均延迟</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="color:#f59e0b;">{{ stats.avg_round_count }}</div>
        <div class="stat-label">平均轮次</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="color:#8b5cf6;">{{ stats.total_sessions }}</div>
        <div class="stat-label">会话总数</div>
      </div>
    </div>

    <div v-if="stats" class="panel">
      <div class="panel-head">工具调用排行</div>
      <div class="panel-body">
        <div v-if="stats.tools.length" class="tool-table-wrap">
          <table class="gap-table">
            <thead><tr><th>中文名</th><th>工具名</th><th>调用次数</th><th>成功</th><th>成功率</th><th>平均延迟</th></tr></thead>
            <tbody>
              <tr v-for="t in stats.tools" :key="t.tool_name">
                <td><span class="tool-display-name">{{ t.display_name || t.tool_name }}</span></td>
                <td><span class="tool-name">{{ t.tool_name }}</span></td>
                <td>{{ t.count }}</td>
                <td>{{ t.is_success }}</td>
                <td><span class="rate-badge" :class="rateClass(t.success_rate)">{{ t.success_rate }}%</span></td>
                <td>{{ t.avg_latency_ms }}ms</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty-state">暂无工具调用数据</div>
      </div>
    </div>

    <div v-if="stats && stats.daily_trend.length" class="panel">
      <div class="panel-head">每日趋势</div>
      <div class="panel-body">
        <div class="trend-chart">
          <div v-for="d in stats.daily_trend" :key="d.date" class="trend-bar-wrap">
            <div class="trend-bar" :style="{height: Math.max(4, d.count * 3) + 'px', background: '#6366f1'}"></div>
            <div class="trend-label">{{ d.date.slice(5) }}</div>
            <div class="trend-rate">{{ d.success_rate }}%</div>
          </div>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head">评估历史</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="!history.length" class="empty-state">暂无评估记录</div>
        <div v-else class="gap-table-wrap">
          <table class="gap-table">
            <thead><tr><th>时间</th><th>模型</th><th>延迟</th><th>轮次</th><th>工具</th><th>成功率</th><th>幻觉</th></tr></thead>
            <tbody>
              <tr v-for="e in history" :key="e.id">
                <td class="text-sm">{{ e.created_at }}</td>
                <td>{{ e.model_name || '-' }}</td>
                <td>{{ e.latency_ms }}ms</td>
                <td>{{ e.round_count }}</td>
                <td>{{ e.tool_call_count }}</td>
                <td><span class="rate-badge" :class="e.is_success ? 'rate-high' : 'rate-low'">{{ e.is_success ? '成功' : '失败' }}</span></td>
                <td><span v-if="e.has_hallucination" class="rate-badge rate-low">幻觉</span><span v-else class="text-muted">-</span></td>
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
const loading = ref(false)

function rateClass(r) {
  if (r >= 90) return 'rate-high'
  if (r >= 70) return 'rate-mid'
  return 'rate-low'
}

async function loadStats() {
  try {
    const data = await request.get('/agent/api/eval/stats', { params: { days: days.value } })
    stats.value = data
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.message || e))
  }
}

async function loadHistory() {
  loading.value = true
  try {
    const data = await request.get('/agent/api/eval/history', { params: { page: 1, per_page: 50 } })
    history.value = data.items || []
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

onMounted(() => { loadStats(); loadHistory() })
</script>

<style scoped>
.eval-page { padding: 4px; }
.page-header { margin-bottom: 12px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 14px; align-items: center; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid,#fff); color: var(--text); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.input { padding: 5px 10px; border: 1px solid var(--border, rgba(0,0,0,0.1)); border-radius: 6px; font-size: 0.82rem; }
.stats-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 14px; }
.stat-card { background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; padding: 14px; text-align: center; }
.stat-value { font-size: 1.8rem; font-weight: 800; line-height: 1.2; }
.stat-label { font-size: 0.75rem; color: var(--text-secondary,#64748b); margin-top: 4px; }
.panel { background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 14px; }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; }
.panel-body { padding: 16px 18px; }
.tool-table-wrap { overflow-x: auto; }
.gap-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.gap-table th { text-align: left; padding: 8px 10px; border-bottom: 2px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; color: var(--text-secondary,#64748b); font-size: 0.75rem; text-transform: uppercase; }
.gap-table td { padding: 10px 10px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.05)); vertical-align: middle; }
.gap-table tbody tr:hover { background: var(--bg-hover,rgba(0,0,0,0.02)); }
.tool-name { font-weight: 600; font-family: monospace; background: rgba(99,102,241,0.08); padding: 1px 6px; border-radius: 4px; font-size: 0.78rem; color: #6366f1; }
.tool-display-name { font-weight: 600; color: #1e293b; font-size: 0.85rem; }
.rate-badge { font-size: 0.75rem; font-weight: 600; padding: 2px 8px; border-radius: 8px; }
.rate-high { background: rgba(34,197,94,0.12); color: #22c55e; }
.rate-mid { background: rgba(245,158,11,0.12); color: #d97706; }
.rate-low { background: rgba(239,68,68,0.12); color: #ef4444; }
.trend-chart { display: flex; gap: 6px; align-items: flex-end; height: 80px; }
.trend-bar-wrap { display: flex; flex-direction: column; align-items: center; gap: 2px; flex: 1; }
.trend-bar { width: 100%; max-width: 40px; border-radius: 4px 4px 0 0; min-height: 4px; }
.trend-label { font-size: 0.65rem; color: var(--text-secondary,#64748b); }
.trend-rate { font-size: 0.65rem; color: #6366f1; font-weight: 600; }
.text-sm { font-size: 0.78rem; }
.text-muted { color: var(--text-tertiary,#94a3b8); }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary,#94a3b8); font-size: 0.9rem; }
</style>
