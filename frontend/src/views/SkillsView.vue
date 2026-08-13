<template>
  <div class="skill-page">
    <div class="page-header">
      <h1>🧩 技能库</h1>
      <p>SKILL.md 可执行技能 · 加载进注册表后可被 Agent 调用（list_skills / use_skill）· 调用全程审计</p>
    </div>

    <div class="stat-row">
      <div class="stat-card"><span class="stat-num">{{ skills.length }}</span><span>技能总数</span></div>
      <div class="stat-card"><span class="stat-num">{{ enabledCount }}</span><span>启用中</span></div>
      <div class="stat-card" :class="{ warn: disabledCount > 0 }"><span class="stat-num">{{ disabledCount }}</span><span>已禁用</span></div>
      <div class="stat-card"><span class="stat-num">{{ totalUsage }}</span><span>累计调用</span></div>
    </div>

    <div class="toolbar">
      <input v-model="search" class="search-input" placeholder="搜索技能名 / 描述 / 分类..." />
      <div class="toolbar-right">
        <button class="btn" @click="importSkill()">⬆️ 导入技能包</button>
        <button class="btn btn-primary" @click="openDialog()">+ 新建技能</button>
      </div>
    </div>

    <table v-if="filtered.length" class="table">
      <thead>
        <tr><th>ID</th><th>技能</th><th>分类</th><th>风险</th><th>来源</th><th>依赖工具</th><th>启用</th><th>调用</th><th>操作</th></tr>
      </thead>
      <tbody>
        <tr v-for="s in filtered" :key="s.id">
          <td>{{ s.id }}</td>
          <td>
            <div class="skill-name">{{ s.name }} <span class="badge">{{ s.version }}</span></div>
            <div class="skill-desc">{{ s.description || '-' }}</div>
          </td>
          <td><span class="badge">{{ categoryLabel(s.category) }}</span></td>
          <td><span class="badge risk-{{ s.risk_level }}">{{ riskLabel(s.risk_level) }}</span></td>
          <td><span class="badge">{{ sourceLabel(s.source) }}</span></td>
          <td class="tool-req">{{ (s.tools_required || []).join('、') || '-' }}</td>
          <td><el-switch :model-value="s.enabled" @change="v => toggleEnabled(s, v)" /></td>
          <td>{{ s.usage_count }}</td>
          <td class="ops">
            <button class="btn-icon-sm" title="详情/查看指令" @click="openDetail(s)">👁️</button>
            <button class="btn-icon-sm" title="编辑" @click="openDialog(s)">✏️</button>
            <button class="btn-icon-sm" title="执行" @click="openRun(s)">▶️</button>
            <button class="btn-icon-sm" title="导出技能包" @click="exportSkill(s)">⬇️</button>
            <button class="btn-icon-sm danger" :title="s.source === 'builtin' ? '禁用(卸载)' : '删除'" @click="delSkill(s)">🗑️</button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty-state">
      <div style="font-size:40px;margin-bottom:12px;">🧩</div>
      <div>{{ search ? '没有找到匹配的技能' : '暂无技能，点「+ 新建技能」或到「技能市场」安装' }}</div>
    </div>

    <div v-if="executions.length" class="audit-panel">
      <div class="panel-head"><span>📜 执行审计（{{ executions.length }} 条）</span></div>
      <table class="table">
        <thead><tr><th>时间</th><th>技能</th><th>触发</th><th>状态</th><th>入参摘要</th><th>输出摘要</th><th>耗时</th></tr></thead>
        <tbody>
          <tr v-for="e in executions" :key="e.id">
            <td>{{ e.created_at || '-' }}</td>
            <td>{{ e.skill_name }}</td>
            <td><span class="badge">{{ e.tool }}</span></td>
            <td><span :class="e.status === 'success' ? 'tag-ok' : 'tag-bad'">{{ e.status }}</span></td>
            <td class="sum">{{ e.input_summary || '-' }}</td>
            <td class="sum">{{ e.output_summary || '-' }}</td>
            <td>{{ e.duration_ms }}ms</td>
          </tr>
        </tbody>
      </table>
    </div>

    <el-dialog v-model="showDialog" :title="editing ? '编辑技能' : '新建技能'" width="640px" top="6vh">
      <el-form label-width="100px">
        <el-form-item label="技能名" required>
          <el-input v-model="form.name" :disabled="!!editing" placeholder="如 log-troubleshooter（use_skill 入参名，唯一）" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="版本 / 作者 / License">
          <div class="triple">
            <el-input v-model="form.version" placeholder="1.0.0" />
            <el-input v-model="form.author" placeholder="作者" />
            <el-input v-model="form.license" placeholder="MIT" />
          </div>
        </el-form-item>
        <el-form-item label="分类 / 风险">
          <div class="triple">
            <el-select v-model="form.category" style="width:100%">
              <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
            </el-select>
            <el-select v-model="form.risk_level" style="width:100%">
              <el-option v-for="r in riskLevels" :key="r" :label="riskLabel(r)" :value="r" />
            </el-select>
            <el-input v-model="form.tools_required_str" placeholder="依赖工具, 逗号分隔" />
          </div>
        </el-form-item>
        <el-form-item label="关键词">
          <el-input v-model="form.keywords_str" placeholder="keywords, 逗号分隔（可选）" />
        </el-form-item>
        <el-form-item label="SKILL.md 内容" required>
          <el-input v-model="form.content" type="textarea" :rows="12" class="mono"
            placeholder="---&#10;name: xxx&#10;description: ...&#10;---&#10;&#10;# 指令正文" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveSkill()">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showDetail" title="技能详情" width="760px" top="5vh">
      <div v-if="detail" class="detail-card">
        <div class="detail-head">
          <span class="detail-name">{{ detail.name }}</span>
          <span class="badge">{{ detail.version }}</span>
          <span class="badge">{{ categoryLabel(detail.category) }}</span>
          <span class="badge risk-{{ detail.risk_level }}">{{ riskLabel(detail.risk_level) }}</span>
          <span class="badge">{{ sourceLabel(detail.source) }}</span>
          <span v-if="detail.enabled" class="tag-ok">启用</span>
          <span v-else class="tag-bad">禁用</span>
        </div>
        <p class="detail-desc">{{ detail.description }}</p>
        <div class="detail-meta">
          <span>作者: {{ detail.author || '-' }}</span>
          <span>License: {{ detail.license || '-' }}</span>
          <span>调用: {{ detail.usage_count }} 次</span>
          <span>依赖: {{ (detail.tools_required || []).join('、') || '无' }}</span>
          <span>关键词: {{ (detail.keywords || []).join('、') || '无' }}</span>
        </div>
        <pre class="content-pre">{{ detail.content }}</pre>
      </div>
      <template #footer><el-button @click="showDetail = false">关闭</el-button></template>
    </el-dialog>

    <el-dialog v-model="showRun" title="执行技能" width="560px" top="15vh">
      <p class="run-tip">在 <code>{{ runSkillName }}</code> 上执行：</p>
      <el-input v-model="runInput" type="textarea" :rows="3" placeholder="输入技能要处理的目标 / 参数..." />
      <div v-if="runResult" class="run-result">
        <p><span :class="runResult.status === 'success' ? 'tag-ok' : 'tag-bad'">{{ runResult.status }}</span> 输出: {{ runResult.output_summary }}</p>
      </div>
      <template #footer>
        <el-button @click="showRun = false">关闭</el-button>
        <el-button type="primary" :loading="running" @click="doRun()">执行</el-button>
      </template>
    </el-dialog>

    <input ref="fileInput" type="file" accept=".zip" style="display:none" @change="onImportFile" />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const skills = ref([])
