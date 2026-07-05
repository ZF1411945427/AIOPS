<template>
  <div class="notif-page">
    <div class="page-header">
      <h1>通知管理</h1>
      <p>通知渠道与发送记录 · {{ channels.length }} 个渠道</p>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="openCreate">+ 新增渠道</button>
      <button class="btn" @click="loadAll">刷新</button>
    </div>

    <div class="panel">
      <div class="panel-head">通知渠道</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="channels.length" class="table">
          <thead><tr><th>ID</th><th>名称</th><th>类型</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="c in channels" :key="c.id">
              <td>{{ c.id }}</td>
              <td>{{ c.name }}</td>
              <td><span class="badge type">{{ typeLabel(c.type) }}</span></td>
              <td><span class="badge" :class="c.enabled ? 'on' : 'off'">{{ c.enabled ? '启用' : '禁用' }}</span></td>
              <td class="text-sm">{{ c.created_at || '-' }}</td>
              <td><button class="btn btn-sm btn-danger" @click="deleteChannel(c)">删除</button></td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">🔔</div><div>暂无通知渠道</div></div>
      </div>
    </div>

    <div class="panel" style="margin-top:14px;">
      <div class="panel-head">通知发送记录 · {{ logs.length }} 条</div>
      <div class="panel-body">
        <table v-if="logs.length" class="table">
          <thead><tr><th>时间</th><th>渠道</th><th>告警ID</th><th>标题</th><th>接收人</th><th>状态</th></tr></thead>
          <tbody>
            <tr v-for="l in logs" :key="l.id">
              <td class="text-sm">{{ l.created_at || '-' }}</td>
              <td><span class="badge type">{{ typeLabel(l.channel_type) }}</span></td>
              <td>{{ l.alert_id || '-' }}</td>
              <td class="text-sm">{{ l.title || '-' }}</td>
              <td class="text-sm">{{ l.recipient || '-' }}</td>
              <td><span class="badge" :class="l.success ? 'on' : 'err'">{{ l.success ? '成功' : '失败' }}</span></td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">暂无发送记录</div>
      </div>
    </div>

    <div v-if="showDialog" class="modal-overlay" @click.self="showDialog = false">
      <div class="modal-box">
        <h3>新增通知渠道</h3>
        <div class="form-row"><label>名称</label><input v-model="form.name" class="input"></div>
        <div class="form-row"><label>类型</label>
          <select v-model="form.type" class="input">
            <option value="email">邮件</option><option value="webhook">Webhook</option>
            <option value="dingtalk">钉钉</option><option value="wecom">企业微信</option>
            <option value="feishu">飞书</option><option value="log">日志</option>
          </select>
        </div>
        <template v-if="form.type === 'email'">
          <div class="form-row"><label>SMTP 主机</label><input v-model="form.config.host" class="input"></div>
          <div class="form-row"><label>端口</label><input v-model.number="form.config.port" type="number" class="input"></div>
          <div class="form-row"><label>用户</label><input v-model="form.config.user" class="input"></div>
          <div class="form-row"><label>密码</label><input v-model="form.config.password" type="password" class="input"></div>
          <div class="form-row"><label>收件人(逗号分隔)</label><input v-model="form.config.recipients" class="input"></div>
        </template>
        <template v-else-if="form.type === 'webhook'">
          <div class="form-row"><label>URL</label><input v-model="form.config.url" class="input"></div>
        </template>
        <template v-else-if="['dingtalk','wecom','feishu'].includes(form.type)">
          <div class="form-row"><label>Webhook</label><input v-model="form.config.webhook" class="input"></div>
        </template>
        <div class="modal-actions">
          <button class="btn" @click="showDialog = false">取消</button>
          <button class="btn btn-primary" @click="createChannel">创建</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const channels = ref([])
const logs = ref([])
const showDialog = ref(false)
const form = ref({ name: '', type: 'email', config: { host: '', port: 587, user: '', password: '', recipients: '', url: '', webhook: '' } })

function typeLabel(t) {
  return { email: '邮件', webhook: 'Webhook', dingtalk: '钉钉', wecom: '企业微信', feishu: '飞书', log: '日志' }[t] || t
}

async function loadChannels() {
  try {
    const data = await request.get('/notifications/api/channels')
    channels.value = data.channels || []
  } catch (e) { /* 静默 */ }
}

async function loadLogs() {
  try {
    const data = await request.get('/notifications/api/logs')
    logs.value = data.logs || []
  } catch (e) { /* 静默 */ }
}

async function loadAll() {
  loading.value = true
  await Promise.all([loadChannels(), loadLogs()])
  loading.value = false
}

function openCreate() {
  form.value = { name: '', type: 'email', config: { host: '', port: 587, user: '', password: '', recipients: '', url: '', webhook: '' } }
  showDialog.value = true
}

async function createChannel() {
  if (!form.value.name) { ElMessage.warning('名称不能为空'); return }
  try {
    await request.post('/notifications/api/channels/create', { name: form.value.name, type: form.value.type, config: form.value.config })
    ElMessage.success('创建成功')
    showDialog.value = false
    loadAll()
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.message || e))
  }
}

async function deleteChannel(c) {
  try {
    await ElMessageBox.confirm(`确认删除渠道「${c.name}」？`, '删除确认', { type: 'warning' })
    await request.delete(`/notifications/api/channels/${c.id}/delete`)
    ElMessage.success('已删除')
    loadAll()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

onMounted(loadAll)
</script>

<style scoped>
.notif-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 16px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.on { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.off { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.err { background: rgba(239,68,68,0.1); color: #ef4444; }
.badge.type { background: rgba(99,102,241,0.1); color: #6366f1; }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 400px; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; color: var(--text, #1e293b); }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
