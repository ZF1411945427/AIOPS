<template>
  <div class="workbench-page-shell">
    <div class="section-toolbar">
      <div class="toolbar-head">
        <span class="toolbar-title">系统态势</span>
        <span class="toolbar-desc">平台运行关键指标一目了然</span>
      </div>
      <div class="workbench-card-actions">
        <el-button size="small" @click="loadData" :loading="loading">
          <el-icon><RefreshRight /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <div class="overview-cards">
      <div class="overview-card" v-for="card in cards" :key="card.label" :class="card.tone">
        <div class="overview-card-icon">{{ card.icon }}</div>
        <div class="overview-card-body">
          <div class="overview-card-value">{{ card.value }}</div>
          <div class="overview-card-label">{{ card.label }}</div>
        </div>
      </div>
    </div>

    <div class="workbench-card" style="margin-top:8px">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">快速入口</span>
        </div>
      </div>
      <div class="quick-links">
        <div class="quick-link-item" v-for="link in quickLinks" :key="link.label" @click="navigate(link.path)">
          <span class="quick-link-icon">{{ link.icon }}</span>
          <span class="quick-link-label">{{ link.label }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { RefreshRight } from '@element-plus/icons-vue'
import { useAppStore } from '@/stores/app'
import request from '@/api/request'

const appStore = useAppStore()
const loading = ref(false)
const data = ref({})

const cards = ref([])

const quickLinks = [
  { icon: '🚨', label: '告警中心', path: '/alerts' },
  { icon: '📊', label: '指标监控', path: '/metrics' },
  { icon: '🖥️', label: '资产列表', path: '/assets' },
  { icon: '🐳', label: 'K8s 概览', path: '/k8s/overview' },
  { icon: '📝', label: '事件中心', path: '/events' },
  { icon: '🤖', label: 'AI 助手', path: 'agent-chat' },
]

function navigate(path) {
  if (path === 'agent-chat') {
    window._navigateTo?.('agent-chat')
  } else {
    window._navigateToIframe?.(path)
  }
}

async function loadData() {
  loading.value = true
  try {
    const res = await request.get('/api/system/overview')
    data.value = res
    cards.value = [
      { icon: '🖥️', label: '资产总数', value: res.assets?.total ?? 0, tone: '' },
      { icon: '✅', label: '在线资产', value: res.assets?.online ?? 0, tone: 'overview-card--success' },
      { icon: '🚨', label: '触发告警', value: res.alerts?.triggered ?? 0, tone: res.alerts?.triggered > 0 ? 'overview-card--danger' : '' },
      { icon: '⚠️', label: '待确认告警', value: res.alerts?.acknowledged ?? 0, tone: res.alerts?.acknowledged > 0 ? 'overview-card--warning' : '' },
      { icon: '📋', label: '进行中故障', value: res.incidents?.open ?? 0, tone: res.incidents?.open > 0 ? 'overview-card--danger' : '' },
      { icon: '🔗', label: '启用的数据源', value: res.datasources ?? 0, tone: 'overview-card--info' },
      { icon: '📈', label: '近 1h 指标记录', value: res.metrics_count_1h ?? 0, tone: '' },
      { icon: '🔔', label: '近 24h 告警', value: res.alerts_count_24h ?? 0, tone: '' },
    ]
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.overview-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 8px;
}
.overview-card {
  background: var(--card-bg);
  border: 1px solid rgba(148,163,184,0.16);
  border-radius: 12px;
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  transition: all 0.2s;
}
.overview-card:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
.overview-card-icon { font-size: 1.4rem; }
.overview-card-value { font-size: 1.4rem; font-weight: 700; color: var(--text-primary); }
.overview-card-label { font-size: 11px; color: var(--text-secondary); margin-top: 2px; }
.overview-card--success { border-left: 3px solid var(--success); }
.overview-card--warning { border-left: 3px solid var(--warning); }
.overview-card--danger { border-left: 3px solid var(--danger); }
.overview-card--info { border-left: 3px solid var(--info); }
.quick-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.quick-link-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: var(--content-bg);
  border: 1px solid rgba(148,163,184,0.16);
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary);
  transition: all 0.15s;
}
.quick-link-item:hover { border-color: var(--primary); color: var(--primary); background: rgba(99,102,241,0.04); }
.quick-link-icon { font-size: 1rem; }
</style>
