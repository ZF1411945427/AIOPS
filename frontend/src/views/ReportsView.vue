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
            <button class="card-del" @click.stop="deleteReport(r.id, $event)" title="删除">×</button>
            <div class="card-top">
              <span class="badge" :class="r.type">{{ typeLabel(r.type) }}</span>
              <span class="text-sm">{{ r.created_at || '-' }}</span>
            </div>
            <div class="rep-title">{{ r.title }}</div>
            <div class="rep-period text-sm">{{ r.period_started_at || '-' }} ~ {{ r.period_ended_at || '-' }}</div>
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
        <button class="btn btn-primary" style="margin-left:auto;" @click="exportReport">导出 HTML</button>
      </div>

      <div class="exec-summary" :class="overallGrade">
        <div class="exec-grade">{{ overallGrade === 'A' ? '优' : overallGrade === 'B' ? '良' : overallGrade === 'C' ? '中' : '差' }}</div>
        <div class="exec-body">
          <div class="exec-title">{{ overallTitle }}</div>
          <div class="exec-meta">告警 {{ detail.total_alerts }} 条 · 严重 {{ detail.critical_count }} 条 · 解决率 {{ detail.resolve_rate }}% · 平均处置 {{ detail.avg_resolve_minutes || '-' }} 分钟</div>
          <div class="exec-meta" v-if="detail.prev_total_alerts">环比：上周期 {{ detail.prev_total_alerts }} 条 → 本期 {{ detail.total_alerts }} 条（{{ diffText(detail.total_alerts, detail.prev_total_alerts) }}）</div>
        </div>
      </div>

      <div class="stat-cards">
        <div class="stat-card blue"><div class="stat-num">{{ detail.total_alerts || 0 }}</div><div class="stat-label">告警总数</div>
          <div v-if="detail.prev_total_alerts" class="stat-diff" :class="diffClass(detail.total_alerts - detail.prev_total_alerts)">{{ diffText(detail.total_alerts, detail.prev_total_alerts) }}</div>
        </div>
        <div class="stat-card red"><div class="stat-num">{{ detail.critical_count || 0 }}</div><div class="stat-label">严重告警</div></div>
        <div class="stat-card green"><div class="stat-num">{{ detail.resolve_rate || 0 }}%</div><div class="stat-label">解决率</div>
          <div v-if="detail.prev_resolve_rate" class="stat-diff" :class="diffClass(detail.resolve_rate - detail.prev_resolve_rate)">{{ diffText(detail.resolve_rate, detail.prev_resolve_rate) }}</div>
        </div>
        <div class="stat-card purple"><div class="stat-num">{{ detail.avg_resolve_minutes || '-' }}</div><div class="stat-label">平均处置(分钟)</div></div>
        <div class="stat-card indigo"><div class="stat-num">{{ detail.asset_count || 0 }}</div><div class="stat-label">资产总数</div></div>
        <div class="stat-card teal"><div class="stat-num">{{ detail.asset_health || 0 }}%</div><div class="stat-label">在线率</div></div>
      </div>

      <div class="chart-row">
        <div class="panel"><div class="panel-head">告警趋势</div><div class="panel-body"><div ref="trendChartRef" class="echart-box"></div></div></div>
        <div class="panel"><div class="panel-head">告警级别分布</div><div class="panel-body"><div ref="severityChartRef" class="echart-box"></div></div></div>
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

      <div class="panel" style="margin-top:14px;" v-if="groupedIncidents.length">
        <div class="panel-head">受影响资产（{{ groupedIncidents.length }} 个）</div>
        <div class="panel-body">
          <div class="inc-table">
            <div class="inc-row inc-header">
              <span class="inc-col-title">资产</span>
              <span class="inc-col-sev">级别</span>
              <span class="inc-col-sta">状态</span>
              <span class="inc-col-id" style="text-align:center;">告警数</span>
              <span class="inc-col-time">最近时间</span>
            </div>
            <div v-for="g in groupedIncidents" :key="g.asset" class="inc-row" :class="g.severity">
              <span class="inc-col-title">{{ g.asset }}</span>
              <span class="inc-col-sev"><span class="sev-badge" :class="g.severity">{{ sevLabel(g.severity) }}</span></span>
              <span class="inc-col-sta"><span class="sta-badge" :class="g.status === 'resolved' ? 'resolved' : 'open'">{{ g.status === 'resolved' ? '已处理' : '待处理' }}</span></span>
              <span class="inc-col-id" style="text-align:center;font-weight:600;">{{ g.total_alerts }}</span>
              <span class="inc-col-time">{{ g.latest_time }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="panel" style="margin-top:14px;">
        <div class="panel-head">评估与建议</div>
        <div class="panel-body">
          <pre class="summary-pre">{{ currentReport.summary }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import request from '@/api/request'

const loading = ref(false)
const generating = ref(false)
const reports = ref([])
const currentReport = ref(null)
const detail = ref({})
const trendChartRef = ref(null)
const severityChartRef = ref(null)
let trendChart = null
let severityChart = null

function typeLabel(t) {
  return { daily: '日报', weekly: '周报', monthly: '月报' }[t] || t
}
function diffClass(val) {
  if (val > 0) return 'diff-up'
  if (val < 0) return 'diff-down'
  return 'diff-flat'
}
function diffText(cur, prev) {
  if (!prev || prev === 0) return ''
  const diff = cur - prev
  const pct = Math.round(Math.abs(diff) / prev * 100)
  const arrow = diff > 0 ? '↑' : '↓'
  return `${arrow} ${pct}%`
}

function sevLabel(s) {
  return { critical: '严重', warning: '警告', info: '提示' }[s] || s || '未知'
}
function staLabel(s) {
  return { open: '待处理', analyzing: '分析中', triggered: '已触发', acknowledged: '已确认', resolved: '已解决', closed: '已关闭', done: '已完成' }[s] || s || '未知'
}

const overallGrade = computed(() => {
  const d = detail.value
  if (!d.total_alerts) return 'A'
  if (d.critical_count > 5 || d.resolve_rate < 60) return 'D'
  if (d.critical_count > 2 || d.resolve_rate < 80) return 'C'
  if (d.critical_count > 0) return 'B'
  return 'A'
})
const overallTitle = computed(() => {
  const d = detail.value
  const g = overallGrade.value
  if (g === 'A') return `本周期系统运行平稳，共 ${d.total_alerts} 条告警妥善处置，无严重风险项`
  if (g === 'B') return `本周期系统基本正常，${d.critical_count} 条严重告警已处置，建议关注高频指标`
  if (g === 'C') return `本周期存在 ${d.critical_count} 条严重告警，解决率 ${d.resolve_rate}%，需加强运维响应`
  return `本周期系统告警较多（${d.total_alerts} 条），严重告警 ${d.critical_count} 条，解决率 ${d.resolve_rate}%，建议立即排查并升级处理`
})

const groupedIncidents = computed(() => {
  const incidents = detail.value.incident_details || []
  const groups = {}
  for (const inc of incidents) {
    const title = inc.title || ''
    const m = title.match(/\]\s*(.+?)\s*(异常|故障|告警|down|宕机)/)
    const asset = m ? m[1].trim() : title
    if (!groups[asset]) {
      groups[asset] = { asset, total_alerts: 0, severity: 'info', status: 'open', latest_time: inc.created_at }
    }
    groups[asset].total_alerts += inc.alert_count || 1
    if (inc.severity === 'critical') groups[asset].severity = 'critical'
    if (['resolved', 'closed', 'done'].includes(inc.status)) groups[asset].status = 'resolved'
    if (inc.created_at > groups[asset].latest_time) groups[asset].latest_time = inc.created_at
  }
  return Object.values(groups).sort((a, b) => b.total_alerts - a.total_alerts)
})

function renderCharts() {
  if (!trendChartRef.value || !severityChartRef.value) return
  nextTick(() => {
    const trend = detail.value.trend || []
    if (trend.length && trendChartRef.value) {
      if (!trendChart) trendChart = echarts.init(trendChartRef.value)
      trendChart.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: 40, right: 12, bottom: 24, top: 8 },
        xAxis: { type: 'category', data: trend.map(d => d.date), axisLabel: { fontSize: 11 } },
        yAxis: { type: 'value', minInterval: 1 },
        series: [{
          type: 'line', data: trend.map(d => d.count), smooth: true,
          lineStyle: { color: '#6366f1', width: 2 },
          areaStyle: { color: 'rgba(99,102,241,0.12)' },
          symbol: 'circle', symbolSize: 6,
          itemStyle: { color: '#6366f1' }
        }]
      }, true)
    }
    const sev = detail.value.by_severity || {}
    const sevEntries = Object.entries(sev)
    if (sevEntries.length && severityChartRef.value) {
      if (!severityChart) severityChart = echarts.init(severityChartRef.value)
      const colors = { '严重': '#ef4444', '警告': '#f59e0b', '提示': '#3b82f6' }
      severityChart.setOption({
        tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
        series: [{
          type: 'pie', radius: ['30%', '65%'],
          data: sevEntries.map(([k, v]) => ({ name: k, value: v })),
          label: { formatter: '{b}\n{d}%' },
          color: sevEntries.map(([k]) => colors[k] || '#6366f1')
        }]
      }, true)
    }
  })
}

