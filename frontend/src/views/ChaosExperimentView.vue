<template>
  <div class="chaos-experiment">
    <!-- 汇总卡片 -->
    <el-row :gutter="16" class="summary-row">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value">{{ summary.total_experiments || 0 }}</div>
          <div class="stat-label">实验总数</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value" style="color: #67C23A">{{ summary.pass_rate || 0 }}%</div>
          <div class="stat-label">通过率</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value" style="color: #E6A23C">{{ summary.total_runs || 0 }}</div>
          <div class="stat-label">总运行次数</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value" style="color: #409EFF">{{ summary.active_schedules || 0 }}</div>
          <div class="stat-label">活跃定时计划</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 趋势图 -->
    <el-card class="chart-card">
      <template #header>
        <div class="card-header">
          <span class="title">近 30 天实验趋势</span>
        </div>
      </template>
      <div ref="trendChartRef" style="height: 280px"></div>
    </el-card>

    <!-- 实验列表 -->
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="title">混沌实验管理</span>
          <el-button type="primary" @click="showCreateDialog">+ 新建实验</el-button>
        </div>
      </template>

      <el-table :data="experimentList" stripe @row-click="openDetail">
        <el-table-column prop="name" label="实验名称" min-width="200" />
        <el-table-column prop="fault_type" label="故障类型" width="130">
          <template #default="{row}">
            <el-tag :type="getFaultTypeColor(row.fault_type)" effect="plain">{{ getFaultTypeLabel(row.fault_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="目标服务" width="150">
          <template #default="{row}">{{ getTargetService(row) }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{row}">
            <el-tag :type="getStatusType(row.status)" effect="dark">{{ getStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="result" label="结果" width="90">
          <template #default="{row}">
            <el-tag v-if="row.result === 'passed'" type="success" effect="dark">通过</el-tag>
            <el-tag v-else-if="row.result === 'failed'" type="danger" effect="dark">失败</el-tag>
            <el-tag v-else type="info" effect="plain">待执行</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" align="center">
          <template #default="{row}">
            <el-button size="small" type="success" @click.stop="startExperiment(row)" :disabled="row.status === 'running'">启动</el-button>
            <el-button size="small" type="warning" @click.stop="abortExperiment(row)" :disabled="row.status !== 'running'">终止</el-button>
            <el-button size="small" type="danger" @click.stop="deleteExperiment(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建实验弹窗 -->
    <el-dialog v-model="createDialogVisible" title="新建混沌实验" width="680px">
      <el-form :model="createForm" label-width="120px">
        <el-form-item label="实验名称" required>
          <el-input v-model="createForm.name" placeholder="请输入实验名称" />
        </el-form-item>
        <el-form-item label="实验描述">
          <el-input v-model="createForm.description" type="textarea" :rows="2" placeholder="实验目的和预期" />
        </el-form-item>
        <el-form-item label="故障类型" required>
          <el-select v-model="createForm.fault_type" placeholder="选择故障类型" style="width: 100%">
            <el-option label="Pod 故障 (pod-kill)" value="pod-kill" />
            <el-option label="CPU 压力 (cpu-stress)" value="cpu-stress" />
            <el-option label="内存压力 (mem-stress)" value="mem-stress" />
            <el-option label="网络延迟 (network-delay)" value="network-delay" />
            <el-option label="网络丢包 (network-loss)" value="network-loss" />
            <el-option label="磁盘填充 (disk-fill)" value="disk-fill" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标服务" required>
          <el-input v-model="createForm.target_service" placeholder="如 payment-service" />
        </el-form-item>
        <el-form-item label="目标命名空间">
          <el-input v-model="createForm.target_namespace" placeholder="default" />
        </el-form-item>
        <el-form-item label="持续时间(秒)">
          <el-input-number v-model="createForm.duration" :min="60" :max="3600" :step="60" />
        </el-form-item>
        <el-form-item label="故障强度">
          <el-input-number v-model="createForm.intensity" :min="1" :max="100" />
          <span class="form-tip">{{ getIntensityTip() }}</span>
        </el-form-item>
        <el-form-item label="稳态阈值(%)">
          <el-input-number v-model="createForm.threshold" :min="90" :max="100" :step="0.1" :precision="1" />
          <span class="form-tip">实验后可用性需高于此值才算通过</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="createExperiment">创建</el-button>
      </template>
    </el-dialog>

    <!-- 实验详情抽屉 -->
    <el-drawer v-model="detailDrawerVisible" title="实验详情" size="55%">
      <template v-if="detailData">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="实验名称">{{ detailData.name }}</el-descriptions-item>
          <el-descriptions-item label="故障类型">{{ getFaultTypeLabel(detailData.fault_type) }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="getStatusType(detailData.status)" effect="dark">{{ getStatusLabel(detailData.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="结果">
            <el-tag v-if="detailData.result === 'passed'" type="success" effect="dark">通过</el-tag>
            <el-tag v-else-if="detailData.result === 'failed'" type="danger" effect="dark">失败</el-tag>
            <el-tag v-else type="info" effect="plain">待执行</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ formatTime(detailData.started_at) }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ formatTime(detailData.finished_at) }}</el-descriptions-item>
          <el-descriptions-item label="描述" :span="2">{{ detailData.description || '无' }}</el-descriptions-item>
        </el-descriptions>

        <el-divider>运行历史</el-divider>
        <el-table :data="runHistory" stripe size="small">
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column label="状态" width="90">
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
          <el-table-column label="开始时间" min-width="160">
            <template #default="{row}">{{ formatTime(row.started_at) }}</template>
          </el-table-column>
          <el-table-column label="结论" min-width="160" prop="notes" />
        </el-table>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import axios from 'axios'

const API = '/api/chaos'

const summary = ref({})
const experimentList = ref([])
const trendChartRef = ref(null)
let trendChart = null

const createDialogVisible = ref(false)
const createForm = reactive({
  name: '', description: '', fault_type: 'pod-kill',
  target_service: '', target_namespace: 'default',
  duration: 300, intensity: 30, threshold: 99.0
})

const detailDrawerVisible = ref(false)
const detailData = ref(null)
const runHistory = ref([])

const getFaultTypeLabel = (t) => ({
  'pod-kill': 'Pod 故障', 'cpu-stress': 'CPU 压力', 'mem-stress': '内存压力',
  'network-delay': '网络延迟', 'network-loss': '网络丢包', 'disk-fill': '磁盘填充'
}[t] || t)

const getFaultTypeColor = (t) => ({
  'pod-kill': 'danger', 'cpu-stress': 'warning', 'mem-stress': 'warning',
  'network-delay': 'primary', 'network-loss': 'danger', 'disk-fill': 'info'
}[t] || 'info')

const getStatusType = (s) => ({
  pending: 'info', running: 'warning', completed: 'success', aborted: 'info', failed: 'danger'
}[s] || 'info')

const getStatusLabel = (s) => ({
  pending: '待执行', running: '运行中', completed: '已完成', aborted: '已终止', failed: '失败'
}[s] || s)

const getTargetService = (row) => {
  if (row.target_selector && typeof row.target_selector === 'object') return row.target_selector.service || '-'
  if (typeof row.target_selector === 'string') {
    try { return JSON.parse(row.target_selector).service || '-' } catch { return '-' }
  }
  return '-'
}

const getIntensityTip = () => {
  const ft = createForm.fault_type
  if (ft === 'pod-kill') return '杀掉 Pod 的百分比'
  if (ft === 'cpu-stress') return 'CPU 负载百分比'
  if (ft === 'mem-stress') return '填充内存 MB'
  if (ft === 'network-delay') return '延迟毫秒数'
  if (ft === 'network-loss') return '丢包百分比'
  if (ft === 'disk-fill') return '磁盘填充百分比'
  return ''
}

const formatTime = (t) => t ? new Date(t).toLocaleString('zh-CN') : '-'

async function loadSummary() {
  try { const { data } = await axios.get(`${API}/summary`); summary.value = data } catch {}
}

async function loadExperiments() {
  try { const { data } = await axios.get(`${API}/experiments`); experimentList.value = data } catch {}
}

async function loadTrend() {
  try {
    const { data } = await axios.get(`${API}/trend`)
    await nextTick()
    if (!trendChart && trendChartRef.value) trendChart = echarts.init(trendChartRef.value)
    if (trendChart) {
      trendChart.setOption({
        tooltip: { trigger: 'axis' },
        legend: { data: ['运行次数', '通过', '失败'], top: 0 },
        grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
        xAxis: { type: 'category', data: data.dates, axisLabel: { fontSize: 10, rotate: 45 } },
        yAxis: { type: 'value', minInterval: 1 },
        series: [
          { name: '运行次数', type: 'bar', data: data.runs, itemStyle: { color: '#409EFF' } },
          { name: '通过', type: 'line', data: data.passed, smooth: true, itemStyle: { color: '#67C23A' } },
          { name: '失败', type: 'line', data: data.failed, smooth: true, itemStyle: { color: '#F56C6C' } },
        ]
      })
    }
  } catch {}
}

function showCreateDialog() {
  Object.assign(createForm, { name: '', description: '', fault_type: 'pod-kill', target_service: '', target_namespace: 'default', duration: 300, intensity: 30, threshold: 99.0 })
  createDialogVisible.value = true
}

async function createExperiment() {
  if (!createForm.name || !createForm.target_service) { ElMessage.warning('请填写实验名称和目标服务'); return }
  const params = { duration: createForm.duration }
  if (['pod-kill'].includes(createForm.fault_type)) params.kill_percentage = createForm.intensity
  else if (['cpu-stress'].includes(createForm.fault_type)) params.load_percentage = createForm.intensity
  else if (['mem-stress'].includes(createForm.fault_type)) params.fill_mb = createForm.intensity
  else if (['network-delay'].includes(createForm.fault_type)) { params.latency_ms = createForm.intensity; params.percentage = 50 }
  else if (['network-loss'].includes(createForm.fault_type)) params.loss_percent = createForm.intensity
  else if (['disk-fill'].includes(createForm.fault_type)) params.fill_percent = createForm.intensity

  try {
    await axios.post(`${API}/experiments`, {
      name: createForm.name, description: createForm.description,
      target_type: createForm.fault_type.startsWith('network') ? 'network' : 'pod',
      target_selector: { service: createForm.target_service, namespace: createForm.target_namespace },
      fault_type: createForm.fault_type, fault_params: params,
      steady_state: { metric: 'availability', threshold: createForm.threshold }
    })
    ElMessage.success('实验创建成功')
    createDialogVisible.value = false
    loadExperiments(); loadSummary()
  } catch (e) { ElMessage.error('创建失败: ' + (e.response?.data?.detail || e.message)) }
}

async function startExperiment(row) {
  try {
    const { data } = await axios.post(`${API}/experiments/${row.id}/start`)
    ElMessage.success(`实验完成，稳态${data.steady_state_passed ? '通过' : '未通过'}`)
    loadExperiments(); loadSummary(); loadTrend()
  } catch (e) { ElMessage.error('启动失败: ' + (e.response?.data?.detail || e.message)) }
}

async function abortExperiment(row) {
  try {
    await axios.post(`${API}/experiments/${row.id}/abort`)
    ElMessage.success('实验已终止')
    loadExperiments(); loadSummary()
  } catch (e) { ElMessage.error('终止失败: ' + (e.response?.data?.detail || e.message)) }
}

async function deleteExperiment(row) {
  try {
    await ElMessageBox.confirm(`确认删除实验"${row.name}"？`, '提示', { type: 'warning' })
    await axios.delete(`${API}/experiments/${row.id}`)
    ElMessage.success('已删除')
    loadExperiments(); loadSummary()
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败') }
}

async function openDetail(row) {
  detailData.value = row
  detailDrawerVisible.value = true
  try { const { data } = await axios.get(`${API}/experiments/${row.id}/runs`); runHistory.value = data } catch {}
}

onMounted(() => { loadSummary(); loadExperiments(); loadTrend() })
</script>

<style scoped>
.chaos-experiment { padding: 0; }
.summary-row { margin-bottom: 16px; }
.stat-card { text-align: center; padding: 10px 0; }
.stat-value { font-size: 28px; font-weight: 700; color: #303133; }
.stat-label { font-size: 13px; color: #909399; margin-top: 4px; }
.chart-card { margin-bottom: 16px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.title { font-size: 16px; font-weight: 600; }
.form-tip { margin-left: 10px; font-size: 12px; color: #909399; }
</style>
