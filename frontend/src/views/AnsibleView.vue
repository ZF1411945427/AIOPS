<template>
  <div class="ansible-page">
    <div class="page-header">
      <div class="title-row">
        <div>
          <h1>Ansible 运维操作</h1>
          <p>主机清单 · Playbook 模板 · 远程执行 · 执行历史</p>
        </div>
        <button class="btn btn-guide" @click="showGuide = !showGuide">📖 操作说明</button>
        <div class="status-tag" :class="ansibleInstalled ? 'ok' : 'warn'">
          <span class="dot"></span>
          <span v-if="statusLoading">检测中...</span>
          <span v-else-if="ansibleInstalled">Ansible 已安装 · {{ ansibleVersion }}</span>
            <span v-else>Ansible 未安装</span>
        </div>
      </div>
    </div>

    <div class="tabs">
      <button class="tab" :class="{ active: activeTab === 'runs' }" @click="switchTab('runs')">执行历史</button>
      <button class="tab" :class="{ active: activeTab === 'inventories' }" @click="switchTab('inventories')">主机清单</button>
      <button class="tab" :class="{ active: activeTab === 'playbooks' }" @click="switchTab('playbooks')">Playbook 模板</button>
    </div>

    <!-- 执行历史 -->
    <div v-if="activeTab === 'runs'">
      <div class="toolbar">
        <button class="btn btn-primary" @click="openRunDialog">+ 执行</button>
        <button class="btn" @click="loadRuns">刷新</button>
      </div>
      <div class="panel">
        <div class="panel-head">执行历史 · 共 {{ runs.length }} 条</div>
        <div class="panel-body">
          <div v-if="runsLoading" class="loading-state">加载中...</div>
          <table v-else-if="runs.length" class="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>主机清单</th>
                <th>Playbook</th>
                <th>状态</th>
                <th>退出码</th>
                <th>创建时间</th>
                <th>完成时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in runs" :key="r.id">
                <td>{{ r.id }}</td>
                <td>{{ r.inventory_name || '-' }}</td>
                <td>{{ r.playbook_name || '-' }}</td>
                <td><span class="badge" :class="statusClass(r.status)">{{ statusLabel(r.status) }}</span></td>
                <td><span class="mono">{{ r.exit_code }}</span></td>
                <td class="text-sm">{{ r.created_at || '-' }}</td>
                <td class="text-sm">{{ r.finished_at || '-' }}</td>
                <td class="action-cell">
                  <button class="btn btn-sm" @click="viewRun(r)">查看</button>
                  <button class="btn btn-sm btn-danger" @click="deleteRun(r)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-state">
            <div style="font-size:32px;margin-bottom:8px;">📜</div>
            <div>暂无执行历史</div>
            <div class="text-muted" style="margin-top:4px;">点击右上角「执行」开始一次 Ansible 任务</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 主机清单 -->
    <div v-if="activeTab === 'inventories'">
      <div class="toolbar">
        <button class="btn btn-primary" @click="openInvDialog(null)">+ 新建清单</button>
        <button class="btn" @click="loadInventories">刷新</button>
      </div>
      <div class="panel">
        <div class="panel-head">主机清单 · 共 {{ inventories.length }} 项</div>
        <div class="panel-body">
          <div v-if="invLoading" class="loading-state">加载中...</div>
          <table v-else-if="inventories.length" class="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>名称</th>
                <th>描述</th>
                <th>更新时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="i in inventories" :key="i.id">
                <td>{{ i.id }}</td>
                <td>{{ i.name }}</td>
                <td class="text-sm">{{ i.description || '-' }}</td>
                <td class="text-sm">{{ i.updated_at || '-' }}</td>
                <td class="action-cell">
                  <button class="btn btn-sm" @click="testInventory(i)">测试</button>
                  <button class="btn btn-sm" @click="openInvDialog(i)">编辑</button>
                  <button class="btn btn-sm btn-danger" @click="deleteInventory(i)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-state">
            <div style="font-size:32px;margin-bottom:8px;">🗂️</div>
            <div>暂无主机清单</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Playbook 模板 -->
    <div v-if="activeTab === 'playbooks'">
      <div class="toolbar">
        <button class="btn btn-primary" @click="openPbDialog(null)">+ 新建 Playbook</button>
        <button class="btn" @click="loadPlaybooks">刷新</button>
      </div>
      <div class="panel">
        <div class="panel-head">Playbook 模板 · 共 {{ playbooks.length }} 项</div>
        <div class="panel-body">
          <div v-if="pbLoading" class="loading-state">加载中...</div>
          <table v-else-if="playbooks.length" class="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>名称</th>
                <th>描述</th>
                <th>更新时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in playbooks" :key="p.id">
                <td>{{ p.id }}</td>
                <td>{{ p.name }}</td>
                <td class="text-sm">{{ p.description || '-' }}</td>
                <td class="text-sm">{{ p.updated_at || '-' }}</td>
                <td class="action-cell">
                  <button class="btn btn-sm" @click="openPbDialog(p)">编辑</button>
                  <button class="btn btn-sm btn-danger" @click="deletePlaybook(p)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-state">
            <div style="font-size:32px;margin-bottom:8px;">📖</div>
            <div>暂无 Playbook 模板</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 执行对话框 -->
    <div v-if="showRunDialog" class="modal-overlay" @click.self="closeRunDialog">
      <div class="modal-box">
        <h3>执行 Playbook</h3>
        <div class="form-row">
          <label>主机清单</label>
          <select v-model="runForm.inventory_id" class="input">
            <option :value="null">请选择</option>
            <option v-for="i in inventories" :key="i.id" :value="i.id">{{ i.name }}</option>
          </select>
        </div>
        <div class="form-row">
          <label>Playbook</label>
          <select v-model="runForm.playbook_id" class="input">
            <option :value="null">请选择</option>
            <option v-for="p in playbooks" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </div>
        <div class="form-row">
          <label>额外变量 (JSON)</label>
          <textarea v-model="runForm.extra_vars" class="input mono" rows="5" placeholder='{"key":"value"}'></textarea>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="closeRunDialog">取消</button>
          <button class="btn btn-primary" :disabled="runExecuting" @click="executeRun">{{ runExecuting ? '执行中...' : '执行' }}</button>
        </div>
      </div>
    </div>

    <!-- 主机清单编辑对话框 -->
    <div v-if="showInvDialog" class="modal-overlay" @click.self="closeInvDialog">
      <div class="modal-box modal-lg">
        <h3>{{ invForm.id ? '编辑主机清单 · ' + invForm.name : '新建主机清单' }}</h3>
        <div class="form-row">
          <label>名称</label>
          <input v-model="invForm.name" class="input" placeholder="如: prod-hosts" />
        </div>
        <div class="form-row">
          <label>描述</label>
          <input v-model="invForm.description" class="input" placeholder="可选" />
        </div>
        <div class="form-row">
          <label>清单内容 (YAML)</label>
          <textarea v-model="invForm.content" class="input mono" rows="12" placeholder="all:&#10;  hosts:&#10;    node1:&#10;      ansible_host: 192.168.1.10"></textarea>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="closeInvDialog">取消</button>
          <button class="btn btn-primary" :disabled="invSaving" @click="saveInventory">{{ invSaving ? '保存中...' : '保存' }}</button>
        </div>
      </div>
    </div>

    <!-- Playbook 编辑对话框 -->
    <div v-if="showPbDialog" class="modal-overlay" @click.self="closePbDialog">
      <div class="modal-box modal-lg">
        <h3>{{ pbForm.id ? '编辑 Playbook · ' + pbForm.name : '新建 Playbook' }}</h3>
        <div class="form-row">
          <label>名称</label>
          <input v-model="pbForm.name" class="input" placeholder="如: restart-nginx" />
        </div>
        <div class="form-row">
          <label>描述</label>
          <input v-model="pbForm.description" class="input" placeholder="可选" />
        </div>
        <div class="form-row">
          <label>Playbook 内容 (YAML)</label>
          <textarea v-model="pbForm.content" class="input mono" rows="14" placeholder="- hosts: all&#10;  tasks:&#10;    - name: ping&#10;      ansible.builtin.ping:"></textarea>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="closePbDialog">取消</button>
          <button class="btn btn-primary" :disabled="pbSaving" @click="savePlaybook">{{ pbSaving ? '保存中...' : '保存' }}</button>
        </div>
      </div>
    </div>

    <!-- 执行结果查看对话框 -->
    <div v-if="showRunDetail" class="modal-overlay" @click.self="closeRunDetail">
      <div class="modal-box modal-lg">
        <h3>执行详情 · #{{ runDetail.id }}</h3>
        <div class="run-meta">
          <span class="badge count">清单: {{ runDetail.inventory_name || '-' }}</span>
          <span class="badge count">Playbook: {{ runDetail.playbook_name || '-' }}</span>
          <span class="badge" :class="statusClass(runDetail.status)">{{ statusLabel(runDetail.status) }}</span>
          <span class="badge count">退出码: {{ runDetail.exit_code }}</span>
          <span class="badge count">{{ runDetail.created_at || '-' }}</span>
        </div>
        <div v-if="runDetail.extra_vars" class="detail-section">
          <div class="result-label">额外变量</div>
          <pre class="output-pre script">{{ runDetail.extra_vars }}</pre>
        </div>
        <div v-if="runDetail.output" class="detail-section">
          <div class="result-label">STDOUT</div>
          <pre class="output-pre dark">{{ runDetail.output }}</pre>
        </div>
        <div v-if="runDetail.error" class="detail-section">
          <div class="result-label danger">STDERR</div>
          <pre class="output-pre danger">{{ runDetail.error }}</pre>
        </div>
        <div v-if="!runDetail.output && !runDetail.error" class="empty-state" style="padding:20px;">无输出</div>
        <div class="modal-actions">
          <button class="btn" @click="closeRunDetail">关闭</button>
        </div>
      </div>
    </div>

    <!-- 测试连接结果 -->
    <div v-if="showTestResult" class="modal-overlay" @click.self="closeTestResult">
      <div class="modal-box modal-lg">
        <h3>测试连接结果 · {{ testMeta }}</h3>
        <div v-if="testLoading" class="loading-state">测试中...</div>
        <div v-else>
          <div class="run-meta">
            <span class="badge" :class="statusClass(testResult.status)">{{ statusLabel(testResult.status) }}</span>
            <span class="badge count">退出码: {{ testResult.exit_code }}</span>
          </div>
          <div v-if="testResult.output" class="detail-section">
            <div class="result-label">STDOUT</div>
            <pre class="output-pre dark">{{ testResult.output }}</pre>
          </div>
          <div v-if="testResult.error" class="detail-section">
            <div class="result-label danger">STDERR</div>
            <pre class="output-pre danger">{{ testResult.error }}</pre>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="closeTestResult">关闭</button>
        </div>
      </div>
    </div>
  </div>

  <GuideDrawer v-model="showGuide" title="📖 Ansible · 操作说明">
    <section class="guide-section">
      <h4>1. Ansible 是什么？</h4>
      <p><strong>Ansible</strong> 是 Red Hat 出品的自动化运维工具。它通过 SSH 连接到远程服务器，执行你定义好的任务，不需要在目标机器上装 Agent。</p>
      <p>简单说：Ansible 让你<strong>一次写好，到处执行</strong>——批量改配置、部署应用、重启服务等。</p>
    </section>
    <section class="guide-section">
      <h4>2. 三个核心概念</h4>
      <div class="key-value-list">
        <div class="kv-row">
          <span class="kv-key">Inventory（清单）</span>
          <span class="kv-val">你要管理的服务器列表，可以分组（如 web_servers、db_servers）。每个主机可以定义变量（IP、端口、用户名）</span>
        </div>
        <div class="kv-row">
          <span class="kv-key">Playbook</span>
          <span class="kv-val">用 YAML 写的"剧本"，定义了一系列任务（安装软件→复制配置→启动服务）。Playbook 是 Ansible 的核心</span>
        </div>
        <div class="kv-row">
          <span class="kv-key">Module（模块）</span>
          <span class="kv-val">Ansible 内置的"工具"，每个模块做一件事（copy=复制文件, yum=安装包, service=管理服务）。Playbook 就是按顺序调用模块</span>
        </div>
      </div>
    </section>
    <section class="guide-section">
      <h4>3. 页面三 Tab 说明</h4>
      <ul>
        <li><strong>执行历史</strong> — 查看所有 Ansible 任务的执行记录，包括状态、退出码、输出日志。支持重新执行或删除</li>
        <li><strong>主机清单</strong> — 管理你的服务器列表（Inventory），每个清单包含多个主机和连接信息</li>
        <li><strong>Playbook 模板</strong> — 编写和管理 Playbook 内容，执行时选择要用的 Playbook</li>
      </ul>
      <div class="tip-box">💡 完整的工作流：<strong>创建清单 → 编写 Playbook → 选择清单+Playbook → 执行 → 查看结果</strong></div>
    </section>
    <section class="guide-section">
      <h4>4. 快速入门：Ping 测试</h4>
      <p>从零开始测试一台服务器连通性：</p>
      <div class="step-list">
        <div class="step-item"><span class="step-num">1</span><span>在<strong>主机清单</strong> Tab，创建新清单，填入服务器 IP、SSH 端口、用户名</span></div>
        <div class="step-item"><span class="step-num">2</span><span>在<strong>Playbook 模板</strong> Tab，创建以下内容：</span></div>
      </div>
      <pre class="guide-code">---
