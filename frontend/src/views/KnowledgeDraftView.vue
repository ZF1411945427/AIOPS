<template>
  <div class="draft-page">
    <div class="page-header">
      <h1>AI 知识草稿</h1>
      <p>告警解决后自动生成 · 人工审批后入库 · 共 {{ total }} 条待审草稿</p>
    </div>

    <div class="toolbar">
      <select v-model="filterStatus" class="input" style="width:130px;" @change="loadDrafts">
        <option value="">全部</option>
        <option value="pending">待审批</option>
        <option value="approved">已通过</option>
        <option value="rejected">已拒绝</option>
      </select>
      <button class="btn" @click="loadDrafts">刷新</button>
    </div>

    <div class="stats-bar" v-if="stats">
      <span class="stat-item stat-pending">待审批 {{ stats.pending }}</span>
      <span class="stat-item stat-approved">已通过 {{ stats.approved }}</span>
      <span class="stat-item stat-rejected">已拒绝 {{ stats.rejected }}</span>
    </div>

    <div class="panel">
      <div class="panel-head">草稿列表 · {{ items.length }} 条</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="!items.length" class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">📝</div>
          <div>暂无草稿 · 解决告警后会自动生成 AI 知识草稿</div>
        </div>
        <div v-else class="draft-list">
          <div v-for="d in items" :key="d.id" class="draft-item">
            <div class="draft-head">
              <span class="draft-title">{{ d.title }}</span>
              <span class="badge" :class="sevClass(d.severity)">{{ d.severity }}</span>
              <span v-if="d.alert_id" class="draft-alert-id">告警 #{{ d.alert_id }}</span>
              <span class="draft-status" :class="'st-' + d.status">{{ statusLabel(d.status) }}</span>
              <span class="draft-time">{{ d.created_at }}</span>
            </div>
            <div v-if="d.tags" class="draft-tags">
              <span v-for="t in tagList(d.tags)" :key="t" class="tag-mini">{{ t }}</span>
            </div>
            <div class="draft-body">
              <div v-if="d.symptom" class="rec-block">
                <span class="rec-label">故障表现</span>
                <div class="rec-text">{{ d.symptom }}</div>
              </div>
              <div v-if="d.root_cause" class="rec-block">
                <span class="rec-label">根因分析</span>
                <div class="rec-text">{{ d.root_cause }}</div>
              </div>
              <div v-if="d.solution" class="rec-block">
                <span class="rec-label">解决方案</span>
                <div class="rec-text">{{ d.solution }}</div>
              </div>
              <div v-if="d.sop_steps && d.sop_steps.length" class="sop-block">
                <span class="rec-label">SOP 步骤</span>
                <div v-for="(step, idx) in d.sop_steps" :key="idx" class="sop-step">
                  <span class="step-num">{{ idx + 1 }}</span>
                  <div class="step-body">
                    <div class="step-action">{{ step.action }}</div>
                    <div v-if="step.command" class="step-cmd"><code>{{ step.command }}</code></div>
                    <div v-if="step.expectation" class="step-exp">预期: {{ step.expectation }}</div>
                  </div>
                </div>
              </div>
            </div>
            <div v-if="d.status === 'pending'" class="draft-actions">
              <span class="src-tag" :class="'src-' + (d.source_type || 'auto')">{{ sourceTypeLabel(d.source_type) }}</span>
              <button class="btn btn-sm btn-primary" @click="approveDraft(d)">通过入库</button>
              <button class="btn btn-sm btn-ghost" @click="openReject(d)">拒绝</button>
            </div>
            <div v-if="d.status === 'rejected' && d.reject_reason" class="reject-reason">
              拒绝原因: {{ d.reject_reason }}
            </div>
          </div>
        </div>
      </div>
    </div>

          <div class="modal-overlay" v-if="showConfirm" @click.self="showConfirm = false">
            <div class="modal-box">
              <h3>确认操作</h3>
              <p style="margin:12px 0;font-size:0.9rem;">{{ confirmMsg }}</p>
              <div v-if="pendingAction?.type === 'reject'" style="margin-top:12px;">
                <input v-model="rejectReason" class="reason-input" placeholder="拒绝原因（可选）" />
              </div>
              <div class="modal-actions">
                <button class="btn" @click="showConfirm = false">取消</button>
                <button class="btn btn-primary" @click="doConfirm">确定</button>
              </div>
            </div>
          </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const items = ref([])
const total = ref(0)
const stats = ref(null)
const filterStatus = ref('pending')
const showConfirm = ref(false)
const confirmMsg = ref('')
const pendingAction = ref(null)
const rejectReason = ref('')

function sevClass(s) {
  return {
    critical: 'sev-critical',
    high: 'sev-high',
    warning: 'sev-warning',
    info: 'sev-info',
  }[s] || 'sev-info'
}

function statusLabel(s) {
  return { pending: '待审批', approved: '已通过', rejected: '已拒绝' }[s] || s
}

function tagList(tags) {
  if (Array.isArray(tags)) return tags
  if (typeof tags === 'string') return tags.split(',').map(t => t.trim()).filter(Boolean)
  return []
}

function sourceTypeLabel(s) {
  return { auto: 'AI自动', sop: 'SOP生成', manual: '手动' }[s] || 'AI自动'
}

function openReject(d) {
  pendingAction.value = { type: 'reject', draft: d }
  confirmMsg.value = `确定拒绝此草稿"${d.title}"？`
  rejectReason.value = ''
  showConfirm.value = true
}

