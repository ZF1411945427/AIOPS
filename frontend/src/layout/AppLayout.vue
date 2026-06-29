<template>
  <div class="app-layout">
    <!-- 切换数据库时的 loading 遮罩，遮挡首帧仪表盘闪烁 -->
    <div v-if="menuLoading" class="menu-loading-overlay">
      <el-icon class="loading-spin" :size="32"><Loading /></el-icon>
    </div>
    <aside class="sidebar" :class="{ collapsed: appStore.sidebarCollapsed }">
      <div class="sidebar-header">
        <div class="logo-badge">AI</div>
        <span v-if="!appStore.sidebarCollapsed" class="brand-name">AIOps</span>
      </div>

      <el-menu
        :default-active="activeMenu"
        :collapse="appStore.sidebarCollapsed"
        class="sidebar-nav"
        @select="handleMenuSelect"
      >
        <template v-for="g in menuGroups" :key="g.key">
          <el-sub-menu v-if="g.items && g.items.length" :index="g.key">
            <template #title>
              <el-icon><component :is="getIcon(g.icon)" /></el-icon>
              <span>{{ g.label }}</span>
            </template>
            <template v-for="item in (g.items || [])" :key="item.key">
              <el-sub-menu v-if="item.items && item.items.length" :index="item.key">
                <template #title>
                  <el-icon><component :is="getIcon(item.icon || g.icon)" /></el-icon>
                  <span>{{ item.label }}</span>
                </template>
                <el-menu-item
                  v-for="leaf in (item.items || [])"
                  :key="leaf.key"
                  :index="leaf.key"
                >{{ leaf.label }}</el-menu-item>
              </el-sub-menu>
              <el-menu-item v-else :index="item.key">{{ item.label }}</el-menu-item>
            </template>
          </el-sub-menu>
          <el-menu-item v-else :index="g.key">
            <el-icon><component :is="getIcon(g.icon)" /></el-icon>
            <span>{{ g.label }}</span>
          </el-menu-item>
        </template>
      </el-menu>
    </aside>

    <div class="main-area">
      <header class="header">
        <div class="header-left">
          <button class="collapse-btn" @click="appStore.toggleSidebar">
            <el-icon><Fold v-if="!appStore.sidebarCollapsed" /><Expand v-else /></el-icon>
          </button>
          <h1 class="page-title">{{ currentTitle }}</h1>
        </div>
        <div class="header-right">
          <div class="db-mode-toggle" :class="appStore.dbMode" @click="handleDbModeSwitch">
            <el-icon :size="14"><DataBoard /></el-icon>
            <span class="db-mode-label">{{ appStore.dbMode === 'demo' ? 'DEMO' : 'REAL' }}</span>
          </div>
          <el-popover trigger="click" placement="bottom-end" :width="180">
            <template #reference>
              <button class="header-action" title="外观设置">
                <el-icon><Brush /></el-icon>
              </button>
            </template>
            <div class="appearance-panel">
              <div class="appearance-label">主题</div>
              <div class="theme-toggle-row">
                <span
                  class="theme-opt"
                  :class="{ active: appStore.theme === 'light' }"
                  @click="appStore.theme = 'light'"
                >
                  <el-icon :size="14"><Sunny /></el-icon>
                  <span>亮色</span>
                </span>
                <span
                  class="theme-opt"
                  :class="{ active: appStore.theme === 'dark' }"
                  @click="appStore.theme = 'dark'"
                >
                  <el-icon :size="14"><MoonNight /></el-icon>
                  <span>暗色</span>
                </span>
              </div>
              <div class="appearance-label">色系</div>
              <div class="scheme-row">
                <span
                  class="color-dot indigo"
                  :class="{ active: appStore.colorScheme === 'indigo' }"
                  @click="appStore.setColorScheme('indigo')"
                >靛蓝</span>
                <span
                  class="color-dot terra-cotta"
                  :class="{ active: appStore.colorScheme === 'terra-cotta' }"
                  @click="appStore.setColorScheme('terra-cotta')"
                >赤陶</span>
              </div>
            </div>
          </el-popover>
          <button class="header-action" @click="toggleChatWidget" title="AI 助手">
            <el-icon><ChatDotRound /></el-icon>
          </button>
          <el-popover trigger="click" placement="bottom" :width="300">
            <template #reference>
              <button class="header-action">
                <el-badge :value="noticeCount" :hidden="noticeCount === 0">
                  <el-icon><Bell /></el-icon>
                </el-badge>
              </button>
            </template>
            <div class="notif-panel">
              <div class="notif-panel-title">系统通知</div>
              <div v-for="(n, i) in notifications" :key="i" class="notif-item" @click="handleNotifClick(n)">
                <span>{{ n.icon }}</span>
                <div class="notif-body">
                  <div class="notif-text">{{ n.title }}</div>
                  <div class="notif-time">{{ n.time }}</div>
                </div>
              </div>
              <div v-if="!notifications.length" class="notif-empty">暂无通知</div>
            </div>
          </el-popover>
          <el-dropdown trigger="click" @command="handleUserCommand" placement="bottom-end">
            <el-avatar :size="28" class="header-avatar">
              <el-icon :size="16"><User /></el-icon>
            </el-avatar>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">个人中心</el-dropdown-item>
                <el-dropdown-item command="settings">系统设置</el-dropdown-item>
                <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <main class="content">
        <div class="content-inner">
          <DashboardView v-if="activeView === 'dashboard'" />
          <SystemPosture v-else-if="activeView === 'system-posture'" />
          <AgentAudit v-else-if="activeView === 'agent-audit'" />
          <OperationAudit v-else-if="activeView === 'op-audit'" />
          <AgentChatView v-else-if="activeView === 'agent-chat'" />
          <MenuConfig v-else-if="activeView === 'menu-config'" />
          <TraceView v-else-if="activeView === 'trace-view'" />
    <TraceAgentGuide v-else-if="activeView === 'trace-agent-guide'" />
          <MetricsView v-else-if="activeView === 'metrics-view'" />
          <ErrorBudgetView v-else-if="activeView === 'error-budget'" />
          <BurnRateView v-else-if="activeView === 'burn-rate'" />
          <SLOConfigView v-else-if="activeView === 'slo-config'" />
          <SLAView v-else-if="activeView === 'sla-agreement'" />
          <OnCallView v-else-if="activeView === 'oncall-schedule'" />
          <EscalationPolicyView v-else-if="activeView === 'escalation-policy'" />
          <AvailabilityReportView v-else-if="activeView === 'availability-report'" />
          <ChaosExperimentView v-else-if="activeView === 'chaos-experiment'" />
          <ChaosReportView v-else-if="activeView === 'chaos-report'" />
          <ChaosScenarioView v-else-if="activeView === 'chaos-scenario'" />
          <iframe v-else-if="activePath" :src="activePath" class="content-iframe" frameborder="0" />
        </div>
      </main>
    </div>

    <AIOpsChatWidget ref="chatWidgetRef" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAppStore } from '@/stores/app'
