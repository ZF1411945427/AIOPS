<template>
  <div class="pm-page">
    <div class="page-header">
      <h1>预测模型</h1>
      <p>时序预测模型配置 · 共 {{ total }} 个模型</p>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="openCreate">+ 新建模型</button>
      <button class="btn btn-success" @click="predictAll">运行全部预测</button>
      <button class="btn" @click="showLogic = true">逻辑说明</button>
      <button class="btn" @click="loadModels">刷新</button>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="models.length" class="card-grid">
          <div v-for="m in models" :key="m.id" class="model-card">
            <div class="card-top">
              <span class="model-name">{{ m.name }}</span>
              <span class="badge" :class="m.enabled ? 'on' : 'off'">{{ m.enabled ? '启用' : '禁用' }}</span>
            </div>
            <div class="card-meta">
              <div><span class="meta-label">指标</span><span>{{ m.metric_name || '-' }}</span></div>
              <div><span class="meta-label">类型</span><span class="badge type">{{ typeLabel(m.model_type) }}</span></div>
              <div><span class="meta-label">资产ID</span><span>{{ m.asset_id || '全局' }}</span></div>
              <div><span class="meta-label">参数</span><span class="text-sm">{{ m.params }}</span></div>
            </div>
            <div class="card-actions">
              <button class="btn btn-sm btn-primary" @click="predictModel(m)">预测</button>
              <button class="btn btn-sm" @click="toggleModel(m)">{{ m.enabled ? '禁用' : '启用' }}</button>
              <button class="btn btn-sm btn-danger" @click="deleteModel(m)">删除</button>
            </div>
          </div>
        </div>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">📈</div><div>暂无预测模型</div></div>
        <div v-if="total > 0" style="display:flex;justify-content:flex-end;padding:12px 0">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :page-sizes="[20, 50, 100]"
            :total="total"
            layout="total, sizes, prev, pager, next"
            small
            @size-change="loadModels"
            @current-change="loadModels"
          />
        </div>
      </div>
    </div>

    <div v-if="showDialog" class="modal-overlay" @click.self="showDialog = false">
      <div class="modal-box">
        <h3>新建预测模型</h3>
        <div class="form-row"><label>名称</label><input v-model="form.name" class="input"></div>
        <div class="form-row"><label>指标名</label><input v-model="form.metric_name" class="input"></div>
        <div class="form-row"><label>资产 ID（可选）</label><input v-model.number="form.asset_id" type="number" class="input"></div>
        <div class="form-row"><label>模型类型</label>
          <select v-model="form.model_type" class="input">
            <option value="linear">线性回归</option>
            <option value="polynomial">多项式</option>
            <option value="rolling_avg">移动平均</option>
          </select>
        </div>
        <div class="form-row"><label>参数 JSON</label><input v-model="form.params" class="input" placeholder='{"window": 20}'></div>
        <div class="modal-actions">
          <button class="btn" @click="showDialog = false">取消</button>
          <button class="btn btn-primary" @click="createModel">创建</button>
        </div>
      </div>
    </div>

    <el-dialog v-model="showLogic" title="预测模型 - 逻辑说明" width="600px">
      <div style="font-size:13px;line-height:1.8">
        <h4 style="margin:0 0 8px">什么是预测模型？</h4>
        <p>预测模型是基于历史时序数据，通过数学算法<strong>预测未来趋势</strong>的工具。在 AIOps 中用于异常检测、容量规划、故障预警等场景。</p>
        
        <h4 style="margin:16px 0 8px">在 AIOps 中的作用</h4>
        <ul style="margin:0;padding-left:20px">
          <li><strong>异常检测</strong>：预测正常范围，超出即告警（如 CPU 突增）</li>
          <li><strong>趋势预测</strong>：预测未来 N 小时的指标走势（如磁盘使用率）</li>
          <li><strong>容量规划</strong>：预测资源何时耗尽，提前扩容</li>
          <li><strong>故障预警</strong>：基于历史模式预测潜在故障</li>
        </ul>

        <h4 style="margin:16px 0 8px">模型类型说明</h4>
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <tr style="background:#f5f5f5"><td style="padding:6px;border:1px solid #ddd;font-weight:600">类型</td><td style="padding:6px;border:1px solid #ddd;font-weight:600">原理</td><td style="padding:6px;border:1px solid #ddd;font-weight:600">适用场景</td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd">线性回归</td><td style="padding:6px;border:1px solid #ddd">用直线拟合数据趋势</td><td style="padding:6px;border:1px solid #ddd">稳定增长/下降的指标</td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd">多项式</td><td style="padding:6px;border:1px solid #ddd">用曲线拟合非线性趋势</td><td style="padding:6px;border:1px solid #ddd">波动较大的指标</td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd">移动平均</td><td style="padding:6px;border:1px solid #ddd">计算滑动窗口均值</td><td style="padding:6px;border:1px solid #ddd">消除噪声、平滑数据</td></tr>
        </table>

        <h4 style="margin:16px 0 8px">操作流程</h4>
        <ol style="margin:0;padding-left:20px">
          <li><strong>新建模型</strong>：选择指标、模型类型、配置参数</li>
          <li><strong>启用模型</strong>：激活后开始实时计算预测值</li>
          <li><strong>查看结果</strong>：在监控图表中叠加预测曲线</li>
          <li><strong>调优参数</strong>：根据预测准确度调整窗口大小等参数</li>
        </ol>

        <h4 style="margin:16px 0 8px">参数说明</h4>
        <ul style="margin:0;padding-left:20px">
          <li><code>window</code>：移动平均的窗口大小（如 20 表示取最近 20 个点的均值）</li>
          <li><code>degree</code>：多项式的阶数（如 2 表示二次曲线）</li>
          <li><code>threshold</code>：异常判定阈值（如 2.0 表示超过 2 倍标准差为异常）</li>
        </ul>
      </div>
    </el-dialog>

    <el-dialog v-model="showResult" title="预测结果" width="800px">
      <div v-if="predictionResult" style="font-size:13px">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
          <div class="result-item">
            <span class="result-label">指标</span>
            <span class="result-value">{{ predictionResult.metric_name }}</span>
          </div>
          <div class="result-item">
            <span class="result-label">当前值</span>
            <span class="result-value">{{ predictionResult.current_value?.toFixed(2) }}</span>
          </div>
          <div class="result-item">
            <span class="result-label">趋势</span>
            <span class="result-value" :class="'trend-' + predictionResult.trend">{{ trendLabel(predictionResult.trend) }}</span>
          </div>
          <div class="result-item">
            <span class="result-label">数据点</span>
            <span class="result-value">{{ predictionResult.data_points }}</span>
          </div>
          <div class="result-item">
            <span class="result-label">R²</span>
            <span class="result-value">{{ predictionResult.r2?.toFixed(4) }}</span>
          </div>
          <div v-if="predictionResult.days_until_threshold" class="result-item">
            <span class="result-label">预计达到阈值</span>
            <span class="result-value warning">{{ predictionResult.days_until_threshold }} 天</span>
          </div>
        </div>

        <div style="margin-bottom:16px">
          <h4 style="margin:0 0 8px">特征数据</h4>
          <div v-if="Object.keys(predictionResult.features || {}).length" style="display:flex;gap:12px;flex-wrap:wrap">
            <div v-for="(v, k) in predictionResult.features" :key="k" class="feature-tag">
              <span class="feature-name">{{ k }}</span>
              <span class="feature-value">{{ v.value?.toFixed(2) }}</span>
            </div>
          </div>
          <div v-else style="color:#94a3b8">暂无特征数据</div>
        </div>

        <div>
          <h4 style="margin:0 0 8px">预测曲线（未来 48 小时）</h4>
          <div style="background:#f8f9fa;border-radius:8px;padding:12px;max-height:300px;overflow-y:auto">
            <table style="width:100%;border-collapse:collapse;font-size:11px">
              <thead>
                <tr style="background:#e5e7eb">
                  <th style="padding:4px 8px;text-align:left">时间</th>
                  <th style="padding:4px 8px;text-align:right">预测值</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(ts, i) in predictionResult.prediction?.timestamps?.slice(0, 24)" :key="i">
                  <td style="padding:4px 8px;border-bottom:1px solid #e5e7eb">{{ formatTime(ts) }}</td>
                  <td style="padding:4px 8px;text-align:right;border-bottom:1px solid #e5e7eb">{{ predictionResult.prediction.values[i]?.toFixed(2) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const models = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const showDialog = ref(false)
const showLogic = ref(false)
const showResult = ref(false)
const predictionResult = ref(null)
const form = ref({ name: '', metric_name: '', asset_id: 0, model_type: 'linear', params: '{"window": 20}' })

function typeLabel(t) {
  return { linear: '线性回归', polynomial: '多项式', rolling_avg: '移动平均' }[t] || t
}

function trendLabel(t) {
  return { increasing: '上升趋势 ↑', decreasing: '下降趋势 ↓', stable: '稳定 →' }[t] || t
}

function formatTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

async function loadModels() {
  loading.value = true
  try {
    const data = await request.get('/prediction-models/api/list', { params: { page: page.value, page_size: pageSize.value } })
    models.value = data.models || []
    total.value = data.total || 0
  } catch (e) {
    ElMessage.error('加载失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.value = { name: '', metric_name: '', asset_id: 0, model_type: 'linear', params: '{"window": 20}' }
  showDialog.value = true
}

async function createModel() {
  if (!form.value.name || !form.value.metric_name) {
    ElMessage.warning('名称和指标不能为空')
    return
  }
  try {
    await request.post('/prediction-models/api/create', form.value)
    ElMessage.success('创建成功')
    showDialog.value = false
    loadModels()
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.message || e))
  }
}

async function toggleModel(m) {
  try {
    await request.post(`/prediction-models/api/${m.id}/toggle`)
    loadModels()
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.message || e))
  }
}

