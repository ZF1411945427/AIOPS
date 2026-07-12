<template>
  <div class="anomaly-page">
    <div class="page-header">
      <h1>异常检测</h1>
      <p>支持 3σ / EWMA / STL / MAD / Prophet / LSTM / Transformer 算法 · 共 {{ total }} 个配置</p>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="openCreate">+ 新增检测配置</button>
      <button class="btn" @click="loadConfigs">刷新</button>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="configs.length" class="table">
          <thead>
            <tr>
              <th>名称</th><th>指标</th><th>算法</th><th>灵敏度</th>
              <th>窗口</th><th>状态</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in configs" :key="c.id">
              <td>{{ c.name }}</td>
              <td>{{ c.metric_name }}</td>
              <td><span class="badge algo" :class="c.algorithm">{{ c.algorithm }}</span></td>
              <td>{{ c.sensitivity }}</td>
              <td>{{ c.window_size }}</td>
              <td><span class="badge" :class="c.enabled ? 'resolved' : 'info'">{{ c.enabled ? '运行中' : '已暂停' }}</span></td>
              <td>
                <button class="btn btn-sm" @click="toggleConfig(c)">{{ c.enabled ? '暂停' : '启动' }}</button>
                <button class="btn btn-sm btn-danger" @click="deleteConfig(c)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">📈</div>
          <div>暂无检测配置，点击"新增检测配置"添加</div>
        </div>
      </div>
    </div>

    <div class="info-cards">
      <div class="info-card"><h4>3σ 检测</h4><p>基于均值和标准差，值偏离均值超过 N 倍标准差判定为异常。适用于正态分布数据。</p></div>
      <div class="info-card"><h4>EWMA 检测</h4><p>指数加权移动平均，对近期数据更敏感，通过残差判定异常。适用于趋势性数据。</p></div>
      <div class="info-card"><h4>STL 分解</h4><p>将时序分解为趋势+季节+残差，残差异常判定。适用于周期性数据。</p></div>
      <div class="info-card"><h4>MAD 检测</h4><p>中位数绝对偏差，对极端值鲁棒，通过修正 Z 分数判定异常。适用于非正态分布或含离群点数据。</p></div>
      <div class="info-card"><h4>Prophet</h4><p>Facebook 时序预测模型，自动拟合趋势+季节性，预测区间外的值判定为异常。适用于强周期性业务指标。</p></div>
      <div class="info-card"><h4>LSTM</h4><p>滑动窗口线性预测模拟 LSTM 行为，通过预测残差与动态阈值比较判定异常。适用于短序列趋势预测。</p></div>
      <div class="info-card"><h4>Transformer</h4><p>基于自注意力机制，通过注意力权重重建序列，残差超过动态阈值判定为异常。适用于多变量关联时序。</p></div>
    </div>

    <div v-if="createVisible" class="modal-overlay" @click.self="createVisible = false">
      <div class="modal-box">
        <div class="modal-header">
          <h3>新增检测配置</h3>
          <button class="modal-close" @click="createVisible = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>名称</label>
            <input v-model="form.name" placeholder="如：CPU 异常检测" />
          </div>
          <div class="form-group">
            <label>指标</label>
            <select v-model="form.metric_name">
              <option v-for="m in metrics" :key="m" :value="m">{{ m }}</option>
              <option v-if="!metrics.length" value="cpu_usage">cpu_usage</option>
            </select>
          </div>
          <div class="form-group">
            <label>算法</label>
            <select v-model="form.algorithm">
              <option value="sigma">3σ (标准差)</option>
              <option value="ewma">EWMA (指数加权移动平均)</option>
              <option value="stl">STL (季节分解)</option>
              <option value="mad">MAD (中位数绝对偏差)</option>
              <option value="prophet">Prophet</option>
              <option value="lstm">LSTM</option>
              <option value="transformer">Transformer</option>
            </select>
          </div>
          <div class="form-group">
            <label>灵敏度</label>
            <input v-model.number="form.sensitivity" type="number" step="0.1" />
          </div>
          <div class="form-group">
            <label>窗口大小</label>
            <input v-model.number="form.window_size" type="number" />
          </div>
          <div v-if="form.algorithm === 'stl'" class="form-group">
            <label>周期数</label>
            <input v-model.number="form.period" type="number" />
          </div>
          <div class="form-actions">
            <button class="btn" @click="createVisible = false">取消</button>
            <button class="btn btn-primary" @click="createConfig" :disabled="creating">{{ creating ? '创建中...' : '创建' }}</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const configs = ref([])
