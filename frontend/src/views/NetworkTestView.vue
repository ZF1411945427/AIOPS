<template>
  <div class="network-test">
    <!-- 合规警示 -->
    <el-alert type="warning" :closable="false" show-icon class="compliance-alert">
      <template #title>
        <span class="compliance-title">合规注意事项</span>
      </template>
      <div class="compliance-body">
        <div>1. 本工具仅用于<b>自有资产</b>的网络连通性巡检与故障诊断</div>
        <div>2. 未经授权对他人服务器进行探测涉嫌违反《网络安全法》第二十七条</div>
        <div>3. TCP 端口测试仅支持单端口检测，不提供批量端口扫描</div>
        <div>4. 所有操作已记录审计日志，限制请求频率（1 秒/次/目标）</div>
      </div>
    </el-alert>

    <!-- 资产快选 -->
    <div class="asset-quick-pick">
      <span class="quick-label">资产快选：</span>
      <el-select
        v-model="quickAssetId"
        placeholder="从资产列表选择目标 IP"
        filterable
        clearable
        size="small"
        style="width: 280px"
        @change="onQuickPick"
      >
        <el-option
          v-for="a in assets"
          :key="a.id"
          :label="`${a.name} (${a.ip})`"
          :value="a.id"
        />
      </el-select>
    </div>

    <!-- Tab 切换 -->
    <el-tabs v-model="activeTab" class="nt-tabs" type="border-card">
      <!-- Ping -->
      <el-tab-pane name="ping">
        <template #label>
          <el-icon><Connection /></el-icon>
          <span class="tab-text">Ping 连通性</span>
        </template>
        <div class="tool-form">
          <el-form :inline="true" :model="pingForm" @submit.prevent="runPing">
            <el-form-item label="目标">
              <el-input v-model="pingForm.target" placeholder="IP 或域名，如 8.8.8.8 / baidu.com" style="width: 260px" clearable @keyup.enter="runPing" />
            </el-form-item>
            <el-form-item label="次数">
              <el-input-number v-model="pingForm.count" :min="1" :max="10" style="width: 100px" />
            </el-form-item>
            <el-form-item label="超时(秒)">
              <el-input-number v-model="pingForm.timeout" :min="1" :max="30" style="width: 100px" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="loading === 'ping'" @click="runPing" :disabled="!pingForm.target">
                <el-icon><VideoPlay /></el-icon> 执行 Ping
              </el-button>
            </el-form-item>
          </el-form>
        </div>
        <div class="result-panel" :class="{ loading: loading === 'ping', empty: !loading && !pingResult }">
          <div v-if="loading === 'ping'" class="loading-text">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span style="margin-left:8px">正在执行，请稍候...</span>
          </div>
          <div v-else-if="!pingResult" class="empty-text">暂无结果，填写目标后点击执行按钮</div>
          <template v-else>
            <div class="result-header">
              <span class="result-status" :class="pingResult.success ? 'success' : 'fail'">
                {{ pingResult.success ? '✅ 成功' : '❌ 失败' }}
              </span>
              <span v-if="pingResult.returncode != null && pingResult.returncode !== 0" class="result-code">退出码 {{ pingResult.returncode }}</span>
            </div>
            <pre class="result-output">{{ pingResult.output || '(无输出)' }}</pre>
          </template>
        </div>
      </el-tab-pane>

      <!-- Traceroute -->
      <el-tab-pane name="traceroute">
        <template #label>
          <el-icon><Share /></el-icon>
          <span class="tab-text">Traceroute 路由追踪</span>
        </template>
        <div class="tool-form">
          <el-form :inline="true" :model="traceForm" @submit.prevent="runTrace">
            <el-form-item label="目标">
              <el-input v-model="traceForm.target" placeholder="IP 或域名" style="width: 260px" clearable @keyup.enter="runTrace" />
            </el-form-item>
            <el-form-item label="最大跳数">
              <el-input-number v-model="traceForm.max_hops" :min="1" :max="50" style="width: 110px" />
            </el-form-item>
            <el-form-item label="超时(秒)">
              <el-input-number v-model="traceForm.timeout" :min="1" :max="30" style="width: 100px" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="loading === 'traceroute'" @click="runTrace" :disabled="!traceForm.target">
                <el-icon><VideoPlay /></el-icon> 执行追踪
              </el-button>
            </el-form-item>
          </el-form>
        </div>
        <div class="result-panel" :class="{ loading: loading === 'traceroute', empty: !loading && !traceResult }">
          <div v-if="loading === 'traceroute'" class="loading-text">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span style="margin-left:8px">正在执行，Traceroute 可能需要较长时间...</span>
          </div>
          <div v-else-if="!traceResult" class="empty-text">暂无结果，填写目标后点击执行按钮</div>
          <template v-else>
            <div class="result-header">
              <span class="result-status" :class="traceResult.success ? 'success' : 'fail'">
                {{ traceResult.success ? '✅ 成功' : '❌ 失败' }}
              </span>
              <span v-if="traceResult.returncode != null && traceResult.returncode !== 0" class="result-code">退出码 {{ traceResult.returncode }}</span>
            </div>
            <pre class="result-output">{{ traceResult.output || '(无输出)' }}</pre>
          </template>
        </div>
      </el-tab-pane>

      <!-- TCP 端口 -->
      <el-tab-pane name="tcp-port">
        <template #label>
          <el-icon><Monitor /></el-icon>
          <span class="tab-text">TCP 端口连通性</span>
        </template>
        <div class="tool-form">
          <el-form :inline="true" :model="tcpForm" @submit.prevent="runTcp">
            <el-form-item label="目标">
              <el-input v-model="tcpForm.target" placeholder="IP 或域名" style="width: 260px" clearable @keyup.enter="runTcp" />
            </el-form-item>
            <el-form-item label="端口">
              <el-input-number v-model="tcpForm.port" :min="1" :max="65535" style="width: 120px" controls-position="right" />
            </el-form-item>
            <el-form-item label="超时(秒)">
              <el-input-number v-model="tcpForm.timeout" :min="1" :max="10" style="width: 100px" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="loading === 'tcp-port'" @click="runTcp" :disabled="!tcpForm.target">
                <el-icon><VideoPlay /></el-icon> 检测端口
              </el-button>
            </el-form-item>
          </el-form>
          <div class="quick-ports">
            <span class="quick-ports-label">常用端口：</span>
            <el-tag
              v-for="p in commonPorts"
              :key="p.port"
              class="port-tag"
              :type="tcpForm.port === p.port ? 'primary' : 'info'"
              effect="plain"
              @click="tcpForm.port = p.port"
            >
              {{ p.port }} {{ p.label }}
            </el-tag>
          </div>
        </div>
        <div class="result-panel" :class="{ loading: loading === 'tcp-port', empty: !loading && !tcpResult }">
          <div v-if="loading === 'tcp-port'" class="loading-text">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span style="margin-left:8px">正在检测端口连通性...</span>
          </div>
          <div v-else-if="!tcpResult" class="empty-text">暂无结果，填写目标和端口后点击检测按钮</div>
          <template v-else>
            <div class="result-header">
              <span class="result-status" :class="tcpResult.success ? 'success' : 'fail'">
                {{ tcpResult.success ? '✅ 端口开放' : '❌ 端口不可达' }}
              </span>
              <span v-if="tcpResult.elapsed_ms != null" class="result-elapsed">耗时 {{ tcpResult.elapsed_ms }}ms</span>
            </div>
            <pre class="result-output">{{ tcpResult.output || '(无输出)' }}</pre>
          </template>
        </div>
      </el-tab-pane>

      <!-- DNS -->
      <el-tab-pane name="dns">
        <template #label>
          <el-icon><Search /></el-icon>
          <span class="tab-text">DNS 解析查询</span>
        </template>
        <div class="tool-form">
          <el-form :inline="true" :model="dnsForm" @submit.prevent="runDns">
            <el-form-item label="域名">
              <el-input v-model="dnsForm.target" placeholder="如 baidu.com" style="width: 240px" clearable @keyup.enter="runDns" />
            </el-form-item>
            <el-form-item label="记录类型">
              <el-select v-model="dnsForm.record_type" style="width: 110px">
                <el-option v-for="t in dnsTypes" :key="t" :label="t" :value="t" />
              </el-select>
            </el-form-item>
            <el-form-item label="DNS 服务器">
              <el-input v-model="dnsForm.dns_server" placeholder="可选，如 8.8.8.8" style="width: 160px" clearable />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="loading === 'dns'" @click="runDns" :disabled="!dnsForm.target">
                <el-icon><VideoPlay /></el-icon> 查询解析
              </el-button>
            </el-form-item>
          </el-form>
        </div>
        <div class="result-panel" :class="{ loading: loading === 'dns', empty: !loading && !dnsResult }">
          <div v-if="loading === 'dns'" class="loading-text">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span style="margin-left:8px">正在查询 DNS 记录...</span>
          </div>
          <div v-else-if="!dnsResult" class="empty-text">暂无结果，填写域名后点击查询按钮</div>
          <template v-else>
            <div class="result-header">
              <span class="result-status" :class="dnsResult.success ? 'success' : 'fail'">
                {{ dnsResult.success ? '✅ 查询成功' : '❌ 查询失败' }}
              </span>
              <span v-if="dnsResult.returncode != null && dnsResult.returncode !== 0" class="result-code">退出码 {{ dnsResult.returncode }}</span>
            </div>
            <pre class="result-output">{{ dnsResult.output || '(无输出)' }}</pre>
          </template>
        </div>
      </el-tab-pane>

      <!-- HTTP/HTTPS 探测 -->
      <el-tab-pane name="http">
        <template #label>
          <el-icon><Link /></el-icon>
          <span class="tab-text">HTTP/HTTPS 探测</span>
        </template>
        <div class="tool-form">
          <el-form :inline="true" :model="httpForm" @submit.prevent="runHttp">
            <el-form-item label="URL">
              <el-input v-model="httpForm.url" placeholder="https://example.com" style="width: 320px" clearable @keyup.enter="runHttp" />
            </el-form-item>
            <el-form-item label="方法">
              <el-select v-model="httpForm.method" style="width: 90px">
                <el-option label="GET" value="GET" />
                <el-option label="HEAD" value="HEAD" />
              </el-select>
            </el-form-item>
            <el-form-item label="超时(秒)">
              <el-input-number v-model="httpForm.timeout" :min="1" :max="30" style="width: 100px" />
            </el-form-item>
            <el-form-item label="跟随重定向">
              <el-switch v-model="httpForm.follow_redirects" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="loading === 'http'" @click="runHttp" :disabled="!httpForm.url">
                <el-icon><VideoPlay /></el-icon> 发起探测
              </el-button>
            </el-form-item>
          </el-form>
        </div>
        <div class="result-panel" :class="{ loading: loading === 'http', empty: !loading && !httpResult }">
          <div v-if="loading === 'http'" class="loading-text">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span style="margin-left:8px">正在发起 HTTP 探测...</span>
          </div>
          <div v-else-if="!httpResult" class="empty-text">暂无结果，填写 URL 后点击探测按钮</div>
          <template v-else>
            <div class="result-header">
              <span class="result-status" :class="httpResult.success ? 'success' : 'fail'">
                {{ httpResult.success ? '✅ 探测成功' : '❌ 探测失败' }}
              </span>
              <span v-if="httpResult.status_code" class="result-code">状态码 {{ httpResult.status_code }} {{ httpResult.reason }}</span>
              <span v-if="httpResult.elapsed_ms != null" class="result-elapsed">耗时 {{ httpResult.elapsed_ms }}ms</span>
            </div>
            <div v-if="httpResult.content_type || httpResult.server" class="result-meta-bar">
              <el-tag v-if="httpResult.content_type" size="small" type="info">{{ httpResult.content_type }}</el-tag>
              <el-tag v-if="httpResult.server" size="small">Server: {{ httpResult.server }}</el-tag>
              <el-tag v-if="httpResult.final_url" size="small" type="success">最终 URL: {{ httpResult.final_url }}</el-tag>
            </div>
            <div class="result-sub-title">响应头</div>
            <pre class="result-output">{{ httpResult.headers || '(无)' }}</pre>
            <div v-if="httpForm.method === 'GET' && httpResult.body_preview" class="result-sub-title">响应体预览 (前 2000 字符)</div>
            <pre v-if="httpForm.method === 'GET' && httpResult.body_preview" class="result-output">{{ httpResult.body_preview }}</pre>
            <div v-if="httpResult.output" class="result-sub-title">错误信息</div>
            <pre v-if="httpResult.output" class="result-output">{{ httpResult.output }}</pre>
          </template>
        </div>
      </el-tab-pane>

      <!-- TLS 证书查询 -->
      <el-tab-pane name="tls-cert">
        <template #label>
          <el-icon><Lock /></el-icon>
          <span class="tab-text">TLS 证书查询</span>
        </template>
        <div class="tool-form">
          <el-form :inline="true" :model="tlsForm" @submit.prevent="runTls">
            <el-form-item label="域名">
              <el-input v-model="tlsForm.target" placeholder="如 baidu.com" style="width: 240px" clearable @keyup.enter="runTls" />
            </el-form-item>
            <el-form-item label="端口">
              <el-input-number v-model="tlsForm.port" :min="1" :max="65535" style="width: 120px" controls-position="right" />
            </el-form-item>
            <el-form-item label="超时(秒)">
              <el-input-number v-model="tlsForm.timeout" :min="1" :max="30" style="width: 100px" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="loading === 'tls-cert'" @click="runTls" :disabled="!tlsForm.target">
                <el-icon><VideoPlay /></el-icon> 查询证书
              </el-button>
            </el-form-item>
          </el-form>
        </div>
        <div class="result-panel" :class="{ loading: loading === 'tls-cert', empty: !loading && !tlsResult }">
          <div v-if="loading === 'tls-cert'" class="loading-text">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span style="margin-left:8px">正在查询 TLS 证书...</span>
          </div>
          <div v-else-if="!tlsResult" class="empty-text">暂无结果，填写域名后点击查询按钮</div>
          <template v-else>
            <div class="result-header">
              <span class="result-status" :class="tlsResult.success ? 'success' : 'fail'">
                {{ tlsResult.success ? '✅ 查询成功' : '❌ 查询失败' }}
              </span>
              <span v-if="tlsResult.days_left != null" class="result-elapsed">
                剩余 {{ tlsResult.days_left }} 天
                <el-tag :type="tlsResult.days_left > 30 ? 'success' : tlsResult.days_left > 0 ? 'warning' : 'danger'" size="small" style="margin-left:4px">
                  {{ tlsResult.days_left > 30 ? '正常' : tlsResult.days_left > 0 ? '即将过期' : '已过期' }}
                </el-tag>
              </span>
            </div>
            <pre class="result-output">{{ tlsResult.output || '(无输出)' }}</pre>
          </template>
        </div>
      </el-tab-pane>

      <!-- IP 归属地查询 -->
      <el-tab-pane name="ip-location">
        <template #label>
          <el-icon><Location /></el-icon>
          <span class="tab-text">IP 归属地</span>
        </template>
        <div class="tool-form">
          <el-form :inline="true" :model="ipLocForm" @submit.prevent="runIpLoc">
            <el-form-item label="IP/域名">
              <el-input v-model="ipLocForm.target" placeholder="如 8.8.8.8 或 baidu.com" style="width: 280px" clearable @keyup.enter="runIpLoc" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="loading === 'ip-location'" @click="runIpLoc" :disabled="!ipLocForm.target">
                <el-icon><VideoPlay /></el-icon> 查询归属地
              </el-button>
            </el-form-item>
          </el-form>
        </div>
        <div class="result-panel" :class="{ loading: loading === 'ip-location', empty: !loading && !ipLocResult }">
          <div v-if="loading === 'ip-location'" class="loading-text">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span style="margin-left:8px">正在查询 IP 归属地...</span>
          </div>
          <div v-else-if="!ipLocResult" class="empty-text">暂无结果，填写 IP 或域名后点击查询按钮</div>
          <template v-else>
            <div class="result-header">
              <span class="result-status" :class="ipLocResult.success ? 'success' : 'fail'">
                {{ ipLocResult.success ? '✅ 查询成功' : '❌ 查询失败' }}
              </span>
              <span v-if="ipLocResult.ip" class="result-code">IP: {{ ipLocResult.ip }}</span>
            </div>
            <div v-if="ipLocResult.success && ipLocResult.country" class="result-meta-bar">
              <el-tag size="small" type="info">{{ ipLocResult.country }}</el-tag>
              <el-tag v-if="ipLocResult.region" size="small">{{ ipLocResult.region }}</el-tag>
              <el-tag v-if="ipLocResult.city" size="small">{{ ipLocResult.city }}</el-tag>
              <el-tag v-if="ipLocResult.isp" size="small" type="warning">{{ ipLocResult.isp }}</el-tag>
            </div>
            <pre class="result-output">{{ ipLocResult.output || '(无输出)' }}</pre>
          </template>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Connection, Share, Monitor, Search, VideoPlay, Loading, Link, Lock, Location } from '@element-plus/icons-vue'
