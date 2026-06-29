<template>
  <div class="chaos-report">
    <!-- 顶部统计 -->
    <el-row :gutter="16" class="summary-row">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value">{{ summary.total_runs || 0 }}</div>
          <div class="stat-label">总运行次数</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value" style="color: #67C23A">{{ summary.passed || 0 }}</div>
          <div class="stat-label">通过</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value" style="color: #F56C6C">{{ summary.failed || 0 }}</div>
          <div class="stat-label">失败</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value" style="color: #E6A23C">{{ summary.total_alerts || 0 }}</div>
          <div class="stat-label">触发告警总数</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <!-- 韧性雷达图 -->
      <el-col :span="12">
        <el-card>
          <template #header><div class="card-header"><span class="title">韧性维度雷达图</span></div></template>
          <div ref="radarChartRef" style="height: 320px"></div>
        </el-card>
      </el-col>

      <!-- 故障类型分布 -->
      <el-col :span="12">
        <el-card>
          <template #header><div class="card-header"><span class="title">故障类型分布</span></div></template>
          <div ref="pieChartRef" style="height: 320px"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 实验对比表格 -->
    <el-card style="margin-top: 16px">
      <template #header><div class="card-header"><span class="title">实验运行记录</span></div></template>
      <el-table :data="allRuns" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column label="实验名称" min-width="200">
          <template #default="{row}">{{ getExpName(row.experiment_id) }}</template>
        </el-table-column>
        <el-table-column label="稳态验证" width="100">
          <template #default="{row}">
            <el-tag :type="row.steady_state_passed ? 'success' : 'danger'" effect="dark" size="small">
              {{ row.steady_state_passed ? '通过' : '未通过' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="告警数" width="80" prop="alerts_triggered" />
        <el-table-column label="预算消耗" width="100">
          <template #default="{row}">{{ row.error_budget_impact }}%</template>
        </el-table-column>
        <el-table-column label="耗时" width="80">
          <template #default="{row}">{{ row.duration_seconds }}s</template>
        </el-table-column>
        <el-table-column label="实验前可用性" width="120">
          <template #default="{row}">{{ row.steady_state_before?.availability || '-' }}%</template>
        </el-table-column>
        <el-table-column label="实验后可用性" width="120">
          <template #default="{row}">
            <span :style="{color: (row.steady_state_after?.availability || 100) < 99 ? '#F56C6C' : '#67C23A'}">
              {{ row.steady_state_after?.availability || '-' }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column label="开始时间" min-width="160">
          <template #default="{row}">{{ formatTime(row.started_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 失败分析 -->
    <el-card style="margin-top: 16px">
      <template #header><div class="card-header"><span class="title">❌ 失败实验分析</span></div></template>
      <el-table :data="failedRuns" stripe>
        <el-table-column label="实验名称" min-width="200">
          <template #default="{row}">{{ getExpName(row.experiment_id) }}</template>
        </el-table-column>
        <el-table-column label="实验后可用性" width="130">
          <template #default="{row}">{{ row.steady_state_after?.availability || '-' }}%</template>
        </el-table-column>
        <el-table-column label="告警数" width="80" prop="alerts_triggered" />
        <el-table-column label="预算消耗" width="100">
          <template #default="{row}">{{ row.error_budget_impact }}%</template>
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
    failedRuns.value = all.filter(r => !r.steady_state_passed)
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
        radar: {
          indicator: data.dimensions.map(d => ({ name: d, max: 100 })),
          radius: '65%',
        },
        series: [{
          type: 'radar',
          data: [{ value: data.values, name: '韧性评分' }],
          areaStyle: { color: 'rgba(64, 158, 255, 0.3)' },
          lineStyle: { color: '#409EFF' },
          itemStyle: { color: '#409EFF' },
        }]
      })
    }
  } catch {}
}

async function loadPieChart() {
  try {
    const { data } = await axios.get(`${API}/summary`)
    const faultDist = data.fault_distribution || {}
    const labels = { 'pod-kill': 'Pod故障', 'cpu-stress': 'CPU压力', 'mem-stress': '内存压力', 'network-delay': '网络延迟', 'network-loss': '网络丢包', 'disk-fill': '磁盘填充' }
    const pieData = Object.entries(faultDist).map(([k, v]) => ({ name: labels[k] || k, value: v }))
    await nextTick()
    if (!pieChart && pieChartRef.value) pieChart = echarts.init(pieChartRef.value)
    if (pieChart) {
      pieChart.setOption({
        tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
        legend: { bottom: 0, type: 'scroll' },
        series: [{
          type: 'pie', radius: ['40%', '70%'], center: ['50%', '45%'],
          data: pieData,
          itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
          label: { show: true, formatter: '{b}\n{d}%' },
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
.stat-card { text-align: center; padding: 10px 0; }
.stat-value { font-size: 28px; font-weight: 700; color: #303133; }
.stat-label { font-size: 13px; color: #909399; margin-top: 4px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.title { font-size: 16px; font-weight: 600; }
</style>
