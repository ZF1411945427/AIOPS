<template>
  <div class="gt-page">
    <div class="page-header">
      <h1>GroundTruth 测试集</h1>
      <p>Agent 评估基准 · 真实工具调用 · 中文语义匹配评分</p>
    </div>
    <div class="stats-grid" v-if="stats">
      <div class="stat-card"><div class="stat-value" style="color:#6366f1;">{{ stats.total_tests }}</div><div class="stat-label">测试用例</div></div>
      <div class="stat-card"><div class="stat-value" style="color:#22c55e;">{{ stats.active_tests }}</div><div class="stat-label">活跃</div></div>
      <div class="stat-card"><div class="stat-value" style="color:#14b8a6;">{{ stats.total_runs }}</div><div class="stat-label">执行次数</div></div>
      <div class="stat-card"><div class="stat-value" style="color:#f59e0b;">{{ stats.avg_total_score }}</div><div class="stat-label">平均分</div></div>
    </div>
    <div class="toolbar">
      <select v-model="filterCategory" class="input" style="width:140px;" @change="loadTests">
        <option value="">全部分类</option>
        <option value="qa">QA</option>
        <option value="tool_call">工具调用</option>
        <option value="rag">RAG</option>
        <option value="reasoning">推理</option>
      </select>
      <label class="inline-check"><input type="checkbox" v-model="showInactive" @change="loadTests" /> 显示已禁用</label>
      <span class="spacer"></span>
      <button class="btn btn-primary" @click="openCreate">+ 新建用例</button>
      <button class="btn" @click="loadTests">刷新</button>
    </div>
    <div class="panel">
      <div class="panel-head">测试用例 · {{ tests.length }} 条</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="!tests.length" class="empty-state">暂无用例</div>
        <div v-else class="table-wrap">
          <table class="table">
            <thead><tr><th>名称</th><th>分类</th><th>难度</th><th>问题</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="t in tests" :key="t.id">
                <td>{{ t.name }}</td>
                <td><span class="badge cat-{{ t.category }}">{{ t.category }}</span></td>
                <td><span class="badge diff-{{ t.difficulty }}">{{ t.difficulty }}</span></td>
                <td class="q-cell">{{ t.question.substring(0, 80) }}{{ t.question.length > 80 ? '...' : '' }}</td>
                <td>
                  <span class="status-dot" :class="t.is_active ? 'on' : 'off'"></span>
                  {{ t.is_active ? '启用' : '禁用' }}
                </td>
                <td>
                  <button class="btn btn-sm" @click="openEdit(t)">编辑</button>
                  <button class="btn btn-sm btn-primary" @click="runTest(t)" :disabled="runningId === t.id">
                    {{ runningId === t.id ? '执行中...' : '执行' }}
                  </button>
                  <button class="btn btn-sm" @click="toggleActive(t)">{{ t.is_active ? '禁用' : '启用' }}</button>
                  <button class="btn btn-sm btn-danger" @click="deleteTest(t)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
    <div class="panel" v-if="runs.length">
      <div class="panel-head">最近执行记录 · {{ runs.length }} 条</div>
      <div class="panel-body">
        <div class="table-wrap">
          <table class="table">
            <thead><tr><th>用例</th><th>模型</th><th>实际调用工具</th><th>答案分</th><th>工具分</th><th>总分</th><th>延迟</th></tr></thead>
            <tbody>
              <tr v-for="r in runs" :key="r.id">
                <td>{{ r.test_name || ('#' + r.test_id) }}</td>
                <td>{{ r.model_name || '-' }}</td>
                <td class="tools-cell">
                  <span v-for="t in r.actual_tools" :key="t.name" class="tool-tag" :class="t.is_success ? 'ok' : 'fail'">
                    {{ t.name }}{{ t.is_success ? '' : '✗' }}
                  </span>
                  <span v-if="!r.actual_tools || !r.actual_tools.length" class="muted">无</span>
                </td>
                <td>{{ r.answer_score }}</td>
                <td>{{ r.tool_score }}</td>
                <td><strong>{{ r.total_score }}</strong></td>
                <td>{{ r.latency_ms }}ms</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
    <div v-if="showForm" class="modal-overlay" @click.self="showForm = false">
      <div class="modal-box">
        <h3>{{ editing ? '编辑用例' : '新建用例' }}</h3>
        <div class="form-group"><label class="form-label">名称</label><input v-model="form.name" class="input" /></div>
        <div class="form-group"><label class="form-label">分类</label><select v-model="form.category" class="input"><option value="qa">QA</option><option value="tool_call">工具调用</option><option value="rag">RAG</option><option value="reasoning">推理</option></select></div>
        <div class="form-group"><label class="form-label">问题</label><textarea v-model="form.question" class="input" rows="3"></textarea></div>
        <div class="form-group"><label class="form-label">预期答案</label><textarea v-model="form.expected_answer" class="input" rows="3"></textarea></div>
        <div class="form-group"><label class="form-label">预期工具（逗号分隔）</label><input v-model="form.expected_tools_str" class="input" placeholder="get_alert_detail, query_assets" /></div>
        <div class="form-group"><label class="form-label">难度</label><select v-model="form.difficulty" class="input"><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select></div>
        <div class="form-group"><label class="form-label">标签</label><input v-model="form.tags" class="input" /></div>
        <div class="form-group"><label class="inline-check"><input type="checkbox" v-model="form.is_active" /> 启用</label></div>
        <div class="modal-actions"><button class="btn" @click="showForm = false">取消</button><button class="btn btn-primary" @click="submitForm">保存</button></div>
      </div>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'
