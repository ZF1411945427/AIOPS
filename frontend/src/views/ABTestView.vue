<template>
  <div class="ab-page">
    <div class="page-header">
      <h1>A/B 测试框架</h1>
      <p>多模型效果对比 · 分流比例可控 · 实时统计胜出组</p>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="showCreate = true">+ 新建实验</button>
      <button class="btn" @click="loadTests">刷新</button>
    </div>

    <div class="panel">
      <div class="panel-head">实验配置</div>
      <div class="panel-body">
        <div v-if="tests.length" class="test-list">
          <div v-for="t in tests" :key="t.id" class="test-item" :class="t.status">
            <div class="test-head">
              <span class="test-name">{{ t.name }}</span>
              <span class="status-badge" :class="t.status">{{ t.status === 'active' ? '运行中' : t.status }}</span>
              <span class="split-tag">{{ t.split_ratio }}</span>
            </div>
            <div class="test-body">
              <div class="model-col">
                <div class="model-a">
                  <span class="model-label">A 组</span>
                  <span class="model-name">{{ t.model_a || ('Provider #' + t.provider_a_id) }}</span>
                </div>
                <div class="vs">VS</div>
                <div class="model-b">
                  <span class="model-label">B 组</span>
                  <span class="model-name">{{ t.model_b || ('Provider #' + t.provider_b_id) }}</span>
                </div>
              </div>
            </div>
            <div v-if="getResults(t.id)" class="test-results">
              <div class="result-a">
                <div class="res-rate">{{ getResults(t.id).group_a.success_rate || 0 }}%</div>
                <div class="res-latency">延迟 {{ getResults(t.id).group_a.avg_latency_ms || 0 }}ms</div>
              </div>
              <div class="winner-badge" v-if="getResults(t.id).winner !== 'insufficient_data'">
                {{ getResults(t.id).winner === 'a' ? '⬅ A 胜出' : getResults(t.id).winner === 'b' ? 'B 胜出 ➡' : '效果相近' }}
              </div>
              <div class="result-b">
                <div class="res-rate">{{ getResults(t.id).group_b.success_rate || 0 }}%</div>
                <div class="res-latency">延迟 {{ getResults(t.id).group_b.avg_latency_ms || 0 }}ms</div>
              </div>
            </div>
            <div class="test-actions">
              <button class="btn btn-sm" @click="loadResults(t.id)">查看详情</button>
              <button class="btn btn-sm btn-ghost" @click="stopTest(t)">停止</button>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">暂无实验配置</div>
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
          <label class="form-label">分流比例</label>
          <select v-model="form.split_ratio" class="input">
            <option value="50/50">50/50</option>
            <option value="70/30">70/30</option>
            <option value="80/20">80/20</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">指标</label>
          <select v-model="form.metric" class="input">
            <option value="latency">延迟优先</option>
            <option value="accuracy">准确率优先</option>
            <option value="success">成功率优先</option>
          </select>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" @click="createTest">创建</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const tests = ref([])
const showCreate = ref(false)
const form = ref({ name: '', split_ratio: '50/50', metric: 'latency', provider_a_id: null, provider_b_id: null })
const resultsCache = ref({})

function getResults(id) { return resultsCache.value[id] }

async function loadTests() {
  try {
    const data = await request.get('/agent/api/ab-test/configs')
    tests.value = data.items || []
  } catch (e) { ElMessage.error('加载失败: ' + (e.message || e)) }
}

async function loadResults(id) {
  try {
    const data = await request.get('/agent/api/ab-test/results/' + id)
    resultsCache.value[id] = data
  } catch (e) { ElMessage.error('加载失败: ' + (e.message || e)) }
}

async function createTest() {
  try {
    await request.post('/agent/api/ab-test/configs', form.value)
    ElMessage.success('实验已创建')
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

onMounted(() => loadTests())
</script>

<style scoped>
.ab-page { padding: 4px; }
.page-header { margin-bottom: 12px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; margin: 0 0 4px; }
.page-header p { color: var(--text-secondary,#64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong,rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid,#fff); cursor: pointer; font-size: 0.82rem; }
.btn-primary { background: var(--accent,#6366f1); color: #fff; border-color: var(--accent,#6366f1); }
.btn-sm { padding: 3px 10px; font-size: 0.75rem; }
.btn-ghost { background: transparent; border-color: var(--border-strong,rgba(0,0,0,0.12)); color: var(--text-secondary,#64748b); }
.panel { background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; margin-bottom: 14px; }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border,rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; }
.panel-body { padding: 16px 18px; }
.test-list { display: flex; flex-direction: column; gap: 12px; }
.test-item { border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 8px; padding: 14px; }
.test-item.active { border-color: #6366f1; border-left: 3px solid #6366f1; }
.test-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.test-name { font-weight: 600; font-size: 0.9rem; flex: 1; }
.status-badge { font-size: 0.7rem; font-weight: 600; padding: 2px 8px; border-radius: 8px; }
.status-badge.active { background: rgba(34,197,94,0.12); color: #22c55e; }
.status-badge.stopped { background: rgba(148,163,184,0.12); color: #64748b; }
.split-tag { font-size: 0.72rem; background: rgba(99,102,241,0.08); color: #6366f1; padding: 1px 6px; border-radius: 4px; }
.test-body { margin-bottom: 10px; }
.model-col { display: flex; align-items: center; gap: 12px; }
.model-a, .model-b { flex: 1; background: rgba(99,102,241,0.06); border-radius: 6px; padding: 8px 12px; }
.model-label { font-size: 0.7rem; color: var(--text-secondary,#64748b); display: block; }
.model-name { font-size: 0.82rem; font-weight: 600; }
.vs { font-size: 0.75rem; color: var(--text-tertiary,#94a3b8); font-weight: 700; }
.test-results { display: flex; align-items: center; gap: 12px; padding: 10px; background: var(--bg-hover,rgba(0,0,0,0.02)); border-radius: 6px; margin-bottom: 10px; }
.result-a, .result-b { flex: 1; text-align: center; }
.res-rate { font-size: 1.2rem; font-weight: 800; }
.res-latency { font-size: 0.72rem; color: var(--text-secondary,#64748b); }
.winner-badge { font-size: 0.78rem; font-weight: 700; color: #6366f1; background: rgba(99,102,241,0.08); padding: 4px 10px; border-radius: 8px; }
.test-actions { display: flex; gap: 8px; }
.form-group { margin-bottom: 12px; }
.form-label { display: block; font-size: 0.78rem; font-weight: 600; color: var(--text-secondary,#64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border,rgba(0,0,0,0.1)); border-radius: 6px; font-size: 0.82rem; box-sizing: border-box; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid,#fff); border-radius: 12px; padding: 24px 28px; min-width: 420px; max-width: 520px; box-shadow: 0 8px 32px rgba(0,0,0,0.15); }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; font-weight: 600; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.empty-state { text-align: center; padding: 32px; color: var(--text-tertiary,#94a3b8); font-size: 0.9rem; }
</style>
