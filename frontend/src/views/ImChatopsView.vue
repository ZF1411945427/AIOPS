<template>
  <div class="im-page">
    <div class="page-header">
      <h1>IM 双向通道（ChatOps）</h1>
      <p>飞书 / 钉钉 / 企业微信群内指令回传 → 触发 Agent 执行 → 结果回推</p>
    </div>

    <div v-if="loading" class="loading-state">加载中...</div>

    <template v-else>
      <!-- 双向通道配置 -->
      <div class="panel">
        <div class="panel-head">
          <span>双向通道配置 ({{ channels.length }})</span>
          <span class="panel-hint">在「通知管理」创建 IM 通道后，在此启用双向</span>
        </div>
        <div class="panel-body">
          <div v-if="!channels.length" class="empty-state">
            暂无双向通道。请先在「通知管理」创建飞书/钉钉/企微通道，然后在此启用双向。
          </div>
          <div v-for="c in channels" :key="c.id" class="ch-card">
            <div class="ch-head">
              <span class="ch-platform" :class="`pf-${c.type}`">{{ platformIcon(c.type) }} {{ platformName(c.type) }}</span>
              <span class="ch-name">{{ c.name }}</span>
              <span class="ch-status" :class="{ on: c.bidirectional, off: !c.bidirectional }">
                {{ c.bidirectional ? '✅ 已启用双向' : '⏸ 单向' }}
              </span>
            </div>
            <div class="ch-config">
              <div class="ch-field">
                <label>回调 URL</label>
                <code class="callback-url">{{ callbackUrl(c) }}</code>
              </div>
              <div class="ch-field">
                <label>默认子专家</label>
                <select v-model="c.default_sub_agent" @change="updateChannel(c)" class="sub-select">
                  <option value="auto">🎯 自动路由</option>
                  <option v-for="sa in subAgents" :key="sa.name" :value="sa.name">{{ sa.icon }} {{ sa.display_name }}</option>
                </select>
              </div>
              <div class="ch-field">
                <label>双向</label>
                <button class="toggle-btn" :class="{ on: c.bidirectional }" @click="toggleBidirectional(c)">
                  {{ c.bidirectional ? '已启用' : '已禁用' }}
                </button>
              </div>
            </div>
            <div class="ch-actions">
              <button class="action-btn" @click="testReply(c)">📡 测试回推</button>
              <button class="action-btn" @click="configureTokens(c)">⚙️ 配置签名密钥</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 最近 IM 消息 -->
      <div class="panel" style="margin-top: 20px;">
        <div class="panel-head">
          <span>最近 IM 消息 ({{ messages.length }})</span>
          <button class="action-btn" @click="loadMessages">🔄 刷新</button>
        </div>
        <div class="panel-body">
          <div v-if="!messages.length" class="empty-state">暂无 IM 消息</div>
          <div v-for="m in messages" :key="m.id" class="msg-card">
            <div class="msg-head">
              <span class="msg-platform">{{ platformIcon(m.platform) }}</span>
              <span class="msg-sender">{{ m.sender_name || m.sender_id }}</span>
              <span class="msg-cmd" :class="`cmd-${m.command}`">/{{ m.command }}</span>
              <span class="msg-status" :class="`st-${m.status}`">{{ statusText(m.status) }}</span>
              <span class="msg-time">{{ formatTime(m.created_at) }}</span>
            </div>
            <div class="msg-text">📝 {{ m.message_text }}</div>
            <div v-if="m.reply_text" class="msg-reply">
              <span class="reply-label">🤖 回复：</span>
              <pre class="reply-text">{{ m.reply_text }}</pre>
            </div>
          </div>
        </div>
      </div>

      <!-- 指令帮助 -->
      <div class="panel" style="margin-top: 20px;">
        <div class="panel-head"><span>支持指令</span></div>
        <div class="panel-body">
          <div class="cmd-list">
            <div class="cmd-item"><code>/ai &lt;消息&gt;</code><span>调用 AI 智能助手，如 /ai 查一下当前告警</span></div>
            <div class="cmd-item"><code>/alert</code><span>查询最近未确认告警摘要</span></div>
            <div class="cmd-item"><code>/help</code><span>显示帮助</span></div>
            <div class="cmd-item"><code>自然语言</code><span>直接发消息（如 mysql 慢查询怎么排查），自动当作 /ai 处理</span></div>
          </div>
        </div>
      </div>
    </template>

    <!-- 配置签名密钥弹窗 -->
    <div v-if="configDialog" class="modal-overlay" @click.self="configDialog = null">
      <div class="modal">
        <div class="modal-title">配置 {{ platformName(configDialog.type) }} 签名密钥</div>
        <div class="modal-body">
          <div class="modal-field">
            <label>Verify Token / Callback Token</label>
            <input v-model="configDialog.callback_token" placeholder="用于校验回调来源" />
            <span class="hint">{{ tokenHint(configDialog.type) }}</span>
          </div>
          <div class="modal-field">
            <label>Encrypt Key / Secret / Token</label>
            <input v-model="configDialog.callback_secret" placeholder="用于签名校验" />
            <span class="hint">{{ secretHint(configDialog.type) }}</span>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn-cancel" @click="configDialog = null">取消</button>
          <button class="btn-save" @click="saveTokens">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(true)
