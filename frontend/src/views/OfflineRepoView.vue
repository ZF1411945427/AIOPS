<template>
  <div class="offline-page">
    <div class="page-header">
      <div class="page-header-row">
        <div>
          <h1>离线仓库</h1>
          <p>离线包管理 · 私有镜像仓库(Registry) · 系统包源(deb/rpm) · 对标 Pixiu builder serve</p>
        </div>
        <button class="btn btn-guide" @click="showGuide = true">📖 操作说明</button>
      </div>
    </div>

    <div class="cfg-tabs">
      <button :class="['tab', activeTab === 'bundles' && 'active']" @click="switchTab('bundles')">📦 离线包</button>
      <button :class="['tab', activeTab === 'registries' && 'active']" @click="switchTab('registries')">🖼️ 私有镜像仓库</button>
      <button :class="['tab', activeTab === 'sources' && 'active']" @click="switchTab('sources')">📃 系统包源</button>
      <button :class="['tab', activeTab === 'proxies' && 'active']" @click="switchTab('proxies')">📡 代理配置</button>
      <button :class="['tab', activeTab === 'health' && 'active']" @click="switchTab('health')">🩺 健康状态</button>
    </div>

    <!-- ═══════════════ 离线包 ═══════════════ -->
    <div v-show="activeTab === 'bundles'">
      <div class="toolbar">
        <button class="btn btn-primary" @click="openUpload">⬆ 上传离线包</button>
        <input v-model="search" class="input" style="width:200px" placeholder="搜名称" @input="loadBundles(1)" />
        <select v-model="statusFilter" class="input" style="width:130px" @change="loadBundles(1)">
          <option value="">全部状态</option>
          <option value="pending">待加载</option>
          <option value="loading">加载中</option>
          <option value="loaded">已加载</option>
          <option value="failed">失败</option>
        </select>
        <button class="btn" @click="loadBundles(1)">刷新</button>
      </div>

      <div v-if="loading" class="loading">加载中...</div>

      <div v-else-if="bundles.length === 0" class="empty-state">
        <p>暂无离线包，点击「上传离线包」导入 .tar.gz</p>
        <p class="hint">包结构：顶层 <code>images/</code>（镜像 tar）与 <code>packages/</code>（deb/rpm）目录</p>
      </div>

      <div v-else class="card-grid">
        <div v-for="b in bundles" :key="b.id" class="bundle-card">
          <div class="bundle-head">
            <span class="bundle-name">{{ b.name }}</span>
            <span class="status-badge" :class="b.status">{{ statusText(b.status) }}</span>
          </div>
          <div class="bundle-meta">
            <span v-if="b.version" class="meta-chip">版本 {{ b.version }}</span>
            <span v-if="b.os_type" class="meta-chip">{{ osLabel(b.os_type) }} {{ b.os_version }}</span>
            <span class="meta-chip">{{ typeLabel(b.bundle_type) }} · {{ b.file_size_display }}</span>
          </div>
          <div class="bundle-desc">{{ b.description || '—' }}</div>
          <div v-if="b.status === 'loaded'" class="bundle-stats">
            <div class="mini-stat"><b>{{ b.loaded_images }}</b><span>/{{ b.total_images }} 镜像</span></div>
            <div class="mini-stat"><b>{{ b.loaded_packages }}</b><span> 软件包</span></div>
          </div>
          <div v-else class="bundle-stats">
            <div class="mini-stat"><b>{{ b.loaded_images }}</b><span>/{{ b.total_images }} 镜像</span></div>
          </div>
          <div class="bundle-msg" v-if="b.status === 'failed' || b.status === 'loading'">{{ b.load_message }}</div>
          <div class="bundle-actions">
            <button class="btn btn-sm" @click="openImages(b)">镜像</button>
            <button class="btn btn-sm" @click="openPkgs(b)">包源</button>
            <button class="btn btn-sm btn-primary" :disabled="b.status === 'loading' || b.status === 'loaded'" @click="loadBundle(b)">加载</button>
            <button class="btn btn-sm btn-delete" @click="delBundle(b)">删除</button>
          </div>
        </div>
      </div>

      <div v-if="total > 0" class="pagination">
        <button class="btn btn-sm" :disabled="page <= 1" @click="prevPage">上一页</button>
        <span>{{ page }} / {{ Math.ceil(total / perPage) }}</span>
        <button class="btn btn-sm" :disabled="page >= Math.ceil(total / perPage)" @click="nextPage">下一页</button>
      </div>
    </div>

    <!-- ═══════════════ Registry ═══════════════ -->
    <div v-show="activeTab === 'registries'">
      <div class="toolbar">
        <button class="btn btn-primary" @click="openRegModal()">＋ 添加仓库</button>
        <button class="btn" @click="loadRegistries">刷新</button>
        <span v-if="regError" class="error-msg">{{ regError }}</span>
      </div>

      <div v-if="registries.length === 0" class="empty-state">
        <p>暂无镜像仓库，添加一个私有 Registry（如 <code>10.0.0.1:5000</code>）</p>
      </div>

      <div v-else>
        <div v-for="r in registries" :key="r.id" class="reg-row">
          <div class="reg-info">
            <div class="reg-name">{{ r.name }}
              <span class="status-badge" :class="r.status">{{ statusText(r.status) }}</span>
              <span v-if="r.is_default" class="badge-tag tag-default">默认</span>
              <span v-if="r.is_internal" class="badge-tag tag-internal">内嵌</span>
            </div>
            <div class="reg-url mono">{{ (r.is_secure ? 'https://' : 'http://') + r.registry_url }}</div>
            <div class="reg-sub">用户：{{ r.username || '匿名' }} · {{ r.has_password ? '已设置密码' : '无密码' }}</div>
          </div>
          <div class="reg-actions">
            <button class="btn btn-sm" @click="testConn(r)" :disabled="testingId === r.id">{{ testingId === r.id ? '测试中...' : '测试连接' }}</button>
            <button class="btn btn-sm" @click="browseImg(r)">镜像列表</button>
            <button class="btn btn-sm" @click="openRegModal(r)">编辑</button>
            <button class="btn btn-sm btn-delete" @click="delReg(r)">删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══════════════ 包源 ═══════════════ -->
    <div v-show="activeTab === 'sources'">
      <div class="toolbar">
        <button class="btn" @click="loadSources">刷新</button>
      </div>
      <div v-if="sources.length === 0" class="empty-state">
        <p>暂无系统包源。加载包含 <code>packages/</code> 目录的离线包后自动生成 deb/rpm 源</p>
      </div>
      <div v-else>
        <div class="panel">
          <div class="table-wrap">
            <table class="table">
              <thead>
                <tr>
                  <th>来源</th><th>系统</th><th>URL</th><th>类型</th><th>包数</th><th>状态</th><th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="s in sources" :key="s.id">
                  <td>{{ s.bundle_id ? '离线包 #' + s.bundle_id : '-' }}</td>
                  <td>{{ osLabel(s.os_type) }} {{ s.os_version }}</td>
                  <td class="mono">{{ s.source_url }}</td>
                  <td><span class="badge-tag">{{ s.source_type }}</span></td>
                  <td>{{ s.package_count }}</td>
                  <td><span class="status-badge" :class="s.is_active ? 'loaded' : 'pending'">{{ s.is_active ? '启用' : '停用' }}</span></td>
                  <td><button class="btn btn-sm btn-delete" @click="delSource(s)">删除</button></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══════════════ 代理配置(供三个部署页下拉复用) ═══════════════ -->
    <div v-show="activeTab === 'proxies'">
      <div class="toolbar">
        <button class="btn btn-primary" @click="openProxyModal()">＋ 新增代理</button>
        <button class="btn" @click="loadProxies">刷新</button>
        <span class="hint" style="margin-left:10px">配置后可供 中间件/K8s/AI 自动部署 下拉直接选用(用于部署访问公网)</span>
      </div>

      <div v-if="proxies.length === 0" class="empty-state">
        <p>暂无代理配置。新增一个，如 NAT 环境宿主机代理 <code>192.168.100.2:7897</code>。</p>
      </div>

      <div v-else>
        <div v-for="px in proxies" :key="px.id" class="reg-row">
          <div class="reg-info">
            <div class="reg-name">{{ px.name }}
              <span v-if="px.is_default" class="badge-tag tag-default">默认</span>
            </div>
            <div class="reg-url mono">HTTP: {{ px.http_proxy || '—' }}</div>
            <div class="reg-sub">HTTPS: {{ px.https_proxy || '—' }} · NO_PROXY: {{ px.no_proxy || '—' }}</div>
          </div>
          <div class="reg-actions">
            <button class="btn btn-sm" v-if="!px.is_default" @click="setDefaultProxy(px)">设为默认</button>
            <button class="btn btn-sm" @click="openProxyModal(px)">编辑</button>
            <button class="btn btn-sm btn-delete" @click="delProxy(px)">删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══════════════ 健康 ═══════════════ -->
    <div v-show="activeTab === 'health'">
      <div class="toolbar">
        <button class="btn btn-primary" @click="refreshHealth">{{ healthLoading ? '检查中...' : '重新检查' }}</button>
      </div>
      <template v-if="health">
        <div class="stat-row">
          <div class="stat-card"><div class="stat-num">{{ health.registry_count }}</div><div class="stat-label">镜像仓库</div></div>
          <div class="stat-card"><div class="stat-num">{{ health.source_count }}</div><div class="stat-label">系统包源</div></div>
          <div class="stat-card"><div class="stat-num">{{ health.bundle_count }}</div><div class="stat-label">离线包</div></div>
          <div class="stat-card"><div class="stat-num">{{ health.loaded_bundle_count }}</div><div class="stat-label">已加载</div></div>
        </div>

        <div class="panel" v-if="health.registries && health.registries.length">
          <div class="panel-head">镜像仓库状态</div>
          <div class="table-wrap">
            <table class="table">
              <thead><tr><th>名称</th><th>地址</th><th>可达性</th><th>信息</th></tr></thead>
              <tbody>
                <tr v-for="r in health.registries" :key="r.id">
                  <td>{{ r.name }}</td><td class="mono">{{ r.registry_url }}</td>
                  <td><span class="status-badge" :class="r.reachable ? 'loaded' : 'failed'">{{ r.reachable ? '可达' : '不可达' }}</span></td>
                  <td>{{ r.message || '-' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="panel" v-if="health.sources && health.sources.length">
          <div class="panel-head">系统包源状态 · HTTP 根地址 <code class="mono">{{ health.source_http_base }}</code></div>
          <div class="table-wrap">
            <table class="table">
              <thead><tr><th>URL</th><th>类型</th><th>可达性</th></tr></thead>
              <tbody>
                <tr v-for="s in health.sources" :key="'s' + s.id">
                  <td class="mono">{{ s.source_url }}</td><td>{{ s.source_type }}</td>
                  <td><span class="status-badge" :class="s.reachable ? 'loaded' : 'failed'">{{ s.reachable ? '可达' : '不可达' }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
    </div>

    <!-- ═══ 上传弹窗 ═══ -->
    <div v-if="showUpload" class="modal-overlay" @click.self="showUpload = false">
      <div class="modal-box" style="width:580px">
        <div class="modal-head">
          <h3>上传离线包</h3>
          <button class="modal-close" @click="showUpload = false">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <label>名称 <span class="req">*</span></label>
            <input v-model="upForm.name" class="input" placeholder="如：pixiu-packages-ubuntu-24.04" />
          </div>
          <div class="form-row">
            <label>类型</label>
            <select v-model="upForm.bundle_type" class="input">
              <option value="images">镜像(images)</option>
              <option value="packages">系统包(packages)</option>
              <option value="server">Server 离线包</option>
            </select>
          </div>
          <div class="form-row">
            <label>系统 / 版本</label>
            <div style="display:flex;gap:8px">
              <select v-model="upForm.os_type" class="input" style="flex:1">
                <option value="">系统类型</option>
                <option value="ubuntu">Ubuntu</option>
                <option value="centos">CentOS</option>
                <option value="debian">Debian</option>
              </select>
              <input v-model="upForm.os_version" class="input" style="flex:1" placeholder="如 24.04 / 7" />
            </div>
          </div>
          <div class="form-row">
            <label>版本(K8s/应用)</label>
            <input v-model="upForm.version" class="input" placeholder="如 v1.31.6" />
          </div>
          <div class="form-row">
            <label>描述</label>
            <textarea v-model="upForm.description" class="input" rows="2" placeholder="可选"></textarea>
          </div>
          <div class="form-row">
            <label>MD5(可选)</label>
            <input v-model="upForm.md5" class="input mono" placeholder="上传后自动计算；填写则校验" />
          </div>
          <div class="form-row">
            <label>文件 <span class="req">*</span></label>
            <div class="drop-zone" @click="upFileInput.click()" @dragover.prevent @drop.prevent="onDropFile">
              <input ref="upFileInput" type="file" accept=".tar.gz,.tgz" style="display:none" @change="onPickFile" />
              <span v-if="upForm.file">{{ upForm.file.name }} ({{ sizeText(upForm.file.size) }})</span>
              <span v-else>点击或拖拽选择 .tar.gz 离线包</span>
            </div>
          </div>
          <div v-if="upError" class="error-msg">{{ upError }}</div>
          <div v-if="uploading" class="load-line">上传中...</div>
        </div>
        <div class="modal-foot">
          <button class="btn" @click="showUpload = false">取消</button>
          <button class="btn btn-primary" :disabled="uploading || !upForm.file" @click="doUpload">{{ uploading ? '上传中...' : '上传' }}</button>
        </div>
      </div>
    </div>

    <!-- ═══ Registry 弹窗 ═══ -->
    <div v-if="regModal.visible" class="modal-overlay" @click.self="regModal.visible = false">
      <div class="modal-box" style="width:540px">
        <div class="modal-head">
          <h3>{{ regModal.editId ? '编辑仓库' : '添加仓库' }}</h3>
          <button class="modal-close" @click="regModal.visible = false">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <label>名称 <span class="req">*</span></label>
            <input v-model="regForm.name" class="input" placeholder="如：内网镜像仓" />
          </div>
          <div class="form-row">
            <label>地址 <span class="req">*</span></label>
            <input v-model="regForm.registry_url" class="input mono" placeholder="如 10.0.0.1:5000" />
          </div>
          <div class="form-row">
            <label>协议</label>
            <label class="checkbox-line"><input type="checkbox" v-model="regForm.is_secure" /> HTTPS</label>
          </div>
          <div class="form-row">
            <label>用户名</label>
            <input v-model="regForm.username" class="input" placeholder="可选，匿名可留空" />
          </div>
          <div class="form-row">
            <label>密码 {{ regForm.has_password ? '(已保存，留空则不变)' : '' }}</label>
            <input v-model="regForm.password" type="password" class="input" placeholder="留空则保持原密码" />
          </div>
          <div class="form-row">
            <label>内嵌仓库</label>
            <label class="checkbox-line"><input type="checkbox" v-model="regForm.is_internal" /> 平台自管理(内嵌)</label>
          </div>
          <div class="form-row">
            <label>设为默认</label>
            <label class="checkbox-line"><input type="checkbox" v-model="regForm.is_default" /> 部署计划默认使用</label>
          </div>
          <div v-if="regError" class="error-msg">{{ regError }}</div>
        </div>
        <div class="modal-foot">
          <button class="btn" @click="regModal.visible = false">取消</button>
          <button class="btn btn-primary" @click="saveReg">保存</button>
        </div>
      </div>
    </div>

    <!-- ═══ 代理配置 弹窗 ═══ -->
    <div v-if="proxyModal.visible" class="modal-overlay" @click.self="proxyModal.visible = false">
      <div class="modal-box" style="width:540px">
        <div class="modal-head">
          <h3>{{ proxyModal.editId ? '编辑代理' : '新增代理' }}</h3>
          <button class="modal-close" @click="proxyModal.visible = false">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <label>名称 <span class="req">*</span></label>
            <input v-model="proxyForm.name" class="input" placeholder="如：NAT 宿主机代理" />
          </div>
          <div class="form-row">
            <label>HTTP 代理</label>
            <input v-model="proxyForm.http_proxy" class="input mono" placeholder="如 http://192.168.100.2:7897" />
          </div>
          <div class="form-row">
            <label>HTTPS 代理</label>
            <input v-model="proxyForm.https_proxy" class="input mono" placeholder="如 http://192.168.100.2:7897(留空则用 HTTP)" />
          </div>
          <div class="form-row">
            <label>NO_PROXY</label>
            <input v-model="proxyForm.no_proxy" class="input" placeholder="127.0.0.1,localhost,.local" />
          </div>
          <div class="form-row">
            <label>设为默认</label>
            <label class="checkbox-line"><input type="checkbox" v-model="proxyForm.is_default" /> 部署页默认选用</label>
          </div>
          <div v-if="proxyError" class="error-msg">{{ proxyError }}</div>
        </div>
        <div class="modal-foot">
          <button class="btn" @click="proxyModal.visible = false">取消</button>
          <button class="btn btn-primary" @click="saveProxy">保存</button>
        </div>
      </div>
    </div>

    <!-- ═══ 镜像/文件弹窗 ═══ -->
    <div v-if="imgModal.visible" class="modal-overlay" @click.self="imgModal.visible = false">
      <div class="modal-box" style="width:640px">
        <div class="modal-head">
          <h3>{{ imgModal.title }}</h3>
          <button class="modal-close" @click="imgModal.visible = false">&times;</button>
        </div>
        <div class="modal-body">
          <div v-if="imgModal.loading" class="loading">加载中...</div>
          <div v-else-if="imgModal.images.length === 0" class="empty-state">无数据</div>
          <div v-else class="table-wrap">
            <table class="table">
              <thead><tr><th>#</th><th>镜像 / 文件</th></tr></thead>
              <tbody>
                <tr v-for="(img, i) in imgModal.images" :key="i">
                  <td>{{ i + 1 }}</td><td class="mono">{{ img.name }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="modal-foot"><button class="btn" @click="imgModal.visible = false">关闭</button></div>
      </div>
    </div>

    <GuideDrawer v-model="showGuide" title="📖 离线仓库 · 操作说明">
      <div class="guide-section">
        <h4>一、功能定位</h4>
        <p><strong>离线仓库</strong>用于在受限/离线环境支撑部署：离线包管理、私有镜像仓库（Registry）、系统包源（deb/rpm），对标 <code>Pixiu builder serve</code>。K8s 集群部署、中间件部署等均会复用这里的 Registry / 包源 / 离线包。</p>
      </div>
      <div class="guide-section">
        <h4>二、离线包</h4>
        <ul>
          <li>点击「<strong>⬆ 上传离线包</strong>」导入 <code>.tar.gz</code>，包内含 <code>images/</code>（镜像 tar）与 <code>packages/</code>（deb/rpm）目录。</li>
          <li>上传后可加载、查验，状态包括 待加载 / 加载中 / 已加载 / 失败。</li>
          <li>可用顶部搜索按名称过滤离线包。</li>
        </ul>
      </div>
      <div class="guide-section">
        <h4>三、私有镜像仓库</h4>
        <p>管理私有 Registry 的地址、认证、命名空间。部署组件时会按需拉取/推送镜像到该仓库，避免依赖公网。</p>
      </div>
      <div class="guide-section">
        <h4>四、系统包源</h4>
        <p>配置 deb/rpm 包源，供目标主机离线安装系统依赖（repos 同步）。点「健康状态」可查看各源连通与同步情况。</p>
      </div>
    </GuideDrawer>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GuideDrawer from '@/components/GuideDrawer.vue'
import request from '@/api/request'

const activeTab = ref('bundles')
const showGuide = ref(false)
const loading = ref(false)
const bundles = ref([])
const search = ref('')
const statusFilter = ref('')
const page = ref(1)
const perPage = ref(12)
const total = ref(0)

const showUpload = ref(false)
const uploading = ref(false)
const upError = ref('')
const upForm = ref({ name: '', bundle_type: 'images', os_type: '', os_version: '', version: '', description: '', md5: '', file: null })

const registries = ref([])
const regError = ref('')
const testingId = ref(null)
const regModal = ref({ visible: false, editId: null })
const regForm = ref({ name: '', registry_url: '', is_secure: false, username: '', password: '', has_password: false, is_internal: false, is_default: false })

const proxies = ref([])
const proxyError = ref('')
const proxyModal = ref({ visible: false, editId: null })
const proxyForm = ref({ name: '', http_proxy: '', https_proxy: '', no_proxy: '', is_default: false })

const sources = ref([])
const health = ref(null)
const healthLoading = ref(false)
const imgModal = ref({ visible: false, title: '', images: [], loading: false })

const upFileInput = ref(null)

function switchTab(t) {
  activeTab.value = t
  if (t === 'registries') loadRegistries()
  else if (t === 'sources') loadSources()
  else if (t === 'proxies') loadProxies()
  else if (t === 'health') refreshHealth()
}

function statusText(s) {
  return { pending: '待加载', loading: '加载中', loaded: '已加载', failed: '失败',
           active: '正常', inactive: '停用', error: '异常' }[s] || s
}
function typeLabel(t) { return { images: '镜像', packages: '系统包', server: 'Server' }[t] || t }
function osLabel(t) { return { ubuntu: 'Ubuntu', centos: 'CentOS', debian: 'Debian' }[t] || t }
function sizeText(n) {
  if (!n) return ''
  const u = ['B', 'KB', 'MB', 'GB']
  let i = 0
  while (n >= 1024 && i < 3) { n /= 1024; i++ }
  return n.toFixed(1) + ' ' + u[i]
}

function prevPage() { if (page.value > 1) { page.value--; loadBundles(page.value) } }
function nextPage() { if (page.value < Math.ceil(total.value / perPage)) { page.value++; loadBundles(page.value) } }

function fail(res, fallback) { return res && res.error ? res.error : (fallback || '') }

async function loadBundles(p) {
  page.value = p || 1
  loading.value = true
  try {
    const res = await request.get('/offline/api/bundles', { params: { search: search.value, status: statusFilter.value, page: page.value, per_page: perPage.value } })
    bundles.value = res.items || []
    total.value = res.total || 0
  } catch (e) { ElMessage.error('加载离线包失败：' + e.message) } finally { loading.value = false }
}

async function loadBundle(b) {
  try {
    await ElMessageBox.confirm(`加载离线包「${b.name}」？将解压并导入镜像/生成包源。`, '确认加载', { type: 'warning' })
  } catch { return }
  try {
    const res = await request.post(`/offline/api/bundles/${b.id}/load`)
    if (res.warning) { ElMessage.warning(res.warning); return }
    await loadBundles(page.value)
    const msg = res.bundle && res.bundle.load_message ? res.bundle.load_message : '加载完成'
    if (res.bundle && res.bundle.status === 'failed') ElMessage.error('加载失败：' + msg)
    else ElMessage.success(msg)
  } catch (e) { ElMessage.error('加载失败：' + e.message) }
}

async function delBundle(b) {
  try { await ElMessageBox.confirm(`删除离线包「${b.name}」？将同时删除文件与包源。`, '删除确认', { type: 'warning' }) } catch { return }
  try { await request.delete(`/offline/api/bundles/${b.id}`); ElMessage.success('已删除'); loadBundles(1) } catch (e) { ElMessage.error(e.message) }
}

async function openImages(b) {
  imgModal.value = { visible: true, title: `镜像清单 · ${b.name}`, images: [], loading: true }
  try {
    const res = await request.get(`/offline/api/bundles/${b.id}/images`)
    imgModal.value.images = res.images || []
    if (!imgModal.value.images.length) ElMessage.info('无镜像文件')
  } catch (e) { ElMessage.error(e.message) } finally { imgModal.value.loading = false }
}

async function openPkgs(b) {
  imgModal.value = { visible: true, title: `包源 · ${b.name}`, images: [], loading: true }
  try {
    const res = await request.get(`/offline/api/bundles/${b.id}/packages`)
    const srcs = res.sources || []
    const lines = []
    srcs.forEach(s => {
      lines.push({ name: `${s.source_type} 源: ${s.source_url} (${s.package_count} 包)` })
      ;(s.packages || []).forEach(p => lines.push({ name: '  ' + p }))
    })
    imgModal.value.images = lines
    if (!lines.length) ElMessage.info('无包源')
  } catch (e) { ElMessage.error(e.message) } finally { imgModal.value.loading = false }
}

function openUpload() {
  upForm.value = { name: '', bundle_type: 'images', os_type: '', os_version: '', version: '', description: '', md5: '', file: null }
  upError.value = ''
  showUpload.value = true
}
function onPickFile(e) {
  upForm.value.file = e.target.files[0] || null
  autoName()
}
function onDropFile(e) {
  upForm.value.file = e.dataTransfer.files[0] || null
  autoName()
}
function autoName() {
  const f = upForm.value.file
  if (f && !upForm.value.name) upForm.value.name = f.name.replace(/\.tar\.gz$/i, '').replace(/\.tgz$/i, '')
}

async function doUpload() {
  if (!upForm.value.file) return
  uploading.value = true
  upError.value = ''
  const fd = new FormData()
  fd.append('file', upForm.value.file)
  fd.append('name', upForm.value.name)
  fd.append('bundle_type', upForm.value.bundle_type)
  fd.append('os_type', upForm.value.os_type)
  fd.append('os_version', upForm.value.os_version)
  fd.append('version', upForm.value.version)
  fd.append('description', upForm.value.description)
  fd.append('md5', upForm.value.md5)
  try {
    const res = await request.post('/offline/api/bundles/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    if (res.error) { upError.value = res.error; return }
    const msg = res.bundle ? `已上传（${res.bundle.file_size_display}）` : '已上传'
    ElMessage.success(msg)
    showUpload.value = false
    await loadBundles(1)
  } catch (e) { upError.value = e.message } finally { uploading.value = false }
}

async function loadRegistries() {
  regError.value = ''
  try {
    const res = await request.get('/offline/api/registries')
    registries.value = res.items || []
  } catch (e) { regError.value = e.message }
}

async function testConn(r) {
  testingId.value = r.id
  try {
    const res = await request.post(`/offline/api/registries/${r.id}/test`)
    if (res.ok) ElMessage.success(`✓ ${res.message || '连接成功'} [${r.registry_url}]`)
    else ElMessage.error(`✕ ${res.message || '连接失败'} [${r.registry_url}]`)
  } catch (e) { ElMessage.error('测试失败：' + e.message) } finally { testingId.value = null }
}

async function browseImg(r) {
  imgModal.value = { visible: true, title: `${r.name} · 仓库镜像`, images: [], loading: true }
  try {
    const res = await request.get(`/offline/api/registries/${r.id}/images`)
    if (!res.ok) imgModal.value.images = [{ name: res.message || '列表失败' }]
    else imgModal.value.images = res.images || []
  } catch (e) { imgModal.value.images = [{ name: e.message }] } finally { imgModal.value.loading = false }
}

function openRegModal(r) {
  regError.value = ''
  if (r) {
    regForm.value = { name: r.name, registry_url: r.registry_url, is_secure: !!r.is_secure, username: r.username || '', password: '', has_password: !!r.has_password, is_internal: !!r.is_internal, is_default: !!r.is_default }
    regModal.value = { visible: true, editId: r.id }
  } else {
    regForm.value = { name: '', registry_url: '', is_secure: false, username: '', password: '', has_password: false, is_internal: false, is_default: false }
    regModal.value = { visible: true, editId: null }
  }
}

async function saveReg() {
  const payload = {
    name: regForm.value.name, registry_url: regForm.value.registry_url,
    is_secure: regForm.value.is_secure, username: regForm.value.username,
    is_internal: regForm.value.is_internal, is_default: regForm.value.is_default,
  }
  if (regForm.value.password) payload.password = regForm.value.password
  try {
    if (regModal.value.editId) await request.put(`/offline/api/registries/${regModal.value.editId}`, payload)
    else await request.post('/offline/api/registries', payload)
    regModal.value.visible = false
    ElMessage.success('已保存')
    await loadRegistries()
  } catch (e) { regError.value = e.message }
}

async function delReg(r) {
  try { await ElMessageBox.confirm(`删除仓库「${r.name}」？`, '删除确认', { type: 'warning' }) } catch { return }
  try { await request.delete(`/offline/api/registries/${r.id}`); ElMessage.success('已删除'); loadRegistries() } catch (e) { regError.value = e.message }
}

async function loadProxies() {
  try { const res = await request.get('/offline/api/proxies'); proxies.value = res.items || [] } catch (e) { proxyError.value = e.message }
}

function openProxyModal(px) {
  proxyError.value = ''
  if (px) {
    proxyForm.value = { name: px.name, http_proxy: px.http_proxy || '', https_proxy: px.https_proxy || '', no_proxy: px.no_proxy || '', is_default: !!px.is_default }
    proxyModal.value = { visible: true, editId: px.id }
  } else {
    proxyForm.value = { name: '', http_proxy: '', https_proxy: '', no_proxy: '', is_default: proxies.value.length === 0 }
    proxyModal.value = { visible: true, editId: null }
  }
}

async function saveProxy() {
  if (!proxyForm.value.name.trim()) { proxyError.value = '名称不能为空'; return }
  try {
    if (proxyModal.value.editId) await request.post(`/offline/api/proxies/${proxyModal.value.editId}/update`, proxyForm.value)
    else await request.post('/offline/api/proxies/create', proxyForm.value)
    proxyModal.value.visible = false
    ElMessage.success('已保存')
    loadProxies()
  } catch (e) { proxyError.value = e.message }
}

async function delProxy(px) {
  try { await ElMessageBox.confirm(`删除代理「${px.name}」？`, '删除确认', { type: 'warning' }) } catch { return }
  try { await request.post(`/offline/api/proxies/${px.id}/delete`); ElMessage.success('已删除'); loadProxies() } catch (e) { proxyError.value = e.message }
}

async function setDefaultProxy(px) {
  try { await request.post(`/offline/api/proxies/${px.id}/default`); ElMessage.success('已设为默认'); loadProxies() } catch (e) { proxyError.value = e.message }
}

async function loadSources() {
  try {
    const res = await request.get('/offline/api/sources')
    sources.value = res.items || []
  } catch (e) { /* ignore */ }
}
async function delSource(s) {
  try { await ElMessageBox.confirm(`删除包源 ${s.source_url}？`, '删除确认', { type: 'warning' }) } catch { return }
  try { await request.delete(`/offline/api/sources/${s.id}`); ElMessage.success('已删除'); loadSources() } catch (e) { ElMessage.error(e.message) }
}

async function refreshHealth() {
  healthLoading.value = true
  try { health.value = await request.get('/offline/api/health') } catch (e) { ElMessage.error(e.message) } finally { healthLoading.value = false }
}

onMounted(() => { loadBundles(1) })
</script>

<style scoped>
.offline-page { padding: 12px; }
.page-header { margin-bottom: 12px; }
.page-header-row { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.page-header h1 { font-size: 20px; margin: 0; }
.page-header p { color: #909399; font-size: 12px; margin: 4px 0 0; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; text-decoration: none; display: inline-block; transition: all 0.2s; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.btn-sm + .btn-sm { margin-left: 4px; }
.btn-delete { background: #fef2f2; color: #dc2626; border: 1px solid #fecaca; }
.btn-delete:hover { background: #fecaca; }

.cfg-tabs { display: flex; gap: 4px; border-bottom: 1px solid #e4e7ed; margin-bottom: 12px; }
.cfg-tabs .tab { padding: 8px 16px; border: none; background: transparent; cursor: pointer; font-size: 14px; color: #606266; border-bottom: 2px solid transparent; }
.cfg-tabs .tab.active { color: #409eff; border-bottom-color: #409eff; font-weight: 600; }

.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.hint { color: #909399; font-size: 12px; margin-top: 4px; }
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; }
.bundle-card { border: 1px solid #e4e7ed; border-radius: 8px; padding: 12px; background: #fff; }
.bundle-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.bundle-name { font-weight: 600; font-size: 14px; }
.bundle-meta { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 6px; }
.meta-chip { background: #f0f2f5; border-radius: 4px; padding: 2px 8px; font-size: 12px; color: #606266; }
.bundle-desc { color: #909399; font-size: 12px; min-height: 18px; margin-bottom: 8px; }
.bundle-stats { display: flex; gap: 16px; margin-bottom: 8px; }
.mini-stat b { font-size: 18px; color: #303133; }
.mini-stat span { font-size: 12px; color: #909399; margin-left: 2px; }
.bundle-msg { font-size: 12px; color: #e6a23c; margin-bottom: 8px; }
.bundle-actions { display: flex; gap: 6px; justify-content: flex-end; }
.load-line { font-size: 12px; color: #409eff; margin-top: 8px; }

.reg-row { display: flex; justify-content: space-between; align-items: center; border: 1px solid #e4e7ed; border-radius: 8px; padding: 10px 14px; margin-bottom: 8px; background: #fff; gap: 12px; }
.reg-name { font-weight: 600; font-size: 14px; display: flex; align-items: center; gap: 6px; }
.reg-url { color: #409eff; font-size: 13px; margin: 2px 0; }
.reg-sub { color: #909399; font-size: 12px; }
.reg-actions { display: flex; gap: 6px; flex-shrink: 0; }

.badge-tag { border-radius: 4px; padding: 1px 8px; font-size: 12px; }
.tag-default { background: #f0f9eb; color: #67c23a; }
.tag-internal { background: #ecf5ff; color: #409eff; }

.stat-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 12px; }
.stat-card { background: #fff; border: 1px solid #e4e7ed; border-radius: 8px; text-align: center; padding: 14px; }
.stat-num { font-size: 24px; font-weight: 700; color: #303133; }
.stat-label { font-size: 12px; color: #909399; margin-top: 2px; }

.status-badge { border-radius: 4px; padding: 1px 8px; font-size: 12px; }
.status-badge.pending { background: #f4f4f5; color: #909399; }
.status-badge.loading { background: #ecf5ff; color: #409eff; }
.status-badge.loaded, .status-badge.active { background: #f0f9eb; color: #67c23a; }
.status-badge.failed, .status-badge.error { background: #fef0f0; color: #f56c6c; }
.status-badge.inactive { background: #f4f4f5; color: #909399; }

.modal-overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: #fff; border-radius: 8px; max-width: 92vw; max-height: 86vh; overflow: auto; }
.modal-head { display: flex; justify-content: space-between; align-items: center; padding: 14px 18px; border-bottom: 1px solid #e4e7ed; }
.modal-head h3 { margin: 0; font-size: 16px; }
.modal-close { border: none; background: none; font-size: 20px; cursor: pointer; color: #909399; }
.modal-body { padding: 16px 18px; }
.modal-foot { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 18px; border-top: 1px solid #e4e7ed; }

.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 13px; color: #606266; margin-bottom: 4px; }
.form-row .req { color: #f56c6c; }
.checkbox-line { display: inline-flex; align-items: center; gap: 4px; font-size: 13px; color: #606266; margin-right: 8px; cursor: pointer; }
.drop-zone { border: 1px dashed #c0c4cc; border-radius: 6px; text-align: center; padding: 20px; color: #909399; font-size: 13px; cursor: pointer; }
.drop-zone:hover { border-color: #409eff; color: #409eff; }

.pagination { display: flex; gap: 8px; align-items: center; justify-content: center; margin-top: 12px; color: #606266; font-size: 13px; }
.empty-state { text-align: center; color: #909399; padding: 30px 0; line-height: 1.8; }
.error-msg { color: #f56c6c; font-size: 12px; }
.loading { text-align: center; color: #909399; padding: 30px 0; }
.mono { font-family: Consolas, Menlo, monospace; }
.code, code { background: #f4f4f5; padding: 1px 4px; border-radius: 3px; font-size: 12px; }
</style>