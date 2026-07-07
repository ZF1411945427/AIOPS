<template>
  <div class="deploy-page">
    <div class="page-header">
      <h1>K8s Deployment 管理</h1>
      <p>Deployment 列表与运维操作 · 共 {{ deployments.length }} 个</p>
    </div>

    <div class="toolbar">
      <select v-model="clusterFilter" class="input" @change="loadDeployments">
        <option value="">全部集群</option>
        <option v-for="c in clusters" :key="c.name" :value="c.name">{{ c.name }}</option>
      </select>
      <input v-model="namespaceFilter" class="input" placeholder="命名空间筛选" @keyup.enter="loadDeployments" />
      <button class="btn btn-primary" @click="loadDeployments">查询</button>
      <button class="btn" @click="resetFilter">重置</button>
      <button class="btn btn-success" @click="openCreate">+ 创建 Deployment</button>
    </div>

    <div class="panel">
      <div class="panel-head">Deployment 列表</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <div v-else-if="deployments.length" class="table-wrap">
          <table class="table">
            <thead><tr><th>名称</th><th>命名空间</th><th>集群</th><th>副本</th><th>就绪</th><th>策略</th><th>镜像</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="d in deployments" :key="d.name" class="row-click" @click="openManage(d)">
                <td class="name-cell">{{ d.name }}</td>
                <td>{{ d.namespace || '-' }}</td>
                <td>{{ d.cluster || '-' }}</td>
                <td>{{ d.replicas ?? '-' }}</td>
                <td>{{ d.available ?? '-' }}</td>
                <td>{{ d.strategy || 'RollingUpdate' }}</td>
                <td class="img-cell">{{ d.image || '-' }}</td>
                <td>{{ (d.available ?? 0) + '/' + (d.replicas ?? '?') }}</td>
                <td @click.stop>
                  <button class="btn btn-sm" @click="openDescribe(d)">查看</button>
                  <button class="btn btn-sm btn-primary" @click="openManage(d)">管理</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">🚀</div><div>暂无 Deployment</div></div>
      </div>
    </div>

    <div v-if="showManage" class="modal-overlay" @click.self="showManage = false">
      <div class="modal-box modal-lg">
        <h3>Deployment 管理 · {{ manageDep?.name }}</h3>
        <div v-if="manageLoading" class="loading-state">加载中...</div>
        <div v-else-if="manageDep">
          <div class="detail-grid">
            <div class="info-item"><span class="ik">名称</span><span class="iv">{{ manageDep.name }}</span></div>
            <div class="info-item"><span class="ik">命名空间</span><span class="iv">{{ manageDep.namespace || '-' }}</span></div>
            <div class="info-item"><span class="ik">集群</span><span class="iv">{{ manageDep.cluster || '-' }}</span></div>
            <div class="info-item"><span class="ik">副本</span><span class="iv">{{ manageDep.attrs?.replicas ?? '-' }}</span></div>
            <div class="info-item"><span class="ik">就绪</span><span class="iv">{{ manageDep.attrs?.ready_replicas ?? manageDep.attrs?.ready ?? '-' }}</span></div>
            <div class="info-item"><span class="ik">策略</span><span class="iv">{{ manageDep.attrs?.strategy || 'RollingUpdate' }}</span></div>
            <div class="info-item"><span class="ik">镜像</span><span class="iv">{{ manageDep.attrs?.image || '-' }}</span></div>
            <div class="info-item"><span class="ik">状态</span><span class="iv">{{ manageDep.status || '-' }}</span></div>
          </div>
          <div class="action-bar">
            <button class="btn btn-primary" @click="doRollout">重新部署</button>
            <button class="btn" @click="openScale">扩缩容</button>
            <button class="btn" @click="openCanary">金丝雀</button>
            <button class="btn btn-success" @click="doPromote">提升金丝雀</button>
            <button class="btn btn-danger" @click="openRollback">回滚</button>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showManage = false">关闭</button>
        </div>
      </div>
    </div>

    <div v-if="showDescribe" class="modal-overlay" @click.self="closeDescribe">
      <div class="modal-box modal-lg">
        <div class="log-header">
          <h3>Deployment 详情 (YAML) · {{ describeDep?.name }}</h3>
          <button class="btn btn-sm" @click="closeDescribe">✕</button>
        </div>
        <div v-if="describeLoading" class="loading-state">加载中...</div>
        <div v-else>
          <button class="btn btn-sm" @click="copyDescribe">{{ copiedDescribe ? '已复制 ✓' : '复制 YAML' }}</button>
          <pre class="describe-yaml">{{ describeYaml }}</pre>
        </div>
      </div>
    </div>

    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal-box">
        <h3>创建 Deployment</h3>
        <div class="form-row"><label>集群</label>
          <select v-model="createForm.cluster" class="input">
            <option value="">请选择</option>
            <option v-for="c in clusters" :key="c.name" :value="c.name">{{ c.name }}</option>
          </select>
        </div>
        <div class="form-row"><label>命名空间</label><input v-model="createForm.namespace" class="input" placeholder="default" /></div>
        <div class="form-row"><label>名称</label><input v-model="createForm.name" class="input" placeholder="my-app" /></div>
        <div class="form-row"><label>镜像</label><input v-model="createForm.image" class="input" placeholder="nginx:latest" /></div>
        <div class="form-row"><label>副本数</label><input v-model.number="createForm.replicas" type="number" min="1" class="input" /></div>
        <div class="form-row"><label>容器端口</label><input v-model.number="createForm.container_port" type="number" min="1" class="input" /></div>
        <div class="form-row"><label>CPU 请求/限制</label>
          <div class="dual-input"><input v-model="createForm.cpu_request" class="input" placeholder="100m" /><input v-model="createForm.cpu_limit" class="input" placeholder="500m" /></div>
        </div>
        <div class="form-row"><label>内存 请求/限制</label>
          <div class="dual-input"><input v-model="createForm.mem_request" class="input" placeholder="128Mi" /><input v-model="createForm.mem_limit" class="input" placeholder="512Mi" /></div>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" @click="doCreate" :disabled="creating">{{ creating ? '创建中...' : '创建' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showScale" class="modal-overlay" @click.self="showScale = false">
      <div class="modal-box">
        <h3>扩缩容 · {{ manageDep?.name }}</h3>
        <div class="form-row"><label>目标副本数</label><input v-model.number="scaleForm.replicas" type="number" min="0" class="input" /></div>
        <div class="modal-actions">
          <button class="btn" @click="showScale = false">取消</button>
          <button class="btn btn-primary" @click="doScale">确认</button>
        </div>
      </div>
    </div>

    <div v-if="showCanary" class="modal-overlay" @click.self="showCanary = false">
      <div class="modal-box">
        <h3>金丝雀发布 · {{ manageDep?.name }}</h3>
        <div class="form-row"><label>金丝雀副本数</label><input v-model.number="canaryForm.canary_replicas" type="number" min="1" class="input" /></div>
        <div class="tip">将创建 {{ manageDep?.name }}-canary 副本进行金丝雀验证</div>
        <div class="modal-actions">
          <button class="btn" @click="showCanary = false">取消</button>
          <button class="btn btn-primary" @click="doCanary">确认</button>
        </div>
      </div>
    </div>

    <div v-if="showRollback" class="modal-overlay" @click.self="showRollback = false">
      <div class="modal-box">
        <h3>回滚 · {{ manageDep?.name }}</h3>
        <div class="form-row"><label>回滚版本号</label><input v-model.number="rollbackForm.revision" type="number" min="0" class="input" placeholder="0 表示重新部署" /></div>
        <div class="tip">填写 0 触发重新部署，填写具体 revision 回滚到指定版本</div>
        <div class="modal-actions">
          <button class="btn" @click="showRollback = false">取消</button>
          <button class="btn btn-danger" @click="doRollback">确认回滚</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
