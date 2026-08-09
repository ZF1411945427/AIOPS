<template>
  <div class="sandbox-page">
    <el-tabs v-model="activeTab" class="sandbox-tabs">
      <el-tab-pane label="全局配置" name="config">
        <el-card shadow="never">
          <el-form :model="config" label-width="180px" size="small">
            <el-form-item label="沙盒总开关">
              <el-switch v-model="config.is_enabled" @change="saveConfig" />
              <span class="form-hint">关闭时沙盒不生效，不影响现有功能</span>
            </el-form-item>
            <el-form-item label="干运行模式">
              <el-switch v-model="config.dry_run_mode" @change="saveConfig" />
              <span class="form-hint">开启后仅记录"将执行"但不真正执行</span>
            </el-form-item>
            <el-form-item label="单会话最大执行次数">
              <el-input-number v-model="config.max_actions_per_session" :min="1" :max="999" @change="saveConfig" />
            </el-form-item>
            <el-form-item label="单日最大执行次数">
              <el-input-number v-model="config.max_actions_per_day" :min="1" :max="9999" @change="saveConfig" />
            </el-form-item>
            <el-form-item label="允许最大风险等级">
              <el-select v-model="config.max_risk_level" @change="saveConfig">
                <el-option v-for="l in riskLevels" :key="l" :label="l" :value="l" />
              </el-select>
            </el-form-item>
            <el-form-item label="写操作窗口开始">
              <el-time-picker v-model="windowStart" format="HH:mm" value-format="HH:mm" :clearable="true" @change="saveConfig" />
              <span class="form-hint">空=不限制</span>
            </el-form-item>
            <el-form-item label="写操作窗口结束">
              <el-time-picker v-model="windowEnd" format="HH:mm" value-format="HH:mm" :clearable="true" @change="saveConfig" />
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="策略管理" name="policies">
        <div class="section-header">
          <el-button type="primary" size="small" @click="showPolicyForm = true">新建策略</el-button>
        </div>
        <el-table :data="policies" stripe size="small" v-loading="loading.policies">
          <el-table-column prop="name" label="策略名" min-width="140" />
          <el-table-column prop="scope_type" label="范围" width="80" />
          <el-table-column label="资产白名单" width="160">
            <template #default="{ row }">
              <el-tag v-if="!row.allowed_asset_ids || row.allowed_asset_ids.length === 0" size="small" type="info">不限</el-tag>
              <el-tag v-for="a in (row.allowed_asset_ids || []).slice(0, 3)" :key="a" size="small" style="margin-right:4px">{{ a }}</el-tag>
              <span v-if="(row.allowed_asset_ids || []).length > 3" class="more-tag">+{{ (row.allowed_asset_ids || []).length - 3 }}</span>
            </template>
          </el-table-column>
          <el-table-column label="风险上限" width="80">
            <template #default="{ row }">{{ row.max_risk_level }}</template>
          </el-table-column>
          <el-table-column prop="is_enabled" label="启用" width="60">
            <template #default="{ row }">
              <el-tag :type="row.is_enabled ? 'success' : 'info'" size="small">{{ row.is_enabled ? '是' : '否' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="editPolicy(row)">编辑</el-button>
              <el-button link type="danger" size="small" @click="deletePolicy(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="决策测试" name="evaluate">
        <el-card shadow="never">
          <el-form :model="evalForm" label-width="140px" size="small">
            <el-form-item label="动作类型">
              <el-input v-model="evalForm.action_type" placeholder="restart/clean/scale/script/run_command" />
            </el-form-item>
            <el-form-item label="工具名">
              <el-input v-model="evalForm.tool_name" placeholder="execute_restart_service" />
            </el-form-item>
            <el-form-item label="资产 ID">
              <el-input-number v-model="evalForm.asset_id" :min="0" />
            </el-form-item>
            <el-form-item label="命令">
              <el-input v-model="evalForm.command" placeholder="systemctl restart nginx" />
            </el-form-item>
            <el-form-item label="风险等级">
              <el-select v-model="evalForm.risk_level">
                <el-option v-for="l in riskLevels" :key="l" :label="l" :value="l" />
              </el-select>
            </el-form-item>
            <el-form-item label="用户 ID / 角色 ID">
              <el-input-number v-model="evalForm.user_id" :min="0" style="width:150px;margin-right:12px" />
              <el-input-number v-model="evalForm.role_id" :min="0" style="width:150px" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="runEvaluate">测试决策</el-button>
            </el-form-item>
          </el-form>
          <el-alert v-if="evalResult" :title="evalResult.decision" :description="evalResult.reason" :type="evalResult.decision === 'allowed' ? 'success' : 'warning'" show-icon style="margin-top:12px" />
          <pre v-if="evalResult" class="eval-result">{{ JSON.stringify(evalResult, null, 2) }}</pre>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="执行日志" name="logs">
        <el-table :data="logs" stripe size="small" v-loading="loading.logs">
          <el-table-column prop="created_at" label="时间" width="160" />
          <el-table-column prop="action_type" label="动作" width="90" />
          <el-table-column prop="tool_name" label="工具" width="160" />
          <el-table-column prop="risk_level" label="风险" width="70" />
          <el-table-column prop="mode" label="模式" width="70">
            <template #default="{ row }">
              <el-tag :type="row.mode === 'dry_run' ? 'warning' : 'success'" size="small">{{ row.mode }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="decision" label="决策" width="80">
            <template #default="{ row }">
              <el-tag :type="row.decision === 'allowed' ? 'success' : 'danger'" size="small">{{ row.decision }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="reject_reason" label="拒绝原因" min-width="140" />
          <el-table-column prop="asset_id" label="资产 ID" width="70" />
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="showPolicyForm" :title="editingPolicy ? '编辑策略' : '新建策略'" width="700px">
      <el-form :model="policyForm" label-width="140px" size="small">
        <el-form-item label="策略名">
          <el-input v-model="policyForm.name" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="policyForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="作用范围类型">
          <el-select v-model="policyForm.scope_type">
            <el-option label="全局" value="global" />
            <el-option label="角色" value="role" />
            <el-option label="用户" value="user" />
            <el-option label="会话" value="session" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="policyForm.scope_type !== 'global'" label="作用范围 ID">
          <el-input-number v-model="policyForm.scope_id" :min="1" />
        </el-form-item>
        <el-form-item label="资产白名单 ID">
          <el-input v-model="policyForm.allowed_asset_ids_str" placeholder="逗号分隔，空=不限" />
        </el-form-item>
        <el-form-item label="资产黑名单 ID">
          <el-input v-model="policyForm.blocked_asset_ids_str" placeholder="逗号分隔" />
        </el-form-item>
        <el-form-item label="工具白名单">
          <el-input v-model="policyForm.allowed_tools_str" placeholder="逗号分隔，空=继承全部" />
        </el-form-item>
        <el-form-item label="工具黑名单">
          <el-input v-model="policyForm.blocked_tools_str" placeholder="逗号分隔" />
        </el-form-item>
        <el-form-item label="允许命令前缀">
          <el-input v-model="policyForm.allowed_commands_str" placeholder="逗号分隔，如 systemctl restart,df" />
        </el-form-item>
        <el-form-item label="禁止命令规则">
          <el-input v-model="policyForm.blocked_commands_str" placeholder="逗号分隔，支持正则" />
        </el-form-item>
        <el-form-item label="最大风险等级">
          <el-select v-model="policyForm.max_risk_level">
            <el-option v-for="l in riskLevels" :key="l" :label="l" :value="l" />
          </el-select>
        </el-form-item>
        <el-form-item label="每日执行次数">
          <el-input-number v-model="policyForm.max_actions_per_day" :min="0" :max="9999" />
          <span class="form-hint">0=继承全局</span>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="policyForm.is_enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPolicyForm = false">取消</el-button>
        <el-button type="primary" @click="savePolicy">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import request from '@/api/request'

const activeTab = ref('config')
const showPolicyForm = ref(false)
const editingPolicy = ref(null)
const riskLevels = ref(['read_only', 'advisory', 'medium', 'high', 'critical'])
const config = reactive({
  is_enabled: false,
  dry_run_mode: false,
  max_actions_per_session: 10,
  max_actions_per_day: 50,
  max_risk_level: 'critical',
  execution_window_start: '',
  execution_window_end: '',
})
const windowStart = ref(null)
const windowEnd = ref(null)
const policies = ref([])
const logs = ref([])
const loading = reactive({ policies: false, logs: false })
const evalForm = reactive({
  action_type: 'restart',
  tool_name: 'execute_restart_service',
  asset_id: 1,
  command: 'systemctl restart nginx',
  risk_level: 'high',
  user_id: 0,
  role_id: 0,
})
const evalResult = ref(null)
const policyForm = reactive({
  name: '', description: '', scope_type: 'global', scope_id: 0,
  allowed_asset_ids_str: '', blocked_asset_ids_str: '',
  allowed_tools_str: '', blocked_tools_str: '',
  allowed_commands_str: '', blocked_commands_str: '',
  max_risk_level: 'critical', max_actions_per_day: 0,
  is_enabled: true,
})

onMounted(() => {
  loadConfig()
  loadPolicies()
  loadLogs()
})

async function loadConfig() {
  try {
    const res = await request.get('/sandbox/api/config')
    Object.assign(config, res)
    windowStart.value = res.execution_window_start || null
    windowEnd.value = res.execution_window_end || null
  } catch (e) { /* ignore */ }
}

async function saveConfig() {
  try {
    config.execution_window_start = windowStart.value || ''
    config.execution_window_end = windowEnd.value || ''
    await request.post('/sandbox/api/config', config)
  } catch (e) { /* ignore */ }
}

async function loadPolicies() {
  loading.policies = true
  try {
    policies.value = await request.get('/sandbox/api/policies')
  } catch (e) { /* ignore */ }
  loading.policies = false
}

async function loadLogs() {
  loading.logs = true
  try {
    logs.value = await request.get('/sandbox/api/logs', { params: { limit: 100 } })
  } catch (e) { /* ignore */ }
  loading.logs = false
}

function editPolicy(row) {
  editingPolicy.value = row
  policyForm.name = row.name
  policyForm.description = row.description
  policyForm.scope_type = row.scope_type
  policyForm.scope_id = row.scope_id
  policyForm.allowed_asset_ids_str = (row.allowed_asset_ids || []).join(',')
  policyForm.blocked_asset_ids_str = (row.blocked_asset_ids || []).join(',')
  policyForm.allowed_tools_str = (row.allowed_tools || []).join(',')
  policyForm.blocked_tools_str = (row.blocked_tools || []).join(',')
  policyForm.allowed_commands_str = (row.allowed_commands || []).join(',')
  policyForm.blocked_commands_str = (row.blocked_commands || []).join(',')
  policyForm.max_risk_level = row.max_risk_level
  policyForm.max_actions_per_day = row.max_actions_per_day
  policyForm.is_enabled = row.is_enabled
  showPolicyForm.value = true
}

async function savePolicy() {
  const data = {
    name: policyForm.name,
    description: policyForm.description,
    scope_type: policyForm.scope_type,
    scope_id: policyForm.scope_id,
    allowed_asset_ids: policyForm.allowed_asset_ids_str ? policyForm.allowed_asset_ids_str.split(',').map(s => s.trim()).filter(Boolean).map(Number) : [],
    blocked_asset_ids: policyForm.blocked_asset_ids_str ? policyForm.blocked_asset_ids_str.split(',').map(s => s.trim()).filter(Boolean).map(Number) : [],
    allowed_tools: policyForm.allowed_tools_str ? policyForm.allowed_tools_str.split(',').map(s => s.trim()).filter(Boolean) : [],
    blocked_tools: policyForm.blocked_tools_str ? policyForm.blocked_tools_str.split(',').map(s => s.trim()).filter(Boolean) : [],
    allowed_commands: policyForm.allowed_commands_str ? policyForm.allowed_commands_str.split(',').map(s => s.trim()).filter(Boolean) : [],
    blocked_commands: policyForm.blocked_commands_str ? policyForm.blocked_commands_str.split(',').map(s => s.trim()).filter(Boolean) : [],
    max_risk_level: policyForm.max_risk_level,
    max_actions_per_day: policyForm.max_actions_per_day,
    is_enabled: policyForm.is_enabled,
  }
  try {
    if (editingPolicy.value) {
      await request.put(`/sandbox/api/policies/${editingPolicy.value.id}`, data)
    } else {
      await request.post('/sandbox/api/policies', data)
    }
  } catch (e) { /* ignore */ }
  showPolicyForm.value = false
  editingPolicy.value = null
  loadPolicies()
}

async function deletePolicy(id) {
  try {
    await request.delete(`/sandbox/api/policies/${id}`)
    loadPolicies()
  } catch (e) { /* ignore */ }
}

async function runEvaluate() {
  evalResult.value = null
  try {
    evalResult.value = await request.post('/sandbox/api/evaluate', evalForm)
  } catch (e) { /* ignore */ }
}
</script>

<style scoped>
.sandbox-page {
  padding: 20px;
  max-width: 1000px;
}
.sandbox-tabs {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
}
.section-header {
  margin-bottom: 12px;
}
.form-hint {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}
.more-tag {
  color: #909399;
  font-size: 12px;
}
.eval-result {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  font-size: 12px;
  margin-top: 8px;
  white-space: pre-wrap;
}
</style>