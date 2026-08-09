<template>
  <div class="agent-manage-page">
    <el-tabs v-model="activeTab" class="agent-tabs">
      <el-tab-pane label="Agent 下发" name="deploy">
        <div class="section-header">
          <h3>可部署 Agent 的资产</h3>
          <el-tag type="info">SSH 凭证就绪</el-tag>
        </div>
        <el-table :data="deployableAssets" v-loading="loadingAssets" stripe style="width: 100%">
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="name" label="资产名称" min-width="160" />
          <el-table-column prop="ip" label="IP" width="140" />
          <el-table-column prop="ci_type" label="类型" width="100" />
          <el-table-column label="Agent 状态" width="130">
            <template #default="{ row }">
              <el-tag v-if="row.agent_online" type="success" size="small">在线</el-tag>
              <el-tag v-else-if="row.has_agent" type="warning" size="small">离线</el-tag>
              <el-tag v-else type="info" size="small">未部署</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180">
            <template #default="{ row }">
              <el-button
                v-if="!row.has_agent"
                type="primary" size="small" :loading="deployingId === row.id"
                @click="handleDeploy(row)"
              >下发 Agent</el-button>
              <el-button
                v-else-if="row.agent_online"
                type="success" size="small"
                @click="showExecDialog(row)"
              >执行命令</el-button>
              <el-tag v-else type="warning" size="small">离线</el-tag>
            </template>
          </el-table-column>
        </el-table>

        <el-dialog v-model="deployDialog" title="Agent 下发确认" width="500px">
          <el-form label-width="100px">
            <el-form-item label="目标资产">
              <el-tag>{{ deployTarget?.name }} ({{ deployTarget?.ip }})</el-tag>
            </el-form-item>
            <el-form-item label="云端地址" required>
              <el-input v-model="cloudUrl" placeholder="http://192.168.89.193:8000">
                <template #append>
                  <el-tooltip content="远端 agent 连接云端的地址，须为目标节点可达的 IP" placement="top">
                    <el-icon><WarningFilled /></el-icon>
                  </el-tooltip>
                </template>
              </el-input>
              <div class="form-tip">目标节点可通过此地址访问云端，默认使用本机局域网 IP</div>
            </el-form-item>
            <el-form-item label="操作">
              <span>通过 SSH 推送 edge agent 到目标节点，安装依赖并启动 systemd 服务</span>
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="deployDialog = false">取消</el-button>
            <el-button type="primary" :loading="deployingId !== null" @click="confirmDeploy">确认下发</el-button>
          </template>
        </el-dialog>

        <el-dialog v-model="deployProgressDialog" title="部署进度" width="600px" :close-on-click-modal="false">
          <div class="deploy-progress">
            <el-progress :percentage="deployProgress" :status="deployStatus" />
            <p class="deploy-message">{{ deployMessage }}</p>
            <pre v-if="deployError" class="deploy-error">{{ deployError }}</pre>
          </div>
          <template #footer>
            <el-button @click="deployProgressDialog = false">关闭</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>

      <el-tab-pane label="Agent 监控" name="monitor">
        <div class="section-header">
          <h3>已注册 Agent</h3>
          <el-tag type="success">在线: {{ onlineCount }}</el-tag>
          <el-tag type="info">总计: {{ agents.length }}</el-tag>
        </div>
        <el-table :data="agents" v-loading="loadingAgents" stripe style="width: 100%">
          <el-table-column prop="agent_id" label="Agent ID" width="140" />
          <el-table-column prop="hostname" label="主机名" min-width="140" />
          <el-table-column prop="asset_name" label="关联资产" min-width="140" />
          <el-table-column prop="os_type" label="OS" width="70" />
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.online" type="success" size="small">在线</el-tag>
              <el-tag v-else type="danger" size="small">离线</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="agent_version" label="版本" width="80" />
          <el-table-column label="心跳" width="160">
            <template #default="{ row }">{{ row.last_heartbeat_at ? formatTime(row.last_heartbeat_at) : '-' }}</template>
          </el-table-column>
          <el-table-column label="重连" width="60" prop="reconnect_count" />
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button v-if="row.online" size="small" @click="showMetrics(row)">指标</el-button>
              <el-button v-if="row.online" size="small" type="primary" @click="showExecDialogForAgent(row)">命令</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-dialog v-model="metricsDialog" title="Agent 实时指标" width="700px">
          <div v-if="metricsData && Object.keys(metricsData).length" class="metrics-grid">
            <div v-for="(val, key) in metricsData" :key="key" class="metric-card">
              <div class="metric-label">{{ key }}</div>
              <div class="metric-value">{{ val }}</div>
            </div>
          </div>
          <div v-else>
            <el-empty description="暂无指标数据（agent 每 60s 上报一次）" />
          </div>
        </el-dialog>
      </el-tab-pane>

      <el-tab-pane label="命令执行" name="command">
        <div class="section-header">
          <h3>远程命令执行</h3>
          <el-tag type="warning">隧道优先，SSH 回退</el-tag>
        </div>
        <el-form :model="execForm" label-width="100px" class="exec-form">
          <el-form-item label="目标资产">
            <el-select v-model="execForm.asset_id" filterable placeholder="选择资产" style="width: 300px">
              <el-option v-for="a in allAssets" :key="a.id" :label="`${a.name} (${a.ip})`" :value="a.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="执行命令">
            <el-input v-model="execForm.command" type="textarea" :rows="3" placeholder="输入要执行的命令" />
          </el-form-item>
          <el-form-item label="超时(秒)">
            <el-input-number v-model="execForm.timeout" :min="5" :max="300" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="execLoading" @click="handleExec">执行</el-button>
          </el-form-item>
        </el-form>
        <div v-if="execResult" class="exec-result">
          <h4>执行结果</h4>
          <div class="exec-meta">
            <el-tag :type="execResult.exit_code === 0 ? 'success' : 'danger'" size="small">
              exit: {{ execResult.exit_code }}
            </el-tag>
            <el-tag type="info" size="small">通道: {{ execResult.channel || 'ssh' }}</el-tag>
            <el-tag type="info" size="small">{{ execResult.duration_ms || 0 }}ms</el-tag>
          </div>
          <pre class="exec-output">{{ execResult.stdout || execResult.stderr || '(空)' }}</pre>
        </div>
      </el-tab-pane>

      <el-tab-pane label="执行日志" name="logs">
        <el-table :data="commandLogs" v-loading="loadingLogs" stripe style="width: 100%">
          <el-table-column prop="id" label="#" width="50" />
          <el-table-column prop="username" label="用户" width="80" />
          <el-table-column prop="command" label="命令" min-width="200" />
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.status === 'success'" type="success" size="small">成功</el-tag>
              <el-tag v-else-if="row.status === 'failed'" type="danger" size="small">失败</el-tag>
              <el-tag v-else-if="row.status === 'timeout'" type="warning" size="small">超时</el-tag>
              <el-tag v-else type="info" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="exit_code" label="Exit" width="60" />
          <el-table-column prop="duration_ms" label="耗时(ms)" width="90" />
          <el-table-column label="时间" width="160">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'
