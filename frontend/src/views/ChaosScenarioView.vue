<template>
  <div class="chaos-scenario">
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="title">混沌实验场景库</span>
          <el-button type="primary" @click="showCreateDialog">+ 自定义场景</el-button>
        </div>
      </template>

      <div class="layer-tabs">
        <el-radio-group v-model="activeLayer" @change="filterScenarios">
          <el-radio-button label="all">全部 ({{ scenarioList.length }})</el-radio-button>
          <el-radio-button v-for="L in LAYERS" :key="L.value" :label="L.value">
            {{ L.label }} ({{ countByLayer(L.value) }})
          </el-radio-button>
        </el-radio-group>
      </div>

      <el-row :gutter="16">
        <el-col v-for="scenario in filteredList" :key="scenario.id" :span="6" style="margin-bottom: 16px">
          <el-card shadow="hover" class="scenario-card" @click="createExperimentFromScenario(scenario)">
            <div class="scenario-header">
              <el-icon :size="28" :color="getLayerColor(scenario.target_layer)">
                <component :is="getLayerIcon(scenario.target_layer)" />
              </el-icon>
              <el-tag :type="getRiskType(scenario.risk_level)" effect="dark" size="small">
                {{ getRiskLabel(scenario.risk_level) }}
              </el-tag>
            </div>
            <div class="scenario-name">{{ scenario.name }}</div>
            <div class="scenario-desc">{{ scenario.description }}</div>
            <div class="scenario-meta">
              <el-tag size="small" effect="plain" :type="getLayerTagType(scenario.target_layer)">
                {{ getLayerLabel(scenario.target_layer) }}
              </el-tag>
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

      <el-empty v-if="filteredList.length === 0" description="当前层级暂无场景" />
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
        <el-form-item label="目标层级" required>
          <el-select v-model="createForm.target_layer" style="width: 100%">
            <el-option v-for="L in LAYERS" :key="L.value" :label="L.label" :value="L.value" />
          </el-select>
          <div class="form-tip">决定故障注入手段：主机=SSH 到服务器，容器=docker 操作，K8s=集群 API，网络=tc 流控</div>
        </el-form-item>
        <el-form-item label="故障类型">
          <el-select v-model="createForm.fault_type" style="width: 100%">
            <el-option label="CPU 压力 (cpu-stress)" value="cpu-stress" />
            <el-option label="内存压力 (mem-stress)" value="mem-stress" />
            <el-option label="磁盘填充 (disk-fill)" value="disk-fill" />
            <el-option label="磁盘 IO 压力 (disk-io-stress)" value="disk-io-stress" />
            <el-option label="进程崩溃 (process-kill)" value="process-kill" />
            <el-option label="网络延迟 (network-delay)" value="network-delay" />
            <el-option label="网络丢包 (network-loss)" value="network-loss" />
            <el-option label="带宽限制 (network-bandwidth)" value="network-bandwidth" />
            <el-option label="网络分区 (network-partition)" value="network-partition" />
            <el-option label="容器停止 (container-stop)" value="container-stop" />
            <el-option label="容器重启 (container-restart)" value="container-restart" />
            <el-option label="Pod 故障 (pod-kill)" value="pod-kill" />
            <el-option label="Deployment 重启 (deployment-restart)" value="deployment-restart" />
            <el-option label="DNS 故障 (dns-fault)" value="dns-fault" />
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
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'

const API = '/api/chaos'
const scenarioList = ref([])
const activeLayer = ref('all')
const createDialogVisible = ref(false)
const createForm = reactive({
  name: '', description: '', target_layer: 'host', fault_type: 'cpu-stress',
  risk_level: 'low', recommended_slo: ''
})

const LAYERS = [
  { value: 'host', label: '主机/VM', icon: 'Monitor', color: '#409EFF' },
  { value: 'container', label: '容器', icon: 'Box', color: '#67C23A' },
  { value: 'k8s', label: 'K8s 编排', icon: 'Connection', color: '#9B59B6' },
  { value: 'network', label: '网络', icon: 'Share', color: '#E6A23C' },
]

