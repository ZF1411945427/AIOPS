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
        <el-table-column label="目标层级" width="110">
          <template #default="{row}">
            <el-tag :type="getLayerTagType(row.target_layer || (row.fault_type === 'pod-kill' ? 'k8s' : 'host'))" effect="plain" size="small">
              {{ getLayerLabel(row.target_layer || (row.fault_type === 'pod-kill' ? 'k8s' : 'host')) }}
            </el-tag>
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
        <el-form-item label="目标层级">
          <el-tag :type="getLayerTagType(createForm.target_layer)" effect="dark">{{ getLayerLabel(createForm.target_layer) }}</el-tag>
          <span class="form-tip">来自场景库，决定故障注入手段</span>
        </el-form-item>
        <el-form-item label="故障类型" required>
          <el-select v-model="createForm.fault_type" placeholder="选择故障类型" style="width: 100%">
            <el-option label="CPU 压力 (cpu-stress)" value="cpu-stress" />
            <el-option label="内存压力 (mem-stress)" value="mem-stress" />
            <el-option label="磁盘填充 (disk-fill)" value="disk-fill" />
            <el-option label="磁盘 IO 压力 (disk-io-stress)" value="disk-io-stress" />
            <el-option label="进程崩溃 (process-kill)" value="process-kill" />
            <el-option label="网络延迟 (network-delay)" value="network-delay" />
            <el-option label="网络丢包 (network-loss)" value="network-loss" />
            <el-option label="带宽限制 (network-bandwidth)" value="network-bandwidth" />
            <el-option label="网络分区 (network-partition)" value="network-partition" />
            <el-option label="容器停止 (container-stop)" value="container-stop" />
            <el-option label="容器重启 (container-restart)" value="container-restart" />
            <el-option label="Pod 故障 (pod-kill)" value="pod-kill" />
            <el-option label="Deployment 重启 (deployment-restart)" value="deployment-restart" />
            <el-option label="DNS 故障 (dns-fault)" value="dns-fault" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标资产" required>
          <el-select v-model="createForm.asset_id" placeholder="选择可 SSH 的真实主机" style="width: 100%" filterable>
            <el-option v-for="a in targetAssets" :key="a.id" :label="`${a.name} (${a.ip})`" :value="a.id" />
          </el-select>
          <div class="form-tip" v-if="targetAssets.length === 0" style="color:#F56C6C;margin-top:4px;">⚠️ 无可用目标资产，请先在资产管理中添加 online 且有 SSH 凭据的主机</div>
        </el-form-item>
        <el-form-item label="目标命名空间" v-if="createForm.target_layer === 'k8s'">
          <el-input v-model="createForm.target_namespace" placeholder="default" />
          <span class="form-tip">K8s Pod 所在命名空间</span>
        </el-form-item>
        <el-form-item label="持续时间(秒)">
          <el-input-number v-model="createForm.duration" :min="60" :max="3600" :step="60" />
        </el-form-item>
        <el-form-item v-if="intensityConfig" :label="intensityConfig.label + ' (' + intensityConfig.unit + ')'">
          <el-input-number v-model="createForm.intensity" :min="intensityConfig.min" :max="intensityConfig.max" :step="intensityConfig.step" />
        </el-form-item>
        <el-form-item label="稳态阈值(%)">
          <el-input-number v-model="createForm.threshold" :min="90" :max="100" :step="0.1" :precision="1" />
          <span class="form-tip">实验后可用性需高于此值才算通过</span>
        </el-form-item>
        <el-form-item label="命令预览">
          <el-button size="small" type="primary" plain @click="previewCommand" :loading="previewLoading">预览将执行的 SSH 命令</el-button>
          <div v-if="previewResult" class="cmd-preview-block">
            <div v-if="previewResult.note" class="cmd-preview-note">{{ previewResult.note }}</div>
            <template v-else>
              <div class="cmd-preview-label">注入命令:</div>
              <pre class="cmd-pre">{{ previewResult.inject_cmd }}</pre>
              <div class="cmd-preview-label">清理命令:</div>
              <pre class="cmd-pre">{{ previewResult.cleanup_cmd }}</pre>
            </template>
          </div>
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
          <el-table-column label="结论" min-width="200" show-overflow-tooltip>
            <template #default="{row}">
              <div class="run-notes">{{ row.notes }}</div>
            </template>
          </el-table-column>
        </el-table>

        <el-divider v-if="latestRunNotes">执行的 SSH 命令</el-divider>
        <div v-if="latestRunNotes" class="cmd-block">
          <div class="cmd-block-header">
            <span>实际在目标主机执行的命令</span>
            <el-button size="small" type="primary" plain @click="copyCommand">复制命令</el-button>
          </div>
          <pre class="cmd-pre">{{ extractCommands(latestRunNotes) }}</pre>
          <div class="cmd-tip">💡 也可登录目标主机终端执行 <code>ps -ef | grep chaos</code> 查看实时进程</div>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick, watch, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import axios from 'axios'