import request from '@/api/request'

const activeTab = ref('deploy')
const deployableAssets = ref([])
const allAssets = ref([])
const loadingAssets = ref(false)
const agents = ref([])
const loadingAgents = ref(false)
const onlineCount = ref(0)
const commandLogs = ref([])
const loadingLogs = ref(false)
const deployingId = ref(null)
const deployDialog = ref(false)
const deployTarget = ref(null)
const cloudUrl = ref('http://11.0.1.1:8000')
const deployProgressDialog = ref(false)
const deployJobId = ref('')
const deployProgress = ref(0)
const deployStatus = ref('')
const deployMessage = ref('')
const deployError = ref('')
const metricsDialog = ref(false)
const metricsData = ref(null)
const execForm = ref({ asset_id: '', command: '', timeout: 30 })
const execLoading = ref(false)
const execResult = ref(null)

function formatTime(ts) {
  if (!ts) return '-'
  return ts.replace('T', ' ').substring(0, 19)
}

async function loadDeployableAssets() {
  loadingAssets.value = true
  try {
    const res = await request.get('/agent/deployable-assets')
    deployableAssets.value = res.assets || []
  } catch (e) {
    console.error('Failed to load deployable assets:', e)
  } finally {
    loadingAssets.value = false
  }
}

async function loadAgents() {
  loadingAgents.value = true
  try {
    const res = await request.get('/agent/agents')
    agents.value = res.agents || []
    onlineCount.value = res.online_count || 0
  } catch (e) {
    console.error('Failed to load agents:', e)
  } finally {
    loadingAgents.value = false
  }
}