const channels = ref([])
const messages = ref([])
const subAgents = ref([])
const configDialog = ref(null)

function platformIcon(type) {
  return { feishu: '🐦', dingtalk: '🔷', wecom: '💚' }[type] || '💬'
}
function platformName(type) {
  return { feishu: '飞书', dingtalk: '钉钉', wecom: '企业微信' }[type] || type
}
function callbackUrl(c) {
  return `${window.location.origin}/im/callback/${c.type}`
}
function statusText(s) {
  return { pending: '待处理', processing: '处理中', replied: '已回复', failed: '失败' }[s] || s
}
function formatTime(t) {
  return new Date(t).toLocaleString('zh-CN', { hour12: false })
}
function tokenHint(type) {
  return {
    feishu: '飞书：事件订阅 → 加密策略 → Encrypt Key',
    dingtalk: '钉钉：Outgoing → secret',
    wecom: '企微：Token（回调配置）',
  }[type] || ''
}
function secretHint(type) {
  return {
    feishu: '飞书：Encrypt Key（用于解密消息体）',
    dingtalk: '钉钉：Secret（用于签名校验）',
    wecom: '企微：EncodingAESKey（用于解密）',
  }[type] || ''
}

async function loadChannels() {
  try {
    const data = await request.get('/im/channels')
    channels.value = data.channels || []
  } catch (e) { console.error(e) }
}

async function loadMessages() {
  try {
    const data = await request.get('/im/incoming', { params: { limit: 30 } })
    messages.value = data.messages || []
  } catch (e) { console.error(e) }
}

async function loadSubAgents() {
  try {
    const data = await request.get('/agent/sub-agents/manifest')
    subAgents.value = (data.sub_agents || []).filter(a => a.name !== 'general')
  } catch (e) { console.error(e) }
}

async function updateChannel(c) {
  try {
    await request.post(`/im/channels/${c.id}/configure`, {
      default_sub_agent: c.default_sub_agent,
    })
    ElMessage.success('子专家已更新')
  } catch (e) { ElMessage.error('更新失败') }
}

async function toggleBidirectional(c) {
  c.bidirectional = !c.bidirectional
  try {
    await request.post(`/im/channels/${c.id}/configure`, { bidirectional: c.bidirectional })
    ElMessage.success(c.bidirectional ? '已启用双向' : '已禁用双向')
  } catch (e) { ElMessage.error('操作失败') }
}

function configureTokens(c) {
  configDialog.value = { ...c }
}

async function saveTokens() {
  try {
    await request.post(`/im/channels/${configDialog.value.id}/configure`, {
      callback_token: configDialog.value.callback_token || '',
      callback_secret: configDialog.value.callback_secret || '',
    })
    ElMessage.success('签名密钥已保存')
    configDialog.value = null
    await loadChannels()
  } catch (e) { ElMessage.error('保存失败') }
}

async function testReply(c) {
  try {
    const data = await request.post(`/im/test-reply/${c.id}`, { text: '🧪 AIOps 测试消息：IM 双向通道已连通' })
    if (data.ok) ElMessage.success('回推成功')
    else ElMessage.warning('回推失败: ' + (data.error || ''))
  } catch (e) { ElMessage.error('请求失败') }
}

onMounted(async () => {
  await Promise.all([loadChannels(), loadMessages(), loadSubAgents()])
  loading.value = false
})
</script>