- name: Ping test
  hosts: all
  gather_facts: no
  tasks:
    - name: ping
      ping:</pre>
      <div class="step-list">
        <div class="step-item"><span class="step-num">3</span><span>点击「执行」，选择刚才的清单和模板，点击确定</span></div>
        <div class="step-item"><span class="step-num">4</span><span>执行完成后在<strong>执行历史</strong>中查看结果，<code>pong</code> 返回值代表连通成功 ✅</span></div>
      </div>
    </section>
    <section class="guide-section">
      <h4>5. 常用 Playbook 示例</h4>
      <h5>🔹 批量修改配置</h5>
      <pre class="guide-code">---
- name: 更新 nginx 配置
  hosts: web_servers
  tasks:
    - name: 复制配置文件
      copy:
        src: /local/nginx.conf
        dest: /etc/nginx/nginx.conf
    - name: 重载 nginx
      service:
        name: nginx
        state: reloaded</pre>
      <h5>🔹 安装软件包</h5>
      <pre class="guide-code">---
- name: 安装 Redis
  hosts: db_servers
  tasks:
    - name: 安装 redis
      yum:
        name: redis
        state: present
    - name: 启动服务
      service:
        name: redis
        state: started
        enabled: yes</pre>
    </section>
    <section class="guide-section">
      <h4>6. 执行流程</h4>
      <p>点击「执行」后：</p>
      <ol style="margin:4px 0 10px;padding-left:18px;font-size:0.8rem;line-height:1.7;color:#475569;">
        <li>选择要操作的主机清单（Inventory）</li>
        <li>选择要执行的 Playbook</li>
        <li>可选：传入额外的变量（Extra Vars，JSON 格式）</li>
        <li>Ansible 通过 SSH 连接到目标机器，按 Playbook 步骤执行</li>
        <li>执行完成后可以查看 STDOUT/STDERR 输出日志</li>
      </ol>
    </section>
  </GuideDrawer>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import GuideDrawer from '@/components/GuideDrawer.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const activeTab = ref('runs')
