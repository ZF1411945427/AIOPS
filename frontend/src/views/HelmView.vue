<template>
  <div class="helm-page">
    <div class="page-header">
      <h1>Helm 应用管理</h1>
      <p>通过 Helm CLI 管理 Release · 仓库 · 安装 · 升级 · 回滚</p>
    </div>

    <div v-if="helmError" class="error-banner">⚠️ {{ helmError }}</div>

    <div class="tab-bar">
      <button :class="['tab', activeTab === 'releases' && 'active']" @click="switchTab('releases')">Release 列表</button>
      <button :class="['tab', activeTab === 'repos' && 'active']" @click="switchTab('repos')">仓库管理</button>
      <button :class="['tab', activeTab === 'install' && 'active']" @click="switchTab('install')">安装应用</button>
    </div>

    <div v-show="activeTab === 'releases'" class="tab-panel">
      <div class="toolbar">
        <select v-model="relCluster" class="input cluster-sel" @change="loadReleases">
          <option value="">请选择集群</option>
          <option v-for="c in clusters" :key="c.name" :value="c.name">{{ c.name }}</option>
        </select>
        <button class="btn" @click="loadReleases" :disabled="!relCluster">查询</button>
        <button class="btn" @click="loadReleases" :disabled="!relCluster">刷新</button>
      </div>

      <div class="panel">
        <div class="panel-head">Release 列表 <span class="count-tag" v-if="releases.length">{{ releases.length }}</span></div>
        <div class="panel-body">
          <div v-if="!relCluster" class="empty-state">请先选择集群</div>
          <div v-else-if="relLoading" class="loading-state">加载中...</div>
          <div v-else-if="relError" class="error-banner">⚠️ {{ relError }}</div>
          <table v-else-if="releases.length" class="table">
            <thead>
              <tr>
                <th>名称</th><th>命名空间</th><th>Chart</th><th>版本</th><th>状态</th><th>更新时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in releases" :key="r.name + '/' + r.namespace">
                <td class="mono">{{ r.name }}</td>
                <td>{{ r.namespace }}</td>
                <td class="mono">{{ r.chart }}</td>
                <td>{{ r.app_version || '-' }}</td>
                <td><span class="badge" :class="statusClass(r.status)">{{ r.status }}</span></td>
                <td>{{ fmtTime(r.updated) }}</td>
                <td class="action-cell">
                  <button class="btn btn-sm" @click="openStatus(r)">查看</button>
                  <button class="btn btn-sm" @click="openRollback(r)">回滚</button>
                  <button class="btn btn-sm btn-danger" @click="confirmUninstall(r)">卸载</button>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">⚓</div><div>该集群暂无 Release</div></div>
        </div>
      </div>
    </div>

    <div v-show="activeTab === 'repos'" class="tab-panel">
      <div class="repo-status" v-if="helmStatus.version">
        <span class="badge green">Helm {{ helmStatus.version }}</span>
      </div>
      <div class="repo-status" v-else-if="helmStatus.error">
        <span class="badge red">Helm 未就绪: {{ helmStatus.error }}</span>
      </div>

      <div class="panel">
        <div class="panel-head">添加仓库</div>
        <div class="panel-body">
          <div class="form-grid">
            <div class="form-row">
              <label>仓库名</label>
              <input v-model="repoForm.name" class="input" placeholder="如: bitnami" />
            </div>
            <div class="form-row">
              <label>仓库 URL</label>
              <input v-model="repoForm.url" class="input" placeholder="https://charts.bitnami.com/bitnami" />
            </div>
          </div>
          <div class="form-actions">
            <button class="btn btn-primary" @click="addRepo" :disabled="repoSaving">{{ repoSaving ? '添加中...' : '添加仓库' }}</button>
            <button class="btn" @click="updateRepos" :disabled="repoUpdating">{{ repoUpdating ? '更新中...' : '更新仓库索引' }}</button>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">仓库列表 <span class="count-tag" v-if="repos.length">{{ repos.length }}</span></div>
        <div class="panel-body">
          <div v-if="repoLoading" class="loading-state">加载中...</div>
          <div v-else-if="repoError" class="error-banner">⚠️ {{ repoError }}</div>
          <table v-else-if="repos.length" class="table">
            <thead><tr><th>名称</th><th>URL</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="rp in repos" :key="rp.name">
                <td class="mono">{{ rp.name }}</td>
                <td class="mono">{{ rp.url }}</td>
                <td><button class="btn btn-sm btn-danger" @click="removeRepo(rp)">删除</button></td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">📦</div><div>暂无仓库</div></div>
        </div>
      </div>
    </div>

    <div v-show="activeTab === 'install'" class="tab-panel">
      <div class="panel">
        <div class="panel-head">安装 / 升级 Release</div>
        <div class="panel-body">
          <div class="form-grid">
            <div class="form-row">
              <label>集群</label>
              <select v-model="installForm.cluster" class="input">
                <option value="">请选择集群</option>
                <option v-for="c in clusters" :key="c.name" :value="c.name">{{ c.name }}</option>
              </select>
            </div>
            <div class="form-row">
              <label>Release 名称</label>
              <input v-model="installForm.name" class="input" placeholder="如: my-app" />
            </div>
            <div class="form-row">
              <label>Chart 名</label>
              <input v-model="installForm.chart" class="input" placeholder="如: bitnami/nginx" />
            </div>
            <div class="form-row">
              <label>命名空间</label>
              <input v-model="installForm.namespace" class="input" placeholder="default" />
            </div>
            <div class="form-row">
              <label>版本 (可选)</label>
              <input v-model="installForm.version" class="input" placeholder="留空取最新" />
            </div>
          </div>

          <div class="chart-search-box">
            <label>Chart 搜索</label>
            <div class="search-row">
              <input v-model="chartKeyword" class="input" placeholder="输入关键词搜索可用 chart（如 nginx）" @input="onChartSearchInput" />
              <button class="btn" @click="searchCharts" :disabled="!chartKeyword">搜索</button>
            </div>
            <div v-if="chartSearching" class="text-muted" style="margin-top:6px;">搜索中...</div>
            <div v-else-if="chartResults.length" class="chart-results">
              <div v-for="ch in chartResults" :key="ch.name" class="chart-item" @click="pickChart(ch)">
                <div class="chart-name mono">{{ ch.name }}</div>
                <div class="chart-meta">{{ ch.version }} · {{ ch.description || '-' }}</div>
              </div>
            </div>
            <div v-else-if="chartSearched" class="text-muted" style="margin-top:6px;">无匹配 chart</div>
          </div>

          <div class="values-section">
            <div class="values-head" @click="valuesOpen = !valuesOpen">
              <span class="toggle-icon">{{ valuesOpen ? '▾' : '▸' }}</span>
              <span>Values YAML (可选)</span>
            </div>
            <textarea v-show="valuesOpen" v-model="installForm.values" class="input values-area" rows="10" placeholder="# key: value&#10;replicaCount: 2"></textarea>
          </div>

          <div class="form-actions">
            <button class="btn btn-primary" @click="doInstall" :disabled="installing">{{ installing ? '安装中...' : '安装' }}</button>
            <button class="btn" @click="doUpgrade" :disabled="upgrading">{{ upgrading ? '升级中...' : '升级' }}</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showStatusDialog" class="modal-overlay" @click.self="closeStatusDialog">
      <div class="modal-box modal-lg">
        <h3>Release 详情 · {{ statusMeta.name }}</h3>
        <div class="cm-meta">
          <span class="badge count">集群: {{ statusMeta.cluster }}</span>
          <span class="badge count">命名空间: {{ statusMeta.namespace }}</span>
        </div>
        <div v-if="statusLoading" class="loading-state">加载中...</div>
        <div v-else-if="statusError" class="error-banner">⚠️ {{ statusError }}</div>
        <div v-else-if="statusData">
          <div class="detail-grid">
            <div class="info-item"><span class="ik">名称</span><span class="iv">{{ statusData.name || '-' }}</span></div>
            <div class="info-item"><span class="ik">命名空间</span><span class="iv">{{ statusData.namespace || '-' }}</span></div>
            <div class="info-item"><span class="ik">Chart</span><span class="iv mono">{{ statusData.chart || '-' }}</span></div>
            <div class="info-item"><span class="ik">版本</span><span class="iv">{{ statusData.version || '-' }}</span></div>
            <div class="info-item"><span class="ik">状态</span><span class="iv"><span class="badge" :class="statusClass(statusData.info?.status)">{{ statusData.info?.status || '-' }}</span></span></div>
            <div class="info-item"><span class="ik">Notes</span><span class="iv notes-box">{{ statusData.info?.notes || '-' }}</span></div>
          </div>

          <div class="sub-title">历史版本</div>
          <div v-if="historyLoading" class="loading-state">加载中...</div>
          <table v-else-if="history.length" class="table">
            <thead><tr><th>Revision</th><th>更新时间</th><th>状态</th><th>Chart</th><th>App 版本</th><th>描述</th></tr></thead>
            <tbody>
              <tr v-for="h in history" :key="h.revision">
                <td>{{ h.revision }}</td>
                <td>{{ fmtTime(h.updated) }}</td>
                <td><span class="badge" :class="statusClass(h.status)">{{ h.status }}</span></td>
                <td class="mono">{{ h.chart }}</td>
                <td>{{ h.app_version || '-' }}</td>
                <td>{{ h.description || '-' }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-state">无历史记录</div>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="closeStatusDialog">关闭</button>
        </div>
      </div>
    </div>

    <div v-if="showRollbackDialog" class="modal-overlay" @click.self="closeRollbackDialog">
      <div class="modal-box">
        <h3>回滚 Release · {{ rollbackMeta.name }}</h3>
        <div class="form-row">
          <label>选择回滚到的 Revision</label>
          <select v-model="rollbackForm.revision" class="input">
            <option :value="null">请选择</option>
            <option v-for="h in rollbackHistory" :key="h.revision" :value="h.revision">Revision {{ h.revision }} · {{ h.status }} · {{ fmtTime(h.updated) }}</option>
          </select>
        </div>
        <div v-if="rollbackLoading" class="loading-state">加载历史中...</div>
        <div class="modal-actions">
          <button class="btn" @click="closeRollbackDialog">取消</button>
          <button class="btn btn-primary" @click="doRollback" :disabled="!rollbackForm.revision || rollbackSaving">{{ rollbackSaving ? '回滚中...' : '确认回滚' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const activeTab = ref('releases')
const clusters = ref([])
const helmStatus = reactive({ version: '', error: '' })
const helmError = ref('')

const relCluster = ref('')
const releases = ref([])
const relLoading = ref(false)
const relError = ref('')

const repos = ref([])
const repoLoading = ref(false)
const repoError = ref('')
const repoForm = reactive({ name: '', url: '' })
const repoSaving = ref(false)
const repoUpdating = ref(false)

const installForm = reactive({ cluster: '', name: '', chart: '', namespace: 'default', version: '', values: '' })
const installing = ref(false)
const upgrading = ref(false)
const valuesOpen = ref(false)

const chartKeyword = ref('')
const chartResults = ref([])
const chartSearching = ref(false)
const chartSearched = ref(false)
let searchTimer = null

const showStatusDialog = ref(false)
const statusLoading = ref(false)
const statusError = ref('')
const statusData = ref(null)
const statusMeta = reactive({ cluster: '', namespace: '', name: '' })
const history = ref([])
const historyLoading = ref(false)

const showRollbackDialog = ref(false)
const rollbackMeta = reactive({ cluster: '', namespace: '', name: '' })
const rollbackHistory = ref([])
const rollbackForm = reactive({ revision: null })
const rollbackLoading = ref(false)
const rollbackSaving = ref(false)

function switchTab(tab) {
  activeTab.value = tab
  if (tab === 'repos' && !repos.value.length && !repoError.value) loadRepos()
}

function statusClass(s) {
  if (!s) return 'gray'
  const v = s.toLowerCase()
  if (v === 'deployed' || v === 'superseded') return 'green'
  if (v === 'failed') return 'red'
  if (v === 'pending-install' || v === 'pending-upgrade' || v === 'pending-rollback' || v.startsWith('pending')) return 'yellow'
  if (v === 'uninstalled') return 'gray'
  return 'gray'
}

function fmtTime(t) {
  if (!t) return '-'
  try {
    const d = new Date(t)
    if (isNaN(d.getTime())) return t
    const p = (n) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
  } catch (e) {
    return t
  }
}

async function loadClusters() {
  try {
    const data = await request.get('/datasources/api/list')
    const list = (data.sources || []).filter((s) => s.type === 'kubernetes')
    clusters.value = list.map((s) => ({ name: s.name, endpoint: s.endpoint }))
  } catch (e) {
    helmError.value = '加载集群列表失败: ' + (e.message || e)
  }
}

async function loadHelmStatus() {
  try {
    const data = await request.get('/helm/api/status')
    helmStatus.version = data.version || ''
    helmStatus.error = data.error || ''
    if (!data.installed) {
      helmError.value = data.error || '未检测到 Helm CLI'
    }
  } catch (e) {
    helmStatus.error = e.message || String(e)
  }
}

async function loadReleases() {
  if (!relCluster.value) {
    ElMessage.warning('请先选择集群')
    return
  }
  relLoading.value = true
  relError.value = ''
  try {
    const data = await request.get('/helm/api/releases', { params: { cluster: relCluster.value } })
    releases.value = data.releases || []
    if (data.error) relError.value = data.error
  } catch (e) {
    relError.value = e.message || String(e)
    releases.value = []
  } finally {
    relLoading.value = false
  }
}

async function loadRepos() {
  repoLoading.value = true
  repoError.value = ''
  try {
    const data = await request.get('/helm/api/repos')
    repos.value = data.repos || []
    if (data.error) repoError.value = data.error
  } catch (e) {
    repoError.value = e.message || String(e)
    repos.value = []
  } finally {
    repoLoading.value = false
  }
}

async function addRepo() {
  if (!repoForm.name || !repoForm.url) {
    ElMessage.warning('请填写仓库名和 URL')
    return
  }
  repoSaving.value = true
  try {
    await request.post('/helm/api/repos/add', { name: repoForm.name, url: repoForm.url })
    ElMessage.success('仓库已添加')
    repoForm.name = ''
    repoForm.url = ''
    loadRepos()
  } catch (e) {
    ElMessage.error('添加失败: ' + (e.message || e))
  } finally {
    repoSaving.value = false
  }
}

async function removeRepo(rp) {
  try {
    await ElMessageBox.confirm(`确认删除仓库「${rp.name}」？`, '删除确认', { type: 'warning' })
    await request.post('/helm/api/repos/remove', { name: rp.name })
    ElMessage.success('已删除')
    loadRepos()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

async function updateRepos() {
  repoUpdating.value = true
  try {
    await request.post('/helm/api/repos/update')
    ElMessage.success('仓库索引已更新')
  } catch (e) {
    ElMessage.error('更新失败: ' + (e.message || e))
  } finally {
    repoUpdating.value = false
  }
}

function onChartSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    if (chartKeyword.value) searchCharts()
  }, 400)
}

async function searchCharts() {
  if (!chartKeyword.value) return
  chartSearching.value = true
  chartSearched.value = false
  try {
    const data = await request.get('/helm/api/charts', { params: { repo_keyword: chartKeyword.value } })
    chartResults.value = data.charts || []
    chartSearched.value = true
    if (data.error) ElMessage.warning(data.error)
  } catch (e) {
    ElMessage.error('搜索失败: ' + (e.message || e))
    chartResults.value = []
  } finally {
    chartSearching.value = false
  }
}

function pickChart(ch) {
  installForm.chart = ch.name
  if (ch.version) installForm.version = ch.version
  ElMessage.success('已选择 chart: ' + ch.name)
}

async function doInstall() {
  if (!installForm.cluster || !installForm.name || !installForm.chart) {
    ElMessage.warning('请填写集群、Release 名称、Chart 名')
    return
  }
  installing.value = true
  try {
    const data = await request.post('/helm/api/install', {
      cluster: installForm.cluster,
      name: installForm.name,
      chart: installForm.chart,
      namespace: installForm.namespace || 'default',
      version: installForm.version,
      values: installForm.values,
    })
    if (data.ok) {
      ElMessage.success(data.message || '安装成功')
    } else {
      ElMessage.error(data.error || '安装失败')
    }
  } catch (e) {
    ElMessage.error('安装失败: ' + (e.message || e))
  } finally {
    installing.value = false
  }
}

async function doUpgrade() {
  if (!installForm.cluster || !installForm.name || !installForm.chart) {
    ElMessage.warning('请填写集群、Release 名称、Chart 名')
    return
  }
  upgrading.value = true
  try {
    const data = await request.post('/helm/api/upgrade', {
      cluster: installForm.cluster,
      name: installForm.name,
      chart: installForm.chart,
      namespace: installForm.namespace || 'default',
      version: installForm.version,
      values: installForm.values,
    })
    if (data.ok) {
      ElMessage.success(data.message || '升级成功')
    } else {
      ElMessage.error(data.error || '升级失败')
    }
  } catch (e) {
    ElMessage.error('升级失败: ' + (e.message || e))
  } finally {
    upgrading.value = false
  }
}

async function openStatus(r) {
  statusMeta.cluster = relCluster.value
  statusMeta.namespace = r.namespace
  statusMeta.name = r.name
  showStatusDialog.value = true
  statusLoading.value = true
  statusError.value = ''
  statusData.value = null
  history.value = []
  historyLoading.value = true
  try {
    const data = await request.get(`/helm/api/status/${statusMeta.cluster}/${statusMeta.namespace}/${statusMeta.name}`)
    if (data.error) {
      statusError.value = data.error
    } else {
      statusData.value = data.status
    }
  } catch (e) {
    statusError.value = e.message || String(e)
  } finally {
    statusLoading.value = false
  }
  try {
    const hd = await request.get('/helm/api/history', { params: { cluster: statusMeta.cluster, name: statusMeta.name, namespace: statusMeta.namespace } })
    history.value = hd.history || []
    if (hd.error) history.value = []
  } catch (e) {
    history.value = []
  } finally {
    historyLoading.value = false
  }
}

function closeStatusDialog() {
  showStatusDialog.value = false
  statusData.value = null
  history.value = []
}

async function openRollback(r) {
  rollbackMeta.cluster = relCluster.value
  rollbackMeta.namespace = r.namespace
  rollbackMeta.name = r.name
  rollbackForm.revision = null
  rollbackHistory.value = []
  showRollbackDialog.value = true
  rollbackLoading.value = true
  try {
    const data = await request.get('/helm/api/history', { params: { cluster: rollbackMeta.cluster, name: rollbackMeta.name, namespace: rollbackMeta.namespace } })
    rollbackHistory.value = (data.history || []).slice().sort((a, b) => (b.revision || 0) - (a.revision || 0))
  } catch (e) {
    ElMessage.error('加载历史失败: ' + (e.message || e))
  } finally {
    rollbackLoading.value = false
  }
}

function closeRollbackDialog() {
  showRollbackDialog.value = false
  rollbackForm.revision = null
  rollbackHistory.value = []
}

async function doRollback() {
  if (!rollbackForm.revision) {
    ElMessage.warning('请选择要回滚的 revision')
    return
  }
  rollbackSaving.value = true
  try {
    const data = await request.post('/helm/api/rollback', {
      cluster: rollbackMeta.cluster,
      name: rollbackMeta.name,
      namespace: rollbackMeta.namespace,
      revision: rollbackForm.revision,
    })
    if (data.ok) {
      ElMessage.success(data.message || '回滚已触发')
      closeRollbackDialog()
      loadReleases()
    } else {
      ElMessage.error(data.error || '回滚失败')
    }
  } catch (e) {
    ElMessage.error('回滚失败: ' + (e.message || e))
  } finally {
    rollbackSaving.value = false
  }
}

async function confirmUninstall(r) {
  try {
    await ElMessageBox.confirm(`确认卸载 Release「${r.name}」(命名空间 ${r.namespace})？此操作不可恢复`, '卸载确认', { type: 'warning', confirmButtonText: '确认卸载', cancelButtonText: '取消' })
    const data = await request.post('/helm/api/uninstall', { cluster: relCluster.value, name: r.name, namespace: r.namespace })
    if (data.ok) {
      ElMessage.success(data.message || '已卸载')
      loadReleases()
    } else {
      ElMessage.error(data.error || '卸载失败')
    }
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('卸载失败: ' + (e.message || e))
  }
}

onMounted(() => {
  loadClusters()
  loadHelmStatus()
})
</script>

<style scoped>
.helm-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.tab-bar { display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.tab { padding: 8px 18px; border: none; background: transparent; color: var(--text-secondary, #64748b); cursor: pointer; font-size: 0.85rem; border-bottom: 2px solid transparent; transition: all 0.2s; }
.tab:hover { color: var(--text, #1e293b); }
.tab.active { color: var(--accent, #6366f1); border-bottom-color: var(--accent, #6366f1); font-weight: 600; }
.tab-panel { margin-top: 4px; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.cluster-sel { width: 220px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; transition: all 0.2s; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-danger:hover { background: rgba(239,68,68,0.18); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.error-banner { background: rgba(239,68,68,0.1); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); border-radius: 8px; padding: 10px 14px; margin-bottom: 14px; font-size: 0.82rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 16px; }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); display: flex; align-items: center; gap: 8px; }
.panel-body { padding: 16px 18px; }
.count-tag { display: inline-block; padding: 1px 8px; border-radius: 8px; background: rgba(99,102,241,0.1); color: var(--accent, #6366f1); font-size: 0.72rem; font-weight: 600; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); vertical-align: top; }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.mono { font-family: ui-monospace, "SFMono-Regular", Menlo, monospace; font-size: 0.8rem; }
.text-muted { color: var(--text-tertiary, #94a3b8); font-size: 0.78rem; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; background: rgba(100,116,139,0.1); color: #64748b; }
.badge.green { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.yellow { background: rgba(245,158,11,0.1); color: #f59e0b; }
.badge.red { background: rgba(239,68,68,0.1); color: #ef4444; }
.badge.count { background: rgba(99,102,241,0.1); color: var(--accent, #6366f1); }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.action-cell { white-space: nowrap; }
.action-cell .btn { margin-right: 4px; }
.repo-status { margin-bottom: 16px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.form-actions { display: flex; gap: 8px; margin-top: 8px; }
.chart-search-box { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--border, rgba(0,0,0,0.07)); }
.chart-search-box label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 6px; }
.search-row { display: flex; gap: 8px; }
.chart-results { margin-top: 8px; max-height: 240px; overflow-y: auto; border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; }
.chart-item { padding: 8px 12px; cursor: pointer; border-bottom: 1px solid var(--border, rgba(0,0,0,0.05)); }
.chart-item:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.chart-item:last-child { border-bottom: none; }
.chart-name { font-size: 0.82rem; font-weight: 600; color: var(--text, #1e293b); }
.chart-meta { font-size: 0.72rem; color: var(--text-secondary, #64748b); margin-top: 2px; }
.values-section { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--border, rgba(0,0,0,0.07)); }
.values-head { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 0.82rem; font-weight: 600; color: var(--text, #1e293b); user-select: none; }
.toggle-icon { display: inline-block; width: 12px; color: var(--text-secondary, #64748b); }
.values-area { margin-top: 8px; font-family: ui-monospace, "SFMono-Regular", Menlo, monospace; font-size: 0.78rem; resize: vertical; line-height: 1.5; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 380px; max-width: 92vw; box-shadow: 0 8px 24px rgba(0,0,0,0.15); max-height: 88vh; overflow-y: auto; }
.modal-lg { min-width: 640px; }
.modal-box h3 { margin: 0 0 12px; font-size: 1rem; color: var(--text, #1e293b); }
.cm-meta { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 16px; margin-bottom: 16px; }
.info-item { display: flex; flex-direction: column; gap: 2px; }
.info-item .ik { font-size: 0.72rem; color: var(--text-tertiary, #94a3b8); }
.info-item .iv { font-size: 0.85rem; color: var(--text, #1e293b); word-break: break-all; }
.notes-box { white-space: pre-wrap; background: var(--bg-hover, rgba(0,0,0,0.03)); padding: 8px 10px; border-radius: 6px; font-family: ui-monospace, monospace; font-size: 0.78rem; grid-column: 1 / -1; max-height: 220px; overflow-y: auto; }
.sub-title { font-weight: 600; font-size: 0.85rem; color: var(--text, #1e293b); margin: 8px 0 8px; padding-top: 8px; border-top: 1px solid var(--border, rgba(0,0,0,0.07)); }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
