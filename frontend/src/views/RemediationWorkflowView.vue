<template>
  <div class="wf-page">
    <div class="page-header">
      <div class="title-row">
        <div>
          <h1>自愈工作流</h1>
          <p>多步骤故障自愈流程编排 · 共 {{ total }} 个工作流</p>
        </div>
        <button class="btn btn-guide" @click="showGuide = !showGuide">📖 操作说明</button>
      </div>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="openCreate">+ 新建工作流</button>
      <button class="btn" @click="loadData">刷新</button>
    </div>

    <div class="panel">
      <div class="panel-header"><h3>工作流列表</h3></div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="workflows.length" class="wf-list">
          <div v-for="w in workflows" :key="w.id" class="wf-card">
            <div class="wf-head">
              <span class="wf-name">{{ w.name }}</span>
              <span class="badge" :class="w.enabled ? 'resolved' : 'info'">{{ w.enabled ? '启用' : '禁用' }}</span>
            </div>
            <div class="wf-steps">
              <span class="steps-label">步骤：</span>
              <span v-for="(s, i) in w.steps" :key="i" class="step-chip">
                {{ typeof s === 'object' ? s.action || s.step : s }}
                <span v-if="i < w.steps.length - 1" class="step-arrow">→</span>
              </span>
            </div>
            <div class="wf-actions">
              <button class="btn btn-sm btn-primary" @click="runWorkflow(w)" :disabled="running === w.id">{{ running === w.id ? '运行中...' : '运行' }}</button>
              <button class="btn btn-sm" @click="toggleWorkflow(w)">{{ w.enabled ? '禁用' : '启用' }}</button>
              <button class="btn btn-sm btn-danger" @click="deleteWorkflow(w)">删除</button>
            </div>
          </div>
        </div>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">⚙️</div><div>暂无工作流</div></div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header"><h3>自愈日志 · 共 {{ logTotal }} 条</h3></div>
      <div class="panel-body">
        <table v-if="logs.length" class="table">
          <thead><tr><th>时间</th><th>工作流</th><th>动作</th><th>目标</th><th>结果</th></tr></thead>
          <tbody>
            <tr v-for="lg in logs" :key="lg.id">
              <td class="text-sm">{{ formatTime(lg.created_at) }}</td>
              <td>#{{ lg.remediation_id }}</td>
              <td>{{ lg.action_type }}</td>
              <td class="text-sm">{{ lg.target }}</td>
              <td><span class="badge" :class="lg.success ? 'resolved' : 'critical'">{{ lg.success ? '成功' : '失败' }}</span></td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">暂无执行日志</div>
        <div v-if="totalPages > 1" class="pagination">
          <button class="btn btn-sm" :disabled="currentPage <= 1" @click="goPage(1)">首页</button>
          <button class="btn btn-sm" :disabled="currentPage <= 1" @click="goPage(currentPage - 1)">上一页</button>
          <span v-for="p in pageNumbers" :key="p" class="page-num" :class="{ active: p === currentPage }" @click="goPage(p)">{{ p }}</span>
          <button class="btn btn-sm" :disabled="currentPage >= totalPages" @click="goPage(currentPage + 1)">下一页</button>
          <button class="btn btn-sm" :disabled="currentPage >= totalPages" @click="goPage(totalPages)">末页</button>
          <span class="page-jump">跳转 <input type="number" class="page-input" v-model.number="jumpPage" min="1" :max="totalPages" @keyup.enter="goPage(jumpPage)" /> 页</span>
          <span class="page-info">共 {{ logTotal }} 条 / {{ totalPages }} 页</span>
        </div>
      </div>
    </div>

    <div v-if="createVisible" class="modal-overlay" @click.self="createVisible = false">
      <div class="modal-box">
        <div class="modal-header"><h3>新建自愈工作流</h3><button class="modal-close" @click="createVisible = false">×</button></div>
        <div class="modal-body">
          <div class="form-group"><label>名称</label><input v-model="form.name" placeholder="如：CPU 高自愈流程" /></div>
          <div class="form-group"><label>关联告警规则 ID（可选）</label><input v-model.number="form.rule_id" type="number" placeholder="留空匹配所有" /></div>
          <div class="form-group">
            <label>步骤定义（JSON 数组）</label>
            <textarea v-model="form.steps" rows="8" placeholder='["healthcheck","restart","notify"]'></textarea>
            <p class="form-tip">可用操作：restart / clean / scale / notify / healthcheck</p>
          </div>
          <div class="form-actions"><button class="btn" @click="createVisible = false">取消</button><button class="btn btn-primary" @click="createWorkflow" :disabled="creating">{{ creating ? '创建中...' : '创建' }}</button></div>
        </div>
      </div>
    </div>

    <GuideDrawer v-model="showGuide" title="📖 自愈工作流 · 操作说明">
      <section class="guide-section">
        <h4>1. 目的</h4>
        <p>自愈工作流用于编排<strong>多步骤的故障自愈流程</strong>。与单动作的自愈规则不同，工作流支持多个动作按顺序执行（如：健康检查→重启→再次检查→通知），形成完整的自愈闭环。</p>
      </section>
      <section class="guide-section">
        <h4>2. 可用步骤动作</h4>
        <div class="key-value-list">
          <div class="kv-row"><span class="kv-key">healthcheck</span><span class="kv-val">健康检查，确认目标服务状态是否正常</span></div>
          <div class="kv-row"><span class="kv-key">restart</span><span class="kv-val">重启目标服务（通过资产 connection_config SSH 执行 systemctl restart）</span></div>
          <div class="kv-row"><span class="kv-key">clean</span><span class="kv-val">清理临时文件或日志，释放磁盘空间</span></div>
          <div class="kv-row"><span class="kv-key">scale</span><span class="kv-val">扩缩容 K8s Deployment（需在目标字段指定 Deployment 名）</span></div>
          <div class="kv-row"><span class="kv-key">notify</span><span class="kv-val">发送通知（自愈成功后通知相关人员）</span></div>
        </div>
      </section>
      <section class="guide-section">
        <h4>3. 操作步骤</h4>
        <ul>
          <li><strong>点击「新建工作流」</strong> — 填写工作流名称，可选关联告警规则 ID（留空则匹配所有告警）</li>
          <li><strong>定义步骤</strong> — 在 JSON 数组中填写步骤动作序列，如 <code>["healthcheck","restart","notify"]</code></li>
          <li><strong>启用工作流</strong> — 创建后点击「启用」按钮激活工作流，此后匹配告警自动触发</li>
          <li><strong>手动运行测试</strong> — 可随时点击「运行」按钮手动触发工作流，测试自愈流程是否正常</li>
        </ul>
      </section>
      <section class="guide-section">
        <h4>4. 实现了什么</h4>
        <p>当告警触发时，系统自动查找匹配的自愈工作流并执行完整步骤序列，实现<strong>多步骤自动处置</strong>。例如：CPU 高→healthcheck 确认→restart 重启→healthcheck 确认→notify 通知。全程无需人工介入。</p>
      </section>
    </GuideDrawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GuideDrawer from '@/components/GuideDrawer.vue'
