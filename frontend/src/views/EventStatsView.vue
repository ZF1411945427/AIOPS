<template>
  <div class="event-stats-page">
    <div class="page-header">
      <h1>事件统计</h1>
      <p>K8s 集群事件统计分析</p>
    </div>

    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-icon blue">📊</div>
        <div class="stat-body"><div class="stat-value">{{ stats.total || 0 }}</div><div class="stat-label">总事件数</div></div>
      </div>
      <div class="stat-card warning">
        <div class="stat-icon yellow">⚠️</div>
        <div class="stat-body"><div class="stat-value">{{ stats.warnings || 0 }}</div><div class="stat-label">警告事件</div></div>
      </div>
      <div class="stat-card danger">
        <div class="stat-icon red">🔴</div>
        <div class="stat-body"><div class="stat-value">{{ stats.criticals || 0 }}</div><div class="stat-label">严重事件</div></div>
      </div>
      <div class="stat-card">
        <div class="stat-icon gray">ℹ️</div>
        <div class="stat-body"><div class="stat-value">{{ stats.infos || 0 }}</div><div class="stat-label">普通事件</div></div>
      </div>
    </div>

    <div class="grid-2">
      <div class="panel">
        <div class="panel-header"><h3>按资源类型分布 (Top 10)</h3></div>
        <div class="panel-body">
          <div v-if="loading" class="loading-state">加载中...</div>
          <table v-else-if="stats.by_kind && stats.by_kind.length" class="table">
            <thead><tr><th>资源类型</th><th>数量</th><th>占比</th></tr></thead>
            <tbody>
              <tr v-for="item in stats.by_kind" :key="item.kind">
                <td>{{ item.kind }}</td>
                <td>{{ item.count }}</td>
                <td>
                  <div class="bar-wrap">
                    <div class="bar-fill blue" :style="{ width: barWidth(item.count, stats.total) + '%' }"></div>
                    <span class="bar-text">{{ pct(item.count, stats.total) }}%</span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-state">暂无数据</div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header"><h3>按原因分布 (Top 10)</h3></div>
        <div class="panel-body">
          <div v-if="loading" class="loading-state">加载中...</div>
          <table v-else-if="stats.by_reason && stats.by_reason.length" class="table">
            <thead><tr><th>原因</th><th>数量</th><th>占比</th></tr></thead>
            <tbody>
              <tr v-for="item in stats.by_reason" :key="item.reason">
                <td>{{ item.reason }}</td>
                <td>{{ item.count }}</td>
                <td>
                  <div class="bar-wrap">
                    <div class="bar-fill orange" :style="{ width: barWidth(item.count, stats.total) + '%' }"></div>
                    <span class="bar-text">{{ pct(item.count, stats.total) }}%</span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-state">暂无数据</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const stats = ref({})

async function loadStats() {
  loading.value = true
  try {
    const data = await request.get('/events/api/stats')
    stats.value = data
  } catch (e) {
    ElMessage.error('加载统计失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function pct(count, total) {
  if (!total) return 0
  return ((count / total) * 100).toFixed(1)
}
function barWidth(count, total) {
  return Math.max(2, pct(count, total))
}

onMounted(loadStats)
</script>

<style scoped>
.event-stats-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.stat-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 16px; }
.stat-card { display: flex; align-items: center; gap: 12px; background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; padding: 14px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.stat-icon { width: 38px; height: 38px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px; background: rgba(99,102,241,0.1); }
.stat-icon.blue { background: rgba(59,130,246,0.1); }
.stat-icon.red { background: rgba(239,68,68,0.1); }
.stat-icon.yellow { background: rgba(245,158,11,0.1); }
.stat-icon.gray { background: rgba(100,116,139,0.1); }
.stat-value { font-size: 1.3rem; font-weight: 700; color: var(--text, #1e293b); }
.stat-label { font-size: 0.72rem; color: var(--text-secondary, #64748b); }
.grid-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-header { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.panel-header h3 { margin: 0; font-size: 0.95rem; color: var(--text, #1e293b); }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.bar-wrap { display: flex; align-items: center; gap: 8px; min-width: 120px; }
.bar-fill { height: 8px; border-radius: 4px; min-width: 2px; }
.bar-fill.blue { background: linear-gradient(90deg, #3b82f6, #60a5fa); }
.bar-fill.orange { background: linear-gradient(90deg, #f59e0b, #fbbf24); }
.bar-text { font-size: 0.72rem; color: var(--text-secondary, #64748b); white-space: nowrap; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
</style>