const tests = ref([])
const runs = ref([])
const stats = ref(null)
const providers = ref([])
const loading = ref(false)
const showForm = ref(false)
const editing = ref(false)
const filterCategory = ref('')
const showInactive = ref(false)
const runningId = ref(null)
const form = ref({ name: '', category: 'qa', question: '', expected_answer: '', expected_tools_str: '', difficulty: 'medium', tags: '', is_active: true })
async function loadTests() {
  loading.value = true
  try {
    const params = {}
    if (filterCategory.value) params.category = filterCategory.value
    if (showInactive.value) params.include_inactive = true
    const [testRes, runRes, statsRes] = await Promise.all([
      request.get('/agent/api/ground-truth/tests', { params }),
      request.get('/agent/api/ground-truth/runs', { params: { limit: 10, ...(filterCategory.value ? { category: filterCategory.value } : {}) } }),
      request.get('/agent/api/ground-truth/stats'),
    ])
    tests.value = testRes.items || []
    runs.value = runRes.items || []
    stats.value = statsRes
  } catch (e) { ElMessage.error('加载失败: ' + (e.message || e)) }
  finally { loading.value = false }
}
async function loadProviders() {
  try {
    const data = await request.get('/agent/api/ground-truth/providers')
    providers.value = data.items || []
  } catch (e) { /* 静默 */ }
}
function openCreate() {
  editing.value = false
  form.value = { name: '', category: 'qa', question: '', expected_answer: '', expected_tools_str: '', difficulty: 'medium', tags: '', is_active: true }
  showForm.value = true
}
function openEdit(t) {
  editing.value = true
  form.value = { ...t, expected_tools_str: (t.expected_tools || []).join(', ') }
  showForm.value = true
}
async function submitForm() {
  if (!form.value.name || !form.value.question) { ElMessage.warning('名称和问题不能为空'); return }
  try {
    const payload = {
      name: form.value.name,
      category: form.value.category,
      question: form.value.question,
      expected_answer: form.value.expected_answer,
      expected_tools: form.value.expected_tools_str ? form.value.expected_tools_str.split(',').map(s => s.trim()).filter(Boolean) : [],
      tags: form.value.tags,
      difficulty: form.value.difficulty,
      is_active: form.value.is_active,
    }
    if (editing.value) {
      await request.put(`/agent/api/ground-truth/tests/${form.value.id}`, payload)
      ElMessage.success('已更新')
    } else {
      await request.post('/agent/api/ground-truth/tests', payload)
      ElMessage.success('已创建')
    }
    showForm.value = false; loadTests()
  } catch (e) { ElMessage.error('操作失败: ' + (e.message || e)) }
}
async function runTest(t) {
  if (runningId.value) return
  runningId.value = t.id
  try {
    const res = await request.post(`/agent/api/ground-truth/tests/${t.id}/run`, {}, { timeout: 120000 })
    if (res.run) {
      ElMessage.success(`执行完成 总分: ${res.run.total_score} (答案 ${res.run.answer_score} / 工具 ${res.run.tool_score})`)
    } else if (res.error) {
      ElMessage.error('执行失败: ' + res.error)
    }
    loadTests()
  } catch (e) { ElMessage.error('执行失败: ' + (e.message || e)) }
  finally { runningId.value = null }
}
async function toggleActive(t) {
  try {
    await request.put(`/agent/api/ground-truth/tests/${t.id}`, { is_active: !t.is_active })
    ElMessage.success(t.is_active ? '已禁用' : '已启用')
    loadTests()
  } catch (e) { ElMessage.error('操作失败: ' + (e.message || e)) }
}
async function deleteTest(t) {
  if (!confirm(`确认删除「${t.name}」？历史执行记录将保留（软删除）。`)) return
  try {
    await request.delete(`/agent/api/ground-truth/tests/${t.id}`)
    ElMessage.success('已删除'); loadTests()
  } catch (e) { ElMessage.error('删除失败: ' + (e.message || e)) }
}
onMounted(() => { loadProviders(); loadTests() })
</script>
<style scoped>
.gt-page { padding: 4px; }
.page-header { margin-bottom: 12px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; margin: 0 0 4px; }
.page-header p { color: var(--text-secondary,#64748b); font-size: 0.85rem; margin: 0; }
.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 14px; }
.stat-card { background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; padding: 14px; text-align: center; }
.stat-value { font-size: 1.8rem; font-weight: 800; }
.stat-label { font-size: 0.75rem; color: var(--text-secondary,#64748b); margin-top: 4px; }
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; align-items: center; }
.spacer { flex: 1; }
.inline-check { font-size: 0.82rem; color: var(--text-secondary,#64748b); display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong,rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid,#fff); cursor: pointer; font-size: 0.82rem; }
.btn-primary { background: var(--accent,#6366f1); color: #fff; border-color: var(--accent,#6366f1); }
.btn-danger { background: #ef4444; color: #fff; border-color: #ef4444; }
.btn-sm { padding: 3px 8px; font-size: 0.75rem; }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.input { padding: 5px 10px; border: 1px solid var(--border,rgba(0,0,0,0.1)); border-radius: 6px; font-size: 0.82rem; outline: none; width: 100%; box-sizing: border-box; }
.input:focus { border-color: var(--accent,#6366f1); }
.panel { background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; margin-bottom: 14px; }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; }
.panel-body { padding: 16px 18px; }
.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.table th { text-align: left; padding: 8px 10px; border-bottom: 2px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; color: var(--text-secondary,#64748b); font-size: 0.75rem; text-transform: uppercase; }
.table td { padding: 10px 10px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.05)); }
.table tbody tr:hover { background: var(--bg-hover,rgba(0,0,0,0.02)); }
.q-cell { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tools-cell { max-width: 320px; }
.tool-tag { display: inline-block; padding: 1px 6px; margin: 1px 2px; border-radius: 4px; font-size: 0.72rem; background: rgba(99,102,241,0.1); color: #6366f1; }
.tool-tag.fail { background: rgba(239,68,68,0.1); color: #ef4444; }
.muted { color: var(--text-tertiary,#94a3b8); }
.badge { padding: 2px 8px; border-radius: 6px; font-size: 0.72rem; font-weight: 600; }
.cat-qa { background: rgba(99,102,241,0.1); color: #6366f1; }
.cat-tool_call { background: rgba(20,184,166,0.1); color: #14b8a6; }
.cat-rag { background: rgba(245,158,11,0.1); color: #f59e0b; }
.cat-reasoning { background: rgba(34,197,94,0.1); color: #22c55e; }
.diff-easy { background: rgba(34,197,94,0.1); color: #22c55e; }
.diff-medium { background: rgba(245,158,11,0.1); color: #f59e0b; }
.diff-hard { background: rgba(239,68,68,0.1); color: #ef4444; }
.status-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 4px; vertical-align: middle; }
.status-dot.on { background: #22c55e; }
.status-dot.off { background: #94a3b8; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary,#94a3b8); font-size: 0.9rem; }
.form-group { margin-bottom: 10px; }
.form-label { display: block; font-size: 0.78rem; font-weight: 600; color: var(--text-secondary,#64748b); margin-bottom: 4px; }
textarea.input { resize: vertical; min-height: 60px; font-family: inherit; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid,#fff); border-radius: 12px; padding: 24px; min-width: 480px; box-shadow: 0 8px 32px rgba(0,0,0,0.15); }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; font-weight: 600; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
