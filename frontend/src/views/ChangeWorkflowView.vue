<template>
  <div class="cw-page">
    <div class="page-header">
      <h1>变更审批</h1>
      <p>变更工单全流程：草稿 → 待审批 → 已批准 → 进行中 → 完成/回滚 · 共 {{ total }} 条</p>
      <button class="btn btn-guide" @click="showGuide = !showGuide" style="margin-left:auto">📖 操作说明</button>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="openCreate">+ 新建变更</button>
      <button class="btn" @click="loadChanges">刷新</button>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="changes.length" class="table">
          <thead>
            <tr>
              <th>ID</th><th>标题</th><th>状态</th><th>类型</th>
              <th>优先级</th><th>风险</th><th>申请人</th><th>时间</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in changes" :key="c.id">
              <td>{{ c.id }}</td>
              <td class="title-cell" @click="showDetail(c.id)">{{ c.title }}</td>
              <td><span class="badge" :class="statusClass(c.status)">{{ statusLabel(c.status) }}</span></td>
              <td>{{ c.change_type }}</td>
              <td><span class="badge" :class="priorityClass(c.priority)">{{ c.priority }}</span></td>
              <td><span class="badge" :class="riskClass(c.risk_level)">{{ c.risk_level }}</span></td>
              <td>{{ c.requester_name || '-' }}</td>
              <td class="text-sm">{{ formatTime(c.created_at) }}</td>
              <td>
                <button class="btn btn-sm" @click="showDetail(c.id)">详情</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">📝</div>
          <div>暂无变更工单，点击"新建变更"创建</div>
        </div>
        <div v-if="totalPages > 1" class="pagination">
          <button class="btn btn-sm" :disabled="currentPage <= 1" @click="goPage(1)">首页</button>
          <button class="btn btn-sm" :disabled="currentPage <= 1" @click="goPage(currentPage - 1)">上一页</button>
          <span v-for="p in pageNumbers" :key="p" class="page-num" :class="{ active: p === currentPage }" @click="goPage(p)">{{ p }}</span>
          <button class="btn btn-sm" :disabled="currentPage >= totalPages" @click="goPage(currentPage + 1)">下一页</button>
          <button class="btn btn-sm" :disabled="currentPage >= totalPages" @click="goPage(totalPages)">末页</button>
          <span class="page-jump">跳转 <input type="number" class="page-input" v-model.number="jumpPage" min="1" :max="totalPages" @keyup.enter="goPage(jumpPage)" /> 页</span>
          <span class="page-info">共 {{ total }} 条 / {{ totalPages }} 页</span>
        </div>
      </div>
    </div>

    <div v-if="createVisible" class="modal-overlay" @click.self="createVisible = false">
      <div class="modal-box">
        <div class="modal-header">
          <h3>新建变更</h3>
          <button class="modal-close" @click="createVisible = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>标题</label>
            <input v-model="form.title" placeholder="如：数据库迁移" />
          </div>
          <div class="form-group">
            <label>描述</label>
            <textarea v-model="form.description" rows="3" placeholder="变更详细说明"></textarea>
          </div>
          <div class="form-grid">
            <div class="form-group">
              <label>类型</label>
              <select v-model="form.change_type">
                <option value="normal">正常变更</option>
                <option value="emergency">紧急变更</option>
                <option value="standard">标准变更</option>
              </select>
            </div>
            <div class="form-group">
              <label>优先级</label>
              <select v-model="form.priority">
                <option value="low">低</option>
                <option value="medium">中</option>
                <option value="high">高</option>
              </select>
            </div>
            <div class="form-group">
              <label>风险等级</label>
              <select v-model="form.risk_level">
                <option value="low">低</option>
                <option value="medium">中</option>
                <option value="high">高</option>
              </select>
            </div>
            <div class="form-group">
              <label>CI 类型</label>
              <input v-model="form.ci_type" placeholder="如：database" />
            </div>
            <div class="form-group">
              <label>计划开始</label>
              <input v-model="form.planned_started_at" type="datetime-local" />
            </div>
            <div class="form-group">
              <label>计划结束</label>
              <input v-model="form.planned_ended_at" type="datetime-local" />
            </div>
          </div>
          <div class="form-actions">
            <button class="btn" @click="createVisible = false">取消</button>
            <button class="btn btn-primary" @click="createChange" :disabled="creating">{{ creating ? '创建中...' : '创建' }}</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="detailVisible" class="modal-overlay" @click.self="detailVisible = false">
      <div class="modal-box large">
        <div class="modal-header">
          <h3>变更 #{{ detail?.id }} · {{ detail?.title }}</h3>
          <button class="modal-close" @click="detailVisible = false">×</button>
        </div>
        <div v-if="detail" class="modal-body">
          <div class="status-banner" :class="detail.status">
            <span class="status-label">当前状态：</span>
            <span class="badge lg" :class="statusClass(detail.status)">{{ statusLabel(detail.status) }}</span>
            <span class="status-meta">{{ detail.change_type }} / {{ detail.priority }} / {{ detail.risk_level }}</span>
          </div>

          <div class="detail-grid">
            <div class="detail-item"><span class="detail-label">申请人</span><span class="detail-value">{{ detail.requester_name || '-' }}</span></div>
            <div class="detail-item"><span class="detail-label">审批人</span><span class="detail-value">{{ detail.reviewer_name || '-' }}</span></div>
            <div class="detail-item"><span class="detail-label">CI 类型</span><span class="detail-value">{{ detail.ci_type || '-' }}</span></div>
            <div class="detail-item"><span class="detail-label">资产 ID</span><span class="detail-value">{{ detail.asset_id || '-' }}</span></div>
            <div class="detail-item"><span class="detail-label">计划开始</span><span class="detail-value">{{ detail.planned_started_at || '-' }}</span></div>
            <div class="detail-item"><span class="detail-label">计划结束</span><span class="detail-value">{{ detail.planned_ended_at || '-' }}</span></div>
          </div>

          <div v-if="detail.description" class="desc-block">
            <div class="detail-label">描述</div>
            <p class="desc-text">{{ detail.description }}</p>
          </div>

          <div v-if="detail.review_comment" class="desc-block">
            <div class="detail-label">审批意见</div>
            <p class="desc-text muted">{{ detail.review_comment }}</p>
          </div>

          <div class="action-bar">
            <button v-if="detail.status === 'draft'" class="btn btn-primary" @click="doAction('submit')">提交审批</button>
            <template v-if="detail.status === 'pending_approval'">
              <input v-model="reviewComment" placeholder="审批意见" class="comment-input" />
              <button class="btn btn-success" @click="doAction('approve')">通过</button>
              <button class="btn btn-danger" @click="doAction('reject')">驳回</button>
            </template>
            <button v-if="detail.status === 'approved'" class="btn btn-info" @click="doAction('start')">开始执行</button>
            <button v-if="detail.status === 'in_progress'" class="btn btn-success" @click="doAction('complete')">完成</button>
            <button v-if="['approved','in_progress'].includes(detail.status)" class="btn btn-warning" @click="doAction('rollback')">回滚</button>
          </div>

          <h4 class="sub-title">执行步骤 ({{ tasks.length }})</h4>

          <div v-if="detail.status === 'in_progress'" class="task-add-row">
            <input v-model="newTask.description" placeholder="步骤描述" />
            <input v-model="newTask.command" placeholder="执行命令(可选)" class="cmd-input" />
            <input v-model.number="newTask.step_order" type="number" min="1" class="order-input" />
            <button class="btn btn-sm btn-primary" @click="addTask">添加</button>
          </div>

          <div class="task-list">
            <div v-for="t in tasks" :key="t.id" class="task-card">
              <div class="task-main">
                <span class="task-order">#{{ t.step_order }}</span>
                <span class="task-desc">{{ t.description }}</span>
                <code v-if="t.command" class="task-cmd">{{ t.command }}</code>
                <span class="badge" :class="taskStatusClass(t.status)">{{ t.status }}</span>
              </div>
              <div v-if="t.result" class="task-result text-sm">结果: {{ t.result }}</div>
              <div v-if="detail.status === 'in_progress'" class="task-update-row">
                <select :value="t.status" @change="updateTaskStatus(t.id, $event.target.value)">
                  <option value="pending">pending</option>
                  <option value="in_progress">in_progress</option>
                  <option value="completed">completed</option>
                  <option value="failed">failed</option>
                  <option value="skipped">skipped</option>
                </select>
              </div>
            </div>
            <div v-if="!tasks.length" class="empty-state small">暂无执行步骤</div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <GuideDrawer v-model="showGuide" title="📖 变更审批 · 操作说明">
    <section class="guide-section">
      <h4>1. 什么是变更管理？</h4>
      <p><strong>变更管理（Change Management）</strong>是对运维操作（升级、配置修改、重启、迁移等）进行<strong>规范化审批</strong>的流程。目的是减少变更引发的故障，确保每次变更都经过评估和授权。</p>
      <p>ITIL 里有个数据：<strong>80% 的故障由变更引起</strong>。所以规范的变更流程不是"走形式"，而是保护系统稳定的第一道防线。</p>
    </section>
    <section class="guide-section">
      <h4>2. 状态流转</h4>
      <div class="guide-code">草稿 → 待审批 → 已批准 → 进行中 → 已完成
                                 ↘ 已驳回        ↘ 已回滚</div>
      <ul>
        <li><strong>草稿</strong> — 创建人还在填写信息，未提交审批</li>
        <li><strong>待审批</strong> — 已提交，等待审批人审核</li>
        <li><strong>已批准 / 已驳回</strong> — 审批结果</li>
        <li><strong>进行中</strong> — 审批通过，正在执行变更操作</li>
        <li><strong>已完成 / 已回滚</strong> — 变更执行完成，或出现问题回滚到变更前状态</li>
      </ul>
    </section>
    <section class="guide-section">
      <h4>3. 变更类型</h4>
      <div class="key-value-list">
        <div class="kv-row"><span class="kv-key">标准变更</span><span class="kv-val">预先批准的常规操作（如例行重启），走简化流程</span></div>
        <div class="kv-row"><span class="kv-key">正常变更</span><span class="kv-val">普通变更，需要审批。比如数据库迁移、版本升级</span></div>
        <div class="kv-row"><span class="kv-key">紧急变更</span><span class="kv-val">需要立即执行的变更（如修复安全漏洞），加急审批</span></div>
      </div>
    </section>
    <section class="guide-section">
      <h4>4. 风险等级</h4>
      <ul>
        <li><span class="tag-demo" style="background:rgba(16,185,129,0.12);color:#10b981;">低</span> — 影响范围小，失败风险低（如修改日志级别）</li>
        <li><span class="tag-demo" style="background:rgba(245,158,11,0.12);color:#d97706;">中</span> — 有一定影响（如更新非核心服务）</li>
        <li><span class="tag-demo" style="background:rgba(239,68,68,0.12);color:#ef4444;">高</span> — 影响核心业务，变更失败可能导致重大故障（如数据库主从切换）</li>
      </ul>
    </section>
    <section class="guide-section">
      <h4>5. 创建变更示例</h4>
      <p>以"升级 nginx 到 1.26"为例：</p>
      <div class="step-list">
        <div class="step-item"><span class="step-num">1</span><span>点击「新建变更」，填写标题<code>生产环境 nginx 升级到 1.26</code>、描述变更原因</span></div>
        <div class="step-item"><span class="step-num">2</span><span>选择<strong>变更类型</strong>：正常变更；<strong>风险等级</strong>：中（影响线上流量）</span></div>
        <div class="step-item"><span class="step-num">3</span><span>添加<strong>执行步骤</strong>：<br>① 备份当前配置 /etc/nginx/<br>② 下载 nginx 1.26 二进制<br>③ 替换二进制并执行 nginx -t 检查语法<br>④ 执行 nginx -s reload 重新加载</span></div>
        <div class="step-item"><span class="step-num">4</span><span>提交后等待审批 → 批准后开始执行 → 完成后点「完成变更」</span></div>
      </div>
    </section>
    <section class="guide-section">
      <h4>6. 回滚操作</h4>
      <p>如果已「完成」的变更出现问题：</p>
      <ol style="margin:4px 0 10px;padding-left:18px;font-size:0.8rem;line-height:1.7;color:#475569;">
        <li>在变更详情中点击「回滚」按钮</li>
        <li>确认后，状态变更为"已回滚"</li>
      </ol>
      <div class="tip-box">💡 回滚只是标记状态，实际的回滚操作（如恢复旧版本）需要人工或通过 Ansible 等工具执行。建议在变更步骤中提前写好回滚步骤。</div>
    </section>
  </GuideDrawer>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import GuideDrawer from '@/components/GuideDrawer.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const changes = ref([])
