<template>
  <div class="awf-page">
    <div class="awf-header">
      <div class="awf-title">
        <input v-model="workflow.name" class="title-input" placeholder="工作流名称" @blur="autoSave">
        <span class="wf-status-badge" :class="workflow.published ? 'published' : 'draft'">{{ workflow.published ? '已发布' : '草稿' }}</span>
      </div>
      <div class="awf-toolbar">
        <button class="btn" @click="newWorkflow">新建</button>
        <button class="btn" @click="loadList">打开</button>
        <button class="btn" @click="autoSave">保存</button>
        <button class="btn btn-primary" @click="publishWorkflow">{{ workflow.published ? '取消发布' : '发布' }}</button>
        <button class="btn btn-success" @click="runTest">运行测试</button>
      </div>
    </div>

    <div class="awf-body">
      <!-- 节点面板 -->
      <div class="node-panel">
        <div class="panel-title">节点类型</div>
        <div class="node-list">
          <div v-for="nt in nodeTypes" :key="nt.type" class="node-item" draggable="true" @dragstart="onDragStart($event, nt.type)">
            <span class="node-icon" :style="{background: nt.color}">{{ nt.icon }}</span>
            <span class="node-label">{{ nt.label }}</span>
          </div>
        </div>
        <div class="panel-title" style="margin-top:16px;">使用说明</div>
        <div class="help-text">1. 拖拽节点到画布<br>2. 拖拽节点边缘连线<br>3. 点击节点配置属性<br>4. 运行测试输入参数</div>
      </div>

      <!-- Vue Flow 画布 -->
      <div class="canvas-wrapper">
        <VueFlow v-model:nodes="nodes" v-model:edges="edges" :default-viewport="{zoom:0.85}" @connect="onConnect" @node-click="onNodeClick" @pane-click="onPaneClick" class="vue-flow-canvas">
          <Background pattern-color="#cbd5e1" :gap="20" />
          <Controls />
          <MiniMap />
          <template #node-start="props"><NodeCard v-bind="props" :node-type-map="nodeTypeMap" @edit="openEditor(props)" /></template>
          <template #node-end="props"><NodeCard v-bind="props" :node-type-map="nodeTypeMap" @edit="openEditor(props)" /></template>
          <template #node-llm="props"><NodeCard v-bind="props" :node-type-map="nodeTypeMap" @edit="openEditor(props)" /></template>
          <template #node-knowledge="props"><NodeCard v-bind="props" :node-type-map="nodeTypeMap" @edit="openEditor(props)" /></template>
          <template #node-tool="props"><NodeCard v-bind="props" :node-type-map="nodeTypeMap" @edit="openEditor(props)" /></template>
          <template #node-condition="props"><NodeCard v-bind="props" :node-type-map="nodeTypeMap" @edit="openEditor(props)" /></template>
          <template #node-code="props"><NodeCard v-bind="props" :node-type-map="nodeTypeMap" @edit="openEditor(props)" /></template>
          <template #node-http="props"><NodeCard v-bind="props" :node-type-map="nodeTypeMap" @edit="openEditor(props)" /></template>
        </VueFlow>
      </div>

      <!-- 属性配置抽屉 -->
      <div class="props-panel" v-if="selectedNode">
        <div class="props-header">
          <span class="props-title">{{ nodeTypeMap[selectedNode.type]?.label }} 节点</span>
          <button class="btn btn-sm btn-danger" @click="deleteNode">删除</button>
        </div>
        <div class="props-body">
          <div class="form-row"><label>节点 ID</label><input v-model="selectedNode.id" class="input" :disabled="true"></div>
          <div class="form-row"><label>节点名称</label><input v-model="selectedNode.data.label" class="input" placeholder="显示名称"></div>

          <!-- Start 节点 -->
          <template v-if="selectedNode.type === 'start'">
            <div class="form-row"><label>输入参数 (JSON)</label>
              <textarea v-model="startInputsStr" class="input textarea mono" rows="5" placeholder='[{"key":"question","type":"string","required":true}]'></textarea>
            </div>
          </template>

          <!-- End 节点 -->
          <template v-if="selectedNode.type === 'end'">
            <div class="form-row"><label>输出映射 (JSON)</label>
              <textarea v-model="endOutputsStr" class="input textarea mono" rows="5" placeholder='[{"key":"answer","value":"{{ nodes.llm1.output.text }}"}]'></textarea>
            </div>
          </template>

          <!-- LLM 节点 -->
          <template v-if="selectedNode.type === 'llm'">
            <div class="form-row"><label>AI Provider</label>
              <select v-model="selectedNode.data.provider_id" class="input">
                <option :value="null">默认</option>
                <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }} ({{ p.default_model }})</option>
              </select>
            </div>
            <div class="form-row"><label>模型</label><input v-model="selectedNode.data.model" class="input" placeholder="gpt-4o"></div>
            <div class="form-row"><label>System Prompt</label><textarea v-model="selectedNode.data.system_prompt" class="input textarea" rows="3" placeholder="系统提示词"></textarea></div>
            <div class="form-row"><label>User Prompt</label><textarea v-model="selectedNode.data.user_prompt" class="input textarea mono" rows="4" placeholder="用户提示词，可用 {{ nodes.xxx.output }}"></textarea></div>
            <div class="form-row"><label>温度</label><input v-model.number="selectedNode.data.temperature" class="input" type="number" step="0.1" min="0" max="2"></div>
            <div class="form-row"><label>Max Tokens</label><input v-model.number="selectedNode.data.max_tokens" class="input" type="number"></div>
          </template>

          <!-- Knowledge 节点 -->
          <template v-if="selectedNode.type === 'knowledge'">
            <div class="form-row"><label>查询语句</label><textarea v-model="selectedNode.data.query" class="input textarea mono" rows="2" placeholder="{{ inputs.question }}"></textarea></div>
            <div class="form-row"><label>知识库 ID</label><input v-model.number="selectedNode.data.kb_id" class="input" type="number"></div>
            <div class="form-row"><label>Top K</label><input v-model.number="selectedNode.data.top_k" class="input" type="number"></div>
            <div class="form-row"><label>分数阈值</label><input v-model.number="selectedNode.data.score_threshold" class="input" type="number" step="0.1" min="0" max="1"></div>
          </template>

          <!-- Tool 节点 -->
          <template v-if="selectedNode.type === 'tool'">
            <div class="form-row"><label>工具名称</label>
              <select v-model="selectedNode.data.tool_name" class="input">
                <option v-for="t in mcpTools" :key="t" :value="t">{{ t }}</option>
              </select>
            </div>
            <div class="form-row"><label>参数 (JSON)</label>
              <textarea v-model="toolParamsStr" class="input textarea mono" rows="5" placeholder='{"alert_id": "{{ inputs.alert_id }}", "limit": 10}'></textarea>
            </div>
          </template>

          <!-- Condition 节点 -->
          <template v-if="selectedNode.type === 'condition'">
            <div class="form-row"><label>分支定义 (JSON)</label>
              <textarea v-model="branchesStr" class="input textarea mono" rows="6" placeholder='[{"condition":"{{ nodes.llm1.output.text contains 严重 }}","target":"escalate"},{"condition":"default","target":"notify"}]'></textarea>
            </div>
          </template>

          <!-- Code 节点 -->
          <template v-if="selectedNode.type === 'code'">
            <div class="form-row"><label>输入映射 (JSON)</label>
              <textarea v-model="codeInputsStr" class="input textarea mono" rows="3" placeholder='{"data": "{{ nodes.tool1.output | tojson }}"}'></textarea>
            </div>
            <div class="form-row"><label>Python 代码</label>
              <textarea v-model="selectedNode.data.code" class="input textarea mono" rows="6" placeholder="result = {'count': len(inputs.get('data', []))}"></textarea>
            </div>
          </template>

          <!-- HTTP 节点 -->
          <template v-if="selectedNode.type === 'http'">
            <div class="form-row"><label>方法</label>
              <select v-model="selectedNode.data.method" class="input">
                <option>GET</option><option>POST</option><option>PUT</option><option>DELETE</option>
              </select>
            </div>
            <div class="form-row"><label>URL</label><input v-model="selectedNode.data.url" class="input" placeholder="https://api.example.com"></div>
            <div class="form-row"><label>Headers (JSON)</label><textarea v-model="httpHeadersStr" class="input textarea mono" rows="2" placeholder='{"Content-Type":"application/json"}'></textarea></div>
            <div class="form-row"><label>Body (JSON)</label><textarea v-model="httpBodyStr" class="input textarea mono" rows="3" placeholder='{"message": "{{ nodes.llm1.output.text }}"}'></textarea></div>
            <div class="form-row"><label>超时(秒)</label><input v-model.number="selectedNode.data.timeout" class="input" type="number"></div>
          </template>
        </div>
      </div>
    </div>

    <!-- 工作流列表 -->
    <div v-if="showList" class="modal-overlay" @click.self="showList = false">
      <div class="modal-box wide">
        <h3>智能体工作流列表</h3>
        <table class="table">
          <thead><tr><th>ID</th><th>名称</th><th>分类</th><th>节点数</th><th>状态</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="w in workflowList" :key="w.id">
              <td>#{{ w.id }}</td>
              <td>{{ w.name }}</td>
              <td>{{ w.category }}</td>
              <td>{{ (w.nodes || []).length }}</td>
              <td><span class="badge" :class="w.published ? 'en-badge' : 'dis-badge'">{{ w.published ? '已发布' : '草稿' }}</span></td>
              <td><button class="btn btn-sm" @click="loadWorkflow(w.id)">打开</button>
                  <button class="btn btn-sm btn-danger" @click="deleteWorkflow(w)">删除</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 运行测试 -->
    <div v-if="showRun" class="modal-overlay" @click.self="showRun = false">
      <div class="modal-box wide">
        <h3>运行测试 — {{ workflow.name }}</h3>
        <div class="form-row"><label>输入参数 (JSON)</label>
          <textarea v-model="runInputsStr" class="input textarea mono" rows="4" placeholder='{"question": "服务器CPU高怎么办？"}'></textarea>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showRun = false">取消</button>
          <button class="btn btn-primary" @click="executeRun">执行</button>
        </div>
        <div v-if="runResult" class="run-result">
          <div class="detail-label">执行结果</div>
          <div class="run-status">状态: <span class="badge" :class="runStatusClass">{{ runResult.run?.status || runResult.status }}</span></div>
          <pre class="code-block">{{ JSON.stringify(runResult.run?.outputs || runResult.outputs || {}, null, 2) }}</pre>
          <div v-if="runResult.run?.node_runs" class="detail-label">节点执行</div>
          <div v-for="nr in (runResult.run?.node_runs || [])" :key="nr.id" class="run-node-item">
            <span class="badge" :class="runNodeStatusClass(nr.status)">{{ nr.status }}</span>
            <span class="run-node-name">{{ nr.node_name || nr.node_id }}</span>
            <span class="run-node-type">[{{ nr.node_type }}]</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, markRaw, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'