import request from '@/api/request'

const loading = ref(false)
const showGuide = ref(false)
const workflows = ref([])
const logs = ref([])
const total = ref(0)
const createVisible = ref(false)
const creating = ref(false)
const running = ref(null)
const form = reactive({ name: '', rule_id: 0, steps: '["healthcheck","restart","notify"]' })

const currentPage = ref(1)
const pageSize = ref(20)
const logTotal = ref(0)
const totalPages = ref(1)
const jumpPage = ref(1)
const pageNumbers = computed(() => {
  const pages = []
  const cur = currentPage.value
  const tp = totalPages.value
  if (tp <= 7) {
    for (let i = 1; i <= tp; i++) pages.push(i)
  } else {
    pages.push(1)
    if (cur > 4) pages.push('...')
    const start = Math.max(2, cur - 1)
    const end = Math.min(tp - 1, cur + 1)
    for (let i = start; i <= end; i++) pages.push(i)
    if (cur < tp - 3) pages.push('...')
    pages.push(tp)
  }
  return pages
})
function goPage(p) {
  if (p < 1 || p > totalPages.value || p === currentPage.value) return
  currentPage.value = p
  loadLogs()
}

async function loadData() {
  loading.value = true
  try {
    const data = await request.get('/remediation-workflows/api/list')
    workflows.value = data.workflows || []
    total.value = data.total || 0
    loadLogs()
  } catch (e) { ElMessage.error('加载失败: ' + e.message) } finally { loading.value = false }
}

async function loadLogs() {
  try {
    const data = await request.get('/remediation-workflows/api/logs', { params: { page: currentPage.value, per_page: pageSize.value } })
    logs.value = data.items || []
    logTotal.value = data.total || 0
    totalPages.value = data.total_pages || 1
  } catch (e) {
    ElMessage.error('加载日志失败: ' + e.message)
  }
}