async function deleteModel(m) {
  try {
    await ElMessageBox.confirm(`确认删除模型「${m.name}」？`, '删除确认', { type: 'warning' })
    await request.delete(`/prediction-models/api/${m.id}/delete`)
    ElMessage.success('已删除')
    loadModels()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

async function predictModel(m) {
  try {
    ElMessage.info('正在运行预测...')
    const data = await request.get(`/prediction-models/api/${m.id}/predict`)
    if (data.status === 'ok') {
      predictionResult.value = data.result
      showResult.value = true
    } else {
      ElMessage.error(data.message || '预测失败')
    }
  } catch (e) {
    ElMessage.error('预测失败: ' + (e.message || e))
  }
}

async function predictAll() {
  try {
    ElMessage.info('正在运行全部预测...')
    const data = await request.get('/prediction-models/api/predict-all')
    if (data.status === 'ok') {
      ElMessage.success(`预测完成，共 ${data.count} 个模型`)
      if (data.count > 0) {
        predictionResult.value = data.results[0]
        showResult.value = true
      }
    }
  } catch (e) {
    ElMessage.error('预测失败: ' + (e.message || e))
  }
}

onMounted(loadModels)
</script>

<style scoped>
.pm-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 16px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-success { background: rgba(34,197,94,0.1); color: #22c55e; border-color: rgba(34,197,94,0.3); }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.model-card { border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; padding: 14px; background: var(--bg-card-solid, #fff); }
.card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.model-name { font-weight: 600; font-size: 0.95rem; color: var(--text, #1e293b); }
.card-meta { font-size: 0.8rem; display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }
.card-meta > div { display: flex; gap: 8px; }
.meta-label { color: var(--text-secondary, #64748b); min-width: 56px; }
.card-actions { display: flex; gap: 8px; }
.text-sm { font-size: 0.75rem; color: var(--text-secondary, #64748b); word-break: break-all; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.on { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.off { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.type { background: rgba(99,102,241,0.1); color: #6366f1; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 380px; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; color: var(--text, #1e293b); }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.result-item { display: flex; flex-direction: column; gap: 4px; }
.result-label { font-size: 0.75rem; color: var(--text-secondary, #64748b); }
.result-value { font-size: 1rem; font-weight: 600; color: var(--text, #1e293b); }
.result-value.warning { color: #f59e0b; }
.trend-increasing { color: #ef4444; }
.trend-decreasing { color: #22c55e; }
.trend-stable { color: #6366f1; }
.feature-tag { display: flex; gap: 8px; padding: 4px 8px; background: #f1f5f9; border-radius: 4px; font-size: 0.75rem; }
.feature-name { color: var(--text-secondary, #64748b); }
.feature-value { font-weight: 600; color: var(--text, #1e293b); }
</style>