import request from '@/api/request'
import NodeCard from '@/components/AgentWorkflowNodeCard.vue'

const { addEdges, removeNodes, project } = useVueFlow()

const nodeTypes = [
  { type: 'start', label: '开始', icon: '▶', color: '#10b981' },
  { type: 'end', label: '结束', icon: '■', color: '#64748b' },
  { type: 'llm', label: 'LLM 推理', icon: 'AI', color: '#6366f1' },
  { type: 'knowledge', label: '知识库', icon: 'KB', color: '#14b8a6' },
  { type: 'tool', label: '工具调用', icon: '🔧', color: '#f59e0b' },
  { type: 'condition', label: '条件分支', icon: '◆', color: '#ec4899' },
  { type: 'code', label: '代码执行', icon: '</>', color: '#8b5cf6' },
  { type: 'http', label: 'HTTP 请求', icon: '⌘', color: '#06b6d4' },
]
const nodeTypeMap = computed(() => Object.fromEntries(nodeTypes.map(n => [n.type, n])))

const nodes = ref([])
const edges = ref([])
const selectedNode = ref(null)
const workflow = ref({ id: null, name: '新建工作流', category: 'generic', published: false, enabled: true, description: '', trigger_type: 'manual' })
const providers = ref([])
const mcpTools = ref([])
const showList = ref(false)
const workflowList = ref([])
const showRun = ref(false)
const runInputsStr = ref('{}')
const runResult = ref(null)

