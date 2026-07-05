<template>
  <div class="rep-page">
    <div class="page-header">
      <h1>运维报表</h1>
      <p>日报 / 周报 / 月报生成与查看 · {{ reports.length }} 份报表</p>
    </div>

    <div v-if="!currentReport" class="toolbar">
      <button class="btn btn-primary" @click="generate('daily')" :disabled="generating">生成日报</button>
      <button class="btn btn-primary" @click="generate('weekly')" :disabled="generating">生成周报</button>
      <button class="btn btn-primary" @click="generate('monthly')" :disabled="generating">生成月报</button>
      <button class="btn" @click="loadReports" style="margin-left:auto;">刷新</button>
    </div>

    <div v-if="!currentReport" class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="reports.length" class="card-grid">
          <div v-for="r in reports" :key="r.id" class="rep-card" @click="viewReport(r.id)">
            <div class="card-top">
              <span class="badge" :class="r.type">{{ typeLabel(r.type) }}</span>
              <span class="text-sm">{{ r.created_at || '-' }}</span>
            </div>
            <div class="rep-title">{{ r.title }}</div>
            <div class="rep-period text-sm">{{ r.period_start || '-' }} ~ {{ r.period_end || '-' }}</div>
            <div class="rep-summary text-sm">{{ (r.summary || '').slice(0, 120) }}{{ (r.summary || '').length > 120 ? '...' : '' }}</div>
          </div>
        </div>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">📊</div><div>暂无报表，点击上方按钮生成</div></div>
      </div>
    </div>

    <div v-else class="detail-view">
      <div class="toolbar">
        <button class="btn" @click="backToList">← 返回列表</button>
        <span class="rep-title-inline">{{ currentReport.title }}</span>
      </div>

      <div class="stat-cards">
        <div class="stat-card blue"><div class="stat-num">{{ detail.total_alerts || 0 }}</div><div class="stat-label">告警总数</div></div>
        <div class="stat-card red"><div class="stat-num">{{ detail.critical_count || 0 }}</div><div class="stat-label">严重告警</div></div>
        <div class="stat-card green"><div class="stat-num">{{ detail.resolve_rate || 0 }}%</div><div class="stat-label">解决率</div></div>
        <div class="stat-card indigo"><div class="stat-num">{{ detail.asset_count || 0 }}</div><div class="stat-label">资产总数</div></div>
        <div class="stat-card teal"><div class="stat-num">{{ detail.asset_health || 0 }}%</div><div class="stat-label">在线率</div></div>
        <div class="stat-card orange"><div class="stat-num">{{ detail.total_incidents || 0 }}</div><div class="stat-label">事件总数</div></div>
      </div>

      <div class="grid-2">
        <div class="panel">
          <div class="panel-head">告警级别分布</div>
          <div class="panel-body">
            <div v-if="severityEntries.length" class="bar-list">
              <div v-for="[k, v] in severityEntries" :key="k" class="bar-row">
                <span class="bar-label">{{ k }}</span>
                <div class="bar-track"><div class="bar-fill" :class="sevClass(k)" :style="{ width: barWidth(v, maxSeverity) }"></div></div>
                <span class="bar-num">{{ v }}</span>
              </div>
            </div>
            <div v-else class="empty-state">暂无数据</div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">资产概览</div>
          <div class="panel-body">
            <div class="kv-row"><span>在线</span><span class="num on">{{ detail.online_count || 0 }} 台</span></div>
            <div class="kv-row"><span>离线</span><span class="num off">{{ detail.offline_count || 0 }} 台</span></div>
            <div class="kv-row"><span>在线率</span><span class="num">{{ detail.asset_health || 0 }}%</span></div>
            <div class="progress-track" style="margin-top:8px;"><div class="progress-fill" :style="{ width: (detail.asset_health || 0) + '%' }"></div></div>
            <div style="margin-top:16px;font-weight:600;font-size:0.85rem;color:var(--text-secondary,#64748b);">事件概览</div>
            <div class="kv-row"><span>未关闭</span><span class="num warn">{{ detail.open_incidents || 0 }} 个</span></div>
            <div class="kv-row"><span>已关闭</span><span class="num on">{{ detail.resolved_incidents || 0 }} 个</span></div>
          </div>
        </div>
      </div>

      <div class="grid-2" style="margin-top:14px;">
        <div class="panel">
          <div class="panel-head">高频告警指标 TOP</div>
          <div class="panel-body">
            <div v-if="detail.top_rules && detail.top_rules.length" class="rank-list">
              <div v-for="(item, i) in detail.top_rules" :key="i" class="rank-row">
                <span class="rank-no">{{ i + 1 }}</span>
                <span class="rank-name">{{ item[0] }}</span>
                <span class="rank-count">{{ item[1] }} 次</span>
              </div>
            </div>
            <div v-else class="empty-state">暂无数据</div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">告警最多资产 TOP</div>
          <div class="panel-body">
            <div v-if="detail.top_assets && detail.top_assets.length" class="rank-list">
              <div v-for="(item, i) in detail.top_assets" :key="i" class="rank-row">
                <span class="rank-no">{{ i + 1 }}</span>
                <span class="rank-name">{{ item.name }}</span>
                <span class="rank-count">{{ item.count }} 次</span>
              </div>
            </div>
            <div v-else class="empty-state">暂无数据</div>
          </div>
        </div>
      </div>

      <div class="panel" style="margin-top:14px;">
        <div class="panel-head">评估与建议</div>
        <div class="panel-body">
          <pre class="summary-pre">{{ extractAdvice(currentReport.summary) }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const generating = ref(false)
const reports = ref([])
const currentReport = ref(null)
const detail = ref({})

const severityEntries = computed(() => {
  const bs = detail.value.by_severity || {}
  return Object.entries(bs)
})
const maxSeverity = computed(() => Math.max(1, ...severityEntries.value.map(([, v]) => v)))

function typeLabel(t) {
  return { daily: '日报', weekly: '周报', monthly: '月报' }[t] || t
}
function sevClass(k) {
  if (k.includes('严重') || k === 'critical') return 'sev-critical'
  if (k.includes('警告') || k === 'warning') return 'sev-warning'
  return 'sev-info'
}
function barWidth(v, max) {
  return Math.max(4, Math.round(v / max * 100)) + '%'
}
function extractAdvice(summary) {
  if (!summary) return '暂无评估'
  const idx = summary.indexOf('【评估与建议】')
  return idx >= 0 ? summary.slice(idx).replace('【评估与建议】', '').trim() : summary
}

async function loadReports() {
  loading.value = true
  try {
    const data = await request.get('/reports/api/list')
    reports.value = data.reports || []
  } catch (e) {
    ElMessage.error('加载失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

async function generate(type) {
  generating.value = true
  try {
    const data = await request.post(`/reports/api/generate/${type}`)
    if (data.status === 'ok') {
      ElMessage.success(`${typeLabel(type)}已生成: ${data.title}`)
      loadReports()
    }
  } catch (e) {
    ElMessage.error('生成失败: ' + (e.message || e))
  } finally {
    generating.value = false
  }
}

async function viewReport(id) {
  try {
    const data = await request.get(`/reports/api/${id}`)
    if (data.status === 'error') {
      ElMessage.error(data.message)
      return
    }
    currentReport.value = { id: data.id, title: data.title, type: data.type, summary: data.summary }
    detail.value = data.data || {}
  } catch (e) {
    ElMessage.error('加载详情失败: ' + (e.message || e))
  }
}

function backToList() {
  currentReport.value = null
  detail.value = {}
}

onMounted(loadReports)
</script>

<style scoped>
.rep-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); }
.panel-body { padding: 16px 18px; }
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.rep-card { border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; padding: 14px; background: var(--bg-card-solid, #fff); cursor: pointer; transition: all 0.2s; }
.rep-card:hover { border-color: var(--accent, #6366f1); box-shadow: 0 2px 8px rgba(99,102,241,0.15); transform: translateY(-1px); }
.card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.rep-title { font-weight: 600; font-size: 0.95rem; color: var(--text, #1e293b); margin-bottom: 4px; }
.rep-period { margin-bottom: 6px; }
.rep-summary { line-height: 1.5; color: var(--text-secondary, #64748b); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.daily { background: rgba(59,130,246,0.1); color: #3b82f6; }
.badge.weekly { background: rgba(99,102,241,0.1); color: #6366f1; }
.badge.monthly { background: rgba(168,85,247,0.1); color: #a855f7; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.rep-title-inline { font-weight: 600; margin-left: 8px; color: var(--text, #1e293b); }
.stat-cards { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin-bottom: 14px; }
.stat-card { border-radius: 8px; padding: 14px; text-align: center; color: #fff; }
.stat-card.blue { background: linear-gradient(135deg, #3b82f6, #2563eb); }
.stat-card.red { background: linear-gradient(135deg, #ef4444, #dc2626); }
.stat-card.green { background: linear-gradient(135deg, #22c55e, #16a34a); }
.stat-card.indigo { background: linear-gradient(135deg, #6366f1, #4f46e5); }
.stat-card.teal { background: linear-gradient(135deg, #14b8a6, #0d9488); }
.stat-card.orange { background: linear-gradient(135deg, #f59e0b, #d97706); }
.stat-num { font-size: 1.6rem; font-weight: 700; }
.stat-label { font-size: 0.72rem; opacity: 0.9; margin-top: 2px; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.bar-list { display: flex; flex-direction: column; gap: 10px; }
.bar-row { display: flex; align-items: center; gap: 8px; }
.bar-label { min-width: 48px; font-size: 0.8rem; color: var(--text-secondary, #64748b); }
.bar-track { flex: 1; height: 18px; background: rgba(0,0,0,0.05); border-radius: 4px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.4s; }
.bar-fill.sev-critical { background: linear-gradient(90deg, #ef4444, #dc2626); }
.bar-fill.sev-warning { background: linear-gradient(90deg, #f59e0b, #d97706); }
.bar-fill.sev-info { background: linear-gradient(90deg, #3b82f6, #2563eb); }
.bar-num { min-width: 32px; text-align: right; font-size: 0.82rem; font-weight: 600; color: var(--text, #1e293b); }
.kv-row { display: flex; justify-content: space-between; padding: 6px 0; font-size: 0.85rem; border-bottom: 1px dashed var(--border, rgba(0,0,0,0.07)); }
.kv-row:last-child { border-bottom: none; }
.num { font-weight: 600; }
.num.on { color: #22c55e; }
.num.off { color: #64748b; }
.num.warn { color: #f59e0b; }
.progress-track { height: 8px; background: rgba(0,0,0,0.05); border-radius: 4px; overflow: hidden; }
.progress-fill { height: 100%; background: linear-gradient(90deg, #22c55e, #16a34a); border-radius: 4px; transition: width 0.4s; }
.rank-list { display: flex; flex-direction: column; gap: 8px; }
.rank-row { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-bottom: 1px dashed var(--border, rgba(0,0,0,0.07)); }
.rank-row:last-child { border-bottom: none; }
.rank-no { min-width: 22px; height: 22px; border-radius: 50%; background: var(--accent, #6366f1); color: #fff; font-size: 0.72rem; font-weight: 600; display: flex; align-items: center; justify-content: center; }
.rank-name { flex: 1; font-size: 0.85rem; color: var(--text, #1e293b); }
.rank-count { font-size: 0.8rem; color: var(--text-secondary, #64748b); font-weight: 600; }
.summary-pre { white-space: pre-wrap; font-family: inherit; font-size: 0.85rem; line-height: 1.7; color: var(--text, #1e293b); margin: 0; }
</style>
