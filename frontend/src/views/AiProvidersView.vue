<template>
  <div class="ai-page">
    <div class="page-header">
      <h1>智能体配置</h1>
      <p>LLM 提供商与 Agent 配置 · {{ providers.length }} 个提供商 / {{ configs.length }} 个配置</p>
    </div>

    <div class="panel">
      <div class="panel-head">
        <span>模型提供商</span>
        <div class="panel-actions">
          <button class="btn btn-sm" @click="loadHealth" :disabled="healthLoading">刷新健康度</button>
          <button class="btn btn-sm" @click="resetAllBreakers" v-if="health.opened_count > 0">全部重置熔断 ({{ health.opened_count }})</button>
          <button class="btn btn-primary btn-sm" @click="openProviderDialog()">+ 新增提供商</button>
        </div>
      </div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="providers.length" class="table">
          <thead><tr><th>ID</th><th>名称</th><th>Base URL</th><th>默认模型</th><th>温度</th><th>API Key</th><th>状态</th><th>健康度</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="p in providers" :key="p.id">
              <td>{{ p.id }}</td>
              <td>{{ p.name }}</td>
              <td class="text-sm">{{ p.base_url || '-' }}</td>
              <td class="text-sm">{{ p.default_model || '-' }}</td>
              <td>{{ p.temperature }}</td>
              <td><span class="badge" :class="p.has_api_key ? 'on' : 'off'">{{ p.has_api_key ? '已配置' : '未配置' }}</span></td>
              <td><span class="badge" :class="p.is_enabled ? 'on' : 'off'">{{ p.is_enabled ? '启用' : '禁用' }}</span></td>
              <td>
                <span class="badge" :class="healthBadgeClass(p.id)" :title="healthTooltip(p.id)">
                  {{ healthBadgeText(p.id) }}
                </span>
                <span class="text-sm" style="margin-left:6px;">{{ healthStats(p.id) }}</span>
              </td>
              <td>
                <button class="btn btn-sm" @click="openProviderDialog(p)">编辑</button>
                <button class="btn btn-sm" @click="testProvider(p)" :disabled="testing === p.id">{{ testing === p.id ? '测试中...' : '测试' }}</button>
                <button class="btn btn-sm" @click="toggleProvider(p)">{{ p.is_enabled ? '禁用' : '启用' }}</button>
                <button class="btn btn-sm" @click="resetBreaker(p)" v-if="getHealth(p.id) && getHealth(p.id).state !== 'closed'">重置熔断</button>
                <button class="btn btn-sm btn-danger" @click="deleteProvider(p)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">暂无提供商</div>
      </div>
    </div>

    <div class="panel" style="margin-top:14px;">
      <div class="panel-head">
        <span>Agent 配置</span>
        <button class="btn btn-primary btn-sm" @click="openConfigDialog()">+ 新增配置</button>
      </div>
      <div class="panel-body">
        <table v-if="configs.length" class="table">
          <thead><tr><th>ID</th><th>名称</th><th>默认提供商</th><th>允许执行</th><th>需确认</th><th>历史消息</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="c in configs" :key="c.id">
              <td>{{ c.id }}</td>
              <td>{{ c.name }}</td>
              <td class="text-sm">{{ providerName(c.default_provider_id) }}</td>
              <td><span class="badge" :class="c.allow_action_execution ? 'on' : 'off'">{{ c.allow_action_execution ? '是' : '否' }}</span></td>
              <td><span class="badge" :class="c.require_confirmation ? 'on' : 'off'">{{ c.require_confirmation ? '是' : '否' }}</span></td>
              <td>{{ c.max_history_messages }}</td>
              <td><button class="btn btn-sm" @click="openConfigDialog(c)">编辑</button></td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">暂无 Agent 配置</div>
      </div>
    </div>

    <div class="panel" style="margin-top:14px;">
      <div class="panel-head">
        <span>语音服务 (STT 识别 / TTS 合成)</span>
        <div class="panel-actions">
          <span v-if="vResolved" class="text-sm" style="color:var(--text-secondary,#64748b)">
            当前生效: 识别「{{ vResolved.stt?.name || vResolved.stt?.engine || '本地' }}」 · 合成「{{ vResolved.tts?.name || vResolved.tts?.engine || 'edge-tts' }}」
          </span>
          <button class="btn btn-sm" @click="loadVoice">刷新</button>
          <button class="btn btn-primary btn-sm" @click="openVoiceDialog()">+ 新增语音配置</button>
        </div>
      </div>
      <div class="panel-body">
        <div v-if="voiceLoading" class="loading-state">加载中...</div>
        <table v-else-if="voices.length" class="table">
          <thead><tr><th>名称</th><th>引擎</th><th>类型</th><th>AccessKeyId</th><th>密钥</th><th>区域</th><th>优先级</th><th>状态</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="v in voices" :key="v.id">
              <td>{{ v.name }}</td>
              <td>{{ engineLabel(v.engine) }}</td>
              <td>{{ typeLabel(v.engine_type) }}</td>
              <td class="text-sm">{{ v.access_key_id || '-' }}</td>
              <td><span class="badge" :class="v.has_access_key ? 'on' : 'off'">{{ v.has_access_key ? '已配置' : '未配置' }}</span></td>
              <td class="text-sm">{{ v.region || '-' }}</td>
              <td>{{ v.priority }}</td>
              <td><span class="badge" :class="v.is_enabled ? 'on' : 'off'">{{ v.is_enabled ? '启用' : '禁用' }}</span></td>
              <td>
                <button class="btn btn-sm" @click="openVoiceDialog(v)">编辑</button>
                <button class="btn btn-sm" @click="testVoice(v)" :disabled="voiceTesting === v.id">{{ voiceTesting === v.id ? '测试中...' : '测试' }}</button>
                <button class="btn btn-sm" @click="toggleVoice(v)">{{ v.is_enabled ? '禁用' : '启用' }}</button>
                <button class="btn btn-sm btn-danger" @click="deleteVoice(v)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">暂无语音配置（STT 未配置、TTS 使用 edge-tts）</div>
        <p class="text-sm" style="margin-top:10px;color:var(--text-tertiary,#94a3b8)">
          支持引擎: 阿里云(纯HTTP推荐) / 百度(永久免费量大) / 腾讯(需 tencentcloud-sdk-python) / edge-tts(微软免费)。配置后主脑与移动端语音自动使用；STT 云端失败返回空，TTS 云端失败自动回退 edge-tts。
        </p>
      </div>
    </div>

    <div v-if="showProviderDialog" class="modal-overlay" @click.self="showProviderDialog = false">
      <div class="modal-box">
        <h3>{{ editingProvider ? '编辑提供商' : '新增提供商' }}</h3>
        <div class="form-row"><label>名称</label><input v-model="pForm.name" class="input"></div>
        <div class="form-row"><label>Base URL</label><input v-model="pForm.base_url" class="input" placeholder="https://api.minimax.chat/v1"></div>
        <div class="form-row"><label>默认模型</label><input v-model="pForm.default_model" class="input"></div>
        <div class="form-row"><label>API Key {{ editingProvider ? '(留空不修改)' : '' }}</label><input v-model="pForm.api_key" type="password" class="input"></div>
        <div class="grid-3">
          <div class="form-row"><label>温度</label><input v-model.number="pForm.temperature" type="number" step="0.1" class="input"></div>
          <div class="form-row"><label>最大 Tokens</label><input v-model.number="pForm.max_tokens" type="number" class="input"></div>
          <div class="form-row"><label>超时(秒)</label><input v-model.number="pForm.timeout_seconds" type="number" class="input"></div>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showProviderDialog = false">取消</button>
          <button class="btn btn-primary" @click="saveProvider">保存</button>
        </div>
      </div>
    </div>

    <div v-if="showConfigDialog" class="modal-overlay" @click.self="showConfigDialog = false">
      <div class="modal-box modal-lg">
        <h3>{{ editingConfig ? '编辑配置' : '新增配置' }}</h3>
        <div class="form-row"><label>名称</label><input v-model="cForm.name" class="input"></div>
        <div class="form-row"><label>默认提供商</label>
          <select v-model="cForm.default_provider_id" class="input">
            <option :value="0">无</option>
            <option v-for="p in enabledProviders" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </div>
        <div class="form-row"><label>系统提示词</label><textarea v-model="cForm.system_prompt" class="input textarea"></textarea></div>
        <div class="form-row"><label>欢迎语</label><input v-model="cForm.welcome_message" class="input"></div>
        <div class="form-row"><label>建议问题 (JSON)</label><textarea v-model="cForm.suggested_questions" class="input textarea"></textarea></div>
        <div class="grid-3">
          <div class="form-row"><label>允许执行</label><input type="checkbox" v-model="cForm.allow_action_execution"></div>
          <div class="form-row"><label>需要确认</label><input type="checkbox" v-model="cForm.require_confirmation"></div>
          <div class="form-row"><label>历史消息数</label><input v-model.number="cForm.max_history_messages" type="number" class="input"></div>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showConfigDialog = false">取消</button>
          <button class="btn btn-primary" @click="saveConfig">保存</button>
        </div>
      </div>
    </div>

    <div v-if="showVoiceDialog" class="modal-overlay" @click.self="showVoiceDialog = false">
      <div class="modal-box modal-lg">
        <h3>{{ editingVoice ? '编辑语音配置' : '新增语音配置' }}</h3>
        <div class="form-row"><label>名称</label><input v-model="vForm.name" class="input" placeholder="如: 阿里云语音"></div>
        <div class="grid-2">
          <div class="form-row"><label>引擎</label>
            <select v-model="vForm.engine" class="input">
              <option value="aliyun">阿里云 (NLS)</option>
              <option value="baidu">百度智能云</option>
              <option value="tencent">腾讯云</option>
              <option value="edge-tts">edge-tts (微软免费, 仅TTS)</option>
            </select>
          </div>
          <div class="form-row"><label>类型</label>
            <select v-model="vForm.engine_type" class="input">
              <option value="both">STT + TTS</option>
              <option value="stt">仅识别 (STT)</option>
              <option value="tts">仅合成 (TTS)</option>
            </select>
          </div>
        </div>
        <div class="grid-2">
          <div class="form-row"><label>AppKey / AppID / 应用ID</label><input v-model="vForm.app_id" class="input" placeholder="阿里填 AppKey; 百度/腾讯填 AppID(可空)"></div>
          <div class="form-row"><label>AccessKeyId / API Key</label><input v-model="vForm.access_key_id" class="input" placeholder="云账号 AccessKeyId 或 API Key"></div>
        </div>
        <div class="form-row"><label>AccessKey Secret / SecretKey {{ editingVoice ? '(留空不修改)' : '' }}</label><input v-model="vForm.access_key_secret" type="password" class="input" placeholder="加密存储, 仅显示是否已配置"></div>
        <div class="grid-3">
          <div class="form-row"><label>区域 Region</label><input v-model="vForm.region" class="input" placeholder="如 cn-shanghai / ap-beijing"></div>
          <div class="form-row"><label>STT 模型 / dev_pid</label><input v-model="vForm.stt_model" class="input" placeholder="如 16k_zh / 1537"></div>
          <div class="form-row"><label>TTS 音色</label><input v-model="vForm.tts_voice" class="input" placeholder="如 xiaoyun / 0"></div>
        </div>
        <div class="grid-3">
          <div class="form-row"><label>Base URL (可选)</label><input v-model="vForm.base_url" class="input" placeholder="默认用官方地址"></div>
          <div class="form-row"><label>优先级(小优先)</label><input v-model.number="vForm.priority" type="number" class="input"></div>
          <div class="form-row"><label>启用</label><input type="checkbox" v-model="vForm.is_enabled"></div>
        </div>
        <div class="form-row"><label>扩展参数 JSON (速率/音量等, 可选)</label><textarea v-model="vForm.extra_json" class="input textarea" placeholder='{}'></textarea></div>
        <div class="modal-actions">
          <button class="btn" @click="showVoiceDialog = false">取消</button>
          <button class="btn btn-primary" @click="saveVoice">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const providers = ref([])