const API = '/api/chaos'

const summary = ref({})
const experimentList = ref([])
const targetAssets = ref([])
const trendChartRef = ref(null)
let trendChart = null

const createDialogVisible = ref(false)
const createForm = reactive({
  name: '', description: '', fault_type: 'pod-kill',
  target_layer: 'host',
  asset_id: null, target_namespace: 'default',
  duration: 300, intensity: 30, threshold: 99.0
})
const previewLoading = ref(false)
const previewResult = ref(null)

const detailDrawerVisible = ref(false)
const detailData = ref(null)
const runHistory = ref([])

const latestRunNotes = computed(() => {
  if (!runHistory.value || runHistory.value.length === 0) return ''
  const latest = runHistory.value[0]
  return latest.notes || ''
})

const extractCommands = (notes) => {
  if (!notes) return ''
  const idx = notes.indexOf('【执行的 SSH 命令】')
  if (idx === -1) return ''
  return notes.substring(idx).trim()
}

const copyCommand = () => {
  const cmds = extractCommands(latestRunNotes.value)
  if (!cmds) return
  navigator.clipboard.writeText(cmds).then(() => {
    ElMessage.success('命令已复制到剪贴板')
  }).catch(() => {
    ElMessage.warning('复制失败，请手动选择复制')
  })
}

const getFaultTypeLabel = (t) => ({
  'cpu-stress': 'CPU 压力', 'mem-stress': '内存压力', 'disk-fill': '磁盘填充',
  'disk-io-stress': '磁盘 IO', 'process-kill': '进程崩溃',
  'network-delay': '网络延迟', 'network-loss': '网络丢包',
  'network-bandwidth': '带宽限制', 'network-partition': '网络分区',
  'container-stop': '容器停止', 'container-restart': '容器重启',
  'pod-kill': 'Pod 故障', 'deployment-restart': 'Deployment 重启', 'dns-fault': 'DNS 故障'
}[t] || t)

const LAYER_LABELS = { host: '主机/VM', container: '容器', k8s: 'K8s 编排', network: '网络' }
const getLayerLabel = (l) => LAYER_LABELS[l] || l
const getLayerTagType = (l) => ({ host: 'primary', container: 'success', k8s: 'warning', network: 'info' }[l] || 'info')

