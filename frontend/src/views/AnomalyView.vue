<template>
  <div class="anomaly-page">
    <div class="page-header">
      <h1>异常检测</h1>
      <p>支持 3σ / EWMA / STL / MAD / Prophet / LSTM / Transformer 算法 · 共 {{ total }} 个配置</p>
    </div>

    <div class="compare-banner">
      <span class="compare-banner-icon">💡</span>
      <div class="compare-banner-body">
        <div class="compare-banner-title">本页是「动态基线异常检测」—— 根据历史数据自动算正常区间，偏离即报</div>
        <div class="compare-banner-desc">
          适合"不知道正常值多少，但行为反常就要报"这种未知异常场景。如果知道明确的危险线（如磁盘>90%），请用
          <span class="compare-banner-link" @click="goRules">告警规则 →</span>
        </div>
      </div>
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
              <td><span class="badge algo" :class="c.algorithm">{{ algoLabel(c.algorithm) }}</span></td>
              <td>{{ c.sensitivity }}</td>
              <td>{{ c.window_size }}</td>
              <td><span class="badge" :class="c.enabled ? 'resolved' : 'info'">{{ c.enabled ? '运行中' : '已暂停' }}</span></td>
              <td>
                <button class="btn btn-sm" @click="openEdit(c)">编辑</button>
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

    <div class="info-banner">
      <strong>先判断：你的指标有没有"危险线"？</strong>
      磁盘 &gt;90%、内存 &gt;85%、CPU &gt;90% 这种<strong>有明确危险线</strong>的指标，请去「告警规则」配固定阈值，<strong>不要用本页自适应检测</strong>（否则开机/正常波动会误报）。
      本页只用于<strong>不知道正常值是多少</strong>的指标（请求延迟、错误率、连接数、新业务指标等）。
    </div>

    <div class="info-cards">
      <div class="info-card">
        <h4>3σ (Z-Score)</h4>
        <p class="card-desc">适合<strong>上下波动、无趋势</strong>的指标，如请求延迟、网络抖动。σ 大时能容忍正常波动，只有大幅偏离才告警。</p>
        <p class="card-note">⚠️ 不适合磁盘/内存等<strong>单调递增或平稳</strong>指标，σ 极小 → 微小上涨就误报。</p>
        <p class="card-tip">小白选它：指标忽高忽低，突然跳到离谱值——用 3σ</p>
      </div>
      <div class="info-card">
        <h4>EWMA</h4>
        <p class="card-desc">适合<strong>缓慢漂移、无固定危险线</strong>的指标，如连接数、流量。给近期数据更高权重，基线跟得上变化。</p>
        <p class="card-note">⚠️ 磁盘/内存有明确危险线（90%/85%），应配固定阈值，不适用本页。</p>
        <p class="card-tip">小白选它：指标慢慢涨、你又说不清多少算高——用 EWMA</p>
      </div>
      <div class="info-card">
        <h4>STL 分解</h4>
        <p class="card-desc">适合<strong>有规律周期</strong>的指标，如每天/每周固定的业务高峰低谷。把趋势和季节分离开，只看残差。</p>
        <p class="card-note">✅ 需要设置周期数（period），比如 24h 周期的指标设 period=24。</p>
        <p class="card-tip">小白选它：每天同一时间指标都会涨——用 STL</p>
      </div>
      <div class="info-card">
        <h4>MAD</h4>
        <p class="card-desc">适合<strong>经常有小毛刺</strong>的指标。比 3σ 更不怕极端值干扰，偶尔飙一下不会被拉偏基线。</p>
        <p class="card-note">✅ 3σ 误报太多时换 MAD 试试，往往能少告一半。</p>
        <p class="card-tip">小白选它：数据经常有杂毛，但不想被烦死——用 MAD</p>
      </div>
      <div class="info-card">
        <h4>Prophet</h4>
        <p class="card-desc">适合<strong>强周期性 + 节假日效应</strong>的业务指标，如日活、订单量。自动拟合多种周期和假期影响。</p>
        <p class="card-note">⚠️ 需要较多历史数据，开机初期不要用。</p>
        <p class="card-tip">小白选它：指标有周末/节假日规律——用 Prophet</p>
      </div>
      <div class="info-card">
        <h4>LSTM (IForest)</h4>
        <p class="card-desc">适合<strong>短序列中的多维异常</strong>，通过滑动窗口构建特征，用 IsolationForest 判断孤立点。</p>
        <p class="card-note">⚠️ 需要至少 15 条数据，窗口自动计算。资源消耗稍大。</p>
        <p class="card-tip">小白选它：想试试"AI 算法"但不知道用啥——试试 LSTM</p>
      </div>
      <div class="info-card">
        <h4>Transformer (LOF)</h4>
        <p class="card-desc">适合<strong>多变量关联场景</strong>，通过密度聚类检测异常。与 LSTM 类似但用 LOF 算法。</p>
        <p class="card-note">⚠️ 需要至少 15 条数据，不适合平稳指标。</p>
        <p class="card-tip">小白选它：上面几个都不好使的时候——试试这个兜底</p>
      </div>
    </div>

    <div v-if="createVisible" class="modal-overlay" @click.self="createVisible = false">
      <div class="modal-box">
        <div class="modal-header">
          <h3>{{ editId ? '编辑检测配置' : '新增检测配置' }}</h3>
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
            <button class="btn btn-primary" @click="createConfig" :disabled="creating">{{ creating ? '保存中...' : (editId ? '保存' : '创建') }}</button>
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
const editId = ref(null)
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
  editId.value = null
  Object.assign(form, { name: '', metric_name: 'cpu_usage', algorithm: 'sigma', sensitivity: 3.0, window_size: 20, period: 12 })
  createVisible.value = true
}