const configs = ref([])
const testing = ref(0)
const showProviderDialog = ref(false)
const showConfigDialog = ref(false)
const editingProvider = ref(null)
const editingConfig = ref(null)
const pForm = ref({ name: '', base_url: '', default_model: '', api_key: '', temperature: 0.2, max_tokens: 10000, timeout_seconds: 30 })
const cForm = ref({ name: 'default', default_provider_id: 0, system_prompt: '', welcome_message: '', suggested_questions: '[]', allow_action_execution: false, require_confirmation: true, max_history_messages: 12 })

// 语音服务(STT/TTS)配置
const voices = ref([])
const voiceLoading = ref(false)
const showVoiceDialog = ref(false)
const editingVoice = ref(null)
const vForm = ref({ name: '', engine: 'aliyun', engine_type: 'both', app_id: '', access_key_id: '', access_key_secret: '', region: '', stt_model: '', tts_voice: '', base_url: '', extra_json: '{}', priority: 10, is_enabled: true })
const voiceTesting = ref(0)
const vResolved = ref(null)

// P1 任务#5: AI Provider 健康度 + 熔断器
const health = ref({ providers: [], total: 0, opened_count: 0, half_open_count: 0, closed_count: 0 })
const healthLoading = ref(false)

const enabledProviders = computed(() => providers.value.filter(p => p.is_enabled))