import { ElMessage } from 'element-plus'
import {
  ChatDotRound, Fold, Expand, Bell, Brush,
  Odometer, ChatDotSquare, DataLine, Tickets, Operation, Monitor,
  Box, Setting, TrendCharts, Coin, Connection, WarningFilled, Search,
  Lightning, User, Tools, Link, MoonNight, Sunny, DataBoard, Loading,
  Cpu, DataAnalysis, Cloudy, Warning
} from '@element-plus/icons-vue'
import AIOpsChatWidget from '@/components/AIOpsChatWidget.vue'
import DashboardView from '@/views/DashboardView.vue'
import AgentAudit from '@/views/AgentAudit.vue'
import OperationAudit from '@/views/OperationAudit.vue'
import AgentChatView from '@/views/AgentChatView.vue'
import MenuConfig from '@/views/MenuConfig.vue'
import SystemPosture from '@/views/SystemPosture.vue'
import TraceView from '@/views/TraceView.vue'
import TraceAgentGuide from '@/views/TraceAgentGuide.vue'
import MetricsView from '@/views/MetricsView.vue'
import ErrorBudgetView from '@/views/ErrorBudgetView.vue'
import OnCallView from '@/views/OnCallView.vue'
import BurnRateView from '@/views/BurnRateView.vue'
import SLOConfigView from '@/views/SLOConfigView.vue'
import SLAView from '@/views/SLAView.vue'
import EscalationPolicyView from '@/views/EscalationPolicyView.vue'
import AvailabilityReportView from '@/views/AvailabilityReportView.vue'
import ChaosExperimentView from '@/views/ChaosExperimentView.vue'
import ChaosReportView from '@/views/ChaosReportView.vue'
import ChaosScenarioView from '@/views/ChaosScenarioView.vue'
import request from '@/api/request'

const appStore = useAppStore()
const chatWidgetRef = ref(null)

// 切换数据库重载时，同步读取上次菜单位置，避免首帧闪烁仪表盘
const _savedMenu = localStorage.getItem('aiops-active-menu')
const menuLoading = ref(!!_savedMenu)  // 有待恢复的菜单时，显示 loading 遮罩
const activeView = ref('dashboard')
const activePath = ref(null)
const currentTitle = ref(_savedMenu ? '' : '运行概览')
const activeMenu = ref(_savedMenu || 'dashboard')
const noticeCount = ref(3)
const notifications = ref([
  { icon: '🚨', title: '检测到 3 条未处理告警', time: '2 分钟前', route: 'alert-center' },
  { icon: '⚡', title: '192.168.100.129 CPU 负载超过 80%', time: '10 分钟前', route: 'alert-center' },
  { icon: '📦', title: 'K8s 集群节点状态正常', time: '30 分钟前', route: 'k8s-overview' },
])
const menuGroups = ref([])

