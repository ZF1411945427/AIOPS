<template>
  <div class="store-page">
    <div class="page-header">
      <h1>📦 组件应用商店</h1>
      <p>官方组件一键部署 · 支持传统 / Docker / K8S(Helm) / 高可用 四种方式 · 配置优化 / 高可用 / 漏洞 / AI 分析</p>
    </div>

    <!-- 统计 -->
    <div class="stat-grid">
      <div class="stat-card"><div class="val blue">{{ stats.total_components }}</div><div class="lbl">可用组件</div></div>
      <div class="stat-card"><div class="val">{{ stats.total_installs }}</div><div class="lbl">安装记录</div></div>
      <div class="stat-card"><div class="val ok">{{ stats.running_installs }}</div><div class="lbl">运行中</div></div>
      <div class="stat-card"><div class="val warn">{{ stats.by_category ? Object.keys(stats.by_category).length : 0 }}</div><div class="lbl">组件分类</div></div>
    </div>

    <div class="tab-bar">
      <div class="tab-item" :class="{active: tab==='catalog'}" @click="tab='catalog'">组件目录</div>
      <div class="tab-item" :class="{active: tab==='installs'}" @click="tab='installs'; loadInstalls()">安装记录</div>
    </div>

    <!-- ═══ 组件目录 Tab ═══ -->
    <div v-show="tab==='catalog'" class="pane">
      <div class="filter-bar">
        <select v-model="filterCat" @change="loadCatalog">
          <option value="">全部分类</option>
          <option value="database">数据库</option>
          <option value="cache">缓存</option>
          <option value="message">消息</option>
          <option value="web">Web</option>
          <option value="observability">可观测</option>
        </select>
        <input v-model="keyword" placeholder="搜索组件..." @input="loadCatalog" />
      </div>
      <div v-if="!loading && comps.length===0" class="empty">暂无组件</div>
      <div v-else class="comp-grid">
        <div v-for="c in comps" :key="c.id" class="comp-card">
          <div class="comp-head">
            <span class="icon">{{ c.icon }}</span>
            <div class="title-box">
              <div class="name">{{ c.display_name }}</div>
              <div class="ver">{{ c.name }} · v{{ c.version }}</div>
            </div>
          </div>
          <div class="desc">{{ c.description }}</div>
          <div class="deploy-tags">
            <span v-for="d in c.deploy_types" :key="d" class="dt-tag">{{ deployLabel(d) }}</span>
          </div>
          <div class="foot">
            <span class="complexity">{{ c.complexity }}</span>
            <button class="btn btn-primary btn-sm" @click="openDeploy(c)">一键部署</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ 安装记录 Tab ═══ -->
    <div v-show="tab==='installs'" class="pane">
      <div class="inst-toolbar">
        <span class="inst-tip">对运行中的组件实例执行批量四合一体检</span>
        <button class="btn btn-primary btn-sm" @click="runBatchFullCheck">🔍 一键批量体检</button>
      </div>
      <div v-if="!installs.length" class="empty">暂无安装记录，去「组件目录」一键部署吧</div>
      <div v-else class="inst-list">
        <div v-for="it in installs" :key="it.id" class="inst-card">
          <div class="inst-head">
            <span class="ic">{{ iconOf(it.component_name) }}</span>
            <div>
              <div class="iname">{{ it.component_name }}</div>
              <div class="imeta">{{ it.asset_name }} · {{ deployLabel(it.deploy_type) }} · {{ it.port || '' }}</div>
            </div>
            <div class="status-group">
              <span class="st" :class="'st-'+it.status">{{ ut(it.status) }}</span>
              <span class="st2" :class="'st2-'+it.health_status">{{ it.health_status }}</span>
            </div>
          </div>
          <div class="ops">
            <button class="btn btn-sm btn-primary" @click="runFullCheck(it)">🔍 全面体检</button>
            <button class="btn btn-sm" @click="runCheck(it,'health')">🧭 高可用</button>
            <button class="btn btn-sm" @click="runCheck(it,'config')">⚙️ 配置优化</button>
            <button class="btn btn-sm" @click="runCheck(it,'vuln')">⚠️ 漏洞</button>
            <button class="btn btn-sm" @click="runCheck(it,'analyze')">🤖 AI 分析</button>
            <button class="btn btn-sm btn-danger" @click="delInstall(it)">删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ 部署弹窗 ═══ -->
    <div v-if="deployComp" class="mask">
      <div class="modal">
        <div class="mhead">
          <h3>{{ deployComp.icon }} {{ deployComp.display_name }} 一键部署</h3>
          <button class="mclose" @click="deployComp=null">✕</button>
        </div>
        <div class="mbody">
          <div class="field">
            <label>目标机 (Asset) *</label>
            <select v-model="deployForm.asset_id">
              <option :value="0">请选择目标机</option>
              <option v-for="a in assets" :key="a.id" :value="a.id">{{ a.name }} ({{ a.ip }})</option>
            </select>
          </div>
          <div class="field">
            <label>部署方式 *</label>
            <div class="dt-select">
              <button v-for="d in deployComp.deploy_types" :key="d" class="dt-btn"
                :class="{active: deployForm.deploy_type===d}" @click="selectDeployType(d)">
                {{ deployLabel(d) }}
              </button>
            </div>
          </div>
          <div class="field" v-if="deployForm.deploy_type==='helm'">
            <label>命名空间 / Release</label>
            <div class="row2"><input v-model="deployForm.namespace" placeholder="default" /><input v-model="deployForm.release" placeholder="release 名" /></div>
          </div>
          <div class="field">
            <label>部署路径</label>
            <input v-model="deployForm.deploy_path" placeholder="如 /data/aiops-components/redis(留空自动生成)" />
          </div>
          <details class="proxy-block">
            <summary>🌐 网络代理(可选, 拉取 docker 镜像需要)</summary>
            <div class="proxy-grid">
              <div class="field">
                <label>HTTP 代理</label>
                <input v-model="deployForm.http_proxy" placeholder="如 http://11.0.1.1:7897" />
              </div>
              <div class="field">
                <label>HTTPS 代理</label>
                <input v-model="deployForm.https_proxy" placeholder="留空=用 HTTP 代理" />
              </div>
              <div class="field">
                <label>NO_PROXY</label>
                <input v-model="deployForm.no_proxy" placeholder="127.0.0.1,localhost,.local" />
              </div>
            </div>
            <div class="proxy-hint">Docker 部署时写入目标机 docker daemon, 使 docker pull 走代理拉取镜像(无外网环境必填)</div>
          </details>
          <div class="field">
            <label>部署配方预览</label>
            <pre class="recipe">{{ deployRecipe || '选择目标机和部署方式后生成' }}</pre>
          </div>
        </div>
        <div class="mfoot">
          <button class="btn" @click="deployComp=null">取消</button>
          <button class="btn btn-primary" :disabled="!deployForm.asset_id||!deployRecipe" @click="doDeploy">确认部署</button>
        </div>
      </div>
    </div>

    <!-- ═══ 检查结果抽屉 ═══ -->
    <div v-if="resultView" class="mask">
      <div class="modal wide">
        <div class="mhead">
          <h3>{{ resultView.title }}</h3>
          <button class="mclose" @click="resultView=null">✕</button>
        </div>
        <div class="mbody">
          <pre class="result">{{ resultView.body }}</pre>
        </div>
        <div class="mfoot"><button class="btn" @click="resultView=null">关闭</button></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'

