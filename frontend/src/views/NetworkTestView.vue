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
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Connection, Share, Monitor, Search, VideoPlay, Loading } from '@element-plus/icons-vue'
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

const pingResult = ref(null)
const traceResult = ref(null)
const tcpResult = ref(null)
const dnsResult = ref(null)

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
