<template>
  <div class="chaos-scenario">
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="title">混沌实验场景库</span>
          <el-button type="primary" @click="showCreateDialog">+ 自定义场景</el-button>
        </div>
      </template>

      <el-row :gutter="16">
        <el-col v-for="scenario in scenarioList" :key="scenario.id" :span="6" style="margin-bottom: 16px">
          <el-card shadow="hover" class="scenario-card" @click="createExperimentFromScenario(scenario)">
            <div class="scenario-header">
              <el-icon :size="28" :color="getCategoryColor(scenario.category)">
                <component :is="getCategoryIcon(scenario.category)" />
              </el-icon>
              <el-tag :type="getRiskType(scenario.risk_level)" effect="dark" size="small">
                {{ getRiskLabel(scenario.risk_level) }}
              </el-tag>
            </div>
            <div class="scenario-name">{{ scenario.name }}</div>
            <div class="scenario-desc">{{ scenario.description }}</div>
            <div class="scenario-meta">
              <el-tag size="small" effect="plain">{{ getFaultTypeLabel(scenario.fault_type) }}</el-tag>
              <el-tag v-if="scenario.is_builtin" size="small" type="info" effect="plain">内置</el-tag>
              <el-tag v-else size="small" type="warning" effect="plain">自定义</el-tag>
            </div>
            <div class="scenario-slo" v-if="scenario.recommended_slo">
              推荐 SLO: {{ scenario.recommended_slo }}
            </div>
            <div class="scenario-action">
              <el-button type="primary" size="small" @click.stop="createExperimentFromScenario(scenario)">
                一键创建实验
              </el-button>
              <el-button v-if="!scenario.is_builtin" type="danger" size="small" @click.stop="deleteScenario(scenario)">
                删除
              </el-button>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </el-card>

    <!-- 创建自定义场景弹窗 -->
    <el-dialog v-model="createDialogVisible" title="创建自定义场景" width="560px">
      <el-form :model="createForm" label-width="100px">
        <el-form-item label="场景名称" required>
          <el-input v-model="createForm.name" placeholder="如: 数据库连接超时" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="类别">
          <el-select v-model="createForm.category" style="width: 100%">
            <el-option label="Pod 故障" value="pod" />
            <el-option label="网络故障" value="network" />
            <el-option label="CPU 压力" value="cpu" />
            <el-option label="内存压力" value="memory" />
            <el-option label="磁盘故障" value="disk" />
            <el-option label="依赖故障" value="dependency" />
          </el-select>
        </el-form-item>
        <el-form-item label="故障类型">
          <el-select v-model="createForm.fault_type" style="width: 100%">
            <el-option label="Pod 故障 (pod-kill)" value="pod-kill" />
            <el-option label="CPU 压力 (cpu-stress)" value="cpu-stress" />
            <el-option label="内存压力 (mem-stress)" value="mem-stress" />
            <el-option label="网络延迟 (network-delay)" value="network-delay" />
            <el-option label="网络丢包 (network-loss)" value="network-loss" />
            <el-option label="磁盘填充 (disk-fill)" value="disk-fill" />
          </el-select>
        </el-form-item>
        <el-form-item label="风险等级">
          <el-radio-group v-model="createForm.risk_level">
            <el-radio value="low">低风险</el-radio>
            <el-radio value="medium">中风险</el-radio>
            <el-radio value="high">高风险</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="推荐 SLO">
          <el-input v-model="createForm.recommended_slo" placeholder="如 payment-service" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="createScenario">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'

const API = '/api/chaos'
const scenarioList = ref([])
const createDialogVisible = ref(false)
const createForm = reactive({
  name: '', description: '', category: 'pod', fault_type: 'pod-kill',
  risk_level: 'low', recommended_slo: ''
})

const getFaultTypeLabel = (t) => ({
  'pod-kill': 'Pod 故障', 'cpu-stress': 'CPU 压力', 'mem-stress': '内存压力',
  'network-delay': '网络延迟', 'network-loss': '网络丢包', 'disk-fill': '磁盘填充'
}[t] || t)

const getRiskType = (r) => ({ low: 'success', medium: 'warning', high: 'danger' }[r] || 'info')
const getRiskLabel = (r) => ({ low: '低风险', medium: '中风险', high: '高风险' }[r] || r)

const getCategoryColor = (c) => ({
  pod: '#F56C6C', network: '#409EFF', cpu: '#E6A23C',
  memory: '#909399', disk: '#67C23A', dependency: '#9B59B6'
}[c] || '#409EFF')

const getCategoryIcon = (c) => {
  const icons = { pod: 'CircleClose', network: 'Connection', cpu: 'Cpu', memory: 'Histogram', disk: 'Files', dependency: 'Share' }
  return icons[c] || 'Setting'
}

async function loadScenarios() {
  try { const { data } = await axios.get(`${API}/scenarios`); scenarioList.value = data } catch {}
}

function showCreateDialog() {
  Object.assign(createForm, { name: '', description: '', category: 'pod', fault_type: 'pod-kill', risk_level: 'low', recommended_slo: '' })
  createDialogVisible.value = true
}

async function createScenario() {
  if (!createForm.name) { ElMessage.warning('请填写场景名称'); return }
  try {
    await axios.post(`${API}/scenarios`, {
      name: createForm.name, description: createForm.description,
      category: createForm.category, fault_type: createForm.fault_type,
      fault_params: { duration: 300 }, recommended_slo: createForm.recommended_slo,
      risk_level: createForm.risk_level
    })
    ElMessage.success('场景创建成功')
    createDialogVisible.value = false
    loadScenarios()
  } catch (e) { ElMessage.error('创建失败') }
}

async function deleteScenario(scenario) {
  try {
    await ElMessageBox.confirm(`确认删除场景"${scenario.name}"？`, '提示', { type: 'warning' })
    await axios.delete(`${API}/scenarios/${scenario.id}`)
    ElMessage.success('已删除')
    loadScenarios()
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败') }
}

async function createExperimentFromScenario(scenario) {
  try {
    const params = scenario.fault_params || { duration: 300 }
    await axios.post(`${API}/experiments`, {
      name: `基于场景: ${scenario.name}`,
      description: scenario.description,
      target_type: scenario.category === 'network' ? 'network' : 'pod',
      target_selector: { service: scenario.recommended_slo || 'default-service', namespace: 'default' },
      fault_type: scenario.fault_type,
      fault_params: params,
      steady_state: { metric: 'availability', threshold: 99.0 }
    })
    ElMessage.success('实验已创建，请到"混沌实验"页面启动')
  } catch (e) { ElMessage.error('创建实验失败') }
}

onMounted(() => loadScenarios())
</script>

<style scoped>
.chaos-scenario { padding: 0; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.title { font-size: 16px; font-weight: 600; }
.scenario-card { cursor: pointer; transition: transform 0.2s; }
.scenario-card:hover { transform: translateY(-4px); }
.scenario-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.scenario-name { font-size: 15px; font-weight: 600; margin-bottom: 6px; }
.scenario-desc { font-size: 12px; color: #909399; line-height: 1.5; margin-bottom: 8px; min-height: 36px; }
.scenario-meta { display: flex; gap: 6px; margin-bottom: 6px; }
.scenario-slo { font-size: 12px; color: #409EFF; margin-bottom: 8px; }
.scenario-action { display: flex; gap: 8px; }
</style>