import request from '@/api/request'

const API = '/api/network-test'
const activeTab = ref('ping')
const loading = ref(null)
const assets = ref([])
const quickAssetId = ref(null)

const pingForm = reactive({ target: '', count: 4, timeout: 5 })
const traceForm = reactive({ target: '', max_hops: 20, timeout: 5 })
const tcpForm = reactive({ target: '', port: 80, timeout: 3 })
const dnsForm = reactive({ target: '', record_type: 'A', dns_server: '' })
const httpForm = reactive({ url: 'https://', method: 'GET', timeout: 10, follow_redirects: true })
const tlsForm = reactive({ target: '', port: 443, timeout: 10 })
const ipLocForm = reactive({ target: '' })

const pingResult = ref(null)
const traceResult = ref(null)
const tcpResult = ref(null)
const dnsResult = ref(null)
const httpResult = ref(null)
const tlsResult = ref(null)
const ipLocResult = ref(null)

const commonPorts = [
  { port: 22, label: 'SSH' },
  { port: 80, label: 'HTTP' },
  { port: 443, label: 'HTTPS' },
  { port: 3306, label: 'MySQL' },
  { port: 6379, label: 'Redis' },
  { port: 8080, label: 'HTTP-Alt' },
  { port: 9200, label: 'ES' },
]
const dnsTypes = ['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'SOA', 'PTR']

function onQuickPick(id) {
  const a = assets.value.find(x => x.id === id)
  if (!a) return
  pingForm.target = a.ip
  traceForm.target = a.ip
  tcpForm.target = a.ip
}

async function loadAssets() {
  try {
    const data = await request.get('/assets/api/assets?limit=200')
    assets.value = Array.isArray(data) ? data : (data.items || data.assets || [])
  } catch (e) {
    // 静默失败
  }
}

async function runPing() {
  loading.value = 'ping'
  pingResult.value = null
  try {
    pingResult.value = await request.post(`${API}/ping`, { ...pingForm })
  } catch (e) {
    pingResult.value = { success: false, output: e.message }
    ElMessage.error(e.message)
  } finally {
    loading.value = null
  }
}

async function runTrace() {
  loading.value = 'traceroute'
  traceResult.value = null
  try {
    traceResult.value = await request.post(`${API}/traceroute`, { ...traceForm })
  } catch (e) {
    traceResult.value = { success: false, output: e.message }
    ElMessage.error(e.message)
  } finally {
    loading.value = null
  }
}

async function runTcp() {
  loading.value = 'tcp-port'
  tcpResult.value = null
  try {
    tcpResult.value = await request.post(`${API}/tcp-port`, { ...tcpForm })
  } catch (e) {
    tcpResult.value = { success: false, output: e.message }
    ElMessage.error(e.message)
  } finally {
    loading.value = null
  }
}

async function runDns() {
  loading.value = 'dns'
  dnsResult.value = null
  try {
    const payload = { target: dnsForm.target, record_type: dnsForm.record_type }
    if (dnsForm.dns_server) payload.dns_server = dnsForm.dns_server
    dnsResult.value = await request.post(`${API}/dns`, payload)
  } catch (e) {
    dnsResult.value = { success: false, output: e.message }
    ElMessage.error(e.message)
  } finally {
    loading.value = null
  }
}

async function runHttp() {
  loading.value = 'http'
  httpResult.value = null
  try {
    httpResult.value = await request.post(`${API}/http`, { ...httpForm })
  } catch (e) {
    httpResult.value = { success: false, output: e.message }
    ElMessage.error(e.message)
  } finally {
    loading.value = null
  }
}

async function runTls() {
  loading.value = 'tls-cert'
  tlsResult.value = null
  try {
    tlsResult.value = await request.post(`${API}/tls-cert`, { ...tlsForm })
  } catch (e) {
    tlsResult.value = { success: false, output: e.message }
    ElMessage.error(e.message)
  } finally {
    loading.value = null
  }
}

async function runIpLoc() {
  loading.value = 'ip-location'
  ipLocResult.value = null
  try {
    ipLocResult.value = await request.post(`${API}/ip-location`, { ...ipLocForm })
  } catch (e) {
    ipLocResult.value = { success: false, output: e.message }
    ElMessage.error(e.message)
  } finally {
    loading.value = null
  }
}

onMounted(loadAssets)
</script>

<style scoped>
.network-test {
  padding: 20px;
}
.compliance-alert {
  margin-bottom: 16px;
}
.compliance-title {
  font-weight: 700;
  font-size: 14px;
}
.compliance-body {
  font-size: 13px;
  line-height: 1.8;
  color: #666;
}
.compliance-body b {
  color: #e6a23c;
}
.asset-quick-pick {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.quick-label {
  font-size: 13px;
  color: #909399;
}
.nt-tabs {
  min-height: 400px;
}
.tab-text {
  margin-left: 4px;
}
.tool-form {
  padding: 12px 0;
}
.quick-ports {
  margin-top: 8px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.quick-ports-label {
  font-size: 12px;
  color: #909399;
}
:deep(.port-tag) {
  cursor: pointer;
}
.result-panel {
  margin-top: 12px;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  background: #fafafa;
  min-height: 120px;
  overflow: hidden;
}
.result-panel.loading,
.result-panel.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #909399;
  font-size: 13px;
  padding: 40px;
}
.loading-text {
  display: flex;
  align-items: center;
}
.empty-text {
  color: #c0c4cc;
}
.result-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  background: #f5f7fa;
  border-bottom: 1px solid #e4e7ed;
  font-size: 13px;
}
.result-status.success {
  color: #67c23a;
  font-weight: 600;
}
.result-status.fail {
  color: #f56c6c;
  font-weight: 600;
}
.result-elapsed {
  color: #409eff;
}
.result-code {
  color: #909399;
}
.result-meta-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  border-bottom: 1px solid #eee;
  flex-wrap: wrap;
}
.result-sub-title {
  padding: 8px 16px 2px;
  font-size: 12px;
  color: #909399;
  font-weight: 600;
}
.result-output {
  padding: 16px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 500px;
  overflow-y: auto;
  margin: 0;
  color: #303133;
}
</style>