const getFaultTypeLabel = (t) => ({
  'cpu-stress': 'CPU 压力', 'mem-stress': '内存压力', 'disk-fill': '磁盘填充',
  'disk-io-stress': '磁盘 IO', 'process-kill': '进程崩溃',
  'network-delay': '网络延迟', 'network-loss': '网络丢包',
  'network-bandwidth': '带宽限制', 'network-partition': '网络分区',
  'container-stop': '容器停止', 'container-restart': '容器重启',
  'pod-kill': 'Pod 故障', 'deployment-restart': 'Deployment 重启', 'dns-fault': 'DNS 故障'
}[t] || t)

const getRiskType = (r) => ({ low: 'success', medium: 'warning', high: 'danger' }[r] || 'info')
const getRiskLabel = (r) => ({ low: '低风险', medium: '中风险', high: '高风险' }[r] || r)

const getLayerLabel = (l) => (LAYERS.find(x => x.value === l) || {}).label || l
const getLayerColor = (l) => (LAYERS.find(x => x.value === l) || {}).color || '#409EFF'
const getLayerIcon = (l) => (LAYERS.find(x => x.value === l) || {}).icon || 'Setting'
const getLayerTagType = (l) => ({
  host: 'primary', container: 'success', k8s: 'warning', network: 'info'
}[l] || 'info')

const countByLayer = (l) => scenarioList.value.filter(s => s.target_layer === l).length
const filteredList = computed(() =>
  activeLayer.value === 'all' ? scenarioList.value : scenarioList.value.filter(s => s.target_layer === activeLayer.value)
)

async function loadScenarios() {
  try { const { data } = await axios.get(`${API}/scenarios`); scenarioList.value = data } catch {}
}

function showCreateDialog() {
  Object.assign(createForm, { name: '', description: '', target_layer: 'host', fault_type: 'cpu-stress', risk_level: 'low', recommended_slo: '' })
  createDialogVisible.value = true
}

async function createScenario() {
  if (!createForm.name) { ElMessage.warning('请填写场景名称'); return }
  try {
    await axios.post(`${API}/scenarios`, {
      name: createForm.name, description: createForm.description,
      category: createForm.target_layer, target_layer: createForm.target_layer,
      fault_type: createForm.fault_type,
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
  const prefill = {
    name: `基于场景: ${scenario.name}`,
    description: scenario.description,
    fault_type: scenario.fault_type,
    target_layer: scenario.target_layer,
    fault_params: scenario.fault_params || { duration: 300 }
  }
  sessionStorage.setItem('chaos_prefill', JSON.stringify(prefill))
  if (window._navigateTo) {
    window._navigateTo('chaos-experiment')
    ElMessage.success('已跳转至实验管理页，请选择目标资产后创建')
  } else {
    ElMessage.warning('请到"混沌实验"菜单创建实验')
  }
}

onMounted(() => loadScenarios())
</script>

<style scoped>
.chaos-scenario { padding: 0; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.title { font-size: 16px; font-weight: 600; }
.layer-tabs { margin-bottom: 16px; }
.scenario-card { cursor: pointer; transition: transform 0.2s; }
.scenario-card:hover { transform: translateY(-4px); }
.scenario-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.scenario-name { font-size: 15px; font-weight: 600; margin-bottom: 6px; }
.scenario-desc { font-size: 12px; color: #909399; line-height: 1.5; margin-bottom: 8px; min-height: 36px; }
.scenario-meta { display: flex; gap: 6px; margin-bottom: 6px; flex-wrap: wrap; }
.scenario-slo { font-size: 12px; color: #409EFF; margin-bottom: 8px; }
.scenario-action { display: flex; gap: 8px; }
.form-tip { font-size: 12px; color: #909399; margin-top: 4px; line-height: 1.4; }
</style>