const ansibleInstalled = ref(false)
const ansibleVersion = ref('')
const statusLoading = ref(false)

const runs = ref([])
const runsLoading = ref(false)
const inventories = ref([])
const invLoading = ref(false)
const playbooks = ref([])
const pbLoading = ref(false)

const showRunDialog = ref(false)
const runExecuting = ref(false)
const runForm = reactive({ inventory_id: null, playbook_id: null, extra_vars: '' })

const showInvDialog = ref(false)
const invSaving = ref(false)
const invForm = reactive({ id: null, name: '', description: '', content: '' })

const showPbDialog = ref(false)
const pbSaving = ref(false)
const pbForm = reactive({ id: null, name: '', description: '', content: '' })

const showRunDetail = ref(false)
const runDetail = ref({})

const showTestResult = ref(false)
const testLoading = ref(false)
const testResult = ref({})
const testMeta = ref('')

function statusClass(s) {
  if (s === 'completed') return 'green'
  if (s === 'failed') return 'red'
  if (s === 'running') return 'blue'
  return 'gray'
}
function statusLabel(s) {
  return { completed: '成功', failed: '失败', running: '运行中', pending: '等待' }[s] || s
}

function switchTab(t) {
  activeTab.value = t
  if (t === 'runs') loadRuns()
  else if (t === 'inventories') loadInventories()
  else if (t === 'playbooks') loadPlaybooks()
}

