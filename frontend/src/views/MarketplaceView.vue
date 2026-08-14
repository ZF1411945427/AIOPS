<template>
  <div class="mp-page">
    <div class="page-header">
      <h1>🛍️ 技能市场</h1>
      <p>私服技能市场（marketplace/packages）· 从技能库发布 zip 包，或从市场安装到技能库 · 多节点间离线分发</p>
    </div>

    <!-- 远程技能源：对接 skills.sh 生态的 GitHub 仓库 -->
    <div class="remote-panel">
      <div class="panel-head">🌐 远程技能源（社区开源 · skills.sh 生态 GitHub 仓库）</div>
      <div class="remote-toolbar">
        <template v-for="pr in presets" :key="pr.owner + '/' + pr.repo">
          <button class="chip" :class="{ active: isActiveRepo(pr.owner, pr.repo) }" @click="loadRepo(pr.owner, pr.repo)">
            {{ pr.owner }}/{{ pr.repo }}
          </button>
        </template>
        <div class="custom-repo">
          <el-input v-model="customRepo" placeholder="自定义仓库 owner/repo（如 microsoft/azure-skills）" style="width:260px" clearable @keyup.enter="loadCustomRepo" />
          <span style="margin:0 4px 0 8px;color:#8b949e;font-size:12px">分支</span>
          <el-input v-model="branch" placeholder="main" style="width:90px" />
          <button class="btn btn-primary" :disabled="!customRepo || loadingRemote" @click="loadCustomRepo">加载</button>
          <button class="btn" :disabled="loadingRemote" @click="loadPresets">🔄</button>
        </div>
      </div>
      <div class="token-row">
        <span class="token-label">🔑 GitHub Token（提升 API 限额 60/时→5000/时，用于目录拉取）</span>
        <el-input v-model="tokenInput" type="password" show-password
                  :placeholder="tokenHasValue ? '已配置（***，留空=不修改）' : '未配置（留空保存=不修改）'"
                  style="width:280px" />
        <button class="btn btn-primary" :disabled="!tokenInput" @click="saveToken">保存</button>
        <button class="btn danger" v-if="tokenHasValue" @click="clearToken">清除</button>
        <span class="token-status" :class="tokenSource">{{ tokenSourceText }}</span>
      </div>
      <div class="filter-row">
        <el-switch v-model="onlyRelevant" active-text="仅看运维相关" @change="onOnlyRelevantChange" />
        <span v-if="remoteLoaded && !llmEvaluated" class="filter-hint">（未接入 LLM，暂未判断相关性，全部展示）</span>
        <span v-else-if="remoteLoaded" class="filter-hint">已由 AI 判断运维相关性 · 共 {{ remoteSkills.length }} 项</span>
      </div>
      <div v-if="remoteHint" class="remote-hint">{{ remoteHint }}</div>
      <div v-if="loadingRemote" class="remote-loading">正在拉取远程技能…</div>

      <div v-if="visibleRemoteSkills.length" class="remote-grid">
        <div v-for="sk in visibleRemoteSkills" :key="sk.name" class="pkg-card" :class="{ 'irrelevant': !sk.relevant }">
          <div class="pkg-head">
            <span class="pkg-name">{{ sk.name }}</span>
            <span class="badge">{{ sk.version || '?' }}</span>
            <span v-if="installedNames.has(sk.name)" class="tag-ok">已安装</span>
            <span v-if="!sk.fetched" class="tag-warn">元数据未抓取</span>
          </div>
          <div v-if="sk.reason" class="reason-badge" :class="sk.relevant ? 'rel' : 'notrel'">
            {{ sk.relevant ? '✅ 运维相关' : '⭕ 与运维关系不大' }}
          </div>
          <div class="pkg-desc">{{ sk.description_zh || sk.description || '（无描述）' }}</div>
          <div class="pkg-meta">
            <span>来源: {{ activeOwner }}/{{ activeRepo }}</span>
            <span v-if="sk.author">作者: {{ sk.author }}</span>
            <span v-if="sk.license">许可: {{ sk.license }}</span>
          </div>
          <div class="pkg-ops">
            <button class="btn" :disabled="loadingRemote" @click="preview(sk)">👁️ 预览</button>
            <button class="btn btn-primary" :disabled="installedNames.has(sk.name) || loadingRemote" @click="installRemote(sk)">
              ⬇️ 安装
            </button>
          </div>
        </div>
      </div>
      <div v-else-if="!loadingRemote && remoteLoaded" class="empty-state small">
        <div v-if="onlyRelevant">当前没有与 AIOps 运维相关的技能（可关闭「仅看运维相关」查看全部）。</div>
        <div v-else>该仓库 skills/ 下没有技能，或目录拉取受限（可设置 GITHUB_TOKEN 提升 API 限额）。</div>
      </div>
    </div>

    <div class="stat-row">
      <div class="stat-card"><span class="stat-num">{{ packages.length }}</span><span>市场包</span></div>
      <div class="stat-card"><span class="stat-num">{{ installedNames.size }}</span><span>本库已安装</span></div>
      <div class="stat-card"><span class="stat-num">{{ skills.length }}</span><span>本库技能</span></div>
    </div>

    <div class="toolbar">
      <div class="mp-hint">📦 私服包存放于 <code>marketplace/packages/</code>，每个包为单个 <code>SKILL.md</code>（frontmatter 即 manifest）</div>
      <button class="btn" @click="loadAll()">🔄 刷新</button>
    </div>

    <div v-if="packages.length" class="pkg-grid">
      <div v-for="p in packages" :key="p.package" class="pkg-card">
        <div class="pkg-head">
          <span class="pkg-name">{{ p.name }}</span>
          <span class="badge">{{ p.version }}</span>
          <span v-if="installedNames.has(p.name)" class="tag-ok">已安装</span>
        </div>
        <div class="pkg-desc">{{ p.description || '（无描述）' }}</div>
        <div class="pkg-meta">
          <span>分类: {{ categoryLabel(p.category) }}</span>
          <span>作者: {{ p.author || '-' }}</span>
          <span>{{ (p.size_bytes / 1024).toFixed(1) }} KB</span>
        </div>
        <div class="pkg-ops">
          <button class="btn btn-primary" :disabled="installedNames.has(p.name)" @click="install(p)">⬇️ 安装</button>
          <button class="btn danger" @click="removePkg(p)">🗑️ 删除包</button>
        </div>
      </div>
    </div>
    <div v-else class="empty-state">
      <div style="font-size:40px;margin-bottom:12px;">🛍️</div>
      <div>市场为空 —— 从技能库「发布」技能后，这里会出现可安装的技能包；也可用上方「远程技能源」直接安装社区技能</div>
    </div>

    <div v-if="skills.length" class="publish-panel">
      <div class="panel-head">📤 从技能库发布到市场</div>
      <div class="publish-row">
        <el-select v-model="publishId" placeholder="选择技能发布" style="width:300px">
          <el-option v-for="s in skills" :key="s.id" :label="`${s.name} v${s.version} (${s.source})`" :value="s.id" />
        </el-select>
        <button class="btn btn-primary" :disabled="!publishId" @click="publish()">{{ publishing ? '发布中...' : '发布到市场' }}</button>
      </div>
    </div>

    <!-- 远程技能预览弹框 -->
    <el-dialog v-model="previewVisible" :title="previewData.name ? `技能预览 · ${previewData.name}` : '技能预览'" width="720px" top="6vh">
      <div v-if="previewData.name" class="pv-meta">
        <el-tag v-if="previewData.version">{{ previewData.version }}</el-tag>
        <el-tag v-if="previewData.category" type="info">{{ previewData.category }}</el-tag>
        <el-tag v-if="previewData.risk_level" :type="riskType(previewData.risk_level)">{{ previewData.risk_level }}</el-tag>
        <el-tag v-if="previewData.author" type="warning">作者: {{ previewData.author }}</el-tag>
        <el-tag v-if="previewData.license" type="success">{{ previewData.license }}</el-tag>
        <el-tag :type="previewData.relevant === false ? 'danger' : 'success'">
          {{ previewData.relevant === false ? '与运维关系不大' : '运维相关' }}
        </el-tag>
      </div>
      <div class="pv-desc">{{ previewData.description_zh || previewData.description }}</div>
      <div class="pv-toggle" v-if="previewData.body_zh && previewData.body_zh !== previewData.body">
        <el-switch v-model="showZh" active-text="中文" inactive-text="原文" />
      </div>
      <pre class="pv-body">{{ showZh ? (previewData.body_zh || previewData.body) : previewData.body }}</pre>
      <template #footer>
        <el-button @click="previewVisible = false">关闭</el-button>
        <el-button v-if="previewData.name && !installedNames.has(previewData.name)" type="primary"
                   :loading="loadingRemote" @click="installFromPreview">安装此技能</el-button>
        <span v-else-if="previewData.name && installedNames.has(previewData.name)" class="tag-ok">已安装</span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const packages = ref([])