<style scoped>
.im-page { padding: 20px; }
.page-header { margin-bottom: 24px; }
.page-header h1 { font-size: 1.4rem; font-weight: 700; margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #888); font-size: 0.85rem; margin: 0; }
.loading-state { text-align: center; padding: 60px; color: var(--text-secondary, #888); }

.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, #e5e7eb); border-radius: 10px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; padding: 14px 20px; border-bottom: 1px solid var(--border, #e5e7eb); font-weight: 600; font-size: 0.9rem; }
.panel-hint { font-size: 0.75rem; color: var(--text-secondary, #94a3b8); font-weight: 400; }
.panel-body { padding: 16px 20px; }
.empty-state { text-align: center; padding: 40px 20px; color: var(--text-secondary, #94a3b8); font-size: 0.85rem; }

.ch-card { background: #fafbfc; border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px 16px; margin-bottom: 12px; }
.ch-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
.ch-platform { font-size: 0.85rem; font-weight: 600; padding: 3px 10px; border-radius: 6px; }
.pf-feishu { background: #fef3c7; color: #92400e; }
.pf-dingtalk { background: #dbeafe; color: #1e40af; }
.pf-wecom { background: #d1fae5; color: #065f46; }
.ch-name { font-size: 0.9rem; font-weight: 600; color: #1e293b; }
.ch-status { font-size: 0.75rem; padding: 2px 10px; border-radius: 10px; font-weight: 600; }
.ch-status.on { background: #dcfce7; color: #166534; }
.ch-status.off { background: #f1f5f9; color: #64748b; }
.ch-config { display: grid; grid-template-columns: 1.5fr 1fr 1fr; gap: 12px; margin-bottom: 10px; }
.ch-field { display: flex; flex-direction: column; gap: 4px; }
.ch-field label { font-size: 0.72rem; color: var(--text-secondary, #64748b); font-weight: 600; }
.callback-url { font-family: 'Fira Code', monospace; font-size: 0.72rem; padding: 6px 10px; background: #1e293b; color: #e2e8f0; border-radius: 4px; word-break: break-all; }
.sub-select { padding: 6px 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 0.8rem; }
.toggle-btn { padding: 6px 14px; border-radius: 6px; border: 1px solid #cbd5e1; background: #f1f5f9; cursor: pointer; font-size: 0.78rem; font-weight: 600; }
.toggle-btn.on { background: #dcfce7; color: #166534; border-color: #86efac; }
.ch-actions { display: flex; gap: 8px; }
.action-btn { padding: 5px 14px; background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 6px; cursor: pointer; font-size: 0.78rem; }
.action-btn:hover { background: #e2e8f0; }

.msg-card { background: #fafbfc; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px 14px; margin-bottom: 10px; }
.msg-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; font-size: 0.78rem; }
.msg-platform { font-size: 1rem; }
.msg-sender { font-weight: 600; color: #1e293b; }
.msg-cmd { font-family: 'Fira Code', monospace; font-size: 0.72rem; padding: 1px 8px; border-radius: 8px; background: #e0f2fe; color: #075985; }
.msg-status { font-size: 0.7rem; padding: 1px 8px; border-radius: 8px; font-weight: 600; }
.st-pending { background: #fef3c7; color: #92400e; }
.st-processing { background: #dbeafe; color: #1e40af; }
.st-replied { background: #dcfce7; color: #166534; }
.st-failed { background: #fee2e2; color: #991b1b; }
.msg-time { margin-left: auto; color: var(--text-secondary, #94a3b8); font-size: 0.7rem; }
.msg-text { font-size: 0.82rem; color: #334155; margin-bottom: 6px; }
.msg-reply { background: #f8fafc; border-left: 3px solid #6366f1; padding: 8px 12px; border-radius: 4px; }
.reply-label { font-size: 0.72rem; color: var(--text-secondary, #64748b); font-weight: 600; }
.reply-text { font-family: 'Fira Code', monospace; font-size: 0.75rem; white-space: pre-wrap; line-height: 1.5; margin: 4px 0 0; color: #1e293b; }

.cmd-list { display: flex; flex-direction: column; gap: 10px; }
.cmd-item { display: flex; gap: 16px; align-items: center; padding: 8px 0; border-bottom: 1px solid #f1f5f9; }
.cmd-item code { font-family: 'Fira Code', monospace; font-size: 0.78rem; padding: 3px 10px; background: #1e293b; color: #e2e8f0; border-radius: 4px; min-width: 180px; }
.cmd-item span { font-size: 0.82rem; color: var(--text-secondary, #64748b); }

.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal { background: #fff; border-radius: 10px; padding: 24px; min-width: 480px; max-width: 600px; }
.modal-title { font-size: 1rem; font-weight: 700; margin-bottom: 16px; }
.modal-body { display: flex; flex-direction: column; gap: 14px; }
.modal-field { display: flex; flex-direction: column; gap: 4px; }
.modal-field label { font-size: 0.78rem; font-weight: 600; color: #475569; }
.modal-field input { padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 0.85rem; font-family: 'Fira Code', monospace; }
.modal-field .hint { font-size: 0.7rem; color: var(--text-secondary, #94a3b8); }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; }
.btn-cancel { padding: 8px 18px; background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 6px; cursor: pointer; font-size: 0.85rem; }
.btn-save { padding: 8px 18px; background: #6366f1; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 0.85rem; font-weight: 600; }

@media (max-width: 900px) {
  .ch-config { grid-template-columns: 1fr; }
}
</style>
