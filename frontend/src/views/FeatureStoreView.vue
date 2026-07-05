<template>
  <div class="fs-page">
    <div class="page-header">
      <h1>特征仓库</h1>
      <p>ML 模型可复用特征存储 · 共 {{ recent.length }} 条最近记录</p>
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
      <div class="panel-head">{{ queryResult.length ? `查询结果 · ${queryResult.length} 条` : `最近记录 · ${recent.length} 条` }}</div>
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
      </div>
    </div>
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
const form = ref({ feature_name: '', entity_type: 'asset', entity_id: 0, feature_value: 0, source: 'manual', feature_json: '{}' })
const query = ref({ feature_name: '', entity_type: '', entity_id: 0 })

const displayList = computed(() => queryResult.value.length ? queryResult.value : recent.value)

async function load() {
  loading.value = true
  try {
    const data = await request.get('/feature-store/api/list')
    features.value = data.features || []
    entities.value = data.entities || []
    recent.value = data.recent || []
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
