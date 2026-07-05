<template>
  <div class="ds-page">
    <div class="page-header">
      <h1>数据源管理</h1>
      <p>采集数据源配置 · 共 {{ sources.length }} 个</p>
    </div>

    <div class="toolbar">
      <a href="/datasources" class="btn btn-primary">+ 新增数据源</a>
      <span class="hint">新增/编辑通过原页面操作</span>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="sources.length" class="table">
          <thead>
            <tr>
              <th>ID</th><th>名称</th><th>类型</th><th>地址</th><th>认证</th>
              <th>状态</th><th>采集间隔</th><th>最后采集</th><th>采集状态</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in sources" :key="s.id">
              <td>{{ s.id }}</td>
              <td>{{ s.name }}</td>
              <td><span class="badge type">{{ s.type }}</span></td>
              <td class="text-sm">{{ s.endpoint || '-' }}</td>
              <td><span class="badge auth">{{ s.auth_type }}</span></td>
              <td><span class="badge" :class="s.enabled ? 'on' : 'off'">{{ s.enabled ? '启用' : '停用' }}</span></td>
              <td class="text-sm">{{ s.scrape_interval }}s</td>
              <td class="text-sm">{{ s.last_scraped_at || '-' }}</td>
              <td><span v-if="s.last_status" class="badge" :class="s.last_status === 'success' ? 'on' : 'off'">{{ s.last_status }}</span><span v-else class="text-sm">-</span></td>
              <td>
                <button class="btn btn-sm" @click="toggleSource(s)">{{ s.enabled ? '停用' : '启用' }}</button>
                <button class="btn btn-sm" @click="testSource(s.id)">测试</button>
                <button class="btn btn-sm btn-danger" @click="deleteSource(s.id, s.name)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">🔌</div>
          <div>暂无数据源</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const sources = ref([])

async function loadSources() {
  loading.value = true
  try {
    const data = await request.get('/datasources/api/list')
    sources.value = data.sources || []
  } catch (e) {
    ElMessage.error('加载数据源失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

async function toggleSource(s) {
  try {
    await request.post(`/datasources/api/${s.id}/toggle`)
    ElMessage.success(s.enabled ? '已停用' : '已启用')
    loadSources()
  } catch (e) {
    ElMessage.error('操作失败: ' + e.message)
  }
}

async function testSource(id) {
  try {
    ElMessage.info('测试中...')
    const data = await request.post(`/datasources/api/${id}/test`)
    if (data.ok) ElMessage.success('连接成功: ' + data.message)
    else ElMessage.warning('连接失败: ' + data.message)
  } catch (e) {
    ElMessage.error('测试失败: ' + e.message)
  }
}

async function deleteSource(id, name) {
  try {
    await ElMessageBox.confirm(`确认删除数据源「${name}」？`, '删除确认', { type: 'warning' })
    await request.post(`/datasources/api/${id}/delete`)
    ElMessage.success('已删除')
    loadSources()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

onMounted(loadSources)
</script>

<style scoped>
.ds-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 16px; }
.hint { font-size: 0.75rem; color: var(--text-tertiary, #94a3b8); }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; text-decoration: none; display: inline-block; transition: all 0.2s; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-danger:hover { background: rgba(239,68,68,0.2); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; white-space: nowrap; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); white-space: nowrap; }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.type { background: rgba(99,102,241,0.1); color: #6366f1; }
.badge.auth { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.on { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.off { background: rgba(100,116,139,0.1); color: #64748b; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
</style>
