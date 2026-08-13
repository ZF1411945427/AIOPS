<template>
  <div class="mc-page">
    <div class="page-header">
      <h1>🛰️ 多集群管理</h1>
      <p>K8s 多集群 data plane · controller/node 双角色 · 每集群独立 telemetry 通道 · edge 升级联动</p>
    </div>

    <div class="stat-row">
      <div class="stat-card"><span class="stat-num">{{ clusters.length }}</span><span>集群总数</span></div>
      <div class="stat-card"><span class="stat-num">{{ controllerCount }}</span><span>controller</span></div>
      <div class="stat-card"><span class="stat-num">{{ nodeCount }}</span><span>node</span></div>
      <div class="stat-card" :class="{ warn: activeCount === 0 }"><span class="stat-num">{{ activeCount }}</span><span>active 数据面</span></div>
    </div>

    <div class="toolbar">
      <div class="hint">inline <code>k8s_clusters</code> · 关联 type=kubernetes 的 DataSource · 各集群 telemetry 隔离</div>
      <div class="toolbar-right">
        <button class="btn" @click="load()">🔄 刷新检查</button>
        <button class="btn btn-primary" @click="openDialog()">+ 注册集群</button>
      </div>
    </div>

    <table v-if="clusters.length" class="table">
      <thead>
        <tr><th>ID</th><th>集群</th><th>角色</th><th>数据面</th><th>遥测通道</th><th>关联 DataSource</th><th>事件/资产</th><th>edge 版本</th><th>操作</th></tr>
      </thead>
      <tbody>
        <tr v-for="c in clusters" :key="c.id">
          <td>{{ c.id }}</td>
          <td class="c-name">{{ c.name }}</td>
          <td><span class="badge" :class="c.role === 'controller' ? 'role-controller' : ''">{{ roleLabel(c.role) }}</span></td>
          <td><span :class="c.data_plane_status === 'active' ? 'tag-ok' : c.data_plane_status === 'standby' ? 'tag-warn' : 'tag-bad'">{{ c.data_plane_status }}</span></td>
          <td><code>{{ c.telemetry_channel }}</code></td>
          <td>{{ c.datasource_status || '-' }}{{ c.endpoint ? ' (' + c.endpoint + ')' : '' }}</td>
          <td>{{ c.event_total }} 事件 / {{ c.asset_total }} 资产</td>
          <td>{{ c.agent_version || '-' }} → {{ c.target_version || '-' }}</td>
          <td class="ops">
            <button class="btn-icon-sm" title="详情/遥测" @click="openDetail(c)">👁️</button>
            <button class="btn-icon-sm" title="检查" @click="check(c)">✅</button>
            <button class="btn-icon-sm" title="编辑" @click="editCluster(c)">✏️</button>
            <button class="btn-icon-sm danger" title="删除" @click="del(c)">🗑️</button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty-state">
      <div style="font-size:40px;margin-bottom:12px;">🛰️</div>
      <div>暂无集群，点「+ 注册集群」把 K8s DataSource 聚合为命名集群</div>
    </div>

    <el-dialog v-model="showDetail" title="集群遥测详情" width="820px" top="5vh">
      <div v-if="detail" class="detail-card">
        <div class="detail-head">
          <span class="d-name">{{ detail.cluster.name }}</span>
          <span class="badge">{{ roleLabel(detail.cluster.role) }}</span>
          <span :class="detail.cluster.data_plane_status === 'active' ? 'tag-ok' : 'tag-bad'">{{ detail.cluster.data_plane_status }}</span>
          <span class="badge">通道: {{ detail.cluster.telemetry_channel }}</span>
        </div>
        <div class="stat-row inner">
          <div class="stat-card"><span class="stat-num">{{ detail.event_total }}</span><span>事件</span></div>
          <div class="stat-card"><span class="stat-num">{{ detail.asset_total }}</span><span>资产</span></div>
          <div class="stat-card" v-for="(v, k) in detail.asset_by_type" :key="k"><span class="stat-num">{{ v }}</span><span>{{ k }}</span></div>
        </div>
        <h4>最近集群事件</h4>
        <table v-if="detail.events.length" class="table">
          <thead><tr><th>时间</th><th>Kind</th><th>Reason</th><th>级别</th></tr></thead>
          <tbody>
            <tr v-for="e in detail.events.slice(0, 12)" :key="e.id">
              <td>{{ e.created_at || '-' }}</td><td>{{ e.kind }}</td><td>{{ e.reason }}</td>
              <td><span :class="e.severity === 'Critical' || e.severity === 'Error' ? 'tag-bad' : 'tag-ok'">{{ e.severity }}</span></td>
            </tr>
          </tbody>
        </table>
        <div v-else class="none">无集群事件</div>
      </div>
      <template #footer><el-button @click="showDetail = false">关闭</el-button></template>
    </el-dialog>

    <el-dialog v-model="showDialog" :title="editing ? '编辑集群' : '注册集群'" width="500px" top="12vh">
      <el-form label-width="110px">
        <el-form-item label="集群名" required><el-input v-model="form.name" :disabled="!!editing" placeholder="如 prod-cluster" /></el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role" style="width:100%">
            <el-option label="controller（控制器）" value="controller" />
            <el-option label="node（工作节点）" value="node" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联 DataSource">
          <el-select v-model="form.datasource_id" style="width:100%" clearable placeholder="选择 K8s DataSource（可选）">
            <el-option v-for="ds in datasources" :key="ds.id" :label="`${ds.name} (${ds.status || '?'})`" :value="ds.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="数据面状态">
          <el-select v-model="form.data_plane_status" style="width:100%">
            <el-option v-for="s in ['active','standby','error']" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="遥测通道"><el-input v-model="form.telemetry_channel" placeholder="默认 <name>.telemetry" /></el-form-item>
        <el-form-item label="target 版本"><el-input v-model="form.target_version" placeholder="升级目标版本（可选）" /></el-form-item>
        <el-form-item label="agent 版本"><el-input v-model="form.agent_version" placeholder="1.0.0" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save()">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const clusters = ref([])
