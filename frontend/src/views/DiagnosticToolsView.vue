<template>
  <div class="diag-tools">
    <!-- 顶部说明 -->
    <div class="diag-header">
      <div class="diag-title">
        <el-icon :size="20"><Cpu /></el-icon>
        <span>实时诊断工具中心</span>
      </div>
      <div class="diag-desc">三层工具体系：Snapshot 快照初筛 → Focused 定向验证 → Flexible 灵活受控</div>
    </div>

    <!-- 资产选择 -->
    <div class="asset-bar">
      <span class="bar-label">目标主机：</span>
      <el-select v-model="selectedAssetId" placeholder="选择目标资产" filterable style="width: 260px" @change="onAssetChange">
        <el-option v-for="a in assets" :key="a.id" :label="`${a.name} (${a.ip})`" :value="a.id" />
      </el-select>
      <el-tag v-if="selectedAsset" type="success" size="small">{{ selectedAsset.name }} · {{ selectedAsset.ip }}</el-tag>
    </div>

    <!-- 三层 Tab -->
    <el-tabs v-model="activeTab" class="diag-tabs">
      <el-tab-pane v-for="cat in categories" :key="cat.key" :name="cat.key">
        <template #label>
          <span class="tab-label">
            <el-icon :size="14"><component :is="getCatIcon(cat.key)" /></el-icon>
            {{ cat.label }}
            <el-badge :value="getToolsByCategory(cat.key).length" type="info" />
          </span>
        </template>

        <!-- 工具卡片网格 -->
        <div class="tool-grid">
          <div
            v-for="tool in getToolsByCategory(cat.key)"
            :key="tool.id"
            class="tool-card"
            :class="{ 'is-flexible': tool.custom }"
            @click="openTool(tool)"
          >
            <div class="tool-card-header">
              <span class="tool-id">{{ tool.id }}</span>
              <el-tag size="small" :type="riskType(tool.risk_level)">{{ tool.risk_level }}</el-tag>
            </div>
            <div class="tool-name">{{ tool.name }}</div>
            <div class="tool-desc">{{ tool.description }}</div>
            <div class="tool-meta">
              <span v-if="tool.timeout"><el-icon><Timer /></el-icon> {{ tool.timeout }}s</span>
              <span><el-icon><Monitor /></el-icon> {{ tool.target_type }}</span>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 执行结果对话框 -->
    <el-dialog v-model="resultDialog" :title="currentTool ? `${currentTool.name} - 诊断结果` : '诊断结果'" width="80%" top="5vh">
      <template v-if="currentTool">
        <div class="result-meta">
          <el-descriptions :column="3" border size="small">
            <el-descriptions-item label="工具">{{ currentTool.id }}</el-descriptions-item>
            <el-descriptions-item label="目标">{{ result?.asset_name }} ({{ result?.asset_ip }})</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="result?.success ? 'success' : 'danger'" size="small">
                {{ result?.success ? '成功' : '失败' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="执行时间">{{ result?.executed_at }}</el-descriptions-item>
            <el-descriptions-item label="退出码">{{ result?.exit_code }}</el-descriptions-item>
            <el-descriptions-item label="超时">{{ currentTool.timeout }}s</el-descriptions-item>
          </el-descriptions>
        </div>

        <!-- 自定义命令输入 -->
        <div v-if="currentTool.custom" class="custom-cmd-area">
          <el-input
            v-model="customCommand"
            :placeholder="currentTool.id === 'flex.mysql' ? '输入只读 SQL (仅允许 SELECT/SHOW/DESC)' : '输入只读 Shell 命令 (白名单校验)'"
            type="textarea"
            :rows="2"
          />
          <el-button @click="validateCmd" size="small" :loading="validating">校验命令</el-button>
          <el-tag v-if="validateResult" :type="validateResult.valid ? 'success' : 'danger'" size="small">
            {{ validateResult.message }}
          </el-tag>
        </div>

        <!-- 执行按钮 -->
        <div class="exec-bar">
          <el-button type="primary" @click="executeTool" :loading="executing" :disabled="!selectedAssetId || (currentTool.custom && !customCommand)">
            <el-icon><VideoPlay /></el-icon> 执行诊断
          </el-button>
        </div>

        <!-- 输出结果 -->
        <div v-if="result" class="result-output">
          <div class="output-header">
            <span>诊断输出</span>
            <el-button text size="small" @click="copyOutput">复制</el-button>
          </div>
          <pre class="output-body">{{ result.output }}</pre>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Cpu, Timer, Monitor, VideoPlay, View, Aim, EditPen
} from '@element-plus/icons-vue'
import request from '@/api/request'

const assets = ref([])
const selectedAssetId = ref(null)
const selectedAsset = computed(() => assets.value.find(a => a.id === selectedAssetId.value))
const activeTab = ref('snapshot')
const categories = ref([])
const allTools = ref([])
const resultDialog = ref(false)
const currentTool = ref(null)
const customCommand = ref('')
const executing = ref(false)
const result = ref(null)
const validating = ref(false)
const validateResult = ref(null)

function getCatIcon(key) {
  return { snapshot: View, focused: Aim, flexible: EditPen }[key] || View
}
function riskType(r) {
  return { read_only: 'success', low_risk: 'warning', high_risk: 'danger' }[r] || 'info'
}
function getToolsByCategory(cat) {
  return allTools.value.filter(t => t.category === cat)
}

async function loadAssets() {
  try {
    const data = await request.get('/api/chaos/targets')
    assets.value = data || []
    if (assets.value.length > 0) selectedAssetId.value = assets.value[0].id
  } catch (e) {
    try {
      const data = await request.get('/assets/api/list', { params: { status: 'online' } })
      assets.value = (data.assets || data || []).filter(a => a.status === 'online')
    } catch {}
  }
}

async function loadRegistry() {
  const data = await request.get('/api/diagnostic-tools/registry')
  allTools.value = []
  for (const cat of ['snapshot', 'focused', 'flexible']) {
    allTools.value.push(...(data.categories[cat] || []))
  }
}

async function loadCategories() {
  const data = await request.get('/api/diagnostic-tools/categories')
  categories.value = data.categories
}

function openTool(tool) {
  currentTool.value = tool
  result.value = null
  customCommand.value = ''
  validateResult.value = null
  resultDialog.value = true
}

function onAssetChange() {
  result.value = null
}

async function validateCmd() {
  if (!customCommand.value) return
  validating.value = true
  try {
    const data = await request.post('/api/diagnostic-tools/validate', { command: customCommand.value })
    validateResult.value = data
    if (data.valid) ElMessage.success('命令校验通过')
    else ElMessage.warning(data.message)
  } catch (e) {
    ElMessage.error('校验失败: ' + e.message)
  } finally {
    validating.value = false
  }
}

async function executeTool() {
  if (!selectedAssetId.value) {
    ElMessage.warning('请先选择目标资产')
    return
  }
  executing.value = true
  result.value = null
  try {
    const body = {
      tool_id: currentTool.value.id,
      asset_id: selectedAssetId.value,
    }
    if (currentTool.value.custom) {
      body.custom_command = customCommand.value
    }
    const data = await request.post('/api/diagnostic-tools/execute', body)
    result.value = data
    if (data.success) ElMessage.success('诊断执行完成')
    else ElMessage.warning('诊断执行失败，查看输出详情')
  } catch (e) {
    ElMessage.error('执行失败: ' + e.message)
  } finally {
    executing.value = false
  }
}

function copyOutput() {
  if (result.value?.output) {
    navigator.clipboard.writeText(result.value.output)
    ElMessage.success('已复制到剪贴板')
  }
}

onMounted(async () => {
  await Promise.all([loadAssets(), loadRegistry(), loadCategories()])
})
</script>

<style scoped>
.diag-tools { padding: 4px; }
.diag-header { margin-bottom: 16px; }
.diag-title { display: flex; align-items: center; gap: 8px; font-size: 18px; font-weight: 700; color: var(--text-primary, #1f2937); }
.diag-desc { font-size: 13px; color: var(--text-secondary, #6b7280); margin-top: 4px; }
.asset-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.bar-label { font-size: 13px; color: var(--text-secondary, #6b7280); white-space: nowrap; }
.diag-tabs { min-height: 400px; }
.tab-label { display: inline-flex; align-items: center; gap: 4px; }
.tool-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  padding: 8px 0;
}
.tool-card {
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 10px;
  padding: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.tool-card:hover {
  border-color: var(--primary-color, #6366f1);
  box-shadow: 0 2px 12px rgba(99,102,241,0.1);
  transform: translateY(-1px);
}
.tool-card.is-flexible { border-style: dashed; }
.tool-card-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 6px;
}
.tool-id {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 12px; font-weight: 600;
  color: var(--primary-color, #6366f1);
}
.tool-name {
  font-size: 14px; font-weight: 600;
  color: var(--text-primary, #1f2937);
  margin-bottom: 4px;
}
.tool-desc {
  font-size: 12px; color: var(--text-secondary, #6b7280);
  line-height: 1.5; margin-bottom: 8px;
}
.tool-meta {
  display: flex; gap: 12px;
  font-size: 11px; color: var(--text-tertiary, #9ca3af);
}
.tool-meta span { display: flex; align-items: center; gap: 2px; }
.result-meta { margin-bottom: 12px; }
.custom-cmd-area { margin-bottom: 12px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.exec-bar { margin-bottom: 12px; }
.result-output { margin-top: 12px; }
.output-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 4px;
  font-size: 13px; font-weight: 600; color: var(--text-primary, #1f2937);
}
.output-body {
  background: #1e1e2e; color: #cdd6f4;
  padding: 12px; border-radius: 8px;
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 12px; line-height: 1.6;
  max-height: 400px; overflow: auto;
  white-space: pre-wrap; word-break: break-all;
}
</style>
