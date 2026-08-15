<template>
  <div class="config-drift-page">
    <!-- 页头 -->
    <div class="page-header">
      <div>
        <h1>⚙️ 配置漂移检测</h1>
        <p>AI 驱动的配置基线采集 · 漂移检测 · 智能配置推荐 · 变更风险评估</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-primary" @click="openCreateBaseline">＋ 建立配置基线</button>
        <button class="btn" @click="loadAll">🔄 刷新</button>
      </div>
    </div>

    <!-- 统计卡 -->
    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-value warn">{{ stats.open_count }}</div>
        <div class="stat-label">待处理漂移</div>
      </div>
      <div class="stat-card">
        <div class="stat-value ok">{{ stats.resolved_count }}</div>
        <div class="stat-label">已解决漂移</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ stats.total_baseline }}</div>
        <div class="stat-label">配置基线</div>
      </div>
      <div class="stat-card">
        <div class="stat-value blue">{{ stats.drifted_assets }}</div>
        <div class="stat-label">受影响资产</div>
      </div>
    </div>

    <!-- Tab 切换 -->
    <div class="tab-bar">
      <div class="tab-item" :class="{ active: activeTab === 'drifts' }" @click="activeTab = 'drifts'">漂移记录</div>
      <div class="tab-item" :class="{ active: activeTab === 'baselines' }" @click="activeTab = 'baselines'">配置基线</div>
      <div class="tab-item" :class="{ active: activeTab === 'templates' }" @click="activeTab = 'templates'">采集模板</div>
    </div>

    <!-- ═══════ 漂移记录 Tab ═══════ -->
    <div v-show="activeTab === 'drifts'" class="tab-pane">
      <div class="filter-bar">
        <select v-model="filterStatus" @change="loadDrifts">
          <option value="">全部状态</option>
          <option value="open">未处理</option>
          <option value="acknowledged">已确认</option>
          <option value="resolved">已解决</option>
          <option value="ignored">已忽略</option>
        </select>
      </div>
      <div v-if="loadingDrifts" class="empty">加载中...</div>
      <div v-else-if="drifts.length === 0" class="empty">
        <div>暂无配置漂移记录</div>
        <p class="muted">建立配置基线后再执行漂移检测，系统将自动对比并生成漂移报告</p>
      </div>
      <div v-else class="drift-list">
        <div v-for="d in drifts" :key="d.id" class="drift-card" :class="'sev-' + d.severity">
          <div class="drift-main">
            <div class="drift-head">
              <span class="severity-tag" :class="'sev-' + d.severity">{{ severityLabel(d.severity) }}</span>
              <span class="status-tag" :class="'st-' + d.status">{{ statusLabel(d.status) }}</span>
              <span class="drift-key">{{ d.config_name || d.config_key }}</span>
              <span class="muted">· {{ d.asset_name }} · {{ formatTime(d.detected_at) }}</span>
            </div>
            <div class="drift-diff" v-if="d.diff_text"><pre>{{ d.diff_text }}</pre></div>
            <div class="drift-ai" v-if="hasAiAssess(d)">
              <span class="ai-label">🤖 AI 评估</span>
              <span>{{ aiSummary(d) }}</span>
            </div>
          </div>
          <div class="drift-actions">
            <button class="btn btn-sm" @click="openDetail(d)">查看评估</button>
            <button v-if="d.status === 'open' || d.status === 'acknowledged'" class="btn btn-sm btn-ok" @click="setStatus(d, 'resolved')">✔ 解决</button>
            <button v-if="d.status === 'open'" class="btn btn-sm" @click="setStatus(d, 'ignored')">忽略</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══════ 配置基线 Tab ═══════ -->
    <div v-show="activeTab === 'baselines'" class="tab-pane">
      <div v-if="loadingBaselines" class="empty">加载中...</div>
      <div v-else-if="baselines.length === 0" class="empty">
        <div>暂无配置基线</div>
        <p class="muted">点击右上角「＋ 建立配置基线」为目标资产采集第一个基线快照</p>
      </div>
      <div v-else class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>资产</th><th>配置项</th><th>分类</th><th>版本</th><th>基线时间</th><th>Hash</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="b in baselines" :key="b.id">
              <td>{{ assetName(b.asset_id) }}</td>
              <td>{{ b.config_name || b.config_key }}</td>
              <td><span class="cat-tag">{{ b.category }}</span></td>
              <td>v{{ b.version }}</td>
              <td>{{ formatTime(b.baseline_at) }}</td>
              <td class="mono">{{ (b.content_hash || '').slice(0, 10) }}…</td>
              <td>
                <button class="btn btn-sm" @click="detectDriftNow(b)">🔍 检测漂移</button>
                <button class="btn btn-sm btn-danger" @click="deleteBaseline(b)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ═══════ 采集模板 Tab ═══════ -->
    <div v-show="activeTab === 'templates'" class="tab-pane">
      <div class="tpl-hint">内置配置采集模板，按资产类型匹配自动采集常用配置项，可在「建立基线」时选用。</div>
      <div v-if="templates.length === 0" class="empty">暂无模板</div>
      <div v-else class="tpl-grid">
        <div v-for="t in templates" :key="t.key" class="tpl-card">
          <div class="tpl-head">
            <span class="cat-tag">{{ t.category }}</span>
            <span class="muted">{{ t.ci_type }}</span>
          </div>
          <div class="tpl-name">{{ t.name }}</div>
          <div class="mono tpl-cmd">{{ t.command }}</div>
          <button class="btn btn-sm" @click="openCreateFromTemplate(t)">用此模板建基线</button>
        </div>
      </div>
    </div>

    <!-- ═══════ 漂移详情抽屉 ═══════ -->
    <div v-if="currentDrift" class="modal-mask">
      <div class="modal">
        <div class="modal-head">
          <h3>🤖 AI 漂移评估 · {{ currentDrift.asset_name }}</h3>
          <button class="modal-close" @click="currentDrift = null">✕</button>
        </div>
        <div class="modal-body">
          <div class="detail-meta">
            <span class="severity-tag" :class="'sev-' + currentDrift.severity">{{ severityLabel(currentDrift.severity) }}</span>
            <span class="status-tag" :class="'st-' + currentDrift.status">{{ statusLabel(currentDrift.status) }}</span>
            <span class="muted">{{ currentDrift.config_name || currentDrift.config_key }} · {{ formatTime(currentDrift.detected_at) }}</span>
          </div>
          <div v-if="hasAiAssess(currentDrift)" class="ai-block">
            <h4>📊 AI 配置漂移分析</h4>
            <div class="ai-row"><label>根因</label><span>{{ aiField(currentDrift, 'root_cause') }}</span></div>
            <div class="ai-row"><label>影响</label><span>{{ aiField(currentDrift, 'impact') }}</span></div>
            <div class="ai-row"><label>建议修正方案</label><span class="reco">{{ aiField(currentDrift, 'recommendation') }}</span></div>
            <div class="ai-row"><label>变更风险评估</label><span>{{ aiField(currentDrift, 'risk') }}</span></div>
            <div class="ai-row"><label>处置建议</label><span>{{ aiAction(currentDrift) }}</span></div>
          </div>
          <div class="diff-block">
            <h4>📝 配置差异</h4>
            <pre>{{ currentDrift.diff_text || '（无差异详情）' }}</pre>
          </div>
          <div class="diff-block">
            <h4>🔽 当前配置</h4>
            <pre>{{ currentDrift.current_content || '（无）' }}</pre>
          </div>
        </div>
        <div class="modal-foot">
          <button class="btn" @click="currentDrift = null">关闭</button>
          <button class="btn btn-ok" @click="setStatus(currentDrift, 'resolved'); currentDrift = null">✔ 标记解决</button>
        </div>
      </div>
    </div>

    <!-- ═══════ 建立基线弹窗 ═══════ -->
    <div v-if="showCreate" class="modal-mask">
      <div class="modal">
        <div class="modal-head">
          <h3>＋ 建立配置基线</h3>
          <button class="modal-close" @click="showCreate = false">✕</button>
        </div>
        <div class="modal-body form">
          <div class="field">
            <label>目标资产 *</label>
            <select v-model="form.asset_id" @change="onAssetSelect">
              <option :value="0">请选择资产</option>
              <option v-for="a in assets" :key="a.id" :value="a.id">{{ a.name }} ({{ a.ip }})</option>
            </select>
          </div>
          <div class="field">
            <label>配置项 Key *</label>
            <input v-model="form.config_key" placeholder="如 nginx.conf / sysctl.conf / my.cnf" />
          </div>
          <div class="field">
            <label>配置项名称</label>
            <input v-model="form.config_name" placeholder="配置显示名（可选）" />
          </div>
          <div class="field">
            <label>分类</label>
            <select v-model="form.category">
              <option value="system">system</option>
              <option value="nginx">nginx</option>
              <option value="redis">redis</option>
              <option value="mysql">mysql</option>
              <option value="k8s">k8s</option>
              <option value="custom">custom</option>
            </select>
          </div>
          <div class="field">
            <label>采集命令（SSH）</label>
            <input v-model="form.source_command" placeholder="如 cat /etc/nginx/nginx.conf" />
            <p class="hint">留空时若配置项匹配内置模板将自动使用默认命令</p>
          </div>
        </div>
        <div class="modal-foot">
          <button class="btn" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" :disabled="!form.asset_id || !form.config_key" @click="createBaseline">保存基线</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const API = '/config-drift/api'
