<template>
  <div class="disc-page">
    <div class="page-header">
      <h1>资产自动发现</h1>
      <p>ICMP / TCP / SSH 多协议扫描 · 自动发现网络资产</p>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="showCreate = true">+ 新建扫描任务</button>
      <button class="btn" @click="loadSchedules">刷新</button>
    </div>

    <div class="panel">
      <div class="panel-head">扫描任务</div>
      <div class="panel-body">
        <div v-if="schedules.length" class="sched-list">
          <div v-for="s in schedules" :key="s.id" class="sched-item" :class="{ disabled: !s.enabled }">
            <div class="sched-head">
              <span class="sched-name">{{ s.name }}</span>
              <span class="sched-status" :class="s.enabled ? 'active' : 'inactive'">{{ s.enabled ? '启用' : '停用' }}</span>
              <span class="sched-protocol">{{ s.protocol }}</span>
              <span class="sched-cron">{{ s.schedule_cron }}</span>
            </div>
            <div class="sched-target">范围: {{ s.target_range }}</div>
            <div class="sched-actions">
              <button class="btn btn-sm btn-primary" @click="runNow(s)">立即扫描</button>
              <button class="btn btn-sm" @click="toggleSchedule(s)">{{ s.enabled ? '停用' : '启用' }}</button>
              <button class="btn btn-sm btn-ghost" @click="deleteSchedule(s)">删除</button>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">暂无扫描任务</div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head">扫描结果</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="!results.length" class="empty-state">暂无扫描结果</div>
        <div v-else class="gap-table-wrap">
          <table class="gap-table">
            <thead><tr><th>IP</th><th>端口</th><th>主机名</th><th>状态</th><th>时间</th></tr></thead>
            <tbody>
              <tr v-for="r in results" :key="r.id">
                <td><span class="ip-addr">{{ r.ip }}</span></td>
                <td>{{ r.port }}</td>
                <td>{{ r.hostname || '-' }}</td>
                <td><span class="status-dot" :class="statusClass(r.status)">{{ r.status }}</span></td>
                <td class="text-sm">{{ r.discovered_at }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal-box">
        <h3>新建扫描任务</h3>
        <div class="form-group">
          <label class="form-label">任务名称</label>
          <input v-model="form.name" class="input" placeholder="例如: 内网服务器发现">
        </div>
        <div class="form-group">
          <label class="form-label">协议</label>
          <select v-model="form.protocol" class="input">
            <option value="tcp">TCP 端口检测</option>
            <option value="ssh">SSH 检测</option>
            <option value="icmp">ICMP Ping</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">目标范围 (逗号分隔)</label>
          <input v-model="form.target_range" class="input" placeholder="192.168.1.1-254, 10.0.0.1">
        </div>
        <div class="form-group">
          <label class="form-label">端口</label>
          <input v-model.number="form.port" type="number" class="input" placeholder="22">
        </div>
        <div class="form-group">
          <label class="form-label">Cron 表达式</label>
          <input v-model="form.schedule_cron" class="input" placeholder="0 2 * * *">
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" @click="createSchedule">创建</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const schedules = ref([])
const results = ref([])
const loading = ref(false)
const showCreate = ref(false)
const form = ref({ name: '', protocol: 'tcp', target_range: '', port: 22, schedule_cron: '0 2 * * *' })

function statusClass(s) {
  if (s === 'open' || s === 'reachable') return 'status-open'
  if (s === 'closed' || s === 'unreachable') return 'status-closed'
  return 'status-unknown'
}

async function loadSchedules() {
  try {
    const data = await request.get('/assets/api/discovery/schedules')
    schedules.value = data.items || []
  } catch (e) { ElMessage.error('加载失败: ' + (e.message || e)) }
}

async function loadResults() {
  loading.value = true
  try {
    const data = await request.get('/assets/api/discovery/results', { params: { page: 1, per_page: 100 } })
    results.value = data.items || []
  } catch (e) { ElMessage.error('加载失败: ' + (e.message || e)) } finally { loading.value = false }
}

async function createSchedule() {
  try {
    await request.post('/assets/api/discovery/schedules', form.value)
    ElMessage.success('任务已创建')
    showCreate.value = false
    loadSchedules()
  } catch (e) { ElMessage.error('创建失败: ' + (e.message || e)) }
}

async function runNow(s) {
  try {
    const data = await request.post('/assets/api/discovery/run/' + s.id)
    ElMessage.success('扫描完成: ' + data.scanned + ' 台')
    loadResults()
  } catch (e) { ElMessage.error('扫描失败: ' + (e.message || e)) }
}

async function toggleSchedule(s) {
  try {
    await request.put('/assets/api/discovery/schedules/' + s.id, { enabled: !s.enabled })
    loadSchedules()
  } catch (e) { ElMessage.error('操作失败: ' + (e.message || e)) }
}

async function deleteSchedule(s) {
  try {
    await request.delete('/assets/api/discovery/schedules/' + s.id)
    ElMessage.success('已删除')
    loadSchedules()
  } catch (e) { ElMessage.error('删除失败: ' + (e.message || e)) }
}

onMounted(() => { loadSchedules(); loadResults() })
</script>

<style scoped>
.disc-page { padding: 4px; }
.page-header { margin-bottom: 12px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; margin: 0 0 4px; }
.page-header p { color: var(--text-secondary,#64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong,rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid,#fff); cursor: pointer; font-size: 0.82rem; }
.btn-primary { background: var(--accent,#6366f1); color: #fff; border-color: var(--accent,#6366f1); }
.btn-sm { padding: 3px 10px; font-size: 0.75rem; }
.btn-ghost { background: transparent; border-color: var(--border-strong,rgba(0,0,0,0.12)); color: var(--text-secondary,#64748b); }
.panel { background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; margin-bottom: 14px; }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; }
.panel-body { padding: 16px 18px; }
.sched-list { display: flex; flex-direction: column; gap: 10px; }
.sched-item { border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 8px; padding: 12px; }
.sched-item.disabled { opacity: 0.6; }
.sched-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.sched-name { font-weight: 600; flex: 1; font-size: 0.88rem; }
.sched-status { font-size: 0.7rem; font-weight: 600; padding: 1px 6px; border-radius: 6px; }
.active { background: rgba(34,197,94,0.12); color: #22c55e; }
.inactive { background: rgba(148,163,184,0.12); color: #64748b; }
.sched-protocol { font-size: 0.72rem; background: rgba(99,102,241,0.08); color: #6366f1; padding: 1px 6px; border-radius: 4px; }
.sched-cron { font-size: 0.72rem; color: var(--text-tertiary,#94a3b8); }
.sched-target { font-size: 0.78rem; color: var(--text-secondary,#64748b); margin-bottom: 8px; }
.sched-actions { display: flex; gap: 6px; }
.gap-table-wrap { overflow-x: auto; }
.gap-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.gap-table th { text-align: left; padding: 8px 10px; border-bottom: 2px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; color: var(--text-secondary,#64748b); font-size: 0.75rem; text-transform: uppercase; }
.gap-table td { padding: 10px 10px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.05)); vertical-align: middle; }
.gap-table tbody tr:hover { background: var(--bg-hover,rgba(0,0,0,0.02)); }
.ip-addr { font-family: monospace; font-weight: 600; }
.status-dot { font-size: 0.75rem; font-weight: 600; }
.status-open { color: #22c55e; }
.status-closed { color: #ef4444; }
.status-unknown { color: #94a3b8; }
.text-sm { font-size: 0.78rem; }
.form-group { margin-bottom: 10px; }
.form-label { display: block; font-size: 0.78rem; font-weight: 600; color: var(--text-secondary,#64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border,rgba(0,0,0,0.1)); border-radius: 6px; font-size: 0.82rem; box-sizing: border-box; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid,#fff); border-radius: 12px; padding: 24px; min-width: 400px; box-shadow: 0 8px 32px rgba(0,0,0,0.15); }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; font-weight: 600; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary,#94a3b8); font-size: 0.9rem; }
</style>