const riskLevels = ref(['read_only', 'interactive', 'danger'])
const categories = ref(['诊断', '修复', '巡检', '数据查询', '通用', '自定义'])
const executions = ref([])
const search = ref('')
const showDialog = ref(false)
const showDetail = ref(false)
const showRun = ref(false)
const editing = ref(null)
const detail = ref(null)
const saving = ref(false)
const running = ref(false)
const runSkillName = ref('')
const runSkillId = ref(null)
const runInput = ref('')
const runResult = ref(null)
const fileInput = ref(null)

const form = ref({ name: '', description: '', version: '1.0.0', author: '', license: 'MIT',
  category: '诊断', risk_level: 'read_only', keywords_str: '', tools_required_str: '', content: '' })

const filtered = computed(() => {
  const q = (search.value || '').toLowerCase()
  if (!q) return skills.value
  return skills.value.filter(s =>
    s.name.toLowerCase().includes(q) || (s.description || '').toLowerCase().includes(q) || s.category.toLowerCase().includes(q)
  )
})
const enabledCount = computed(() => skills.value.filter(s => s.enabled).length)
const disabledCount = computed(() => skills.value.filter(s => !s.enabled).length)
const totalUsage = computed(() => skills.value.reduce((a, s) => a + (s.usage_count || 0), 0))