const skills = ref([])
const publishId = ref(null)
const publishing = ref(false)

const presets = ref([])
const customRepo = ref('')
const branch = ref('main')
const remoteSkills = ref([])
const remoteLoaded = ref(false)
const loadingRemote = ref(false)
const remoteHint = ref('')
const activeOwner = ref('')
const activeRepo = ref('')

const previewVisible = ref(false)
const previewData = ref({})

const tokenInput = ref('')
const tokenHasValue = ref(false)
const tokenSource = ref('none')

const onlyRelevant = ref(true)
const llmEvaluated = ref(false)
const showZh = ref(true)

const installedNames = computed(() => new Set(skills.value.map(s => s.name)))

const visibleRemoteSkills = computed(() => {
  if (!onlyRelevant.value) return remoteSkills.value
  return remoteSkills.value.filter(s => s.relevant !== false)
})

function categoryLabel(c) { return c || '-' }
function riskType(r) {
  return { read_only: 'info', interactive: 'warning', danger: 'danger' }[r] || 'info'
}
function isActiveRepo(o, r) { return activeOwner.value === o && activeRepo.value === r }
function onOnlyRelevantChange() { /* 纯前端过滤，无需额外逻辑 */ }

const tokenSourceText = computed(() => {
  if (!tokenHasValue.value) return '未配置'
  if (tokenSource.value === 'env') return '使用环境变量 GITHUB_TOKEN'
  if (tokenSource.value === 'system') return '已配置（系统存储）'
  return '未配置'
})

