<template>
  <div class="vault-page">
    <div class="page-header">
      <h1>🔐 凭据保险库</h1>
      <p>集中加密存储连接凭据 · 连接配置只存 <code>{{ refTpl }}</code> 引用，运行时自动解密注入 · 共 {{ secrets.length }} 条凭据</p>
    </div>

    <div class="stat-row">
      <div class="stat-card"><span class="stat-num">{{ secrets.length }}</span><span>凭据总数</span></div>
      <div class="stat-card"><span class="stat-num">{{ referenceNames.size }}</span><span>被引用凭据</span></div>
      <div class="stat-card"><span class="stat-num">{{ references.length }}</span><span>数据源引用</span></div>
      <div class="stat-card" :class="{ warn: missingRefs > 0 }"><span class="stat-num">{{ missingRefs }}</span><span>失效引用</span></div>
    </div>

    <div class="toolbar">
      <input v-model="search" class="search-input" placeholder="搜索凭据名称 / 描述..." />
      <div class="toolbar-right">
        <button class="btn" @click="loadRefs()">刷新引用</button>
        <button class="btn btn-primary" @click="openDialog()">+ 新建凭据</button>
      </div>
    </div>

    <table v-if="filtered.length" class="table">
      <thead>
        <tr><th>ID</th><th>引用名</th><th>类型</th><th>作用域</th><th>描述</th><th>值</th><th>更新时间</th><th>操作</th></tr>
      </thead>
      <tbody>
        <tr v-for="s in filtered" :key="s.id">
          <td>{{ s.id }}</td>
          <td class="ref-name">
            <code>{{ refStr(s.name) }}</code>
            <button class="btn-icon-sm" title="复制引用" @click="copyRef(s.name)">📋</button>
          </td>
          <td><span class="badge type-{{ s.value_type }}">{{ valueTypeLabel(s.value_type) }}</span></td>
          <td><span class="badge">{{ scopeLabel(s.scope) }}</span></td>
          <td>{{ s.description || '-' }}</td>
          <td>
            <span v-if="s.has_value" class="masked">••••••••</span>
            <span v-else class="empty">未设置</span>
          </td>
          <td>{{ s.updated_at || '-' }}</td>
          <td class="ops">
            <button class="btn-icon-sm" title="编辑" @click="openDialog(s)">✏️</button>
            <button class="btn-icon-sm danger" title="删除" @click="delSecret(s)">🗑️</button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty-state">
      <div style="font-size:40px;margin-bottom:12px;">🔐</div>
      <div>{{ search ? '没有找到匹配的凭据' : '暂无凭据' }}</div>
      <button v-if="!search" class="btn btn-primary" style="margin-top:12px" @click="openDialog()">+ 新建第一条凭据</button>
    </div>

    <div v-if="references.length" class="ref-panel">
      <div class="panel-head">
        <span>📎 数据源引用一览（auth_config 中出现的 <code>{{ refTpl }}</code>）</span>
      </div>
      <table class="table">
        <thead><tr><th>引用名</th><th>使用数据源</th><th>状态</th></tr></thead>
        <tbody>
          <tr v-for="r in references" :key="r.secret_name">
            <td><code>{{ refStr(r.secret_name) }}</code></td>
            <td>{{ r.sources.map(s => s.source_name).join('、') }}</td>
            <td>
              <span v-if="r.exists" class="tag-ok">✓ 有效</span>
              <span v-else class="tag-bad">✗ 失效（保险库无此凭据）</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="resolve-panel">
      <div class="panel-head">
        <span>🧪 引用解析测试（传任意 JSON/字符串，验证 {{ refTpl }} 会替换成真实值）</span>
      </div>
      <div class="resolve-body">
        <textarea v-model="resolveInput" class="resolve-input" rows="3" placeholder='{"ssh_user":"root","ssh_password":"{{secret:name}}"}'></textarea>
        <button class="btn btn-primary" @click="doResolve">解析</button>
      </div>
      <pre v-if="resolveResult !== null" class="resolve-result">{{ resolveResult }}</pre>
    </div>

    <!-- 新建/编辑弹框 -->
    <div v-if="showDialog" class="modal-overlay" @click.self="showDialog = false">
      <div class="modal-box">
        <h3>{{ editing ? '编辑凭据' : '新建凭据' }}</h3>
        <div class="form-row"><label>引用名（英文标识）</label><input v-model="form.name" class="input" :disabled="!!editing" placeholder="如 prod_db_password" /></div>
        <div class="form-row"><label>类型</label>
          <select v-model="form.value_type" class="sel">
            <option v-for="t in valueTypes" :key="t" :value="t">{{ valueTypeLabel(t) }}</option>
          </select>
        </div>
        <div class="form-row"><label>作用域</label>
          <select v-model="form.scope" class="sel">
            <option v-for="sc in scopes" :key="sc" :value="sc">{{ scopeLabel(sc) }}</option>
          </select>
        </div>
        <div class="form-row"><label>描述</label><input v-model="form.description" class="input" placeholder="用途说明" /></div>
        <div class="form-row">
          <label>{{ editing ? '新值（留空则不修改）' : '值' }}</label>
          <input v-model="form.secret_value" type="password" class="input" placeholder="密码 / Token / 密钥" :autocomplete="editing ? 'new-password' : 'off'" />
        </div>
        <div v-if="editing" class="hint">值为空保存时保持原值不变；值仅加密存储，不对外回显。</div>
        <div class="modal-actions">
          <div style="flex:1"></div>
          <button class="btn" @click="showDialog = false">取消</button>
          <button class="btn btn-primary" @click="saveSecret">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import request from '@/api/request'