function providerName(id) {
  const p = providers.value.find(x => x.id === id)
  return p ? p.name : '无'
}

function getHealth(providerId) {
  const item = health.value.providers.find(x => x.id === providerId)
  return item ? item.health : null
}

function healthBadgeClass(providerId) {
  const h = getHealth(providerId)
  if (!h) return 'off'
  if (h.state === 'open') return 'danger'
  if (h.state === 'half_open') return 'warn'
  return 'on'
}

function healthBadgeText(providerId) {
  const h = getHealth(providerId)
  if (!h) return '未监控'
  if (h.state === 'open') return `熔断 ${h.open_remaining_sec}s`
  if (h.state === 'half_open') return '半开试探'
  return '正常'
}

function healthStats(providerId) {
  const h = getHealth(providerId)
  if (!h || h.total_calls === 0) return '无调用'
  return `成功率 ${(h.success_rate * 100).toFixed(0)}% · P95 ${h.p95_latency_ms}ms · ${h.total_calls}次`
}

function healthTooltip(providerId) {
  const h = getHealth(providerId)
  if (!h) return '尚未调用'
  return `状态: ${h.state}\n成功率: ${(h.success_rate * 100).toFixed(1)}%\nP95: ${h.p95_latency_ms}ms\n总调用: ${h.total_calls}\n最近错误: ${h.last_error || '无'}`
}