// 属性面板的 JSON 字符串绑定
const startInputsStr = ref('[]')
const endOutputsStr = ref('[]')
const toolParamsStr = ref('{}')
const branchesStr = ref('[]')
const codeInputsStr = ref('{}')
const httpHeadersStr = ref('{}')
const httpBodyStr = ref('{}')

function onDragStart(event, type) {
  event.dataTransfer.setData('node-type', type)
  event.dataTransfer.effectAllowed = 'move'
}

function onConnect(params) {
  addEdges([{ ...params, animated: true, style: { stroke: '#6366f1', strokeWidth: 2 } }])
}

function onNodeClick({ node }) {
  selectedNode.value = nodes.value.find(n => n.id === node.id) || node
  syncPropsToStr()
}

function onPaneClick() {
  selectedNode.value = null
}

function openEditor(props) {
  onNodeClick(props)
}

function syncPropsToStr() {
  if (!selectedNode.value) return
  const d = selectedNode.value.data || {}
  startInputsStr.value = JSON.stringify(d.inputs || [], null, 2)
  endOutputsStr.value = JSON.stringify(d.outputs || [], null, 2)
  toolParamsStr.value = JSON.stringify(d.parameters || {}, null, 2)
  branchesStr.value = JSON.stringify(d.branches || [], null, 2)
  codeInputsStr.value = JSON.stringify(d.inputs_mapping || {}, null, 2)
  httpHeadersStr.value = JSON.stringify(d.headers || {}, null, 2)
  httpBodyStr.value = JSON.stringify(d.body || {}, null, 2)
}

