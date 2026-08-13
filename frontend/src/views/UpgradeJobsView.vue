<template>
  <div class="up-page">
    <div class="page-header">
      <h1>⬆️ Edge 升级协作器</h1>
      <p>edge 升级任务 · 状态机(pending/running/completed/failed/rolled_back) · 批次滚动 · 逐 agent verify · 失败自动回滚(持久化)</p>
    </div>

    <div class="stat-row">
      <div class="stat-card"><span class="stat-num">{{ jobs.length }}</span><span>任务总数</span></div>
      <div class="stat-card"><span class="stat-num">{{ statusCount('completed') }}</span><span>已完成</span></div>
      <div class="stat-card" :class="{ warn: statusCount('failed') > 0 }"><span class="stat-num">{{ statusCount('failed') }}</span><span>失败/回滚</span></div>
      <div class="stat-card"><span class="stat-num">{{ runningCount }}</span><span>进行中</span></div>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="openDialog()">+ 新建升级任务</button>
      <button class="btn" @click="load()">🔄 刷新</button>
    </div>

    <div v-if="jobs.length" class="job-list">
      <div v-for="j in jobs" :key="j.id" class="job-card">
        <div class="job-head">
          <span class="job-name">{{ j.name }}</span>
          <span class="badge ver">{{ j.from_version }} → {{ j.to_version }}</span>
          <span class="status-pill" :class="'st-' + j.status">{{ statusLabel(j.status) }}</span>
          <button class="btn-icon-sm danger" title="删除" @click="del(j)">🗑️</button>
        </div>
        <div class="progress-row">
          <div class="bar"><div class="fill" :style="{ width: j.overall_progress + '%' }"></div></div>
          <span class="pct">{{ j.overall_progress }}%</span>
        </div>
        <div class="job-meta">
          <span>策略: {{ j.strategy }} (batch={{ j.batch_size }})</span>
          <span>创建: {{ (j.created_at || '').slice(0, 19).replace('T', ' ') }}</span>
        </div>
        <div v-if="j.log && j.log.length" class="job-log">
          <div v-for="(l, i) in j.log.slice(-6)" :key="i" class="log-line">{{ l.msg }}</div>
        </div>
        <div class="job-ops">
          <button v-if="canRun(j)" class="btn btn-primary" @click="run(j)">▶️ 执行</button>
          <button v-if="isRunning(j)" class="btn" @click="pause(j)">⏸ 暂停</button>
          <button class="btn" @click="detail(j)">👁️ 步骤详情</button>
        </div>
      </div>
    </div>
    <div v-else class="empty-state"><div style="font-size:40px;margin-bottom:12px;">⬆️</div><div>暂无升级任务</div></div>

    <el-dialog v-model="showDialog" title="新建升级任务" width="520px" top="12vh">
      <el-form label-width="110px">
        <el-form-item label="任务名"><el-input v-model="form.name" placeholder="自动生成 upgrade-to-<ver>" /></el-form-item>
        <el-form-item label="目标版本" required><el-input v-model="form.to_version" placeholder="如 1.2.0" /></el-form-item>
        <el-form-item label="关联集群">
          <el-select v-model="form.cluster_id" style="width:100%" clearable placeholder="可选">
            <el-option v-for="c in clusters" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="策略">
          <el-select v-model="form.strategy" style="width:100%">
            <el-option label="batch（分批）" value="batch" />
            <el-option label="all_at_once（一次全量）" value="all_at_once" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.strategy === 'batch'" label="每批数量"><el-input-number v-model="form.batch_size" :min="1" :max="20" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="create()">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showDetail" title="升级步骤详情" width="780px" top="5vh">
      <div v-if="detailJob" class="detail-card">
        <div class="detail-head">
          <span class="job-name big">{{ detailJob.name }}</span>
          <span class="status-pill" :class="'st-' + detailJob.status">{{ statusLabel(detailJob.status) }}</span>
          <span class="badge ver">{{ detailJob.from_version }} → {{ detailJob.to_version }}</span>
        </div>
        <table class="table">
          <thead><tr><th>批</th><th>顺序</th><th>Agent</th><th>主机</th><th>动作</th><th>状态</th><th>输出</th><th>耗时</th></tr></thead>
          <tbody>
            <tr v-for="s in detailJob.steps" :key="s.id">
              <td>{{ s.batch_no }}</td>
              <td>{{ s.step_order }}</td>
              <td><code>{{ s.agent_id }}</code></td>
              <td>{{ s.hostname }}</td>
              <td><span class="badge">{{ s.action }}</span></td>
              <td><span :class="'step-' + s.status">{{ s.status }}</span></td>
              <td class="out">{{ s.output || '-' }}</td>
              <td>{{ s.duration_ms }}ms</td>
            </tr>
          </tbody>
        </table>
      </div>
      <template #footer><el-button @click="showDetail = false">关闭</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const jobs = ref([])
const clusters = ref([])
const showDialog = ref(false)
const showDetail = ref(false)
const creating = ref(false)
const detailJob = ref(null)
const form = ref({ name: '', to_version: '', cluster_id: null, strategy: 'batch', batch_size: 2 })

const runningCount = computed(() => jobs.value.filter(j => ['pending', 'running'].includes(j.status)).length)
function statusCount(s) { return jobs.value.filter(j => j.status === s).length }
function statusLabel(s) { return { pending: '待执行', running: '执行中', paused: '已暂停', completed: '已完成', failed: '失败', rolled_back: '已回滚' }[s] || s }
function canRun(j) { return ['pending', 'failed', 'paused'].includes(j.status) }
function isRunning(j) { return j.status === 'running' }

