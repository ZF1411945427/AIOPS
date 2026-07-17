<template>
  <div class="chaos-report">
    <!-- 顶部统计 -->
    <el-row :gutter="16" class="summary-row">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card stat-total">
          <div class="stat-icon"><el-icon :size="32"><DataLine /></el-icon></div>
          <div class="stat-body">
            <div class="stat-value">{{ summary.total_runs || 0 }}</div>
            <div class="stat-label">总运行次数</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card stat-pass">
          <div class="stat-icon"><el-icon :size="32"><CircleCheck /></el-icon></div>
          <div class="stat-body">
            <div class="stat-value">{{ summary.passed || 0 }}</div>
            <div class="stat-label">通过</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card stat-fail">
          <div class="stat-icon"><el-icon :size="32"><CircleClose /></el-icon></div>
          <div class="stat-body">
            <div class="stat-value">{{ summary.failed || 0 }}</div>
            <div class="stat-label">失败</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card stat-alert">
          <div class="stat-icon"><el-icon :size="32"><Bell /></el-icon></div>
          <div class="stat-body">
            <div class="stat-value">{{ summary.total_alerts || 0 }}</div>
            <div class="stat-label">触发告警总数</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <!-- 韧性雷达图 -->
      <el-col :span="12">
        <el-card class="chart-card radar-card">
          <template #header><div class="card-header"><span class="title">韧性维度雷达图</span><span class="card-sub">各故障类型韧性评分</span></div></template>
          <div ref="radarChartRef" style="height: 340px"></div>
        </el-card>
      </el-col>

      <!-- 故障类型分布 -->
      <el-col :span="12">
        <el-card class="chart-card pie-card">
          <template #header><div class="card-header"><span class="title">故障类型分布</span><span class="card-sub">实验运行按故障类型统计</span></div></template>
          <div ref="pieChartRef" style="height: 340px"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 实验对比表格 -->
    <el-card style="margin-top: 16px" class="table-card">
      <template #header><div class="card-header"><span class="title">实验运行记录</span><span class="card-sub">全部实验的稳态验证结果</span></div></template>
      <el-table :data="allRuns" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column label="实验名称" min-width="200">
          <template #default="{row}">{{ getExpName(row.experiment_id) }}</template>
        </el-table-column>
        <el-table-column label="稳态验证" width="100">
          <template #default="{row}">
            <el-tag :type="row.is_steady_state_passed ? 'success' : 'danger'" effect="dark" size="small">
              {{ row.is_steady_state_passed ? '通过' : '未通过' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="告警数" width="80" prop="alerts_triggered" />
        <el-table-column label="预算消耗" width="100">
          <template #default="{row}">
            <span :class="{ 'budget-high': row.error_budget_impact > 50 }">{{ row.error_budget_impact }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="80">
          <template #default="{row}">{{ row.duration_seconds }}s</template>
        </el-table-column>
        <el-table-column label="实验前可用性" width="130">
          <template #default="{row}">{{ row.steady_state_before?.availability || '-' }}%</template>
        </el-table-column>
        <el-table-column label="实验后可用性" width="140">
          <template #default="{row}">
            <div class="avail-cell">
              <div class="avail-bar-bg">
                <div class="avail-bar" :style="{ width: (row.steady_state_after?.availability || 0) + '%', background: availColor(row.steady_state_after?.availability) }"></div>
              </div>
              <span :style="{color: availColor(row.steady_state_after?.availability)}">{{ row.steady_state_after?.availability || '-' }}%</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="开始时间" min-width="160">
          <template #default="{row}">{{ formatTime(row.started_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 失败分析 -->
    <el-card style="margin-top: 16px" class="table-card fail-card">
      <template #header><div class="card-header"><span class="title">❌ 失败实验分析</span><span class="card-sub">稳态未通过的实验明细</span></div></template>
      <el-table :data="failedRuns" stripe>
        <el-table-column label="实验名称" min-width="200">
          <template #default="{row}">{{ getExpName(row.experiment_id) }}</template>
        </el-table-column>
        <el-table-column label="实验后可用性" width="140">
          <template #default="{row}">
            <div class="avail-cell">
              <div class="avail-bar-bg">
                <div class="avail-bar" :style="{ width: (row.steady_state_after?.availability || 0) + '%', background: availColor(row.steady_state_after?.availability) }"></div>
              </div>
              <span :style="{color: availColor(row.steady_state_after?.availability)}">{{ row.steady_state_after?.availability || '-' }}%</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="告警数" width="80" prop="alerts_triggered" />
        <el-table-column label="预算消耗" width="100">
          <template #default="{row}">
            <span :class="{ 'budget-high': row.error_budget_impact > 50 }">{{ row.error_budget_impact }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="结论" min-width="200" prop="notes" />
      </el-table>
      <el-empty v-if="failedRuns.length === 0" description="没有失败的实验，系统韧性良好 🎉" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { DataLine, CircleCheck, CircleClose, Bell } from '@element-plus/icons-vue'
import axios from 'axios'

const API = '/api/chaos'
const summary = ref({})
const allRuns = ref([])
const experimentMap = ref({})
const failedRuns = ref([])

const radarChartRef = ref(null)
const pieChartRef = ref(null)
let radarChart = null, pieChart = null

const formatTime = (t) => t ? new Date(t).toLocaleString('zh-CN') : '-'

const getExpName = (id) => experimentMap.value[id] || `实验#${id}`

const availColor = (v) => {
  if (v == null) return '#909399'
  if (v >= 99) return '#67C23A'
  if (v >= 90) return '#E6A23C'
  return '#F56C6C'
}

const RADAR_COLORS = ['#409EFF', '#67C23A', '#E6A23C', '#F56C6C', '#9B59B6', '#00C9A7']
const PIE_COLORS = ['#5470c6','#91cc75','#fac858','#ee6666','#73c0de','#3ba272','#fc8452','#9a60b4','#ea7ccc','#5ab1db','#d4a5e5','#f7b733','#fc4a1a','#2abb67']

async function loadSummary() {
  try {
    const { data } = await axios.get(`${API}/summary`)
    summary.value = data
  } catch {}
}

async function loadExperiments() {
  try {
    const { data } = await axios.get(`${API}/experiments`)
    data.forEach(e => { experimentMap.value[e.id] = e.name })
  } catch {}
}

async function loadAllRuns() {
  try {
    const { data: exps } = await axios.get(`${API}/experiments`)
    const all = []
    for (const exp of exps) {
      try {
        const { data: runs } = await axios.get(`${API}/experiments/${exp.id}/runs`)
        all.push(...runs)
      } catch {}
    }
    allRuns.value = all.sort((a, b) => b.id - a.id)
    failedRuns.value = all.filter(r => !r.is_steady_state_passed)
  } catch {}
}

async function loadRadarChart() {
  try {
    const { data } = await axios.get(`${API}/resilience-radar`)
    await nextTick()
    if (!radarChart && radarChartRef.value) radarChart = echarts.init(radarChartRef.value)
    if (radarChart) {
      radarChart.setOption({
        tooltip: {},
        legend: { bottom: 0, data: ['韧性评分'] },
        radar: {
          indicator: data.dimensions.map(d => ({ name: d, max: 100 })),
          radius: '65%',
          axisName: { color: '#606266', fontSize: 11 },
          splitLine: { lineStyle: { color: 'rgba(64,158,255,0.2)' } },
          splitArea: { areaStyle: { color: ['rgba(64,158,255,0.05)', 'rgba(64,158,255,0.1)'] } },
          axisLine: { lineStyle: { color: 'rgba(64,158,255,0.3)' } },
        },
        series: [{
          type: 'radar',
          data: [{
            value: data.values,
            name: '韧性评分',
            areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(64,158,255,0.5)' },
              { offset: 1, color: 'rgba(103,194,58,0.3)' },
            ]) },
            lineStyle: { color: '#409EFF', width: 2 },
            itemStyle: { color: '#409EFF' },
            label: { show: true, formatter: (p) => p.value, fontSize: 10, color: '#409EFF' },
          }],
        }]
      })
    }
  } catch (e) { console.error('[ChaosReport] 韧性雷达加载失败:', e.response?.status, e.response?.data?.detail || e.message) }
}

async function loadPieChart() {
  try {
    const { data } = await axios.get(`${API}/summary`)
    const faultDist = data.fault_distribution || {}
    const labels = {
      'cpu-stress': 'CPU压力', 'mem-stress': '内存压力', 'disk-fill': '磁盘填充',
      'disk-io-stress': '磁盘IO', 'process-kill': '进程崩溃',
      'network-delay': '网络延迟', 'network-loss': '网络丢包',
      'network-bandwidth': '带宽限制', 'network-partition': '网络分区',
      'container-stop': '容器停止', 'container-restart': '容器重启',
      'pod-kill': 'Pod故障', 'deployment-restart': 'Deployment重启', 'dns-fault': 'DNS故障'
    }
    const pieData = Object.entries(faultDist).map(([k, v]) => ({ name: labels[k] || k, value: v }))
    await nextTick()
    if (!pieChart && pieChartRef.value) pieChart = echarts.init(pieChartRef.value)
    if (pieChart) {
      pieChart.setOption({
        tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
        legend: { bottom: 0, type: 'scroll' },
        color: PIE_COLORS,
        series: [{
          type: 'pie', radius: ['40%', '70%'], center: ['50%', '45%'],
          data: pieData,
          itemStyle: { borderRadius: 8, borderColor: '#fff', borderWidth: 2 },
          label: { show: true, formatter: '{b}\n{d}%', color: '#606266' },
          emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.2)' } },
        }]
      })
    }
  } catch {}
}