function syncStrToProps() {
  if (!selectedNode.value) return
  const d = selectedNode.value.data || (selectedNode.value.data = {})
  try { d.inputs = JSON.parse(startInputsStr.value || '[]') } catch {}
  try { d.outputs = JSON.parse(endOutputsStr.value || '[]') } catch {}
  try { d.parameters = JSON.parse(toolParamsStr.value || '{}') } catch {}
  try { d.branches = JSON.parse(branchesStr.value || '[]') } catch {}
  try { d.inputs_mapping = JSON.parse(codeInputsStr.value || '{}') } catch {}
  try { d.headers = JSON.parse(httpHeadersStr.value || '{}') } catch {}
  try { d.body = JSON.parse(httpBodyStr.value || '{}') } catch {}
}

function deleteNode() {
  if (!selectedNode.value) return
  nodes.value = nodes.value.filter(n => n.id !== selectedNode.value.id)
  edges.value = edges.value.filter(e => e.source !== selectedNode.value.id && e.target !== selectedNode.value.id)
  selectedNode.value = null
}

// 画布拖放
function onCanvasDrop(event) {
  event.preventDefault()
  const type = event.dataTransfer.getData('node-type')
  if (!type) return
  const rect = event.currentTarget.getBoundingClientRect()
  const position = { x: event.clientX - rect.left, y: event.clientY - rect.top }
  const nt = nodeTypes.find(n => n.type === type)
  const nodeId = type + '_' + Date.now().toString(36)
  const defaultData = getDefaultData(type)
  nodes.value.push({
    id: nodeId,
    type: type,
    position,
    data: { label: nt.label, ...defaultData },
  })
}

function getDefaultData(type) {
  switch (type) {
    case 'start': return { inputs: [] }
    case 'end': return { outputs: [] }
    case 'llm': return { provider_id: null, model: '', system_prompt: '', user_prompt: '', temperature: 0.3, max_tokens: 2000 }
    case 'knowledge': return { query: '', kb_id: 1, top_k: 5, score_threshold: 0.5 }
    case 'tool': return { tool_name: '', parameters: {} }
    case 'condition': return { branches: [] }
    case 'code': return { code: 'result = {}', inputs_mapping: {} }
    case 'http': return { method: 'GET', url: '', headers: {}, body: {}, timeout: 10 }
    default: return {}
  }
}

async function loadProviders() {
  try {
    const data = await request.get('/ai-providers/api/list')
    providers.value = data.items || data || []
  } catch (e) { console.error('load providers:', e) }
}

async function loadMcpTools() {
  try {
    const data = await request.get('/agent/api/tools')
    mcpTools.value = data.tools || data || []
  } catch (e) {
    // 降级：硬编码常用工具
    mcpTools.value = ['query_alerts', 'query_metrics', 'query_logs', 'query_knowledge_rag', 'query_assets', 'query_k8s', 'query_incidents', 'query_changes', 'execute_run_command', 'execute_restart_service', 'execute_clean_disk', 'execute_resolve_alert', 'execute_acknowledge_alert', 'propose_action', 'propose_workflow', 'list_workflow_templates', 'list_agent_workflows', 'run_agent_workflow']
  }
}

function newWorkflow() {
  workflow.value = { id: null, name: '新建工作流', category: 'generic', published: false, enabled: true, description: '', trigger_type: 'manual' }
  nodes.value = [
    { id: 'start', type: 'start', position: { x: 80, y: 200 }, data: { label: '开始', inputs: [] } },
    { id: 'end', type: 'end', position: { x: 600, y: 200 }, data: { label: '结束', outputs: [] } },
  ]
  edges.value = [{ id: 'e-start-end', source: 'start', target: 'end', animated: true, style: { stroke: '#6366f1', strokeWidth: 2 } }]
  selectedNode.value = null
}