async function loadHealth() {
  healthLoading.value = true
  try {
    const data = await request.get('/ai/api/providers/health')
    if (data.providers) {
      health.value = {
        providers: data.providers,
        total: data.total || 0,
        opened_count: data.opened_count || 0,
        half_open_count: data.half_open_count || 0,
        closed_count: data.closed_count || 0,
      }
    } else if (data.warning) {
      // 静默处理：未登录或异常
    }
  } catch (e) {
    // 静默失败，不打扰用户
    console.error('load health:', e)
  } finally {
    healthLoading.value = false
  }
}

async function resetBreaker(p) {
  try {
    await request.post(`/ai/api/providers/${p.id}/reset-breaker`)
    ElMessage.success(`已重置「${p.name}」熔断器`)
    loadHealth()
  } catch (e) {
    ElMessage.error('重置失败: ' + (e.message || e))
  }
}

async function resetAllBreakers() {
  try {
    await ElMessageBox.confirm(`确认重置所有已熔断的 provider（${health.value.opened_count} 个）？`, '重置确认', { type: 'warning' })
    await request.post('/ai/api/providers/reset-all-breakers')
    ElMessage.success('所有熔断器已重置')
    loadHealth()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('重置失败: ' + (e.message || e))
  }
}

async function load() {
  loading.value = true
  try {
    const data = await request.get('/ai/api/providers')
    providers.value = data.providers || []
    configs.value = data.configs || []
    // 同步加载健康度（非阻塞，失败不影响主流程）
    loadHealth()
  } catch (e) {
    ElMessage.error('加载失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function openProviderDialog(p = null) {
  editingProvider.value = p
  if (p) {
    pForm.value = { name: p.name, base_url: p.base_url, default_model: p.default_model, api_key: '', temperature: p.temperature, max_tokens: p.max_tokens, timeout_seconds: p.timeout_seconds }
  } else {
    pForm.value = { name: '', base_url: '', default_model: '', api_key: '', temperature: 0.2, max_tokens: 10000, timeout_seconds: 30 }
  }
  showProviderDialog.value = true
}

async function saveProvider() {
  if (!pForm.value.name) { ElMessage.warning('名称不能为空'); return }
  try {
    if (editingProvider.value) {
      await request.put(`/ai/api/providers/${editingProvider.value.id}/edit`, pForm.value)
    } else {
      await request.post('/ai/api/providers/create', pForm.value)
    }
    ElMessage.success('保存成功')
    showProviderDialog.value = false
    load()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.message || e))
  }
}