async function load() {
  try {
    const d = await request.get('/api/upgrade-jobs')
    jobs.value = d.jobs || []
    const c = await request.get('/api/k8s-clusters')
    clusters.value = c.clusters || []
  } catch (e) { ElMessage.error(e.message) }
}

function openDialog() {
  form.value = { name: '', to_version: '', cluster_id: null, strategy: 'batch', batch_size: 2 }
  showDialog.value = true
}

async function create() {
  if (!form.value.to_version.trim()) { ElMessage.warning('目标版本不能为空'); return }
  creating.value = true
  try {
    const d = await request.post('/api/upgrade-jobs', form.value)
    ElMessage.success(`任务已创建 (status=${d.job.status})`)
    showDialog.value = false
    await load()
  } catch (e) { ElMessage.error(e.message) } finally { creating.value = false }
}

async function run(j) {
  try {
    const d = await request.post(`/api/upgrade-jobs/${j.id}/run`, {})
    if (d.ok) ElMessage.success(`执行结果: ${d.job.status} (${d.job.overall_progress}%)`)
    await load()
  } catch (e) { ElMessage.error(e.message) }
}

async function pause(j) {
  try {
    const d = await request.post(`/api/upgrade-jobs/${j.id}/pause`, {})
    if (d.ok) ElMessage.success('已暂停')
    await load()
  } catch (e) { ElMessage.error(e.message) }
}

async function detail(j) {
  try {
    const d = await request.get(`/api/upgrade-jobs/${j.id}`)
    detailJob.value = d.job
    showDetail.value = true
  } catch (e) { ElMessage.error(e.message) }
}

async function del(j) {
  try {
    await ElMessageBox.confirm(`确认删除升级任务「${j.name}」？`, '删除任务', { type: 'warning' })
  } catch { return }
  try {
    await request.delete(`/api/upgrade-jobs/${j.id}`)
    ElMessage.success('已删除')
    await load()
  } catch (e) { ElMessage.error(e.message) }
}

load()
</script>

<style scoped>
.up-page { padding: 20px; }
.page-header h1 { margin: 0 0 6px; }
.page-header p { color: #8b949e; margin: 0 0 16px; font-size: 13px; }
.stat-row { display: flex; gap: 14px; margin-bottom: 16px; flex-wrap: wrap; }
.stat-card { background: #fafafa; border: 1px solid #eee; border-radius: 8px; padding: 12px 20px; min-width: 110px; }
.stat-card.warn .stat-num { color: #d03050; }
.stat-num { display: block; font-size: 22px; font-weight: 600; }
.stat-card span { color: #666; font-size: 12px; }
.toolbar { display: flex; gap: 10px; margin-bottom: 16px; }
.btn { padding: 7px 14px; border: 1px solid #d9d9d9; background: #fff; border-radius: 6px; cursor: pointer; }
.btn:hover { border-color: #409eff; color: #409eff; }
.btn-primary { background: #409eff; color: #fff; border-color: #409eff; }
.btn-primary:hover { background: #66b1ff; color: #fff; }
.job-list { display: flex; flex-direction: column; gap: 14px; }
.job-card { border: 1px solid #eee; border-radius: 10px; padding: 14px 16px; background: #fff; }
.job-head { display: flex; gap: 10px; align-items: center; }
.job-name { font-weight: 700; font-size: 15px; }
.job-name.big { font-size: 18px; }
.badge.ver { background: #f0f2f5; }
.status-pill { padding: 2px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }
.st-pending { background: #f0f2f5; color: #57606a; }
.st-running { background: #e6f7ff; color: #1890ff; }
.st-paused { background: #fff7e6; color: #d48806; }
.st-completed { background: #f6ffed; color: #52c41a; }
.st-failed, .st-rolled_back { background: #fff1f0; color: #cf1322; }
.progress-row { display: flex; align-items: center; gap: 10px; margin: 10px 0 6px; }
.bar { flex: 1; height: 8px; background: #f0f2f5; border-radius: 4px; overflow: hidden; }
.fill { height: 100%; background: #409eff; border-radius: 4px; transition: width .3s; }
.pct { font-size: 12px; color: #57606a; width: 38px; }
.job-meta { display: flex; gap: 20px; font-size: 12px; color: #8b949e; margin-bottom: 8px; }
.job-log { background: #fafafa; border-radius: 6px; padding: 8px 10px; margin-bottom: 10px; }
.log-line { font-size: 11px; color: #57606a; }
.job-ops { display: flex; gap: 8px; }
.detail-head { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; }
.table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; }
.table th, .table td { border-bottom: 1px solid #f0f0f0; padding: 8px 10px; text-align: left; font-size: 13px; }
.table th { background: #fafafa; color: #666; font-weight: 500; white-space: nowrap; }
.badge { display: inline-block; background: #f0f2f5; border-radius: 4px; padding: 1px 8px; font-size: 12px; color: #57606a; }
.step-success { color: #52c41a; font-weight: 600; }
.step-failed { color: #cf1322; font-weight: 600; }
.step-pending { color: #57606a; }
.step-running { color: #1890ff; font-weight: 600; }
.step-skipped { color: #d48806; }
.out { max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; color: #57606a; }
.btn-icon-sm { border: 1px solid #d9d9d9; background: #fff; border-radius: 4px; width: 26px; height: 26px; cursor: pointer; margin-left: auto; }
.btn-icon-sm:hover { border-color: #d03050; }
.empty-state { text-align: center; color: #8b949e; padding: 60px 0; background: #fafafa; border-radius: 8px; }
</style>
