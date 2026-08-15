<template>
  <div class="notif-page">
    <div class="page-header">
      <h1>通知管理</h1>
      <p>通知渠道、发送记录与升级策略 · {{ channels.length }} 个渠道 / {{ policyList.length }} 个升级策略</p>
    </div>

    <el-tabs v-model="activeTab" class="notif-tabs">
      <!-- 通知渠道 -->
      <el-tab-pane label="通知渠道" name="channels">
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
                  <td>
                    <el-switch :model-value="c.enabled" size="small" @change="toggleChannel(c)" style="margin-right:8px" />
                    <button class="btn btn-sm" @click="openEdit(c)" style="margin-right:4px">编辑</button>
                    <button class="btn btn-sm" style="margin-right:4px" @click="testChannel(c)">测试</button>
                    <button class="btn btn-sm btn-danger" @click="deleteChannel(c)">删除</button>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">🔔</div><div>暂无通知渠道</div></div>
          </div>
        </div>
      </el-tab-pane>

      <!-- 发送记录 -->
      <el-tab-pane label="发送记录" name="logs">
        <div class="panel">
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
                  <td><span class="badge" :class="l.is_success ? 'on' : 'err'">{{ l.is_success ? '成功' : '失败' }}</span></td>
                </tr>
              </tbody>
            </table>
            <div v-else class="empty-state">暂无发送记录</div>
          </div>
        </div>
      </el-tab-pane>

      <!-- 升级策略 -->
      <el-tab-pane label="升级策略" name="escalation">
        <div class="toolbar">
          <button class="btn btn-guide" @click="showGuide = !showGuide">📖 操作说明</button>
          <button class="btn btn-primary" @click="showCreateDialog">+ 新建策略</button>
        </div>
        <div class="panel">
          <div class="panel-head">升级策略管理</div>
          <div class="panel-body">
            <table v-if="policyList.length" class="table">
              <thead><tr><th>策略名</th><th>升级级别</th><th>等待时间(分)</th><th>通知渠道</th><th>状态</th><th>操作</th></tr></thead>
              <tbody>
                <tr v-for="row in policyList" :key="row.id">
                  <td>{{ row.name }}</td>
                  <td><span v-for="(l, i) in parseList(row.levels)" :key="i" class="badge type" style="margin-right:4px">{{ l }}</span></td>
                  <td>
                    <span v-for="(w, i) in parseList(row.wait_minutes)" :key="i">{{ w }}分{{ i < parseList(row.wait_minutes).length - 1 ? ' → ' : '' }}</span>
                  </td>
                  <td><span v-for="(c, i) in parseList(row.notify_channels)" :key="i" class="badge type" style="margin-right:4px">{{ c }}</span></td>
                  <td><span class="badge" :class="row.is_active ? 'on' : 'off'">{{ row.is_active ? '启用' : '禁用' }}</span></td>
                  <td><button class="btn btn-sm btn-danger" @click="deletePolicy(row.id)">删除</button></td>
                </tr>
              </tbody>
            </table>
            <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">📶</div><div>暂无升级策略</div></div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 新增/编辑通知渠道对话框 -->
    <div v-if="showDialog" class="modal-overlay">
      <div class="modal-box">
        <h3>{{ isEditing ? '编辑通知渠道' : '新增通知渠道' }}</h3>
        <div class="form-row"><label>名称</label><input v-model="form.name" class="input"></div>
        <div class="form-row"><label>类型</label>
          <select v-model="form.type" class="input" :disabled="isEditing">
            <option value="email">邮件</option><option value="webhook">Webhook</option>
            <option value="dingtalk">钉钉</option><option value="wecom">企业微信</option>
            <option value="feishu">飞书</option><option value="log">日志</option>
          </select>
        </div>
        <template v-if="form.type === 'email'">
          <div class="form-row"><label>SMTP 主机</label><input v-model="form.config.host" class="input"></div>
          <div class="form-row"><label>端口</label><input v-model.number="form.config.port" type="number" class="input"></div>
          <div class="form-row"><label>用户</label><input v-model="form.config.user" class="input"></div>
          <div class="form-row"><label>密码</label><input v-model="form.config.password" type="password" class="input" :placeholder="isEditing ? '不填则不修改' : ''"></div>
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
          <button class="btn btn-primary" @click="isEditing ? updateChannel() : createChannel()">{{ isEditing ? '保存' : '创建' }}</button>
        </div>
      </div>
    </div>

    <!-- 新建升级策略对话框 -->
    <el-dialog v-model="escDialogVisible" title="新建升级策略" width="500px">
      <el-form :model="escForm" label-width="100px">
        <el-form-item label="策略名">
          <el-input v-model="escForm.name" placeholder="如: 严重告警升级" />
        </el-form-item>
        <el-form-item label="升级级别">
          <el-input v-model="levelsStr" placeholder="用逗号分隔，如: L1,L2,L3" />
        </el-form-item>
        <el-form-item label="等待时间(分)">
          <el-input v-model="waitStr" placeholder="用逗号分隔，如: 5,15,30" />
        </el-form-item>
        <el-form-item label="通知渠道">
          <el-input v-model="escChannelsStr" placeholder="用逗号分隔，如: 短信,邮件,电话" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="escDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="createPolicy">确定</el-button>
      </template>
    </el-dialog>

    <GuideDrawer v-model="showGuide" title="📖 升级策略 · 概念说明">
      <section class="guide-section">
        <h4>1. 什么是升级策略？</h4>
        <p><strong>升级策略（Escalation Policy）</strong>定义了：当告警发生且没人处理时，<strong>事情会如何一步步升级</strong>，直到有人响应为止。</p>
        <p>简单的说就是：<strong>L1 没人看 → 找 L2 → L2 也没看 → 找 L3 → ...</strong></p>
      </section>
      <section class="guide-section">
        <h4>2. 升级流程示例</h4>
        <p>一条典型的升级链：</p>
        <div class="guide-code" style="color:#e2e8f0; padding:10px 14px; margin:6px 0;">
