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
        :collapse-transition="false"
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
            <div class="user-info-trigger">
              <span v-if="userInfo && userInfo.tenant_name" class="tenant-badge">{{ userInfo.tenant_name }}</span>
              <el-avatar :size="28" class="header-avatar">
                <el-icon :size="16"><User /></el-icon>
              </el-avatar>
            </div>
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
          <MonitorView v-if="activeView === 'monitor-view'" />
          <DashboardView v-else-if="activeView === 'dashboard'" />
          <SystemPosture v-else-if="activeView === 'system-posture'" />
      <AgentAudit v-else-if="activeView === 'audit'" />
      <OperationAudit v-else-if="activeView === 'op-audit'" />
      <AgentChatView v-else-if="activeView === 'agent-chat'" />
      <MenuConfig v-else-if="activeView === 'menu-config'" />
      <TraceView v-else-if="activeView === 'traces'" />
    <TraceAgentGuide v-else-if="activeView === 'discovery'" />
      <MetricsView v-else-if="activeView === 'metrics'" />
          <ErrorBudgetView v-else-if="activeView === 'error-budget'" />
          <BurnRateView v-else-if="activeView === 'burn-rate'" />
          <SloDashboardView v-else-if="activeView === 'slo-dashboard'" />
          <SLOConfigView v-else-if="activeView === 'slo-config'" />
          <SLAView v-else-if="activeView === 'sla-agreement'" />
          <OnCallView v-else-if="activeView === 'oncall-schedule'" />
          <EscalationPolicyView v-else-if="activeView === 'escalation-policy'" />
          <AvailabilityReportView v-else-if="activeView === 'availability-report'" />
          <ChaosExperimentView v-else-if="activeView === 'chaos-experiment'" />
          <ChaosReportView v-else-if="activeView === 'chaos-report'" />
          <ChaosScenarioView v-else-if="activeView === 'chaos-scenario'" />
          <AlertsView v-else-if="activeView === 'alerts'" />
          <AssetsView v-else-if="activeView === 'asset-list'" />
          <DatasourcesView v-else-if="activeView === 'datasources'" />
          <LogsView v-else-if="activeView === 'logs'" />
      <IncidentsView v-else-if="activeView === 'incident'" />
      <EventStatsView v-else-if="activeView === 'event-stats'" />
      <EventSourcesView v-else-if="activeView === 'event-sources'" />
      <AnomalyView v-else-if="activeView === 'anomaly'" />
      <RemediationView v-else-if="activeView === 'remediation'" />
      <RemediationWorkflowView v-else-if="activeView === 'remediation-workflow'" />
      <ScriptExecView v-else-if="activeView === 'script-exec'" />
      <BlueGreenView v-else-if="activeView === 'blue-green'" />
      <ChangeWorkflowView v-else-if="activeView === 'change-workflow'" />
      <PendingActionsView v-else-if="activeView === 'pending-actions'" />
          <AiProvidersView v-else-if="activeView === 'ai-providers'" />
          <AgentCapabilitiesView v-else-if="activeView === 'agent-capabilities'" />
          <FeatureStoreView v-else-if="activeView === 'feature-store'" />
          <PredictionModelsView v-else-if="activeView === 'prediction-models'" />
          <UsersView v-else-if="activeView === 'users'" />
          <NotificationsView v-else-if="activeView === 'notifications'" />
          <SettingsView v-else-if="activeView === 'settings'" />
          <EsIntegrationView v-else-if="activeView === 'integration'" />
          <TagsView v-else-if="activeView === 'tags'" />
          <ExtCmdbView v-else-if="activeView === 'ext-cmdb'" />
          <ReportsView v-else-if="activeView === 'reports'" />
          <K8sOverviewView v-else-if="activeView === 'k8s-overview'" />
          <K8sMonitorView v-else-if="activeView === 'k8s-monitor'" />
          <K8sResourceListView v-else-if="activeView === 'k8s-statefulsets'" resource-type="statefulsets" />
          <K8sResourceListView v-else-if="activeView === 'k8s-daemonsets'" resource-type="daemonsets" />
          <K8sResourceListView v-else-if="activeView === 'k8s-services'" resource-type="services" />
          <K8sResourceListView v-else-if="activeView === 'k8s-ingresses'" resource-type="ingresses" />
          <K8sResourceListView v-else-if="activeView === 'k8s-configmaps'" resource-type="configmaps" />
          <K8sResourceListView v-else-if="activeView === 'k8s-secrets'" resource-type="secrets" />
          <K8sResourceListView v-else-if="activeView === 'k8s-hpas'" resource-type="hpas" />
          <K8sResourceListView v-else-if="activeView === 'k8s-pvcs'" resource-type="pvcs" />
          <K8sResourceListView v-else-if="activeView === 'k8s-pvs'" resource-type="pvs" />
          <K8sResourceListView v-else-if="activeView === 'k8s-namespaces'" resource-type="namespaces" />
          <ContainerTopologyView v-else-if="activeView === 'k8s-topology'" />
          <K8sPodsView v-else-if="activeView === 'k8s-pods'" />
          <K8sDeploymentsView v-else-if="activeView === 'k8s-deployments'" />
          <DockerOverviewView v-else-if="activeView === 'docker-overview'" />
          <DockerListView v-else-if="activeView === 'docker-list'" />
          <KnowledgeView v-else-if="activeView === 'kb-list'" />
          <KnowledgeDocumentsView v-else-if="activeView === 'kb-documents'" />
          <KnowledgeGraphView v-else-if="activeView === 'kb-graph'" />
          <GraphInferenceView v-else-if="activeView === 'graph-inference'" />
          <SmartRecommendView v-else-if="activeView === 'smart-recommend'" />
          <RunbooksView v-else-if="activeView === 'runbooks'" />
          <LifecycleView v-else-if="activeView === 'lifecycle'" />
          <TopologyView v-else-if="activeView === 'topology'" />
          <TopologyPathView v-else-if="activeView === 'topology-path'" />
          <OpenApiView v-else-if="activeView === 'openapi'" />
          <WorkflowRunsView v-else-if="activeView === 'workflow-runs'" />
          <WorkflowTemplatesView v-else-if="activeView === 'workflow-templates'" />
          <AgentWorkflowEditor v-else-if="activeView === 'agent-workflow-editor'" />
          <AgentWorkflowRunsView v-else-if="activeView === 'agent-workflow-runs'" />
          <HelmView v-else-if="activeView === 'helm-releases'" />
          <AnsibleView v-else-if="activeView === 'ansible'" />
          <LicenseView v-else-if="activeView === 'license'" />
          <FireMapView v-else-if="activeView === 'firemap'" />
          <InspectionView v-else-if="activeView === 'smart-inspection'" />
          <KnowledgeDraftView v-else-if="activeView === 'knowledge-draft'" />
          <RemediationEffectView v-else-if="activeView === 'remediation-effect'" />
          <AgentEvalView v-else-if="activeView === 'agent-eval'" />
          <ABTestView v-else-if="activeView === 'ab-test'" />
          <RAGRerankView v-else-if="activeView === 'rag-rerank'" />
          <AnomalyBenchmarkView v-else-if="activeView === 'anomaly-benchmark'" />
          <AssetDiscoveryView v-else-if="activeView === 'asset-discovery'" />
          <OpsAnalyticsView v-else-if="activeView === 'ops-analytics'" />
          <DashboardDesignerView v-else-if="activeView === 'dashboard-designer'" />
          <DiagnosticToolsView v-else-if="activeView === 'diagnostic-tools'" />
          <TenantManagementView v-else-if="activeView === 'tenant-management'" />
          <RolesView v-else-if="activeView === 'roles-manage'" />
          <ObservabilityCorrelationView v-else-if="activeView === 'observability-correlation'" />
          <TraceAnomalyConfigView v-else-if="activeView === 'trace-anomaly-config'" />
          <AgentGroundTruthView v-else-if="activeView === 'agent-ground-truth'" />
          <K8sHpaRecommendView v-else-if="activeView === 'k8s-hpa-recommend'" />
          <K8sResourceOptimizeView v-else-if="activeView === 'k8s-resource-optimize'" />
          <iframe v-else-if="activePath" :src="activePath" class="content-iframe" frameborder="0" />
        </div>
      </main>
    </div>

    <AIOpsChatWidget ref="chatWidgetRef" />
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
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
const AgentAudit = defineAsyncComponent(() => import('@/views/AgentAudit.vue'))
const OperationAudit = defineAsyncComponent(() => import('@/views/OperationAudit.vue'))
const AgentChatView = defineAsyncComponent(() => import('@/views/AgentChatView.vue'))
const MenuConfig = defineAsyncComponent(() => import('@/views/MenuConfig.vue'))
const SystemPosture = defineAsyncComponent(() => import('@/views/SystemPosture.vue'))
const TraceView = defineAsyncComponent(() => import('@/views/TraceView.vue'))
const TraceAgentGuide = defineAsyncComponent(() => import('@/views/TraceAgentGuide.vue'))
const MetricsView = defineAsyncComponent(() => import('@/views/MetricsView.vue'))
const ErrorBudgetView = defineAsyncComponent(() => import('@/views/ErrorBudgetView.vue'))
const OnCallView = defineAsyncComponent(() => import('@/views/OnCallView.vue'))
const BurnRateView = defineAsyncComponent(() => import('@/views/BurnRateView.vue'))
const SLOConfigView = defineAsyncComponent(() => import('@/views/SLOConfigView.vue'))
const SloDashboardView = defineAsyncComponent(() => import('@/views/SloDashboardView.vue'))
const SLAView = defineAsyncComponent(() => import('@/views/SLAView.vue'))
const EscalationPolicyView = defineAsyncComponent(() => import('@/views/EscalationPolicyView.vue'))
const AvailabilityReportView = defineAsyncComponent(() => import('@/views/AvailabilityReportView.vue'))
const ChaosExperimentView = defineAsyncComponent(() => import('@/views/ChaosExperimentView.vue'))
const ChaosReportView = defineAsyncComponent(() => import('@/views/ChaosReportView.vue'))
const ChaosScenarioView = defineAsyncComponent(() => import('@/views/ChaosScenarioView.vue'))
const AlertsView = defineAsyncComponent(() => import('@/views/AlertsView.vue'))
const AssetsView = defineAsyncComponent(() => import('@/views/AssetsView.vue'))
const DatasourcesView = defineAsyncComponent(() => import('@/views/DatasourcesView.vue'))
const LogsView = defineAsyncComponent(() => import('@/views/LogsView.vue'))
const IncidentsView = defineAsyncComponent(() => import('@/views/IncidentsView.vue'))
const EventStatsView = defineAsyncComponent(() => import('@/views/EventStatsView.vue'))
const EventSourcesView = defineAsyncComponent(() => import('@/views/EventSourcesView.vue'))
const AnomalyView = defineAsyncComponent(() => import('@/views/AnomalyView.vue'))
const RemediationView = defineAsyncComponent(() => import('@/views/RemediationView.vue'))
const RemediationWorkflowView = defineAsyncComponent(() => import('@/views/RemediationWorkflowView.vue'))
const ScriptExecView = defineAsyncComponent(() => import('@/views/ScriptExecView.vue'))
const BlueGreenView = defineAsyncComponent(() => import('@/views/BlueGreenView.vue'))
const ChangeWorkflowView = defineAsyncComponent(() => import('@/views/ChangeWorkflowView.vue'))
const PendingActionsView = defineAsyncComponent(() => import('@/views/PendingActionsView.vue'))
const AiProvidersView = defineAsyncComponent(() => import('@/views/AiProvidersView.vue'))
const FeatureStoreView = defineAsyncComponent(() => import('@/views/FeatureStoreView.vue'))
const PredictionModelsView = defineAsyncComponent(() => import('@/views/PredictionModelsView.vue'))
const UsersView = defineAsyncComponent(() => import('@/views/UsersView.vue'))
const NotificationsView = defineAsyncComponent(() => import('@/views/NotificationsView.vue'))
const SettingsView = defineAsyncComponent(() => import('@/views/SettingsView.vue'))
const EsIntegrationView = defineAsyncComponent(() => import('@/views/EsIntegrationView.vue'))
const TagsView = defineAsyncComponent(() => import('@/views/TagsView.vue'))
const ExtCmdbView = defineAsyncComponent(() => import('@/views/ExtCmdbView.vue'))
const ReportsView = defineAsyncComponent(() => import('@/views/ReportsView.vue'))
const K8sOverviewView = defineAsyncComponent(() => import('@/views/K8sOverviewView.vue'))
const K8sMonitorView = defineAsyncComponent(() => import('@/views/K8sMonitorView.vue'))
const K8sResourceListView = defineAsyncComponent(() => import('@/views/K8sResourceListView.vue'))
const ContainerTopologyView = defineAsyncComponent(() => import('@/views/ContainerTopologyView.vue'))
const K8sPodsView = defineAsyncComponent(() => import('@/views/K8sPodsView.vue'))
const K8sDeploymentsView = defineAsyncComponent(() => import('@/views/K8sDeploymentsView.vue'))
const DockerOverviewView = defineAsyncComponent(() => import('@/views/DockerOverviewView.vue'))
const DockerListView = defineAsyncComponent(() => import('@/views/DockerListView.vue'))
const KnowledgeView = defineAsyncComponent(() => import('@/views/KnowledgeView.vue'))
const KnowledgeDocumentsView = defineAsyncComponent(() => import('@/views/KnowledgeDocumentsView.vue'))
const KnowledgeGraphView = defineAsyncComponent(() => import('@/views/KnowledgeGraphView.vue'))
const GraphInferenceView = defineAsyncComponent(() => import('@/views/GraphInferenceView.vue'))
const SmartRecommendView = defineAsyncComponent(() => import('@/views/SmartRecommendView.vue'))
const RunbooksView = defineAsyncComponent(() => import('@/views/RunbooksView.vue'))
const LifecycleView = defineAsyncComponent(() => import('@/views/LifecycleView.vue'))
const TopologyView = defineAsyncComponent(() => import('@/views/TopologyView.vue'))
const TopologyPathView = defineAsyncComponent(() => import('@/views/TopologyPathView.vue'))
const OpenApiView = defineAsyncComponent(() => import('@/views/OpenApiView.vue'))
const WorkflowRunsView = defineAsyncComponent(() => import('@/views/WorkflowRunsView.vue'))
const WorkflowTemplatesView = defineAsyncComponent(() => import('@/views/WorkflowTemplatesView.vue'))
const AgentWorkflowEditor = defineAsyncComponent(() => import('@/views/AgentWorkflowEditor.vue'))
const AgentWorkflowRunsView = defineAsyncComponent(() => import('@/views/AgentWorkflowRunsView.vue'))
const HelmView = defineAsyncComponent(() => import('@/views/HelmView.vue'))
const AnsibleView = defineAsyncComponent(() => import('@/views/AnsibleView.vue'))
const LicenseView = defineAsyncComponent(() => import('@/views/LicenseView.vue'))
const FireMapView = defineAsyncComponent(() => import('@/views/FireMapView.vue'))
const InspectionView = defineAsyncComponent(() => import('@/views/InspectionView.vue'))
const KnowledgeDraftView = defineAsyncComponent(() => import('@/views/KnowledgeDraftView.vue'))
const RemediationEffectView = defineAsyncComponent(() => import('@/views/RemediationEffectView.vue'))
const AgentEvalView = defineAsyncComponent(() => import('@/views/AgentEvalView.vue'))
const ABTestView = defineAsyncComponent(() => import('@/views/ABTestView.vue'))
const RAGRerankView = defineAsyncComponent(() => import('@/views/RAGRerankView.vue'))
const AnomalyBenchmarkView = defineAsyncComponent(() => import('@/views/AnomalyBenchmarkView.vue'))
const AssetDiscoveryView = defineAsyncComponent(() => import('@/views/AssetDiscoveryView.vue'))
const OpsAnalyticsView = defineAsyncComponent(() => import('@/views/OpsAnalyticsView.vue'))
const DashboardDesignerView = defineAsyncComponent(() => import('@/views/DashboardDesignerView.vue'))
const DiagnosticToolsView = defineAsyncComponent(() => import('@/views/DiagnosticToolsView.vue'))
const TenantManagementView = defineAsyncComponent(() => import('@/views/TenantManagementView.vue'))
const AgentCapabilitiesView = defineAsyncComponent(() => import('@/views/AgentCapabilitiesView.vue'))
const RolesView = defineAsyncComponent(() => import('@/views/RolesView.vue'))
const ObservabilityCorrelationView = defineAsyncComponent(() => import('@/views/ObservabilityCorrelationView.vue'))
const TraceAnomalyConfigView = defineAsyncComponent(() => import('@/views/TraceAnomalyConfigView.vue'))
const AgentGroundTruthView = defineAsyncComponent(() => import('@/views/AgentGroundTruthView.vue'))
const K8sHpaRecommendView = defineAsyncComponent(() => import('@/views/K8sHpaRecommendView.vue'))
const K8sResourceOptimizeView = defineAsyncComponent(() => import('@/views/K8sResourceOptimizeView.vue'))
const MonitorView = defineAsyncComponent(() => import('@/views/MonitorView.vue'))
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
const noticeCount = ref(0)
const notifications = ref([])
const userInfo = ref(null)
let notifTimer = null

