<template>
  <div class="assets-page">
    <div class="page-header">
      <h1>资产管理</h1>
      <p>CMDB 配置管理 · 共 {{ assets.length }} 项资产</p>
    </div>

    <div class="toolbar">
      <input v-model="search" @input="onSearch" placeholder="搜索资产名称..." class="search-input">
      <select v-model="ciType" @change="loadAssets">
        <option value="">全部类型</option>
        <optgroup v-for="group in ciTypeGroups" :key="group.label" :label="group.label">
          <option v-for="ct in group.items" :key="ct.value" :value="ct.value">{{ ct.label }}</option>
        </optgroup>
      </select>
      <label class="filter-chk"><input type="checkbox" v-model="hideDeprecated" @change="applyFilter"> 隐藏已废弃</label>
      <label class="filter-chk"><input type="checkbox" v-model="onlyOrphan" @change="applyFilter"> 仅看孤岛</label>
      <a href="javascript:void(0)" class="btn btn-primary" @click="openCreate">+ 新增资产</a>
      <span class="toolbar-hint">K8s 子资源接入集群后自动发现（三层纳管：持久化 CI / 弱纳管 CI / 实时视图）</span>
    </div>

    <div class="tier-bar" v-if="k8sStats.total">
      <div class="tier-item"><span class="tier-dot" style="background:#10b981"></span><span class="tier-name">持久化 CI</span><span class="tier-num">{{ k8sStats.persistent }}</span><span class="tier-sub">集群/节点/命名空间/工作负载/Service/Ingress/PV/PVC</span></div>
      <div class="tier-item"><span class="tier-dot" style="background:#06b6d4"></span><span class="tier-name">弱纳管 CI</span><span class="tier-num">{{ k8sStats.weak }}</span><span class="tier-sub">ConfigMap/Secret（只存引用关系）</span></div>
      <div class="tier-item"><span class="tier-dot" style="background:#94a3b8"></span><span class="tier-name">实时视图</span><span class="tier-num">{{ k8sStats.realtime }}</span><span class="tier-sub">Pod/ReplicaSet（不入库，聚合到工作负载）</span></div>
      <div class="tier-item tier-warn" v-if="k8sStats.orphan > 0"><span class="tier-warn-icon">⚠</span><span class="tier-name">孤岛资源</span><span class="tier-num">{{ k8sStats.orphan }}</span><span class="tier-sub">未被引用，疑似配置漂移</span></div>
    </div>

    <div class="panel">
      <div class="panel-body">
        <div v-if="loading" class="loading-state">加载中...</div>
        <table v-else-if="pagedAssets.length" class="table">
          <thead>
            <tr>
              <th class="col-id">ID</th><th>名称</th><th>CI 类型</th><th>IP / 地址</th><th>状态</th><th>生命周期</th>
              <th>引用/孤岛</th><th>创建时间</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in pagedAssets" :key="a.id" :class="{ 'row-deprecated': a.status === 'deprecated', 'row-orphan': isOrphan(a) }">
              <td class="col-id text-sm">{{ a.id }}</td>
              <td><span class="asset-name">{{ shortName(a.name) }}</span><div class="asset-fullname" v-if="a.name.includes('/')">{{ a.name }}</div></td>
              <td><span class="badge ci-type" :style="ciTypeStyle(a.ci_type)">{{ a.ci_type || '-' }}</span></td>
              <td class="text-sm">{{ a.ip || '-' }}</td>
              <td><span class="badge" :class="a.status">{{ statusLabel(a.status) }}</span></td>
              <td><span class="badge lc-badge" :class="lifecycleClass(a.lifecycle_status)">{{ a.lifecycle_status }}</span></td>
              <td class="text-sm">
                <span v-if="a.refCount !== null" class="ref-info" :class="{ orphan: a.isOrphan }">
                  {{ a.refCount > 0 ? `被 ${a.refCount} 引用` : '孤岛 ⚠' }}
                </span>
                <span v-else class="text-muted">-</span>
              </td>
              <td class="text-sm">{{ a.created_at || '-' }}</td>
              <td>
                <button v-if="a.ci_type === 'kubernetes_cluster'" class="btn btn-sm btn-sync" :disabled="syncingId === a.id" @click="syncK8s(a)">{{ syncingId === a.id ? '同步中...' : '同步' }}</button>
                <a v-if="a.tags" href="javascript:void(0)" class="btn btn-sm btn-tag" @click="showTags(a)">标签</a>
                <a href="javascript:void(0)" class="btn btn-sm btn-lifecycle" @click="goLifecycle(a.id)">生命周期</a>
                <a href="javascript:void(0)" class="btn btn-sm" @click="openEdit(a.id)">编辑</a>
                <button class="btn btn-sm btn-danger" @click="deleteAsset(a.id, a.name)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">
          <div style="font-size:32px;margin-bottom:8px;">📦</div>
          <div>暂无资产数据</div>
        </div>
      </div>
    </div>

    <div class="pagination" v-if="filteredAssets.length > 0">
      <div class="pg-info">共 <b>{{ filteredAssets.length }}</b> 项</div>
      <div class="pg-pages">
        <button class="pg-btn" :disabled="currentPage === 1" @click="goPage(currentPage - 1)">‹ 上一页</button>
        <template v-for="(p, idx) in pageNumbers" :key="idx">
          <span v-if="p === '...'" class="pg-ellipsis">…</span>
          <button v-else class="pg-btn" :class="{ active: p === currentPage }" @click="goPage(p)">{{ p }}</button>
        </template>
        <button class="pg-btn" :disabled="currentPage === totalPages" @click="goPage(currentPage + 1)">下一页 ›</button>
      </div>
      <div class="pg-size">
        <select v-model.number="pageSize" class="pg-select">
          <option v-for="s in pageSizeOptions" :key="s" :value="s">{{ s }} 条/页</option>
        </select>
        <span class="pg-jump">跳至 <input class="pg-input" @keyup.enter="jumpPage($event)" placeholder="页"> 页</span>
      </div>
    </div>

    <div v-if="showForm" class="modal-overlay" @click.self="closeForm">
      <div class="modal-box wide">
        <h3>{{ formMode === 'create' ? '新增资产' : '编辑资产' }}</h3>

        <div class="form-section">
          <div class="section-title">基本信息</div>
          <div class="form-grid">
            <div class="form-row"><label>资产名称 *</label><input v-model="form.name" class="input" :placeholder="namePlaceholder"></div>
            <div class="form-row"><label>CI 类型</label>
              <select v-model="form.ci_type" class="input" @change="onCiTypeChange">
                <option value="" disabled>请选择</option>
                <optgroup v-for="group in ciTypeGroups" :key="group.label" :label="group.label">
                  <option v-for="ct in group.items" :key="ct.value" :value="ct.value">{{ ct.label }}</option>
                </optgroup>
              </select>
            </div>
            <div class="form-row" v-if="showField('ip')"><label>IP 地址</label><input v-model="form.ip" class="input" placeholder="10.0.0.1"></div>
            <div class="form-row"><label>状态</label>
              <select v-model="form.status" class="input">
                <option value="online">在线</option>
                <option value="offline">离线</option>
                <option value="degraded">降级</option>
              </select>
            </div>
            <div class="form-row"><label>标签</label><input v-model="form.tags" class="input" placeholder="逗号分隔，如 prod,web"></div>
          </div>
        </div>

        <div class="form-section" v-if="showSpecSection">
          <div class="section-title">规格属性</div>
          <div class="form-grid">
            <div class="form-row" v-for="f in ciTypeMeta.specFields" :key="f.key">
              <label>{{ f.label }}</label>
              <input v-model="specValues[f.key]" class="input" :type="f.type || 'text'" :placeholder="f.placeholder || ''">
            </div>
          </div>
        </div>

        <div class="form-section" v-if="form.ci_type">
          <div class="section-title">连接配置</div>
          <div class="conn-tip">{{ ciTypeMeta?.connectionTip || '配置该资产的连接信息，用于远程运维和监控。' }}</div>

          <template v-if="isSshType">
            <div class="form-grid">
              <div class="form-row"><label>连接方式</label>
                <select v-model="form.connection_type" class="input"><option value="ssh">SSH</option><option value="agent">Agent</option></select>
              </div>
              <div class="form-row"><label>登录用户</label><input v-model="form.ssh_user" class="input" placeholder="root"></div>
              <div class="form-row"><label>SSH 端口</label><input v-model.number="form.ssh_port" class="input" type="number" placeholder="22"></div>
              <div class="form-row"><label>密码 / 密钥</label><input v-model="form.ssh_password" class="input" type="password" placeholder="留空则不设置"></div>
            </div>
          </template>

          <template v-else-if="isSnmpType">
            <div class="form-grid">
              <div class="form-row"><label>连接方式</label>
                <select v-model="form.connection_type" class="input"><option value="ssh">SSH</option><option value="snmp">SNMP</option></select>
              </div>
              <div class="form-row"><label>SNMP 社区</label><input v-model="form.snmp_community" class="input" placeholder="public"></div>
              <div class="form-row"><label>SNMP 端口</label><input v-model.number="form.snmp_port" class="input" type="number" placeholder="161"></div>
              <div class="form-row"><label>SNMP 版本</label>
                <select v-model="form.snmp_version" class="input"><option value="v2c">v2c</option><option value="v3">v3</option></select>
              </div>
            </div>
          </template>

          <template v-else-if="form.ci_type === 'kubernetes_cluster'">
            <div class="form-grid">
              <div class="form-row full"><label>API Server 地址</label><input v-model="form.k8s_api_server" class="input" placeholder="https://192.168.1.10:6443"></div>
              <div class="form-row full"><label>Token</label><textarea v-model="form.k8s_token" class="input textarea" rows="2" placeholder="ServiceAccount Token 或 kubeconfig 内容"></textarea></div>
            </div>
          </template>

          <template v-else-if="form.ci_type === 'database'">
            <div class="form-grid">
              <div class="form-row"><label>数据库类型</label>
                <select v-model="form.db_subtype" class="input">
                  <option value="mysql">MySQL</option><option value="postgresql">PostgreSQL</option>
                  <option value="redis">Redis</option><option value="mongodb">MongoDB</option>
                  <option value="elasticsearch">Elasticsearch</option>
                </select>
              </div>
              <div class="form-row"><label>端口</label><input v-model.number="form.db_port" class="input" type="number" :placeholder="dbPortPlaceholder"></div>
              <div class="form-row"><label>用户名</label><input v-model="form.db_user" class="input" placeholder="root"></div>
              <div class="form-row"><label>密码</label><input v-model="form.db_password" class="input" type="password"></div>
              <div class="form-row"><label>数据库名</label><input v-model="form.db_name" class="input" placeholder="可选"></div>
            </div>
          </template>

          <template v-else-if="form.ci_type === 'middleware'">
            <div class="form-grid">
              <div class="form-row"><label>中间件类型</label>
                <select v-model="form.mw_subtype" class="input">
                  <option value="nginx">Nginx</option><option value="tomcat">Tomcat</option>
                  <option value="rabbitmq">RabbitMQ</option><option value="kafka">Kafka</option>
                </select>
              </div>
              <div class="form-row"><label>管理端口</label><input v-model.number="form.mw_port" class="input" type="number" placeholder="80/8080/9092"></div>
              <div class="form-row"><label>管理地址</label><input v-model="form.mw_admin_url" class="input" placeholder="http://..."></div>
            </div>
          </template>

          <template v-else-if="form.ci_type === 'storage_device'">
            <div class="form-grid">
              <div class="form-row"><label>连接方式</label>
                <select v-model="form.connection_type" class="input"><option value="ssh">SSH</option><option value="snmp">SNMP</option></select>
              </div>
              <div class="form-row"><label>存储类型</label>
                <select v-model="form.storage_type" class="input"><option value="nfs">NFS</option><option value="san">SAN</option><option value="nas">NAS</option><option value="object">对象存储</option></select>
              </div>
              <div class="form-row"><label>挂载路径</label><input v-model="form.storage_mount" class="input" placeholder="/mnt/data"></div>
              <div class="form-row"><label>容量(TB)</label><input v-model.number="form.storage_capacity" class="input" type="number" step="0.1" placeholder="10"></div>
            </div>
          </template>

          <template v-else-if="form.ci_type === 'business_app' || form.ci_type === 'api_service'">
            <div class="form-grid">
              <div class="form-row full"><label>服务地址</label><input v-model="form.app_url" class="input" placeholder="https://api.example.com/health"></div>
              <div class="form-row"><label>认证方式</label>
                <select v-model="form.app_auth" class="input"><option value="">无</option><option value="basic">Basic Auth</option><option value="bearer">Bearer Token</option></select>
              </div>
              <div class="form-row"><label>凭据</label><input v-model="form.app_credential" class="input" placeholder="用户名:密码 或 Token"></div>
            </div>
          </template>

          <template v-else-if="form.ci_type === 'ssl_certificate'">
            <div class="form-grid">
              <div class="form-row full"><label>域名</label><input v-model="form.cert_domain" class="input" placeholder="*.example.com"></div>
              <div class="form-row"><label>颁发者</label><input v-model="form.cert_issuer" class="input" placeholder="Let's Encrypt"></div>
              <div class="form-row"><label>到期日期</label><input v-model="form.cert_expiry" class="input" type="date"></div>
            </div>
          </template>

          <template v-else-if="form.ci_type === 'dns_record'">
            <div class="form-grid">
              <div class="form-row full"><label>域名</label><input v-model="form.dns_domain" class="input" placeholder="example.com"></div>
              <div class="form-row"><label>记录类型</label>
                <select v-model="form.dns_type" class="input"><option value="A">A</option><option value="CNAME">CNAME</option><option value="MX">MX</option><option value="TXT">TXT</option></select>
              </div>
              <div class="form-row"><label>记录值</label><input v-model="form.dns_value" class="input" placeholder="192.168.1.1"></div>
            </div>
          </template>

          <template v-else-if="form.ci_type === 'monitoring_endpoint'">
            <div class="form-grid">
              <div class="form-row full"><label>探针地址</label><input v-model="form.monitor_url" class="input" placeholder="https://.../metrics"></div>
              <div class="form-row"><label>探针类型</label>
                <select v-model="form.monitor_type" class="input"><option value="prometheus">Prometheus</option><option value="http">HTTP</option><option value="tcp">TCP</option><option value="icmp">ICMP</option></select>
              </div>
              <div class="form-row"><label>检查间隔(秒)</label><input v-model.number="form.monitor_interval" class="input" type="number" placeholder="60"></div>
            </div>
          </template>

          <template v-else>
            <div class="conn-note">该类型无需额外连接配置。</div>
          </template>
        </div>

        <div class="modal-actions">
          <button class="btn btn-conn-test" :disabled="testingConn || !form.ci_type" @click="testConnection">{{ testingConn ? '测试中...' : '测试连接' }}</button>
          <span v-if="connTestResult" class="conn-test-msg" :class="connTestResult.ok ? 'suc' : 'fail'">{{ connTestResult.ok ? '✅ 连接成功' : '❌ ' + connTestResult.message }}</span>
          <div style="flex:1"></div>
          <button class="btn" @click="closeForm">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="saveAsset">{{ saving ? '保存中...' : (formMode === 'create' ? '创建' : '保存') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const saving = ref(false)
const testingConn = ref(false)
const connTestResult = ref(null)
const assets = ref([])
const search = ref('')
const ciType = ref('')
let searchTimer = null
const showForm = ref(false)
const formMode = ref('create')

const ciTypeGroups = [
  { label: '🏗️ 基础设施层', items: [
    { value: 'server', label: '物理服务器' }, { value: 'virtual_machine', label: '虚拟机' },
    { value: 'network_device', label: '网络设备' }, { value: 'switch', label: '交换机' },
    { value: 'router', label: '路由器' }, { value: 'firewall', label: '防火墙' },
    { value: 'load_balancer', label: '负载均衡' }, { value: 'storage_device', label: '存储设备' },
    { value: 'database', label: '数据库' }, { value: 'middleware', label: '中间件' },
  ]},
  { label: '☁️ 云资源层', items: [
    { value: 'cloud_host', label: '云主机' }, { value: 'kubernetes_cluster', label: 'K8s 集群' },
  ]},
  { label: '🐳 K8s 持久化 CI', items: [
    { value: 'node', label: 'Node 节点' }, { value: 'namespace', label: 'Namespace' },
    { value: 'deployment', label: 'Deployment' }, { value: 'statefulset', label: 'StatefulSet' },
    { value: 'daemonset', label: 'DaemonSet' }, { value: 'service', label: 'Service' },
    { value: 'ingress', label: 'Ingress' }, { value: 'pv', label: 'PV 存储卷' },
    { value: 'pvc', label: 'PVC 存储声明' },
  ]},
  { label: '🔒 K8s 弱纳管 CI', items: [
    { value: 'configmap', label: 'ConfigMap' }, { value: 'secret', label: 'Secret' },
  ]},
  { label: '📊 业务层', items: [
    { value: 'business_app', label: '业务应用' }, { value: 'api_service', label: 'API 服务' },
    { value: 'ssl_certificate', label: 'SSL 证书' }, { value: 'dns_record', label: 'DNS 记录' },
    { value: 'monitoring_endpoint', label: '监控端点' },
  ]},
]

const PERSISTENT_TYPES = new Set(['node','namespace','deployment','statefulset','daemonset','service','ingress','pv','pvc','kubernetes_cluster','cluster'])
const WEAK_TYPES = new Set(['configmap','secret'])
const CI_TYPE_COLOR = {
  kubernetes_cluster:'#6366f1', cluster:'#6366f1', namespace:'#3b82f6', node:'#10b981',
  deployment:'#f59e0b', statefulset:'#f97316', daemonset:'#ea580c', service:'#8b5cf6',
  ingress:'#ec4899', pv:'#475569', pvc:'#64748b', configmap:'#06b6d4', secret:'#dc2626',
}

const sshTypes = ['server', 'virtual_machine', 'cloud_host', 'middleware']
const snmpTypes = ['network_device', 'switch', 'router', 'firewall', 'load_balancer', 'storage_device']
const isSshType = computed(() => sshTypes.includes(form.value.ci_type))
const isSnmpType = computed(() => snmpTypes.includes(form.value.ci_type))

const ciTypeMetaMap = {
  server: { specFields: [{ key: 'cpu_cores', label: 'CPU 核心数', type: 'number' }, { key: 'memory_gb', label: '内存(GB)', type: 'number' }, { key: 'disk_gb', label: '磁盘(GB)', type: 'number' }, { key: 'os', label: '操作系统' }, { key: 'manufacturer', label: '厂商' }, { key: 'model', label: '型号' }], connectionTip: '物理服务器使用 SSH 连接进行远程运维。' },
  virtual_machine: { specFields: [{ key: 'cpu_cores', label: 'vCPU', type: 'number' }, { key: 'memory_gb', label: '内存(GB)', type: 'number' }, { key: 'disk_gb', label: '系统盘(GB)', type: 'number' }, { key: 'os', label: '操作系统' }, { key: 'hypervisor', label: '虚拟化平台', placeholder: 'VMware/KVM' }], connectionTip: '虚拟机使用 SSH 连接进行远程运维。' },
  network_device: { specFields: [{ key: 'manufacturer', label: '厂商', placeholder: 'Cisco/Huawei' }, { key: 'model', label: '型号' }], connectionTip: '网络设备支持 SSH 和 SNMP。' },
  switch: { specFields: [{ key: 'manufacturer', label: '厂商' }, { key: 'model', label: '型号' }, { key: 'ports_count', label: '端口数', type: 'number' }], connectionTip: '交换机建议使用 SNMP 监控。' },
  router: { specFields: [{ key: 'manufacturer', label: '厂商' }, { key: 'model', label: '型号' }], connectionTip: '路由器支持 SSH 和 SNMP。' },
  firewall: { specFields: [{ key: 'manufacturer', label: '厂商' }, { key: 'model', label: '型号' }], connectionTip: '防火墙建议使用 SSH 连接。' },
  load_balancer: { specFields: [{ key: 'manufacturer', label: '厂商', placeholder: 'F5/Nginx' }, { key: 'algorithm', label: '调度算法', placeholder: 'round-robin' }], connectionTip: '负载均衡建议通过管理接口监控。' },
  storage_device: { specFields: [{ key: 'manufacturer', label: '厂商' }, { key: 'model', label: '型号' }], connectionTip: '存储设备支持 SNMP 或 SSH 连接。' },
  database: { specFields: [{ key: 'version', label: '版本' }], connectionTip: '配置数据库连接信息用于监控和巡检。' },
  middleware: { specFields: [{ key: 'version', label: '版本' }], connectionTip: '中间件通过管理端口进行健康检查。' },
  cloud_host: { specFields: [{ key: 'cpu_cores', label: 'vCPU', type: 'number' }, { key: 'memory_gb', label: '内存(GB)', type: 'number' }, { key: 'disk_gb', label: '系统盘(GB)', type: 'number' }, { key: 'cloud_provider', label: '云厂商', placeholder: '阿里云/AWS' }, { key: 'instance_id', label: '实例 ID' }], connectionTip: '云主机可通过 SSH 管理。' },
  kubernetes_cluster: { specFields: [{ key: 'version', label: 'K8s 版本' }, { key: 'node_count', label: '节点数', type: 'number' }], connectionTip: '添加 K8s 集群后系统可通过 API 自动发现集群下的所有子资源（节点、Deployment、Service、Ingress、Pod 等），无需手动逐一添加。' },
  business_app: { specFields: [{ key: 'owner', label: '负责人' }], connectionTip: '业务应用通过 HTTP 健康检查监控可用性。' },
  api_service: { specFields: [{ key: 'owner', label: '负责人' }], connectionTip: 'API 服务配置 HTTP 端点进行健康检查。' },
  ssl_certificate: { specFields: [{ key: 'cert_type', label: '证书类型', placeholder: 'DV/OV/EV' }], connectionTip: 'SSL 证书用于域名 HTTPS 配置。' },
  dns_record: { connectionTip: 'DNS 记录管理域名解析。' },
  monitoring_endpoint: { specFields: [{ key: 'threshold_warning', label: '警告阈值' }, { key: 'threshold_critical', label: '严重阈值' }], connectionTip: '配置探针定时检查服务状态。' },
}

const ciTypeMeta = computed(() => ciTypeMetaMap[form.value.ci_type])
const showSpecSection = computed(() => !!ciTypeMeta.value?.specFields)
const syncingId = ref(null)

const namePlaceholder = computed(() => ({
  server: '如 web-prod-01', virtual_machine: '如 vm-api-01', kubernetes_cluster: '如 k8s-prod',
  database: '如 db-master-01', middleware: '如 redis-cache-01', business_app: '如 订单系统',
  api_service: '如 用户服务 API', ssl_certificate: '如 example.com 证书',
  dns_record: '如 www.example.com', monitoring_endpoint: '如 Prometheus 生产',
})[form.value.ci_type] || '请输入资产名称')

const dbPortPlaceholder = computed(() => ({
  mysql: '3306', postgresql: '5432', redis: '6379', mongodb: '27017', elasticsearch: '9200',
})[form.value.db_subtype] || '3306')

const form = ref({})
const specValues = ref({})

const defaultForm = {
  id: null, name: '', ci_type: '', ip: '', status: 'online', tags: '',
  connection_type: 'ssh', ssh_user: 'root', ssh_port: 22, ssh_password: '',
  k8s_api_server: '', k8s_token: '',
  snmp_community: 'public', snmp_port: 161, snmp_version: 'v2c',
  db_subtype: 'mysql', db_port: 3306, db_user: 'root', db_password: '', db_name: '',
  mw_subtype: 'nginx', mw_port: 80, mw_admin_url: '',
  app_url: '', app_auth: '', app_credential: '',
  cert_domain: '', cert_issuer: '', cert_expiry: '',
  dns_domain: '', dns_type: 'A', dns_value: '',
  monitor_url: '', monitor_type: 'http', monitor_interval: 60,
  storage_type: 'nfs', storage_mount: '', storage_capacity: 0,
  version: '',
}

const showableFields = {
  server: { ip: true }, virtual_machine: { ip: true }, cloud_host: { ip: true },
  network_device: { ip: true }, switch: { ip: true }, router: { ip: true },
  firewall: { ip: true }, load_balancer: { ip: true }, storage_device: { ip: true },
  database: { ip: true }, middleware: { ip: true },
  kubernetes_cluster: { ip: true }, business_app: { ip: true }, api_service: { ip: true },
}

function showField(key) { return showableFields[form.value.ci_type]?.[key] ?? false }

function statusLabel(s) { return { online: '在线', offline: '离线', degraded: '降级', deprecated: '已废弃' }[s] || s }
function lifecycleClass(s) {
  if (s === 'active') return 'lc-active'
  if (s === 'maintenance') return 'lc-maintenance'
  if (s === 'retired') return 'lc-retired'
  return 'lc-provisioning'
}
function goLifecycle(assetId) {
  if (typeof window !== 'undefined') window._lifecycleFocusId = assetId
  if (typeof window !== 'undefined' && typeof window._navigateTo === 'function') window._navigateTo('lifecycle')
  else ElMessage.warning('请从左侧菜单进入「资产生命周期」进行流转')
}
function connectionTypeLabel(t) { return { ssh: 'SSH', agent: 'Agent', kubernetes: 'K8s API', snmp: 'SNMP', http: 'HTTP', database: '数据库' }[t] || t || '-' }

function tierClass(ci_type) {
  if (PERSISTENT_TYPES.has(ci_type)) return 'tier-persistent'
  if (WEAK_TYPES.has(ci_type)) return 'tier-weak'
  return 'tier-default'
}
function tierLabel(ci_type) {
  if (ci_type === 'pod' || ci_type === 'replicaset') return '实时视图'
  if (PERSISTENT_TYPES.has(ci_type)) return '持久化'
  if (WEAK_TYPES.has(ci_type)) return '弱纳管'
  return '标准'
}
function ciTypeStyle(ci_type) {
  const c = CI_TYPE_COLOR[ci_type]
  return c ? { background: c + '1a', color: c } : {}
}
function shortName(full) { return full.includes('/') ? full.split('/').pop() : full }
function isOrphan(a) { return a.isOrphan === true }
function showTags(a) {
  ElMessageBox.alert(a.tags, `${shortName(a.name)} 的标签`, { confirmButtonText: '关闭', customClass: 'tags-modal' })
}

const hideDeprecated = ref(false)
const onlyOrphan = ref(false)

const filteredAssets = computed(() => {
  let list = assets.value
  if (hideDeprecated.value) list = list.filter(a => a.status !== 'deprecated')
  if (onlyOrphan.value) list = list.filter(a => a.isOrphan === true)
  return list
})

function applyFilter() { /* computed 自动响应，无需操作 */ }

const currentPage = ref(1)
const pageSize = ref(20)
const pageSizeOptions = [10, 20, 50, 100]
const totalPages = computed(() => Math.max(1, Math.ceil(filteredAssets.value.length / pageSize.value)))
const pagedAssets = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredAssets.value.slice(start, start + pageSize.value)
})
const pageNumbers = computed(() => {
  const tp = totalPages.value
  const cp = currentPage.value
  const arr = []
  if (tp <= 7) { for (let i = 1; i <= tp; i++) arr.push(i) }
  else {
    arr.push(1)
    if (cp > 4) arr.push('...')
    for (let i = Math.max(2, cp - 1); i <= Math.min(tp - 1, cp + 1); i++) arr.push(i)
    if (cp < tp - 3) arr.push('...')
    arr.push(tp)
  }
  return arr
})
function goPage(p) {
  if (p === '...' || p < 1 || p > totalPages.value) return
  currentPage.value = p
}
function jumpPage(e) {
  const n = parseInt(e.target.value)
  if (!isNaN(n) && n >= 1 && n <= totalPages.value) currentPage.value = n
  e.target.value = ''
}
watch([search, ciType, hideDeprecated, onlyOrphan, pageSize], () => { currentPage.value = 1 })
watch(() => filteredAssets.value.length, () => { if (currentPage.value > totalPages.value) currentPage.value = totalPages.value })

