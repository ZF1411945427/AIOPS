<template>
  <div class="inspection-page">
    <div class="page-header">
      <div class="title-row">
        <div>
          <h1>🔍 智能巡检</h1>
          <p>AI 驱动的多维资产健康巡检 · 指标/告警/链路全量采集 · 智能分析报告</p>
        </div>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-icon" style="background:linear-gradient(135deg,#667eea,#764ba2)">📋</div>
        <div class="stat-info"><div class="stat-value">{{ stats.total_tasks }}</div><div class="stat-label">巡检任务</div></div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background:linear-gradient(135deg,#f093fb,#f5576c)">🚀</div>
        <div class="stat-info"><div class="stat-value">{{ stats.total_records }}</div><div class="stat-label">执行次数</div></div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background:linear-gradient(135deg,#4facfe,#00f2fe)">📊</div>
        <div class="stat-info"><div class="stat-value">{{ stats.avg_score }}<span style="font-size:14px">分</span></div><div class="stat-label">平均健康评分</div></div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background:linear-gradient(135deg,#43e97b,#38f9d7)">🤖</div>
        <div class="stat-info"><div class="stat-value">AI</div><div class="stat-label">智能分析引擎</div></div>
      </div>
    </div>

    <!-- Tab 切换 -->
    <div class="tab-bar">
      <div class="tab-item" :class="{ active: activeTab === 'tasks' }" @click="activeTab = 'tasks'">巡检任务</div>
      <div class="tab-item" :class="{ active: activeTab === 'templates' }" @click="activeTab = 'templates'">巡检模板</div>
      <div class="tab-item" :class="{ active: activeTab === 'records' }" @click="activeTab = 'records'">执行记录</div>
    </div>

    <!-- ═══════ 巡检任务 Tab ═══════ -->
    <div v-show="activeTab === 'tasks'">
      <div class="toolbar">
        <button class="btn btn-primary" @click="openCreateTask">+ 新建巡检任务</button>
        <button class="btn" @click="loadTasks">刷新</button>
      </div>
      <div class="panel">
        <div class="panel-body">
          <div v-if="loadingTasks" class="loading-state">加载中...</div>
          <table v-else-if="tasks.length" class="table">
            <thead>
              <tr>
                <th>任务名称</th><th>巡检模板</th><th>资产范围</th><th>AI分析</th><th>状态</th><th>上次执行</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in tasks" :key="t.id">
                <td><strong>{{ t.name }}</strong></td>
                <td>{{ getTemplateName(t.template_id) }}</td>
                <td>
                  <span class="badge info" v-if="t.scope_type === 'manual'">手动选择 ({{ t.asset_ids.length }}个)</span>
                  <span class="badge warning" v-else>动态范围</span>
                </td>
                <td><span class="badge" :class="t.ai_analysis ? 'resolved' : 'info'">{{ t.ai_analysis ? 'AI 分析' : '规则检查' }}</span></td>
                <td>
                  <span v-if="t.status === 'running'" class="badge running">执行中...</span>
                  <span v-else class="badge idle">空闲</span>
                </td>
                <td class="text-sm">{{ t.last_run_at ? formatTime(t.last_run_at) : '从未执行' }}</td>
                <td>
                  <button class="btn btn-sm btn-success" @click="runTask(t)" :disabled="t.status === 'running'">
                    {{ t.status === 'running' ? '执行中...' : '▶ 执行' }}
                  </button>
                  <button class="btn btn-sm" @click="openEditTask(t)">编辑</button>
                  <button class="btn btn-sm btn-danger" @click="deleteTask(t)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-state">
            <div style="font-size:48px;margin-bottom:12px">🔍</div>
            <div>暂无巡检任务</div>
            <p style="color:var(--text-muted);margin-top:8px">创建任务选择资产范围，AI 将自动采集多维数据并生成巡检报告</p>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══════ 巡检模板 Tab ═══════ -->
    <div v-show="activeTab === 'templates'">
      <div class="toolbar">
        <button class="btn btn-primary" @click="openCreateTemplate">+ 新建模板</button>
      </div>
      <div class="template-grid">
        <div v-for="tpl in templates" :key="tpl.id" class="template-card">
          <div class="template-header">
            <h3>{{ tpl.name }}</h3>
            <span class="badge" :class="tpl.enabled ? 'resolved' : 'info'">{{ tpl.enabled ? '启用' : '停用' }}</span>
          </div>
          <p class="template-desc">{{ tpl.description }}</p>
          <div class="template-meta">
            <span>🎯 {{ tpl.target_ci_types.map(t => CI_LABELS[t] || t).join(', ') }}</span>
            <span>📋 {{ tpl.check_items.length }} 个检查项</span>
          </div>
          <div class="template-items">
            <div v-for="(item, idx) in tpl.check_items.slice(0, 3)" :key="idx" class="check-item">
              <span class="check-name">{{ item.name }}</span>
              <span class="check-threshold">{{ item.threshold }}{{ item.unit }}</span>
            </div>
            <div v-if="tpl.check_items.length > 3" class="check-more">+{{ tpl.check_items.length - 3 }} 项...</div>
          </div>
          <div class="template-actions">
            <button class="btn btn-sm" @click="openEditTemplate(tpl)">编辑</button>
            <button class="btn btn-sm btn-danger" @click="deleteTemplate(tpl)">删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══════ 执行记录 Tab ═══════ -->
    <div v-show="activeTab === 'records'">
      <div class="toolbar">
        <button class="btn" @click="loadRecords">刷新</button>
      </div>
      <div class="panel">
        <div class="panel-body">
          <div v-if="!records.length" class="empty-state">
            <div style="font-size:48px;margin-bottom:12px">📭</div>
            <div>暂无执行记录</div>
          </div>
          <div v-else>
            <div v-for="r in records" :key="r.id" class="record-card" @click="viewRecord(r)">
              <div class="record-header">
                <div class="record-score" :class="scoreClass(r.overall_score)">
                  {{ r.overall_score }}<span>分</span>
                </div>
                <div class="record-info">
                  <h4>任务 #{{ r.task_id }} · {{ formatTime(r.started_at) }}</h4>
                  <p>{{ r.checked_assets }} 个资产 · 耗时 {{ r.duration_seconds.toFixed(1) }}s</p>
                </div>
                <div class="record-badges">
                  <span class="badge resolved">✅ {{ r.normal_count }}</span>
                  <span class="badge warning" v-if="r.warning_count">⚠️ {{ r.warning_count }}</span>
                  <span class="badge critical" v-if="r.critical_count">🔴 {{ r.critical_count }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══════ 巡检报告抽屉 ═══════ -->
    <div v-if="showReport" class="drawer-overlay" @click.self="showReport = false">
      <div class="drawer report-drawer">
        <div class="drawer-header">
          <h2>🤖 AI 巡检报告</h2>
          <button class="modal-close" @click="showReport = false">×</button>
        </div>
        <div class="drawer-body">
          <div v-if="currentRecord" class="report-content">
            <div class="report-summary">
              <div class="report-score" :class="scoreClass(currentRecord.overall_score)">
                {{ currentRecord.overall_score }}<span>分</span>
              </div>
              <div class="report-meta">
                <div>📊 巡检资产: {{ currentRecord.checked_assets }} 个</div>
                <div>⏱️ 耗时: {{ currentRecord.duration_seconds.toFixed(1) }} 秒</div>
                <div>🕐 完成时间: {{ formatTime(currentRecord.finished_at) }}</div>
              </div>
            </div>

            <div class="report-badges">
              <span class="badge resolved" style="font-size:14px;padding:8px 16px">✅ 正常 {{ currentRecord.normal_count }}</span>
              <span class="badge warning" style="font-size:14px;padding:8px 16px" v-if="currentRecord.warning_count">⚠️ 警告 {{ currentRecord.warning_count }}</span>
              <span class="badge critical" style="font-size:14px;padding:8px 16px" v-if="currentRecord.critical_count">🔴 严重 {{ currentRecord.critical_count }}</span>
            </div>

            <div v-if="currentRecord.ai_report" class="ai-report">
              <h3>🤖 AI 分析报告</h3>
              <div class="report-markdown" v-html="renderMarkdown(currentRecord.ai_report)"></div>
            </div>

            <div v-if="currentRecord.item_results.length" class="detail-section">
              <h3>📋 逐项检查详情</h3>
              <div v-for="(item, idx) in currentRecord.item_results" :key="idx" class="asset-check-group">
                <div class="asset-check-header" :class="'border-' + item.worst_status">
                  <span class="asset-check-name">{{ item.asset_name }}</span>
                  <span class="asset-check-type">{{ item.ci_type }} · {{ item.ip }}</span>
                  <span class="badge" :class="item.worst_status === 'critical' ? 'critical' : item.worst_status === 'warning' ? 'warning' : 'resolved'">
                    {{ item.worst_status === 'critical' ? '严重' : item.worst_status === 'warning' ? '警告' : '正常' }}
                  </span>
                </div>
                <div class="check-list">
                  <div v-for="(c, ci) in item.checks" :key="ci" class="check-row" :class="'status-' + c.status">
                    <span class="check-icon">{{ c.status === 'critical' ? '🔴' : c.status === 'warning' ? '🟡' : '✅' }}</span>
                    <span class="check-label">{{ c.name }}</span>
                    <span class="check-value">{{ c.value !== null ? c.value + (c.unit || '') : '-' }}</span>
                    <span class="check-detail">{{ c.detail }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══════ 新建/编辑模板弹窗 ═══════ -->
    <div v-if="showTemplateDialog" class="modal-overlay" @click.self="showTemplateDialog = false">
      <div class="modal-box" style="max-width:720px">
        <div class="modal-header">
          <h3>{{ editingTemplate ? '编辑模板' : '新建模板' }}</h3>
          <button class="modal-close" @click="showTemplateDialog = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>模板名称 *</label>
            <input v-model="tplForm.name" placeholder="如：服务器健康巡检" />
          </div>
          <div class="form-group">
            <label>描述</label>
            <input v-model="tplForm.description" placeholder="模板功能说明" />
          </div>
          <div class="form-group">
            <label>目标 CI 类型（多选）</label>
            <div class="ci-type-grid">
              <label v-for="cit in CI_TYPES" :key="cit" class="ci-type-label">
                <input type="checkbox" :value="cit" v-model="tplForm.target_ci_types" /> {{ CI_LABELS[cit] || cit }}
              </label>
            </div>
          </div>
          <div class="form-group">
            <label>检查项</label>
            <div class="check-items-editor">
              <div class="check-item-header">
                <span>检查项名称</span><span>指标名</span><span>阈值</span><span>单位</span><span>严重度</span><span></span>
              </div>
              <div v-for="(item, idx) in tplForm.check_items" :key="idx" class="check-item-row">
                <input v-model="item.name" placeholder="如：CPU 使用率" />
                <input v-model="item.metric" placeholder="如：cpu_usage" />
                <input v-model="item.threshold" type="number" placeholder="90" style="width:70px" />
                <input v-model="item.unit" placeholder="%" style="width:60px" />
                <select v-model="item.severity" style="width:90px">
                  <option value="critical">critical</option>
                  <option value="warning">warning</option>
                </select>
                <button class="btn btn-sm btn-danger" @click="removeCheckItem(idx)">×</button>
              </div>
              <button class="btn btn-sm" @click="addCheckItem">+ 添加检查项</button>
            </div>
          </div>
          <div class="form-group">
            <label><input type="checkbox" v-model="tplForm.enabled" /> 启用此模板</label>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn" @click="showTemplateDialog = false">取消</button>
          <button class="btn btn-primary" @click="saveTemplate" :disabled="!tplForm.name">保存</button>
        </div>
      </div>
    </div>

    <!-- ═══════ 新建/编辑任务弹窗 ═══════ -->
    <div v-if="showTaskDialog" class="modal-overlay" @click.self="showTaskDialog = false">
      <div class="modal-box" style="max-width:700px">
        <div class="modal-header">
          <h3>{{ editingTask ? '编辑巡检任务' : '新建巡检任务' }}</h3>
          <button class="modal-close" @click="showTaskDialog = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>任务名称 *</label>
            <input v-model="taskForm.name" placeholder="如：生产环境服务器日检" />
          </div>
          <div class="form-group">
            <label>巡检模板 *</label>
            <select v-model.number="taskForm.template_id">
              <option :value="0">请选择模板</option>
              <option v-for="tpl in templates" :key="tpl.id" :value="tpl.id">{{ tpl.name }}</option>
            </select>
          </div>
          <div class="form-group">
            <label>资产范围</label>
            <div class="scope-type-row">
              <label><input type="radio" v-model="taskForm.scope_type" value="manual" /> 手动选择</label>
              <label><input type="radio" v-model="taskForm.scope_type" value="dynamic" /> 动态范围</label>
            </div>
          </div>

          <!-- 手动选择资产 -->
          <div v-if="taskForm.scope_type === 'manual'" class="form-group">
            <label>选择资产</label>
            <div v-if="selectedTemplate && selectedTemplate.target_ci_types.length && !assetCiTypeFilter" class="template-filter-hint">
              已按模板自动过滤：{{ selectedTemplate.target_ci_types.map(t => CI_LABELS[t] || t).join(' / ') }}
              <span class="filter-override">（可在右侧下拉切换）</span>
            </div>
            <div class="asset-selector">
              <div class="selector-toolbar">
                <input v-model="assetKeyword" placeholder="搜索资产名称或IP..." @input="searchAssets" class="selector-search" />
                <select v-model="assetCiTypeFilter" @change="searchAssets" class="selector-filter">
                  <option value="">按模板类型</option>
                  <option v-for="cit in CI_TYPES" :key="cit" :value="cit">{{ CI_LABELS[cit] || cit }}</option>
                </select>
              </div>
              <div class="selector-list">
                <div v-for="a in assetOptions" :key="a.id" class="selector-item" :class="{ selected: taskForm.asset_ids.includes(a.id) }" @click="toggleAsset(a.id)">
                  <span class="selector-check">{{ taskForm.asset_ids.includes(a.id) ? '☑' : '☐' }}</span>
                  <span class="selector-name">{{ a.name }}</span>
                  <span class="selector-type">{{ a.ci_type }}</span>
                  <span class="selector-ip">{{ a.ip }}</span>
                </div>
                <div v-if="!assetOptions.length" class="empty-state" style="padding:20px">无匹配资产</div>
              </div>
              <div class="selector-footer">已选择 {{ taskForm.asset_ids.length }} 个资产</div>
            </div>
          </div>

          <!-- 动态范围 -->
          <div v-if="taskForm.scope_type === 'dynamic'" class="form-group">
            <label>动态筛选条件 (JSON)</label>
            <textarea v-model="taskForm.scope_filter_json" rows="4" placeholder='{"ci_types": ["server"], "tags": ["prod"], "status": "online"}'></textarea>
          </div>

          <div class="form-group">
            <label><input type="checkbox" v-model="taskForm.ai_analysis" /> 启用 AI 智能分析（LLM 生成巡检报告）</label>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn" @click="showTaskDialog = false">取消</button>
          <button class="btn btn-primary" @click="saveTask" :disabled="!taskForm.name || !taskForm.template_id">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, reactive, onMounted, computed, watch } from 'vue'
import axios from 'axios'

const API = '/inspection/api'

export default {
  name: 'InspectionView',
  setup() {
    const activeTab = ref('tasks')
    const loadingTasks = ref(false)
    const stats = ref({ total_tasks: 0, total_records: 0, completed_records: 0, avg_score: 0, latest_record: null })
    const templates = ref([])
    const tasks = ref([])
    const records = ref([])

    const showTaskDialog = ref(false)
    const editingTask = ref(null)
    const taskForm = reactive({
      name: '', template_id: 0, scope_type: 'manual', asset_ids: [],
      scope_filter_json: '{}', ai_analysis: true,
    })

    const assetKeyword = ref('')
    const assetCiTypeFilter = ref('')
    const assetOptions = ref([])

    const showReport = ref(false)
    const currentRecord = ref(null)

    const showTemplateDialog = ref(false)
    const editingTemplate = ref(null)
    const tplForm = reactive({
      name: '', description: '', target_ci_types: [], check_items: [], enabled: true,
    })
    const CI_TYPES = [
      'server', 'virtual_machine', 'cloud_host', 'network_device', 'switch', 'router',
      'firewall', 'load_balancer', 'storage_device',
      'database', 'redis', 'mysql', 'postgresql', 'kafka', 'rabbitmq', 'rocketmq', 'mongodb', 'elasticsearch', 'middleware',
      'deployment', 'service', 'pod', 'container', 'statefulset', 'daemonset',
      'api_service', 'api_gateway', 'api',
    ]
    const CI_LABELS = {
      server: '服务器', virtual_machine: '虚拟机', cloud_host: '云主机', network_device: '网络设备',
      switch: '交换机', router: '路由器', firewall: '防火墙', load_balancer: '负载均衡', storage_device: '存储设备',
      database: '数据库', redis: 'Redis', mysql: 'MySQL', postgresql: 'PostgreSQL', kafka: 'Kafka',
      rabbitmq: 'RabbitMQ', rocketmq: 'RocketMQ', mongodb: 'MongoDB', elasticsearch: 'Elasticsearch', middleware: '中间件',
      deployment: 'K8s部署', service: 'Service', pod: 'Pod', container: '容器', statefulset: 'StatefulSet', daemonset: 'DaemonSet',
      api_service: 'API服务', api_gateway: 'API网关', api: 'API',
    }

    const selectedTemplate = computed(() => templates.value.find(t => t.id === taskForm.template_id))

    const loadStats = async () => {
      try { const { data } = await axios.get(`${API}/stats`); stats.value = data } catch (e) { console.error(e) }
    }

    const loadTemplates = async () => {
      try { const { data } = await axios.get(`${API}/templates`); templates.value = data } catch (e) { console.error(e) }
    }

    const loadTasks = async () => {
      loadingTasks.value = true
      try { const { data } = await axios.get(`${API}/tasks`); tasks.value = data } catch (e) { console.error(e) }
      loadingTasks.value = false
    }

    const loadRecords = async () => {
      try { const { data } = await axios.get(`${API}/records`); records.value = data } catch (e) { console.error(e) }
    }

    const searchAssets = async () => {
      try {
        const params = { page: 1, per_page: 50 }
        if (assetKeyword.value) params.keyword = assetKeyword.value
        if (assetCiTypeFilter.value) {
          params.ci_type = assetCiTypeFilter.value
        } else if (selectedTemplate.value && selectedTemplate.value.target_ci_types.length) {
          params.ci_types = selectedTemplate.value.target_ci_types.join(',')
        }
        const { data } = await axios.get(`${API}/assets-browse`, { params })
        assetOptions.value = data.items || []
      } catch (e) { console.error(e) }
    }

    const toggleAsset = (id) => {
      const idx = taskForm.asset_ids.indexOf(id)
      if (idx >= 0) taskForm.asset_ids.splice(idx, 1)
      else taskForm.asset_ids.push(id)
    }

    const openCreateTask = () => {
      editingTask.value = null
      Object.assign(taskForm, { name: '', template_id: 0, scope_type: 'manual', asset_ids: [], scope_filter_json: '{}', ai_analysis: true })
      assetKeyword.value = ''
      assetCiTypeFilter.value = ''
      showTaskDialog.value = true
      searchAssets()
    }

    const openEditTask = (task) => {
      editingTask.value = task
      Object.assign(taskForm, {
        name: task.name, template_id: task.template_id, scope_type: task.scope_type,
        asset_ids: [...task.asset_ids], scope_filter_json: JSON.stringify(task.scope_filter, null, 2),
        ai_analysis: task.ai_analysis,
      })
      showTaskDialog.value = true
      searchAssets()
    }

    const saveTask = async () => {
      const payload = {
        name: taskForm.name, template_id: taskForm.template_id, scope_type: taskForm.scope_type,
        asset_ids: taskForm.asset_ids, ai_analysis: taskForm.ai_analysis,
      }
      if (taskForm.scope_type === 'dynamic') {
        try { payload.scope_filter = JSON.parse(taskForm.scope_filter_json) } catch { payload.scope_filter = {} }
      }
      try {
        if (editingTask.value) {
          await axios.put(`${API}/tasks/${editingTask.value.id}`, payload)
        } else {
          await axios.post(`${API}/tasks`, payload)
        }
        showTaskDialog.value = false
        loadTasks(); loadStats()
      } catch (e) { alert('保存失败: ' + (e.response?.data?.error || e.message)) }
    }

    const deleteTask = async (task) => {
      if (!confirm(`确定删除任务「${task.name}」？`)) return
      try { await axios.delete(`${API}/tasks/${task.id}`); loadTasks(); loadStats() } catch (e) { alert('删除失败') }
    }

    const runTask = async (task) => {
      task.status = 'running'
      try {
        const { data } = await axios.post(`${API}/tasks/${task.id}/run`)
        if (data.error) { alert(data.error); task.status = 'idle'; return }
        task.status = 'idle'
        task.last_run_at = new Date().toISOString()
        loadRecords(); loadStats()
        activeTab.value = 'records'
        viewRecord(data)
      } catch (e) { task.status = 'idle'; alert('执行失败: ' + (e.response?.data?.error || e.message)) }
    }

    const viewRecord = (record) => { currentRecord.value = record; showReport.value = true }

    const getTemplateName = (id) => { const t = templates.value.find(t => t.id === id); return t ? t.name : `#${id}` }

    const formatTime = (iso) => {
      if (!iso) return '-'
      return new Date(iso).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
    }

    const scoreClass = (score) => {
      if (score >= 90) return 'score-good'
      if (score >= 60) return 'score-warn'
      return 'score-bad'
    }

    const renderMarkdown = (md) => {
      if (!md) return ''
      return md
        .replace(/^### (.+)$/gm, '<h4>$1</h4>')
        .replace(/^## (.+)$/gm, '<h3>$1</h3>')
        .replace(/^# (.+)$/gm, '<h2>$1</h2>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/^- (.+)$/gm, '<li>$1</li>')
        .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
        .replace(/\n{2,}/g, '<br><br>')
        .replace(/\n/g, '<br>')
    }

    const openCreateTemplate = () => {
      editingTemplate.value = null
      tplForm.name = ''
      tplForm.description = ''
      tplForm.target_ci_types = []
      tplForm.check_items = [{ name: '', metric: '', threshold: 90, unit: '%', severity: 'warning' }]
      tplForm.enabled = true
      showTemplateDialog.value = true
    }
    const openEditTemplate = (tpl) => {
      editingTemplate.value = tpl
      tplForm.name = tpl.name
      tplForm.description = tpl.description || ''
      tplForm.target_ci_types = [...(tpl.target_ci_types || [])]
      tplForm.check_items = (tpl.check_items || []).map(c => ({ ...c }))
      tplForm.enabled = tpl.enabled !== false
      showTemplateDialog.value = true
    }
    const addCheckItem = () => { tplForm.check_items.push({ name: '', metric: '', threshold: 90, unit: '', severity: 'warning' }) }
    const removeCheckItem = (idx) => { tplForm.check_items.splice(idx, 1) }
    const saveTemplate = async () => {
      const payload = {
        name: tplForm.name,
        description: tplForm.description,
        target_ci_types: tplForm.target_ci_types,
        check_items: tplForm.check_items.filter(c => c.name && c.metric),
        enabled: tplForm.enabled,
      }
      try {
        if (editingTemplate.value) {
          await axios.put(`${API}/templates/${editingTemplate.value.id}`, payload)
        } else {
          await axios.post(`${API}/templates`, payload)
        }
        showTemplateDialog.value = false
        loadTemplates()
      } catch (e) { alert('保存失败: ' + (e.response?.data?.error || e.message)) }
    }
    const deleteTemplate = async (tpl) => {
      if (!confirm(`确定删除模板「${tpl.name}」？`)) return
      try { await axios.delete(`${API}/templates/${tpl.id}`); loadTemplates() } catch (e) { alert('删除失败') }
    }

    watch(() => taskForm.template_id, (newId, oldId) => {
      if (newId && newId !== oldId) {
        taskForm.asset_ids = []
        assetCiTypeFilter.value = ''
        searchAssets()
      }
    })

    onMounted(() => { loadStats(); loadTemplates(); loadTasks(); loadRecords() })

    return {
      activeTab, loadingTasks, stats, templates, tasks, records,
      showTaskDialog, editingTask, taskForm,
      assetKeyword, assetCiTypeFilter, assetOptions,
      showReport, currentRecord,
      showTemplateDialog, editingTemplate, tplForm, CI_TYPES, CI_LABELS, selectedTemplate,
      loadTasks, loadRecords, searchAssets, toggleAsset,
      openCreateTask, openEditTask, saveTask, deleteTask, runTask,
      viewRecord, getTemplateName, formatTime, scoreClass, renderMarkdown,
      openCreateTemplate, openEditTemplate, addCheckItem, removeCheckItem, saveTemplate, deleteTemplate,
    }
  },
}
</script>

<style scoped>
.inspection-page { padding: 20px; }
.page-header { margin-bottom: 20px; }
.page-header h1 { margin: 0 0 4px; font-size: 22px; }
.page-header p { margin: 0; color: var(--text-muted, #999); font-size: 13px; }

.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }
.stat-card { display: flex; align-items: center; gap: 14px; padding: 18px 20px; background: var(--card-bg, #fff); border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.stat-icon { width: 48px; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 22px; color: #fff; flex-shrink: 0; }
.stat-value { font-size: 24px; font-weight: 700; }
.stat-label { font-size: 12px; color: var(--text-muted, #999); }

.tab-bar { display: flex; gap: 0; border-bottom: 2px solid var(--border-color, #e8e8e8); margin-bottom: 16px; }
.tab-item { padding: 10px 20px; cursor: pointer; font-weight: 500; color: var(--text-muted, #999); border-bottom: 2px solid transparent; margin-bottom: -2px; transition: all 0.2s; }
.tab-item.active { color: var(--primary, #409eff); border-bottom-color: var(--primary, #409eff); }

.toolbar { display: flex; gap: 8px; margin-bottom: 12px; }
.btn { padding: 6px 14px; border: 1px solid var(--border-color, #ddd); border-radius: 6px; cursor: pointer; background: var(--card-bg, #fff); font-size: 13px; transition: all 0.2s; }
.btn:hover { background: var(--hover-bg, #f5f5f5); }
.btn-primary { background: var(--primary, #409eff); color: #fff; border-color: var(--primary, #409eff); }
.btn-primary:hover { opacity: 0.9; }
.btn-success { background: #67c23a; color: #fff; border-color: #67c23a; }
.btn-danger { background: #f56c6c; color: #fff; border-color: #f56c6c; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

.panel { background: var(--card-bg, #fff); border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); overflow: hidden; }
.panel-body { padding: 0; }
.table { width: 100%; border-collapse: collapse; }
.table th, .table td { padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--border-color, #f0f0f0); font-size: 13px; }
.table th { background: var(--hover-bg, #fafafa); font-weight: 600; color: var(--text-muted, #666); }
.table tr:hover td { background: var(--hover-bg, #f8f9fa); }

.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; font-weight: 500; }
.badge.resolved { background: #e8f8e8; color: #3a8d3a; }
.badge.warning { background: #fff3e0; color: #e67e00; }
.badge.critical { background: #fde8e8; color: #d32f2f; }
.badge.info { background: #e8f0fe; color: #1967d2; }
.badge.running { background: #fff3e0; color: #e67e00; animation: pulse 1.5s infinite; }
.badge.idle { background: #f0f0f0; color: #999; }

@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }

.empty-state { text-align: center; padding: 48px 20px; color: var(--text-muted, #999); }
.loading-state { text-align: center; padding: 40px; color: var(--text-muted, #999); }
.text-sm { font-size: 12px; color: var(--text-muted, #999); }

/* 模板卡片 */
.template-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
.template-card { background: var(--card-bg, #fff); border-radius: 12px; padding: 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.template-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.template-header h3 { margin: 0; font-size: 16px; }
.template-desc { color: var(--text-muted, #999); font-size: 13px; margin: 0 0 10px; }
.template-meta { display: flex; gap: 16px; font-size: 12px; color: var(--text-muted, #999); margin-bottom: 10px; }
.template-items { border-top: 1px solid var(--border-color, #f0f0f0); padding-top: 10px; }
.check-item { display: flex; justify-content: space-between; padding: 4px 0; font-size: 12px; }
.check-name { color: var(--text-primary, #333); }
.check-threshold { color: var(--primary, #409eff); font-weight: 500; }
.check-more { font-size: 12px; color: var(--text-muted, #999); padding-top: 4px; }
.template-actions { display: flex; gap: 8px; margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border-color, #f0f0f0); }

/* 记录卡片 */
.record-card { background: var(--card-bg, #fff); border-radius: 12px; padding: 16px 20px; margin-bottom: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); cursor: pointer; transition: all 0.2s; }
.record-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.1); transform: translateY(-1px); }
.record-header { display: flex; align-items: center; gap: 20px; }
.record-score { font-size: 28px; font-weight: 700; min-width: 80px; text-align: center; }
.record-score span { font-size: 14px; font-weight: 400; }
.score-good { color: #67c23a; }
.score-warn { color: #e6a23c; }
.score-bad { color: #f56c6c; }
.record-info { flex: 1; }
.record-info h4 { margin: 0 0 4px; font-size: 14px; }
.record-info p { margin: 0; font-size: 12px; color: var(--text-muted, #999); }
.record-badges { display: flex; gap: 8px; }

/* 抽屉 */
.drawer-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 1000; display: flex; justify-content: flex-end; }
.drawer { background: var(--card-bg, #fff); width: 680px; max-width: 90vw; height: 100vh; overflow-y: auto; box-shadow: -4px 0 20px rgba(0,0,0,0.15); }
.drawer-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border-color, #e8e8e8); position: sticky; top: 0; background: var(--card-bg, #fff); z-index: 1; }
.drawer-header h2 { margin: 0; font-size: 18px; }
.drawer-body { padding: 20px; }

.report-summary { display: flex; align-items: center; gap: 24px; margin-bottom: 20px; padding: 20px; background: var(--hover-bg, #f8f9fa); border-radius: 12px; }
.report-score { font-size: 40px; font-weight: 700; }
.report-score span { font-size: 16px; font-weight: 400; }
.report-meta { font-size: 13px; line-height: 1.8; }

.report-badges { display: flex; gap: 12px; margin-bottom: 20px; }

.ai-report { margin: 20px 0; padding: 20px; background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); border-radius: 12px; }
.ai-report h3 { margin: 0 0 12px; }
.report-markdown { font-size: 14px; line-height: 1.8; }
.report-markdown :deep(h2) { font-size: 18px; margin: 20px 0 8px; }
.report-markdown :deep(h3) { font-size: 16px; margin: 16px 0 6px; }
.report-markdown :deep(h4) { font-size: 14px; margin: 12px 0 4px; }
.report-markdown :deep(ul) { margin: 4px 0; padding-left: 20px; }
.report-markdown :deep(li) { margin: 2px 0; }

.detail-section { margin-top: 20px; }
.detail-section h3 { margin: 0 0 12px; }

.asset-check-group { margin-bottom: 12px; border: 1px solid var(--border-color, #e8e8e8); border-radius: 8px; overflow: hidden; }
.asset-check-header { display: flex; align-items: center; gap: 12px; padding: 10px 14px; background: var(--hover-bg, #fafafa); }
.asset-check-header.border-critical { border-left: 3px solid #f56c6c; }
.asset-check-header.border-warning { border-left: 3px solid #e6a23c; }
.asset-check-header.border-normal { border-left: 3px solid #67c23a; }
.asset-check-name { font-weight: 600; font-size: 13px; }
.asset-check-type { font-size: 12px; color: var(--text-muted, #999); flex: 1; }
.check-list { padding: 4px 0; }
.check-row { display: flex; align-items: center; gap: 8px; padding: 6px 14px; font-size: 12px; }
.check-row.status-critical { background: #fef0f0; }
.check-row.status-warning { background: #fdf6ec; }
.check-icon { width: 20px; text-align: center; }
.check-label { width: 120px; font-weight: 500; }
.check-value { width: 80px; font-weight: 600; }
.check-detail { color: var(--text-muted, #999); flex: 1; }

/* 资产选择器 */
.asset-selector { border: 1px solid var(--border-color, #ddd); border-radius: 8px; overflow: hidden; }
.selector-toolbar { display: flex; gap: 8px; padding: 8px; border-bottom: 1px solid var(--border-color, #f0f0f0); }
.selector-search { flex: 1; padding: 6px 10px; border: 1px solid var(--border-color, #ddd); border-radius: 4px; font-size: 13px; }
.selector-filter { padding: 6px 10px; border: 1px solid var(--border-color, #ddd); border-radius: 4px; font-size: 13px; }
.selector-list { max-height: 240px; overflow-y: auto; }
.selector-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; cursor: pointer; font-size: 13px; border-bottom: 1px solid var(--border-color, #f5f5f5); }
.selector-item:hover { background: var(--hover-bg, #f5f7fa); }
.selector-item.selected { background: #ecf5ff; }
.selector-check { font-size: 16px; }
.selector-name { font-weight: 500; flex: 1; }
.selector-type { font-size: 11px; color: var(--text-muted, #999); background: var(--hover-bg, #f0f0f0); padding: 1px 6px; border-radius: 4px; }
.selector-ip { font-size: 12px; color: var(--text-muted, #999); }
.selector-footer { padding: 8px 12px; background: var(--hover-bg, #fafafa); font-size: 12px; color: var(--text-muted, #999); }
.template-filter-hint { padding: 6px 10px; background: #ecf5ff; border: 1px solid #b3d8ff; border-radius: 6px; font-size: 12px; color: #409eff; margin-bottom: 8px; }
.filter-override { color: #999; }

/* 弹窗 */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 1000; display: flex; align-items: center; justify-content: center; }
.modal-box { background: var(--card-bg, #fff); border-radius: 12px; width: 560px; max-width: 90vw; max-height: 85vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.15); }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border-color, #e8e8e8); }
.modal-header h3 { margin: 0; }
.modal-close { background: none; border: none; font-size: 24px; cursor: pointer; color: var(--text-muted, #999); }
.modal-body { padding: 20px; }
.modal-footer { padding: 12px 20px; border-top: 1px solid var(--border-color, #e8e8e8); display: flex; justify-content: flex-end; gap: 8px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 13px; font-weight: 500; margin-bottom: 4px; }
.form-group input, .form-group select, .form-group textarea { width: 100%; padding: 8px 10px; border: 1px solid var(--border-color, #ddd); border-radius: 6px; font-size: 13px; box-sizing: border-box; }
.form-group textarea { font-family: monospace; font-size: 12px; }
.scope-type-row { display: flex; gap: 20px; }
.scope-type-row label { display: flex; align-items: center; gap: 4px; font-weight: 400; cursor: pointer; }

/* 模板编辑 */
.ci-type-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; max-height: 160px; overflow-y: auto; border: 1px solid var(--border-color, #ddd); border-radius: 6px; padding: 10px; background: var(--hover-bg, #fafafa); }
.ci-type-label { display: flex; align-items: center; gap: 4px; font-size: 12px; cursor: pointer; font-weight: 400; }
.ci-type-label input { width: auto; }

.check-items-editor { border: 1px solid var(--border-color, #ddd); border-radius: 6px; overflow: hidden; }
.check-item-header { display: grid; grid-template-columns: 1fr 1fr 70px 60px 90px 32px; gap: 6px; padding: 8px 10px; background: var(--hover-bg, #f5f7fa); font-size: 11px; font-weight: 600; color: var(--text-muted, #999); }
.check-item-row { display: grid; grid-template-columns: 1fr 1fr 70px 60px 90px 32px; gap: 6px; padding: 6px 10px; border-top: 1px solid var(--border-color, #f0f0f0); align-items: center; }
.check-item-row input, .check-item-row select { padding: 4px 6px; border: 1px solid var(--border-color, #ddd); border-radius: 4px; font-size: 12px; width: 100%; box-sizing: border-box; }
.check-items-editor > button { margin: 8px 10px; }
</style>