const getFaultTypeColor = (t) => ({
  'cpu-stress': 'warning', 'mem-stress': 'warning', 'disk-fill': 'info',
  'disk-io-stress': 'info', 'process-kill': 'danger',
  'network-delay': 'primary', 'network-loss': 'danger',
  'network-bandwidth': 'primary', 'network-partition': 'danger',
  'container-stop': 'success', 'container-restart': 'success',
  'pod-kill': 'danger', 'deployment-restart': 'warning', 'dns-fault': 'danger'
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

const intensityConfig = computed(() => {
  const ft = createForm.fault_type
  const cfg = {
    'cpu-stress': { label: 'CPU 负载', unit: '%', min: 1, max: 100, step: 10, default: 80 },
    'mem-stress': { label: '填充内存', unit: 'MB', min: 64, max: 3072, step: 64, default: 512 },
    'disk-fill': { label: '磁盘填充', unit: '%', min: 10, max: 95, step: 5, default: 90 },
    'network-delay': { label: '网络延迟', unit: 'ms', min: 10, max: 5000, step: 50, default: 500 },
    'network-loss': { label: '丢包率', unit: '%', min: 1, max: 100, step: 5, default: 30 },
    'network-bandwidth': { label: '带宽限制', unit: 'kbps', min: 64, max: 1048576, step: 64, default: 1024 },
    'pod-kill': { label: '杀 Pod 比例', unit: '%', min: 10, max: 100, step: 10, default: 50 },
  }
  return cfg[ft] || null
})

watch(() => createForm.fault_type, (ft) => {
  if (intensityConfig.value) {
    createForm.intensity = intensityConfig.value.default
  }
  previewResult.value = null
})

const formatTime = (t) => t ? new Date(t).toLocaleString('zh-CN') : '-'

async function loadSummary() {
  try { const { data } = await axios.get(`${API}/summary`); summary.value = data } catch {}
}

async function loadExperiments() {
  try { const { data } = await axios.get(`${API}/experiments`); experimentList.value = data } catch {}
}

async function loadTargets() {
  try { const { data } = await axios.get(`${API}/targets`); targetAssets.value = data } catch {}
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
  Object.assign(createForm, { name: '', description: '', fault_type: 'pod-kill', target_layer: 'host', asset_id: null, target_namespace: 'default', duration: 300, intensity: 30, threshold: 99.0 })
  previewResult.value = null
  createDialogVisible.value = true
}

async function previewCommand() {
  previewLoading.value = true
  try {
    const params = { duration: createForm.duration }
    const ft = createForm.fault_type
    if (ft === 'cpu-stress') params.load_percentage = createForm.intensity
    else if (ft === 'mem-stress') params.fill_mb = createForm.intensity
    else if (ft === 'disk-fill') params.fill_percent = createForm.intensity
    else if (ft === 'network-delay') { params.latency_ms = createForm.intensity; params.percentage = 50 }
    else if (ft === 'network-loss') params.loss_percent = createForm.intensity
    else if (ft === 'network-bandwidth') params.rate_kbps = createForm.intensity
    else if (ft === 'network-partition') params.target_cidr = '10.0.0.0/8'
    else if (ft === 'process-kill') params.process_name = 'nginx'
    else if (ft === 'pod-kill') params.kill_percentage = createForm.intensity
    const { data } = await axios.post(`${API}/experiments/preview-command`, {
      name: createForm.name || '预览', description: createForm.description,
      target_type: ft.startsWith('network') ? 'network' : 'pod',
      target_layer: createForm.target_layer,
      target_selector: { asset_id: createForm.asset_id || 0, service: '', namespace: createForm.target_namespace },
      fault_type: ft, fault_params: params,
      steady_state: { metric: 'availability', threshold: createForm.threshold }
    })
    previewResult.value = data
  } catch (e) {
    ElMessage.error('命令预览失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    previewLoading.value = false
  }
}

async function createExperiment() {
  if (!createForm.name || !createForm.asset_id) { ElMessage.warning('请填写实验名称并选择目标资产'); return }
  const params = { duration: createForm.duration }
  const ft = createForm.fault_type
  if (ft === 'cpu-stress') params.load_percentage = createForm.intensity
  else if (ft === 'mem-stress') params.fill_mb = createForm.intensity
  else if (ft === 'disk-fill') params.fill_percent = createForm.intensity
  else if (ft === 'network-delay') { params.latency_ms = createForm.intensity; params.percentage = 50 }
  else if (ft === 'network-loss') params.loss_percent = createForm.intensity
  else if (ft === 'network-bandwidth') params.rate_kbps = createForm.intensity
  else if (ft === 'network-partition') params.target_cidr = '10.0.0.0/8'
  else if (ft === 'process-kill') params.process_name = 'nginx'
  else if (ft === 'pod-kill') params.kill_percentage = createForm.intensity

  const targetAsset = targetAssets.value.find(a => a.id === createForm.asset_id)
  try {
    await axios.post(`${API}/experiments`, {
      name: createForm.name, description: createForm.description,
      target_type: createForm.fault_type.startsWith('network') ? 'network' : 'pod',
      target_layer: createForm.target_layer,
      target_selector: { asset_id: createForm.asset_id, service: targetAsset?.name || '', namespace: createForm.target_namespace },
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
    if (data.status === 'completed') {
      // pod-kill 等立即完成的情况
      ElMessage.warning(data.message || '实验已完成')
      loadExperiments(); loadSummary(); loadTrend()
      return
    }
    ElMessage.success(data.message || `故障注入已启动，预计 ${data.duration}s 后完成`)
    // 异步轮询：每 4s 刷新，直到 status !== 'running'
    pollExperimentStatus(row.id, data.duration || 60)
  } catch (e) { ElMessage.error('启动失败: ' + (e.response?.data?.detail || e.message)) }
}

function pollExperimentStatus(expId, duration) {
  let elapsed = 0
  const interval = 4000
  const maxWait = (duration + 30) * 1000
  const timer = setInterval(async () => {
    elapsed += interval
    try {
      await loadExperiments()
      const cur = experimentList.value.find(e => e.id === expId)
      if (cur && cur.status !== 'running') {
        clearInterval(timer)
        loadSummary(); loadTrend()
        const pass = cur.result === 'passed'
        ElMessage.success(`实验完成，稳态${pass ? '通过 ✅' : '未通过 ❌'}`)
      }
    } catch {}
    if (elapsed >= maxWait) {
      clearInterval(timer)
      loadExperiments(); loadSummary()
    }
  }, interval)
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

function applyPrefill(prefill) {
  createForm.name = prefill.name || ''
  createForm.description = prefill.description || ''
  createForm.fault_type = prefill.fault_type || 'pod-kill'
  createForm.target_layer = prefill.target_layer || 'host'
  createForm.asset_id = null
  createForm.target_namespace = 'default'
  const fp = prefill.fault_params || {}
  createForm.duration = fp.duration || 300
  const ft = createForm.fault_type
  if (ft === 'cpu-stress') createForm.intensity = fp.load_percentage ?? 80
  else if (ft === 'mem-stress') createForm.intensity = fp.fill_mb ?? 512
  else if (ft === 'disk-fill') createForm.intensity = fp.fill_percent ?? 90
  else if (ft === 'network-delay') createForm.intensity = fp.latency_ms ?? 500
  else if (ft === 'network-loss') createForm.intensity = fp.loss_percent ?? 30
  else if (ft === 'network-bandwidth') createForm.intensity = fp.rate_kbps ?? 1024
  else if (ft === 'pod-kill') createForm.intensity = fp.kill_percentage ?? 50
  else createForm.intensity = 30
  createDialogVisible.value = true
}

onMounted(async () => {
  loadSummary(); loadExperiments(); loadTrend()
  await loadTargets()
  try {
    const raw = sessionStorage.getItem('chaos_prefill')
    if (raw) {
      sessionStorage.removeItem('chaos_prefill')
      applyPrefill(JSON.parse(raw))
    }
  } catch {}
})
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
.run-notes { white-space: pre-line; line-height: 1.6; font-size: 12px; color: #606266; }
.cmd-block { margin-top: 12px; }
.cmd-block-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: 13px; color: #606266; font-weight: 600; }
.cmd-pre { background: #1e1e1e; color: #d4d4d4; padding: 12px 16px; border-radius: 8px; font-size: 12px; line-height: 1.6; overflow-x: auto; white-space: pre-wrap; word-break: break-all; margin: 0; }
.cmd-tip { margin-top: 8px; font-size: 12px; color: #909399; }
.cmd-tip code { background: #f0f0f0; padding: 2px 6px; border-radius: 3px; color: #E6A23C; font-family: monospace; }
.cmd-preview-block { margin-top: 10px; width: 100%; }
.cmd-preview-note { color: #E6A23C; font-size: 12px; padding: 8px 12px; background: #fdf6ec; border-radius: 6px; }
.cmd-preview-label { font-size: 12px; color: #909399; margin: 8px 0 4px; font-weight: 600; }
</style>