const k8sStats = computed(() => {
  const k8sAssets = assets.value.filter(a => a.k8s_cluster || PERSISTENT_TYPES.has(a.ci_type) || WEAK_TYPES.has(a.ci_type))
  let persistent = 0, weak = 0, realtime = 0, orphan = 0
  k8sAssets.forEach(a => {
    if (a.status === 'deprecated') { realtime++; return }
    if (PERSISTENT_TYPES.has(a.ci_type)) persistent++
    else if (WEAK_TYPES.has(a.ci_type)) weak++
    if (a.isOrphan) orphan++
  })
  return { total: k8sAssets.length, persistent, weak, realtime, orphan }
})

function onCiTypeChange() {
  connTestResult.value = null
  const meta = ciTypeMetaMap[form.value.ci_type] || {}
  specValues.value = {}
  if (meta.specFields) meta.specFields.forEach(f => { specValues.value[f.key] = '' })
  if (isSshType.value) form.value.connection_type = 'ssh'
  else if (isSnmpType.value) form.value.connection_type = 'snmp'
  else if (form.value.ci_type === 'kubernetes_cluster') { form.value.connection_type = 'kubernetes'; form.value.ip = '' }
  else if (form.value.ci_type === 'database') form.value.connection_type = 'database'
  else if (['business_app', 'api_service'].includes(form.value.ci_type)) form.value.connection_type = 'http'
  else form.value.connection_type = 'ssh'
}