import { ElMessage } from 'element-plus'

const secrets = ref([])
const valueTypes = ref(['password', 'token', 'api_key', 'private_key', 'custom'])
const scopes = ref(['global', 'data_source', 'asset'])
const references = ref([])
const search = ref('')
const showDialog = ref(false)
const editing = ref(null)
const form = ref({ name: '', value_type: 'password', scope: 'global', description: '', secret_value: '' })
const resolveInput = ref('')
const resolveResult = ref(null)

const refTpl = '{{secret:name}}'
function refStr(name) { return `{{secret:${name}}}` }

const filtered = computed(() => {
  const q = (search.value || '').toLowerCase()
  if (!q) return secrets.value
  return secrets.value.filter(s =>
    s.name.toLowerCase().includes(q) || (s.description || '').toLowerCase().includes(q)
  )
})

const referenceNames = computed(() => new Set(references.value.map(r => r.secret_name)))
const missingRefs = computed(() => references.value.filter(r => !r.exists).length)

function valueTypeLabel(t) {
  return { password: '密码', token: 'Token', api_key: 'API Key', private_key: '私钥', custom: '自定义' }[t] || t
}
function scopeLabel(s) {
  return { global: '全局', data_source: '数据源', asset: '资产' }[s] || s
}

async function loadSecrets() {
  try {
    const d = await request.get('/api/vault/secrets')
    secrets.value = d.secrets || []
    valueTypes.value = d.value_types || valueTypes.value
    scopes.value = d.scopes || scopes.value
  } catch (e) { ElMessage.error(e.message) }
}

async function loadRefs() {
  try {
    const d = await request.get('/api/vault/references')
    references.value = d.references || []
  } catch (e) { ElMessage.error(e.message) }
}

function openDialog(s = null) {
  editing.value = s
  form.value = s
    ? { name: s.name, value_type: s.value_type, scope: s.scope, description: s.description, secret_value: '' }
    : { name: '', value_type: 'password', scope: 'global', description: '', secret_value: '' }
  showDialog.value = true
}

async function saveSecret() {
  if (!form.value.name) return ElMessage.warning('请填写引用名')
  if (!editing.value && !form.value.secret_value) return ElMessage.warning('请填写值')
  try {
    if (editing.value) {
      const d = await request.put(`/api/vault/secrets/${editing.value.id}`, form.value)
      ElMessage.success('已保存')
    } else {
      const d = await request.post('/api/vault/secrets', form.value)
      ElMessage.success('已创建')
    }
    showDialog.value = false
    await Promise.all([loadSecrets(), loadRefs()])
  } catch (e) { ElMessage.error(e.message) }
}