function approveDraft(d) {
  pendingAction.value = { type: 'approve', draft: d }
  confirmMsg.value = `确定通过此草稿"${d.title}"并写入知识库？`
  showConfirm.value = true
}

async function loadDrafts() {
  loading.value = true
  try {
    const params = { status: filterStatus.value, page: 1, per_page: 100 }
    const data = await request.get('/knowledge/api/auto-gen/drafts', { params })
    items.value = data.items || []
    total.value = data.total

    const allData = await request.get('/knowledge/api/auto-gen/drafts', { params: { status: '', page: 1, per_page: 100 } })
    const all = allData.items || []
    stats.value = {
      pending: all.filter(x => x.status === 'pending').length,
      approved: all.filter(x => x.status === 'approved').length,
      rejected: all.filter(x => x.status === 'rejected').length,
    }
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

async function doConfirm() {
  if (!pendingAction.value) return
  const { type, draft } = pendingAction.value
  showConfirm.value = false
  try {
    if (type === 'approve') {
      await request.post('/knowledge/api/auto-gen/drafts/' + draft.id + '/approve')
      ElMessage.success('已通过: ' + draft.title)
    } else {
      await request.post('/knowledge/api/auto-gen/drafts/' + draft.id + '/reject', { reason: rejectReason.value })
      ElMessage.success('已拒绝: ' + draft.title)
    }
    await loadDrafts()
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.message || e))
  }
}

onMounted(() => {
  loadDrafts()
})
</script>

<style scoped>
.draft-page { padding: 4px; }
.page-header { margin-bottom: 12px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }

.toolbar { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; flex-wrap: wrap; }
.search-input { min-width: 240px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-sm { padding: 3px 10px; font-size: 0.75rem; }
.btn-ghost { background: transparent; border-color: var(--border-strong, rgba(0,0,0,0.12)); color: var(--text-secondary, #64748b); }

.stats-bar { display: flex; gap: 12px; margin-bottom: 12px; }
.stat-item { font-size: 0.82rem; font-weight: 600; padding: 4px 12px; border-radius: 8px; }
.stat-pending { background: rgba(245,158,11,0.12); color: #d97706; }
.stat-approved { background: rgba(34,197,94,0.12); color: #22c55e; }
.stat-rejected { background: rgba(148,163,184,0.12); color: #64748b; }

.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 14px; }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); }
.panel-body { padding: 16px 18px; }

.draft-list { display: flex; flex-direction: column; gap: 12px; }
.draft-item { padding: 14px; border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; background: var(--bg-hover, rgba(0,0,0,0.02)); }
.draft-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.draft-title { font-size: 0.95rem; font-weight: 600; color: var(--text, #1e293b); flex: 1; }
.draft-alert-id { font-size: 0.72rem; color: var(--text-tertiary, #94a3b8); background: rgba(0,0,0,0.05); padding: 2px 6px; border-radius: 4px; }
.draft-status { font-size: 0.72rem; font-weight: 600; padding: 2px 8px; border-radius: 8px; }
.st-pending { background: rgba(245,158,11,0.12); color: #d97706; }
.st-approved { background: rgba(34,197,94,0.12); color: #22c55e; }
.st-rejected { background: rgba(148,163,184,0.12); color: #64748b; }
.draft-time { font-size: 0.72rem; color: var(--text-tertiary, #94a3b8); margin-left: auto; }
.draft-tags { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 8px; }
.tag-mini { display: inline-block; padding: 1px 6px; border-radius: 4px; background: rgba(99,102,241,0.08); color: var(--accent, #6366f1); font-size: 0.7rem; }
.draft-body { margin-top: 8px; }
.draft-actions { margin-top: 10px; display: flex; gap: 8px; align-items: center; }
.src-tag { font-size: 0.7rem; padding: 2px 8px; border-radius: 8px; background: rgba(99,102,241,0.1); color: #6366f1; font-weight: 600; }
.src-sop { background: rgba(34,197,94,0.1); color: #22c55e; }

.sop-block { margin-top: 10px; }
.sop-step { display: flex; gap: 10px; margin-top: 6px; }
.step-num { width: 20px; height: 20px; background: var(--accent,#6366f1); color: #fff; border-radius: 50%; font-size: 0.7rem; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.step-body { flex: 1; }
.step-action { font-size: 0.82rem; color: var(--text,#1e293b); font-weight: 600; }
.step-cmd { margin-top: 4px; }
.step-cmd code { background: #f1f5f9; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; color: #6366f1; font-family: monospace; }
.step-exp { font-size: 0.75rem; color: var(--text-secondary,#64748b); margin-top: 2px; }

.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.sev-critical { background: rgba(239,68,68,0.12); color: #ef4444; }
.sev-high { background: rgba(249,115,22,0.12); color: #f97316; }
.sev-warning { background: rgba(245,158,11,0.12); color: #d97706; }
.sev-info { background: rgba(59,130,246,0.12); color: #3b82f6; }

.rec-block { margin-top: 6px; }
.rec-label { font-size: 0.72rem; color: var(--text-secondary, #64748b); font-weight: 600; }
.rec-text { margin-top: 4px; font-size: 0.82rem; color: var(--text, #1e293b); line-height: 1.5; white-space: pre-wrap; }

.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 12px; padding: 24px 28px; min-width: 400px; max-width: 500px; max-height: 80vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.15); }
.modal-box h3 { margin: 0 0 8px; font-size: 1.05rem; font-weight: 600; color: var(--text, #1e293b); }
.modal-actions { margin-top: 16px; display: flex; justify-content: flex-end; gap: 8px; }
</style>
