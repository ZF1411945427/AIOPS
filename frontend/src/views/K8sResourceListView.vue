<template>
  <div class="k8s-list-page">
    <div class="page-header">
      <h1>{{ title }}</h1>
      <p>{{ subtitle }} · 共 {{ items.length }} 项</p>
      <button class="btn btn-guide" @click="showGuide = true">📖 操作说明</button>
    </div>

    <div class="toolbar">
      <select v-model="filters.cluster" @change="loadList">
        <option value="">全部集群</option>
        <option v-for="c in clusters" :key="c.name" :value="c.name">{{ c.name }}</option>
      </select>
      <input v-model="filters.namespace" class="input ns-input" placeholder="命名空间（留空查全部）" @keyup.enter="loadList" />
      <button class="btn" @click="loadList">查询</button>
      <button class="btn" @click="resetFilters">重置</button>
      <button v-if="canCreate" class="btn btn-primary" @click="openCreate">+ 创建 {{ title }}</button>
    </div>

    <div v-if="errorMsg" class="error-banner">⚠️ {{ errorMsg }}</div>

    <div class="panel">
      <div class="panel-head">{{ title }}</div>
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="items.length" class="table">
          <thead>
            <tr>
              <th v-for="col in columns" :key="col.key">{{ col.label }}</th>
              <th v-if="hasAction">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="it in items" :key="rowKey(it)">
              <td v-for="col in columns" :key="col.key">
                <template v-if="col.render === 'badge'"><span class="badge" :class="badgeClass(col.key, it[col.key])">{{ it[col.key] }}</span></template>
                <template v-else-if="col.render === 'list'"><span v-for="(v, i) in (it[col.key] || [])" :key="i" class="tag-mini">{{ v }}</span><span v-if="!(it[col.key] && it[col.key].length)" class="text-muted">-</span></template>
                <template v-else-if="col.render === 'lines'"><div class="lines-cell">{{ (it[col.key] || []).join('\n') || '-' }}</div></template>
                <template v-else-if="col.render === 'count'"><span class="badge count">{{ it[col.key] ?? 0 }}</span></template>
                <template v-else>{{ it[col.key] ?? '-' }}</template>
              </td>
              <td v-if="hasAction" class="action-cell">
                <button class="btn btn-sm" @click="openDescribe(it)">查看</button>
                <button v-if="resourceType === 'configmaps'" class="btn btn-sm" @click="openCmDetail(it)">编辑</button>
                <template v-if="resourceType === 'hpas'">
                  <button class="btn btn-sm" @click="openEditHpa(it)">编辑</button>
                  <button class="btn btn-sm btn-danger" @click="deleteHpa(it)">删除</button>
                </template>
                <button v-if="canDeleteRow(it)" class="btn btn-sm btn-danger" @click="deleteRow(it)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">📦</div>
          <div>暂无{{ title }}数据</div>
          <div class="text-muted" style="margin-top:4px;">请确认已选择集群或检查命名空间</div>
        </div>
      </div>
    </div>

    <div v-if="showDescribe" class="modal-overlay" @click.self="closeDescribe">
      <div class="modal-box modal-lg">
        <h3>{{ title }} 详情 · {{ describeMeta.name }}</h3>
        <div class="cm-meta">
          <span class="badge count">集群: {{ describeMeta.cluster }}</span>
          <span class="badge count">命名空间: {{ describeMeta.namespace }}</span>
          <span class="badge count">类型: {{ describeMeta.resourceType }}</span>
        </div>
        <div v-if="describeLoading" class="loading-state">加载中...</div>
        <div v-else>
          <button class="btn btn-sm" @click="copyDescribe">{{ copiedDescribe ? '已复制 ✓' : '复制 YAML' }}</button>
          <pre class="describe-yaml">{{ describeYaml }}</pre>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="closeDescribe">关闭</button>
        </div>
      </div>
    </div>

    <div v-if="showCmDialog" class="modal-overlay" @click.self="closeCmDialog">
      <div class="modal-box modal-lg">
        <h3>ConfigMap 详情 · {{ cmMeta.name }}</h3>
        <div class="cm-meta">
          <span class="badge count">集群: {{ cmMeta.cluster }}</span>
          <span class="badge count">命名空间: {{ cmMeta.namespace }}</span>
        </div>
        <div v-if="cmLoading" class="loading-state">加载中...</div>
        <div v-else class="cm-body">
          <div v-for="(row, i) in cmRows" :key="i" class="cm-row">
            <input v-model="row.key" class="input cm-key" placeholder="键" />
            <textarea v-model="row.value" class="input cm-val" rows="2" placeholder="值"></textarea>
            <button class="btn btn-sm btn-danger" @click="cmRows.splice(i, 1)">删</button>
          </div>
          <button class="btn btn-sm" @click="cmRows.push({ key: '', value: '' })">+ 新增键</button>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="closeCmDialog">取消</button>
          <button class="btn btn-primary" :disabled="cmSaving" @click="saveCm">{{ cmSaving ? '保存中...' : '保存' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showHpaDialog" class="modal-overlay" @click.self="closeHpaDialog">
      <div class="modal-box">
        <h3>{{ hpaDialogMode === 'create' ? '创建 HPA' : '编辑 HPA · ' + hpaForm.name }}</h3>
        <div v-if="hpaDialogMode === 'create'" class="form-row">
          <label>集群</label>
          <select v-model="hpaForm.cluster" class="input">
            <option value="">请选择集群</option>
            <option v-for="c in clusters" :key="c.name" :value="c.name">{{ c.name }}</option>
          </select>
        </div>
        <div v-if="hpaDialogMode === 'create'" class="form-row">
          <label>命名空间</label>
          <input v-model="hpaForm.namespace" class="input" placeholder="default" />
        </div>
        <div v-if="hpaDialogMode === 'create'" class="form-row">
          <label>HPA 名称</label>
          <input v-model="hpaForm.name" class="input" placeholder="如: web-hpa" />
        </div>
        <div v-if="hpaDialogMode === 'create'" class="form-row">
          <label>目标 Deployment</label>
          <input v-model="hpaForm.target" class="input" placeholder="如: web-deploy" />
        </div>
        <div class="form-row form-row-3">
          <div><label>最小副本</label><input v-model.number="hpaForm.min_replicas" type="number" min="1" class="input" /></div>
          <div><label>最大副本</label><input v-model.number="hpaForm.max_replicas" type="number" min="1" class="input" /></div>
          <div><label>CPU 目标利用率 (%)</label><input v-model.number="hpaForm.cpu_percent" type="number" min="1" max="100" class="input" /></div>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="closeHpaDialog">取消</button>
          <button class="btn btn-primary" :disabled="hpaSaving" @click="saveHpa">{{ hpaSaving ? '保存中...' : '保存' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showCreate" class="modal-overlay" @click.self="closeCreate">
      <div class="modal-box modal-lg">
        <h3>创建 {{ title }}</h3>
        <div class="form-grid">
          <div class="form-row">
            <label>集群 <span class="req">*</span></label>
            <select v-model="createForm.cluster" class="input">
              <option value="">请选择集群</option>
              <option v-for="c in clusters" :key="c.name" :value="c.name">{{ c.name }}</option>
            </select>
          </div>
          <div v-if="resourceType !== 'namespaces'" class="form-row">
            <label>命名空间</label>
            <input v-model="createForm.namespace" class="input" placeholder="default" />
          </div>
          <div class="form-row">
            <label>名称 <span class="req">*</span></label>
            <input v-model="createForm.name" class="input" :placeholder="namePlaceholder" />
          </div>
          <template v-if="resourceType === 'statefulsets' || resourceType === 'daemonsets'">
            <div class="form-row">
              <label>镜像 <span class="req">*</span></label>
              <input v-model="createForm.image" class="input" placeholder="如: nginx:1.25" />
            </div>
            <div class="form-row">
              <label>容器端口</label>
              <input v-model.number="createForm.container_port" type="number" min="1" class="input" placeholder="80" />
            </div>
          </template>
          <div v-if="resourceType === 'statefulsets'" class="form-row">
            <label>副本数</label>
            <input v-model.number="createForm.replicas" type="number" min="0" class="input" placeholder="1" />
          </div>
          <div v-if="resourceType === 'statefulsets'" class="form-row">
            <label>Headless Service</label>
            <input v-model="createForm.service_name" class="input" placeholder="如: web-svc（留空则用名称）" />
          </div>
          <template v-if="resourceType === 'statefulsets' || resourceType === 'daemonsets'">
            <div class="form-row">
              <label>CPU 请求</label>
              <input v-model="createForm.cpu_request" class="input" placeholder="如: 100m" />
            </div>
            <div class="form-row">
              <label>CPU 上限</label>
              <input v-model="createForm.cpu_limit" class="input" placeholder="如: 500m" />
            </div>
            <div class="form-row">
              <label>内存请求</label>
              <input v-model="createForm.mem_request" class="input" placeholder="如: 128Mi" />
            </div>
            <div class="form-row">
              <label>内存上限</label>
              <input v-model="createForm.mem_limit" class="input" placeholder="如: 512Mi" />
            </div>
          </template>
          <template v-if="resourceType === 'services'">
            <div class="form-row">
              <label>类型</label>
              <select v-model="createForm.svc_type" class="input">
                <option value="ClusterIP">ClusterIP</option>
                <option value="NodePort">NodePort</option>
                <option value="LoadBalancer">LoadBalancer</option>
              </select>
            </div>
            <div class="form-row">
              <label>端口 <span class="req">*</span></label>
              <input v-model.number="createForm.port" type="number" min="1" class="input" placeholder="80" />
            </div>
            <div class="form-row">
              <label>目标端口</label>
              <input v-model.number="createForm.target_port" type="number" min="1" class="input" placeholder="80" />
            </div>
            <div class="form-row">
              <label>协议</label>
              <select v-model="createForm.protocol" class="input">
                <option value="TCP">TCP</option>
                <option value="UDP">UDP</option>
              </select>
            </div>
          </template>
          <template v-if="resourceType === 'ingresses'">
            <div class="form-row">
              <label>Host <span class="req">*</span></label>
              <input v-model="createForm.host" class="input" placeholder="如: app.example.com" />
            </div>
            <div class="form-row">
              <label>路径</label>
              <input v-model="createForm.path" class="input" placeholder="/" />
            </div>
            <div class="form-row">
              <label>Service 名称 <span class="req">*</span></label>
              <input v-model="createForm.svc_name" class="input" placeholder="如: web-svc" />
            </div>
            <div class="form-row">
              <label>Service 端口 <span class="req">*</span></label>
              <input v-model.number="createForm.svc_port" type="number" min="1" class="input" placeholder="80" />
            </div>
            <div class="form-row">
              <label>启用 TLS</label>
              <select v-model="createForm.tls" class="input">
                <option :value="false">否</option>
                <option :value="true">是</option>
              </select>
            </div>
          </template>
          <template v-if="resourceType === 'secrets'">
            <div class="form-row">
              <label>类型</label>
              <select v-model="createForm.secret_type" class="input">
                <option value="Opaque">Opaque</option>
                <option value="kubernetes.io/tls">kubernetes.io/tls</option>
                <option value="kubernetes.io/dockerconfigjson">kubernetes.io/dockerconfigjson</option>
              </select>
            </div>
          </template>
          <template v-if="resourceType === 'pvcs'">
            <div class="form-row">
              <label>容量 <span class="req">*</span></label>
              <input v-model="createForm.storage" class="input" placeholder="如: 5Gi" />
            </div>
            <div class="form-row">
              <label>访问模式</label>
              <select v-model="createForm.access_mode" class="input">
                <option value="ReadWriteOnce">ReadWriteOnce</option>
                <option value="ReadOnlyMany">ReadOnlyMany</option>
                <option value="ReadWriteMany">ReadWriteMany</option>
              </select>
            </div>
            <div class="form-row">
              <label>StorageClass</label>
              <input v-model="createForm.storage_class" class="input" placeholder="留空使用默认" />
            </div>
          </template>
        </div>

        <div v-if="resourceType === 'configmaps' || resourceType === 'secrets'" class="data-block">
          <div class="data-block-title">数据键值（{{ resourceType === 'secrets' ? '明文值，提交时自动 Base64 编码' : 'ConfigMap 值' }}）</div>
          <div v-for="(row, i) in createDataRows" :key="i" class="cm-row">
            <input v-model="row.key" class="input cm-key" placeholder="键" />
            <textarea v-model="row.value" class="input cm-val" rows="2" :placeholder="resourceType === 'secrets' ? '明文值' : '值'"></textarea>
            <button class="btn btn-sm btn-danger" @click="createDataRows.splice(i, 1)">删</button>
          </div>
          <button class="btn btn-sm" @click="createDataRows.push({ key: '', value: '' })">+ 新增键</button>
        </div>

        <div class="modal-actions">
          <button class="btn" @click="closeCreate">取消</button>
          <button class="btn btn-primary" :disabled="createSaving" @click="saveCreate">{{ createSaving ? '保存中...' : '保存' }}</button>
        </div>
      </div>
    </div>
  <GuideDrawer v-model="showGuide" title="📖 K8s 资源列表操作说明">
    <div class="guide-section">
      <h4>页面功能</h4>
      <p>本页面提供统一的 K8s 资源列表查看与管理入口，支持多种资源类型：Namespace、StatefulSet、DaemonSet、Service、Ingress、ConfigMap、Secret、HPA、PVC、PV。</p>
    </div>
    <div class="guide-section">
      <h4>切换资源类型</h4>
      <p>通过左侧菜单或顶部导航选择不同的资源类型，页面自动切换对应的列表视图和操作按钮。</p>
      <div class="key-value-list">
        <div class="kv-row"><span class="kv-key">Deployment</span><span class="kv-val">Deployment 管理页面（独立）</span></div>
        <div class="kv-row"><span class="kv-key">Service</span><span class="kv-val">查看 ClusterIP、端口映射、类型</span></div>
        <div class="kv-row"><span class="kv-key">ConfigMap</span><span class="kv-val">查看和编辑键值对配置</span></div>
        <div class="kv-row"><span class="kv-key">Secret</span><span class="kv-val">查看密钥列表（值自动 Base64 编码）</span></div>
        <div class="kv-row"><span class="kv-key">Ingress</span><span class="kv-val">查看路由规则和 TLS 配置</span></div>
        <div class="kv-row"><span class="kv-key">PVC/PV</span><span class="kv-val">查看存储卷状态和容量</span></div>
      </div>
    </div>
    <div class="guide-section">
      <h4>搜索与筛选</h4>
      <ul>
        <li><strong>集群筛选</strong> — 下拉选择目标集群</li>
        <li><strong>命名空间</strong> — 输入命名空间名称后点击查询</li>
        <li><strong>重置</strong> — 清空筛选条件重新加载</li>
      </ul>
    </div>
    <div class="guide-section">
      <h4>查看 YAML 详情</h4>
      <p>点击列表中任意资源的 <strong>查看</strong> 按钮，弹出 YAML 详情弹窗，支持一键复制。对于 ConfigMap 还可直接编辑键值对。</p>
      <div class="tip-box">提示：HPA 资源支持直接在列表中创建、编辑和删除。</div>
    </div>
  </GuideDrawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'
import { useAppStore } from '@/stores/app'
import GuideDrawer from '@/components/GuideDrawer.vue'

const appStore = useAppStore()

const props = defineProps({
  resourceType: { type: String, required: true },
})

const TITLE_MAP = {
  namespaces: 'Namespace',
  statefulsets: 'StatefulSet',
  daemonsets: 'DaemonSet',
  services: 'Service',
  ingresses: 'Ingress',
  configmaps: 'ConfigMap',
  secrets: 'Secret',
  hpas: 'HPA',
  pvcs: 'PVC',
  pvs: 'PV',
}

const COLUMN_MAP = {
  namespaces: [
    { key: 'name', label: '名称' },
    { key: 'status', label: '状态', render: 'badge' },
    { key: 'age', label: '创建时间' },
  ],
  statefulsets: [
    { key: 'name', label: '名称' },
    { key: 'namespace', label: '命名空间' },
    { key: 'replicas', label: '副本' },
    { key: 'ready', label: '就绪' },
    { key: 'service', label: 'Service' },
    { key: 'image', label: '镜像' },
  ],
  daemonsets: [
    { key: 'name', label: '名称' },
    { key: 'namespace', label: '命名空间' },
    { key: 'desired', label: '期望' },
    { key: 'ready', label: '就绪' },
    { key: 'node_selector', label: '节点选择' },
  ],
  services: [
    { key: 'name', label: '名称' },
    { key: 'namespace', label: '命名空间' },
    { key: 'type', label: '类型' },
    { key: 'cluster_ip', label: 'ClusterIP' },
    { key: 'ports', label: '端口' },
  ],
  ingresses: [
    { key: 'name', label: '名称' },
    { key: 'namespace', label: '命名空间' },
    { key: 'rules', label: '规则', render: 'lines' },
    { key: 'tls', label: 'TLS', render: 'list' },
  ],
  configmaps: [
    { key: 'name', label: '名称' },
    { key: 'namespace', label: '命名空间' },
    { key: 'data_count', label: '键数量', render: 'count' },
    { key: 'data_keys', label: '键列表', render: 'list' },
  ],
  secrets: [
    { key: 'name', label: '名称' },
    { key: 'namespace', label: '命名空间' },
    { key: 'type', label: '类型' },
    { key: 'data_count', label: '键数量', render: 'count' },
  ],
  hpas: [
    { key: 'name', label: '名称' },
    { key: 'namespace', label: '命名空间' },
    { key: 'min_replicas', label: '最小副本' },
    { key: 'max_replicas', label: '最大副本' },
    { key: 'current_replicas', label: '当前副本' },
    { key: 'desired_replicas', label: '期望副本' },
    { key: 'target_cpu_utilization', label: 'CPU目标%' },
    { key: 'current_cpu_utilization', label: 'CPU当前%' },
  ],
  pvcs: [
    { key: 'name', label: '名称' },
    { key: 'namespace', label: '命名空间' },
    { key: 'status', label: '状态', render: 'badge' },
    { key: 'storage', label: '容量' },
    { key: 'access_modes', label: '访问模式' },
    { key: 'volume', label: 'Volume' },
  ],
  pvs: [
    { key: 'name', label: '名称' },
    { key: 'capacity', label: '容量' },
    { key: 'access_modes', label: '访问模式' },
    { key: 'reclaim', label: '回收策略' },
    { key: 'status', label: '状态', render: 'badge' },
    { key: 'claim', label: '绑定PVC' },
  ],
}

const loading = ref(false)
const showGuide = ref(false)
const items = ref([])
const clusters = ref([])
const errorMsg = ref('')
const filters = reactive({ cluster: appStore.k8sCluster || '', namespace: '' })

const showCmDialog = ref(false)
const cmLoading = ref(false)
const cmSaving = ref(false)
const cmMeta = reactive({ cluster: '', namespace: '', name: '' })
const cmRows = ref([])

const showDescribe = ref(false)
const describeLoading = ref(false)
const describeYaml = ref('')
const describeMeta = reactive({ cluster: '', namespace: '', name: '', resourceType: '' })
const copiedDescribe = ref(false)

const showHpaDialog = ref(false)
const hpaDialogMode = ref('create')
const hpaSaving = ref(false)
const hpaForm = reactive({ cluster: '', namespace: 'default', name: '', target: '', min_replicas: 1, max_replicas: 3, cpu_percent: 80 })

const showCreate = ref(false)
const createSaving = ref(false)
const createForm = reactive({
  cluster: '', namespace: 'default', name: '',
  image: '', replicas: 1, container_port: 80, service_name: '',
  cpu_request: '', cpu_limit: '', mem_request: '', mem_limit: '',
  svc_type: 'ClusterIP', port: 80, target_port: 80, protocol: 'TCP',
  host: '', path: '/', svc_name: '', svc_port: 80, tls: false,
  secret_type: 'Opaque',
  storage: '5Gi', access_mode: 'ReadWriteOnce', storage_class: '',
})
const createDataRows = ref([])

const CREATE_TYPES = ['namespaces', 'statefulsets', 'daemonsets', 'services', 'ingresses', 'configmaps', 'secrets', 'pvcs', 'hpas']
const DELETE_ROW_TYPES = ['namespaces', 'statefulsets', 'daemonsets', 'services', 'ingresses', 'configmaps', 'secrets', 'pvcs']

const canCreate = computed(() => CREATE_TYPES.includes(props.resourceType))
const namePlaceholder = computed(() => {
  const m = {
    namespaces: '如: dev-team', statefulsets: '如: web-sts', daemonsets: '如: log-agent',
    services: '如: web-svc', ingresses: '如: web-ingress', configmaps: '如: app-config',
    secrets: '如: app-secret', pvcs: '如: data-pvc', hpas: '如: web-hpa',
  }
  return m[props.resourceType] || '名称'
})

const title = computed(() => TITLE_MAP[props.resourceType] || props.resourceType)
const subtitle = computed(() => `${title.value} 资源列表`)
const columns = computed(() => COLUMN_MAP[props.resourceType] || [])
const hasAction = computed(() => ['namespaces', 'statefulsets', 'daemonsets', 'services', 'ingresses', 'configmaps', 'secrets', 'pvcs', 'hpas'].includes(props.resourceType))

function rowKey(it) {
  return (it.namespace || '') + '/' + (it.name || '') + '/' + Math.random().toString(36).slice(2, 6)
}

function badgeClass(key, val) {
  if (key === 'status') {
    if (val === 'Bound' || val === 'Available' || val === 'Active') return 'green'
    if (val === 'Pending' || val === 'Terminating') return 'yellow'
    return 'gray'
  }
  return 'gray'
}

async function loadList() {
  loading.value = true
  errorMsg.value = ''
  try {
    const data = await request.get('/k8s/api/' + props.resourceType, { params: { cluster: filters.cluster, namespace: filters.namespace } })
    items.value = data.items || []
    clusters.value = data.clusters || []
    if (data.error) errorMsg.value = data.error
    if (clusters.value.length && !clusters.value.some(c => c.name === filters.cluster)) {
      filters.cluster = clusters.value[0]?.name || ''
    }
    appStore.setK8sCluster(filters.cluster)
  } catch (e) {
    errorMsg.value = e.message || String(e)
    items.value = []
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filters.cluster = ''
  filters.namespace = ''
  loadList()
}

async function openDescribe(it) {
  describeMeta.cluster = filters.cluster
  describeMeta.namespace = it.namespace || ''
  describeMeta.name = it.name
  describeMeta.resourceType = props.resourceType
  showDescribe.value = true
  describeLoading.value = true
  describeYaml.value = ''
  copiedDescribe.value = false
  try {
    const url = `/k8s/api/describe/${props.resourceType}/${describeMeta.cluster}/${describeMeta.namespace}/${describeMeta.name}`
    const data = await request.get(url)
    if (data.error) {
      ElMessage.error('加载详情失败: ' + data.error)
      describeYaml.value = '# 加载失败: ' + data.error
    } else {
      describeYaml.value = data.yaml || '# 无内容'
    }
  } catch (e) {
    ElMessage.error('加载详情失败: ' + (e.message || e))
    describeYaml.value = '# 加载失败: ' + (e.message || e)
  } finally {
    describeLoading.value = false
  }
}

function closeDescribe() {
  showDescribe.value = false
  describeYaml.value = ''
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

async function openCmDetail(it) {
  cmMeta.cluster = filters.cluster
  cmMeta.namespace = it.namespace
  cmMeta.name = it.name
  showCmDialog.value = true
  cmLoading.value = true
  cmRows.value = []
  try {
    const data = await request.get(`/k8s/api/configmaps/${cmMeta.cluster}/${cmMeta.namespace}/${cmMeta.name}`)
    const obj = data.data || {}
    cmRows.value = Object.keys(obj).map(k => ({ key: k, value: obj[k] }))
  } catch (e) {
    ElMessage.error('加载详情失败: ' + (e.message || e))
  } finally {
    cmLoading.value = false
  }
}

function closeCmDialog() {
  showCmDialog.value = false
  cmRows.value = []
}

async function saveCm() {
  const data = {}
  for (const r of cmRows.value) {
    if (r.key) data[r.key] = r.value
  }
  cmSaving.value = true
  try {
    await request.post(`/k8s/api/configmaps/${cmMeta.cluster}/${cmMeta.namespace}/${cmMeta.name}/update`, { data })
    ElMessage.success('已保存')
    closeCmDialog()
    loadList()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.message || e))
  } finally {
    cmSaving.value = false
  }
}

function openCreateHpa() {
  hpaDialogMode.value = 'create'
  hpaForm.cluster = filters.cluster || (clusters.value[0]?.name || '')
  hpaForm.namespace = filters.namespace || 'default'
  hpaForm.name = ''
  hpaForm.target = ''
  hpaForm.min_replicas = 1
  hpaForm.max_replicas = 3
  hpaForm.cpu_percent = 80
  showHpaDialog.value = true
}

function openEditHpa(it) {
  hpaDialogMode.value = 'edit'
  hpaForm.cluster = filters.cluster
  hpaForm.namespace = it.namespace
  hpaForm.name = it.name
  hpaForm.target = ''
  hpaForm.min_replicas = it.min_replicas || 1
  hpaForm.max_replicas = it.max_replicas || 3
  hpaForm.cpu_percent = (typeof it.target_cpu_utilization === 'number' ? it.target_cpu_utilization : 80)
  showHpaDialog.value = true
}

function closeHpaDialog() {
  showHpaDialog.value = false
}

async function saveHpa() {
  if (hpaDialogMode.value === 'create') {
    if (!hpaForm.cluster || !hpaForm.name || !hpaForm.target) {
      ElMessage.warning('请填写集群、HPA 名称、目标 Deployment')
      return
    }
  }
  hpaSaving.value = true
  try {
    if (hpaDialogMode.value === 'create') {
      await request.post('/k8s/api/hpas/create', {
        cluster: hpaForm.cluster,
        namespace: hpaForm.namespace || 'default',
        name: hpaForm.name,
        target: hpaForm.target,
        min_replicas: hpaForm.min_replicas,
        max_replicas: hpaForm.max_replicas,
        cpu_percent: hpaForm.cpu_percent,
      })
    } else {
      await request.post(`/k8s/api/hpas/${hpaForm.cluster}/${hpaForm.namespace}/${hpaForm.name}/update`, {
        min_replicas: hpaForm.min_replicas,
        max_replicas: hpaForm.max_replicas,
        cpu_percent: hpaForm.cpu_percent,
      })
    }
    ElMessage.success(hpaDialogMode.value === 'create' ? '已创建' : '已更新')
    closeHpaDialog()
    loadList()
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.message || e))
  } finally {
    hpaSaving.value = false
  }
}

async function deleteHpa(it) {
  try {
    await ElMessageBox.confirm(`确认删除 HPA「${it.name}」？`, '删除确认', { type: 'warning' })
    await request.post(`/k8s/api/hpas/${filters.cluster}/${it.namespace}/${it.name}/delete`)
    ElMessage.success('已删除')
    loadList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

function canDeleteRow(it) {
  if (props.resourceType === 'hpas') return false
  return DELETE_ROW_TYPES.includes(props.resourceType)
}

function openCreate() {
  if (props.resourceType === 'hpas') {
    openCreateHpa()
    return
  }
  createForm.cluster = filters.cluster || (clusters.value[0]?.name || '')
  createForm.namespace = filters.namespace || 'default'
  createForm.name = ''
  createForm.image = ''
  createForm.replicas = 1
  createForm.container_port = 80
  createForm.service_name = ''
  createForm.cpu_request = ''
  createForm.cpu_limit = ''
  createForm.mem_request = ''
  createForm.mem_limit = ''
  createForm.svc_type = 'ClusterIP'
  createForm.port = 80
  createForm.target_port = 80
  createForm.protocol = 'TCP'
  createForm.host = ''
  createForm.path = '/'
  createForm.svc_name = ''
  createForm.svc_port = 80
  createForm.tls = false
  createForm.secret_type = 'Opaque'
  createForm.storage = '5Gi'
  createForm.access_mode = 'ReadWriteOnce'
  createForm.storage_class = ''
  createDataRows.value = (props.resourceType === 'configmaps' || props.resourceType === 'secrets') ? [{ key: '', value: '' }] : []
  showCreate.value = true
}

function closeCreate() {
  showCreate.value = false
  createDataRows.value = []
}

function buildCreatePayload() {
  const t = props.resourceType
  const p = { cluster: createForm.cluster, namespace: createForm.namespace || 'default', name: createForm.name }
  if (t === 'statefulsets') {
    p.image = createForm.image
    p.replicas = createForm.replicas
    p.service_name = createForm.service_name
    p.container_port = createForm.container_port
    p.cpu_request = createForm.cpu_request
    p.cpu_limit = createForm.cpu_limit
    p.mem_request = createForm.mem_request
    p.mem_limit = createForm.mem_limit
  } else if (t === 'daemonsets') {
    p.image = createForm.image
    p.container_port = createForm.container_port
    p.cpu_request = createForm.cpu_request
    p.cpu_limit = createForm.cpu_limit
    p.mem_request = createForm.mem_request
    p.mem_limit = createForm.mem_limit
  } else if (t === 'services') {
    p.type = createForm.svc_type
    p.port = createForm.port
    p.target_port = createForm.target_port
    p.protocol = createForm.protocol
  } else if (t === 'ingresses') {
    p.host = createForm.host
    p.path = createForm.path
    p.service_name = createForm.svc_name
    p.service_port = createForm.svc_port
    p.tls = createForm.tls
  } else if (t === 'configmaps' || t === 'secrets') {
    const data = {}
    for (const r of createDataRows.value) {
      if (r.key) data[r.key] = r.value
    }
    p.data = data
    if (t === 'secrets') p.type = createForm.secret_type
  } else if (t === 'pvcs') {
    p.storage = createForm.storage
    p.access_mode = createForm.access_mode
    p.storage_class = createForm.storage_class
  }
  return p
}

async function saveCreate() {
  if (!createForm.cluster || !createForm.name) {
    ElMessage.warning('请填写集群和名称')
    return
  }
  if (props.resourceType === 'statefulsets' || props.resourceType === 'daemonsets') {
    if (!createForm.image) { ElMessage.warning('请填写镜像'); return }
  }
  if (props.resourceType === 'ingresses') {
    if (!createForm.host || !createForm.svc_name) { ElMessage.warning('请填写 Host 和 Service 名称'); return }
  }
  const payload = buildCreatePayload()
  createSaving.value = true
  try {
    await request.post(`/k8s/api/${props.resourceType}/create`, payload)
    ElMessage.success('已创建')
    closeCreate()
    loadList()
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.message || e))
  } finally {
    createSaving.value = false
  }
}

async function deleteRow(it) {
  const t = props.resourceType
  const label = it.name
  try {
    await ElMessageBox.confirm(`确认删除 ${title.value}「${label}」？该操作不可恢复。`, '删除确认', { type: 'warning' })
    let url
    if (t === 'namespaces') {
      url = `/k8s/api/namespaces/${filters.cluster}/${it.name}/delete`
    } else {
      url = `/k8s/api/${t}/${filters.cluster}/${it.namespace}/${it.name}/delete`
    }
    await request.post(url)
    ElMessage.success('已删除')
    loadList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

watch(() => props.resourceType, () => {
  items.value = []
  loadList()
})

onMounted(loadList)
</script>

<style scoped>
.k8s-list-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.toolbar select { padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; }
.ns-input { width: 220px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; transition: all 0.2s; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.error-banner { background: rgba(239,68,68,0.1); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); border-radius: 8px; padding: 10px 14px; margin-bottom: 14px; font-size: 0.82rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); vertical-align: top; }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.text-muted { color: var(--text-tertiary, #94a3b8); font-size: 0.78rem; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; background: rgba(100,116,139,0.1); color: #64748b; }
.badge.green { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.yellow { background: rgba(245,158,11,0.1); color: #f59e0b; }
.badge.count { background: rgba(99,102,241,0.1); color: var(--accent, #6366f1); }
.tag-mini { display: inline-block; padding: 1px 6px; border-radius: 4px; background: rgba(99,102,241,0.08); color: var(--accent, #6366f1); font-size: 0.7rem; margin-right: 4px; margin-bottom: 2px; }
.lines-cell { white-space: pre-line; font-size: 0.78rem; color: var(--text-secondary, #64748b); max-width: 360px; }
.action-cell { white-space: nowrap; }
.action-cell .btn { margin-right: 4px; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 380px; max-width: 92vw; box-shadow: 0 8px 24px rgba(0,0,0,0.15); max-height: 88vh; overflow-y: auto; }
.modal-lg { min-width: 640px; }
.modal-box h3 { margin: 0 0 12px; font-size: 1rem; color: var(--text, #1e293b); }
.cm-meta { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.cm-body { margin-bottom: 12px; }
.cm-row { display: flex; gap: 8px; margin-bottom: 8px; align-items: flex-start; }
.cm-key { width: 200px; flex-shrink: 0; }
.cm-val { flex: 1; font-family: ui-monospace, monospace; font-size: 0.78rem; resize: vertical; }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.form-row-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 16px; }
.form-grid .form-row { margin-bottom: 0; }
.req { color: #ef4444; margin-left: 2px; }
.data-block { margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border, rgba(0,0,0,0.07)); }
.data-block-title { font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 8px; }
.describe-yaml { background: #1e1e1e; color: #d4d4d4; padding: 14px; border-radius: 8px; font-family: ui-monospace, 'Cascadia Code', Consolas, monospace; font-size: 0.78rem; line-height: 1.5; max-height: 60vh; overflow: auto; white-space: pre; margin-top: 10px; }
</style>