async function loadNotifications() {
  try {
    const data = await request.get('/notifications/api/recent')
    notifications.value = data.notifications || []
    noticeCount.value = data.count || 0
  } catch (e) {
    // 静默失败，不打扰用户（顶栏通知非关键路径）
    console.error('load notifications:', e)
  }
}

async function loadUserInfo() {
  try {
    const data = await request.get('/me')
    if (data.ok && data.user) {
      userInfo.value = data.user
    }
  } catch (e) {
    console.error('load user info:', e)
  }
}
const menuGroups = ref([])

const ICON_MAP = {
  Odometer, ChatDotSquare, DataLine, Tickets, Operation, Monitor,
  Box, Setting, TrendCharts, Coin, Connection, WarningFilled, Search,
  Lightning, User, Tools, Link, Cpu, DataAnalysis, Cloudy, Warning
}

function getIcon(name) {
  return ICON_MAP[name] || Monitor
}

const VUE_PAGES = new Set(['dashboard', 'roles-manage', 'agent-chat', 'audit', 'op-audit', 'menu-config', 'system-posture', 'traces', 'discovery', 'metrics', 'error-budget', 'burn-rate', 'slo-config', 'slo-dashboard', 'sla-agreement', 'oncall-schedule', 'escalation-policy', 'availability-report', 'chaos-experiment', 'chaos-report', 'chaos-scenario', 'alerts', 'asset-list', 'datasources', 'logs', 'incident', 'event-stats', 'event-sources', 'anomaly', 'remediation', 'remediation-workflow', 'script-exec', 'blue-green', 'change-workflow', 'pending-actions', 'ai-providers', 'feature-store', 'prediction-models', 'users', 'notifications', 'settings', 'integration', 'tags', 'ext-cmdb', 'reports', 'k8s-overview', 'k8s-monitor', 'k8s-statefulsets', 'k8s-daemonsets', 'k8s-services', 'k8s-ingresses', 'k8s-configmaps', 'k8s-secrets', 'k8s-hpas', 'k8s-pvcs', 'k8s-pvs', 'k8s-topology', 'k8s-pods', 'k8s-deployments', 'docker-overview', 'docker-list', 'kb-list', 'kb-documents', 'kb-graph', 'graph-inference', 'smart-recommend', 'runbooks', 'lifecycle', 'topology', 'topology-path', 'openapi', 'workflow-runs', 'workflow-templates', 'agent-workflow-editor', 'agent-workflow-runs', 'helm-releases', 'ansible', 'license', 'k8s-namespaces', 'firemap', 'smart-inspection', 'knowledge-draft', 'remediation-effect', 'agent-eval', 'ab-test', 'rag-rerank', 'anomaly-benchmark', 'asset-discovery', 'ops-analytics', 'dashboard-designer', 'diagnostic-tools', 'tenant-management', 'observability-correlation', 'trace-anomaly-config', 'agent-ground-truth', 'k8s-hpa-recommend', 'k8s-resource-optimize'])

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

  if (item.type === 'vue' || VUE_PAGES.has(key)) {
    activeView.value = key
    activePath.value = null
  } else {
    activeView.value = ''
    activePath.value = item.path
  }
  // 持久化当前菜单位置，供刷新恢复
  localStorage.setItem('aiops-active-menu', key)
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

  // 加载真实系统通知 + 30s 定时刷新
  loadNotifications()
  notifTimer = setInterval(loadNotifications, 30000)

  // 加载用户信息（含租户）
  loadUserInfo()

  try {
    const data = await request.get('/api/menu')
    menuGroups.value = Array.isArray(data) ? data : (data.menu || [])
    // 恢复上次菜单位置（刷新或切换数据库后均生效）
    if (_savedMenu) {
      const item = _findItem(_savedMenu)
      if (item) {
        handleMenuSelect(_savedMenu)
      } else {
        // 菜单项不存在（如切换数据库后菜单变化），清除存储回到默认
        localStorage.removeItem('aiops-active-menu')
      }
    }
  } catch (e) {
    ElMessage.error('加载菜单失败: ' + e.message)
  } finally {
    menuLoading.value = false
  }
})

onBeforeUnmount(() => {
  if (notifTimer) {
    clearInterval(notifTimer)
    notifTimer = null
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
.user-info-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}
.tenant-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(99, 102, 241, 0.1);
  color: #6366f1;
  font-weight: 500;
  white-space: nowrap;
}
</style>