const datasources = ref([])
const roles = ref(['controller', 'node'])
const showDialog = ref(false)
const showDetail = ref(false)
const editing = ref(null)
const detail = ref(null)
const saving = ref(false)
const form = ref({ name: '', role: 'node', datasource_id: null, data_plane_status: 'active',
  telemetry_channel: '', target_version: '', agent_version: '1.0.0' })

const controllerCount = computed(() => clusters.value.filter(c => c.role === 'controller').length)
const nodeCount = computed(() => clusters.value.filter(c => c.role === 'node').length)
const activeCount = computed(() => clusters.value.filter(c => c.data_plane_status === 'active').length)

function roleLabel(r) { return r === 'controller' ? 'controller' : 'node' }

async function load() {
  try {
    const d = await request.get('/api/k8s-clusters')
    clusters.value = d.clusters || []
    roles.value = d.roles || roles.value
    datasources.value = d.datasources || []
  } catch (e) { ElMessage.error(e.message) }
}

function openDialog(c) {
  editing.value = c || null
  form.value = c
    ? { name: c.name, role: c.role, datasource_id: c.datasource_id, data_plane_status: c.data_plane_status,
        telemetry_channel: c.telemetry_channel, target_version: c.target_version || '', agent_version: c.agent_version }
    : { name: '', role: 'node', datasource_id: null, data_plane_status: 'active', telemetry_channel: '',
        target_version: '', agent_version: '1.0.0' }
  showDialog.value = true
}