function riskLabel(r) { return { read_only: '只读', interactive: '交互', danger: '危险' }[r] || r }
function sourceLabel(s) { return { builtin: '内置', upload: '上传', marketplace: '市场' }[s] || s }
function categoryLabel(c) { return c || '-' }

async function load() {
  try {
    const d = await request.get('/api/skills')
    skills.value = d.skills || []
    riskLevels.value = d.risk_levels || riskLevels.value
  } catch (e) { ElMessage.error(e.message) }
}

async function loadExecutions() {
  try {
    const d = await request.get('/api/skills/executions')
    executions.value = (d.executions || []).slice(0, 30)
  } catch (e) { /* 非阻塞 */ }
}

function openDialog(s) {
  editing.value = s || null
  if (s) {
    form.value = {
      name: s.name, description: s.description || '', version: s.version, author: s.author || '',
      license: s.license || '', category: s.category || '诊断', risk_level: s.risk_level,
      keywords_str: (s.keywords || []).join(', '), tools_required_str: (s.tools_required || []).join(', '),
      content: s.content || '',
    }
  } else {
    form.value = { name: '', description: '', version: '1.0.0', author: '', license: 'MIT',
      category: '诊断', risk_level: 'read_only', keywords_str: '', tools_required_str: '', content: '' }
  }
  showDialog.value = true
}

