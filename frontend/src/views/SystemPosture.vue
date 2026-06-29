<template>
  <div class="workbench-page-shell">
    <div class="section-toolbar">
      <div class="toolbar-head">
        <span class="toolbar-title">系统态势</span>
        <span class="toolbar-desc">SLA 健康度 · 近 {{ days }} 天</span>
      </div>
      <div class="workbench-card-actions">
        <el-select v-model="days" size="small" style="width:110px" @change="load">
          <el-option :value="7" label="近 7 天" />
          <el-option :value="14" label="近 14 天" />
          <el-option :value="30" label="近 30 天" />
          <el-option :value="60" label="近 60 天" />
        </el-select>
        <el-button size="small" type="primary" @click="refresh" :loading="saving">刷新</el-button>
      </div>
    </div>

    <div class="sla-summary">
      <div class="summary-item healthy"><div class="summary-num">{{ overviewData.summary?.healthy || 0 }}</div><div class="summary-label">健康</div></div>
      <div class="summary-item warning"><div class="summary-num">{{ overviewData.summary?.warning || 0 }}</div><div class="summary-label">亚健康</div></div>
      <div class="summary-item danger"><div class="summary-num">{{ overviewData.summary?.critical || 0 }}</div><div class="summary-label">故障</div></div>
      <div class="summary-item info"><div class="summary-num">{{ overviewData.summary?.unknown || 0 }}</div><div class="summary-label">无数据</div></div>
    </div>

    <div class="workbench-card heatmap-card" v-if="!loading && heatmapData.length">
      <div class="heatmap-header">
        <div class="sys-name-col">系统</div>
        <div v-for="d in dayLabels" :key="d" class="day-header" :title="d">{{ d.slice(5) }}</div>
        <div class="avg-col">均分</div>
      </div>
      <div v-for="row in heatmapData" :key="row.system_key" class="heatmap-row">
        <div class="sys-name-col">
          <div class="sys-name-text">{{ row.system_name || row.system_key }}</div>
        </div>
        <div
          v-for="d in dayLabels"
          :key="d"
          class="day-cell"
          :class="getCellCls(row, d)"
          :title="`${d} | SLA: ${getCellSla(row, d)} | 告警: ${getCellAlerts(row, d)} | 故障: ${getCellIncidents(row, d)}`"
        />
        <div class="avg-col">
          <div class="avg-score" :class="avgCls(row.avg_score)">{{ row.avg_score }}</div>
        </div>
      </div>
      <div class="cal-legend">
        <span class="lbl">健康度</span>
        <span class="leg-item heal">≥99%</span>
        <span class="leg-item warn">95-99%</span>
        <span class="leg-item crit">&lt;95%</span>
        <span class="leg-item none">无数据</span>
      </div>
    </div>

    <div v-if="loading" class="loading-tip">
      <el-icon class="is-loading" :size="18"><Loading /></el-icon>
      <span>正在加载数据...</span>
    </div>

    <div v-else-if="!heatmapData.length" class="empty-tip">暂无数据，请先点击「刷新」</div>

    <div class="workbench-card" style="margin-top:12px" v-if="!loading && overviewData.systems?.length">
      <el-table :data="overviewData.systems" style="width:100%" size="small" :max-height="260">
        <el-table-column prop="system_name" label="系统" min-width="130" />
        <el-table-column prop="status" label="状态" width="80">
          <template #default="{ row }"><el-tag :type="tagType(row.status)" size="small">{{ statusTxt(row.status) }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="sla_value" label="SLA" width="90" sortable>
          <template #default="{ row }"><span :class="slaCls(row.sla_value)">{{ row.sla_value?.toFixed(2) }}%</span></template>
        </el-table-column>
        <el-table-column prop="health_score" label="健康分" width="120" sortable>
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px">
              <el-progress :percentage="row.health_score||0" :color="progColor(row.health_score)" :show-text="false" style="width:60px" />
              <span style="font-size:12px">{{ row.health_score || 0 }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="alerts_count" label="告警" width="70" sortable />
        <el-table-column prop="incidents_count" label="故障" width="70" sortable />
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import request from '@/api/request'

const days = ref(30)
const saving = ref(false)
const loading = ref(true)
const overviewData = ref({ systems: [], summary: {} })
const heatmapData = ref([])

const dayLabels = computed(() => {
  const labels = []
  for (let i = days.value - 1; i >= 0; i--) {
    const d = new Date()
    d.setDate(d.getDate() - i)
    labels.push(d.toISOString().slice(0, 10))
  }
  return labels
})

function tagType(s) {
  return { healthy: 'success', warning: 'warning', critical: 'danger', unknown: 'info' }[s] || 'info'
}
function statusTxt(s) {
  return { healthy: '健康', warning: '亚健康', critical: '故障', unknown: '未知' }[s] || s
}
function slaCls(v) {
  if (!v) return ''
  return v >= 99 ? 'sla-h' : v >= 95 ? 'sla-w' : 'sla-d'
}
function progColor(v) {
  if (v >= 99) return '#10b981'
  if (v >= 95) return '#f59e0b'
  return '#ef4444'
}
function avgCls(v) {
  if (v >= 99) return 'avg-h'
  if (v >= 95) return 'avg-w'
  return 'avg-c'
}
function getCellSla(row, day) {
  const cell = (row.cells || []).find(c => c.day === day)
  if (!cell || cell.sla_value === null) return 'N/A'
  return cell.sla_value.toFixed(2) + '%'
}
function getCellAlerts(row, day) {
  const cell = (row.cells || []).find(c => c.day === day)
  return cell?.alerts ?? '-'
}
function getCellIncidents(row, day) {
  const cell = (row.cells || []).find(c => c.day === day)
  return cell?.incidents ?? '-'
}
function getCellCls(row, day) {
  const cell = (row.cells || []).find(c => c.day === day)
  if (!cell || cell.sla_value === null) return 'cell-none'
  if (cell.sla_value >= 99) return 'cell-h'
  if (cell.sla_value >= 95) return 'cell-w'
  return 'cell-c'
}
function slaCellAvg(cells) {
  const vals = (cells || []).filter(c => c.sla_value !== null).map(c => c.sla_value)
  if (!vals.length) return 0
  return Math.round(vals.reduce((a, b) => a + b, 0) / vals.length)
}

async function load() {
  loading.value = true
  try {
    const [ov, hm] = await Promise.all([
      request.get(`/api/system/posture?days=${days.value}`),
      request.get(`/api/system/posture/heatmap?days=${days.value}`),
    ])
    overviewData.value = ov
    heatmapData.value = (Array.isArray(hm) ? hm : []).map(row => ({
      ...row,
      avg_score: slaCellAvg(row.cells || []),
    }))
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function refresh() {
  saving.value = true
  try {
    await request.post(`/api/system/posture/refresh?days=${days.value}`)
    await load()
  } catch (e) {
    console.error(e)
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.sla-summary { display: flex; gap: 10px; margin-bottom: 10px; }
.summary-item {
  flex: 1; background: var(--card-bg); border-radius: 10px;
  padding: 12px 10px; border: 1px solid rgba(148,163,184,0.12);
  display: flex; flex-direction: column; align-items: center;
}
.summary-num { font-size: 22px; font-weight: 800; }
.summary-label { font-size: 10px; color: var(--text-secondary); margin-top: 2px; }
.summary-item.healthy .summary-num { color: #10b981; }
.summary-item.warning .summary-num { color: #f59e0b; }
.summary-item.danger .summary-num { color: #ef4444; }
.summary-item.info .summary-num { color: var(--text-muted); }

.heatmap-card { padding: 14px 16px; }
.heatmap-header, .heatmap-row {
  display: grid;
  align-items: center;
  min-height: 30px;
}
.heatmap-header {
  grid-template-columns: 140px repeat(30, 1fr) 48px;
  border-bottom: 1px solid rgba(148,163,184,0.15);
  margin-bottom: 2px;
}
.heatmap-row {
  grid-template-columns: 140px repeat(30, 1fr) 48px;
  border-bottom: 1px solid rgba(148,163,184,0.06);
}
.heatmap-row:last-of-type { border-bottom: none; }

.sys-name-col { padding: 2px 8px 2px 0; }
.sys-name-text { font-size: 12px; font-weight: 600; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.day-header {
  text-align: center; font-size: 9px; color: var(--text-muted);
  overflow: hidden;
}
.day-cell {
  height: 22px; border-radius: 3px; cursor: default; margin: 0 1px;
  transition: transform 0.1s, box-shadow 0.1s;
}
.day-cell:hover {
  transform: scaleY(1.2);
  box-shadow: 0 2px 6px rgba(0,0,0,0.2);
  z-index: 1; position: relative;
}
.cell-h { background: #10b981; }
.cell-w { background: #f59e0b; }
.cell-c { background: #ef4444; }
.cell-none { background: #f1f5f9; }

.avg-col { text-align: center; }
.avg-score { font-size: 12px; font-weight: 800; }
.avg-h { color: #10b981; }
.avg-w { color: #f59e0b; }
.avg-c { color: #ef4444; }

.cal-legend { display: flex; align-items: center; gap: 8px; margin-top: 10px; font-size: 11px; }
.lbl { color: var(--text-secondary); margin-right: 4px; }
.leg-item { padding: 2px 8px; border-radius: 4px; color: #fff; font-weight: 600; font-size: 10px; }
.leg-item.heal { background: #10b981; }
.leg-item.warn { background: #f59e0b; }
.leg-item.crit { background: #ef4444; }
.leg-item.none { background: #f1f5f9; color: var(--text-muted); }

.empty-tip { text-align: center; padding: 32px; color: var(--text-muted); font-size: 13px; }
.loading-tip { text-align: center; padding: 32px; color: var(--primary); font-size: 13px; display: flex; align-items: center; justify-content: center; gap: 8px; }
.sla-h { color: #10b981; font-weight: 700; }
.sla-w { color: #f59e0b; font-weight: 700; }
.sla-d { color: #ef4444; font-weight: 700; }
</style>
