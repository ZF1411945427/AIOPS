<template>
  <div class="fs-page">
    <div class="page-header">
      <h1>特征仓库</h1>
      <p>ML 模型可复用特征存储 · 共 {{ total }} 条记录</p>
    </div>

    <div class="toolbar">
      <button class="btn" @click="showLogic = true">逻辑说明</button>
    </div>

    <div class="grid-2">
      <div class="panel">
        <div class="panel-head">添加特征</div>
        <div class="panel-body">
          <div class="form-row"><label>特征名</label><input v-model="form.feature_name" class="input"></div>
          <div class="form-row"><label>实体类型</label>
            <select v-model="form.entity_type" class="input">
              <option value="asset">asset</option><option value="metric">metric</option>
              <option value="alert">alert</option><option value="global">global</option>
            </select>
          </div>
          <div class="form-row"><label>实体 ID</label><input v-model.number="form.entity_id" type="number" class="input"></div>
          <div class="form-row"><label>特征值</label><input v-model.number="form.feature_value" type="number" class="input"></div>
          <div class="form-row"><label>来源</label><input v-model="form.source" class="input"></div>
          <div class="form-row"><label>特征 JSON</label><input v-model="form.feature_json" class="input"></div>
          <button class="btn btn-primary" @click="addFeature">添加</button>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">查询特征</div>
        <div class="panel-body">
          <div class="form-row"><label>特征名</label>
            <select v-model="query.feature_name" class="input">
              <option value="">全部</option>
              <option v-for="f in features" :key="f" :value="f">{{ f }}</option>
            </select>
          </div>
          <div class="form-row"><label>实体类型</label>
            <select v-model="query.entity_type" class="input">
              <option value="">全部</option>
              <option v-for="e in entities" :key="e" :value="e">{{ e }}</option>
            </select>
          </div>
          <div class="form-row"><label>实体 ID</label><input v-model.number="query.entity_id" type="number" class="input"></div>
          <button class="btn btn-primary" @click="queryFeatures">查询</button>
        </div>
      </div>
    </div>

    <div class="panel" style="margin-top:14px;">
      <div class="panel-head">{{ queryResult.length ? `查询结果 · ${queryResult.length} 条` : `最近记录 · ${total} 条` }}</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="displayList.length" class="table">
          <thead><tr><th>ID</th><th>特征名</th><th>实体</th><th>值</th><th>来源</th><th>时间</th></tr></thead>
          <tbody>
            <tr v-for="r in displayList" :key="r.id">
              <td>{{ r.id }}</td>
              <td>{{ r.feature_name }}</td>
              <td class="text-sm">{{ r.entity_type }}:{{ r.entity_id }}</td>
              <td>{{ r.feature_value }}</td>
              <td class="text-sm">{{ r.source || '-' }}</td>
              <td class="text-sm">{{ r.created_at || '-' }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">暂无数据</div>
        <div v-if="!queryResult.length && total > 0" style="display:flex;justify-content:flex-end;padding:12px 0">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :page-sizes="[20, 50, 100]"
            :total="total"
            layout="total, sizes, prev, pager, next"
            small
            @size-change="load"
            @current-change="load"
          />
        </div>
      </div>
    </div>

    <el-dialog v-model="showLogic" title="特征仓库 - 逻辑说明" width="650px">
      <div style="font-size:13px;line-height:1.8">
        <h4 style="margin:0 0 8px">一、什么是特征仓库？</h4>
        <p>特征仓库（Feature Store）是机器学习中用于存储和管理<strong>特征数据</strong>的系统。特征是从原始数据中提取的、用于训练和预测模型的数值化属性。</p>
        <p style="background:#f0f9ff;padding:8px 12px;border-radius:6px;border-left:3px solid #3b82f6;margin:8px 0">
          <strong>大白话：</strong>就像一个"数据字典"，把散落在各处的关键数据收集起来，给预测模型用。比如预测 CPU 会不会爆，需要知道"过去 1 小时平均 CPU"、"内存大小"这些数据，特征仓库就是存这些数据的地方。
        </p>
        
        <h4 style="margin:16px 0 8px">二、在 AIOps 中哪里用？</h4>
        <table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:12px">
          <tr style="background:#f5f5f5"><td style="padding:6px;border:1px solid #ddd;font-weight:600">使用场景</td><td style="padding:6px;border:1px solid #ddd;font-weight:600">具体效果</td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd">预测模型</td><td style="padding:6px;border:1px solid #ddd">预测模型从特征仓库读取特征作为输入，提高预测准确度</td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd">智能推荐</td><td style="padding:6px;border:1px solid #ddd">推荐算法根据资产特征判断关联性</td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd">异常检测</td><td style="padding:6px;border:1px solid #ddd">根据历史特征建立基线，超出即告警</td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd">根因分析</td><td style="padding:6px;border:1px solid #ddd">分析告警时参考资产特征，缩小排查范围</td></tr>
        </table>

        <h4 style="margin:16px 0 8px">三、创建/添加步骤</h4>
        <ol style="margin:0;padding-left:20px">
          <li><strong>填写特征名</strong>：如 <code>cpu_avg_1h</code>（过去 1 小时平均 CPU）</li>
          <li><strong>选择实体类型</strong>：asset（资产）、metric（指标）、alert（告警）、global（全局）</li>
          <li><strong>填写实体 ID</strong>：对应资产的 ID，如 1 表示第一台服务器</li>
          <li><strong>填写特征值</strong>：数值，如 CPU 使用率 50.26</li>
          <li><strong>填写来源</strong>：manual（手动）、collector（采集器）、seed（种子数据）</li>
          <li><strong>点击"添加"</strong>：数据保存到特征仓库</li>
        </ol>

        <h4 style="margin:16px 0 8px">四、实体类型说明</h4>
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <tr style="background:#f5f5f5"><td style="padding:6px;border:1px solid #ddd;font-weight:600">类型</td><td style="padding:6px;border:1px solid #ddd;font-weight:600">说明</td><td style="padding:6px;border:1px solid #ddd;font-weight:600">示例特征</td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd">asset</td><td style="padding:6px;border:1px solid #ddd">资产（服务器、容器等）</td><td style="padding:6px;border:1px solid #ddd">cpu_avg_1h, mem_avg_1h, disk_avg_1h</td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd">metric</td><td style="padding:6px;border:1px solid #ddd">监控指标</td><td style="padding:6px;border:1px solid #ddd">qps, latency_p99, error_rate</td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd">alert</td><td style="padding:6px;border:1px solid #ddd">告警事件</td><td style="padding:6px;border:1px solid #ddd">alert_count_24h, severity_avg</td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd">global</td><td style="padding:6px;border:1px solid #ddd">全局上下文</td><td style="padding:6px;border:1px solid #ddd">cluster_load, time_of_day</td></tr>
        </table>

        <h4 style="margin:16px 0 8px">五、查询和使用</h4>
        <ul style="margin:0;padding-left:20px">
          <li><strong>按特征名筛选</strong>：选择特定特征查看所有资产的值</li>
          <li><strong>按实体类型筛选</strong>：只看资产特征或只看告警特征</li>
          <li><strong>按实体 ID 筛选</strong>：查看某台服务器的所有特征</li>
          <li><strong>预测模型自动使用</strong>：创建预测模型后，系统会自动读取相关特征作为预测上下文</li>
        </ul>

        <h4 style="margin:16px 0 8px">六、实际效果示例</h4>
        <div style="background:#f0fdf4;padding:8px 12px;border-radius:6px;border-left:3px solid #22c55e;margin:8px 0">
          <strong>场景：</strong>为服务器 1 添加特征 cpu_avg_1h=50.26<br>
          <strong>效果：</strong>当预测模型预测 cpu_usage 时，会自动读取这个特征作为上下文，知道"当前平均 CPU 是 50.26%"，从而给出更准确的预测
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const features = ref([])
const entities = ref([])
const recent = ref([])
const queryResult = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const showLogic = ref(false)
const form = ref({ feature_name: '', entity_type: 'asset', entity_id: 0, feature_value: 0, source: 'manual', feature_json: '{}' })
const query = ref({ feature_name: '', entity_type: '', entity_id: 0 })

const displayList = computed(() => queryResult.value.length ? queryResult.value : recent.value)

async function load() {
  loading.value = true
  try {
    const data = await request.get('/feature-store/api/list', { params: { page: page.value, page_size: pageSize.value } })
    features.value = data.features || []
    entities.value = data.entities || []
    recent.value = data.recent || []
    total.value = data.total || 0
    queryResult.value = []
  } catch (e) {
    ElMessage.error('加载失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

async function addFeature() {
  if (!form.value.feature_name) { ElMessage.warning('特征名不能为空'); return }
  try {
    await request.post('/feature-store/api/add', form.value)
    ElMessage.success('已添加')
    form.value = { feature_name: '', entity_type: 'asset', entity_id: 0, feature_value: 0, source: 'manual', feature_json: '{}' }
    load()
  } catch (e) {
    ElMessage.error('添加失败: ' + (e.message || e))
  }
}

async function queryFeatures() {
  try {
    const data = await request.post('/feature-store/api/query', query.value)
    queryResult.value = data.items || []
    ElMessage.success(`查询到 ${data.count} 条`)
  } catch (e) {
    ElMessage.error('查询失败: ' + (e.message || e))
  }
}

onMounted(load)
</script>

<style scoped>
.fs-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 14px; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); }
.panel-body { padding: 14px 18px; }
.form-row { margin-bottom: 10px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.btn { padding: 6px 16px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
</style>