const total = ref(0)
const metrics = ref([])
const createVisible = ref(false)
const creating = ref(false)
const form = reactive({
  name: '', metric_name: 'cpu_usage', algorithm: 'sigma',
  sensitivity: 3.0, window_size: 20, period: 12,
})

async function loadMetrics() {
  try {
    const data = await request.get('/anomaly/api/metrics')
    metrics.value = data.metrics || []
    if (metrics.value.length && !metrics.value.includes(form.metric_name)) {
      form.metric_name = metrics.value[0]
    }
  } catch (e) {
    // 降级使用默认值
  }
}

async function loadConfigs() {
  loading.value = true
  try {
    const data = await request.get('/anomaly/api/list')
    configs.value = data.configs || []
    total.value = data.total || 0
  } catch (e) {
    ElMessage.error('加载配置失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, { name: '', metric_name: 'cpu_usage', algorithm: 'sigma', sensitivity: 3.0, window_size: 20, period: 12 })
  createVisible.value = true
}

async function createConfig() {
  if (!form.name) {
    ElMessage.warning('请填写名称')
    return
  }
  creating.value = true
  try {
    const fd = new FormData()
    fd.append('name', form.name)
    fd.append('metric_name', form.metric_name)
    fd.append('asset_id', 0)
    fd.append('algorithm', form.algorithm)
    fd.append('sensitivity', form.sensitivity)
    fd.append('window_size', form.window_size)
    fd.append('period', form.period)
    await request.post('/anomaly/api/configs/create', fd)
    ElMessage.success('创建成功')
    createVisible.value = false
    loadConfigs()
  } catch (e) {
    ElMessage.error('创建失败: ' + e.message)
  } finally {
    creating.value = false
  }
}

async function toggleConfig(c) {
  try {
    await request.post(`/anomaly/api/configs/${c.id}/toggle`)
    ElMessage.success(c.enabled ? '已暂停' : '已启动')
    loadConfigs()
  } catch (e) {
    ElMessage.error('操作失败: ' + e.message)
  }
}

async function deleteConfig(c) {
  try {
    await ElMessageBox.confirm(`确认删除配置"${c.name}"？`, '删除确认')
    await request.post(`/anomaly/api/configs/${c.id}/delete`)
    ElMessage.success('已删除')
    loadConfigs()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

onMounted(() => {
  loadConfigs()
  loadMetrics()
})
</script>

<style scoped>
.anomaly-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; transition: all 0.2s; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.btn-danger { color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-danger:hover { background: rgba(239,68,68,0.08); }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 16px; }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.algo { background: rgba(99,102,241,0.1); color: #6366f1; }
.badge.resolved { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.info { background: rgba(100,116,139,0.1); color: #64748b; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.info-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin-top: 16px; }
.info-card { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; padding: 14px; }
.info-card h4 { margin: 0 0 6px; font-size: 0.9rem; color: var(--accent, #6366f1); }
.info-card p { margin: 0; font-size: 0.78rem; color: var(--text-secondary, #64748b); line-height: 1.5; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 12px; width: 90%; max-width: 520px; max-height: 85vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.2); }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.modal-header h3 { margin: 0; font-size: 1.1rem; }
.modal-close { background: none; border: none; font-size: 24px; cursor: pointer; color: var(--text-secondary, #64748b); line-height: 1; }
.modal-body { padding: 20px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 0.8rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.form-group input, .form-group select { width: 100%; padding: 8px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.85rem; box-sizing: border-box; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
