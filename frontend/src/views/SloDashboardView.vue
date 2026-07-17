<template>
  <div class="slo-dashboard">
    <div class="page-header">
      <h1>SLO 仪表盘</h1>
      <p>实时可用性 · 错误预算燃烧速率 · Error Budget</p>
      <div class="header-actions">
        <button class="btn" @click="loadDashboard" :disabled="loading">刷新</button>
        <button class="btn btn-primary" @click="triggerCalculate">强制计算</button>
      </div>
    </div>

    <div v-if="loading" class="loading-state">加载中...</div>

    <div v-else-if="!items.length" class="empty-state">
      <div style="font-size:32px;margin-bottom:8px;">📊</div>
      <div>暂无 SLO 配置</div>
      <div class="text-sm">请先去「SLO 配置管理」添加 SLO</div>
    </div>

    <div v-else>
      <div class="summary-cards">
        <div class="stat-card" :class="summaryCritical > 0 ? 'critical' : summaryWarning > 0 ? 'warning' : 'healthy'">
          <div class="stat-value">{{ summaryTotal }}</div>
          <div class="stat-label">全部 SLO</div>
        </div>
        <div class="stat-card healthy">
          <div class="stat-value" style="color:#22c55e;">{{ summaryHealthy }}</div>
          <div class="stat-label">健康</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-value" style="color:#d97706;">{{ summaryWarning }}</div>
          <div class="stat-label">警告</div>
        </div>
        <div class="stat-card critical">
          <div class="stat-value" style="color:#ef4444;">{{ summaryCritical }}</div>
          <div class="stat-label">危险</div>
        </div>
      </div>

      <div class="slo-grid">
        <div v-for="item in items" :key="item.id" class="slo-card" :class="'status-' + item.status">
          <div class="slo-card-header">
            <div class="slo-name">{{ item.service_name }}</div>
            <span class="badge" :class="item.status">{{ item.status }}</span>
          </div>

          <div class="slo-availability">
            <div class="avail-value" :class="availabilityClass(item.availability)">
              {{ item.availability != null ? (item.availability * 100).toFixed(3) + '%' : '—' }}
            </div>
            <div class="avail-target">目标: {{ ((item.slo_target || 0.999) * 100).toFixed(3) }}%</div>
          </div>

          <div class="slo-bar-wrap">
            <div class="slo-bar-label">
              <span>Error Budget</span>
              <span>{{ item.budget_remaining != null ? item.budget_remaining.toFixed(1) + '%' : '—' }}</span>
            </div>
            <div class="slo-bar">
              <div class="slo-bar-fill" :class="'fill-' + item.status"
                :style="{ width: (item.budget_remaining != null ? Math.max(0, item.budget_remaining) : 100) + '%' }">
              </div>
            </div>
          </div>

          <div class="slo-metrics">
            <div class="metric-row">
              <span class="metric-label">燃烧速率</span>
              <span class="metric-val" :class="burnRateClass(item.burn_rate)">
                {{ item.burn_rate != null ? item.burn_rate.toFixed(2) + 'x' : '—' }}
              </span>
            </div>
            <div class="metric-row">
              <span class="metric-label">总请求</span>
              <span class="metric-val">{{ item.total_requests || 0 }}</span>
            </div>
            <div class="metric-row">
              <span class="metric-label">错误</span>
              <span class="metric-val" style="color:#ef4444;">{{ item.error_requests || 0 }}</span>
            </div>
            <div class="metric-row">
              <span class="metric-label">窗口</span>
              <span class="metric-val">{{ item.window_days || 30 }}天</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const items = ref([])

const summaryTotal = computed(() => items.value.length)
const summaryHealthy = computed(() => items.value.filter(x => x.status === 'healthy').length)
const summaryWarning = computed(() => items.value.filter(x => x.status === 'warning').length)
const summaryCritical = computed(() => items.value.filter(x => x.status === 'critical').length)

function availabilityClass(v) {
  if (v == null) return ''
  if (v >= 0.999) return 'avail-great'
  if (v >= 0.99) return 'avail-ok'
  return 'avail-bad'
}

