<template>
  <div class="k8s-page">
    <div class="page-header">
      <div class="page-header-row">
        <div>
          <h1>K8s 集群部署</h1>
          <p>离线环境下基于 kubeadm 一键创建集群，复用离线仓库的私有 Registry / 包源 / 离线包，产出 kubeconfig 并自动接入监控</p>
        </div>
        <button class="btn primary" @click="openCreate">＋ 新建集群</button>
      </div>
    </div>

    <div class="toolbar">
      <button class="btn" :class="{ active: statusFilter === '' }" @click="setStatus('')">全部</button>
      <button class="btn" :class="{ active: statusFilter === 'succeeded' }" @click="setStatus('succeeded')">成功</button>
      <button class="btn" :class="{ active: statusFilter === 'failed' }" @click="setStatus('failed')">失败</button>
      <button class="btn" :class="{ active: statusFilter === 'running' }" @click="setStatus('running')">部署中</button>
      <button class="btn" :class="{ active: statusFilter === 'draft' }" @click="setStatus('draft')">草稿</button>
    </div>

    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="!plans.length" class="empty-state">
      暂无集群部署计划<br>点击右上角「新建集群」开始
    </div>
    <div v-else class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>集群名称</th>
            <th>版本</th>
            <th>运行时</th>
            <th>CNI</th>
            <th>节点</th>
            <th>状态</th>
            <th>更新时间</th>
            <th style="width: 200px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in plans" :key="p.id">
            <td class="pname">{{ p.name }}</td>
            <td>{{ p.kubernetes_version || '-' }}</td>
            <td>{{ p.runtime }}</td>
            <td>{{ p.cni }}</td>
            <td>{{ nodeSummary(p) }}</td>
            <td><span class="status-badge" :class="p.status">{{ statusText(p.status) }}</span></td>
            <td class="muted">{{ p.updated_at }}</td>
            <td class="row-actions">
              <button class="btn sm" @click="openDetail(p.id)">部署/详情</button>
              <button class="btn sm" @click="openEdit(p)">编辑</button>
              <button class="btn sm danger" @click="removePlan(p)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 新建/编辑 -->
    <div v-if="showEdit" class="modal-overlay" @click.self="closeEdit">
      <div class="modal-box wide">
        <div class="modal-head">
          <h3>{{ editId ? '编辑集群' : '新建集群' }}</h3>
          <button class="modal-close" @click="closeEdit">×</button>
        </div>
        <div class="modal-body">
          <div class="form-grid">
            <div class="form-row">
              <label>集群名称 <span class="req">*</span></label>
              <input v-model="form.name" placeholder="如 prod-k8s" />
            </div>
            <div class="form-row">
              <label>K8s 版本</label>
              <select v-model="form.kubernetes_version">
                <option value="" disabled>请选择 K8s 版本</option>
                <option v-for="ver in (meta.versions || [])" :key="ver" :value="ver">{{ ver }}</option>
              </select>
            </div>
            <div class="form-row">
              <label>容器运行时</label>
              <select v-model="form.runtime">
                <option value="containerd">containerd</option>
                <option value="docker">docker</option>
              </select>
            </div>
            <div class="form-row">
              <label>CNI</label>
              <select v-model="form.cni" @change="autoCidr">
                <option value="calico">calico</option>
                <option value="flannel">flannel</option>
                <option value="cilium">cilium</option>
              </select>
            </div>
            <div class="form-row">
              <label>Pod CIDR</label>
              <input v-model="form.pod_cidr" placeholder="10.244.0.0/16" />
            </div>
            <div class="form-row">
              <label>Service CIDR</label>
              <input v-model="form.service_cidr" placeholder="10.96.0.0/12" />
            </div>
            <div class="form-row">
              <label>证书有效期(年)</label>
              <input v-model.number="form.cert_expiry_years" type="number" min="1" max="100" placeholder="默认100≈永久" />
              <div class="hint" style="font-size:11px">CA 与 apiserver/etcd 等全部证书统一此年限(所有证书时长一致)，默认 100 年≈永久</div>
            </div>
            <div class="form-row">
              <label>控制面镜像仓库(imageRepository)</label>
              <input v-model="form.image_repository" placeholder="留空=用私有大仓库 /kubernetes" />
            </div>
            <div class="form-row">
              <label>离线包(可选)</label>
              <select v-model="form.bundle_id">
                <option :value="null">不使用</option>
                <option v-for="b in meta.bundles" :key="b.id" :value="b.id">{{ b.name }} ({{ b.version || '?' }})</option>
              </select>
            </div>
            <div class="form-row">
              <label>私有 Registry(镜像源)</label>
              <select v-model="form.registry_id">
                <option :value="null">默认仓库</option>
                <option v-for="r in meta.registries" :key="r.id" :value="r.id">{{ r.name }} ({{ r.registry_url }})</option>
              </select>
            </div>
          </div>

          <details class="proxy-block">
            <summary>🌐 网络代理(可选，仅在线部署需要)</summary>
            <div class="form-row" style="margin-bottom:8px">
              <label>快速选用</label>
              <select v-model="proxySelectedId" class="input" @change="applyProxy">
                <option :value="null">— 选择离线仓库已存代理 / 留空手填 —</option>
                <option v-for="px in proxyList" :key="px.id" :value="px.id">{{ px.name }}{{ px.is_default ? ' (默认)' : '' }}</option>
              </select>
            </div>
            <div class="form-grid" style="margin-top: 8px">
              <div class="form-row">
                <label>HTTP 代理</label>
                <input v-model="form.http_proxy" placeholder="如 http://192.168.100.2:7897" />
              </div>
              <div class="form-row">
                <label>HTTPS 代理</label>
                <input v-model="form.https_proxy" placeholder="留空=用 HTTP 代理" />
              </div>
              <div class="form-row">
                <label>NO_PROXY</label>
                <input v-model="form.no_proxy" placeholder="127.0.0.1,localhost,.local" />
              </div>
            </div>
            <div class="hint">设置后会注入到 apt/curl/wget 等所有联网步骤。NAT 模式下填宿主机代理 IP（如 VMware 网关 192.168.100.2:7897）</div>
          </details>

          <label class="checkbox-row" style="margin: 10px 0 6px">
            <input type="checkbox" v-model="form.untaint_master" />
            <span>去除主节点污点（允许 Pod 调度到 master）</span>
          </label>

          <div class="node-head">
            <h4>节点列表 <span class="req">*</span></h4>
            <button class="btn sm" @click="addNode">＋ 添加节点</button>
          </div>
          <div class="nodes">
            <div v-for="(n, i) in form.nodes" :key="i" class="node-row">
              <select v-model="n.host_role" class="role">
                <option value="master">master</option>
                <option value="worker">worker</option>
              </select>
              <select v-model="n.asset_id" class="asset">
                <option :value="null">手动(手填连接)</option>
                <option v-for="a in meta.assets" :key="a.id" :value="a.id">{{ a.name }} ({{ a.ip }})</option>
              </select>
              <input v-model="n.ip" placeholder="IP" class="ip" />
              <input v-model="n.hostname" placeholder="主机名" class="hn" />
              <input v-model="n.username" placeholder="用户(root)" class="user" />
              <input v-model="n.password" :type="showPw[i] ? 'text' : 'password'" placeholder="SSH密码" class="pw" />
              <input v-model.number="n.ssh_port" placeholder="22" class="port" />
              <button class="btn sm danger" @click="form.nodes.splice(i, 1)">删</button>
            </div>
          </div>
          <div class="hint">关联资产可选择自动读取连接配置；不关联则手动填 IP/用户名/密码。</div>
        </div>
        <div class="modal-foot">
          <button class="btn" @click="closeEdit">取消</button>
          <button class="btn primary" :disabled="saving" @click="savePlan">{{ saving ? '保存中...' : (editId ? '保存' : '创建') }}</button>
        </div>
      </div>
    </div>

    <!-- 详情/部署 -->
    <div v-if="detail" class="modal-overlay" @click.self="closeDetail">
      <div class="modal-box wide" ref="detailModalBox">
        <div class="modal-head">
          <h3>{{ detail.name }} <span class="status-badge" :class="detail.status">{{ statusText(detail.status) }}</span></h3>
          <button class="modal-close" @click="closeDetail">×</button>
        </div>
        <div class="modal-body">
          <div class="deploy-actions">
            <span class="kv" v-if="detail.kubernetes_version">版本 {{ detail.kubernetes_version }}</span>
            <span class="kv">运行时 {{ detail.runtime }}</span>
            <span class="kv">CNI {{ detail.cni }}</span>
            <span class="kv">Pod {{ detail.pod_cidr }}</span>
            <span class="kv">Svc {{ detail.service_cidr }}</span>
            <span class="kv" v-if="detail.image_repository">仓库 {{ detail.image_repository }}</span>
          </div>

          <div class="node-table-wrap">
            <table class="table">
              <thead>
                <tr><th>角色</th><th>IP</th><th>主机名</th><th>用户</th><th>SSH端口</th><th>状态</th></tr>
              </thead>
              <tbody>
                <tr v-for="n in detail.nodes" :key="n.id">
                  <td>{{ n.host_role }}</td>
                  <td>{{ n.ip }}</td>
                  <td>{{ n.hostname || '-' }}</td>
                  <td>{{ n.username || 'root' }}</td>
                  <td>{{ n.ssh_port }}</td>
                  <td><span class="status-badge" :class="n.status">{{ statusText(n.status) }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="phase-bar" v-if="deploying">
            <div v-for="(s, i) in phases" :key="i" class="phase" :class="phaseState(i)">
              {{ s }}
            </div>
          </div>

          <div v-if="precheckChecks.length" class="precheck-panel">
            <div class="precheck-title">预检明细</div>
            <div v-for="(c, i) in precheckChecks" :key="i" class="precheck-item">
              <span class="precheck-mark" :class="c.ok ? 'ok' : 'fail'">{{ c.ok ? '✓' : '✗' }}</span>
              <span class="precheck-name">{{ c.name }}</span>
              <span class="precheck-msg" :class="c.ok ? 'ok' : 'fail'">{{ c.message }}</span>
            </div>
            <div v-if="precheckAdvice" class="precheck-ai">
              <div class="precheck-ai-title">🤖 AI 预检建议{{ precheckAdvice.ai_generated ? '' : ' (规则)' }}</div>
              <div class="precheck-ai-summary">{{ precheckAdvice.summary }}</div>
              <div v-for="(r, ri) in (precheckAdvice.recommendations || [])" :key="'r'+ri" class="precheck-ai-item">• {{ r }}</div>
            </div>
          </div>

          <div class="terminal" ref="termBox" v-if="detail.logs && detail.logs.length">
            <div v-for="(l, i) in detail.logs" :key="i" class="tline" :class="l.type">
              <span class="tts">{{ l.ts }}</span>
              <span class="tnode" v-if="l.node">[{{ l.node }}]</span>
              <span>{{ l.message }}</span>
            </div>
          </div>
          <div v-else class="hint">暂无执行日志。点击「开始部署」观察实时进度。</div>

          <div v-if="decision" class="ai-decision-card">
            <div class="ai-decision-head">🤖 AI 需你决策</div>
            <div class="ai-decision-q">{{ decision.question }}</div>
            <div v-if="decision.root_cause" class="ai-decision-root">根因: {{ decision.root_cause }}</div>
            <div class="ai-decision-opts">
              <button v-for="o in (decision.options || [])" :key="o.key" class="ai-opt-btn"
                      :class="{ primary: o.key === 'fix' || o.key === 'retry_after_fix' }"
                      @click="submitDecision(o.key)">
                {{ o.title }}
              </button>
            </div>
            <div class="ai-decision-desc" v-if="decision.hint">{{ decision.hint }}</div>
          </div>

          <div class="k8s-report" v-if="detail.report && detail.status === 'succeeded'">
            <div class="k8s-report-head">
              <span class="k8s-report-title">📋 集群部署报告</span>
              <span class="k8s-report-status" :class="detail.report.status">{{ detail.report.status }}</span>
            </div>
            <div class="k8s-report-meta">
              <span>{{ detail.report.kubernetes_version }}</span>
              <span>运行时 {{ detail.report.runtime }}</span>
              <span>CNI {{ detail.report.cni }}</span>
              <span>{{ detail.report.master_count }} master / {{ detail.report.worker_count }} worker</span>
            </div>
            <div v-if="detail.report.ai_summary" class="k8s-report-ai">
              <div class="k8s-report-ai-title">🤖 AI 总结{{ detail.report.ai_summary.ai_generated ? '' : ' (规则)' }}</div>
              <div class="k8s-report-ai-sum">{{ detail.report.ai_summary.summary }}</div>
              <div v-for="(r, ri) in (detail.report.ai_summary.recommendations || [])" :key="'rs'+ri" class="k8s-report-ai-item">• {{ r }}</div>
            </div>
          </div>
        </div>
        <div class="modal-foot">
          <button class="btn" :disabled="deploying || detail.status === 'running'" @click="precheck">逻辑预检</button>
          <button class="btn danger" v-if="deploying || detail.status === 'running'" @click="stopDeploy">■ 停止</button>
          <button class="btn primary" v-else-if="detail.status === 'stopped'" @click="startDeploy">▶ 继续部署</button>
          <button class="btn primary" v-else @click="startDeploy">▶ 开始部署</button>
          <button class="btn primary" v-if="detail.status === 'succeeded' && !deploying" @click="addToAssets">＋ 添加到 K8s 资产</button>
          <button class="btn" v-if="detail.status === 'succeeded'" @click="downloadKubeconfig">下载 kubeconfig</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const plans = ref([])
const loading = ref(false)
const statusFilter = ref('')
const meta = ref({ bundles: [], registries: [], assets: [], versions: [] })
const proxyList = ref([])
const proxySelectedId = ref(null)
async function refreshProxyList() {
  try { const r = await request.get('/offline/api/proxies'); proxyList.value = r.items || [] } catch (e) { /* ignore */ }
}
function applyProxy() {
  const px = proxyList.value.find(p => p.id === proxySelectedId.value)
  if (!px) return
  form.value.http_proxy = px.http_proxy || ''
  form.value.https_proxy = px.https_proxy || ''
  form.value.no_proxy = px.no_proxy || '127.0.0.1,localhost,.local'
}

const showEdit = ref(false)
const editId = ref(null)
const saving = ref(false)
const showPw = ref({})
const form = ref(emptyForm())

const detail = ref(null)
const deploying = ref(false)
const deployWs = ref(null)
const termBox = ref(null)
const detailModalBox = ref(null)
const decision = ref(null)
const precheckChecks = ref([])
const precheckAdvice = ref(null)

const phases = ['预检', '环境准备', '运行时/二进制', 'kubeadm配置', '初始化', 'CNI', '节点加入']

function emptyForm() {
  return { name: '', kubernetes_version: 'v1.31.6', runtime: 'containerd', cni: 'calico',
           pod_cidr: '10.244.0.0/16', service_cidr: '10.96.0.0/12', image_repository: '', bundle_id: null, registry_id: null,
           http_proxy: '', https_proxy: '', no_proxy: '127.0.0.1,localhost,.local', untaint_master: false,
           cert_expiry_years: 100,
           nodes: [{ host_role: 'master', asset_id: null, ip: '', hostname: '', username: 'root', password: '', ssh_port: 22 }] }
}

function statusText(s) {
  return { draft: '草稿', planned: '已规划', running: '部署中', stopped: '已停止', succeeded: '成功', failed: '失败', rolled_back: '已回滚',
           pending: '待执行', ok: 'O' }[s] || s
}
function resetDeployState() {
  decision.value = null
  deploying.value = false
  precheckChecks.value = []
  precheckAdvice.value = null
  if (deployWs.value) { deployWs.value.close(); deployWs.value = null }
}
function nodeSummary(p) {
  if (!p.nodes && !p.node_count) return '-'
  const masters = (p.nodes || []).filter(n => n.host_role === 'master').length
  const workers = (p.nodes || []).length - masters
  return `M${masters} W${workers}`
}
function setStatus(s) { statusFilter.value = s; loadPlans() }
function phaseState(i) {
  const cur = detail.value ? (detail.value.current_step || 0) : 0
  if (i < cur) return 'done'
  if (i === cur) return 'cur'
  return ''
}
function autoCidr() {
  if (form.value.cni === 'cilium' && !form.value.pod_cidr) form.value.pod_cidr = '10.0.0.0/8'
  else if (!form.value.pod_cidr || form.value.pod_cidr === '10.244.0.0/16') form.value.pod_cidr = '10.244.0.0/16'
}

async function loadPlans() {
  loading.value = true
  try {
    const res = await request.get('/k8s-offline/api/plans', { params: { status: statusFilter.value, per_page: 100 } })
    plans.value = (res.items || []).map(p => ({ ...p, nodes: [] }))
  } catch (e) { ElMessage.error(e.message) } finally { loading.value = false }
}
async function loadMeta() {
  try { meta.value = await request.get('/k8s-offline/api/meta') } catch (e) { /* ignore */ }
}
function openCreate() {
  editId.value = null
  form.value = emptyForm()
  showPw.value = {}
  showEdit.value = true
}
async function openEdit(p) {
  try {
    const res = await request.get(`/k8s-offline/api/plans/${p.id}`, { params: { include_kubeconfig: false } })
    if (!res || !res.id) { ElMessage.error('加载计划详情失败'); return }
    editId.value = p.id
    form.value = {
      name: res.name || '',
      kubernetes_version: res.kubernetes_version || '',
      runtime: res.runtime || 'containerd',
      cni: res.cni || 'calico',
      pod_cidr: res.pod_cidr || '',
      service_cidr: res.service_cidr || '',
      image_repository: res.image_repository || '',
      bundle_id: res.bundle_id,
      registry_id: res.registry_id,
      http_proxy: res.http_proxy || '',
      https_proxy: res.https_proxy || '',
      no_proxy: res.no_proxy || '127.0.0.1,localhost,.local',
      untaint_master: !!res.untaint_master,
      cert_expiry_years: res.cert_expiry_years ?? 100,
      nodes: (res.nodes || []).map(n => ({
        host_role: n.host_role || 'worker',
        asset_id: n.asset_id,
        ip: n.ip || '',
        hostname: n.hostname || '',
        username: n.username || 'root',
        password: '',
        ssh_port: n.ssh_port || 22,
      })),
    }
    showPw.value = {}
    showEdit.value = true
  } catch (e) { ElMessage.error(e.message) }
}
function addNode() { form.value.nodes.push({ host_role: 'worker', asset_id: null, ip: '', hostname: '', username: 'root', password: '', ssh_port: 22 }) }
function closeEdit() { if (!saving.value) showEdit.value = false }

async function savePlan() {
  const nodes = form.value.nodes.filter(n => n.ip || n.asset_id)
  if (!form.value.name || !nodes.length) { ElMessage.warning('请填写集群名称且至少一个节点'); return }
  saving.value = true
  try {
    const payload = { ...form.value, nodes }
    let res
    if (editId.value) res = await request.post(`/k8s-offline/api/plans/${editId.value}/update`, payload)
    else res = await request.post('/k8s-offline/api/plans/create', payload)
    if (!res.ok) { ElMessage.error(res.message || '保存失败'); return }
    ElMessage.success(res.plan ? `已创建 ${res.plan.name}` : '已保存')
    showEdit.value = false
    loadPlans()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

async function removePlan(p) {
  try {
    await ElMessageBox.confirm(`确认删除集群计划「${p.name}」？`, '提示', { type: 'warning' })
  } catch (e) { return }
  try {
    const res = await request.post(`/k8s-offline/api/plans/${p.id}/delete`)
    if (!res.ok) { ElMessage.error(res.message || '删除失败'); return }
    ElMessage.success('已删除')
    loadPlans()
  } catch (e) { ElMessage.error(e.message) }
}

async function openDetail(id) {
  resetDeployState()
  detail.value = null
  try {
    const res = await request.get(`/k8s-offline/api/plans/${id}`, { params: { include_kubeconfig: false } })
    detail.value = res
    // 恢复该计划持久化的决策卡片（各计划独立，互不干扰）
    if (res.pending_decision && res.pending_decision.options && res.pending_decision.options.length) {
      decision.value = res.pending_decision
    }
  } catch (e) { ElMessage.error(e.message) }
}
function closeDetail() {
  deploying.value = false
  if (deployWs.value) { deployWs.value.close(); deployWs.value = null }
  detail.value = null
  resetDeployState()
}

watch(() => detail.value?.logs?.length, async () => {
  await nextTick()
  if (termBox.value) termBox.value.scrollTop = termBox.value.scrollHeight
})

async function refreshDetail(id) {
  const res = await request.get(`/k8s-offline/api/plans/${id}`, { params: { include_kubeconfig: false } })
  if (res && res.id) detail.value = res
}

async function precheck() {
  precheckChecks.value = []
  precheckAdvice.value = null
  try {
    const res = await request.post(`/k8s-offline/api/plans/${detail.value.id}/precheck`, null, { params: { test_ssh: true } })
    refreshDetail(detail.value.id)
    precheckChecks.value = res.checks || []
    precheckAdvice.value = res.ai_advice || null
    if (res.ok) ElMessage.success(`逻辑预检通过 (${(res.checks || []).length} 项)`)
    else ElMessage.warning('预检问题: ' + (res.issues || []).join('; '))
  } catch (e) { ElMessage.error(e.message) }
}
async function validateSsh() {
  ElMessage.info('正在校验节点 SSH 连通性...')
  try {
    const res = await request.post(`/k8s-offline/api/plans/${detail.value.id}/validate`, null, { params: { test_ssh: true } })
    const list = (res.ssh || []).map(s => `${s.node}: ${s.ok ? 'OK' : s.message}`).join('\n')
    await ElMessageBox.alert(list || '无节点', 'SSH 校验结果', { type: res.ok ? 'success' : 'warning' })
  } catch (e) { ElMessage.error(e.message) }
}

function startDeploy() {
  if (detail.value.status !== 'stopped') detail.value.logs = []
  deploying.value = true
  const url = `ws://${location.host}/k8s-offline/ws/plans/${detail.value.id}/deploy`
  deployWs.value = new WebSocket(url)
  deployWs.value.onmessage = (ev) => {
    let evt
    try { evt = JSON.parse(ev.data) } catch (e) { return }
    if (evt.type === 'phase') detail.value.current_step = evt.step
    else if (evt.type === 'status') detail.value.status = evt.status
    else if (evt.type === 'log' || evt.type === 'output') {
      if (!Array.isArray(detail.value.logs)) detail.value.logs = []
      detail.value.logs.push({
        type: evt.type,
        node: evt.node || '',
        message: evt.message !== undefined && evt.message !== null ? evt.message : (evt.line || ''),
        ts: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
      })
    }
    else if (evt.type === 'complete') {
      deploying.value = false
      refreshDetail(detail.value.id)
      ElMessage[evt.status === 'succeeded' ? 'success' : 'error'](evt.message || '部署结束')
    }     else if (evt.type === 'error') {
      ElMessage.error(evt.message)
    } else if (evt.type === 'decide') {
      decision.value = {
        id: evt.id,
        question: evt.question || '部署遇到问题，请选择处理方案',
        options: evt.options || [],
        hint: '',
      }
      if (!Array.isArray(detail.value.logs)) detail.value.logs = []
      detail.value.logs.push({
        type: 'ai', node: '', message: `🤖 需要你决策: ${decision.value.question}`,
        ts: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
      })
      // 弹窗提示，确保用户注意到决策来了
      ElMessage.info('🤖 AI 需要你决策，请查看下方的决策卡片')
      // 等待 DOM 更新后，将弹窗滚动到决策卡片位置
      nextTick(() => {
        const box = detailModalBox.value
        if (box) {
          // 把 modal-box 滚动到底部，让决策卡片可见
          setTimeout(() => { box.scrollTop = box.scrollHeight }, 100)
          setTimeout(() => { box.scrollTop = box.scrollHeight }, 500)
        }
      })
    } else if (evt.type === 'preflight') {
      if (!Array.isArray(detail.value.logs)) detail.value.logs = []
      detail.value.logs.push({
        type: 'ai', node: '', message: `🤖 AI 预检: containerd安装=${evt.containerd_install || '-'} 策略=${evt.strategy || '-'}` + ((evt.risks || []).length ? ` 风险: ${(evt.risks || []).join('; ')}` : ''),
        ts: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
      })
    }
    else if (evt.type === 'ai') {
      if (!Array.isArray(detail.value.logs)) detail.value.logs = []
      detail.value.logs.push({
        type: 'ai',
        node: '',
        message: `🤖 AI 诊断: ${evt.root_cause || ''} → 建议 ${evt.suggestion || 'fix'} (${evt.advice || ''})`,
        ts: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
      })
    }
  }
  deployWs.value.onclose = () => {
    deploying.value = false
    refreshDetail(detail.value.id)
  }
  deployWs.value.onerror = () => { deploying.value = false; ElMessage.error('WebSocket 连接失败') }
}

async function submitDecision(key) {
  const choice = (key || '').toString()
  try {
    const res = await request.post(`/k8s-offline/api/plans/${detail.value.id}/decision`, { choice })
    if (res && res.ok) {
      if (!Array.isArray(detail.value.logs)) detail.value.logs = []
      detail.value.logs.push({
        type: 'ai', node: '', message: `👉 你选择了: ${choice}`,
        ts: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
      })
      decision.value = null
      refreshDetail(detail.value.id)
    } else {
      ElMessage.warning((res && res.message) || '提交决策失败')
    }
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function stopDeploy() {
  try { request.post(`/k8s-offline/api/plans/${detail.value.id}/stop`) } catch (e) {}
  if (deployWs.value) deployWs.value.close()
  deploying.value = false
  refreshDetail(detail.value.id)
}

async function downloadKubeconfig() {
  try {
    const res = await request.get(`/k8s-offline/api/plans/${detail.value.id}/kubeconfig`)
    if (!res.ok || !res.kubeconfig) { ElMessage.warning('无 kubeconfig'); return }
    const blob = new Blob([res.kubeconfig], { type: 'text/yaml' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${detail.value.name}-kubeconfig.yaml`
    a.click()
    URL.revokeObjectURL(a.href)
  } catch (e) { ElMessage.error(e.message) }
}

async function addToAssets() {
  // 手动注册 + 确认编辑框：可修改资产/数据源名称后再注册
  let name = (detail.value.name || '').trim()
  try {
    const { value } = await ElMessageBox.prompt(
      '填写要注册的 K8s 资产名称（数据源名，可修改），确认后注册为 K8s 资产。',
      '注册为 K8s 资产',
      { inputValue: name, inputPlaceholder: '资产名称', confirmButtonText: '注册', cancelButtonText: '取消',
        inputValidator: v => (v && v.trim() ? true : '资产名称不能为空') }
    )
    name = (value || '').trim()
  } catch (e) {
    return // 用户取消
  }
  try {
    const res = await request.post(`/k8s-offline/api/plans/${detail.value.id}/to-assets`, { name })
    if (!res.ok) { ElMessage.warning(res.message || '操作失败'); return }
    const ds = res.datasource || {}
    ElMessage.success(`${res.message}：${ds.name} (${ds.endpoint || '-'})`)
    refreshDetail(detail.value.id)
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(() => { loadPlans(); loadMeta(); refreshProxyList() })
</script>

<style scoped>
.k8s-page { padding: 12px; }
.page-header { margin-bottom: 12px; }
.page-header-row { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.page-header h1 { font-size: 20px; margin: 0; }
.page-header p { color: #909399; font-size: 12px; margin: 4px 0 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.hint { color: #909399; font-size: 12px; margin-top: 6px; }

.btn { border: 1px solid #dcdfe6; background: #fff; color: #606266; border-radius: 4px; padding: 6px 12px; cursor: pointer; font-size: 13px; }
.btn:hover { border-color: #409eff; color: #409eff; }
.btn.primary { background: #409eff; border-color: #409eff; color: #fff; }
.btn.primary:hover { background: #66b1ff; }
.btn.danger { border-color: #f56c6c; color: #f56c6c; }
.btn.danger:hover { background: #fef0f0; }
.btn.sm { padding: 3px 8px; font-size: 12px; }
.btn.active { border-color: #409eff; color: #409eff; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; background: #fff; font-size: 13px; }
.table th, .table td { border: 1px solid #ebeef5; padding: 8px 10px; text-align: left; }
.table th { background: #f5f7fa; color: #909399; font-weight: 600; }
.table tr:hover td { background: #f5f7fa; }
.pname { font-weight: 600; }
.muted { color: #909399; font-size: 12px; }
.row-actions { display: flex; gap: 6px; }

.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: #fff; border-radius: 8px; max-width: 92vw; max-height: 88vh; overflow: auto; }
.modal-box.wide { width: 960px; }
.modal-head { display: flex; justify-content: space-between; align-items: center; padding: 14px 18px; border-bottom: 1px solid #e4e7ed; }
.modal-head h3 { margin: 0; font-size: 16px; display: flex; align-items: center; gap: 8px; }
.modal-close { border: none; background: none; font-size: 20px; cursor: pointer; color: #909399; }
.modal-body { padding: 16px 18px; }
.modal-foot { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 18px; border-top: 1px solid #e4e7ed; }

.form-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.form-row { margin-bottom: 8px; }
.form-row label { display: block; font-size: 13px; color: #606266; margin-bottom: 4px; }
.form-row .req { color: #f56c6c; }
input, select { width: 100%; border: 1px solid #dcdfe6; border-radius: 4px; padding: 6px 8px; font-size: 13px; box-sizing: border-box; }

.node-head { display: flex; align-items: center; justify-content: space-between; margin: 16px 0 8px; }
.node-head h4 { margin: 0; font-size: 14px; }
.node-head .req { color: #f56c6c; }

.proxy-block { border: 1px dashed #dcdfe6; border-radius: 4px; padding: 8px 12px; margin: 12px 0; background: #fafbfc; }
.proxy-block summary { cursor: pointer; font-size: 13px; color: #606266; user-select: none; }
.proxy-block summary:hover { color: #409eff; }

.checkbox-row { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #606266; cursor: pointer; }
.checkbox-row input[type="checkbox"] { width: auto; cursor: pointer; }
.nodes { display: flex; flex-direction: column; gap: 6px; }
.node-row { display: flex; gap: 6px; align-items: center; }
.node-row select, .node-row input { width: auto; }
.node-row .role { width: 80px; }
.node-row .asset { width: 180px; }
.node-row .ip { width: 130px; }
.node-row .hn { width: 120px; }
.node-row .user { width: 90px; }
.node-row .pw { width: 130px; }
.node-row .port { width: 70px; }

.status-badge { border-radius: 4px; padding: 1px 8px; font-size: 12px; }
.status-badge.draft, .status-badge.pending { background: #f4f4f5; color: #909399; }
.status-badge.running { background: #ecf5ff; color: #409eff; }
.status-badge.succeeded, .status-badge.ok { background: #f0f9eb; color: #67c23a; }
.status-badge.failed { background: #fef0f0; color: #f56c6c; }
.status-badge.rolled_back { background: #fdf6ec; color: #e6a23c; }

.deploy-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.deploy-actions .kv { background: #f0f2f5; border-radius: 4px; padding: 2px 8px; font-size: 12px; color: #606266; }

.node-table-wrap { margin-bottom: 12px; }

.phase-bar { display: flex; gap: 4px; margin: 12px 0; flex-wrap: wrap; }
.phase { padding: 3px 8px; font-size: 11px; border-radius: 3px; background: #f4f4f5; color: #909399; }
.phase.done { background: #f0f9eb; color: #67c23a; }
.phase.cur { background: #409eff; color: #fff; }

.terminal { background: #1e1e1e; color: #d4d4d4; border-radius: 4px; padding: 10px; max-height: 320px; overflow: auto; font-family: Consolas, Menlo, monospace; font-size: 12px; }
.terminal .tline { white-space: pre-wrap; word-break: break-all; margin-bottom: 2px; }
.terminal .tts { color: #6a9955; margin-right: 6px; }
.terminal .tnode { color: #569cd6; margin-right: 6px; }
.terminal .error { color: #f48771; }
.terminal .warn { color: #dcdcaa; }
.terminal .ok { color: #89d185; }
.terminal .info { color: #9cdcfe; }
.precheck-panel { background: #f6f8fa; border: 1px solid #e1e4e8; border-radius: 4px; padding: 10px; margin-bottom: 10px; }
.precheck-title { font-weight: 600; margin-bottom: 6px; color: #24292f; }
.precheck-item { display: flex; align-items: center; gap: 8px; padding: 3px 0; font-size: 13px; }
.precheck-mark.ok { color: #1a7f37; font-weight: 700; }
.precheck-mark.fail { color: #cf222e; font-weight: 700; }
.precheck-name { min-width: 160px; color: #24292f; }
.precheck-msg.ok { color: #1a7f37; }
.precheck-msg.fail { color: #cf222e; }
.terminal .ssh { color: #c586c0; }
.terminal .ai { color: #d9a0ff; }

.precheck-ai { border-top: 1px dashed #d0d7de; margin-top: 8px; padding-top: 8px; }
.precheck-ai-title { font-weight: 600; color: #4f46e5; margin-bottom: 4px; }
.precheck-ai-summary { font-size: 13px; color: #24292f; margin-bottom: 4px; }
.precheck-ai-item { font-size: 12px; color: #57606a; padding: 1px 0; }

.ai-decision-card { margin-top: 12px; background: #eef2ff; border: 1px solid #c7d2fe; border-radius: 8px; padding: 14px 16px; }
.ai-decision-head { font-weight: 700; color: #4f46e5; margin-bottom: 8px; }
.ai-decision-q { font-size: 13px; color: #111827; margin-bottom: 6px; }
.ai-decision-root { font-size: 12px; color: #6b7280; margin-bottom: 10px; }
.ai-decision-opts { display: flex; flex-wrap: wrap; gap: 8px; }
.ai-opt-btn { padding: 6px 14px; border-radius: 6px; border: 1px solid #c7d2fe; background: #fff; color: #3730a3; font-size: 13px; font-weight: 600; cursor: pointer; transition: all .15s; }
.ai-opt-btn:hover { background: #e0e7ff; }
.ai-opt-btn.primary { background: #4f46e5; border-color: #4f46e5; color: #fff; }
.ai-opt-btn.primary:hover { background: #4338ca; }
.ai-decision-desc { font-size: 12px; color: #8a63d2; margin-top: 8px; }

.k8s-report { margin-top: 12px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px 14px; }
.k8s-report-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.k8s-report-title { font-weight: 700; color: #111827; }
.k8s-report-status { font-size: 12px; padding: 2px 10px; border-radius: 12px; font-weight: 600; }
.k8s-report-status.succeeded { background: #dcfce7; color: #16a34a; }
.k8s-report-status.failed { background: #fee2e2; color: #dc2626; }
.k8s-report-status.stopped { background: #fee2e2; color: #dc2626; }
.k8s-report-meta { display: flex; flex-wrap: wrap; gap: 14px; font-size: 12px; color: #6b7280; margin-bottom: 8px; }
.k8s-report-ai { border-top: 1px dashed #d1d5db; padding-top: 8px; }
.k8s-report-ai-title { font-weight: 600; color: #4f46e5; margin-bottom: 4px; }
.k8s-report-ai-sum { font-size: 13px; color: #111827; margin-bottom: 4px; }
.k8s-report-ai-item { font-size: 12px; color: #57606a; padding: 1px 0; }

.modal-box .req { color: #f56c6c; }
.empty-state { text-align: center; color: #909399; padding: 30px 0; line-height: 1.8; }
.loading { text-align: center; color: #909399; padding: 30px 0; }
</style>