async function loadStatus() {
  statusLoading.value = true
  try {
    const data = await request.get('/ansible/api/status')
    ansibleInstalled.value = !!data.installed
    ansibleVersion.value = data.version || ''
  } catch (e) {
    ansibleInstalled.value = false
  } finally {
    statusLoading.value = false
  }
}

async function loadRuns() {
  runsLoading.value = true
  try {
    const data = await request.get('/ansible/api/runs')
    runs.value = data.items || []
  } catch (e) {
    ElMessage.error('加载执行历史失败: ' + e.message)
  } finally {
    runsLoading.value = false
  }
}

async function loadInventories() {
  invLoading.value = true
  try {
    const data = await request.get('/ansible/api/inventories')
    inventories.value = data.items || []
  } catch (e) {
    ElMessage.error('加载主机清单失败: ' + e.message)
  } finally {
    invLoading.value = false
  }
}

async function loadPlaybooks() {
  pbLoading.value = true
  try {
    const data = await request.get('/ansible/api/playbooks')
    playbooks.value = data.items || []
  } catch (e) {
    ElMessage.error('加载 Playbook 失败: ' + e.message)
  } finally {
    pbLoading.value = false
  }
}

function openRunDialog() {
  runForm.inventory_id = inventories.value[0]?.id || null
  runForm.playbook_id = playbooks.value[0]?.id || null
  runForm.extra_vars = ''
  showRunDialog.value = true
}
function closeRunDialog() {
  showRunDialog.value = false
}