function openCreate() { formMode.value = 'create'; form.value = { ...defaultForm }; specValues.value = {}; connTestResult.value = null; showForm.value = true }

async function openEdit(id) {
  try {
    const detail = await request.get(`/assets/api/${id}/detail`)
    formMode.value = 'edit'; form.value = { ...defaultForm, ...detail }; specValues.value = {}; connTestResult.value = null
    const meta = ciTypeMetaMap[detail.ci_type] || {}
    if (meta.specFields) {
      const attrs = (typeof detail.ci_attributes === 'object' ? detail.ci_attributes : {}) || {}
      meta.specFields.forEach(f => { specValues.value[f.key] = attrs[f.key] || '' })
    }
    showForm.value = true
  } catch (e) { ElMessage.error('加载详情失败: ' + (e.message || e)) }
}

function closeForm() { showForm.value = false; connTestResult.value = null }

function getTestHost() {
  const ct = form.value.ci_type
  if (ct === 'kubernetes_cluster') return form.value.k8s_api_server || ''
  if (['business_app', 'api_service'].includes(ct)) return form.value.app_url || ''
  if (ct === 'monitoring_endpoint') return form.value.monitor_url || ''
  return form.value.ip || ''
}

async function testConnection() {
  if (!form.value.ci_type) { ElMessage.warning('请先选择 CI 类型'); return }
  const host = getTestHost()
  if (!host) { ElMessage.warning('请先填写 IP/地址'); return }
  testingConn.value = true; connTestResult.value = null
  try {
    let cfg = {}
    if (form.value.ci_type === 'kubernetes_cluster') {
      cfg = { api_server: form.value.k8s_api_server, token: form.value.k8s_token }
    } else if (isSshType.value) {
      cfg = { ssh_user: form.value.ssh_user, ssh_password: form.value.ssh_password, ssh_port: form.value.ssh_port }
    }
    const p = new URLSearchParams()
    p.append('connection_type', form.value.connection_type || 'ssh')
    p.append('host', host)
    p.append('connection_config', JSON.stringify(cfg))
    const data = await request.post('/assets/api/test-connection', p, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
    connTestResult.value = data
  } catch (e) {
    connTestResult.value = { ok: false, message: e.message || e }
  } finally { testingConn.value = false }
}

async function syncK8s(asset) {
  syncingId.value = asset.id
  try {
    const data = await request.post(`/assets/api/${asset.id}/sync-k8s`)
    if (data.ok) {
      const s = data.synced || {}
      const parts = []
      if (s.namespaces) parts.push(`NS ${s.namespaces}`)
      if (s.nodes) parts.push(`Node ${s.nodes}`)
      if (s.deployments) parts.push(`Deploy ${s.deployments}`)
      if (s.statefulsets) parts.push(`STS ${s.statefulsets}`)
      if (s.daemonsets) parts.push(`DS ${s.daemonsets}`)
      if (s.services) parts.push(`Svc ${s.services}`)
      if (s.ingresses) parts.push(`Ing ${s.ingresses}`)
      if (s.pvcs) parts.push(`PVC ${s.pvcs}`)
      if (s.pvs) parts.push(`PV ${s.pvs}`)
      if (s.configmaps) parts.push(`CM ${s.configmaps}`)
      if (s.secrets) parts.push(`Secret ${s.secrets}`)
      const summary = parts.join(' · ')
      const extra = []
      if (s.pods_skipped) extra.push(`Pod 跳过 ${s.pods_skipped}（不入库）`)
      if (s.orphans) extra.push(`孤岛 ${s.orphans}`)
      ElMessage.success(`同步完成 [${data.model || 'tiered'}]: ${summary}${extra.length ? ' | ' + extra.join('，') : ''}`)
    } else {
      ElMessage.error('同步失败: ' + (data.message || '未知错误'))
    }
    loadAssets()
  } catch (e) {
    ElMessage.error('同步失败: ' + (e.message || e))
  } finally { syncingId.value = null }
}

function buildPayload() {
  const p = { name: form.value.name, ci_type: form.value.ci_type, ip: form.value.ip, status: form.value.status, tags: form.value.tags, connection_type: form.value.connection_type }
  const meta = ciTypeMetaMap[form.value.ci_type] || {}
  if (meta.specFields && Object.keys(specValues.value).some(k => specValues.value[k])) {
    const attrs = {}; meta.specFields.forEach(f => { if (specValues.value[f.key]) attrs[f.key] = specValues.value[f.key] })
    if (Object.keys(attrs).length) p.ci_attributes = attrs
  }
  if (form.value.ci_type === 'kubernetes_cluster') {
    const cfg = {}
    if (form.value.k8s_api_server) cfg.k8s_api_server = form.value.k8s_api_server
    if (form.value.k8s_token) cfg.k8s_token = form.value.k8s_token
    if (Object.keys(cfg).length) p.connection_config = cfg
    p.ip = form.value.k8s_api_server || ''
  } else if (form.value.ci_type === 'database') {
    p.db_subtype = form.value.db_subtype; p.db_port = form.value.db_port; p.db_user = form.value.db_user; p.db_password = form.value.db_password; p.db_name = form.value.db_name
  } else if (form.value.ci_type === 'middleware') {
    p.mw_subtype = form.value.mw_subtype; p.mw_port = form.value.mw_port; p.mw_admin_url = form.value.mw_admin_url
  } else if (['business_app', 'api_service'].includes(form.value.ci_type)) {
    p.app_url = form.value.app_url; p.app_auth = form.value.app_auth; p.app_credential = form.value.app_credential; p.ip = form.value.app_url || ''
  } else if (form.value.ci_type === 'ssl_certificate') {
    p.cert_domain = form.value.cert_domain; p.cert_issuer = form.value.cert_issuer; p.cert_expiry = form.value.cert_expiry
  } else if (form.value.ci_type === 'dns_record') {
    p.dns_domain = form.value.dns_domain; p.dns_type = form.value.dns_type; p.dns_value = form.value.dns_value
  } else if (form.value.ci_type === 'monitoring_endpoint') {
    p.monitor_url = form.value.monitor_url; p.monitor_type = form.value.monitor_type; p.monitor_interval = form.value.monitor_interval; p.ip = form.value.monitor_url || ''
  } else if (form.value.ci_type === 'storage_device') {
    p.storage_type = form.value.storage_type; p.storage_mount = form.value.storage_mount; p.storage_capacity = form.value.storage_capacity
  }
  if (isSshType.value) {
    p.ssh_user = form.value.ssh_user; p.ssh_password = form.value.ssh_password; p.ssh_port = form.value.ssh_port
  }
  if (form.value.id) p.id = form.value.id
  return p
}

async function saveAsset() {
  if (!form.value.name.trim()) { ElMessage.warning('资产名称不能为空'); return }
  if (!form.value.ci_type) { ElMessage.warning('请选择 CI 类型'); return }
  saving.value = true
  try {
    const payload = buildPayload()
    if (formMode.value === 'create') { await request.post('/assets/api/create', payload); ElMessage.success('创建成功') }
    else { await request.post(`/assets/api/${form.value.id}/update`, payload); ElMessage.success('保存成功') }
    showForm.value = false; loadAssets()
  } catch (e) { ElMessage.error('保存失败: ' + (e.message || e)) }
  finally { saving.value = false }
}

async function loadAssets() {
  loading.value = true
  try {
    const data = await request.get('/assets/api/list', { params: { search: search.value, ci_type: ciType.value } })
    assets.value = (data || []).map(a => ({
      ...a,
      refCount: a.ref_count !== null && a.ref_count !== undefined ? a.ref_count : null,
      isOrphan: !!a.is_orphan,
      lifecycle_status: a.lifecycle_status || 'provisioning',
    }))
  }
  catch (e) { ElMessage.error('加载失败: ' + e.message) }
  finally { loading.value = false }
}

function onSearch() { if (searchTimer) clearTimeout(searchTimer); searchTimer = setTimeout(loadAssets, 300) }

async function deleteAsset(id, name) {
  try { await ElMessageBox.confirm(`确认删除「${name}」？`, '删除确认', { type: 'warning' }); await request.post(`/assets/api/${id}/delete`); ElMessage.success('已删除'); loadAssets() }
  catch (e) { if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e)) }
}