const loading = ref(false)
const deployments = ref([])
const clusters = ref([])
const clusterFilter = ref(appStore.k8sCluster || '')
const namespaceFilter = ref('')

const showManage = ref(false)
const manageLoading = ref(false)
const manageDep = ref(null)

const showCreate = ref(false)
const creating = ref(false)
const createForm = ref({ cluster: '', namespace: 'default', name: '', image: '', replicas: 1, container_port: 80, cpu_request: '100m', cpu_limit: '500m', mem_request: '128Mi', mem_limit: '512Mi' })

const showDescribe = ref(false)
const describeLoading = ref(false)
const describeYaml = ref('')
const describeDep = ref(null)
const copiedDescribe = ref(false)

const showScale = ref(false)
const scaleForm = ref({ replicas: 1 })

const showCanary = ref(false)
const canaryForm = ref({ canary_replicas: 1 })

const showRollback = ref(false)
const rollbackForm = ref({ revision: 0 })

async function loadDeployments() {
  loading.value = true
  try {
    const data = await request.get('/k8s/api/deployments', { params: { cluster: clusterFilter.value, namespace: namespaceFilter.value } })
    deployments.value = data.items || []
    clusters.value = data.clusters || []
    if (clusters.value.length && !clusters.value.some(c => c.name === clusterFilter.value)) {
      clusterFilter.value = clusters.value[0]?.name || ''
    }
    appStore.setK8sCluster(clusterFilter.value)
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

function resetFilter() { clusterFilter.value = ''; namespaceFilter.value = ''; loadDeployments() }

async function openManage(d) {
  showManage.value = true
  manageLoading.value = true
  manageDep.value = d
  try {
    const data = await request.get(`/k8s/api/deployment/${d.cluster}/${d.namespace}/${d.name}/manage`)
    manageDep.value = data.deployment || d
  } catch (e) {
    ElMessage.error('详情加载失败: ' + (e.message || e))
  } finally {
    manageLoading.value = false
  }
}

function openCreate() {
  createForm.value = { cluster: clusters.value[0]?.name || '', namespace: 'default', name: '', image: '', replicas: 1, container_port: 80, cpu_request: '100m', cpu_limit: '500m', mem_request: '128Mi', mem_limit: '512Mi' }
  showCreate.value = true
}

async function doCreate() {
  const f = createForm.value
  if (!f.cluster || !f.name || !f.image) { ElMessage.warning('集群/名称/镜像必填'); return }
  creating.value = true
  try {
    await request.post('/containers/api/deploy/create', f)
    ElMessage.success('创建成功')
    showCreate.value = false
    loadDeployments()
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.message || e))
  } finally {
    creating.value = false
  }
}