告警触发
  ↓ (等待 5 分钟)
L1 值班人收到短信通知
  ↓ (5 分钟内未确认)
L2 技术主管收到电话通知
  ↓ (15 分钟内未确认)
L3 运维经理收到电话 + 邮件通知
  ↓ (30 分钟内未确认)
L4 总监 → 启动应急响应流程
        </div>
      </section>
      <section class="guide-section">
        <h4>3. 三个关键配置</h4>
        <div class="key-value-list">
          <div class="kv-row">
            <span class="kv-key">升级级别</span>
            <span class="kv-val">定义了哪些角色参与（如 L1=值班工程师, L2=技术主管, L3=运维经理）。级别越高，处理问题的人资历越深（但也越贵、人数越少）</span>
          </div>
          <div class="kv-row">
            <span class="kv-key">等待时间</span>
            <span class="kv-val">在每个级别等待多久。通常在 L1 等短一点（5分钟），L2 等长一点（15分钟）。等待时间决定了"多快能联系到人"</span>
          </div>
          <div class="kv-row">
            <span class="kv-key">通知渠道</span>
            <span class="kv-val">不同级别用不同渠道通知。L1 用短信/App 推送（便宜但容易错过），L3 用电话（成本高但必达）</span>
          </div>
        </div>
      </section>
      <section class="guide-section">
        <h4>4. 为什么要设计升级策略？</h4>
        <ul>
          <li><strong>避免告警无人处理</strong> — 值班人可能在忙/睡觉/没信号</li>
          <li><strong>确保及时响应</strong> — 升级链保证事情总有人兜底</li>
          <li><strong>分层处理</strong> — 简单问题 L1 解决，复杂问题升级到更专业的人</li>
          <li><strong>可审计</strong> — 每次升级都有记录，方便事后复盘</li>
        </ul>
      </section>
    </GuideDrawer>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'
