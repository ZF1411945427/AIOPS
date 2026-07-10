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

    <el-dialog v-model="showLogic" title="特征仓库 - 逻辑说明" width="600px">
      <div style="font-size:13px;line-height:1.8">
        <h4 style="margin:0 0 8px">什么是特征仓库？</h4>
        <p>特征仓库（Feature Store）是机器学习中用于存储和管理<strong>特征数据</strong>的系统。特征是从原始数据中提取的、用于训练和预测模型的数值化属性。</p>
        
        <h4 style="margin:16px 0 8px">在 AIOps 中的作用</h4>
        <ul style="margin:0;padding-left:20px">
          <li><strong>资产特征</strong>：如 CPU 核数、内存大小、磁盘类型等静态属性</li>
          <li><strong>指标特征</strong>：如过去 1 小时的平均 CPU 使用率、内存峰值等</li>
          <li><strong>告警特征</strong>：如告警频率、严重级别、影响范围等</li>
          <li><strong>全局特征</strong>：如当前时间（工作日/节假日）、集群负载等级等</li>
        </ul>

        <h4 style="margin:16px 0 8px">操作流程</h4>
        <ol style="margin:0;padding-left:20px">
          <li><strong>添加特征</strong>：手动或通过采集器添加特征数据</li>
          <li><strong>查询特征</strong>：按特征名、实体类型、实体 ID 筛选</li>
          <li><strong>模型训练</strong>：预测模型从特征仓库读取特征进行训练</li>
          <li><strong>实时预测</strong>：预测时实时查询最新特征值</li>
        </ol>

        <h4 style="margin:16px 0 8px">实体类型说明</h4>
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <tr style="background:#f5f5f5"><td style="padding:6px;border:1px solid #ddd;font-weight:600">类型</td><td style="padding:6px;border:1px solid #ddd;font-weight:600">说明</td><td style="padding:6px;border:1px solid #ddd;font-weight:600">示例</td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd">asset</td><td style="padding:6px;border:1px solid #ddd">资产（服务器、容器等）</td><td style="padding:6px;border:1px solid #ddd">CPU 核数、内存大小</td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd">metric</td><td style="padding:6px;border:1px solid #ddd">监控指标</td><td style="padding:6px;border:1px solid #ddd">CPU 使用率、QPS</td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd">alert</td><td style="padding:6px;border:1px solid #ddd">告警事件</td><td style="padding:6px;border:1px solid #ddd">告警频率、严重级别</td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd">global</td><td style="padding:6px;border:1px solid #ddd">全局上下文</td><td style="padding:6px;border:1px solid #ddd">时间、集群负载</td></tr>
        </table>
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