async function executeRun() {
  if (!runForm.inventory_id) { ElMessage.warning('请选择主机清单'); return }
  if (!runForm.playbook_id) { ElMessage.warning('请选择 Playbook'); return }
  let extraVars = {}
  if (runForm.extra_vars.trim()) {
    try {
      extraVars = JSON.parse(runForm.extra_vars)
    } catch (e) {
      ElMessage.warning('额外变量 JSON 格式错误: ' + e.message)
      return
    }
  }
  runExecuting.value = true
  try {
    const data = await request.post('/ansible/api/run', {
      inventory_id: runForm.inventory_id,
      playbook_id: runForm.playbook_id,
      extra_vars: extraVars,
    })
    if (data.status === 'completed') {
      ElMessage.success('执行成功')
    } else {
      ElMessage.warning('执行完成: ' + statusLabel(data.status))
    }
    closeRunDialog()
    loadRuns()
  } catch (e) {
    ElMessage.error('执行失败: ' + e.message)
  } finally {
    runExecuting.value = false
  }
}

async function viewRun(r) {
  try {
    const data = await request.get(`/ansible/api/runs/${r.id}`)
    runDetail.value = data.item || r
    showRunDetail.value = true
  } catch (e) {
    ElMessage.error('加载详情失败: ' + e.message)
  }
}
function closeRunDetail() {
  showRunDetail.value = false
}

async function deleteRun(r) {
  try {
    await ElMessageBox.confirm(`确认删除执行记录 #${r.id}？`, '删除确认', { type: 'warning' })
    await request.delete(`/ansible/api/runs/${r.id}`)
    ElMessage.success('已删除')
    loadRuns()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + e.message)
  }
}

function openInvDialog(item) {
  if (item) {
    invForm.id = item.id
    invForm.name = item.name
    invForm.description = item.description
    invForm.content = item.content
  } else {
    invForm.id = null
    invForm.name = ''
    invForm.description = ''
    invForm.content = ''
  }
  showInvDialog.value = true
}
function closeInvDialog() {
  showInvDialog.value = false
}

async function saveInventory() {
  if (!invForm.name.trim()) { ElMessage.warning('请输入名称'); return }
  invSaving.value = true
  try {
    const payload = { name: invForm.name, description: invForm.description, content: invForm.content }
    if (invForm.id) {
      await request.put(`/ansible/api/inventories/${invForm.id}`, payload)
    } else {
      await request.post('/ansible/api/inventories', payload)
    }
    ElMessage.success(invForm.id ? '已更新' : '已创建')
    closeInvDialog()
    loadInventories()
  } catch (e) {
    ElMessage.error('保存失败: ' + e.message)
  } finally {
    invSaving.value = false
  }
}

async function deleteInventory(i) {
  try {
    await ElMessageBox.confirm(`确认删除主机清单「${i.name}」？`, '删除确认', { type: 'warning' })
    await request.delete(`/ansible/api/inventories/${i.id}`)
    ElMessage.success('已删除')
    loadInventories()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + e.message)
  }
}

async function testInventory(i) {
  testMeta.value = i.name
  testLoading.value = true
  testResult.value = {}
  showTestResult.value = true
  try {
    const data = await request.post('/ansible/api/test-inventory', { content: i.content })
    testResult.value = data
  } catch (e) {
    testResult.value = { status: 'failed', error: e.message, exit_code: -1, output: '' }
  } finally {
    testLoading.value = false
  }
}
function closeTestResult() {
  showTestResult.value = false
}

function openPbDialog(item) {
  if (item) {
    pbForm.id = item.id
    pbForm.name = item.name
    pbForm.description = item.description
    pbForm.content = item.content
  } else {
    pbForm.id = null
    pbForm.name = ''
    pbForm.description = ''
    pbForm.content = ''
  }
  showPbDialog.value = true
}
function closePbDialog() {
  showPbDialog.value = false
}

