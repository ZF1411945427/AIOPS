<template>
  <div class="mp-page">
    <div class="page-header">
      <h1>🛍️ 技能市场</h1>
      <p>私服技能市场（marketplace/packages）· 从技能库发布 zip 包，或从市场安装到技能库 · 多节点间离线分发</p>
    </div>

    <div class="stat-row">
      <div class="stat-card"><span class="stat-num">{{ packages.length }}</span><span>市场包</span></div>
      <div class="stat-card"><span class="stat-num">{{ installedNames.size }}</span><span>本库已安装</span></div>
      <div class="stat-card"><span class="stat-num">{{ skills.length }}</span><span>本库技能</span></div>
    </div>

    <div class="toolbar">
      <div class="mp-hint">📦 包存放于 <code>marketplace/packages/</code>，每个包为单个 <code>SKILL.md</code>（frontmatter 即 manifest）</div>
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
      <div>市场为空 —— 从技能库「发布」技能后，这里会出现可安装的技能包</div>
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

const installedNames = computed(() => new Set(skills.value.map(s => s.name)))

function categoryLabel(c) { return c || '-' }

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
</script>

<style scoped>
.mp-page { padding: 20px; }
.page-header h1 { margin: 0 0 6px; }
.page-header p { color: #8b949e; margin: 0 0 16px; font-size: 13px; }
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
.pkg-head { display: flex; gap: 8px; align-items: center; }
.pkg-name { font-weight: 700; font-size: 15px; }
.badge { background: #f0f2f5; border-radius: 4px; padding: 1px 8px; font-size: 12px; color: #57606a; }
.tag-ok { color: #52c41a; font-weight: 600; font-size: 12px; }
.pkg-desc { color: #57606a; font-size: 13px; margin: 8px 0; min-height: 38px; }
.pkg-meta { display: flex; gap: 12px; font-size: 12px; color: #8b949e; margin-bottom: 10px; flex-wrap: wrap; }
.pkg-ops { display: flex; gap: 8px; }
.empty-state { text-align: center; color: #8b949e; padding: 60px 0; background: #fafafa; border-radius: 8px; }
.publish-panel { margin-top: 24px; background: #fafafa; border-radius: 8px; padding: 16px; }
.panel-head { font-weight: 600; margin-bottom: 10px; }
.publish-row { display: flex; gap: 10px; align-items: center; }
</style>
