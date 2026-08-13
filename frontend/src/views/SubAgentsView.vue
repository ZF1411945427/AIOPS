<template>
  <div class="sa-page">
    <div class="page-header">
      <h1>子智能体管理</h1>
      <p>Multi-Agent Orchestration — 按域分派的专家 Agent 配置（SRE / 网络 / 数据库 / 中间件 / K8s）</p>
    </div>

    <div v-if="loading" class="loading-state">加载中...</div>

    <template v-else>
      <div class="sa-overview">
        <div class="ov-card">
          <div class="ov-title">子专家概览</div>
          <div class="ov-row"><span class="ov-label">总数</span><span class="ov-val">{{ agents.length }}</span></div>
          <div class="ov-row"><span class="ov-label">启用</span><span class="ov-val">{{ enabledCount }}</span></div>
          <div class="ov-row"><span class="ov-label">预置</span><span class="ov-val">{{ presetCount }}</span></div>
        </div>
        <div class="ov-card">
          <div class="ov-title">路由测试</div>
          <div class="route-test">
            <input v-model="testMessage" class="route-input" placeholder="输入测试消息，如：mysql 慢查询怎么排查" @keyup.enter="testRoute" />
            <button class="route-btn" @click="testRoute">路由</button>
          </div>
          <div v-if="routeResult" class="route-result">
            <span class="route-icon">{{ routeResult.icon }}</span>
            <span class="route-name" :style="{color: routeResult.color}">{{ routeResult.display_name }}</span>
            <span v-if="routeResult.hit_keywords.length" class="route-hits">命中: {{ routeResult.hit_keywords.join(', ') }}</span>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <span>子专家清单 ({{ agents.length }})</span>
          <button class="action-btn" @click="reseed">🔄 重新播种预置</button>
        </div>
        <div class="panel-body">
          <div v-for="a in agents" :key="a.id" class="sa-card" :style="{ borderLeftColor: a.color }">
            <div class="sa-card-head">
              <span class="sa-icon">{{ a.icon }}</span>
              <span class="sa-name">{{ a.display_name }}</span>
              <span class="sa-domain-badge" :style="{ background: a.color + '22', color: a.color }">{{ a.domain }}</span>
              <span v-if="!a.is_enabled" class="sa-disabled">已禁用</span>
              <span class="sa-tools">{{ a.tool_whitelist.length ? a.tool_whitelist.length + ' 工具' : '继承全部' }}</span>
              <button class="edit-btn" @click="openEdit(a)">✎ 编辑</button>
            </div>
            <div class="sa-desc">{{ a.description }}</div>
            <div class="sa-keywords">
              <span class="kw-label">路由关键词：</span>
              <span v-for="kw in a.keywords" :key="kw" class="kw-chip">{{ kw }}</span>
              <span v-if="!a.keywords.length" class="kw-empty">无（通用助手）</span>
            </div>
            <details class="sa-details">
              <summary>查看 System Prompt 与工具白名单</summary>
              <div class="sa-prompt">
                <div class="prompt-label">System Prompt：</div>
                <pre class="prompt-text">{{ a.system_prompt || '(空 — 使用默认)' }}</pre>
              </div>
              <div class="sa-tools-list">
                <div class="prompt-label">工具白名单 ({{ a.tool_whitelist.length }})：</div>
                <div class="tools-chips">
                  <span v-for="t in a.tool_whitelist" :key="t" class="tool-chip">{{ t }}</span>
                  <span v-if="!a.tool_whitelist.length" class="kw-empty">空 — 继承全部 45 个工具</span>
                </div>
              </div>
            </details>
          </div>
        </div>
      </div>
    </template>
  </div>

  <!-- 编辑子智能体对话框 -->
  <div v-if="showForm" class="mask" @click.self="showForm = false">
    <div class="dialog">
      <div class="dialog-head">
        <h3>编辑子智能体 — {{ editingAgent?.display_name }}</h3>
        <button class="close-btn" @click="showForm = false">✕</button>
      </div>
      <div class="dialog-body">
        <div class="field"><label>显示名称</label><input v-model="form.display_name" class="input" /></div>
        <div class="field"><label>描述</label><input v-model="form.description" class="input" /></div>
        <div class="field-row">
          <div class="field" style="flex:0 0 60px"><label>图标</label><input v-model="form.icon" class="input" style="width:50px" /></div>
          <div class="field" style="flex:0 0 70px"><label>颜色</label><input v-model="form.color" type="color" class="input" style="width:60px;padding:2px" /></div>
          <div class="field" style="flex:0 0 80px"><label>排序</label><input v-model.number="form.sort_order" type="number" class="input" style="width:60px" /></div>
          <div class="field" style="flex:0"><label class="checkbox-label">
            <input type="checkbox" v-model="form.is_enabled" /> 启用
          </label></div>
        </div>
        <div class="field"><label>路由关键词（逗号分隔）</label>
          <input v-model="form.keywordsText" class="input" placeholder="如：mysql, 慢查询, 锁" />
        </div>
        <div class="field"><label>System Prompt</label>
          <textarea v-model="form.system_prompt" class="textarea" rows="6" placeholder="子专家身份提示词"></textarea>
        </div>
        <div class="field"><label>工具白名单（点击切换，空=继承全部）</label>
          <div class="tool-picker" v-if="allTools.length">
            <span v-for="t in allTools" :key="t.name" class="tool-item"
              :class="{ active: form.tool_whitelist.includes(t.name) }"
              @click="toggleTool(t.name)">{{ t.display_name || t.name }}</span>
          </div>
          <div v-else class="loading" style="font-size:12px;color:#888">加载工具清单中...</div>
        </div>
      </div>
      <div class="dialog-actions">
        <button class="btn-plain" @click="showForm = false">取消</button>
        <button class="btn-primary" :disabled="saving" @click="saveAgent">{{ saving ? '保存中...' : '保存' }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(true)
const agents = ref([])
const testMessage = ref('')
const routeResult = ref(null)
const showForm = ref(false)
const editingAgent = ref(null)
const saving = ref(false)
const allTools = ref([])
const form = ref({
  display_name: '', description: '', icon: '🤖', color: '#6366f1',
  sort_order: 0, is_enabled: true,
  system_prompt: '', keywordsText: '', tool_whitelist: [],
})

const enabledCount = computed(() => agents.value.filter(a => a.is_enabled).length)
const presetCount = computed(() => agents.value.filter(a => ['general','sre_expert','network_expert','database_expert','middleware_expert','k8s_expert'].includes(a.name)).length)

async function load() {
  try {
    const data = await request.get('/agent/sub-agents')
    agents.value = data.sub_agents || []
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

async function loadTools() {
  try {
    const data = await request.get('/agent/api/capabilities')
    const tools = data.tools || data || []
    allTools.value = tools.filter(t => t.expose_to_llm !== false)
  } catch (e) { allTools.value = [] }
}

function openEdit(a) {
  editingAgent.value = a
  form.value = {
    display_name: a.display_name,
    description: a.description || '',
    icon: a.icon || '🤖',
    color: a.color || '#6366f1',
    sort_order: a.sort_order || 0,
    is_enabled: a.is_enabled !== false,
    system_prompt: a.system_prompt || '',
    keywordsText: (a.keywords || []).join(', '),
    tool_whitelist: [...(a.tool_whitelist || [])],
  }
  showForm.value = true
}

function toggleTool(name) {
  const idx = form.value.tool_whitelist.indexOf(name)
  if (idx >= 0) form.value.tool_whitelist.splice(idx, 1)
  else form.value.tool_whitelist.push(name)
}

async function saveAgent() {
  if (!editingAgent.value) return
  saving.value = true
  try {
    const payload = {
      display_name: form.value.display_name,
      description: form.value.description,
      icon: form.value.icon,
      color: form.value.color,
      sort_order: form.value.sort_order,
      is_enabled: form.value.is_enabled,
      system_prompt: form.value.system_prompt,
      keywords: form.value.keywordsText.split(',').map(k => k.trim()).filter(Boolean),
      tool_whitelist: form.value.tool_whitelist,
    }
    await request.put('/agent/sub-agents/' + editingAgent.value.id + '/edit', payload)
    ElMessage.success('保存成功')
    showForm.value = false
    await load()
  } catch (e) { ElMessage.error('保存失败: ' + (e.message || e)) }
  finally { saving.value = false }
}

async function testRoute() {
  if (!testMessage.value.trim()) return
  try {
    const data = await request.post('/agent/sub-agents/route', { message: testMessage.value })
    routeResult.value = data
  } catch (e) { ElMessage.error('路由测试失败') }
}

async function reseed() {
  try {
    const data = await request.post('/agent/sub-agents/seed')
    ElMessage.success(data.message || '已重新播种')
    await load()
  } catch (e) { ElMessage.error('重新播种失败') }
}

onMounted(() => { load(); loadTools() })
</script>

<style scoped>
.sa-page { padding: 20px; }
.page-header { margin-bottom: 24px; }
.page-header h1 { font-size: 1.4rem; font-weight: 700; margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #888); font-size: 0.85rem; margin: 0; }
.loading-state { text-align: center; padding: 60px; color: var(--text-secondary, #888); }

.sa-overview { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }
.ov-card { background: var(--bg-card, #fff); border: 1px solid var(--border, #e5e7eb); border-radius: 10px; padding: 20px; }
.ov-title { font-size: 0.9rem; font-weight: 600; margin-bottom: 14px; }
.ov-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border-light, #f0f0f0); font-size: 0.82rem; }
.ov-label { color: var(--text-secondary, #888); }
.ov-val { font-weight: 600; }

.route-test { display: flex; gap: 8px; margin-bottom: 12px; }
.route-input { flex: 1; padding: 8px 12px; border: 1px solid var(--border, #d1d5db); border-radius: 6px; font-size: 0.82rem; }
.route-btn { padding: 8px 18px; background: #6366f1; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 0.82rem; font-weight: 600; }
.route-btn:hover { background: #4f46e5; }
.route-result { display: flex; align-items: center; gap: 8px; padding: 10px 12px; background: #f8fafc; border-radius: 6px; font-size: 0.82rem; }
.route-icon { font-size: 1.2rem; }
.route-name { font-weight: 600; }
.route-hits { color: var(--text-secondary, #64748b); font-size: 0.75rem; }

.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, #e5e7eb); border-radius: 10px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; padding: 14px 20px; border-bottom: 1px solid var(--border, #e5e7eb); font-weight: 600; font-size: 0.9rem; }
.action-btn { padding: 6px 14px; background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 6px; cursor: pointer; font-size: 0.78rem; }
.action-btn:hover { background: #e2e8f0; }
.panel-body { padding: 16px 20px; }

.sa-card { background: #fafbfc; border: 1px solid #e5e7eb; border-left: 4px solid #6366f1; border-radius: 8px; padding: 14px 16px; margin-bottom: 12px; }
.sa-card-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
.sa-icon { font-size: 1.3rem; }
.sa-name { font-size: 0.95rem; font-weight: 600; color: #1e293b; }
.sa-domain-badge { font-size: 0.7rem; padding: 2px 10px; border-radius: 10px; font-weight: 600; }
.sa-disabled { font-size: 0.7rem; padding: 2px 8px; border-radius: 10px; background: #f3f4f6; color: #6b7280; }
.sa-tools { margin-left: auto; font-size: 0.72rem; color: var(--text-secondary, #64748b); background: #f1f5f9; padding: 2px 10px; border-radius: 10px; }
.edit-btn { font-size: 0.72rem; padding: 2px 10px; border: 1px solid var(--border-color,#d1d5db); border-radius: 6px; background: transparent; cursor: pointer; color: #6366f1; }
.sa-desc { font-size: 0.82rem; color: var(--text-secondary, #64748b); margin-bottom: 10px; line-height: 1.5; }
.sa-keywords { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
.kw-label { font-size: 0.75rem; color: var(--text-secondary, #94a3b8); font-weight: 600; }
.kw-chip { font-size: 0.72rem; padding: 2px 8px; border-radius: 10px; background: #e0f2fe; color: #075985; }
.kw-empty { font-size: 0.75rem; color: var(--text-secondary, #94a3b8); font-style: italic; }
.sa-details { margin-top: 8px; }
.sa-details summary { cursor: pointer; font-size: 0.78rem; color: #6366f1; font-weight: 600; padding: 4px 0; }
.sa-prompt { margin-top: 10px; }
.prompt-label { font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); margin-bottom: 6px; }
.prompt-text { background: #1e293b; color: #e2e8f0; padding: 12px; border-radius: 6px; font-size: 0.75rem; white-space: pre-wrap; line-height: 1.5; margin: 0 0 12px; font-family: 'Fira Code', monospace; }
.sa-tools-list { margin-top: 8px; }
.tools-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.tool-chip { font-size: 0.7rem; padding: 2px 8px; border-radius: 10px; background: #dcfce7; color: #166534; font-family: 'Fira Code', monospace; }

.mask { position: fixed; inset: 0; background: rgba(0,0,0,.35); display: flex; align-items: flex-start; justify-content: center; padding-top: 40px; z-index: 100; }
.dialog { background: var(--card-bg,#fff); border-radius: 10px; min-width: 600px; max-width: 800px; max-height: 85vh; overflow-y: auto; box-shadow: 0 8px 30px rgba(0,0,0,.15); }
.dialog-head { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border-color,#e5e7eb); }
.dialog-head h3 { margin: 0; font-size: 15px; }
.close-btn { background: none; border: none; font-size: 18px; cursor: pointer; color: #888; padding: 0 4px; }
.dialog-body { padding: 16px 20px; }
.field { margin-bottom: 12px; }
.field label { display: block; font-size: 12px; color: var(--text-muted,#888); margin-bottom: 4px; font-weight: 600; }
.field-row { display: flex; gap: 12px; align-items: flex-end; }
.checkbox-label { display: flex !important; align-items: center; gap: 6px; cursor: pointer; padding-bottom: 8px; }
.input { width: 100%; padding: 7px 10px; border: 1px solid var(--border-color,#d1d5db); border-radius: 6px; background: var(--input-bg,#fff); color: var(--text,#1e293b); font-size: 13px; box-sizing: border-box; }
.textarea { width: 100%; padding: 7px 10px; border: 1px solid var(--border-color,#d1d5db); border-radius: 6px; background: var(--input-bg,#fff); color: var(--text,#1e293b); font-size: 13px; box-sizing: border-box; resize: vertical; font-family: inherit; }
.tool-picker { display: flex; flex-wrap: wrap; gap: 4px; max-height: 180px; overflow-y: auto; border: 1px solid var(--border-color,#e5e7eb); border-radius: 6px; padding: 6px; }
.tool-item { font-size: 0.72rem; padding: 3px 8px; border-radius: 10px; background: #f1f5f9; color: #475569; cursor: pointer; border: 1px solid transparent; transition: all .12s; }
.tool-item:hover { background: #e2e8f0; }
.tool-item.active { background: #dbeafe; color: #1e40af; border-color: #93c5fd; }
.dialog-actions { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 20px; border-top: 1px solid var(--border-color,#e5e7eb); }
.btn-primary { padding: 7px 18px; border: none; border-radius: 6px; background: var(--primary,#6366f1); color: #fff; cursor: pointer; font-size: 13px; font-weight: 500; }
.btn-primary:disabled { opacity: .5; cursor: not-allowed; }
.btn-plain { padding: 6px 14px; border: 1px solid var(--border-color,#d1d5db); border-radius: 6px; background: transparent; color: var(--text,#1e293b); cursor: pointer; font-size: 13px; }

@media (max-width: 900px) {
  .sa-overview { grid-template-columns: 1fr; }
}
</style>