async function save() {
  if (!form.value.name.trim()) { ElMessage.warning('集群名不能为空'); return }
  saving.value = true
  try {
    const f = { ...form.value, telemetry_channel: form.value.telemetry_channel || `${form.value.name}.telemetry` }
    if (editing.value) {
      const payload = { role: f.role, datasource_id: f.datasource_id, data_plane_status: f.data_plane_status,
        telemetry_channel: f.telemetry_channel, target_version: f.target_version, agent_version: f.agent_version }
      await request.put(`/api/k8s-clusters/${editing.value.id}`, payload)
      ElMessage.success('已保存')
    } else {
      await request.post('/api/k8s-clusters', f)
      ElMessage.success('集群已注册')
    }
    showDialog.value = false
    await load()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

function editCluster(c) { openDialog(c) }

async function del(c) {
  try {
    await ElMessageBox.confirm(`确认删除集群「${c.name}」？`, '删除集群', { type: 'warning' })
  } catch { return }
  try {
    await request.delete(`/api/k8s-clusters/${c.id}`)
    ElMessage.success('已删除')
    await load()
  } catch (e) { ElMessage.error(e.message) }
}

async function check(c) {
  try {
    const d = await request.post(`/api/k8s-clusters/${c.id}/check`, {})
    if (d.ok) { ElMessage.success(`数据面: ${d.status.data_plane_status}`) }
    await load()
  } catch (e) { ElMessage.error(e.message) }
}

async function openDetail(c) {
  try {
    const d = await request.get(`/api/k8s-clusters/${c.id}`)
    detail.value = d.cluster
    showDetail.value = true
  } catch (e) { ElMessage.error(e.message) }
}

load()
</script>

<style scoped>
.mc-page { padding: 20px; }
.page-header h1 { margin: 0 0 6px; }
.page-header p { color: #8b949e; margin: 0 0 16px; font-size: 13px; }
.stat-row { display: flex; gap: 14px; margin-bottom: 16px; flex-wrap: wrap; }
.stat-row.inner { margin-top: 12px; }
.stat-card { background: #fafafa; border: 1px solid #eee; border-radius: 8px; padding: 12px 20px; min-width: 100px; }
.stat-card.warn .stat-num { color: #d03050; }
.stat-num { display: block; font-size: 22px; font-weight: 600; }
.stat-card span { color: #666; font-size: 12px; }
.toolbar { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 14px; align-items: center; }
.hint { color: #8b949e; font-size: 12px; }
.hint code { background: #f0f2f5; padding: 2px 6px; border-radius: 4px; }
.toolbar-right { display: flex; gap: 10px; }
.btn { padding: 7px 14px; border: 1px solid #d9d9d9; background: #fff; border-radius: 6px; cursor: pointer; }
.btn:hover { border-color: #409eff; color: #409eff; }
.btn-primary { background: #409eff; color: #fff; border-color: #409eff; }
.btn-primary:hover { background: #66b1ff; color: #fff; }
.table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; }
.table th, .table td { border-bottom: 1px solid #f0f0f0; padding: 10px 12px; text-align: left; font-size: 13px; }
.table th { background: #fafafa; color: #666; font-weight: 500; white-space: nowrap; }
.c-name { font-weight: 600; }
.badge { display: inline-block; background: #f0f2f5; border-radius: 4px; padding: 1px 8px; font-size: 12px; color: #57606a; }
.badge.role-controller { background: #e6f7ff; color: #1890ff; }
.tag-ok { color: #52c41a; font-weight: 600; font-size: 12px; }
.tag-warn { color: #d48806; font-weight: 600; font-size: 12px; }
.tag-bad { color: #cf1322; font-weight: 600; font-size: 12px; }
.ops { white-space: nowrap; }
.btn-icon-sm { border: 1px solid #d9d9d9; background: #fff; border-radius: 4px; width: 26px; height: 26px; cursor: pointer; margin-right: 4px; }
.btn-icon-sm:hover { border-color: #409eff; }
.btn-icon-sm.danger:hover { border-color: #d03050; }
.empty-state { text-align: center; color: #8b949e; padding: 60px 0; background: #fafafa; border-radius: 8px; }
.detail-card { border: 1px solid #eee; border-radius: 8px; padding: 16px; }
.detail-head { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.d-name { font-size: 18px; font-weight: 700; }
.detail-card h4 { margin: 16px 0 8px; }
.none { color: #8b949e; font-size: 13px; }
</style>