const ASSET_API = '/assets/api'

const activeTab = ref('drifts')
const stats = ref({ open_count: 0, resolved_count: 0, total_baseline: 0, drifted_assets: 0 })
const drifts = ref([])
const baselines = ref([])
const templates = ref([])
const assets = ref([])
const filterStatus = ref('')
const loadingDrifts = ref(false)
const loadingBaselines = ref(false)
const currentDrift = ref(null)
const showCreate = ref(false)
const form = ref({ asset_id: 0, config_key: '', config_name: '', category: 'custom', source_command: '' })

const assetMap = ref({})

function severityLabel(s) {
  return { low: '低', medium: '中', high: '高', critical: '严重' }[s] || s || '中'
}
function statusLabel(s) {
  return { open: '未处理', acknowledged: '已确认', resolved: '已解决', ignored: '已忽略' }[s] || s || ''
}
function formatTime(ts) {
  if (!ts) return '-'
  const d = new Date(ts)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function assetName(id) {
  const a = assetMap.value[id]
  return a ? `${a.name} (${a.ip})` : `资产#${id}`
}
function hasAiAssess(d) {
  try {
    return d && d.ai_assessment && JSON.parse(d.ai_assessment).summary
  } catch (e) { return false }
}
function parseAi(d) {
  try { return JSON.parse(d.ai_assessment) } catch (e) { return {} }
}
function aiSummary(d) { return parseAi(d).summary || '' }
function aiField(d, k) { return parseAi(d)[k] || '-' }
function aiAction(d) {
  const a = parseAi(d)
  return { apply: '建议应用修正', review: '建议人工复核', ignore: '建议忽略' }[a.change_action] || a.change_action || '-'
}

async function loadStats() {
  try { const { data } = await axios.get(`${API}/stats`); stats.value = data } catch (e) {}
}
async function loadAssets() {
  try {
    const { data } = await axios.get(`${ASSET_API}/list`, { params: { page_size: 500 } })
    const items = data.items || data.assets || data.list || []
    assetMap.value = {}
    items.forEach((a) => { assetMap.value[a.id] = a })
    assets.value = items
  } catch (e) {}
}
async function loadDrifts() {
  loadingDrifts.value = true
  try {
    const { data } = await axios.get(`${API}/drifts`, { params: { status: filterStatus.value } })
    drifts.value = data.items || []
  } finally { loadingDrifts.value = false }
}
async function loadBaselines() {
  loadingBaselines.value = true
  try {
    const { data } = await axios.get(`${API}/baselines`)
    baselines.value = data.items || []
  } finally { loadingBaselines.value = false }
}
async function loadTemplates() {
  try { const { data } = await axios.get(`${API}/templates`); templates.value = data.items || [] } catch (e) {}
}
function loadAll() {
  loadStats(); loadDrifts(); loadBaselines(); loadTemplates()
}

function openDetail(d) { currentDrift.value = d }
async function setStatus(d, status) {
  try {
    await axios.post(`${API}/drifts/${d.id}/status`, { status })
    loadAll()
  } catch (e) { alert('操作失败') }
}
async function detectDriftNow(b) {
  if (!confirm(`对资产「${assetName(b.asset_id)}」的「${b.config_name || b.config_key}」执行漂移检测？`)) return
  try {
    const { data } = await axios.post(`${API}/detect`, { asset_id: b.asset_id, config_key: b.config_key })
    if (data.ok && data.result) {
      alert(data.result.drifted ? `⚠️ 检测到 ${data.result.drift_count || 1} 处漂移` : '✅ 配置与基线一致，无漂移')
    } else { alert(data.error || '检测失败') }
    loadAll()
  } catch (e) { alert('检测失败') }
}
async function deleteBaseline(b) {
  if (!confirm(`删除基线「${b.config_name || b.config_key}」？`)) return
  try { await axios.delete(`${API}/baselines/${b.id}`); loadBaselines() } catch (e) { alert('删除失败') }
}
function openCreateBaseline() {
  form.value = { asset_id: 0, config_key: '', config_name: '', category: 'custom', source_command: '' }
  showCreate.value = true
}
function openCreateFromTemplate(t) {
  form.value = { asset_id: 0, config_key: t.key, config_name: t.name, category: t.category, source_command: t.command }
  showCreate.value = true
}
function onAssetSelect() {
  const a = assetMap.value[form.value.asset_id]
  // 保留用户输入，仅提示默认分类
}
async function createBaseline() {
  try {
    const { data } = await axios.post(`${API}/baselines`, {
      asset_id: form.value.asset_id,
      config_key: form.value.config_key,
      config_name: form.value.config_name,
      category: form.value.category,
      source_command: form.value.source_command,
    })
    if (data.ok) {
      alert('✅ 基线已建立')
      showCreate.value = false
      loadAll()
    } else {
      alert('建立失败: ' + (data.error || ''))
    }
  } catch (e) { alert('建立失败') }
}

onMounted(() => { loadAssets(); loadAll() })
</script>

<style scoped>
.config-drift-page { padding: 20px; color: var(--text, #1f2937); }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
.page-header h1 { font-size: 22px; margin: 0 0 4px; }
.page-header p { margin: 0; color: var(--text-muted, #6b7280); font-size: 13px; }
.header-actions { display: flex; gap: 8px; }

.stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 20px; }
.stat-card { background: var(--card-bg, #fff); border: 1px solid var(--border-color, #e5e7eb); border-radius: 10px; padding: 16px; text-align: center; }
.stat-value { font-size: 28px; font-weight: 700; }
.stat-value.warn { color: #f59e0b; } .stat-value.ok { color: #10b981; } .stat-value.blue { color: #3b82f6; }
.stat-label { font-size: 12px; color: var(--text-muted, #6b7280); margin-top: 4px; }

.tab-bar { display: flex; gap: 0; border-bottom: 2px solid var(--border-color, #e5e7eb); margin-bottom: 16px; }
.tab-item { padding: 10px 18px; cursor: pointer; font-size: 14px; color: var(--text-muted, #6b7280); border-bottom: 2px solid transparent; margin-bottom: -2px; }
.tab-item.active { color: #3b82f6; border-bottom-color: #3b82f6; font-weight: 600; }
.tab-pane { margin-top: 4px; }

.filter-bar { margin-bottom: 12px; }
.filter-bar select { padding: 6px 10px; border: 1px solid var(--border-color, #d1d5db); border-radius: 6px; }

.empty { text-align: center; padding: 50px 20px; color: var(--text-muted, #6b7280); font-size: 14px; }
.muted { color: var(--text-muted, #9ca3af); font-size: 12px; margin-top: 6px; }

.drift-list { display: flex; flex-direction: column; gap: 12px; }
.drift-card { background: var(--card-bg, #fff); border: 1px solid var(--border-color, #e5e7eb); border-left: 4px solid #d1d5db; border-radius: 8px; padding: 14px 16px; display: flex; justify-content: space-between; gap: 12px; }
.drift-card.sev-low { border-left-color: #22c55e; } .drift-card.sev-medium { border-left-color: #f59e0b; }
.drift-card.sev-high { border-left-color: #f97316; } .drift-card.sev-critical { border-left-color: #ef4444; }
.drift-main { flex: 1; min-width: 0; }
.drift-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.drift-key { font-weight: 600; font-size: 14px; }
.drift-diff pre { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 10px; font-size: 12px; max-height: 120px; overflow: auto; margin: 0 0 8px; }
.drift-ai { font-size: 13px; background: #eff6ff; border-radius: 6px; padding: 8px 10px; }
.ai-label { font-weight: 600; color: #3b82f6; margin-right: 6px; }
.drift-actions { display: flex; flex-direction: column; gap: 6px; justify-content: flex-start; }

.severity-tag { padding: 2px 8px; border-radius: 10px; font-size: 12px; font-weight: 600; color: #fff; }
.severity-tag.sev-low { background: #22c55e; } .severity-tag.sev-medium { background: #f59e0b; }
.severity-tag.sev-high { background: #f97316; } .severity-tag.sev-critical { background: #ef4444; }
.status-tag { padding: 2px 8px; border-radius: 10px; font-size: 12px; background: #e5e7eb; color: #374151; }
.status-tag.st-resolved { background: #d1fae5; color: #065f46; }
.status-tag.st-ignored { background: #f3f4f6; color: #9ca3af; }
.cat-tag { padding: 2px 8px; border-radius: 10px; font-size: 12px; background: #ede9fe; color: #6d28d9; }

.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table th, .table td { border-bottom: 1px solid var(--border-color, #e5e7eb); padding: 10px 12px; text-align: left; }
.table th { background: #f9fafb; font-weight: 600; }
.mono { font-family: monospace; font-size: 12px; }

.tpl-hint { background: #eff6ff; border-radius: 8px; padding: 10px 14px; font-size: 13px; margin-bottom: 14px; color: #1e40af; }
.tpl-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
.tpl-card { background: var(--card-bg, #fff); border: 1px solid var(--border-color, #e5e7eb); border-radius: 8px; padding: 14px; }
.tpl-head { display: flex; justify-content: space-between; margin-bottom: 8px; }
.tpl-name { font-weight: 600; margin-bottom: 8px; }
.tpl-cmd { background: #f8fafc; border-radius: 6px; padding: 6px 8px; margin-bottom: 10px; font-size: 11px; overflow-wrap: anywhere; }

.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal { background: #fff; border-radius: 12px; width: 680px; max-width: 94vw; max-height: 88vh; display: flex; flex-direction: column; box-shadow: 0 20px 50px rgba(0,0,0,.25); }
.modal-head { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid #e5e7eb; }
.modal-head h3 { margin: 0; font-size: 16px; }
.modal-close { background: none; border: none; font-size: 18px; cursor: pointer; color: #6b7280; }
.modal-body { padding: 18px 20px; overflow-y: auto; flex: 1; }
.modal-foot { display: flex; justify-content: flex-end; gap: 10px; padding: 14px 20px; border-top: 1px solid #e5e7eb; }
.detail-meta { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }
.ai-block { background: #eff6ff; border-radius: 8px; padding: 14px; margin-bottom: 14px; }
.ai-block h4, .diff-block h4 { margin: 0 0 10px; font-size: 14px; }
.ai-row { display: flex; gap: 10px; margin-bottom: 8px; font-size: 13px; }
.ai-row label { flex-shrink: 0; width: 110px; color: #6b7280; font-weight: 600; }
.ai-row .reco { background: #dbeafe; border-radius: 4px; padding: 2px 6px; }
.diff-block { background: #f8fafc; border-radius: 8px; padding: 14px; margin-bottom: 14px; }
.diff-block pre { margin: 0; font-size: 12px; max-height: 220px; overflow: auto; white-space: pre-wrap; }

.form .field { margin-bottom: 14px; }
.form label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 6px; color: #374151; }
.form input, .form select { width: 100%; padding: 8px 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px; box-sizing: border-box; }
.hint { font-size: 12px; color: #9ca3af; margin-top: 4px; }
.btn { padding: 8px 14px; border: 1px solid #d1d5db; background: #fff; border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn-primary { background: #3b82f6; color: #fff; border-color: #3b82f6; }
.btn-ok { background: #10b981; color: #fff; border-color: #10b981; }
.btn-danger { color: #ef4444; border-color: #fecaca; }
.btn-sm { padding: 5px 10px; font-size: 12px; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
</style>