async function doRollout() {
  try {
    await ElMessageBox.confirm('确认重新部署该 Deployment？', '提示', { type: 'warning' })
    const res = await request.post(`/k8s/api/deployment/${manageDep.value.cluster}/${manageDep.value.namespace}/${manageDep.value.name}/rollout`, {})
    if (res.ok) { ElMessage.success('已触发重新部署'); loadDeployments() }
    else ElMessage.error(res.error || '失败')
  } catch (e) { if (e !== 'cancel') ElMessage.error('操作失败: ' + (e.message || e)) }
}

function openScale() {
  scaleForm.value = { replicas: manageDep.value?.attrs?.replicas || 1 }
  showScale.value = true
}

async function doScale() {
  try {
    const res = await request.post(`/k8s/api/deployment/${manageDep.value.cluster}/${manageDep.value.namespace}/${manageDep.value.name}/scale`, { replicas: scaleForm.value.replicas })
    if (res.ok) { ElMessage.success(`已扩缩容到 ${scaleForm.value.replicas}`); showScale.value = false; loadDeployments() }
    else ElMessage.error(res.error || '失败')
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.message || e))
  }
}

function openCanary() {
  canaryForm.value = { canary_replicas: 1 }
  showCanary.value = true
}

async function doCanary() {
  try {
    const res = await request.post(`/k8s/api/deployment/${manageDep.value.cluster}/${manageDep.value.namespace}/${manageDep.value.name}/canary`, { canary_replicas: canaryForm.value.canary_replicas })
    if (res.ok) { ElMessage.success(`金丝雀已创建/更新 (${res.canary_name})`); showCanary.value = false }
    else ElMessage.error(res.error || '失败')
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.message || e))
  }
}

