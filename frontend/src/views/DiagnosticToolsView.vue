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
          <el-button type="primary" plain :loading="aiAnalyzing" :disabled="!result" @click="analyzeOutput">
            <el-icon><MagicStick /></el-icon> {{ aiAnalyzing ? 'AI 分析中...' : (aiAnalysis ? '重新解读' : 'AI 智能解读') }}
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

        <!-- AI 智能解读 -->
        <div v-if="result" class="ai-section">
          <div class="ai-header">
            <span class="ai-title"><el-icon :size="16"><MagicStick /></el-icon> AI 智能解读</span>
          </div>
          <div v-if="aiAnalyzing" class="ai-loading">
            <el-icon class="is-loading"><Loading /></el-icon> 正在调用 AI 进行根因分析，请稍候（最长约 2 分钟）...
          </div>
          <div v-else-if="aiAnalysis" class="ai-content" v-html="aiAnalysis"></div>
          <div v-else class="ai-tip">点击「AI 智能解读」，AI 将对上方诊断输出进行根因推断、异常定位与修复建议。</div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Cpu, Timer, Monitor, VideoPlay, View, Aim, EditPen, MagicStick, Loading
} from '@element-plus/icons-vue'
import MarkdownIt from 'markdown-it'
import request from '@/api/request'

const md = new MarkdownIt({ html: false, breaks: true, linkify: true })

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
const aiAnalyzing = ref(false)
const aiAnalysis = ref('')
const aiAnalyzedAt = ref('')

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
  aiAnalysis.value = ''
  aiAnalyzedAt.value = ''
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

async function analyzeOutput() {
  if (!result.value || !result.value.output) {
    ElMessage.warning('请先执行诊断获取输出')
    return
  }
  aiAnalyzing.value = true
  aiAnalysis.value = ''
  aiAnalyzedAt.value = ''
  try {
    const data = await request.post('/api/diagnostic-tools/analyze', {
      tool_id: currentTool.value.id,
      asset_id: selectedAssetId.value,
      command: result.value.command,
      output: result.value.output,
      exit_code: result.value.exit_code,
    }, { timeout: 130000 })
    if (data.ok) {
      aiAnalysis.value = md.render(data.analysis || '')
      aiAnalyzedAt.value = data.analyzed_at || ''
      ElMessage.success('AI 解读完成')
    } else {
      ElMessage.error(data.error || 'AI 解读失败')
    }
  } catch (e) {
    ElMessage.error('AI 解读失败: ' + (e.message || e))
  } finally {
    aiAnalyzing.value = false
  }
}

function reAnalyze() {
  analyzeOutput()
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
.exec-bar { margin-bottom: 12px; display: flex; gap: 10px; align-items: center; }
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
.ai-section {
  margin-top: 16px;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 10px;
  overflow: hidden;
}
.ai-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px;
  background: linear-gradient(90deg, rgba(99,102,241,0.08), rgba(99,102,241,0.02));
  border-bottom: 1px solid var(--border-color, #e5e7eb);
}
.ai-title {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 14px; font-weight: 600;
  color: var(--primary-color, #6366f1);
}
.ai-loading {
  display: flex; align-items: center; gap: 8px;
  padding: 24px 14px;
  font-size: 13px; color: var(--text-secondary, #6b7280);
}
.ai-content {
  padding: 14px 16px;
  font-size: 13px; line-height: 1.8;
  color: var(--text-primary, #1f2937);
  max-height: 460px; overflow: auto;
}
.ai-content :deep(h3) {
  font-size: 15px; margin: 16px 0 6px; font-weight: 700;
  color: var(--primary-color, #6366f1);
  border-left: 3px solid var(--primary-color, #6366f1);
  padding-left: 8px;
}
.ai-content :deep(h3:first-child) { margin-top: 0; }
.ai-content :deep(p) { margin: 6px 0; }
.ai-content :deep(ul), .ai-content :deep(ol) { margin: 6px 0; padding-left: 22px; }
.ai-content :deep(li) { margin: 3px 0; }
.ai-content :deep(code) {
  background: rgba(99,102,241,0.1); color: var(--primary-color, #6366f1);
  padding: 1px 5px; border-radius: 4px;
  font-family: 'SF Mono', 'Consolas', monospace; font-size: 12px;
}
.ai-content :deep(pre) {
  background: #1e1e2e; color: #cdd6f4;
  padding: 10px 12px; border-radius: 8px; overflow: auto;
  font-size: 12px; line-height: 1.6;
}
.ai-content :deep(pre code) { background: none; color: inherit; padding: 0; }
.ai-content :deep(strong) { color: var(--text-primary, #1f2937); }
.ai-tip {
  padding: 20px 16px;
  font-size: 13px; color: var(--text-tertiary, #9ca3af);
  text-align: center;
}
</style>
