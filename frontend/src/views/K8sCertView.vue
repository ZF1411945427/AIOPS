<template>
  <div class="cert-page">
    <div class="page-header">
      <div class="page-header-row">
        <div>
          <h1>K8s 证书巡检</h1>
          <p>多发行版证书有效期扫描 · 自动检测集群类型 · 支持一键续期</p>
        </div>
        <button class="btn btn-guide" @click="showGuide = true">📖 操作说明</button>
      </div>
    </div>

    <div class="toolbar">
      <select v-model="clusterId" class="input" style="width:240px" @change="onClusterChange">
        <option value="">选择集群</option>
        <option v-for="c in clusters" :key="c.id" :value="c.id">
          {{ c.name }} ({{ c.endpoint }}){{ distroBadge(c) }}
        </option>
      </select>
      <span v-if="selectedCluster" class="distro-tag" :class="'distro-' + (selectedCluster.k8s_distro || 'auto')">
        {{ distroLabel(selectedCluster.k8s_distro) }}
      </span>
      <button class="btn btn-primary" @click="loadInspect" :disabled="!clusterId || loading">
        {{ loading ? '巡检中...' : '开始巡检' }}
      </button>
      <button class="btn btn-warn" @click="openRenew" :disabled="!clusterId || !result || renewing">
        {{ renewing ? '续期中...' : '一键续期' }}
      </button>
      <span v-if="result" class="inspect-time">巡检时间：{{ result.inspect_time }}</span>
    </div>

    <div v-if="error" class="error-bar">{{ error }}</div>

    <template v-if="result">
      <div class="distro-info" v-if="result.distro">
        <span class="distro-badge" :class="'distro-' + result.distro">{{ result.distro_label || result.distro }}</span>
        <span class="inspect-method">巡检方式：{{ result.inspect_method || 'SSH' }}</span>
      </div>
      <div class="stat-row">
        <div class="stat-card">
          <div class="stat-num" style="color:#909399">{{ result.summary.total }}</div>
          <div class="stat-label">证书总数</div>
        </div>
        <div class="stat-card">
          <div class="stat-num" style="color:#67c23a">{{ result.summary.ok }}</div>
          <div class="stat-label">正常</div>
        </div>
        <div class="stat-card">
          <div class="stat-num" style="color:#e6a23c">{{ result.summary.warning }}</div>
          <div class="stat-label">预警</div>
        </div>
        <div class="stat-card">
          <div class="stat-num" style="color:#f56c6c">{{ result.summary.expiring }}</div>
          <div class="stat-label">临期 ≤90 天</div>
        </div>
        <div class="stat-card">
          <div class="stat-num" style="color:#f56c6c">{{ result.summary.expired }}</div>
          <div class="stat-label">已过期</div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">证书有效期清单</div>
        <div class="panel-body">
          <div class="table-wrap">
            <table class="table">
              <thead>
                <tr>
                  <th>证书</th>
                  <th>路径</th>
                  <th>剩余天数</th>
                  <th>到期时间</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="c in result.certs" :key="c.path">
                  <td>{{ c.name }}</td>
                  <td class="mono">{{ c.path }}</td>
                  <td><strong>{{ c.days_left === null ? '-' : c.days_left + ' 天' }}</strong></td>
                  <td>{{ c.not_after || '-' }}</td>
                  <td><span class="badge" :class="c.status">{{ statusText(c.status) }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </template>

    <div v-if="!result && !error && !loading" class="panel">
      <div class="panel-body">
        <div class="empty-state" style="line-height:1.8">
          <div>请选择一个 Kubernetes 集群并点击「开始巡检」</div>
          <div style="color:#909399;font-size:12px;margin-top:4px">
            自动检测集群类型（kubeadm / K3s / RKE / OpenShift / 自定义），支持 SSH 和 API 两种巡检方式
          </div>
        </div>
      </div>
    </div>

    <div v-if="renewModal.visible" class="modal-overlay" @click.self="closeRenew">
      <div class="modal-box" style="width:560px">
        <div class="modal-head">
          <h3>一键续期 · {{ result ? result.cluster : '' }}</h3>
          <button class="modal-close" @click="closeRenew">&times;</button>
        </div>
        <div class="modal-body">
          <p class="renew-tip" v-if="result && result.distro">
            集群类型：<strong>{{ result.distro_label || result.distro }}</strong>
            <span v-if="result.distro === 'cloud'"> — 云托管集群不支持续期</span>
          </p>
          <p class="renew-tip" v-if="result && result.distro !== 'cloud'">
            将执行对应发行版的续期命令。续期成功后 kubelet 检测到静态 Pod manifest 变更会自动重启组件。
          </p>
          <p class="renew-tip" v-if="result && result.distro === 'k3s'">
            K3s 续期命令：<code>k3s certificate rotate</code>，续期后需重启 K3s server。
          </p>
          <p class="renew-tip" v-if="result && result.distro === 'rke'">
            RKE 续期命令：<code>rke cert rotate</code>，需在 RKE 工作节点执行。
          </p>
          <label class="renew-years" v-if="result && result.distro === 'kubeadm'">
            续期年限：
            <input type="number" min="1" max="20" v-model.number="renewModal.years" />
            年
            <span class="renew-years-tip">（kubeadm 将重签全部证书为指定年限，并主动重启控制面）</span>
          </label>

          <div v-if="renewing" class="renew-processing">
            <p class="renew-hint">⏳ 正在续期并重启控制面组件（kube-apiserver / etcd / controller-manager / scheduler），集群将短暂不可用，约需 1-3 分钟...</p>
            <p class="renew-hint muted">如确认此为维护窗口，操作将自动完成，无需额外确认。</p>
          </div>
          <div v-else-if="renewResult" class="renew-result">
            <p class="renew-head" :style="{ color: renewResult.ok ? '#67c23a' : '#f56c6c' }">
              {{ renewResult.ok ? '✓ 续期成功' : '✕ 续期失败' }}
              <span v-if="renewResult.not_after_target" class="renew-target-inline">目标期限：{{ renewResult.not_after_target }}</span>
            </p>
            <pre class="renew-output-inline">{{ renewResult.output }}</pre>
            <p v-if="renewResult.restart_hint" class="renew-hint">{{ renewResult.restart_hint }}</p>
            <p v-if="renewResult.error && !renewResult.ok" class="renew-err">{{ renewResult.error }}</p>
            <button class="btn btn-sm" @click="closeRenew">关闭</button>
          </div>
        </div>
        <div class="modal-foot">
          <button class="btn" @click="closeRenew">取消</button>
          <button v-if="result && result.distro !== 'cloud'" class="btn btn-warn" @click="requestRenew" :disabled="renewing || renewingConfirm">{{ renewing ? '续期中...' : '确认续期' }}</button>
        </div>
      </div>
    </div>

    <div v-if="renewConfirmVisible" class="modal-overlay">
      <div class="modal-box" style="width:520px">
        <div class="modal-head">
          <h3>确认续期</h3>
          <button class="modal-close" @click="renewConfirmVisible = false">&times;</button>
        </div>
        <div class="modal-body">
          <p class="confirm-warn">⚠️ 此操作将重新签发集群全部证书，并<strong>主动重启控制面组件</strong>：</p>
          <ul class="confirm-list">
            <li>kube-apiserver</li>
            <li>kube-controller-manager</li>
            <li>kube-scheduler</li>
            <li>etcd</li>
          </ul>
          <p class="confirm-tip">
            续期期间控制面组件将短暂重启（约 1-3 分钟），请确保这是预期的维护窗口。续期年限：<strong>{{ renewModal.years }} 年</strong>。
          </p>
        </div>
        <div class="modal-foot">
          <button class="btn" @click="renewConfirmVisible = false">取消</button>
          <button class="btn btn-danger" @click="confirmRenew">确定执行</button>
        </div>
      </div>
    </div>

    <GuideDrawer v-model="showGuide" title="📖 K8s 证书巡检操作说明">
      <ol>
        <li>数据源管理中新建 <b>Kubernetes 集群</b> 类型数据源，填写 API Server 地址和 Token。</li>
        <li>如需 SSH 证书巡检，在高级配置中填写 master 节点 SSH 连接信息（ssh_host / ssh_user / ssh_password / ssh_port）。</li>
        <li>如需指定 K8s 发行版类型，在高级配置中选择 <b>k8s_distro</b>（自动检测 / kubeadm / K3s / RKE / OpenShift / 自定义路径 / 云托管）。</li>
        <li>本页选择集群后自动检测发行版，点击「开始巡检」扫描各发行版标准证书路径下的有效期。</li>
        <li>状态分级：<b>正常</b> &gt;90 天；<b>预警</b> 31~90 天；<b>临期</b> ≤30 天；<b>已过期</b> &lt;0 天。</li>
        <li>点击「一键续期」执行对应发行版的续期命令（kubeadm: <code>kubeadm certs renew all</code>；K3s: <code>k3s certificate rotate</code>；RKE: <code>rke cert rotate</code>）。</li>
        <li>云托管集群（EKS/AKS/GKE）通过 K8s API 读取 Secret 中的证书，不支持续期。</li>
      </ol>
    </GuideDrawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import GuideDrawer from '@/components/GuideDrawer.vue'
import request from '@/api/request'

const clusters = ref([])
const clusterId = ref('')
const loading = ref(false)
const error = ref('')
const result = ref(null)
const renewing = ref(false)
const renewingConfirm = ref(false)
const renewResult = ref(null)
const showGuide = ref(false)
const renewModal = ref({ visible: false, years: 3 })
const renewConfirmVisible = ref(false)

const selectedCluster = computed(() => clusters.value.find(c => c.id === clusterId.value) || null)

const DISTRO_LABELS = {
  auto: '自动检测', kubeadm: 'kubeadm', k3s: 'K3s',
  rke: 'RKE', openshift: 'OpenShift', binary: '自定义路径', cloud: '云托管',
}

function distroLabel(d) { return DISTRO_LABELS[d] || d || '自动检测' }

function distroBadge(c) {
  const d = c.k8s_distro || 'auto'
  return d !== 'auto' ? ` [${distroLabel(d)}]` : ''
}

function statusText(s) {
  return { ok: '正常', warning: '预警', expiring: '临期', expired: '已过期', error: '解析失败' }[s] || s
}

function onClusterChange() {
  result.value = null
  error.value = ''
  renewResult.value = null
}

async function loadClusters() {
  try {
    const res = await request.get('/k8s/cert/api/clusters')
    clusters.value = Array.isArray(res) ? res : (res.data || [])
  } catch (e) {
    error.value = '加载集群列表失败：' + (e.message || e)
  }
}

async function loadInspect() {
  if (!clusterId.value) return
  loading.value = true
  error.value = ''
  renewResult.value = null
  try {
    const res = await request.post('/k8s/cert/api/inspect', { cluster_id: clusterId.value })
    if (res.ok) {
      result.value = res
    } else {
      error.value = res.error || '巡检失败'
    }
  } catch (e) {
    error.value = '巡检请求失败：' + (e.message || e)
  } finally {
    loading.value = false
  }
}

function openRenew() {
  renewModal.value = { visible: true, years: 3 }
  renewResult.value = null
  renewing.value = false
  renewingConfirm.value = false
  renewConfirmVisible.value = false
}

function closeRenew() {
  renewModal.value.visible = false
  renewConfirmVisible.value = false
}

function requestRenew() {
  renewConfirmVisible.value = true
}

async function confirmRenew() {
  renewConfirmVisible.value = false
  renewing.value = true
  renewResult.value = null
  try {
    const res = await request.post('/k8s/cert/api/renew', {
      cluster_id: clusterId.value,
      years: renewModal.value.years || 0,
    })
    renewResult.value = res
    if (res.ok) {
      loadInspect()
    }
  } catch (e) {
    renewResult.value = { ok: false, output: '', error: String(e.message || e) }
  } finally {
    renewing.value = false
  }
}

onMounted(loadClusters)
</script>

<style scoped>
.cert-page { padding: 16px 20px; }
.page-header { margin-bottom: 16px; }
.page-header-row { display: flex; align-items: center; justify-content: space-between; }
.page-header h1 { font-size: 20px; margin: 0 0 4px; color: #303133; }
.page-header p { margin: 0; color: #909399; font-size: 13px; }
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
.inspect-time { color: #909399; font-size: 12px; margin-left: 8px; }
.distro-tag {
  display: inline-block; padding: 2px 10px; border-radius: 10px; font-size: 12px; font-weight: 600;
}
.distro-tag.distro-auto { background: #f4f4f5; color: #909399; }
.distro-tag.distro-kubeadm { background: #e6f7ff; color: #1890ff; }
.distro-tag.distro-k3s { background: #f6ffed; color: #52c41a; }
.distro-tag.distro-rke { background: #fff7e6; color: #fa8c16; }
.distro-tag.distro-openshift { background: #fff0f6; color: #eb2f96; }
.distro-tag.distro-cloud { background: #f0f5ff; color: #2f54eb; }
.distro-tag.distro-binary { background: #f4f4f5; color: #606266; }
.distro-info {
  display: flex; align-items: center; gap: 12px; margin-bottom: 12px; padding: 8px 14px;
  background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px;
}
.distro-badge {
  display: inline-block; padding: 3px 12px; border-radius: 10px; font-weight: 600; font-size: 13px;
}
.distro-badge.distro-kubeadm { background: #e6f7ff; color: #1890ff; }
.distro-badge.distro-k3s { background: #f6ffed; color: #52c41a; }
.distro-badge.distro-rke { background: #fff7e6; color: #fa8c16; }
.distro-badge.distro-openshift { background: #fff0f6; color: #eb2f96; }
.distro-badge.distro-cloud { background: #f0f5ff; color: #2f54eb; }
.distro-badge.distro-binary { background: #f4f4f5; color: #606266; }
.inspect-method { color: #909399; }
.stat-row { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.stat-card {
  flex: 1; min-width: 110px; background: #fff; border: 1px solid #ebeef5;
  border-radius: 8px; padding: 14px 16px; text-align: center;
}
.stat-num { font-size: 26px; font-weight: 700; }
.stat-label { font-size: 12px; color: #909399; margin-top: 4px; }
.error-bar {
  background: #fef0f0; color: #f56c6c; border: 1px solid #fbc4c4;
  border-radius: 6px; padding: 10px 14px; margin-bottom: 14px; font-size: 13px;
}
.mono { font-family: Consolas, Monaco, monospace; font-size: 12px; color: #606266; }
.badge {
  display: inline-block; padding: 2px 10px; border-radius: 10px; font-size: 12px;
}
.badge.ok { background: #f0f9eb; color: #67c23a; }
.badge.warning { background: #fdf6ec; color: #e6a23c; }
.badge.expiring { background: #fef0f0; color: #f56c6c; }
.badge.expired { background: #f56c6c; color: #fff; }
.badge.error { background: #f4f4f5; color: #909399; }
.btn { padding: 6px 14px; border: 1px solid #dcdfe6; background: #fff; border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: #409eff; border-color: #409eff; color: #fff; }
.btn-warn { background: #e6a23c; border-color: #e6a23c; color: #fff; }
.renew-tip { font-size: 13px; color: #606266; line-height: 1.7; }
.renew-tip code { background: #f4f4f5; padding: 2px 6px; border-radius: 4px; }
.renew-years { display: block; margin-top: 10px; font-size: 13px; color: #303133; }
.renew-years input { width: 70px; padding: 4px 8px; border: 1px solid #dcdfe6; border-radius: 4px; margin: 0 6px; }
.renew-years-tip { color: #909399; font-size: 12px; }
.renew-target { font-size: 13px; color: #67c23a; margin: 0 0 8px; }
.checkbox-line { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #606266; margin-top: 12px; }
.renew-output {
  background: #1d1f21; color: #c9d1d9; border-radius: 8px; padding: 14px; max-height: 300px; overflow: auto;
}
.renew-output pre { margin: 0; white-space: pre-wrap; font-family: Consolas, Monaco, monospace; font-size: 12px; line-height: 1.6; }
.renew-hint { color: #67c23a; font-size: 13px; margin: 10px 0 0; }
.renew-hint.muted { color: #909399; font-size: 12px; }
.table { width: 100%; border-collapse: collapse; }
.table th, .table td { padding: 8px 10px; border-bottom: 1px solid #ebeef5; text-align: left; font-size: 13px; }
.table th { background: #f5f7fa; color: #909399; font-weight: 600; }
.panel { background: #fff; border: 1px solid #ebeef5; border-radius: 8px; margin-bottom: 16px; }
.panel-head { padding: 12px 16px; border-bottom: 1px solid #ebeef5; font-weight: 600; font-size: 14px; }
.panel-body { padding: 12px 16px; }
.empty-state { text-align: center; color: #909399; padding: 30px 0; }
.renew-processing { margin-top: 12px; }
.renew-result { margin-top: 12px; background: #f7f8fa; border: 1px solid #ebeef5; border-radius: 8px; padding: 12px; }
.renew-head { font-size: 14px; font-weight: 600; margin: 0 0 8px; }
.renew-target-inline { font-size: 12px; color: #606266; font-weight: 400; margin-left: 8px; }
.renew-output-inline {
  margin: 0; white-space: pre-wrap; word-break: break-word; font-family: Consolas, Monaco, monospace;
  font-size: 12px; line-height: 1.6; background: #1d1f21; color: #c9d1d9; border-radius: 8px;
  padding: 12px; max-height: 260px; overflow: auto;
}
.renew-err { color: #f56c6c; font-size: 13px; margin: 10px 0 0; }
.btn-sm { padding: 6px 14px; font-size: 13px; margin-top: 12px; }
.btn-danger { background: #f56c6c; color: #fff; }
.confirm-warn { font-size: 14px; color: #e6a23c; margin: 0 0 10px; line-height: 1.6; }
.confirm-list { margin: 0 0 12px 20px; padding: 0; color: #606266; font-size: 13px; line-height: 1.9; }
.confirm-list li { margin: 2px 0; }
.confirm-tip { font-size: 13px; color: #909399; margin: 0; line-height: 1.6; }
.confirm-tip strong { color: #f56c6c; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card, #fff); border-radius: 12px; max-height: 85vh; overflow: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.15); }
.modal-head { display: flex; justify-content: space-between; align-items: center; padding: 14px 20px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); position: sticky; top: 0; background: var(--bg-card, #fff); z-index: 1; }
.modal-head h3 { margin: 0; font-size: 1rem; font-weight: 600; }
.modal-close { font-size: 1.4rem; background: none; border: none; cursor: pointer; color: var(--text-secondary, #64748b); padding: 0; line-height: 1; }
.modal-body { padding: 16px 20px; }
.modal-foot { display: flex; justify-content: flex-end; gap: 10px; padding: 14px 20px; border-top: 1px solid var(--border, rgba(0,0,0,0.07)); }
</style>