async function testProvider(p) {
  testing.value = p.id
  try {
    const data = await request.post(`/ai/providers/${p.id}/test`)
    if (data.status === 'success') ElMessage.success(data.message || '连接成功')
    else ElMessage.error(data.message || '连接失败')
  } catch (e) {
    ElMessage.error('测试失败: ' + (e.message || e))
  } finally {
    testing.value = 0
  }
}

async function toggleProvider(p) {
  try {
    await request.post(`/ai/api/providers/${p.id}/toggle`)
    load()
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.message || e))
  }
}

async function deleteProvider(p) {
  try {
    await ElMessageBox.confirm(`确认删除提供商「${p.name}」？`, '删除确认', { type: 'warning' })
    await request.delete(`/ai/api/providers/${p.id}/delete`)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

function openConfigDialog(c = null) {
  editingConfig.value = c
  if (c) {
    cForm.value = { name: c.name, default_provider_id: c.default_provider_id || 0, system_prompt: c.system_prompt || '', welcome_message: c.welcome_message || '', suggested_questions: c.suggested_questions || '[]', allow_action_execution: !!c.allow_action_execution, require_confirmation: !!c.require_confirmation, max_history_messages: c.max_history_messages || 12 }
  } else {
    cForm.value = { name: 'default', default_provider_id: 0, system_prompt: '', welcome_message: '', suggested_questions: '[]', allow_action_execution: false, require_confirmation: true, max_history_messages: 12 }
  }
  showConfigDialog.value = true
}

async function saveConfig() {
  try {
    if (editingConfig.value) {
      await request.put(`/ai/api/configs/${editingConfig.value.id}/edit`, cForm.value)
    } else {
      await request.post('/ai/api/configs/create', cForm.value)
    }
    ElMessage.success('保存成功')
    showConfigDialog.value = false
    load()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.message || e))
  }
}

// ── 语音服务(STT/TTS)配置 ─────────────────────────────
async function loadVoice() {
  voiceLoading.value = true
  try {
    const data = await request.get('/ai/voice/providers')
    voices.value = data.providers || []
  } catch (e) { console.error('load voice:', e) } finally { voiceLoading.value = false }
  try {
    vResolved.value = await request.get('/ai/voice/resolved')
  } catch (e) { /* ignore */ }
}