function openCreate() {
  Object.assign(form, { name: '', rule_id: 0, steps: '["healthcheck","restart","notify"]' })
  createVisible.value = true
}

async function createWorkflow() {
  if (!form.name) { ElMessage.warning('请填写名称'); return }
  creating.value = true
  try {
    const fd = new FormData()
    fd.append('name', form.name)
    fd.append('rule_id', form.rule_id)
    fd.append('steps', form.steps)
    await request.post('/remediation-workflows/api/create', fd)
    ElMessage.success('创建成功')
    createVisible.value = false
    loadData()
  } catch (e) { ElMessage.error('创建失败: ' + e.message) } finally { creating.value = false }
}

async function toggleWorkflow(w) {
  try {
    await request.post(`/remediation-workflows/api/${w.id}/toggle`)
    ElMessage.success(w.enabled ? '已禁用' : '已启用')
    loadData()
  } catch (e) { ElMessage.error('操作失败: ' + e.message) }
}

async function deleteWorkflow(w) {
  try {
    await ElMessageBox.confirm(`确认删除工作流"${w.name}"？`, '删除确认')
    await request.post(`/remediation-workflows/api/${w.id}/delete`)
    ElMessage.success('已删除')
    loadData()
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e)) }
}

async function runWorkflow(w) {
  try {
    await ElMessageBox.confirm(`确认运行工作流"${w.name}"？将处理最近的触发告警`, '运行确认')
    running.value = w.id
    const data = await request.post(`/remediation-workflows/api/${w.id}/run`)
    ElMessage.success(`运行完成，处理 ${data.ran} 条告警`)
    loadData()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('运行失败: ' + (e.message || e))
  } finally { running.value = null }
}

function formatTime(s) { return s ? s.substring(0, 19) : '-' }

onMounted(loadData)
</script>

<style scoped>
.wf-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.title-row { display: flex; align-items: center; gap: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.btn-danger { color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-danger:hover { background: rgba(239,68,68,0.08); }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 16px; }
.panel-header { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.panel-header h3 { margin: 0; font-size: 0.95rem; }
.panel-body { padding: 16px 18px; }
.wf-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 12px; }
.wf-card { border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; padding: 14px; }
.wf-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.wf-name { font-weight: 600; font-size: 0.95rem; }
.wf-steps { margin-bottom: 10px; font-size: 0.8rem; }
.steps-label { color: var(--text-secondary, #64748b); margin-right: 4px; }
.step-chip { display: inline-block; background: rgba(99,102,241,0.1); color: #6366f1; padding: 2px 8px; border-radius: 6px; margin-right: 4px; font-size: 0.75rem; }
.step-arrow { color: var(--text-tertiary, #94a3b8); margin-left: 4px; }
.wf-actions { display: flex; gap: 6px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.resolved { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.critical { background: rgba(239,68,68,0.1); color: #ef4444; }
.badge.info { background: rgba(100,116,139,0.1); color: #64748b; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 6px; margin-top: 16px; flex-wrap: wrap; }
.page-info { font-size: 0.82rem; color: var(--text-secondary, #64748b); }
.page-num { display: inline-flex; align-items: center; justify-content: center; min-width: 30px; height: 30px; padding: 0 6px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.8rem; cursor: pointer; transition: all 0.2s; user-select: none; }
.page-num:hover { background: var(--bg-hover, rgba(99,102,241,0.08)); border-color: var(--accent, #6366f1); }
.page-num.active { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); font-weight: 600; }
.page-jump { font-size: 0.8rem; color: var(--text-secondary, #64748b); display: flex; align-items: center; gap: 4px; }
.page-input { width: 50px; padding: 3px 6px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; text-align: center; font-size: 0.8rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 12px; width: 90%; max-width: 560px; max-height: 85vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.2); }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.modal-header h3 { margin: 0; font-size: 1.1rem; }
.modal-close { background: none; border: none; font-size: 24px; cursor: pointer; color: var(--text-secondary, #64748b); line-height: 1; }
.modal-body { padding: 20px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 0.8rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.form-group input, .form-group textarea { width: 100%; padding: 8px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.85rem; box-sizing: border-box; }
.form-group textarea { font-family: monospace; resize: vertical; }
.form-tip { font-size: 0.72rem; color: var(--text-tertiary, #94a3b8); margin: 4px 0 0; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