const API = '/component-market/api'
const ASSET_API = '/assets/api'

const tab = ref('catalog')
const comps = ref([])
const stats = ref({ total_components:0, total_installs:0, running_installs:0, by_category:{} })
const installs = ref([])
const assets = ref([])
const filterCat = ref('')
const keyword = ref('')
const loading = ref(false)
const deployComp = ref(null)
const deployForm = ref({ asset_id:0, deploy_type:'', namespace:'default', release:'', deploy_path:'', http_proxy:'', https_proxy:'', no_proxy:'127.0.0.1,localhost,.local' })
const deployRecipe = ref('')
const resultView = ref(null)

const deployLabels = { native:'🐧 传统', docker:'🐳 Docker', helm:'☸️ K8S/Helm', ha:'🛡️ 高可用' }
function deployLabel(d) { return deployLabels[d] || d }
const iconBy = { mysql:'🐬', redis:'🔴', kafka:'📨', rabbitmq:'🐇', nginx:'🌐', elasticsearch:'🔎', mongodb:'🍃', postgresql:'🐘' }
function iconOf(n) { return iconBy[n] || '📦' }
const statusText = { deploying:'部署中', running:'运行中', failed:'失败', stopped:'已停止' }
function ut(s) { return statusText[s] || s }

async function loadStats() { try { const {data}=await axios.get(`${API}/stats`); stats.value=data } catch(e){} }
async function loadCatalog() {
  loading.value=true
  try {
    const {data}=await axios.get(`${API}/catalog`, { params:{ category:filterCat.value, keyword:keyword.value } })
    comps.value=data.items||[]
  } finally { loading.value=false }
}
async function loadInstalls() {
  try { const {data}=await axios.get(`${API}/installs`); installs.value=data.items||[] } catch(e){}
}
async function loadAssets() {
  try {
    const {data}=await axios.get(`${ASSET_API}/list`, { params:{ page_size:500 } })
    assets.value=(data.items||data.assets||data.list||[])
  } catch(e){}
}
async function loadAll() { loadStats(); loadCatalog(); loadAssets() }