async function loadAllAssets() {
  try {
    const res = await request.get('/agent/deployable-assets')
    allAssets.value = res.assets || []
  } catch (e) {
    console.error('Failed to load assets:', e)
  }
}

async function loadCommandLogs() {
  loadingLogs.value = true
  try {
    const res = await request.get('/agent/commands', { params: { limit: 50 } })
    commandLogs.value = res.commands || []
  } catch (e) {
    console.error('Failed to load logs:', e)
  } finally {
    loadingLogs.value = false
  }
}

function handleDeploy(asset) {
  deployTarget.value = asset
  deployDialog.value = true
}

async function confirmDeploy() {
  if (!deployTarget.value) return
  deployDialog.value = false
  deployingId.value = deployTarget.value.id
  deployProgressDialog.value = true
  deployProgress.value = 0
  deployStatus.value = ''
  deployMessage.value = '部署任务已提交...'
  deployError.value = ''

  try {
    const res = await request.post('/agent/deploy', { asset_id: deployTarget.value.id, cloud_url: cloudUrl.value })
    deployJobId.value = res.job_id

    const poll = setInterval(async () => {
      try {
        const status = await request.get(`/agent/deploy/${deployJobId.value}`)
        deployProgress.value = status.progress || 0
        deployMessage.value = status.progress_message || ''
        if (status.error) deployError.value = status.error
        if (status.status === 'success') {
          deployStatus.value = 'success'
          deployMessage.value = status.result?.agent_id
            ? `✅ Agent 已注册！agent_id: ${status.result.agent_id}`
            : '✅ Agent 部署成功'
          clearInterval(poll)
          deployingId.value = null
          loadDeployableAssets()
          loadAgents()
        } else if (status.status === 'failed') {
          deployStatus.value = 'exception'
          deployError.value = status.error || '部署失败'
          clearInterval(poll)
          deployingId.value = null
        }
      } catch (e) {
        // retry
      }
    }, 2000)
  } catch (e) {
    deployError.value = e.message || '部署请求失败'
    deployStatus.value = 'exception'
    deployingId.value = null
  }
}

function showExecDialog(asset) {
  execForm.value = { asset_id: asset.id, command: '', timeout: 30 }
  activeTab.value = 'command'
}

function showExecDialogForAgent(agent) {
  execForm.value = { asset_id: agent.asset_id || '', command: '', timeout: 30 }
  activeTab.value = 'command'
}

async function handleExec() {
  if (!execForm.value.asset_id || !execForm.value.command) return
  execLoading.value = true
  execResult.value = null
  try {
    const res = await request.post('/agent/exec', execForm.value)
    execResult.value = res
  } catch (e) {
    execResult.value = { exit_code: -1, stderr: e.message || '执行失败' }
  } finally {
    execLoading.value = false
    loadCommandLogs()
  }
}

async function showMetrics(agent) {
  metricsData.value = null
  metricsDialog.value = true
  try {
    const res = await request.get(`/edge/metrics/${agent.agent_id}`)
    metricsData.value = res.metrics || {}
  } catch (e) {
    metricsData.value = { error: '获取指标失败' }
  }
}

onMounted(() => {
  loadDeployableAssets()
  loadAgents()
  loadAllAssets()
  loadCommandLogs()
})
</script>

<style scoped>
.agent-manage-page {
  padding: 20px;
}
.agent-tabs {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
}
.section-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.section-header h3 {
  margin: 0;
  font-size: 16px;
}
.deploy-progress {
  text-align: center;
  padding: 20px;
}
.deploy-message {
  margin-top: 12px;
  color: #666;
}
.deploy-error {
  margin-top: 12px;
  padding: 12px;
  background: #fef0f0;
  border-radius: 4px;
  color: #f56c6c;
  font-size: 13px;
  white-space: pre-wrap;
  text-align: left;
}
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}
.metric-card {
  padding: 16px;
  background: #f5f7fa;
  border-radius: 6px;
  text-align: center;
}
.metric-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}
.metric-value {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}
.exec-form {
  max-width: 700px;
  margin-bottom: 20px;
}
.exec-result {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 16px;
  max-width: 700px;
}
.exec-result h4 {
  margin: 0 0 8px;
}
.exec-meta {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}
.exec-output {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: 4px;
  font-size: 13px;
  max-height: 300px;
  overflow: auto;
  white-space: pre-wrap;
}
.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>