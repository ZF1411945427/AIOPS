<template>
  <div class="sa-page">
    <div class="page-header">
      <h1>安全自查</h1>
      <p>SAST 漏洞扫描 + 依赖 CVE + License 合规 + 配置基线 一站式自查 · 交付前输出 0 高危报告 · SBOM 物料清单</p>
    </div>

    <!-- 概览卡片 -->
    <div class="summary-grid" v-if="report">
      <div class="summary-card" :class="overallClass">
        <div class="summary-label">总体结论</div>
        <div class="summary-value-sm">{{ overallLabel }}</div>
        <div class="summary-sub">{{ report.generated_at }}</div>
      </div>
      <div class="summary-card" :class="{ danger: banditHigh > 0, ok: banditHigh === 0 && banditTotal === 0 }">
        <div class="summary-label">SAST 高危</div>
        <div class="summary-value">{{ banditHigh }}</div>
        <div class="summary-sub">中危 {{ banditMedium }} / 低危 {{ banditLow }}</div>
      </div>
      <div class="summary-card" :class="{ danger: depVulnCount > 0, ok: depVulnCount === 0 }">
        <div class="summary-label">依赖 CVE</div>
        <div class="summary-value">{{ depVulnCount }}</div>
        <div class="summary-sub">影响 {{ depAffected }} 个包 / 共 {{ depTotal }} 个</div>
      </div>
      <div class="summary-card" :class="{ danger: riskyLicenseCount > 0, ok: riskyLicenseCount === 0 }">
        <div class="summary-label">高危 License</div>
        <div class="summary-value">{{ riskyLicenseCount }}</div>
        <div class="summary-sub">总组件 {{ licenseTotal }}</div>
      </div>
      <div class="summary-card" :class="{ ok: configPass === configTotal && configFail === 0, danger: configFail > 0, warn: configFail === 0 && configWarn > 0 }">
        <div class="summary-label">配置基线</div>
        <div class="summary-value">{{ configPass }}/{{ configTotal }}</div>
        <div class="summary-sub">告警 {{ configWarn }} / 失败 {{ configFail }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">缓存状态</div>
        <div class="summary-value-sm">{{ report.from_cache ? '命中缓存' : '刚刷新' }}</div>
        <div class="summary-sub" v-if="report.cache_age_seconds">已缓存 {{ formatAge(report.cache_age_seconds) }}</div>
      </div>
    </div>

    <!-- 操作栏 -->
    <div class="panel">
      <div class="panel-head">
        <span>自查明细</span>
        <div class="panel-actions">
          <button class="btn btn-sm" @click="runScan(false)" :disabled="loading">
            {{ loading ? '扫描中...' : '刷新缓存读取' }}
          </button>
          <button class="btn btn-sm btn-primary" @click="runScan(true)" :disabled="loading">
            {{ loading ? '扫描中...' : '重新全量扫描' }}
          </button>
          <button class="btn btn-sm" @click="exportSbom" :disabled="loading">导出 SBOM</button>
        </div>
      </div>

      <!-- Tab -->
      <div class="tab-bar">
        <button v-for="t in tabs" :key="t.key" class="tab" :class="{ active: activeTab === t.key }" @click="activeTab = t.key">
          {{ t.label }} <span class="tab-count" :class="tabCountClass(t.key)">{{ tabCount(t.key) }}</span>
        </button>
      </div>

      <div class="panel-body">
        <div v-if="loading && !report" class="loading-state">
          正在执行安全扫描（bandit + pip-audit + pip-licenses），首次约 1-3 分钟，请稍候...
        </div>
        <div v-else-if="!report" class="empty-state">
          尚未生成报告，点击「重新全量扫描」开始
        </div>
        <div v-else-if="error" class="empty-state text-danger">{{ error }}</div>

        <!-- 配置基线 -->
        <template v-else-if="activeTab === 'config'">
          <div v-if="!configChecks.length" class="empty-state">无配置检查数据</div>
          <table v-else class="table">
            <thead>
              <tr>
                <th>检查项</th>
                <th>当前值</th>
                <th>状态</th>
                <th>建议</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in configChecks" :key="c.key" :class="rowClass(c.status)">
                <td>{{ c.label }}</td>
                <td class="text-mono">{{ c.value }}</td>
                <td><span class="badge" :class="statusClass(c.status)">{{ statusLabel(c.status) }}</span></td>
                <td class="text-sm">{{ c.advice || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </template>

        <!-- SAST 漏洞 -->
        <template v-else-if="activeTab === 'sast'">
          <div class="filter-bar">
            <label class="text-sm">严重度:</label>
            <select v-model="sastFilter" class="select-sm">
              <option value="">全部</option>
              <option value="HIGH">高危</option>
              <option value="MEDIUM">中危</option>
              <option value="LOW">低危</option>
            </select>
            <label class="text-sm">搜索:</label>
            <input v-model="sastSearch" class="input-sm" placeholder="文件名/规则/描述" />
          </div>
          <div v-if="!banditAvailable" class="empty-state text-danger">{{ banditError }}</div>
          <div v-else-if="!filteredSast.length" class="empty-state">无匹配项</div>
          <table v-else class="table">
            <thead>
              <tr>
                <th>严重度</th>
                <th>置信度</th>
                <th>规则</th>
                <th>位置</th>
                <th>描述</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in filteredSast" :key="i" :class="sevRowClass(r.severity)">
                <td><span class="badge" :class="sevClass(r.severity)">{{ r.severity }}</span></td>
                <td class="text-sm">{{ r.confidence }}</td>
                <td class="text-mono">{{ r.test_id }}</td>
                <td class="text-mono">{{ r.filename }}:{{ r.line }}</td>
                <td class="text-sm">{{ r.text }}</td>
              </tr>
            </tbody>
          </table>
        </template>

        <!-- 依赖 CVE -->
        <template v-else-if="activeTab === 'deps'">
          <div class="filter-bar">
            <label class="text-sm">搜索:</label>
            <input v-model="depSearch" class="input-sm" placeholder="包名/CVE ID" />
          </div>
          <div v-if="!depAvailable" class="empty-state text-danger">{{ depError }}</div>
          <div v-else-if="!filteredDeps.length" class="empty-state">无匹配项</div>
          <table v-else class="table">
            <thead>
              <tr>
                <th>包名</th>
                <th>当前版本</th>
                <th>CVE ID</th>
                <th>修复版本</th>
                <th>描述</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(v, i) in filteredDeps" :key="i" class="row-warn">
                <td class="text-mono">{{ v.package }}</td>
                <td class="text-mono">{{ v.version }}</td>
                <td class="text-mono">{{ v.vuln_id }}</td>
                <td class="text-mono text-success">{{ (v.fix_versions || []).join(' / ') || '—' }}</td>
                <td class="text-sm">{{ v.description }}</td>
              </tr>
            </tbody>
          </table>
        </template>

        <!-- License 合规 -->
        <template v-else-if="activeTab === 'license'">
          <div class="filter-bar">
            <label class="text-sm">只看高危:</label>
            <input type="checkbox" v-model="onlyRiskyLicense" />
            <label class="text-sm">搜索:</label>
            <input v-model="licenseSearch" class="input-sm" placeholder="包名/License" />
          </div>
          <div v-if="!licenseAvailable" class="empty-state text-danger">{{ licenseError }}</div>
          <div v-else-if="!filteredLicenses.length" class="empty-state">无匹配项</div>
          <table v-else class="table">
            <thead>
              <tr>
                <th>包名</th>
                <th>版本</th>
                <th>License</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(l, i) in filteredLicenses" :key="i" :class="isRisky(l) ? 'row-danger' : ''">
                <td class="text-mono">{{ l.name }}</td>
                <td class="text-mono">{{ l.version }}</td>
                <td class="text-sm">{{ l.license || '(未知)' }}</td>
                <td>
                  <span class="badge" :class="isRisky(l) ? 'danger' : 'on'">
                    {{ isRisky(l) ? '⚠️ 高危' : '✅ 合规' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </template>

        <!-- SBOM -->
        <template v-else-if="activeTab === 'sbom'">
          <div class="empty-state" v-if="!licenseAvailable">{{ licenseError || '无 SBOM 数据' }}</div>
          <div v-else>
            <p class="text-sm" style="margin: 0 0 12px;">
              软件物料清单（SBOM）：共 {{ licenseTotal }} 个组件 · 高危 License {{ riskyLicenseCount }} 个 ·
              可点击「导出 SBOM」下载完整 JSON
            </p>
            <table class="table">
              <thead>
                <tr>
                  <th>包名</th>
                  <th>版本</th>
                  <th>License</th>
                  <th>作者</th>
                  <th>URL</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(l, i) in sbomList" :key="i" :class="isRisky(l) ? 'row-danger' : ''">
                  <td class="text-mono">{{ l.name }}</td>
                  <td class="text-mono">{{ l.version }}</td>
                  <td class="text-sm">{{ l.license || '(未知)' }}</td>
                  <td class="text-sm">{{ l.author || '—' }}</td>
                  <td class="text-sm text-mono">{{ l.url || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const error = ref('')
const report = ref(null)
const activeTab = ref('config')

const tabs = [
  { key: 'config', label: '配置基线' },
  { key: 'sast', label: 'SAST 漏洞' },
  { key: 'deps', label: '依赖 CVE' },
  { key: 'license', label: 'License 合规' },
  { key: 'sbom', label: 'SBOM 清单' },
]

const sastFilter = ref('')
const sastSearch = ref('')
const depSearch = ref('')
const licenseSearch = ref('')
const onlyRiskyLicense = ref(false)

// ── 派生数据 ──
const banditData = computed(() => report.value?.bandit || {})
const banditAvailable = computed(() => banditData.value.available !== false)
const banditError = computed(() => banditData.value.error || 'bandit 未安装或执行失败')
const banditIssues = computed(() => banditData.value.issues || [])
const banditHigh = computed(() => banditData.value.summary?.high || 0)
const banditMedium = computed(() => banditData.value.summary?.medium || 0)
const banditLow = computed(() => banditData.value.summary?.low || 0)
const banditTotal = computed(() => banditData.value.summary?.total || 0)

const depData = computed(() => report.value?.dependencies || {})
const depAvailable = computed(() => depData.value.available !== false)
const depError = computed(() => depData.value.error || 'pip-audit 未安装或执行失败')
const depVulns = computed(() => depData.value.vulnerabilities || [])
const depVulnCount = computed(() => depData.value.summary?.vuln_count || 0)
const depAffected = computed(() => depData.value.summary?.affected_deps || 0)
const depTotal = computed(() => depData.value.summary?.total_deps || 0)

const licenseData = computed(() => report.value?.licenses || {})
const licenseAvailable = computed(() => licenseData.value.available !== false)
const licenseError = computed(() => licenseData.value.error || 'pip-licenses 未安装或执行失败')
const licenseList = computed(() => licenseData.value.licenses || [])
const riskyLicenses = computed(() => licenseData.value.risky_licenses || [])
const licenseTotal = computed(() => licenseData.value.summary?.total || 0)
const riskyLicenseCount = computed(() => licenseData.value.summary?.risky_count || 0)
const sbomList = computed(() => licenseList.value)

const configData = computed(() => report.value?.config || {})
const configChecks = computed(() => configData.value.checks || [])
const configPass = computed(() => configData.value.summary?.pass || 0)
const configWarn = computed(() => configData.value.summary?.warn || 0)
const configFail = computed(() => configData.value.summary?.fail || 0)
const configTotal = computed(() => configData.value.summary?.total || 0)

const overallClass = computed(() => {
  if (!report.value) return ''
  if (banditHigh.value > 0 || configFail.value > 0 || riskyLicenseCount.value > 0) return 'danger'
  if (banditMedium.value > 0 || depVulnCount.value > 0 || configWarn.value > 0) return 'warn'
  return 'ok'
})
const overallLabel = computed(() => {
  if (!report.value) return '—'
  const c = overallClass.value
  if (c === 'danger') return '需立即修复 ❌'
  if (c === 'warn') return '存在告警 ⚠️'
  if (c === 'ok') return '通过 ✅'
  return '—'
})

// ── 过滤 ──
const filteredSast = computed(() => {
  let list = banditIssues.value
  if (sastFilter.value) list = list.filter(r => r.severity === sastFilter.value)
  if (sastSearch.value) {
    const k = sastSearch.value.toLowerCase()
    list = list.filter(r =>
      (r.filename || '').toLowerCase().includes(k) ||
      (r.test_id || '').toLowerCase().includes(k) ||
      (r.text || '').toLowerCase().includes(k))
  }
  return list
})

const filteredDeps = computed(() => {
  let list = depVulns.value
  if (depSearch.value) {
    const k = depSearch.value.toLowerCase()
    list = list.filter(v =>
      (v.package || '').toLowerCase().includes(k) ||
      (v.vuln_id || '').toLowerCase().includes(k))
  }
  return list
})

const filteredLicenses = computed(() => {
  let list = licenseList.value
  if (onlyRiskyLicense.value) {
    const riskySet = new Set(riskyLicenses.value.map(r => r.name + '@' + r.version))
    list = list.filter(l => riskySet.has(l.name + '@' + l.version))
  }
  if (licenseSearch.value) {
    const k = licenseSearch.value.toLowerCase()
    list = list.filter(l =>
      (l.name || '').toLowerCase().includes(k) ||
      (l.license || '').toLowerCase().includes(k))
  }
  return list
})

function isRisky(l) {
  return riskyLicenses.value.some(r => r.name === l.name && r.version === l.version)
}

// ── 工具 ──
function tabCount(key) {
  if (key === 'config') return configTotal.value
  if (key === 'sast') return banditTotal.value
  if (key === 'deps') return depVulnCount.value
  if (key === 'license') return riskyLicenseCount.value || licenseTotal.value
  if (key === 'sbom') return licenseTotal.value
  return 0
}
function tabCountClass(key) {
  const n = tabCount(key)
  if (key === 'sast' && banditHigh.value > 0) return 'danger'
  if (key === 'deps' && depVulnCount.value > 0) return 'danger'
  if (key === 'license' && riskyLicenseCount.value > 0) return 'danger'
  if (key === 'config' && configFail.value > 0) return 'danger'
  if (key === 'config' && configWarn.value > 0) return 'warn'
  return ''
}
function rowClass(status) {
  return { pass: '', warn: 'row-warn', fail: 'row-danger' }[status] || ''
}
function statusClass(status) {
  return { pass: 'on', warn: 'warn', fail: 'danger' }[status] || 'off'
}
function statusLabel(status) {
  return { pass: '✅ 通过', warn: '⚠️ 告警', fail: '❌ 失败' }[status] || status
}
function sevClass(sev) {
  return { HIGH: 'danger', MEDIUM: 'warn', LOW: 'on' }[sev] || 'off'
}
function sevRowClass(sev) {
  return { HIGH: 'row-danger', MEDIUM: 'row-warn', LOW: '' }[sev] || ''
}
function formatAge(sec) {
  if (sec < 60) return `${sec}s`
  if (sec < 3600) return `${Math.floor(sec / 60)}min`
  return `${Math.floor(sec / 3600)}h${Math.floor((sec % 3600) / 60)}m`
}

// ── 操作 ──
async function runScan(force) {
  loading.value = true
  error.value = ''
  try {
    const data = await request.post(`/api/security-audit/scan?force=${force ? 'true' : 'false'}`)
    if (data.error) {
      error.value = data.error
      ElMessage.error(data.error)
    } else {
      report.value = data
      if (data.from_cache && !force) {
        ElMessage.success(`已读取缓存报告（${formatAge(data.cache_age_seconds || 0)}前生成）`)
      } else {
        ElMessage.success('安全扫描完成')
      }
    }
  } catch (e) {
    error.value = `扫描请求失败: ${e?.message || e}`
    ElMessage.error(error.value)
  } finally {
    loading.value = false
  }
}

async function exportSbom() {
  try {
    const data = await request.get('/api/security-audit/sbom')
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `SBOM-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('SBOM 已下载')
  } catch (e) {
    ElMessage.error(`导出失败: ${e?.message || e}`)
  }
}

onMounted(() => {
  // 先尝试读缓存（秒级返回），无缓存则提示用户手动扫描
  request.get('/api/security-audit/report').then(data => {
    if (data && data.available !== false && data.generated_at) {
      report.value = data
    }
  }).catch(() => {})
})
</script>

<style scoped>
.sa-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 16px; }
.summary-card { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; padding: 12px 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.summary-card.danger { border-left: 3px solid #ef4444; }
.summary-card.warn { border-left: 3px solid #f59e0b; }
.summary-card.ok { border-left: 3px solid #22c55e; }
.summary-label { font-size: 0.72rem; color: var(--text-secondary, #64748b); text-transform: uppercase; letter-spacing: 0.3px; margin-bottom: 4px; }
.summary-value { font-size: 1.4rem; font-weight: 700; color: var(--text, #1e293b); }
.summary-value-sm { font-size: 0.95rem; font-weight: 600; color: var(--text, #1e293b); }
.summary-sub { font-size: 0.7rem; color: var(--text-tertiary, #94a3b8); margin-top: 2px; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); display: flex; justify-content: space-between; align-items: center; }
.panel-actions { display: flex; gap: 10px; align-items: center; }
.panel-body { padding: 16px 18px; }
.tab-bar { display: flex; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); padding: 0 18px; flex-wrap: wrap; }
.tab { padding: 10px 14px; border: none; background: transparent; color: var(--text-secondary, #64748b); cursor: pointer; font-size: 0.85rem; border-bottom: 2px solid transparent; }
.tab.active { color: var(--text, #1e293b); border-bottom-color: #3b82f6; font-weight: 600; }
.tab-count { display: inline-block; min-width: 18px; padding: 1px 5px; border-radius: 8px; background: rgba(100,116,139,0.15); color: #64748b; font-size: 0.7rem; margin-left: 4px; }
.tab-count.danger { background: rgba(239,68,68,0.15); color: #ef4444; }
.tab-count.warn { background: rgba(245,158,11,0.15); color: #f59e0b; }
.filter-bar { display: flex; gap: 14px; align-items: center; margin-bottom: 14px; flex-wrap: wrap; }
.select-sm, .input-sm { padding: 4px 8px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 4px; font-size: 0.78rem; background: var(--bg-card-solid, #fff); }
.input-sm { min-width: 160px; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.72rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; white-space: nowrap; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.table tr:hover td { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.table tr.row-warn td { background: rgba(245,158,11,0.04); }
.table tr.row-danger td { background: rgba(239,68,68,0.06); }
.text-sm { font-size: 0.78rem; color: var(--text-secondary, #64748b); }
.text-mono { font-family: 'Consolas', monospace; font-size: 0.8rem; }
.text-success { color: #22c55e; }
.text-danger { color: #ef4444; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.7rem; font-weight: 600; }
.badge.on { background: rgba(34,197,94,0.1); color: #22c55e; }
.badge.off { background: rgba(100,116,139,0.1); color: #64748b; }
.badge.warn { background: rgba(245,158,11,0.1); color: #f59e0b; }
.badge.danger { background: rgba(239,68,68,0.1); color: #ef4444; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.82rem; }
.btn:hover { background: var(--bg-hover, rgba(0,0,0,0.03)); }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }
.btn-primary { background: #3b82f6; color: #fff; border-color: #3b82f6; }
.btn-primary:hover { background: #2563eb; }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
</style>
