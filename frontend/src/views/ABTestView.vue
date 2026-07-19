<template>
  <div class="ab-page">
    <div class="page-header">
      <h1>A/B 测试框架</h1>
      <p>多模型效果对比 · 分流比例可控 · 实时统计胜出组（同一时刻仅 1 个实验运行）</p>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="openCreate">+ 新建实验</button>
      <button class="btn" @click="loadAll">刷新</button>
    </div>

    <div class="panel">
      <div class="panel-head">实验配置 · {{ tests.length }} 条</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="!tests.length" class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">🧪</div>
          <div>暂无实验配置 · 点击「新建实验」开始对比模型效果</div>
        </div>
        <div v-else class="test-list">
          <div v-for="t in tests" :key="t.id" class="test-item" :class="t.status">
            <div class="test-head">
              <span class="test-name">{{ t.name }}</span>
              <span class="status-badge" :class="t.status">{{ t.status === 'active' ? '运行中' : '已停止' }}</span>
              <span class="split-tag">分流 {{ t.split_ratio }}</span>
              <span class="metric-tag">指标: {{ metricLabel(t.metric) }}</span>
            </div>
            <div class="test-body">
              <div class="model-col">
                <div class="model-a">
                  <span class="model-label">A 组</span>
                  <span class="model-name">{{ providerName(t.provider_a_id) || '未配置' }}</span>
                  <span class="model-sub" v-if="t.model_a">{{ t.model_a }}</span>
                </div>
                <div class="vs">VS</div>
                <div class="model-b">
                  <span class="model-label">B 组</span>
                  <span class="model-name">{{ providerName(t.provider_b_id) || '未配置' }}</span>
                  <span class="model-sub" v-if="t.model_b">{{ t.model_b }}</span>
                </div>
              </div>
            </div>
            <div v-if="getResults(t.id) && getResults(t.id).total > 0" class="test-results">
              <div class="result-a">
                <div class="res-rate">{{ getResults(t.id).group_a.success_rate || 0 }}%</div>
                <div class="res-latency">延迟 {{ getResults(t.id).group_a.avg_latency_ms || 0 }}ms</div>
                <div class="res-count">{{ getResults(t.id).group_a.total || 0 }} 次</div>
              </div>
              <div class="winner-badge" v-if="getResults(t.id).winner !== 'insufficient_data'">
                {{ winnerLabel(getResults(t.id).winner) }}
              </div>
              <div class="result-b">
                <div class="res-rate">{{ getResults(t.id).group_b.success_rate || 0 }}%</div>
                <div class="res-latency">延迟 {{ getResults(t.id).group_b.avg_latency_ms || 0 }}ms</div>
                <div class="res-count">{{ getResults(t.id).group_b.total || 0 }} 次</div>
              </div>
            </div>
            <div v-else class="test-results-empty">暂无实验数据（发起对话后自动采集）</div>
            <div class="test-actions">
              <button class="btn btn-sm" @click="viewDetail(t)">查看详情</button>
              <button v-if="t.status === 'active'" class="btn btn-sm btn-ghost" @click="stopTest(t)">停止</button>
              <button v-else class="btn btn-sm btn-primary" @click="startTest(t)">启动</button>
              <button class="btn btn-sm btn-danger" @click="deleteTest(t)">删除</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showDetail" class="modal-overlay" @click.self="showDetail = false">
      <div class="modal-box" style="min-width:560px;">
        <h3>实验详情 · {{ detailTest?.name }}</h3>
        <div v-if="detailResult">
          <div class="detail-row"><span>评估指标:</span><strong>{{ metricLabel(detailResult.metric) }}</strong></div>
          <div class="detail-row"><span>总记录:</span><strong>{{ detailResult.total }}</strong></div>
          <div class="detail-row"><span>胜出组:</span><strong>{{ winnerLabel(detailResult.winner) }}</strong></div>
          <table class="table" style="margin-top:10px;">
            <thead><tr><th>组</th><th>总数</th><th>成功</th><th>成功率</th><th>平均延迟</th><th>平均 Token</th></tr></thead>
            <tbody>
              <tr>
                <td>A 组</td>
                <td>{{ detailResult.group_a.total || 0 }}</td>
                <td>{{ detailResult.group_a.is_success || 0 }}</td>
                <td>{{ detailResult.group_a.success_rate || 0 }}%</td>
                <td>{{ detailResult.group_a.avg_latency_ms || 0 }}ms</td>
                <td>{{ detailResult.group_a.avg_tokens || 0 }}</td>
              </tr>
              <tr>
                <td>B 组</td>
                <td>{{ detailResult.group_b.total || 0 }}</td>
                <td>{{ detailResult.group_b.is_success || 0 }}</td>
                <td>{{ detailResult.group_b.success_rate || 0 }}%</td>
                <td>{{ detailResult.group_b.avg_latency_ms || 0 }}ms</td>
                <td>{{ detailResult.group_b.avg_tokens || 0 }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="loading-state">加载中...</div>
        <div class="modal-actions"><button class="btn" @click="showDetail = false">关闭</button></div>
      </div>
    </div>

    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal-box">
        <h3>新建 A/B 实验</h3>
        <div class="form-group">
          <label class="form-label">实验名称</label>
          <input v-model="form.name" class="input" placeholder="例如: GPT-4 vs Claude-3 对比测试">
        </div>
        <div class="form-group">
          <label class="form-label">A 组模型（Provider）</label>
          <select v-model="form.provider_a_id" class="input">
            <option :value="null" disabled>请选择 A 组 Provider</option>
            <option v-for="p in providers" :key="p.id" :value="p.id">
              {{ p.name }} ({{ p.default_model || p.provider_type }}){{ p.is_enabled ? '' : ' [已禁用]' }}
            </option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">B 组模型（Provider）</label>
          <select v-model="form.provider_b_id" class="input">
            <option :value="null" disabled>请选择 B 组 Provider</option>
            <option v-for="p in providers" :key="p.id" :value="p.id">
              {{ p.name }} ({{ p.default_model || p.provider_type }}){{ p.is_enabled ? '' : ' [已禁用]' }}
            </option>
          </select>
        </div>
        <div v-if="form.provider_a_id && form.provider_b_id && form.provider_a_id === form.provider_b_id" class="form-error">
          ⚠ A 组和 B 组不能选择同一个 Provider
        </div>
        <div class="form-group">
          <label class="form-label">分流比例</label>
          <select v-model="form.split_ratio" class="input">
            <option value="50/50">50/50</option>
            <option value="70/30">70/30</option>
            <option value="80/20">80/20</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">评估指标</label>
          <select v-model="form.metric" class="input">
            <option value="latency">延迟优先（avg_latency_ms &gt; 100ms 差异判定）</option>
            <option value="accuracy">准确率优先（success_rate &gt; 5% 差异判定）</option>
            <option value="success">综合分（success_rate - latency/1000）</option>
          </select>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" @click="createTest" :disabled="!canCreate">创建并启动</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const tests = ref([])
const providers = ref([])
const showCreate = ref(false)
const showDetail = ref(false)
const detailResult = ref(null)
const detailTest = ref(null)
const loading = ref(false)
const form = ref({ name: '', split_ratio: '50/50', metric: 'latency', provider_a_id: null, provider_b_id: null })
const resultsCache = ref({})

const canCreate = computed(() => {
  return form.value.name
    && form.value.provider_a_id
    && form.value.provider_b_id
    && form.value.provider_a_id !== form.value.provider_b_id
})
function getResults(id) { return resultsCache.value[id] }
function providerName(pid) {
  if (!pid) return ''
  const p = providers.value.find(x => x.id === pid)
  return p ? p.name : ''
}
function metricLabel(m) {
  return { latency: '延迟优先', accuracy: '准确率优先', success: '综合分' }[m] || m || '-'
}
function winnerLabel(w) {
  return {
    a: '⬅ A 胜出',
    b: 'B 胜出 ➡',
    inconclusive: '效果相近',
    insufficient_data: '数据不足',
  }[w] || w
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([loadProviders(), loadTests()])
  } finally { loading.value = false }
}
async function loadTests() {
  try {
    const data = await request.get('/agent/api/ab-test/configs')
    tests.value = data.items || []
    tests.value.forEach(t => loadResults(t.id))
  } catch (e) { ElMessage.error('加载失败: ' + (e.message || e)) }
}
async function loadProviders() {
  try {
    const data = await request.get('/ai/api/providers')
    providers.value = data.providers || []
  } catch (e) { ElMessage.error('加载 Provider 失败: ' + (e.message || e)) }
}
async function loadResults(id) {
  try {
    const data = await request.get('/agent/api/ab-test/results/' + id)
    resultsCache.value[id] = data
  } catch (e) {
    ElMessage.warning(`加载实验 #${id} 结果失败: ` + (e.message || e))
  }
}
async function viewDetail(t) {
  detailTest.value = t
  detailResult.value = null
  showDetail.value = true
  try {
    detailResult.value = await request.get('/agent/api/ab-test/results/' + t.id)
  } catch (e) {
    ElMessage.error('加载详情失败: ' + (e.message || e))
  }
}
async function createTest() {
  try {
    await request.post('/agent/api/ab-test/configs', { ...form.value, status: 'active' })
    ElMessage.success('实验已创建并启动')
    showCreate.value = false
    loadTests()
  } catch (e) { ElMessage.error('创建失败: ' + (e.message || e)) }
}
async function stopTest(t) {
  try {
    await request.put('/agent/api/ab-test/configs/' + t.id, { status: 'stopped' })
    ElMessage.success('实验已停止')
    loadTests()
  } catch (e) { ElMessage.error('操作失败: ' + (e.message || e)) }
}
async function startTest(t) {
  try {
    await request.put('/agent/api/ab-test/configs/' + t.id, { status: 'active' })
    ElMessage.success('实验已启动（其他运行中的实验已自动停止）')
    loadTests()
  } catch (e) { ElMessage.error('操作失败: ' + (e.message || e)) }
}
async function deleteTest(t) {
  try {
    await ElMessageBox.confirm(`确认删除实验「${t.name}」？所有关联记录将一并删除。`, '确认删除', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch (e) { return }
  try {
    await request.delete('/agent/api/ab-test/configs/' + t.id)
    ElMessage.success('已删除')
    loadTests()
  } catch (e) { ElMessage.error('删除失败: ' + (e.message || e)) }
}
onMounted(loadAll)
</script>

<style scoped>
.ab-page { padding: 4px; }
.page-header { margin-bottom: 12px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; margin: 0 0 4px; }
.page-header p { color: var(--text-secondary,#64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong,rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid,#fff); cursor: pointer; font-size: 0.82rem; }
.btn-primary { background: var(--accent,#6366f1); color: #fff; border-color: var(--accent,#6366f1); }
.btn-danger { background: #ef4444; color: #fff; border-color: #ef4444; }
.btn-ghost { background: transparent; color: var(--text-secondary,#64748b); }
.btn-sm { padding: 3px 8px; font-size: 0.75rem; }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.input { padding: 5px 10px; border: 1px solid var(--border,rgba(0,0,0,0.1)); border-radius: 6px; font-size: 0.82rem; outline: none; width: 100%; box-sizing: border-box; }
.input:focus { border-color: var(--accent,#6366f1); }
.panel { background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; margin-bottom: 14px; }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; }
.panel-body { padding: 16px 18px; }
.test-item { border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; padding: 14px; margin-bottom: 12px; }
.test-item.active { border-left: 3px solid #22c55e; }
.test-item.stopped { border-left: 3px solid #94a3b8; }
.test-head { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
.test-name { font-weight: 600; font-size: 0.95rem; }
.status-badge { padding: 2px 8px; border-radius: 6px; font-size: 0.72rem; font-weight: 600; }
.status-badge.active { background: rgba(34,197,94,0.12); color: #22c55e; }
.status-badge.stopped { background: rgba(148,163,184,0.15); color: #64748b; }
.split-tag, .metric-tag { padding: 2px 8px; border-radius: 6px; font-size: 0.72rem; background: rgba(99,102,241,0.08); color: #6366f1; }
.test-body { margin-bottom: 10px; }
.model-col { display: flex; align-items: center; gap: 12px; }
.model-a, .model-b { flex: 1; padding: 10px; border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 8px; }
.model-a { background: rgba(99,102,241,0.04); }
.model-b { background: rgba(20,184,166,0.04); }
.model-label { display: block; font-size: 0.72rem; color: var(--text-secondary,#64748b); margin-bottom: 2px; }
.model-name { display: block; font-weight: 600; font-size: 0.9rem; }
.model-sub { display: block; font-size: 0.72rem; color: var(--text-tertiary,#94a3b8); margin-top: 2px; }
.vs { font-weight: 700; color: var(--text-tertiary,#94a3b8); font-size: 0.78rem; }
.test-results { display: flex; align-items: center; gap: 12px; padding: 10px; background: var(--bg-hover,rgba(0,0,0,0.02)); border-radius: 8px; margin-bottom: 10px; }
.result-a, .result-b { flex: 1; text-align: center; }
.res-rate { font-size: 1.2rem; font-weight: 700; color: var(--accent,#6366f1); }
.res-latency { font-size: 0.75rem; color: var(--text-secondary,#64748b); margin-top: 2px; }
.res-count { font-size: 0.72rem; color: var(--text-tertiary,#94a3b8); }
.winner-badge { padding: 4px 10px; border-radius: 6px; background: rgba(245,158,11,0.12); color: #f59e0b; font-size: 0.78rem; font-weight: 600; }
.test-results-empty { padding: 10px; text-align: center; color: var(--text-tertiary,#94a3b8); font-size: 0.82rem; background: var(--bg-hover,rgba(0,0,0,0.02)); border-radius: 8px; margin-bottom: 10px; }
.test-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary,#94a3b8); font-size: 0.9rem; }
.form-group { margin-bottom: 10px; }
.form-label { display: block; font-size: 0.78rem; font-weight: 600; color: var(--text-secondary,#64748b); margin-bottom: 4px; }
.form-error { color: #ef4444; font-size: 0.78rem; margin-bottom: 10px; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid,#fff); border-radius: 12px; padding: 24px; min-width: 480px; box-shadow: 0 8px 32px rgba(0,0,0,0.15); }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; font-weight: 600; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.table th { text-align: left; padding: 6px 8px; border-bottom: 2px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; color: var(--text-secondary,#64748b); font-size: 0.72rem; }
.table td { padding: 8px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.05)); }
.detail-row { display: flex; gap: 8px; padding: 6px 0; font-size: 0.85rem; }
.detail-row span { color: var(--text-secondary,#64748b); min-width: 80px; }
</style>