async function delSecret(s) {
  if (!confirm(`确认删除凭据「${s.name}」？使用该引用的数据源将无法连接。`)) return
  try {
    await request.delete(`/api/vault/secrets/${s.id}`)
    ElMessage.success('已删除')
    await Promise.all([loadSecrets(), loadRefs()])
  } catch (e) { ElMessage.error(e.message) }
}

function copyRef(name) {
  const text = `{{secret:${name}}}`
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(() => ElMessage.success('引用已复制：' + text))
  } else {
    ElMessage.info('请手动复制：' + text)
  }
}

async function doResolve() {
  if (!resolveInput.value.trim()) return ElMessage.warning('请输入要解析的内容')
  let body
  try {
    body = JSON.parse(resolveInput.value)
  } catch {
    body = resolveInput.value
  }
  try {
    const d = await request.post('/api/vault/secrets/resolve', body)
    resolveResult.value = JSON.stringify(d.resolved, null, 2)
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(() => {
  loadSecrets()
  loadRefs()
})
</script>

<style scoped>
.vault-page { padding: 20px; }
.page-header h1 { margin: 0 0 4px; font-size: 22px; }
.page-header p { margin: 0 0 16px; color: #888; font-size: 13px; }
.page-header code, .ref-name code, .ref-panel code { background: #f0f2f5; padding: 2px 6px; border-radius: 4px; font-size: 12px; }
.stat-row { display: flex; gap: 14px; margin-bottom: 16px; }
.stat-card { flex: 1; background: #fff; border: 1px solid #eee; border-radius: 8px; padding: 14px 16px; display: flex; flex-direction: column; gap: 2px; font-size: 13px; color: #888; }
.stat-num { font-size: 26px; font-weight: 700; color: #1f2d3d; }
.stat-card.warn .stat-num { color: #e6a23c; }
.toolbar { display: flex; justify-content: space-between; margin-bottom: 12px; gap: 10px; }
.search-input { padding: 8px 12px; border: 1px solid #dcdfe6; border-radius: 6px; width: 280px; }
.toolbar-right { display: flex; gap: 8px; }
.table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.table th { background: #f7f8fa; text-align: left; padding: 10px 12px; font-size: 12px; color: #666; }
.table td { padding: 10px 12px; border-top: 1px solid #f0f0f0; font-size: 13px; }
.ref-name { display: flex; align-items: center; gap: 6px; }
.masked { letter-spacing: 3px; color: #909399; }
.empty { color: #c0c4cc; }
.ops { display: flex; gap: 6px; }
.badge { padding: 2px 8px; border-radius: 10px; font-size: 12px; background: #f0f2f5; color: #606266; }
.badge.type-token { background: #ecf5ff; color: #409eff; }
.badge.type-api_key { background: #f0f9eb; color: #67c23a; }
.badge.type-private_key { background: #fdf6ec; color: #e6a23c; }
.badge.type-custom { background: #f4f4f5; color: #909399; }
.ref-panel, .resolve-panel { margin-top: 20px; background: #fff; border: 1px solid #eee; border-radius: 8px; }
.panel-head { padding: 12px 16px; font-size: 14px; font-weight: 600; border-bottom: 1px solid #f0f0f0; }
.resolve-body { display: flex; gap: 10px; padding: 12px 16px; align-items: flex-start; }
.resolve-input { flex: 1; font-family: monospace; font-size: 12px; border: 1px solid #dcdfe6; border-radius: 6px; padding: 8px; }
.resolve-result { margin: 0 16px 14px; padding: 10px; background: #f7f8fa; border-radius: 6px; font-size: 12px; max-height: 200px; overflow: auto; white-space: pre-wrap; }
.tag-ok { color: #67c23a; font-size: 13px; }
.tag-bad { color: #f56c6c; font-size: 13px; }
.hint { font-size: 12px; color: #909399; margin-top: -6px; margin-bottom: 8px; }
</style>