function openEdit(c) {
  editId.value = c.id
  Object.assign(form, {
    name: c.name, metric_name: c.metric_name, algorithm: c.algorithm,
    sensitivity: c.sensitivity, window_size: c.window_size, period: c.period || 12,
  })
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
    if (editId.value) {
      await request.post(`/anomaly/api/configs/${editId.value}/update`, fd)
      ElMessage.success('保存成功')
    } else {
      await request.post('/anomaly/api/configs/create', fd)
      ElMessage.success('创建成功')
    }
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

const algoLabels = {
  sigma: '3σ',
  ewma: 'EWMA',
  stl: 'STL',
  mad: 'MAD',
  prophet: 'Prophet',
  lstm: 'LSTM',
  transformer: 'Transformer',
}
function algoLabel(algo) {
  return algoLabels[algo] || algo
}

onMounted(() => {
  loadConfigs()
  loadMetrics()
})

function goRules() {
  if (window._navigateTo) window._navigateTo('alert-rules')
}
</script>

<style scoped>
.anomaly-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.compare-banner { display: flex; gap: 10px; align-items: flex-start; background: rgba(99,102,241,0.06); border: 1px solid rgba(99,102,241,0.18); border-left: 3px solid var(--accent, #6366f1); border-radius: 8px; padding: 10px 14px; margin-bottom: 16px; }
.compare-banner-icon { font-size: 1.1rem; line-height: 1.4; }
.compare-banner-body { flex: 1; }
.compare-banner-title { font-size: 0.85rem; font-weight: 600; color: var(--text, #1e293b); margin-bottom: 2px; }
.compare-banner-desc { font-size: 0.78rem; color: var(--text-secondary, #64748b); line-height: 1.5; }
.compare-banner-link { color: var(--accent, #6366f1); cursor: pointer; font-weight: 600; }
.compare-banner-link:hover { text-decoration: underline; }
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
.info-banner { background: rgba(245,158,11,0.08); border: 1px solid rgba(245,158,11,0.2); border-left: 3px solid #f59e0b; border-radius: 8px; padding: 12px 16px; margin-top: 16px; font-size: 0.82rem; color: var(--text, #1e293b); line-height: 1.6; }
.info-banner strong { color: #d97706; }
.info-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; margin-top: 12px; }
.info-card { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; padding: 14px; }
.info-card h4 { margin: 0 0 6px; font-size: 0.9rem; color: var(--accent, #6366f1); }
.info-card .card-desc { margin: 0 0 6px; font-size: 0.78rem; color: var(--text, #1e293b); line-height: 1.5; }
.info-card .card-note { margin: 0 0 6px; font-size: 0.72rem; color: #d97706; line-height: 1.4; }
.info-card .card-tip { margin: 0; font-size: 0.72rem; color: var(--text-secondary, #64748b); line-height: 1.4; font-style: italic; }
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