const ICON_MAP = {
  Odometer, ChatDotSquare, DataLine, Tickets, Operation, Monitor,
  Box, Setting, TrendCharts, Coin, Connection, WarningFilled, Search,
  Lightning, User, Tools, Link, Cpu, DataAnalysis, Cloudy, Warning
}

function getIcon(name) {
  return ICON_MAP[name] || Monitor
}

const VUE_PAGES = new Set(['dashboard', 'agent-chat', 'agent-audit', 'op-audit', 'menu-config', 'system-posture', 'trace-view', 'trace-agent-guide', 'metrics-view', 'error-budget', 'burn-rate', 'slo-config', 'sla-agreement', 'oncall-schedule', 'escalation-policy', 'availability-report', 'chaos-experiment', 'chaos-report', 'chaos-scenario'])

function _flattenItems(items) {
  const result = []
  for (const item of items) {
    if (item.items && item.items.length) {
      result.push(..._flattenItems(item.items))
    } else {
      result.push(item)
    }
  }
  return result
}

function _findItem(key) {
  for (const g of menuGroups.value) {
    if (g.key === key) return g
    if (g.items) {
      for (const item of g.items) {
        if (item.key === key) return item
        if (item.items) {
          for (const leaf of item.items) {
            if (leaf.key === key) return leaf
          }
        }
      }
    }
  }
  return null
}

function handleMenuSelect(arg) {
  const key = typeof arg === 'string' ? arg : (arg.key || '')
  activeMenu.value = key
  const item = _findItem(key)

  if (!item || !item.type) {
    return
  }

  currentTitle.value = item.label

  const pathKey = item.path.replace(/^\//, '')

  if (item.type === 'vue' || VUE_PAGES.has(pathKey)) {
    activeView.value = pathKey
    activePath.value = null
  } else {
    activeView.value = ''
    activePath.value = item.path
  }
}

function toggleChatWidget() {
  if (chatWidgetRef.value) {
    chatWidgetRef.value.toggleOpen()
  }
}

function handleUserCommand(command) {
  if (command === 'logout') {
    window.location.href = '/logout'
  } else if (command === 'profile') {
    handleMenuSelect('users')
  } else if (command === 'settings') {
    handleMenuSelect('settings')
  }
}

function handleNotifClick(n) {
  if (n.route) {
    handleMenuSelect(n.route)
  }
}

onMounted(async () => {
  window._navigateTo = (key) => handleMenuSelect(key)
  window._navigateToIframe = (path) => {
    const item = { type: 'iframe', path }
    activeMenu.value = path
    activeView.value = ''
    activePath.value = path
    currentTitle.value = path
  }
  // 获取当前数据库模式
  appStore.fetchDbMode()

  try {
    const data = await request.get('/api/menu')
    menuGroups.value = Array.isArray(data) ? data : (data.menu || [])
    // 恢复切换数据库前的菜单位置
    if (_savedMenu) {
      localStorage.removeItem('aiops-active-menu')
      handleMenuSelect(_savedMenu)
    }
  } catch (e) {
    ElMessage.error('加载菜单失败: ' + e.message)
  } finally {
    menuLoading.value = false
  }
})

async function handleDbModeSwitch() {
  const nextMode = appStore.dbMode === 'demo' ? 'real' : 'demo'
  try {
    const data = await appStore.switchDbMode(nextMode)
    ElMessage.success(data.message)
    // 保存当前菜单位置，重载后恢复
    localStorage.setItem('aiops-active-menu', activeMenu.value)
    setTimeout(() => window.location.reload(), 800)
  } catch (e) {
    ElMessage.error('切换失败: ' + e.message)
  }
}
</script>

<style scoped>
/* 数据库模式切换按钮 */
.db-mode-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  user-select: none;
  transition: all 0.25s;
  border: 1.5px solid transparent;
  white-space: nowrap;
}
.db-mode-toggle.demo {
  background: rgba(99, 102, 241, 0.1);
  color: #6366f1;
  border-color: rgba(99, 102, 241, 0.3);
}
.db-mode-toggle.demo:hover {
  background: rgba(99, 102, 241, 0.2);
}
.db-mode-toggle.real {
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
  border-color: rgba(16, 185, 129, 0.3);
}
.db-mode-toggle.real:hover {
  background: rgba(16, 185, 129, 0.2);
}
.db-mode-label {
  letter-spacing: 0.5px;
}
/* 切换数据库 loading 遮罩 */
.menu-loading-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary, #f5f7fa);
}
.loading-spin {
  animation: spin 0.8s linear infinite;
  color: var(--primary-color, #6366f1);
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
