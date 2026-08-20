<template>
  <div class="providers-page">
    <div class="page-header">
      <h1>Provider 集成中心</h1>
      <p>统一管理监控、告警、通知、工单等第三方集成 · 已安装 {{ installed.length }} 个</p>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="showCatalog = true">+ 安装 Provider</button>
      <button class="btn" @click="loadInstalled">刷新</button>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="installed.length" class="table">
          <thead>
            <tr>
              <th>名称</th>
              <th>类型</th>
              <th>分类</th>
              <th>地址</th>
              <th>状态</th>
              <th>最后采集</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in installed" :key="p.id">
              <td>{{ p.name }}</td>
              <td><span class="badge type">{{ p.display_name || p.type }}</span></td>
              <td><span class="badge">{{ p.category }}</span></td>
              <td class="text-sm">{{ p.endpoint || '-' }}</td>
              <td>
                <span class="badge" :class="p.enabled ? 'on' : 'off'">{{ p.enabled ? '启用' : '停用' }}</span>
                <span v-if="p.last_status" class="badge" :class="p.last_status === 'online' ? 'on' : 'off'">{{ p.last_status }}</span>
              </td>
              <td class="text-sm">{{ p.last_scraped_at || '-' }}</td>
              <td>
                <button class="btn btn-sm" @click="testProvider(p.id)">测试</button>
                <button class="btn btn-sm" @click="toggleProvider(p)">{{ p.enabled ? '停用' : '启用' }}</button>
                <button class="btn btn-sm btn-danger" @click="uninstallProvider(p.id, p.name)">卸载</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">🔌</div>
          <div>暂无已安装的 Provider</div>
          <button class="btn btn-primary" style="margin-top:12px" @click="showCatalog = true">浏览 Provider 市场</button>
        </div>
      </div>
    </div>

    <div v-if="testResult" class="test-result" :class="testResult.ok ? 'success' : 'error'">
      {{ testResult.ok ? '✅ ' : '❌ ' }}{{ testResult.message }}
      <button class="btn btn-sm" style="margin-left:12px" @click="testResult = null">关闭</button>
    </div>

    <div v-if="showCatalog" class="modal-overlay" @click.self="showCatalog = false">
      <div class="modal-box wide">
        <div class="modal-header">
          <h3>Provider 市场</h3>
          <button class="modal-close" @click="showCatalog = false">×</button>
        </div>
        <div class="catalog-search">
          <input v-model="catalogSearch" placeholder="搜索 Provider..." class="form-input" />
          <select v-model="categoryFilter" class="form-select">
            <option value="">全部分类</option>
            <option v-for="cat in categories" :key="cat" :value="cat">{{ cat }}</option>
          </select>
        </div>
        <div class="catalog-grid">
          <div v-for="p in filteredCatalog" :key="p.type" class="catalog-card" @click="selectProvider(p)">
            <div class="card-header">
              <span class="badge cat">{{ p.category }}</span>
              <span v-if="p.coming_soon" class="badge soon">即将推出</span>
            </div>
            <div class="card-body">
              <h4>{{ p.display_name }}</h4>
              <p>{{ p.description }}</p>
            </div>
            <div class="card-footer">
              <span v-for="tag in p.tags" :key="tag" class="tag">{{ tag }}</span>
              <span v-for="cap in p.capabilities" :key="cap" class="cap-badge">{{ cap }}</span>
            </div>
          </div>
        </div>
        <div v-if="!filteredCatalog.length" class="empty-state">无匹配的 Provider</div>
      </div>
    </div>

    <div v-if="installTarget" class="modal-overlay" @click.self="cancelInstall">
      <div class="modal-box">
        <div class="modal-header">
          <h3>安装 {{ installTarget.display_name }}</h3>
          <button class="modal-close" @click="cancelInstall">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>名称 *</label>
            <input v-model="installForm.name" class="form-input" placeholder="例如: 生产环境 Prometheus" />
          </div>
          <div class="form-group">
            <label>端点地址</label>
            <input v-model="installForm.endpoint" class="form-input" placeholder="https://..." />
          </div>
          <div v-for="(meta, key) in installTarget.auth_config_schema" :key="key" class="form-group">
            <label v-if="!meta.hidden">
              {{ meta.description || key }}
              <span v-if="meta.required" class="required">*</span>
              <span v-if="meta.sensitive" class="sensitive-hint">(敏感)</span>
            </label>
            <input v-if="!meta.hidden && meta.type !== 'select'" v-model="installForm.auth_config[key]"
              :type="meta.sensitive ? 'password' : 'text'"
              class="form-input"
              :placeholder="meta.placeholder || key" />
            <select v-if="!meta.hidden && meta.type === 'select'" v-model="installForm.auth_config[key]" class="form-select">
              <option v-for="opt in meta.options" :key="opt" :value="opt">{{ opt }}</option>
            </select>
          </div>
          <div class="form-group">
            <label>采集间隔 (秒)</label>
            <input v-model.number="installForm.scrape_interval" type="number" class="form-input" />
          </div>
          <div class="form-actions">
            <button class="btn" @click="cancelInstall">取消</button>
            <button class="btn btn-primary" @click="doInstall" :disabled="installing">
              {{ installing ? '安装中...' : '安装' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import request from '@/api/request'

const installed = ref([])
const catalog = ref([])
const loading = ref(false)
const showCatalog = ref(false)
const catalogSearch = ref('')
const categoryFilter = ref('')
const installTarget = ref(null)
const installForm = ref({ name: '', endpoint: '', auth_config: {}, scrape_interval: 60 })
const installing = ref(false)
const testResult = ref(null)

const categories = computed(() => {
  const cats = new Set(catalog.value.map(p => p.category).filter(Boolean))
  return [...cats]
})

const filteredCatalog = computed(() => {
  let list = catalog.value
  if (catalogSearch.value) {
    const q = catalogSearch.value.toLowerCase()
    list = list.filter(p => p.display_name?.toLowerCase().includes(q) || p.type?.toLowerCase().includes(q) || p.description?.toLowerCase().includes(q))
  }
  if (categoryFilter.value) {
    list = list.filter(p => p.category === categoryFilter.value)
  }
  return list
})

async function loadInstalled() {
  loading.value = true
  try {
    const data = await request.get('/api/providers/installed')
    installed.value = data.installed || []
  } catch (e) {
    console.error('加载已安装 Provider 失败', e)
  } finally {
    loading.value = false
  }
}

async function loadCatalog() {
  try {
    const data = await request.get('/api/providers/catalog')
    catalog.value = data.providers || []
  } catch (e) {
    console.error('加载 Provider 目录失败', e)
  }
}

function selectProvider(p) {
  installTarget.value = p
  installForm.value = { name: p.display_name, endpoint: '', auth_config: {}, scrape_interval: 60 }
  showCatalog.value = false
}

function cancelInstall() {
  installTarget.value = null
  installForm.value = { name: '', endpoint: '', auth_config: {}, scrape_interval: 60 }
}

async function doInstall() {
  if (!installForm.value.name) return
  installing.value = true
  try {
    const payload = {
      type: installTarget.value.type,
      name: installForm.value.name,
      endpoint: installForm.value.endpoint,
      auth_config: installForm.value.auth_config,
      scrape_interval: installForm.value.scrape_interval,
    }
    const data = await request.post('/api/providers/install', payload)
    if (data.ok) {
      installed.value.unshift(data.provider)
      cancelInstall()
    }
  } catch (e) {
    alert('安装失败: ' + (e.response?.data?.error || e.message))
  } finally {
    installing.value = false
  }
}

async function testProvider(id) {
  testResult.value = null
  try {
    const data = await request.post(`/api/providers/installed/${id}/test`)
    testResult.value = data
  } catch (e) {
    testResult.value = { ok: false, message: e.message }
  }
  setTimeout(() => { testResult.value = null }, 5000)
}

async function toggleProvider(p) {
  try {
    await request.post(`/api/providers/installed/${p.id}/toggle`)
    p.enabled = !p.enabled
  } catch (e) {
    console.error('切换失败', e)
  }
}

async function uninstallProvider(id, name) {
  if (!confirm(`确定卸载 Provider「${name}」？`)) return
  try {
    const data = await request.post(`/api/providers/installed/${id}/uninstall`)
    if (data.ok) {
      installed.value = installed.value.filter(p => p.id !== id)
    }
  } catch (e) {
    alert('卸载失败: ' + (e.response?.data?.error || e.message))
  }
}

onMounted(() => {
  loadInstalled()
  loadCatalog()
})
</script>

<style scoped>
.providers-page { padding: 20px; max-width: 1200px; margin: 0 auto; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 22px; margin: 0 0 4px; }
.page-header p { color: #888; font-size: 13px; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 16px; }
.panel { background: #fff; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
.panel-body { padding: 16px; }
.loading-state, .empty-state { text-align: center; padding: 40px; color: #888; }
.table { width: 100%; border-collapse: collapse; }
.table th, .table td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; font-size: 13px; }
.table th { font-weight: 600; color: #555; background: #fafafa; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.badge.on { background: #d1fae5; color: #065f46; }
.badge.off { background: #fee2e2; color: #991b1b; }
.badge.type { background: #e0e7ff; color: #3730a3; }
.badge.cat { background: #fef3c7; color: #92400e; }
.badge.soon { background: #f3e8ff; color: #6b21a8; }
.text-sm { font-size: 12px; color: #888; }
.btn { padding: 6px 14px; border: 1px solid #ddd; border-radius: 6px; background: #fff; cursor: pointer; font-size: 13px; }
.btn:hover { background: #f5f5f5; }
.btn-primary { background: #6366f1; color: #fff; border-color: #6366f1; }
.btn-primary:hover { background: #4f46e5; }
.btn-danger { color: #dc2626; border-color: #fca5a5; }
.btn-danger:hover { background: #fef2f2; }
.btn-sm { padding: 3px 10px; font-size: 12px; }
.test-result { margin-top: 12px; padding: 10px 16px; border-radius: 6px; font-size: 13px; }
.test-result.success { background: #d1fae5; color: #065f46; }
.test-result.error { background: #fee2e2; color: #991b1b; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: #fff; border-radius: 12px; width: 500px; max-height: 80vh; overflow-y: auto; }
.modal-box.wide { width: 800px; }
.modal-header { padding: 16px 20px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }
.modal-header h3 { margin: 0; font-size: 16px; }
.modal-close { background: none; border: none; font-size: 22px; cursor: pointer; color: #888; }
.modal-body { padding: 20px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 13px; font-weight: 500; margin-bottom: 4px; color: #333; }
.form-input, .form-select { width: 100%; padding: 8px 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; box-sizing: border-box; }
.form-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 20px; }
.required { color: #dc2626; }
.sensitive-hint { color: #f59e0b; font-size: 11px; }
.catalog-search { padding: 12px 20px; display: flex; gap: 8px; border-bottom: 1px solid #eee; }
.catalog-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; padding: 16px; }
.catalog-card { border: 1px solid #eee; border-radius: 8px; padding: 12px; cursor: pointer; transition: all .15s; }
.catalog-card:hover { border-color: #6366f1; box-shadow: 0 2px 8px rgba(99,102,241,.15); }
.card-header { display: flex; gap: 4px; margin-bottom: 8px; }
.card-body h4 { margin: 0 0 4px; font-size: 14px; }
.card-body p { margin: 0; font-size: 12px; color: #888; line-height: 1.4; }
.card-footer { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
.tag { background: #f0f0f0; padding: 1px 6px; border-radius: 3px; font-size: 10px; color: #666; }
.cap-badge { background: #dbeafe; padding: 1px 6px; border-radius: 3px; font-size: 10px; color: #1e40af; }
</style>