async function loadPackages() {
  try {
    const d = await request.get('/api/marketplace/packages')
    packages.value = d.packages || []
  } catch (e) { ElMessage.error(e.message) }
}

async function loadSkills() {
  try {
    const d = await request.get('/api/skills')
    skills.value = d.skills || []
  } catch (e) { /* 非阻塞 */ }
}

function loadAll() { loadPackages(); loadSkills() }

async function loadPresets() {
  try {
    const d = await request.get('/api/marketplace/remote/presets')
    presets.value = d.presets || []
  } catch (e) { /* 非阻塞 */ }
}

async function loadToken() {
  try {
    const d = await request.get('/api/marketplace/remote/token')
    tokenHasValue.value = !!d.has_value
    tokenSource.value = d.source || 'none'
  } catch (e) { /* 非阻塞 */ }
}

async function saveToken() {
  try {
    const d = await request.post('/api/marketplace/remote/token', { token: tokenInput.value })
    ElMessage.success(d.message || '已保存')
    tokenInput.value = ''
    await loadToken()
  } catch (e) { ElMessage.error(e.message) }
}

async function clearToken() {
  try {
    const d = await request.post('/api/marketplace/remote/token', { clear: true })
    ElMessage.success(d.message || '已清除')
    tokenInput.value = ''
    await loadToken()
  } catch (e) { ElMessage.error(e.message) }
}

async function loadRepo(owner, repo) {
  loadingRemote.value = true
  remoteHint.value = ''
  remoteSkills.value = []
  activeOwner.value = owner
  activeRepo.value = repo
  try {
    const d = await request.get(`/api/marketplace/remote/repos/${owner}/${repo}/skills`, { params: { branch: branch.value || 'main' } })
    remoteSkills.value = d.skills || []
    llmEvaluated.value = !!d.llm_evaluated
    remoteLoaded.value = true
  } catch (e) {
    remoteHint.value = e.message
    remoteLoaded.value = true
    ElMessage.error(e.message)
  } finally { loadingRemote.value = false }
}

