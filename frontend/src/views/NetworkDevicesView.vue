<template>
  <div class="net-page">
    <div class="page-header">
      <h1>🌐 网络设备管理</h1>
      <p>SNMP 管理 · 连通校验 / 接口轮询(IF-MIB) / 邻居发现(LLDP/CDP) / 主机-交换机端口链路映射</p>
    </div>

    <div class="stat-row">
      <div class="stat-card"><span class="stat-num">{{ devices.length }}</span><span>设备总数</span></div>
      <div class="stat-card"><span class="stat-num">{{ upCount }}</span><span>可达(ok)</span></div>
      <div class="stat-card" :class="{ warn: downCount > 0 }"><span class="stat-num">{{ downCount }}</span><span>不可达/错误</span></div>
    </div>

    <div class="toolbar">
      <input v-model="search" class="search-input" placeholder="搜索设备名 / IP..." />
      <div class="toolbar-right">
        <button class="btn" @click="load()">🔄 刷新</button>
        <button class="btn" @click="openMap()">🔗 主机链路映射</button>
        <button class="btn btn-primary" @click="openDialog()">+ 添加设备</button>
      </div>
    </div>

    <table v-if="devices.length" class="table">
      <thead>
        <tr><th>ID</th><th>设备</th><th>IP</th><th>类型</th><th>厂商/型号</th><th>状态</th><th>最近轮询</th><th>接口</th><th>邻居</th><th>操作</th></tr>
      </thead>
      <tbody>
        <tr v-for="d in filtered" :key="d.id">
          <td>{{ d.id }}</td>
          <td class="d-name">{{ d.name }}</td>
          <td>{{ d.ip }}</td>
          <td><span class="badge">{{ typeLabel(d.device_type) }}</span></td>
          <td class="vm">{{ d.vendor || '-' }}<span v-if="d.model" class="sub"> / {{ d.model }}</span></td>
          <td><span :class="d.status === 'ok' ? 'tag-ok' : 'tag-bad'">{{ d.status }}</span></td>
          <td>{{ (d.last_poll_at || '').slice(0, 19).replace('T', ' ') || '-' }}</td>
          <td>{{ d.if_count ?? '-' }}</td>
          <td>{{ d.nb_count ?? '-' }}</td>
          <td class="ops">
            <button class="btn-icon-sm" title="连通校验" @click="validate(d)">🔍</button>
            <button class="btn-icon-sm" title="接口轮询" @click="poll(d)">📊</button>
            <button class="btn-icon-sm" title="邻居发现" @click="discover(d)">🕸️</button>
            <button class="btn-icon-sm" title="详情" @click="showDeviceDetail(d)">👁️</button>
            <button class="btn-icon-sm danger" title="删除" @click="del(d)">🗑️</button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty-state">
      <div style="font-size:40px;margin-bottom:12px;">🌐</div>
      <div>暂无网络设备，点「+ 添加设备」开始纳管交换机/路由器等</div>
    </div>

    <el-dialog v-model="showDialog" :title="editing ? '编辑设备' : '添加设备'" width="540px" top="10vh">
      <el-form label-width="110px">
        <el-form-item label="设备名" required><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="管理 IP" required><el-input v-model="form.ip" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.device_type" style="width:100%">
            <el-option v-for="t in deviceTypes" :key="t" :label="typeLabel(t)" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="SNMP 版本">
          <el-select v-model="form.snmp_version" style="width:100%">
            <el-option label="v2c" value="v2c" /><el-option label="v1" value="v1" />
          </el-select>
        </el-form-item>
        <el-form-item label="Community"><el-input v-model="form.community" placeholder="public" /></el-form-item>
        <el-form-item label="端口"><el-input-number v-model="form.port" :min="1" :max="65535" /></el-form-item>
        <el-form-item label="厂商/型号">
          <div class="duo"><el-input v-model="form.vendor" placeholder="厂商" /><el-input v-model="form.model" placeholder="型号" /></div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save()">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showDetail" title="设备详情" width="820px" top="5vh">
      <div v-if="detail" class="detail-card">
        <div class="detail-head">
          <span class="d-name">{{ detail.name }}</span>
          <span class="badge">{{ detail.ip }}</span>
          <span :class="detail.status === 'ok' ? 'tag-ok' : 'tag-bad'">{{ detail.status }}</span>
          <span class="badge">{{ detail.vendor }} {{ detail.model }}</span>
        </div>
        <div class="sec">
          <div class="sec-head">📊 接口 ({{ detail.interfaces.length }}) · up {{ detail.up_ifaces }}</div>
          <table v-if="detail.interfaces.length" class="table">
            <thead><tr><th>Idx</th><th>接口</th><th>MAC</th><th>速度</th><th>状态</th><th>In</th><th>Out</th><th>InErr</th></tr></thead>
            <tbody>
              <tr v-for="i in detail.interfaces" :key="i.id">
                <td>{{ i.if_index }}</td><td>{{ i.name }}</td><td class="vm">{{ i.mac || '-' }}</td>
                <td>{{ fmtSpeed(i.speed) }}</td>
                <td><span :class="i.up ? 'tag-ok' : 'tag-bad'">{{ i.up ? 'up' : 'down' }}</span></td>
                <td>{{ fmtBytes(i.in_octets) }}</td><td>{{ fmtBytes(i.out_octets) }}</td><td>{{ i.in_errors }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="none">未轮询接口（点 📊 执行轮询）</div>
        </div>
        <div class="sec">
          <div class="sec-head">🕸️ 邻居 ({{ detail.neighbors.length }})</div>
          <table v-if="detail.neighbors.length" class="table">
            <thead><tr><th>本端接口</th><th>邻居设备</th><th>邻居端口</th><th>协议</th></tr></thead>
            <tbody>
              <tr v-for="n in detail.neighbors" :key="n.id">
                <td>{{ n.local_interface }}</td><td>{{ n.neighbor_device }}</td><td>{{ n.neighbor_port }}</td><td><span class="badge">{{ n.proto }}</span></td>
              </tr>
            </tbody>
          </table>
          <div v-else class="none">未发现邻居（点 🕸️ 执行发现）</div>
        </div>
      </div>
      <template #footer><el-button @click="showDetail = false">关闭</el-button></template>
    </el-dialog>

    <el-dialog v-model="showMap" title="主机-交换机端口链路映射" width="560px" top="12vh">
      <div class="map-row">
        <el-input v-model="mapIp" placeholder="输入主机 IP，反查其接入的交换机端口" />
        <button class="btn btn-primary" @click="doMap()">查询</button>
      </div>
      <div v-if="mapResult" class="map-result">
        <p class="map-host">主机 <code>{{ mapResult.host_ip }}</code> · MAC <code>{{ mapResult.host_mac }}</code> · {{ mapResult.total }} 条链路</p>
        <table v-if="mapResult.links.length" class="table">
          <thead><tr><th>交换机</th><th>交换机 IP</th><th>端口</th><th>端口 MAC</th><th>状态</th></tr></thead>
          <tbody>
            <tr v-for="(l, i) in mapResult.links" :key="i">
              <td>{{ l.switch }}</td><td>{{ l.switch_ip }}</td><td>{{ l.port }}</td><td>{{ l.port_mac }}</td>
              <td><span :class="l.status === 'up' ? 'tag-ok' : 'tag-bad'">{{ l.status }}</span></td>
            </tr>
          </tbody>
        </table>
        <div v-else class="none">未匹配到链路（需先对交换机做接口轮询以采集端口 MAC）</div>
      </div>
      <template #footer><el-button @click="showMap = false">关闭</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '@/api/request'

const devices = ref([])
const deviceTypes = ref(['switch', 'router', 'firewall', 'ap', 'other'])
const search = ref('')
const showDialog = ref(false)
const showDetail = ref(false)
const showMap = ref(false)
const editing = ref(null)
const detail = ref(null)
const saving = ref(false)
const mapIp = ref('')
const mapResult = ref(null)
const form = ref({})

const filtered = computed(() => {
  const q = (search.value || '').toLowerCase()
  if (!q) return devices.value
  return devices.value.filter(d => d.name.toLowerCase().includes(q) || d.ip.toLowerCase().includes(q))
})
const upCount = computed(() => devices.value.filter(d => d.status === 'ok').length)
const downCount = computed(() => devices.value.filter(d => d.status !== 'ok').length)

function typeLabel(t) { return { switch: '交换机', router: '路由器', firewall: '防火墙', ap: 'AP', other: '其他' }[t] || t }
function fmtBytes(n) { n = Number(n || 0); if (n >= 1e9) return (n / 1e9).toFixed(1) + 'GB'; if (n >= 1e6) return (n / 1e6).toFixed(1) + 'MB'; return n.toFixed(0) + 'B' }
function fmtSpeed(s) { s = Number(s || 0); if (s >= 1e9) return (s / 1e9).toFixed(1) + 'G'; if (s >= 1e6) return (s / 1e6).toFixed(0) + 'M'; return s + '' }

async function load() {
  try {
    const d = await request.get('/api/network/devices')
    devices.value = d.devices || []
    deviceTypes.value = d.device_types || deviceTypes.value
  } catch (e) { ElMessage.error(e.message) }
}

function openDialog(d) {
  editing.value = d || null
  form.value = d
    ? { ...d }
    : { name: '', ip: '', device_type: 'switch', snmp_version: 'v2c', community: 'public', port: 161, vendor: '', model: '' }
  showDialog.value = true
}

async function save() {
  if (!form.value.name.trim() || !form.value.ip.trim()) { ElMessage.warning('设备名和 IP 不能为空'); return }
  saving.value = true
  try {
    if (editing.value) {
      await request.put(`/api/network/devices/${editing.value.id}`, form.value)
      ElMessage.success('已保存')
    } else {
      await request.post('/api/network/devices', form.value)
      ElMessage.success('设备已添加')
    }
    showDialog.value = false
    await load()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

async function validate(d) {
  try {
    const r = await request.post(`/api/network/devices/${d.id}/validate`, {})
    if (r.ok && r.result.ok) { ElMessage.success(`SNMP 校验通过: ${r.result.sys_descr || 'ok'}`) }
    else { ElMessage.error(r.result?.error || '校验失败') }
    await load()
  } catch (e) { ElMessage.error(e.message) }
}

async function poll(d) {
  try {
    const r = await request.post(`/api/network/devices/${d.id}/poll`, {})
    if (r.ok && r.result.ok) { ElMessage.success(`接口轮询完成: ${r.result.total_ifaces} 个 (up ${r.result.up_ifaces})`) }
    else { ElMessage.error(r.result?.error || '轮询失败') }
    await load()
  } catch (e) { ElMessage.error(e.message) }
}

async function discover(d) {
  try {
    const r = await request.post(`/api/network/devices/${d.id}/discover`, {})
    if (r.ok && r.result.ok) { ElMessage.success(`发现 ${r.result.total} 个邻居`) }
    else { ElMessage.error(r.result?.error || '邻居发现失败') }
    await load()
  } catch (e) { ElMessage.error(e.message) }
}

async function showDeviceDetail(d) {
  try {
    const r = await request.get(`/api/network/devices/${d.id}`)
    detail.value = r.device
    showDetail.value = true
  } catch (e) { ElMessage.error(e.message) }
}

async function del(d) {
  try {
    await ElMessageBox.confirm(`确认删除网络设备「${d.name}」？`, '删除设备', { type: 'warning' })
  } catch { return }
  try {
    await request.delete(`/api/network/devices/${d.id}`)
    ElMessage.success('已删除')
    await load()
  } catch (e) { ElMessage.error(e.message) }
}

function openMap() { mapIp.value = ''; mapResult.value = null; showMap.value = true }
async function doMap() {
  if (!mapIp.value.trim()) { ElMessage.warning('请输入主机 IP'); return }
  try {
    const r = await request.post('/api/network/map-links', { host_ip: mapIp.value })
    mapResult.value = r.result
  } catch (e) { ElMessage.error(e.message) }
}

load()
</script>

<style scoped>
.net-page { padding: 20px; }
.page-header h1 { margin: 0 0 6px; }
.page-header p { color: #8b949e; margin: 0 0 16px; font-size: 13px; }
.stat-row { display: flex; gap: 14px; margin-bottom: 16px; }
.stat-card { background: #fafafa; border: 1px solid #eee; border-radius: 8px; padding: 12px 20px; min-width: 110px; }
.stat-card.warn .stat-num { color: #d03050; }
.stat-num { display: block; font-size: 22px; font-weight: 600; }
.stat-card span { color: #666; font-size: 12px; }
.toolbar { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.search-input { flex: 1; max-width: 300px; padding: 8px 12px; border: 1px solid #d9d9d9; border-radius: 6px; }
.toolbar-right { display: flex; gap: 10px; }
.btn { padding: 7px 14px; border: 1px solid #d9d9d9; background: #fff; border-radius: 6px; cursor: pointer; }
.btn:hover { border-color: #409eff; color: #409eff; }
.btn-primary { background: #409eff; color: #fff; border-color: #409eff; }
.btn-primary:hover { background: #66b1ff; color: #fff; }
.table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; }
.table th, .table td { border-bottom: 1px solid #f0f0f0; padding: 9px 11px; text-align: left; font-size: 13px; }
.table th { background: #fafafa; color: #666; font-weight: 500; white-space: nowrap; }
.d-name { font-weight: 600; }
.vm { font-size: 12px; color: #57606a; }
.vm .sub { color: #8b949e; }
.badge { display: inline-block; background: #f0f2f5; border-radius: 4px; padding: 1px 8px; font-size: 12px; color: #57606a; }
.tag-ok { color: #52c41a; font-weight: 600; font-size: 12px; }
.tag-bad { color: #cf1322; font-weight: 600; font-size: 12px; }
.ops { white-space: nowrap; }
.btn-icon-sm { border: 1px solid #d9d9d9; background: #fff; border-radius: 4px; width: 26px; height: 26px; cursor: pointer; margin-right: 4px; }
.btn-icon-sm:hover { border-color: #409eff; }
.btn-icon-sm.danger:hover { border-color: #d03050; }
.empty-state { text-align: center; color: #8b949e; padding: 60px 0; background: #fafafa; border-radius: 8px; }
.duo { display: flex; gap: 8px; width: 100%; }
.detail-card { border: 1px solid #eee; border-radius: 8px; padding: 16px; }
.detail-head { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.d-name { font-size: 18px; font-weight: 700; }
.sec { margin-top: 14px; }
.sec-head { font-weight: 600; margin-bottom: 6px; font-size: 14px; }
.none { color: #8b949e; font-size: 13px; padding: 8px 0; }
.map-row { display: flex; gap: 10px; }
.map-result { margin-top: 14px; }
.map-host { font-size: 13px; color: #57606a; }
</style>