async function loadList() {
  try {
    const data = await request.get('/agent-workflow/api/workflows')
    workflowList.value = data.items || []
    showList.value = true
  } catch (e) {
    ElMessage.error('加载列表失败: ' + (e.message || e))
  }
}

async function loadWorkflow(id) {
  try {
    const w = await request.get(`/agent-workflow/api/workflows/${id}`)
    workflow.value = { id: w.id, name: w.name, category: w.category, published: w.published, enabled: w.enabled, description: w.description, trigger_type: w.trigger_type }
    // 转换节点格式：后端 nodes 是 [{id, type, name, data}]，Vue Flow 需要 {id, type, position, data:{label}}
    nodes.value = (w.nodes || []).map(n => ({
      id: n.id,
      type: n.type,
      position: n.position || { x: 100 + Math.random() * 400, y: 50 + Math.random() * 300 },
      data: { label: n.name || n.data?.label || n.type, ...(n.data || {}) },
    }))
    edges.value = (w.edges || []).map(e => ({
      id: `e-${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      animated: true,
      style: { stroke: '#6366f1', strokeWidth: 2 },
    }))
    showList.value = false
    ElMessage.success('已加载: ' + w.name)
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.message || e))
  }
}

async function autoSave() {
  syncStrToProps()
  if (!workflow.value.name) {
    ElMessage.warning('请输入工作流名称')
    return
  }
  const payload = {
    name: workflow.value.name,
    category: workflow.value.category,
    description: workflow.value.description,
    enabled: workflow.value.enabled,
    trigger_type: workflow.value.trigger_type,
    nodes: nodes.value.map(n => ({ id: n.id, type: n.type, name: n.data.label, data: n.data, position: n.position })),
    edges: edges.value.map(e => ({ source: e.source, target: e.target })),
  }
  try {
    if (workflow.value.id) {
      await request.post(`/agent-workflow/api/workflows/${workflow.value.id}/update`, payload)
    } else {
      const data = await request.post('/agent-workflow/api/workflows/create', payload)
      workflow.value.id = data.id
    }
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.message || e))
  }
}

async function publishWorkflow() {
  await autoSave()
  try {
    await request.post(`/agent-workflow/api/workflows/${workflow.value.id}/update`, { published: !workflow.value.published })
    workflow.value.published = !workflow.value.published
    ElMessage.success(workflow.value.published ? '已发布' : '已取消发布')
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.message || e))
  }
}

async function deleteWorkflow(w) {
  try {
    await ElMessageBox.confirm(`删除工作流「${w.name}」？`, '删除确认', { type: 'warning' })
    await request.post(`/agent-workflow/api/workflows/${w.id}/delete`)
    ElMessage.success('已删除')
    loadList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

function runTest() {
  if (!workflow.value.id) {
    ElMessage.warning('请先保存工作流')
    return
  }
  // 生成输入参数模板
  const startNode = nodes.value.find(n => n.type === 'start')
  const inputs = {}
  if (startNode?.data?.inputs) {
    for (const inp of startNode.data.inputs) {
      if (inp.type === 'integer') inputs[inp.key] = 1
      else if (inp.type === 'object') inputs[inp.key] = {}
      else inputs[inp.key] = ''
    }
  }
  runInputsStr.value = JSON.stringify(inputs, null, 2)
  runResult.value = null
  showRun.value = true
}

async function executeRun() {
  let inputs
  try { inputs = JSON.parse(runInputsStr.value || '{}') } catch (e) {
    ElMessage.warning('输入 JSON 格式错误')
    return
  }
  try {
    const data = await request.post(`/agent-workflow/api/runs/${workflow.value.id}/execute`, { inputs })
    runResult.value = data
    if (data.run?.status === 'completed') {
      ElMessage.success('执行完成')
    } else if (data.run?.status === 'failed') {
      ElMessage.error('执行失败: ' + (data.run.error || ''))
    }
  } catch (e) {
    ElMessage.error('执行失败: ' + (e.message || e))
  }
}

function runStatusClass() {
  const s = runResult.value?.run?.status
  return { 'st-completed': s === 'completed', 'st-failed': s === 'failed', 'st-running': s === 'running' }
}
function runNodeStatusClass(s) {
  return { 'st-completed': s === 'completed', 'st-failed': s === 'failed', 'st-running': s === 'running', 'st-skipped': s === 'skipped' }
}

onMounted(() => {
  newWorkflow()
  loadProviders()
  loadMcpTools()
  // 监听画布拖放
  nextTick(() => {
    const canvas = document.querySelector('.canvas-wrapper')
    if (canvas) {
      canvas.addEventListener('dragover', e => e.preventDefault())
      canvas.addEventListener('drop', onCanvasDrop)
    }
  })
})
</script>

<style scoped>
.awf-page { display: flex; flex-direction: column; height: calc(100vh - 60px); padding: 4px; }
.awf-header { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; margin-bottom: 8px; }
.awf-title { display: flex; align-items: center; gap: 10px; }
.title-input { font-size: 1.1rem; font-weight: 600; border: none; background: transparent; color: var(--text, #1e293b); outline: none; min-width: 200px; }
.title-input:focus { border-bottom: 1px solid var(--accent, #6366f1); }
.wf-status-badge { padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.wf-status-badge.published { background: rgba(16,185,129,0.12); color: #10b981; }
.wf-status-badge.draft { background: rgba(100,116,139,0.12); color: #64748b; }
.awf-toolbar { display: flex; gap: 6px; }
.btn { padding: 5px 12px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.8rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-success { background: rgba(16,185,129,0.9); color: #fff; border-color: rgba(16,185,129,0.9); }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-sm { padding: 3px 8px; font-size: 0.72rem; }
.awf-body { display: flex; gap: 8px; flex: 1; min-height: 0; }
.node-panel { width: 180px; background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; padding: 12px; overflow-y: auto; }
.panel-title { font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); text-transform: uppercase; letter-spacing: 0.3px; margin-bottom: 8px; }
.node-list { display: flex; flex-direction: column; gap: 6px; }
.node-item { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 6px; cursor: grab; font-size: 0.82rem; transition: all 0.15s; }
.node-item:hover { border-color: var(--accent, #6366f1); background: rgba(99,102,241,0.05); }
.node-item:active { cursor: grabbing; }
.node-icon { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 5px; color: #fff; font-size: 0.7rem; font-weight: 600; }
.node-label { color: var(--text, #1e293b); }
.help-text { font-size: 0.72rem; color: var(--text-tertiary, #94a3b8); line-height: 1.6; }
.canvas-wrapper { flex: 1; border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; overflow: hidden; position: relative; background: #f8fafc; }
.vue-flow-canvas { width: 100%; height: 100%; }
.props-panel { width: 320px; background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; display: flex; flex-direction: column; overflow: hidden; }
.props-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); background: var(--bg-hover, rgba(0,0,0,0.03)); }
.props-title { font-weight: 600; font-size: 0.88rem; color: var(--text, #1e293b); }
.props-body { padding: 12px 14px; overflow-y: auto; flex: 1; }
.form-row { margin-bottom: 10px; }
.form-row label { display: block; font-size: 0.76rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 5px 9px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 5px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.8rem; box-sizing: border-box; }
.textarea { resize: vertical; font-family: inherit; }
.textarea.mono { font-family: 'Consolas', monospace; font-size: 0.75rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 380px; max-width: 90vw; max-height: 90vh; overflow-y: auto; box-shadow: 0 8px 24px rgba(0,0,0,0.15); }
.modal-box.wide { min-width: 560px; }
.modal-box h3 { margin: 0 0 16px; font-size: 1rem; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 8px 10px; font-size: 0.72rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); }
.table td { padding: 8px 10px; font-size: 0.82rem; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.en-badge { background: rgba(16,185,129,0.12); color: #10b981; }
.badge.dis-badge { background: rgba(100,116,139,0.12); color: #64748b; }
.badge.st-completed { background: rgba(16,185,129,0.12); color: #10b981; }
.badge.st-failed { background: rgba(239,68,68,0.12); color: #ef4444; }
.badge.st-running { background: rgba(99,102,241,0.12); color: #6366f1; }
.badge.st-skipped { background: rgba(100,116,139,0.12); color: #64748b; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
.run-result { margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border, rgba(0,0,0,0.07)); }
.run-status { margin-bottom: 8px; font-size: 0.85rem; }
.code-block { background: rgba(0,0,0,0.04); border-radius: 6px; padding: 8px 10px; font-size: 0.75rem; font-family: 'Consolas', monospace; white-space: pre-wrap; word-break: break-all; margin: 4px 0 12px; max-height: 200px; overflow-y: auto; }
.run-node-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 0.8rem; }
.run-node-name { font-weight: 500; }
.run-node-type { color: var(--text-tertiary, #94a3b8); font-size: 0.72rem; }
</style>