function engineLabel(engine) {
  return { aliyun: '阿里云', baidu: '百度', tencent: '腾讯云', 'edge-tts': 'edge-tts', local: '本地' }[engine] || engine
}
function typeLabel(t) {
  return { stt: '识别', tts: '合成', both: '识别+合成' }[t] || t
}

function openVoiceDialog(v = null) {
  editingVoice.value = v
  if (v) {
    vForm.value = { name: v.name, engine: v.engine, engine_type: v.engine_type, app_id: v.app_id || '', access_key_id: v.access_key_id || '', access_key_secret: '', region: v.region || '', stt_model: v.stt_model || '', tts_voice: v.tts_voice || '', base_url: v.base_url || '', extra_json: v.extra_json || '{}', priority: v.priority, is_enabled: !!v.is_enabled }
  } else {
    vForm.value = { name: '', engine: 'aliyun', engine_type: 'both', app_id: '', access_key_id: '', access_key_secret: '', region: '', stt_model: '', tts_voice: '', base_url: '', extra_json: '{}', priority: 10, is_enabled: true }
  }
  showVoiceDialog.value = true
}

function _validExtra() {
  const s = (vForm.value.extra_json || '').trim()
  if (!s) return '{}'
  try { JSON.parse(s); return s } catch (e) { return null }
}

async function saveVoice() {
  if (!vForm.value.name) { ElMessage.warning('名称不能为空'); return }
  const extra = _validExtra()
  if (extra === null) { ElMessage.warning('扩展参数 JSON 格式错误'); return }
  const payload = { ...vForm.value, extra_json: extra, priority: parseInt(vForm.value.priority || 10) }
  try {
    if (editingVoice.value) {
      await request.put(`/ai/voice/providers/${editingVoice.value.id}/edit`, payload)
    } else {
      await request.post('/ai/voice/providers/create', payload)
    }
    ElMessage.success('保存成功')
    showVoiceDialog.value = false
    loadVoice()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.message || e))
  }
}

async function testVoice(v) {
  voiceTesting.value = v.id
  try {
    const data = await request.post(`/ai/voice/providers/${v.id}/test`)
    const parts = []
    if (data.auth) parts.push(data.auth.msg || (data.auth.ok ? '鉴权 OK' : '鉴权失败'))
    if (data.tts) parts.push(data.tts.ok ? `TTS 合成 ${data.tts.bytes} 字节` : 'TTS 失败')
    const msg = parts.join(' · ')
    if (data.status === 'ok') ElMessage.success(msg || '测试通过')
    else ElMessage.error(msg || '测试失败')
  } catch (e) {
    ElMessage.error('测试失败: ' + (e.message || e))
  } finally {
    voiceTesting.value = 0
  }
}

async function toggleVoice(v) {
  try {
    await request.post(`/ai/voice/providers/${v.id}/toggle`)
    loadVoice()
  } catch (e) { ElMessage.error('操作失败: ' + (e.message || e)) }
}

async function deleteVoice(v) {
  try {
    await ElMessageBox.confirm(`确认删除语音配置「${v.name}」？`, '删除确认', { type: 'warning' })
    await request.delete(`/ai/voice/providers/${v.id}/delete`)
    ElMessage.success('已删除')
    loadVoice()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

onMounted(() => { load(); loadVoice() })
</script>

<style scoped>
.ai-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); display: flex; justify-content: space-between; align-items: center; }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; white-space: nowrap; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); white-space: nowrap; }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.on { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.off { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.warn { background: rgba(245,158,11,0.1); color: #f59e0b; }
.badge.danger { background: rgba(239,68,68,0.1); color: #ef4444; }
.panel-actions { display: flex; gap: 8px; align-items: center; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 420px; max-height: 86vh; overflow-y: auto; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-lg { min-width: 560px; }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; color: var(--text, #1e293b); }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.textarea { min-height: 80px; resize: vertical; font-family: inherit; }
.grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