function loadCustomRepo() {
  const v = (customRepo.value || '').replace(/^https?:\/\/(www\.)?github\.com\//, '').trim()
  const m = v.split('/')
  if (m.length >= 2 && m[0] && m[1]) {
    loadRepo(m[0], m[1])
  } else {
    ElMessage.error('仓库格式应为 owner/repo')
  }
}

async function preview(sk) {
  previewData.value = {}
  showZh.value = true
  previewVisible.value = true
  try {
    const d = await request.get(`/api/marketplace/remote/repos/${activeOwner.value}/${activeRepo.value}/skills/${sk.name}`, { params: { branch: branch.value || 'main' } })
    previewData.value = d
  } catch (e) { ElMessage.error(e.message) }
}

async function installRemote(sk) {
  try {
    const d = await request.post('/api/marketplace/remote/install', { owner: activeOwner.value, repo: activeRepo.value, skill: sk.name, branch: branch.value || 'main' })
    ElMessage.success(d.message || '已安装')
    previewVisible.value = false
    await loadAll()
    await loadRepo(activeOwner.value, activeRepo.value)
  } catch (e) { ElMessage.error(e.message) }
}

async function installFromPreview() {
  await installRemote({ name: previewData.value.name })
}

async function publish() {
  publishing.value = true
  try {
    const d = await request.post('/api/marketplace/publish', { skill_id: publishId.value })
    ElMessage.success(d.message || '已发布')
    publishId.value = null
    await loadPackages()
  } catch (e) { ElMessage.error(e.message) } finally { publishing.value = false }
}

async function install(p) {
  try {
    const d = await request.post('/api/marketplace/install', { package: p.package })
    ElMessage.success(d.message || '已安装')
    await loadAll()
  } catch (e) { ElMessage.error(e.message) }
}

async function removePkg(p) {
  try {
    await ElMessageBox.confirm(`确认删除市场包「${p.package}」？不影响已安装的技能。`, '删除市场包', { type: 'warning' })
  } catch { return }
  try {
    await request.delete(`/api/marketplace/packages/${encodeURIComponent(p.package)}`)
    ElMessage.success('已删除')
    await loadPackages()
  } catch (e) { ElMessage.error(e.message) }
}

loadAll()
loadPresets()
loadToken()
</script>

<style scoped>
.mp-page { padding: 20px; }
.page-header h1 { margin: 0 0 6px; }
.page-header p { color: #8b949e; margin: 0 0 16px; font-size: 13px; }
.remote-panel { background: #f6f8fa; border: 1px solid #e6e9ee; border-radius: 10px; padding: 14px; margin-bottom: 18px; }
.panel-head { font-weight: 600; margin-bottom: 10px; }
.remote-toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 10px; }
.chip { padding: 6px 12px; border: 1px solid #d9d9d9; background: #fff; border-radius: 20px; cursor: pointer; font-size: 13px; }
.chip.active { background: #409eff; color: #fff; border-color: #409eff; }
.custom-repo { display: flex; align-items: center; gap: 0; }
.token-row { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
.token-label { color: #57606a; font-size: 13px; font-weight: 500; }
.token-status { font-size: 12px; }
.token-status.none { color: #8b949e; }
.token-status.system { color: #52c41a; }
.token-status.env { color: #d48806; }
.filter-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.filter-hint { color: #8b949e; font-size: 12px; }
.reason-badge { font-size: 12px; margin: 4px 0; }
.reason-badge.rel { color: #52c41a; }
.reason-badge.notrel { color: #8b949e; }
.pkg-card.irrelevant { opacity: 0.5; }
.pv-toggle { margin: 0 0 8px; }
.remote-hint { color: #d03050; font-size: 12px; margin-bottom: 8px; }
.remote-loading { color: #909399; font-size: 13px; padding: 8px 0; }
.remote-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; margin-top: 6px; }
.pv-meta { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.pv-desc { color: #57606a; font-size: 13px; margin-bottom: 10px; }
.pv-body { background: #f6f8fa; border: 1px solid #eee; border-radius: 6px; padding: 12px; max-height: 50vh; overflow: auto; font-size: 12px; white-space: pre-wrap; word-break: break-word; }
.stat-row { display: flex; gap: 14px; margin-bottom: 16px; }
.stat-card { background: #fafafa; border: 1px solid #eee; border-radius: 8px; padding: 12px 20px; min-width: 110px; }
.stat-num { display: block; font-size: 22px; font-weight: 600; }
.stat-card span { color: #666; font-size: 12px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; gap: 12px; }
.mp-hint { color: #8b949e; font-size: 12px; }
.mp-hint code { background: #f0f2f5; padding: 2px 6px; border-radius: 4px; }
.btn { padding: 7px 14px; border: 1px solid #d9d9d9; background: #fff; border-radius: 6px; cursor: pointer; }
.btn:hover { border-color: #409eff; color: #409eff; }
.btn-primary { background: #409eff; color: #fff; border-color: #409eff; }
.btn-primary:hover { background: #66b1ff; color: #fff; }
.btn.danger:hover { border-color: #d03050; color: #d03050; }
.pkg-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
.pkg-card { border: 1px solid #eee; border-radius: 10px; padding: 14px; background: #fff; }
.pkg-head { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.pkg-name { font-weight: 700; font-size: 15px; }
.badge { background: #f0f2f5; border-radius: 4px; padding: 1px 8px; font-size: 12px; color: #57606a; }
.tag-ok { color: #52c41a; font-weight: 600; font-size: 12px; }
.tag-warn { color: #d48806; font-weight: 600; font-size: 12px; }
.pkg-desc { color: #57606a; font-size: 13px; margin: 8px 0; min-height: 38px; }
.pkg-meta { display: flex; gap: 12px; font-size: 12px; color: #8b949e; margin-bottom: 10px; flex-wrap: wrap; }
.pkg-ops { display: flex; gap: 8px; }
.empty-state { text-align: center; color: #8b949e; padding: 60px 0; background: #fafafa; border-radius: 8px; }
.empty-state.small { padding: 24px 0; font-size: 13px; }
.publish-panel { margin-top: 24px; background: #fafafa; border-radius: 8px; padding: 16px; }
.publish-row { display: flex; gap: 10px; align-items: center; }
</style>