async function savePlaybook() {
  if (!pbForm.name.trim()) { ElMessage.warning('请输入名称'); return }
  pbSaving.value = true
  try {
    const payload = { name: pbForm.name, description: pbForm.description, content: pbForm.content }
    if (pbForm.id) {
      await request.put(`/ansible/api/playbooks/${pbForm.id}`, payload)
    } else {
      await request.post('/ansible/api/playbooks', payload)
    }
    ElMessage.success(pbForm.id ? '已更新' : '已创建')
    closePbDialog()
    loadPlaybooks()
  } catch (e) {
    ElMessage.error('保存失败: ' + e.message)
  } finally {
    pbSaving.value = false
  }
}

async function deletePlaybook(p) {
  try {
    await ElMessageBox.confirm(`确认删除 Playbook「${p.name}」？`, '删除确认', { type: 'warning' })
    await request.delete(`/ansible/api/playbooks/${p.id}`)
    ElMessage.success('已删除')
    loadPlaybooks()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + e.message)
  }
}

onMounted(() => {
  loadStatus()
  loadRuns()
  loadInventories()
  loadPlaybooks()
})

const showGuide = ref(false)
</script>

<style scoped>
.ansible-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.title-row { display: flex; align-items: center; gap: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.status-tag { display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px; border-radius: 16px; font-size: 0.78rem; font-weight: 500; }
.status-tag .dot { width: 8px; height: 8px; border-radius: 50%; }
.status-tag.ok { background: rgba(34,197,94,0.1); color: #22c55e; }
.status-tag.ok .dot { background: #22c55e; }
.status-tag.warn { background: rgba(245,158,11,0.1); color: #f59e0b; }
.status-tag.warn .dot { background: #f59e0b; }
.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); margin-bottom: 16px; }
.tab { padding: 8px 16px; border: none; background: transparent; color: var(--text-secondary, #64748b); cursor: pointer; font-size: 0.85rem; border-bottom: 2px solid transparent; transition: all 0.2s; }
.tab:hover { color: var(--text, #1e293b); }
.tab.active { color: var(--accent, #6366f1); border-bottom-color: var(--accent, #6366f1); font-weight: 600; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.input.mono, textarea.mono { font-family: ui-monospace, 'Consolas', 'Monaco', monospace; font-size: 0.8rem; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; transition: all 0.2s; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-danger { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-danger:hover { background: rgba(239,68,68,0.18); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); }
.panel-body { padding: 16px 18px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); vertical-align: top; }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.text-muted { color: var(--text-tertiary, #94a3b8); font-size: 0.78rem; }
.mono { font-family: ui-monospace, 'Consolas', 'Monaco', monospace; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; background: rgba(100,116,139,0.1); color: #64748b; }
.badge.green { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.red { background: rgba(239,68,68,0.1); color: #ef4444; }
.badge.blue { background: rgba(59,130,246,0.1); color: #3b82f6; }
.badge.gray { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.count { background: rgba(99,102,241,0.1); color: var(--accent, #6366f1); }
.action-cell { white-space: nowrap; }
.action-cell .btn { margin-right: 4px; }
.loading-state, .empty-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-box { background: var(--bg-card-solid, #fff); border-radius: 10px; padding: 20px 24px; min-width: 420px; max-width: 92vw; box-shadow: 0 8px 24px rgba(0,0,0,0.15); max-height: 88vh; overflow-y: auto; }
.modal-lg { min-width: 720px; }
.modal-box h3 { margin: 0 0 12px; font-size: 1rem; color: var(--text, #1e293b); }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.form-row textarea { resize: vertical; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.run-meta { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.detail-section { margin-bottom: 12px; }
.result-label { font-size: 0.72rem; color: var(--text-secondary, #64748b); text-transform: uppercase; letter-spacing: 0.3px; margin-bottom: 4px; }
.result-label.danger { color: #ef4444; }
.output-pre { margin: 0; padding: 12px; border-radius: 6px; font-family: ui-monospace, 'Consolas', 'Monaco', monospace; font-size: 0.78rem; white-space: pre-wrap; word-break: break-word; max-height: 320px; overflow: auto; }
.output-pre.dark { background: #1e293b; color: #e2e8f0; }
.output-pre.danger { background: #7f1d1d; color: #fecaca; }
.output-pre.script { background: var(--bg-hover, rgba(0,0,0,0.03)); color: var(--text, #1e293b); }
</style>