watch(detail, renderCharts, { deep: true, flush: 'post' })

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
    nextTick(renderCharts)
  } catch (e) {
    ElMessage.error('加载详情失败: ' + (e.message || e))
  }
}

function backToList() {
  currentReport.value = null
  detail.value = {}
  trendChart = null
  severityChart = null
}

function exportReport() {
  if (!currentReport.value) return
  window.open(`/reports/api/${currentReport.value.id}/export`, '_blank')
}

async function deleteReport(id, e) {
  e.stopPropagation()
  try {
    await ElMessageBox.confirm('确认删除这份报表？此操作不可恢复。', '删除报表', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
  } catch (err) {
    return
  }
  try {
    const data = await request.post(`/reports/api/${id}/delete`)
    if (data.status === 'ok') {
      ElMessage.success('已删除')
      loadReports()
    } else {
      ElMessage.error(data.message || '删除失败')
    }
  } catch (err) {
    ElMessage.error('删除失败: ' + (err.message || err))
  }
}

onMounted(loadReports)
onUnmounted(() => {
  trendChart?.dispose()
  severityChart?.dispose()
})
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
.rep-card { border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; padding: 14px; background: var(--bg-card-solid, #fff); cursor: pointer; transition: all 0.2s; position: relative; }
.rep-card:hover { border-color: var(--accent, #6366f1); box-shadow: 0 2px 8px rgba(99,102,241,0.15); transform: translateY(-1px); }
.card-del { position: absolute; top: 6px; right: 8px; width: 22px; height: 22px; border: none; background: transparent; color: var(--text-muted, #94a3b8); font-size: 16px; cursor: pointer; border-radius: 4px; display: flex; align-items: center; justify-content: center; opacity: 0; transition: all 0.15s; line-height: 1; }
.rep-card:hover .card-del { opacity: 0.7; }
.card-del:hover { opacity: 1 !important; background: rgba(239,68,68,0.1); color: #ef4444; }
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
.stat-card.purple { background: linear-gradient(135deg, #a855f7, #7c3aed); }
.stat-num { font-size: 1.6rem; font-weight: 700; }
.stat-label { font-size: 0.72rem; opacity: 0.9; margin-top: 2px; }
.stat-diff { font-size: 0.7rem; font-weight: 600; margin-top: 4px; opacity: 0.9; }
.stat-diff.diff-up { color: #fca5a5; }
.stat-diff.diff-down { color: #86efac; }
.stat-diff.diff-flat { color: #d1d5db; }
.chart-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px; }
.echart-box { width: 100%; height: 260px; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.rank-list { display: flex; flex-direction: column; gap: 8px; }
.rank-row { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-bottom: 1px dashed var(--border, rgba(0,0,0,0.07)); }
.rank-row:last-child { border-bottom: none; }
.rank-no { min-width: 22px; height: 22px; border-radius: 50%; background: var(--accent, #6366f1); color: #fff; font-size: 0.72rem; font-weight: 600; display: flex; align-items: center; justify-content: center; }
.rank-name { flex: 1; font-size: 0.85rem; color: var(--text, #1e293b); }
.rank-count { font-size: 0.8rem; color: var(--text-secondary, #64748b); font-weight: 600; }
.summary-pre { white-space: pre-wrap; font-family: inherit; font-size: 0.85rem; line-height: 1.7; color: var(--text, #1e293b); margin: 0; }

.exec-summary { display: flex; align-items: center; gap: 16px; padding: 18px 20px; border-radius: 10px; margin-bottom: 14px; color: #fff; }
.exec-summary.A { background: linear-gradient(135deg, #22c55e, #16a34a); }
.exec-summary.B { background: linear-gradient(135deg, #3b82f6, #2563eb); }
.exec-summary.C { background: linear-gradient(135deg, #f59e0b, #d97706); }
.exec-summary.D { background: linear-gradient(135deg, #ef4444, #dc2626); }
.exec-grade { font-size: 2rem; font-weight: 800; line-height: 1; opacity: 0.9; }
.exec-body { flex: 1; }
.exec-title { font-size: 1rem; font-weight: 600; margin-bottom: 4px; }
.exec-meta { font-size: 0.78rem; opacity: 0.85; margin-top: 2px; }

.inc-table { font-size: 0.82rem; }
.inc-row { display: flex; align-items: center; padding: 7px 0; border-bottom: 1px solid var(--border, rgba(0,0,0,0.06)); gap: 8px; }
.inc-row.inc-header { font-weight: 600; color: var(--text-secondary, #64748b); font-size: 0.75rem; text-transform: uppercase; border-bottom: 2px solid var(--border, rgba(0,0,0,0.1)); }
.inc-col-id { width: 50px; flex-shrink: 0; }
.inc-col-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.inc-col-sev { width: 56px; }
.inc-col-sta { width: 60px; }
.inc-col-time { width: 100px; text-align: right; color: var(--text-secondary, #64748b); }
.sev-badge { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; }
.sev-badge.critical { background: rgba(239,68,68,0.1); color: #ef4444; }
.sev-badge.warning { background: rgba(245,158,11,0.1); color: #f59e0b; }
.sev-badge.info { background: rgba(59,130,246,0.1); color: #3b82f6; }
.sta-badge { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; }
.sta-badge.open { background: rgba(239,68,68,0.1); color: #ef4444; }
.sta-badge.resolved { background: rgba(34,197,94,0.1); color: #22c55e; }
.sta-badge.closed { background: rgba(34,197,94,0.1); color: #22c55e; }
.sta-badge.done { background: rgba(34,197,94,0.1); color: #22c55e; }
.sta-badge.acknowledged { background: rgba(99,102,241,0.1); color: #6366f1; }
.sta-badge.analyzing { background: rgba(245,158,11,0.1); color: #f59e0b; }
</style>