onMounted(() => {
  loadSummary()
  loadExperiments().then(() => loadAllRuns())
  loadRadarChart()
  loadPieChart()
})
</script>

<style scoped>
.chaos-report { padding: 0; }
.summary-row { margin-bottom: 16px; }

.stat-card {
  text-align: left;
  padding: 16px 20px;
  border-radius: 10px;
  border: none;
  display: flex;
  align-items: center;
  gap: 16px;
  color: #fff;
  overflow: hidden;
  position: relative;
}
.stat-card :deep(.el-card__body) { padding: 0; width: 100%; display: flex; align-items: center; gap: 16px; }
.stat-total { background: linear-gradient(135deg, #409EFF 0%, #1a78d4 100%); }
.stat-pass { background: linear-gradient(135deg, #67C23A 0%, #4e9e2a 100%); }
.stat-fail { background: linear-gradient(135deg, #F56C6C 0%, #d94a4a 100%); }
.stat-alert { background: linear-gradient(135deg, #E6A23C 0%, #c8842a 100%); }
.stat-icon { opacity: 0.9; }
.stat-body { flex: 1; }
.stat-value { font-size: 32px; font-weight: 700; color: #fff; line-height: 1.1; }
.stat-label { font-size: 13px; color: rgba(255,255,255,0.85); margin-top: 4px; }

.chart-card { border-radius: 10px; overflow: hidden; }
.chart-card :deep(.el-card__header) { padding: 14px 18px; }
.radar-card :deep(.el-card__header) { background: linear-gradient(90deg, #e8f1ff 0%, #f5f9ff 100%); border-left: 4px solid #409EFF; }
.pie-card :deep(.el-card__header) { background: linear-gradient(90deg, #fff5e6 0%, #fffbf5 100%); border-left: 4px solid #E6A23C; }

.card-header { display: flex; justify-content: space-between; align-items: center; }
.title { font-size: 16px; font-weight: 600; color: #303133; }
.card-sub { font-size: 12px; color: #909399; }

.table-card { border-radius: 10px; }
.table-card :deep(.el-card__header) { background: linear-gradient(90deg, #f0f9ff 0%, #f7fbff 100%); border-left: 4px solid #409EFF; }
.fail-card :deep(.el-card__header) { background: linear-gradient(90deg, #fef0f0 0%, #fff7f7 100%); border-left: 4px solid #F56C6C; }

.avail-cell { display: flex; align-items: center; gap: 6px; }
.avail-bar-bg { width: 60px; height: 8px; background: #f0f0f0; border-radius: 4px; overflow: hidden; }
.avail-bar { height: 100%; border-radius: 4px; transition: width 0.3s; }
.budget-high { color: #F56C6C; font-weight: 600; }
</style>