function openDeploy(c) {
  deployComp.value=c
  deployForm.value={ asset_id:0, deploy_type:(c.deploy_types||[])[0]||'docker', namespace:'default', release:'', deploy_path:'', http_proxy:'', https_proxy:'', no_proxy:'127.0.0.1,localhost,.local' }
  deployRecipe.value=''
}
async function selectDeployType(d) {
  deployForm.value.deploy_type=d
  await renderRecipe()
}
async function renderRecipe() {
  const c=deployComp.value; const a=assets.value.find(x=>x.id===deployForm.value.asset_id)
  try {
    const {data}=await axios.get(`${API}/render`, { params:{
      component_id:c.id, deploy_type:deployForm.value.deploy_type,
      host:a?`${a.ip}`:'', namespace:deployForm.value.namespace, release:deployForm.value.release } })
    deployRecipe.value=data.content || data.error || ''
  } catch(e){ deployRecipe.value='渲染失败' }
}
async function doDeploy() {
  try {
    const {data}=await axios.post(`${API}/deploy`, {
      component_id:deployComp.value.id, asset_id:deployForm.value.asset_id,
      deploy_type:deployForm.value.deploy_type, namespace:deployForm.value.namespace,
      release:deployForm.value.release, deploy_path:deployForm.value.deploy_path,
      http_proxy:deployForm.value.http_proxy, https_proxy:deployForm.value.https_proxy,
      no_proxy:deployForm.value.no_proxy,
    })
    if(data.ok){
      ElMessage.success(data.component && data.deploy_log && String(data.deploy_log).includes('Up')
        ? `${data.component} 部署成功` : `已创建 ${data.component} ${data.deploy_type} 部署记录`)
      deployComp.value=null
      tab.value='installs'; loadInstalls()
      if(data.deploy_log) resultView.value={ title:`🚀 部署结果 · ${data.component}`, body: data.deploy_log }
    } else ElMessage.error(data.error||'部署失败')
  } catch(e){ ElMessage.error('部署失败') }
}
async function runBatchFullCheck() {
  if(!confirm('对所有运行中的组件实例执行批量四合一体检？')) return
  try {
    const {data}=await axios.post(`${API}/batch-full-check`)
    if(!data.ok){ ElMessage.error(data.error||'批量体检失败'); return }
    const r=data.result
    resultView.value={ title:`🔍 批量体检报告 (共 ${r.total} 实例)`, body: JSON.stringify(r,null,2) }
    loadInstalls()
  } catch(e){ ElMessage.error('批量体检失败') }
}
async function runFullCheck(it) {
  try {
    const {data}=await axios.post(`${API}/installs/${it.id}/full-check`)
    if(!data.ok){ ElMessage.error(data.error||'体检失败'); return }
    resultView.value={ title:`🔍 全面体检报告 · ${it.component_name}`, body: JSON.stringify(data.result,null,2) }
    loadInstalls()
  } catch(e){ ElMessage.error('体检失败') }
}
async function runCheck(it, kind) {
  try {
    const {data}=await axios.post(`${API}/installs/${it.id}/${kind}`)
    if(!data.ok){ ElMessage.error(data.error||'检查失败'); return }
    const r=data.result
    resultView.value={ title: resultTitle(kind, it.component_name), body: JSON.stringify(r,null,2) }
    loadInstalls()
  } catch(e){ ElMessage.error('检查失败') }
}
function resultTitle(kind, name){
  return { health:`🧭 高可用检查 · ${name}`, config:`⚙️ 配置优化 · ${name}`, vuln:`⚠️ 漏洞检查 · ${name}`, analyze:`🤖 AI 健康分析 · ${name}` }[kind]||'检查结果'
}
async function delInstall(it){
  if(!confirm(`删除安装记录 ${it.component_name}@${it.asset_name}?`)) return
  try{ await axios.delete(`${API}/installs/${it.id}`); loadInstalls() }catch(e){}
}

onMounted(()=>{ loadAll() })
</script>