onMounted(() => { loadAssets() })
</script>

<style scoped>
.assets-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.search-input { padding: 6px 12px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; width: 240px; }
.toolbar select { padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; min-width: 140px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; text-decoration: none; display: inline-block; transition: all 0.2s; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-conn-test { background: transparent; color: var(--accent, #6366f1); border-color: var(--accent, #6366f1); font-size: 0.78rem; }
.btn-conn-test:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-sync { background: rgba(16,185,129,0.1); color: #10b981; border-color: rgba(16,185,129,0.3); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; white-space: nowrap; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); white-space: nowrap; }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.asset-name { font-weight: 500; }
.col-id { width: 52px; font-variant-numeric: tabular-nums; }
.col-id.text-sm, td.col-id { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: var(--text-tertiary, #94a3b8); font-size: 0.74rem; }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.ci-type { background: rgba(59,130,246,0.1); color: #3b82f6; }
.badge.online { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.offline { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.degraded { background: rgba(245,158,11,0.1); color: #d97706; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 540px; max-width: 90vw; max-height: 90vh; overflow-y: auto; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-box.wide { min-width: 540px; }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; }
.form-section { margin-bottom: 20px; }
.section-title { font-size: 0.82rem; font-weight: 700; color: var(--text, #1e293b); padding-bottom: 6px; margin-bottom: 10px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.form-row { margin-bottom: 0; }
.form-row.full { grid-column: 1 / -1; }
.form-row label { display: block; font-size: 0.76rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 5px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.input.textarea { resize: vertical; font-family: inherit; }
.conn-tip { font-size: 0.76rem; color: var(--text-tertiary, #94a3b8); margin-bottom: 10px; line-height: 1.5; padding: 8px 10px; background: rgba(99,102,241,0.06); border-radius: 4px; border-left: 2px solid var(--accent, #6366f1); }
.conn-note { font-size: 0.76rem; color: var(--text-tertiary, #94a3b8); padding: 6px 10px; background: rgba(0,0,0,0.02); border-radius: 4px; }
.modal-actions { display: flex; gap: 8px; margin-top: 18px; align-items: center; }
.conn-test-msg { font-size: 0.78rem; }
.conn-test-msg.suc { color: #10b981; }
.conn-test-msg.fail { color: #ef4444; }
.toolbar-hint { font-size: 0.72rem; color: var(--text-tertiary, #94a3b8); }
.filter-chk { font-size: 0.78rem; color: var(--text-secondary, #64748b); display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
.filter-chk input { cursor: pointer; }

.tier-bar { display: flex; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; padding: 10px 14px; background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; }
.tier-item { display: flex; align-items: center; gap: 6px; font-size: 0.74rem; padding: 4px 10px; border-radius: 5px; background: rgba(99,102,241,0.04); }
.tier-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.tier-name { font-weight: 600; color: var(--text, #1e293b); }
.tier-num { font-weight: 700; color: var(--accent, #6366f1); min-width: 18px; }
.tier-sub { color: var(--text-tertiary, #94a3b8); font-size: 0.66rem; }
.tier-warn { background: rgba(239,68,68,0.08); }
.tier-warn-icon { color: #ef4444; font-size: 0.85rem; }
.tier-warn .tier-num { color: #ef4444; }

.tier-badge { display: inline-block; padding: 1px 7px; border-radius: 4px; font-size: 0.62rem; font-weight: 600; }
.tier-badge.tier-persistent { background: rgba(16,185,129,0.1); color: #10b981; }
.tier-badge.tier-weak { background: rgba(6,182,212,0.1); color: #06b6d4; }
.tier-badge.tier-default { background: rgba(100,116,139,0.1); color: #64748b; }

.asset-fullname { font-size: 0.62rem; color: var(--text-tertiary, #94a3b8); margin-top: 1px; }
.ref-info { font-size: 0.72rem; color: #06b6d4; font-weight: 500; }
.ref-info.orphan { color: #ef4444; font-weight: 600; }
.text-muted { color: var(--text-tertiary, #94a3b8); }
.badge.deprecated { background: rgba(100,116,139,0.15); color: #64748b; text-decoration: line-through; }
tr.row-deprecated td { opacity: 0.55; }
tr.row-deprecated .asset-name { text-decoration: line-through; }
tr.row-orphan td { background: rgba(239,68,68,0.03); }

.pagination { display: flex; align-items: center; justify-content: space-between; margin-top: 14px; padding: 10px 16px; background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 8px; flex-wrap: wrap; gap: 8px; }
.pg-info { font-size: 0.8rem; color: var(--text-secondary, #64748b); }
.pg-info b { color: var(--accent, #6366f1); }
.pg-pages { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.pg-btn { min-width: 30px; height: 28px; padding: 0 8px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 5px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.76rem; cursor: pointer; transition: all 0.15s; }
.pg-btn:hover:not(:disabled):not(.active) { background: var(--bg-hover, rgba(0,0,0,0.03)); border-color: var(--accent, #6366f1); }
.pg-btn.active { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.pg-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.pg-ellipsis { color: var(--text-tertiary, #94a3b8); padding: 0 4px; font-size: 0.8rem; }
.pg-size { display: flex; align-items: center; gap: 10px; font-size: 0.76rem; color: var(--text-secondary, #64748b); }
.pg-select { padding: 4px 8px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 5px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.76rem; cursor: pointer; }
.pg-jump { display: flex; align-items: center; gap: 4px; }
.pg-input { width: 42px; height: 24px; padding: 0 4px; text-align: center; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 4px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.76rem; }
.btn-lifecycle { background: rgba(99,102,241,0.08); color: #6366f1; border-color: rgba(99,102,241,0.25); }
.btn-lifecycle:hover { background: rgba(99,102,241,0.15); }
.btn-tag { background: rgba(245,158,11,0.08); color: #d97706; border-color: rgba(245,158,11,0.25); }
.btn-tag:hover { background: rgba(245,158,11,0.15); }
.lc-badge { font-size: 0.68rem; padding: 2px 7px; }
.lc-badge.lc-provisioning { background: rgba(148,163,184,0.15); color: #475569; }
.lc-badge.lc-active { background: rgba(34,197,94,0.15); color: #16a34a; }
.lc-badge.lc-maintenance { background: rgba(245,158,11,0.15); color: #d97706; }
.lc-badge.lc-retired { background: rgba(107,114,128,0.15); color: #4b5563; }
</style>
