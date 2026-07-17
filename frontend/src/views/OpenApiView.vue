<template>
  <div class="openapi-page">
    <div class="page-header">
      <h1>{{ meta.title || '开放接口文档' }}</h1>
      <p>外部系统接入 AIOps 平台的 RESTful 接口 · 版本 {{ meta.version || 'v1' }}</p>
    </div>

    <div class="panel info-panel">
      <div class="panel-body">
        <div class="info-grid">
          <div class="info-item"><div class="info-label">Base URL</div><div class="info-value"><code>{{ meta.base_url || '/api/v1' }}</code></div></div>
          <div class="info-item"><div class="info-label">认证方式</div><div class="info-value">{{ meta.auth?.type || 'Bearer Token' }}</div></div>
          <div class="info-item"><div class="info-label">请求头</div><div class="info-value"><code>{{ meta.auth?.header || 'Authorization: Bearer <token>' }}</code></div></div>
          <div class="info-item"><div class="info-label">权限范围</div>
            <div class="info-value">
              <span v-for="p in (meta.auth?.permissions || [])" :key="p" class="perm-badge">{{ p }}</span>
            </div>
          </div>
        </div>
        <div class="info-desc">所有接口需在请求头携带 <code>Authorization: Bearer &lt;token&gt;</code>，Token 由管理员签发并按权限（read/write/admin）控制可访问范围。</div>
      </div>
    </div>

    <div class="panel" style="margin-top:14px;">
      <div class="panel-head">接口列表 · {{ endpoints.length }} 个</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else>
          <div v-for="(ep, idx) in endpoints" :key="idx" class="ep-item">
            <div class="ep-head" @click="toggleEp(idx)">
              <span class="method-badge" :class="methodClass(ep.method)">{{ ep.method }}</span>
              <span class="ep-path">{{ ep.path }}</span>
              <span class="ep-summary">{{ ep.summary }}</span>
              <span class="ep-auth">{{ ep.auth }}</span>
              <span class="ep-toggle">{{ openedEp === idx ? '▾' : '▸' }}</span>
            </div>
            <div v-if="openedEp === idx" class="ep-body">
              <div v-if="ep.params" class="ep-section">
                <div class="ep-section-title">查询参数</div>
                <table class="inner-table">
                  <thead><tr><th>参数</th><th>说明</th></tr></thead>
                  <tbody>
                    <tr v-for="(v, k) in ep.params" :key="k"><td><code>{{ k }}</code></td><td>{{ v }}</td></tr>
                  </tbody>
                </table>
              </div>
              <div class="ep-section">
                <div class="ep-section-title">请求示例</div>
                <pre class="code-block">{{ formatJson(ep.body_example) }}</pre>
              </div>
              <div class="ep-section">
                <div class="ep-section-title">响应示例</div>
                <pre class="code-block">{{ formatJson(ep.response_example) }}</pre>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="tokens.length" class="panel" style="margin-top:14px;">
      <div class="panel-head">Token 管理 · {{ tokens.length }} 个</div>
      <div class="panel-body">
        <table class="table">
          <thead><tr><th>ID</th><th>名称</th><th>权限</th><th>状态</th><th>最近使用</th><th>创建时间</th></tr></thead>
          <tbody>
            <tr v-for="t in tokens" :key="t.id">
              <td>{{ t.id }}</td>
              <td>{{ t.name }}</td>
              <td><span class="perm-badge" :class="permClass(t.permissions)">{{ t.permissions }}</span></td>
              <td><span class="badge" :class="t.enabled ? 'badge-green' : 'badge-gray'">{{ t.enabled ? '启用' : '禁用' }}</span></td>
              <td>{{ t.last_used_at || '未使用' }}</td>
              <td>{{ t.created_at || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="panel" style="margin-top:14px;">
      <div class="panel-head">代码示例</div>
      <div class="panel-body">
        <div v-for="(cmd, key) in examples" :key="key" class="code-section">
          <div class="code-section-head">
            <span class="code-title">{{ exampleTitle(key) }}</span>
            <button class="btn btn-sm" @click="copyCode(cmd)">复制</button>
          </div>
          <pre class="code-block">{{ cmd }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const meta = ref({})
const endpoints = ref([])
const tokens = ref([])
const examples = ref({})
const openedEp = ref(null)

function toggleEp(idx) {
  openedEp.value = openedEp.value === idx ? null : idx
}

function methodClass(m) {
  const s = (m || '').toUpperCase()
  if (s === 'GET') return 'm-get'
  if (s === 'POST') return 'm-post'
  if (s === 'PUT') return 'm-put'
  if (s === 'DELETE') return 'm-delete'
  return 'm-other'
}

function permClass(p) {
  if (p === 'admin') return 'perm-admin'
  if (p === 'write') return 'perm-write'
  if (p === 'read') return 'perm-read'
  return ''
}

function exampleTitle(key) {
  const map = {
    curl_push_metrics: 'curl 推送指标',
    curl_query_metrics: 'curl 查询指标',
  }
  return map[key] || key
}

function formatJson(v) {
  if (v == null) return ''
  if (typeof v === 'string') return v
  try { return JSON.stringify(v, null, 2) } catch { return String(v) }
}

async function copyCode(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}

async function loadDocs() {
  loading.value = true
  try {
    const data = await request.get('/api/v1/api/docs')
    meta.value = {
      title: data.title,
      version: data.version,
      base_url: data.base_url,
      auth: data.auth,
    }
    endpoints.value = data.endpoints || []
    tokens.value = data.tokens || []
    examples.value = data.examples || {}
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

onMounted(loadDocs)
</script>

<style scoped>
.openapi-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); }
.panel-body { padding: 16px 18px; }
.info-panel .panel-body { padding: 18px; }
.info-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px 24px; margin-bottom: 12px; }
.info-item { display: flex; flex-direction: column; gap: 4px; }
.info-label { font-size: 0.72rem; color: var(--text-secondary, #64748b); text-transform: uppercase; letter-spacing: 0.3px; }
.info-value { font-size: 0.85rem; color: var(--text, #1e293b); }
.info-value code { background: var(--bg-hover, rgba(0,0,0,0.03)); padding: 1px 6px; border-radius: 4px; font-family: ui-monospace, monospace; font-size: 0.8rem; color: var(--accent, #6366f1); }
.info-desc { font-size: 0.8rem; color: var(--text-secondary, #64748b); padding-top: 10px; border-top: 1px solid var(--border, rgba(0,0,0,0.07)); }
.info-desc code { background: var(--bg-hover, rgba(0,0,0,0.03)); padding: 1px 5px; border-radius: 3px; font-family: ui-monospace, monospace; font-size: 0.78rem; }
.perm-badge { display: inline-block; padding: 1px 8px; border-radius: 8px; font-size: 0.72rem; font-weight: 600; background: rgba(99,102,241,0.1); color: var(--accent, #6366f1); margin-right: 4px; }
.perm-admin { background: rgba(239,68,68,0.12); color: #dc2626; }
.perm-write { background: rgba(245,158,11,0.12); color: #d97706; }
.perm-read { background: rgba(34,197,94,0.12); color: #16a34a; }
.ep-item { border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; margin-bottom: 8px; overflow: hidden; }
.ep-head { display: flex; align-items: center; gap: 12px; padding: 10px 14px; cursor: pointer; background: var(--bg-hover, rgba(0,0,0,0.02)); }
.ep-head:hover { background: var(--bg-hover, rgba(0,0,0,0.05)); }
.method-badge { padding: 3px 10px; border-radius: 6px; font-size: 0.72rem; font-weight: 700; font-family: ui-monospace, monospace; color: #fff; min-width: 56px; text-align: center; }
.m-get { background: #22c55e; }
.m-post { background: #6366f1; }
.m-put { background: #f59e0b; }
.m-delete { background: #ef4444; }
.m-other { background: #6b7280; }
.ep-path { font-family: ui-monospace, monospace; font-size: 0.85rem; font-weight: 600; color: var(--text, #1e293b); }
.ep-summary { flex: 1; font-size: 0.8rem; color: var(--text-secondary, #64748b); }
.ep-auth { font-size: 0.72rem; color: var(--text-secondary, #64748b); background: rgba(99,102,241,0.08); padding: 2px 8px; border-radius: 6px; }
.ep-toggle { color: var(--text-secondary, #64748b); }
.ep-body { padding: 14px; border-top: 1px solid var(--border, rgba(0,0,0,0.07)); }
.ep-section { margin-bottom: 14px; }
.ep-section-title { font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.3px; }
.inner-table { width: 100%; border-collapse: collapse; }
.inner-table th { text-align: left; padding: 6px 10px; font-size: 0.72rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); }
.inner-table td { padding: 6px 10px; font-size: 0.8rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.inner-table code { font-family: ui-monospace, monospace; color: var(--accent, #6366f1); }
.code-block { background: #1e293b; color: #e2e8f0; padding: 12px 14px; border-radius: 6px; font-family: ui-monospace, monospace; font-size: 0.78rem; line-height: 1.5; overflow-x: auto; margin: 0; white-space: pre-wrap; word-break: break-all; }
.code-section { margin-bottom: 12px; }
.code-section:last-child { margin-bottom: 0; }
.code-section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.code-title { font-size: 0.8rem; font-weight: 600; color: var(--text, #1e293b); }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-sm { padding: 3px 10px; font-size: 0.72rem; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.72rem; font-weight: 600; }
.badge-green { background: rgba(34,197,94,0.12); color: #16a34a; }
.badge-gray { background: rgba(107,114,128,0.12); color: #4b5563; }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
</style>