async function doPromote() {
  try {
    await ElMessageBox.confirm('确认提升金丝雀版本为主版本？此操作将用金丝雀镜像替换主 Deployment 并删除金丝雀。', '危险操作', { type: 'warning' })
    const res = await request.post(`/k8s/api/deployment/${manageDep.value.cluster}/${manageDep.value.namespace}/${manageDep.value.name}/promote`, {})
    if (res.ok) { ElMessage.success(`已提升金丝雀 (新镜像: ${res.new_image || '-'})`); loadDeployments() }
    else ElMessage.error(res.error || '失败')
  } catch (e) { if (e !== 'cancel') ElMessage.error('操作失败: ' + (e.message || e)) }
}

function openRollback() {
  rollbackForm.value = { revision: 0 }
  showRollback.value = true
}

async function doRollback() {
  try {
    const res = await request.post(`/k8s/api/deployment/${manageDep.value.cluster}/${manageDep.value.namespace}/${manageDep.value.name}/rollback`, { revision: rollbackForm.value.revision })
    if (res.ok) { ElMessage.success('已触发回滚'); showRollback.value = false; loadDeployments() }
    else ElMessage.error(res.error || '失败')
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.message || e))
  }
}

async function openDescribe(d) {
  describeDep.value = d
  showDescribe.value = true
  describeLoading.value = true
  describeYaml.value = ''
  copiedDescribe.value = false
  try {
    const data = await request.get(`/k8s/api/describe/deployments/${d.cluster}/${d.namespace}/${d.name}`)
    if (data.error) {
      describeYaml.value = '# 加载失败: ' + data.error
      ElMessage.error('加载详情失败: ' + data.error)
    } else {
      describeYaml.value = data.yaml || '# 无内容'
    }
  } catch (e) {
    describeYaml.value = '# 加载失败: ' + (e.message || e)
    ElMessage.error('加载详情失败: ' + (e.message || e))
  } finally {
    describeLoading.value = false
  }
}

function closeDescribe() {
  showDescribe.value = false
  describeYaml.value = ''
  describeDep.value = null
}

async function copyDescribe() {
  try {
    await navigator.clipboard.writeText(describeYaml.value)
    copiedDescribe.value = true
    setTimeout(() => { copiedDescribe.value = false }, 2000)
  } catch {
    ElMessage.warning('复制失败，请手动选择文本复制')
  }
}

onMounted(loadDeployments)
</script>

<style scoped>
.deploy-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.input { padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; min-width: 160px; box-sizing: border-box; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-success { background: #10b981; color: #fff; border-color: #10b981; }
.btn-success:hover { background: #059669; }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); }
.panel-body { padding: 8px 18px 18px; }
.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; white-space: nowrap; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr.row-click:hover td { background: var(--bg-hover, rgba(99,102,241,0.05)); cursor: pointer; }
.name-cell { font-weight: 600; }
.img-cell { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 380px; box-shadow: 0 8px 24px rgba(0,0,0,0.15); max-height: 86vh; overflow-y: auto; }
.modal-lg { min-width: 600px; max-width: 760px; }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; color: var(--text, #1e293b); }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; margin-bottom: 16px; }
.info-item { display: flex; gap: 8px; font-size: 0.82rem; line-height: 1.6; }
.ik { width: 72px; flex-shrink: 0; color: var(--text-secondary, #64748b); }
.iv { flex: 1; color: var(--text, #1e293b); word-break: break-all; }
.action-bar { display: flex; gap: 8px; flex-wrap: wrap; padding: 12px; background: var(--bg-hover, rgba(0,0,0,0.02)); border-radius: 8px; }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.dual-input { display: flex; gap: 8px; }
.dual-input .input { min-width: 0; flex: 1; }
.tip { font-size: 0.75rem; color: var(--text-secondary, #64748b); margin-top: 4px; line-height: 1.5; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.log-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.describe-yaml { background: #1e1e1e; color: #d4d4d4; padding: 14px; border-radius: 8px; font-family: ui-monospace, 'Cascadia Code', Consolas, monospace; font-size: 0.78rem; line-height: 1.5; max-height: 62vh; overflow: auto; white-space: pre; margin-top: 10px; }
.loading-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
</style>