const total = ref(0)
const createVisible = ref(false)
const creating = ref(false)
const detailVisible = ref(false)
const detail = ref(null)
const tasks = ref([])
const reviewComment = ref('')
const newTask = reactive({ description: '', command: '', step_order: 1 })
const form = reactive({
  title: '', description: '', ci_type: '', change_type: 'normal',
  priority: 'medium', risk_level: 'low', planned_started_at: '', planned_ended_at: '',
})

const currentPage = ref(1)
const pageSize = ref(20)
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
  loadChanges()
}

async function loadChanges() {
  loading.value = true
  try {
    const data = await request.get('/change-workflow/api/list', { params: { page: currentPage.value, per_page: pageSize.value } })
    changes.value = data.changes || []
    total.value = data.total || 0
    totalPages.value = data.total_pages || 1
  } catch (e) {
    ElMessage.error('加载失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, { title: '', description: '', ci_type: '', change_type: 'normal', priority: 'medium', risk_level: 'low', planned_started_at: '', planned_ended_at: '' })
  createVisible.value = true
}

async function createChange() {
  if (!form.title) { ElMessage.warning('请填写标题'); return }
  creating.value = true
  try {
    const fd = new FormData()
    fd.append('title', form.title)
    fd.append('description', form.description)
    fd.append('ci_type', form.ci_type)
    fd.append('asset_id', 0)
    fd.append('change_type', form.change_type)
    fd.append('priority', form.priority)
    fd.append('risk_level', form.risk_level)
    fd.append('planned_started_at', form.planned_started_at)
    fd.append('planned_ended_at', form.planned_ended_at)
    const data = await request.post('/change-workflow/api/create', fd)
    ElMessage.success('创建成功')
    createVisible.value = false
    currentPage.value = 1
    loadChanges()
    showDetail(data.id)
  } catch (e) {
    ElMessage.error('创建失败: ' + e.message)
  } finally {
    creating.value = false
  }
}

async function showDetail(id) {
  reviewComment.value = ''
  try {
    const data = await request.get(`/change-workflow/api/${id}`)
    detail.value = data.change
    tasks.value = data.tasks || []
    detailVisible.value = true
  } catch (e) {
    ElMessage.error('加载详情失败: ' + e.message)
  }
}

async function doAction(action) {
  if (!detail.value) return
  const actionLabels = { submit: '提交审批', approve: '审批通过', reject: '驳回', start: '开始执行', complete: '完成', rollback: '回滚' }
  try {
    await ElMessageBox.confirm(`确认${actionLabels[action]}？`, '操作确认')
    const fd = new FormData()
    if (action === 'approve' || action === 'reject') fd.append('review_comment', reviewComment.value)
    const data = await request.post(`/change-workflow/api/${detail.value.id}/${action}`, fd)
    ElMessage.success(`${actionLabels[action]}成功，状态: ${statusLabel(data.status)}`)
    showDetail(detail.value.id)
    loadChanges()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('操作失败: ' + (e.message || e))
  }
}

async function addTask() {
  if (!newTask.description) { ElMessage.warning('请填写步骤描述'); return }
  try {
    const fd = new FormData()
    fd.append('description', newTask.description)
    fd.append('command', newTask.command)
    fd.append('step_order', newTask.step_order || tasks.value.length + 1)
    await request.post(`/change-workflow/api/${detail.value.id}/tasks/new`, fd)
    ElMessage.success('步骤已添加')
    Object.assign(newTask, { description: '', command: '', step_order: tasks.value.length + 2 })
    showDetail(detail.value.id)
  } catch (e) {
    ElMessage.error('添加失败: ' + e.message)
  }
}

async function updateTaskStatus(taskId, newStatus) {
  try {
    const fd = new FormData()
    fd.append('status', newStatus)
    fd.append('result', '')
    await request.post(`/change-workflow/api/${detail.value.id}/tasks/${taskId}/status`, fd)
    ElMessage.success('状态已更新')
    showDetail(detail.value.id)
  } catch (e) {
    ElMessage.error('更新失败: ' + e.message)
  }
}

function statusLabel(s) {
  const m = { draft: '草稿', pending_approval: '待审批', approved: '已批准', rejected: '已驳回', in_progress: '进行中', completed: '已完成', rolled_back: '已回滚' }
  return m[s] || s
}
function statusClass(s) {
  const m = { draft: 'info', pending_approval: 'warning', approved: 'approved', rejected: 'critical', in_progress: 'in_progress', completed: 'resolved', rolled_back: 'critical' }
  return m[s] || 'info'
}
function priorityClass(p) {
  return { low: 'info', medium: 'warning', high: 'critical' }[p] || 'info'
}
function riskClass(r) {
  return { low: 'resolved', medium: 'warning', high: 'critical' }[r] || 'info'
}
function taskStatusClass(s) {
  return { pending: 'info', in_progress: 'warning', completed: 'resolved', failed: 'critical', skipped: 'skipped' }[s] || 'info'
}
function formatTime(s) {
  if (!s) return '-'
  return s.substring(5, 16)
}

onMounted(loadChanges)

const showGuide = ref(false)
</script>

<style scoped>
.cw-page { padding: 4px; }
.page-header { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; transition: all 0.2s; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-success { background: #22c55e; color: #fff; border-color: #22c55e; }
.btn-danger { background: #ef4444; color: #fff; border-color: #ef4444; }
.btn-info { background: #3b82f6; color: #fff; border-color: #3b82f6; }
.btn-warning { background: #f59e0b; color: #fff; border-color: #f59e0b; }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.title-cell { cursor: pointer; color: var(--accent, #6366f1); font-weight: 500; }
.title-cell:hover { text-decoration: underline; }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.lg { padding: 4px 12px; font-size: 0.8rem; }
.badge.info { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.warning { background: rgba(245,158,11,0.1); color: #f59e0b; }
.badge.approved { background: rgba(59,130,246,0.1); color: #3b82f6; }
.badge.in_progress { background: rgba(99,102,241,0.1); color: #6366f1; }
.badge.resolved { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.critical { background: rgba(239,68,68,0.1); color: #ef4444; }
.badge.skipped { background: rgba(100,116,139,0.1); color: #94a3b8; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 6px; margin-top: 16px; flex-wrap: wrap; }
.page-info { font-size: 0.82rem; color: var(--text-secondary, #64748b); }
.page-num { display: inline-flex; align-items: center; justify-content: center; min-width: 30px; height: 30px; padding: 0 6px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.8rem; cursor: pointer; transition: all 0.2s; user-select: none; }
.page-num:hover { background: var(--bg-hover, rgba(99,102,241,0.08)); border-color: var(--accent, #6366f1); }
.page-num.active { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); font-weight: 600; }
.page-jump { font-size: 0.8rem; color: var(--text-secondary, #64748b); display: flex; align-items: center; gap: 4px; }
.page-input { width: 50px; padding: 3px 6px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; text-align: center; font-size: 0.8rem; }
.empty-state.small { padding: 16px; font-size: 0.82rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 12px; width: 90%; max-width: 560px; max-height: 85vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.2); }
.modal-box.large { max-width: 820px; max-height: 90vh; }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); position: sticky; top: 0; background: var(--bg-card-solid, #fff); z-index: 1; }
.modal-header h3 { margin: 0; font-size: 1.05rem; }
.modal-close { background: none; border: none; font-size: 24px; cursor: pointer; color: var(--text-secondary, #64748b); line-height: 1; }
.modal-body { padding: 20px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 0.8rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.form-group input, .form-group select, .form-group textarea { width: 100%; padding: 8px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.85rem; box-sizing: border-box; }
.form-group textarea { font-family: inherit; resize: vertical; }
.form-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.form-grid .form-group { margin-bottom: 0; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.status-banner { display: flex; align-items: center; gap: 10px; padding: 12px; border-radius: 8px; margin-bottom: 16px; background: var(--bg-hover, rgba(0,0,0,0.03)); flex-wrap: wrap; }
.status-label { font-size: 0.8rem; color: var(--text-secondary, #64748b); }
.status-meta { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.detail-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }
.detail-item { display: flex; flex-direction: column; gap: 4px; }
.detail-label { font-size: 0.72rem; color: var(--text-secondary, #64748b); text-transform: uppercase; letter-spacing: 0.3px; }
.detail-value { font-size: 0.85rem; color: var(--text, #1e293b); }
.desc-block { margin-bottom: 14px; }
.desc-text { margin: 4px 0 0; font-size: 0.85rem; color: var(--text, #1e293b); line-height: 1.5; }
.desc-text.muted { color: var(--text-secondary, #64748b); }
.action-bar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; padding: 12px; background: var(--bg-hover, rgba(0,0,0,0.03)); border-radius: 8px; margin-bottom: 16px; }
.comment-input { padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; min-width: 200px; }
.sub-title { font-size: 0.95rem; margin: 0 0 10px; color: var(--text, #1e293b); }
.task-add-row { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.task-add-row input { padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; }
.task-add-row input:first-child { flex: 1; min-width: 180px; }
.task-add-row .cmd-input { flex: 1; min-width: 160px; }
.task-add-row .order-input { width: 70px; }
.task-list { display: flex; flex-direction: column; gap: 8px; }
.task-card { border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; padding: 10px 12px; }
.task-main { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.task-order { font-weight: 700; color: var(--accent, #6366f1); font-size: 0.85rem; }
.task-desc { font-size: 0.85rem; color: var(--text, #1e293b); }
.task-cmd { font-family: 'Consolas', 'Monaco', monospace; font-size: 0.75rem; background: var(--bg-hover, rgba(0,0,0,0.03)); padding: 2px 6px; border-radius: 4px; color: var(--text-secondary, #64748b); }
.task-result { margin-top: 6px; padding-top: 6px; border-top: 1px dashed var(--border, rgba(0,0,0,0.07)); }
.task-update-row { margin-top: 8px; }
.task-update-row select { padding: 4px 8px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.78rem; }
</style>