async function saveSkill() {
  if (!form.value.name.trim()) { ElMessage.warning('技能名不能为空'); return }
  if (!form.value.content.trim()) { ElMessage.warning('SKILL.md 内容不能为空'); return }
  saving.value = true
  try {
    const payload = {
      ...form.value,
      keywords: form.value.keywords_str.split(/[,，]/).map(s => s.trim()).filter(Boolean),
      tools_required: form.value.tools_required_str.split(/[,，]/).map(s => s.trim()).filter(Boolean),
    }
    delete payload.keywords_str
    delete payload.tools_required_str
    if (editing.value) {
      await request.put(`/api/skills/${editing.value.id}`, payload)
      ElMessage.success('已保存')
    } else {
      await request.post('/api/skills', payload)
      ElMessage.success('技能已安装')
    }
    showDialog.value = false
    await load()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

async function toggleEnabled(s, v) {
  try {
    await request.put(`/api/skills/${s.id}`, { enabled: v })
    s.enabled = v
    ElMessage.success(v ? '已启用' : '已禁用')
  } catch (e) { ElMessage.error(e.message); load() }
}

async function delSkill(s) {
  const isBuiltin = s.source === 'builtin'
  try {
    await ElMessageBox.confirm(
      isBuiltin ? `内置技能「${s.name}」将从 Agent 清单移除（禁用），确定？` : `确认删除技能「${s.name}」？`,
      isBuiltin ? '禁用技能' : '删除技能', { type: 'warning' })
  } catch { return }
  try {
    await request.delete(`/api/skills/${s.id}`)
    ElMessage.success(isBuiltin ? '已禁用（卸载）' : '已删除')
    await load()
  } catch (e) { ElMessage.error(e.message) }
}

function exportSkill(s) {
  window.open(`/api/skills/${s.id}/export`, '_blank')
}

function importSkill() {
  fileInput.value.click()
}

async function onImportFile(e) {
  const file = e.target.files[0]
  if (!file) return
  const fd = new FormData()
  fd.append('file', file)
  try {
    const d = await request.post('/api/skills/import', fd)
    ElMessage.success(`已导入技能 ${d.skill?.name} v${d.skill?.version}`)
    await load()
  } catch (err) { ElMessage.error(err.message) }
  e.target.value = ''
}

async function openDetail(s) {
  try {
    const d = await request.get(`/api/skills/${s.id}`)
    detail.value = d.skill
    showDetail.value = true
  } catch (e) { ElMessage.error(e.message) }
}

function openRun(s) {
  runSkillName.value = s.name
  runSkillId.value = s.id
  runInput.value = ''
  runResult.value = null
  showRun.value = true
}

async function doRun() {
  running.value = true
  try {
    const d = await request.post(`/api/skills/${runSkillId.value}/run`, { input: runInput.value })
    runResult.value = d
    ElMessage.success('执行记录已写入审计')
    await load()
    await loadExecutions()
  } catch (e) { ElMessage.error(e.message) } finally { running.value = false }
}

load()
loadExecutions()
</script>

<style scoped>
.skill-page { padding: 20px; }
.page-header h1 { margin: 0 0 6px; }
.page-header p { color: #8b949e; margin: 0 0 16px; font-size: 13px; }
.stat-row { display: flex; gap: 14px; margin-bottom: 16px; flex-wrap: wrap; }
.stat-card { background: #fafafa; border: 1px solid #eee; border-radius: 8px; padding: 12px 20px; min-width: 110px; }
.stat-card.warn .stat-num { color: #d03050; }
.stat-num { display: block; font-size: 22px; font-weight: 600; }
.stat-card span { color: #666; font-size: 12px; }
.toolbar { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.search-input { flex: 1; max-width: 340px; padding: 8px 12px; border: 1px solid #d9d9d9; border-radius: 6px; }
.toolbar-right { display: flex; gap: 10px; }
.btn { padding: 7px 14px; border: 1px solid #d9d9d9; background: #fff; border-radius: 6px; cursor: pointer; }
.btn:hover { border-color: #409eff; color: #409eff; }
.btn-primary { background: #409eff; color: #fff; border-color: #409eff; }
.btn-primary:hover { background: #66b1ff; color: #fff; }
.table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; }
.table th, .table td { border-bottom: 1px solid #f0f0f0; padding: 10px 12px; text-align: left; font-size: 13px; }
.table th { background: #fafafa; color: #666; font-weight: 500; white-space: nowrap; }
.skill-name { font-weight: 600; }
.skill-name .badge { margin-left: 6px; }
.skill-desc { color: #8b949e; font-size: 12px; margin-top: 2px; max-width: 320px; }
.badge { display: inline-block; background: #f0f2f5; border-radius: 4px; padding: 1px 8px; font-size: 12px; color: #57606a; }
.badge.risk-read_only { background: #e6f7ff; color: #1890ff; }
.badge.risk-interactive { background: #fff7e6; color: #d48806; }
.badge.risk-danger { background: #fff1f0; color: #cf1322; }
.tool-req { max-width: 220px; font-size: 12px; color: #57606a; }
.ops { white-space: nowrap; }
.btn-icon-sm { border: 1px solid #d9d9d9; background: #fff; border-radius: 4px; width: 26px; height: 26px; cursor: pointer; margin-right: 4px; }
.btn-icon-sm:hover { border-color: #409eff; }
.btn-icon-sm.danger:hover { border-color: #d03050; }
.empty-state { text-align: center; color: #8b949e; padding: 60px 0; background: #fafafa; border-radius: 8px; }
.audit-panel { margin-top: 24px; }
.panel-head { font-weight: 600; margin-bottom: 8px; }
.tag-ok { color: #52c41a; font-weight: 600; font-size: 12px; }
.tag-bad { color: #cf1322; font-weight: 600; font-size: 12px; }
.sum { max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; color: #57606a; }
.triple { display: flex; gap: 8px; width: 100%; }
.mono textarea, .mono { font-family: Consolas, Menlo, monospace; }
.detail-card { border: 1px solid #eee; border-radius: 8px; padding: 16px; }
.detail-head { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.detail-name { font-size: 18px; font-weight: 700; }
.detail-desc { color: #57606a; margin: 10px 0; }
.detail-meta { display: flex; gap: 16px; flex-wrap: wrap; font-size: 12px; color: #8b949e; margin-bottom: 10px; }
.content-pre { background: #0d1117; color: #c9d1d9; border-radius: 8px; padding: 14px; overflow: auto; max-height: 420px; font-size: 12px; line-height: 1.6; }
.run-tip { margin: 0 0 10px; }
.run-result { margin-top: 10px; }
</style>