<style scoped>
.store-page{padding:20px;color:#1f2937}
.page-header h1{margin:0 0 4px;font-size:20px}
.page-header p{margin:0 0 16px;color:#6b7280;font-size:13px}
.stat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px}
.stat-card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:12px;text-align:center}
.val{font-size:24px;font-weight:700}.val.blue{color:#3b82f6}.val.ok{color:#10b981}.val.warn{color:#f59e0b}
.lbl{font-size:12px;color:#6b7280}
.tab-bar{display:flex;gap:0;border-bottom:2px solid #e5e7eb;margin-bottom:16px}
.tab-item{padding:10px 18px;cursor:pointer;color:#6b7280;border-bottom:2px solid transparent;margin-bottom:-2px}
.tab-item.active{color:#3b82f6;border-bottom-color:#3b82f6;font-weight:600}
.filter-bar{display:flex;gap:10px;margin-bottom:16px}
.filter-bar select,.filter-bar input{padding:7px 10px;border:1px solid #d1d5db;border-radius:6px;font-size:13px}
.filter-bar select{width:140px}
.comp-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.comp-card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:14px}
.comp-head{display:flex;gap:10px;align-items:center;margin-bottom:8px}
.icon{font-size:26px}.title-box .name{font-weight:600;font-size:15px}.ver{font-size:11px;color:#9ca3af}
.desc{font-size:12px;color:#4b5563;min-height:32px;margin-bottom:10px}
.deploy-tags{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}
.dt-tag{font-size:11px;background:#eff6ff;color:#1e40af;padding:2px 8px;border-radius:10px}
.foot{display:flex;justify-content:space-between;align-items:center}
.complexity{font-size:11px;color:#9ca3af}
.inst-toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
.inst-tip{font-size:12px;color:#9ca3af}
.inst-list{display:flex;flex-direction:column;gap:12px}.inst-card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:14px;display:flex;justify-content:space-between;align-items:center;gap:12px}
.inst-head{display:flex;gap:12px;align-items:center}
.ic{font-size:24px}.iname{font-weight:600}.imeta{font-size:12px;color:#6b7280}
.status-group{display:flex;gap:6px}
.st{padding:2px 8px;border-radius:10px;font-size:11px;background:#e5e7eb;color:#374151}
.st-st{color:#1e40af}
.st2{padding:2px 8px;border-radius:10px;font-size:11px}
.st2-healthy{background:#d1fae5;color:#065f46}.st2-unhealthy{background:#fee2e2;color:#991b1b}.st2-unknown{background:#f3f4f6;color:#6b7280}
.ops{display:flex;gap:6px;flex-wrap:wrap}
.mask{position:fixed;inset:0;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;z-index:100}
.modal{background:#fff;border-radius:12px;width:620px;max-width:94vw;max-height:88vh;display:flex;flex-direction:column}
.modal.wide{width:760px}
.mhead{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;border-bottom:1px solid #e5e7eb}
.mhead h3{margin:0;font-size:16px}.mclose{background:none;border:none;font-size:18px;cursor:pointer}
.mbody{padding:18px 20px;overflow-y:auto}
.mfoot{display:flex;justify-content:flex-end;gap:10px;padding:14px 20px;border-top:1px solid #e5e7eb}
.field{margin-bottom:14px}.field label{display:block;font-size:13px;font-weight:600;margin-bottom:6px}
.field select,.field input{width:100%;padding:8px 10px;border:1px solid #d1d5db;border-radius:6px;box-sizing:border-box;font-size:13px}
.dt-select{display:flex;gap:8px}.dt-btn{padding:8px 14px;border:1px solid #d1d5db;background:#fff;border-radius:8px;cursor:pointer;font-size:13px}
.dt-btn.active{background:#3b82f6;color:#fff;border-color:#3b82f6}
.row2{display:flex;gap:10px}
.proxy-block{border:1px dashed #dcdfe6;border-radius:8px;padding:10px 12px;margin-bottom:14px;background:#fafbfc}
.proxy-block summary{cursor:pointer;font-size:13px;color:#3b82f6;font-weight:600;user-select:none}
.proxy-grid{display:grid;grid-template-columns:1fr;gap:10px;margin-top:10px}
.proxy-hint{font-size:12px;color:#9ca3af;margin-top:4px}
.recipe{background:#0f172a;color:#e2e8f0;border-radius:8px;padding:12px;font-size:12px;max-height:260px;overflow:auto;white-space:pre-wrap}
.result{background:#0f172a;color:#e2e8f0;border-radius:8px;padding:14px;font-size:12px;max-height:60vh;overflow:auto;white-space:pre-wrap}
.empty{text-align:center;padding:50px;color:#6b7280}
.btn{padding:8px 14px;border:1px solid #d1d5db;background:#fff;border-radius:6px;cursor:pointer;font-size:13px}
.btn-primary{background:#3b82f6;color:#fff;border-color:#3b82f6}
.btn-danger{color:#ef4444;border-color:#fecaca}
.btn-sm{padding:5px 10px;font-size:12px}
.btn:disabled{opacity:.5;cursor:not-allowed}
</style>