import GuideDrawer from '@/components/GuideDrawer.vue'

const activeTab = ref('channels')

// ===== 通知渠道 + 发送记录 =====
const loading = ref(false)
const channels = ref([])
const logs = ref([])
const showDialog = ref(false)
const isEditing = ref(false)
const editingId = ref(null)
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
  isEditing.value = false
  editingId.value = null
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

function openEdit(c) {
  isEditing.value = true
  editingId.value = c.id
  form.value = {
    name: c.name,
    type: c.type,
    config: {
      host: c.config?.host || '',
      port: c.config?.port ?? 587,
      user: c.config?.user || '',
      password: '',
      recipients: c.config?.recipients || '',
      url: c.config?.url || '',
      webhook: c.config?.webhook || '',
    },
  }
  showDialog.value = true
}

async function updateChannel() {
  if (!form.value.name) { ElMessage.warning('名称不能为空'); return }
  try {
    await request.post(`/notifications/api/channels/${editingId.value}/update`, {
      name: form.value.name,
      type: form.value.type,
      config: form.value.config,
    })
    ElMessage.success('保存成功')
    showDialog.value = false
    loadAll()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.message || e))
  }
}

async function testChannel(c) {
  try {
    const data = await request.post(`/notifications/api/channels/${c.id}/test`)
    if (data.status === 'ok') {
      ElMessage.success('测试发送成功')
    } else {
      ElMessage.error('测试失败: ' + (data.detail || '未知错误'))
    }
  } catch (e) {
    ElMessage.error('测试失败: ' + (e.message || e))
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

async function toggleChannel(c) {
  try {
    const data = await request.post(`/notifications/api/channels/${c.id}/toggle`, { enabled: !c.enabled })
    ElMessage.success(data.enabled ? '已启用' : '已禁用')
    loadAll()
  } catch (e) {
    ElMessage.error('切换失败: ' + (e.message || e))
  }
}

// ===== 升级策略 =====
const showGuide = ref(false)
const policyList = ref([])
const escDialogVisible = ref(false)
const levelsStr = ref('')
const waitStr = ref('')
const escChannelsStr = ref('')
const escForm = reactive({
  name: '',
  levels: [],
  wait_minutes: [],
  notify_channels: [],
  is_active: true
})

async function loadPolicies() {
  try {
    const data = await request.get('/api/sre/escalation')
    policyList.value = Array.isArray(data) ? data : (data.items || [])
  } catch (e) {
    console.error('loadPolicies:', e)
  }
}

function showCreateDialog() {
  escForm.name = ''
  levelsStr.value = ''
  waitStr.value = ''
  escChannelsStr.value = ''
  escDialogVisible.value = true
}

async function createPolicy() {
  try {
    await request.post('/api/sre/escalation', {
      ...escForm,
      levels: levelsStr.value.split(',').map(s => s.trim()).filter(Boolean),
      wait_minutes: waitStr.value.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n)),
      notify_channels: escChannelsStr.value.split(',').map(s => s.trim()).filter(Boolean),
      is_active: true
    })
    ElMessage.success('创建成功')
    escDialogVisible.value = false
    loadPolicies()
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.message || e))
  }
}

async function deletePolicy(id) {
  try {
    await ElMessageBox.confirm('确认删除该升级策略？', '删除确认', { type: 'warning' })
    await request.delete(`/api/sre/escalation/${id}`)
    ElMessage.success('删除成功')
    loadPolicies()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

function parseList(val) {
  if (!val) return []
  if (Array.isArray(val)) return val
  try { return JSON.parse(val) } catch { return [] }
}

onMounted(() => {
  loadAll()
  loadPolicies()
})
</script>

<style scoped>
.notif-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.notif-tabs :deep(.el-tabs__header) { margin-bottom: 14px; }
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