function burnRateClass(br) {
  if (br == null) return ''
  if (br > 10) return 'burn-critical'
  if (br > 5) return 'burn-warning'
  return 'burn-ok'
}

async function loadDashboard() {
  loading.value = true
  try {
    items.value = await request.get('/api/sre/slo/dashboard')
  } catch (e) {
    ElMessage.error('加载失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

async function triggerCalculate() {
  try {
    await request.post('/api/sre/slo/calculate')
    ElMessage.success('计算完成')
    await loadDashboard()
  } catch (e) {
    ElMessage.error('计算失败: ' + e.message)
  }
}

onMounted(loadDashboard)
</script>

<style scoped>
.slo-dashboard { padding: 4px; }
.page-header { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; margin: 0; }
.page-header p { color: var(--text-secondary,#64748b); font-size: 0.85rem; margin: 0; }
.header-actions { display: flex; gap: 8px; margin-left: auto; }
.btn { padding: 6px 14px; border: 1px solid var(--border-strong,rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid,#fff); cursor: pointer; font-size: 0.82rem; }
.btn-primary { background: var(--accent,#6366f1); color: #fff; border-color: var(--accent,#6366f1); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.loading-state, .empty-state { text-align: center; padding: 48px; color: var(--text-tertiary,#94a3b8); }
.text-sm { font-size: 0.78rem; margin-top: 4px; }

.summary-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
.stat-card { background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; padding: 16px; text-align: center; }
.stat-card.healthy { border-left: 3px solid #22c55e; }
.stat-card.warning { border-left: 3px solid #d97706; }
.stat-card.critical { border-left: 3px solid #ef4444; }
.stat-value { font-size: 2rem; font-weight: 800; }
.stat-label { font-size: 0.75rem; color: var(--text-secondary,#64748b); margin-top: 4px; }

.slo-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.slo-card { background: var(--bg-card,#fff); border: 1px solid var(--border,rgba(0,0,0,0.07)); border-radius: 10px; padding: 16px; }
.slo-card.status-critical { border-left: 3px solid #ef4444; }
.slo-card.status-warning { border-left: 3px solid #d97706; }
.slo-card.status-healthy { border-left: 3px solid #22c55e; }

.slo-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.slo-name { font-weight: 700; font-size: 1rem; }
.badge { padding: 2px 8px; border-radius: 6px; font-size: 0.72rem; font-weight: 600; }
.badge.healthy { background: rgba(34,197,94,0.12); color: #22c55e; }
.badge.warning { background: rgba(245,158,11,0.12); color: #d97706; }
.badge.critical { background: rgba(239,68,68,0.12); color: #ef4444; }

.slo-availability { text-align: center; padding: 12px 0; }
.avail-value { font-size: 2.2rem; font-weight: 900; }
.avail-great { color: #22c55e; }
.avail-ok { color: #d97706; }
.avail-bad { color: #ef4444; }
.avail-target { font-size: 0.75rem; color: var(--text-secondary,#64748b); margin-top: 2px; }

.slo-bar-wrap { margin-bottom: 12px; }
.slo-bar-label { display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--text-secondary,#64748b); margin-bottom: 4px; }
.slo-bar { height: 6px; background: var(--bg-hover,rgba(0,0,0,0.05)); border-radius: 3px; overflow: hidden; }
.slo-bar-fill { height: 100%; border-radius: 3px; transition: width 0.5s; }
.fill-healthy { background: #22c55e; }
.fill-warning { background: #d97706; }
.fill-critical { background: #ef4444; }

.slo-metrics { border-top: 1px solid var(--border,rgba(0,0,0,0.05)); padding-top: 10px; }
.metric-row { display: flex; justify-content: space-between; font-size: 0.8rem; padding: 3px 0; }
.metric-label { color: var(--text-secondary,#64748b); }
.metric-val { font-weight: 600; }
.burn-critical { color: #ef4444; }
.burn-warning { color: #d97706; }
.burn-ok { color: #22c55e; }
</style>
