<template>
  <div class="app-layout">
    <!-- 切换数据库时的 loading 遮罩，遮挡首帧仪表盘闪烁 -->
    <div v-if="menuLoading" class="menu-loading-overlay">
      <el-icon class="loading-spin" :size="32"><Loading /></el-icon>
    </div>
    <aside class="sidebar" :class="{ collapsed: appStore.sidebarCollapsed }">
<div class="sidebar-header">
        <div class="logo-badge">
          <!-- Taste 皮肤: 粉橙 -->
          <svg v-if="appStore.skin === 'taste'" viewBox="0 0 44 44" width="40" height="40">
            <defs><linearGradient id="lgA" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#c84e89" /><stop offset="100%" stop-color="#f15f79" /></linearGradient>
            <linearGradient id="lgB" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#fcb045" /><stop offset="100%" stop-color="#f59e0b" /></linearGradient></defs>
            <rect x="8" y="6" width="4" height="32" rx="2" fill="url(#lgA)" /><rect x="32" y="6" width="4" height="32" rx="2" fill="url(#lgB)" />
            <rect x="8" y="6" width="28" height="4" rx="2" fill="url(#lgA)" /><rect x="8" y="34" width="28" height="4" rx="2" fill="url(#lgB)" />
            <rect x="8" y="20" width="28" height="3" rx="1.5" fill="url(#lgA)" opacity="0.6" />
            <line x1="8" y1="6" x2="36" y2="20" stroke="url(#lgA)" stroke-width="2.5" stroke-linecap="round" />
            <line x1="8" y1="20" x2="36" y2="34" stroke="url(#lgB)" stroke-width="2.5" stroke-linecap="round" />
            <circle cx="8" cy="6" r="2.5" fill="#fff" /><circle cx="36" cy="6" r="2.5" fill="#fff" />
            <circle cx="8" cy="34" r="2.5" fill="#fff" /><circle cx="36" cy="34" r="2.5" fill="#fff" />
            <circle cx="8" cy="20" r="2" fill="#fff" /><circle cx="36" cy="20" r="2" fill="#fff" />
            <circle cx="22" cy="20" r="3" fill="url(#lgA)" /><circle cx="22" cy="20" r="1.5" fill="#fff" />
          </svg>
          <!-- Frost 皮肤: 冰霜 -->
          <svg v-else-if="appStore.skin === 'frost'" viewBox="0 0 44 44" width="40" height="40">
            <defs><linearGradient id="lgA" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#06b6d4" /><stop offset="100%" stop-color="#22d3ee" /></linearGradient>
            <linearGradient id="lgB" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#e2e8f0" /><stop offset="100%" stop-color="#f1f5f9" /></linearGradient></defs>
            <rect x="8" y="6" width="4" height="32" rx="2" fill="url(#lgA)" /><rect x="32" y="6" width="4" height="32" rx="2" fill="url(#lgB)" />
            <rect x="8" y="6" width="28" height="4" rx="2" fill="url(#lgA)" /><rect x="8" y="34" width="28" height="4" rx="2" fill="url(#lgB)" />
            <rect x="8" y="20" width="28" height="3" rx="1.5" fill="url(#lgA)" opacity="0.6" />
            <line x1="8" y1="6" x2="36" y2="20" stroke="url(#lgA)" stroke-width="2.5" stroke-linecap="round" />
            <line x1="8" y1="20" x2="36" y2="34" stroke="url(#lgB)" stroke-width="2.5" stroke-linecap="round" />
            <circle cx="8" cy="6" r="2.5" fill="#fff" /><circle cx="36" cy="6" r="2.5" fill="#fff" />
            <circle cx="8" cy="34" r="2.5" fill="#fff" /><circle cx="36" cy="34" r="2.5" fill="#fff" />
            <circle cx="8" cy="20" r="2" fill="#fff" /><circle cx="36" cy="20" r="2" fill="#fff" />
            <circle cx="22" cy="20" r="3" fill="url(#lgA)" /><circle cx="22" cy="20" r="1.5" fill="#fff" />
          </svg>
          <!-- Nebula 皮肤: 深空星云 -->
          <svg v-else-if="appStore.skin === 'nebula'" viewBox="0 0 44 44" width="40" height="40">
            <defs><linearGradient id="lgA" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#7c3aed" /><stop offset="100%" stop-color="#c026d3" /></linearGradient>
            <linearGradient id="lgB" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#22d3ee" /><stop offset="100%" stop-color="#818cf8" /></linearGradient></defs>
            <rect x="8" y="6" width="4" height="32" rx="2" fill="url(#lgA)" /><rect x="32" y="6" width="4" height="32" rx="2" fill="url(#lgB)" />
            <rect x="8" y="6" width="28" height="4" rx="2" fill="url(#lgA)" /><rect x="8" y="34" width="28" height="4" rx="2" fill="url(#lgB)" />
            <rect x="8" y="20" width="28" height="3" rx="1.5" fill="url(#lgA)" opacity="0.6" />
            <line x1="8" y1="6" x2="36" y2="20" stroke="url(#lgA)" stroke-width="2.5" stroke-linecap="round" />
            <line x1="8" y1="20" x2="36" y2="34" stroke="url(#lgB)" stroke-width="2.5" stroke-linecap="round" />
            <circle cx="8" cy="6" r="2.5" fill="#fff" /><circle cx="36" cy="6" r="2.5" fill="#e9d5ff" />
            <circle cx="8" cy="34" r="2.5" fill="#e0f2fe" /><circle cx="36" cy="34" r="2.5" fill="#fff" />
            <circle cx="8" cy="20" r="2" fill="#fff" /><circle cx="36" cy="20" r="2" fill="#fff" />
            <circle cx="22" cy="20" r="3" fill="url(#lgA)" /><circle cx="22" cy="20" r="1.5" fill="#fff" />
          </svg>
          <!-- 默认皮肤: 蓝紫 -->
          <svg v-else viewBox="0 0 44 44" width="40" height="40">
            <defs><linearGradient id="lgA" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#6366f1" /><stop offset="100%" stop-color="#8b5cf6" /></linearGradient>
            <linearGradient id="lgB" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#0ea5e9" /><stop offset="100%" stop-color="#06b6d4" /></linearGradient></defs>
            <rect x="8" y="6" width="4" height="32" rx="2" fill="url(#lgA)" /><rect x="32" y="6" width="4" height="32" rx="2" fill="url(#lgB)" />
            <rect x="8" y="6" width="28" height="4" rx="2" fill="url(#lgA)" /><rect x="8" y="34" width="28" height="4" rx="2" fill="url(#lgB)" />
            <rect x="8" y="20" width="28" height="3" rx="1.5" fill="url(#lgA)" opacity="0.6" />
            <line x1="8" y1="6" x2="36" y2="20" stroke="url(#lgA)" stroke-width="2.5" stroke-linecap="round" />
            <line x1="8" y1="20" x2="36" y2="34" stroke="url(#lgB)" stroke-width="2.5" stroke-linecap="round" />
            <circle cx="8" cy="6" r="2.5" fill="#fff" /><circle cx="36" cy="6" r="2.5" fill="#fff" />
            <circle cx="8" cy="34" r="2.5" fill="#fff" /><circle cx="36" cy="34" r="2.5" fill="#fff" />
            <circle cx="8" cy="20" r="2" fill="#fff" /><circle cx="36" cy="20" r="2" fill="#fff" />
            <circle cx="22" cy="20" r="3" fill="url(#lgA)" /><circle cx="22" cy="20" r="1.5" fill="#fff" />
          </svg>
        </div>
        <span v-if="!appStore.sidebarCollapsed" class="brand-name" :class="'skin-' + appStore.skin">
          <span class="brand-cn">智渊</span>
          <span class="brand-en">AIOPS</span>
        </span>
      </div>

      <div v-if="!appStore.sidebarCollapsed" class="sidebar-search">
        <el-autocomplete
          v-model="searchKeyword"
          :fetch-suggestions="fetchMenuSuggestions"
          :trigger-on-focus="false"
          placeholder="搜索菜单功能…"
          class="menu-search-input"
          clearable
          @select="handleSearchSelect"
        >
          <template #prefix>
            <el-icon class="menu-search-icon"><Search /></el-icon>
          </template>
          <template #default="{ item }">
            <div class="menu-search-item">
              <div class="menu-search-label">{{ item.label }}</div>
              <div class="menu-search-crumbs">{{ item.crumbs.join(' / ') }}</div>
            </div>
          </template>
        </el-autocomplete>
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
                >
                  <el-icon><component :is="getIcon(leaf.icon || item.icon || g.icon)" /></el-icon>
                  <span>{{ leaf.label }}</span>
                </el-menu-item>
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
          <el-popover trigger="click" placement="bottom-end" :width="250">
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
                <span
                  class="theme-opt"
                  :class="{ active: appStore.theme === 'dark-glass' }"
                  @click="appStore.theme = 'dark-glass'"
                >
                  <el-icon :size="14"><Monitor /></el-icon>
                  <span>暗色玻璃</span>
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
                <span
                  class="color-dot fluorescent-green"
                  :class="{ active: appStore.colorScheme === 'fluorescent-green' }"
                  @click="appStore.setColorScheme('fluorescent-green')"
                >荧光绿</span>
              </div>
              <div class="appearance-label">皮肤</div>
              <div class="skin-row">
                <span
                  class="skin-opt"
                  :class="{ active: appStore.skin === '' }"
                  @click="appStore.setSkin('')"
                >默认</span>
                <span
                  class="skin-opt taste"
                  :class="{ active: appStore.skin === 'taste' }"
                  @click="appStore.setSkin('taste')"
                >Taste</span>
                <span
                  class="skin-opt frost"
                  :class="{ active: appStore.skin === 'frost' }"
                  @click="appStore.setSkin('frost')"
                >Frost</span>
                <span
                  class="skin-opt nebula"
                  :class="{ active: appStore.skin === 'nebula' }"
                  @click="appStore.setSkin('nebula')"
                >Nebula</span>
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

      <div v-if="marqueeAlerts.length" class="alert-marquee">
        <div class="marquee-icon" @click="goToAlerts">
          <el-icon><Bell /></el-icon>
        </div>
        <div class="marquee-track" @click="goToAlerts">
          <div class="marquee-content" :style="marqueeStyle">
            <span
              v-for="(a, i) in [...marqueeAlerts, ...marqueeAlerts]"
              :key="a.id + '-' + i"
              class="marquee-item"
              :class="a.severity"
            >
              <span class="marquee-sev">{{ a.severity === 'critical' ? '严重' : '警告' }}</span>
              <span class="marquee-msg">{{ a.message }}</span>
              <span v-if="a.asset_name" class="marquee-asset">[{{ a.asset_name }}]</span>
              <span class="marquee-time">{{ a.created_at }}</span>
            </span>
          </div>
        </div>
        <div class="marquee-speed">
          <input type="range" min="0" max="100" v-model.number="marqueeSpeedVal" class="speed-slider" @click.stop />
          <span class="speed-label">{{ speedLabel }}</span>
        </div>
        <div class="marquee-count" @click="goToAlerts">
          {{ marqueeAlerts.length }} 条
        </div>
      </div>

      <main class="content">
        <div class="content-inner">
          <MonitorView v-if="activeView === 'monitor-view'" />
          <SystemPosture v-else-if="activeView === 'system-posture'" />
      <AgentAudit v-else-if="activeView === 'audit'" />
      <OperationAudit v-else-if="activeView === 'op-audit'" />
      <AIOpsAssistantView v-else-if="activeView === 'ai-ops-assistant'" />
      <MenuConfig v-else-if="activeView === 'menu-config'" />
      <TraceView v-else-if="activeView === 'traces'" />
    <TraceAgentGuide v-else-if="activeView === 'discovery'" />
      <MetricsView v-else-if="activeView === 'metrics'" />
          <ErrorBudgetView v-else-if="activeView === 'error-budget'" />
          <BurnRateView v-else-if="activeView === 'burn-rate'" />
          <SloDashboardView v-else-if="activeView === 'slo-dashboard'" />
          <SLOConfigView v-else-if="activeView === 'slo-config'" />
          <SLOView v-else-if="activeView === 'slo'" />
          <SLAView v-else-if="activeView === 'sla-agreement'" />
          <OnCallView v-else-if="activeView === 'oncall-schedule'" />
          <AvailabilityReportView v-else-if="activeView === 'availability-report'" />
          <ChaosExperimentView v-else-if="activeView === 'chaos-experiment'" />
          <ChaosReportView v-else-if="activeView === 'chaos-report'" />
          <ChaosScenarioView v-else-if="activeView === 'chaos-scenario'" />
          <AlertsView v-else-if="activeView === 'alerts'" />
          <AlertRulesView v-else-if="activeView === 'alert-rules'" />
          <AssetsView v-else-if="activeView === 'asset-list'" />
          <ConfigDriftView v-else-if="activeView === 'config-drift'" />
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

          <AiProvidersView v-else-if="activeView === 'ai-providers'" />
          <AgentCapabilitiesView v-else-if="activeView === 'agent-capabilities'" />
          <SubAgentsView v-else-if="activeView === 'sub-agents'" />
          <ImChatopsView v-else-if="activeView === 'im-chatops'" />
          <EdgeTunnelView v-else-if="activeView === 'edge-tunnel'" />
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
          <K8sResourceView v-else-if="activeView === 'k8s-resource'" />
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
          <K8sHpaRecommendView v-else-if="activeView === 'k8s-hpa-recommend'" />
          <K8sResourceOptimizeView v-else-if="activeView === 'k8s-resource-optimize'" />
          <K8sCertView v-else-if="activeView === 'k8s-cert-inspect'" />
          <NetworkTestView v-else-if="activeView === 'network-test'" />
          <BackgroundTasksView v-else-if="activeView === 'background-tasks'" />
          <ContractCheckView v-else-if="activeView === 'contract-check'" />
          <RagEvalView v-else-if="activeView === 'rag-eval'" />
          <AuditMatrixView v-else-if="activeView === 'audit-matrix'" />
          <SecurityAuditView v-else-if="activeView === 'security-audit'" />
          <SecretsVaultView v-else-if="activeView === 'secret-vault'" />
          <SkillCenterView v-else-if="activeView === 'skills' || activeView === 'skill-market'" />
          <MultiClusterView v-else-if="activeView === 'multicluster'" />
          <UpgradeJobsView v-else-if="activeView === 'upgrade-jobs'" />
          <NetworkDevicesView v-else-if="activeView === 'network-devices'" />
          <AgentManageView v-else-if="activeView === 'agent-deploy'" />
          <AgentAutonomousView v-else-if="activeView === 'agent-autonomous'" />
          <DeployView v-else-if="activeView === 'ai-deploy'" />
          <SandboxView v-else-if="activeView === 'sandbox-overview'" />
          <OfflineRepoView v-else-if="activeView === 'offline-repo'" />
          <K8sOfflineDeployView v-else-if="activeView === 'k8s-cluster-deploy'" />
          <ComponentStoreHostView v-else-if="activeView === 'middleware-store'" />
          <iframe v-else-if="activePath" :src="activePath" class="content-iframe" frameborder="0" />
        </div>
      </main>
    </div>

    <AIOpsChatWidget ref="chatWidgetRef" />
    <FirstRunGuide :visible="showFirstRun" @close="showFirstRun = false" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { useAppStore } from '@/stores/app'
import { ElMessage } from 'element-plus'
import {
  ChatDotRound, Fold, Expand, Bell, Brush, ChatLineRound,
  Odometer, ChatDotSquare, DataLine, Tickets, Operation, Monitor,
  Box, Setting, TrendCharts, Coin, Connection, WarningFilled, Search,
  Lightning, User, Tools, Link, MoonNight, Sunny, DataBoard, Loading,
  Cpu, DataAnalysis, Cloudy, Warning, AlarmClock, Histogram, Folder,
  Calendar, Notebook, Star, Trophy, ScaleToOriginal,
  FirstAidKit, Finished, CircleCheck, DocumentChecked, Guide, Compass,
  Document, Timer, Key, MagicStick, Wallet, Stamp, Memo, Flag,
  Briefcase, Promotion, PriceTag,
  Van, Grid, ArrowRight, ArrowLeft, ArrowUp, ArrowDown, Check, CirclePlus,
  Remove, Close, Plus, Minus, Delete, Edit, View, Hide, Download,
  Upload, Printer, CopyDocument, Refresh, Tools as ToolsIcon,
  Management, Service, Goods, GoodsFilled, DocumentAdd, DocumentCopy,
  DocumentDelete, FolderAdd, FolderChecked, FolderOpened, FolderRemove,
  Collection, CollectionTag, Postcard, Ticket, Briefcase as BriefcaseIcon,
  Suitcase, SuitcaseLine, Operation as OpIcon, Lock
} from '@element-plus/icons-vue'
import AIOpsChatWidget from '@/components/AIOpsChatWidget.vue'
import FirstRunGuide from '@/components/FirstRunGuide.vue'
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
const SLOView = defineAsyncComponent(() => import('@/views/SLOView.vue'))
const SLAView = defineAsyncComponent(() => import('@/views/SLAView.vue'))
const AvailabilityReportView = defineAsyncComponent(() => import('@/views/AvailabilityReportView.vue'))
const ChaosExperimentView = defineAsyncComponent(() => import('@/views/ChaosExperimentView.vue'))
const ChaosReportView = defineAsyncComponent(() => import('@/views/ChaosReportView.vue'))
const ChaosScenarioView = defineAsyncComponent(() => import('@/views/ChaosScenarioView.vue'))
const AlertsView = defineAsyncComponent(() => import('@/views/AlertsView.vue'))
const AlertRulesView = defineAsyncComponent(() => import('@/views/AlertRulesView.vue'))
const AssetsView = defineAsyncComponent(() => import('@/views/AssetsView.vue'))
const ConfigDriftView = defineAsyncComponent(() => import('@/views/ConfigDriftView.vue'))
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
const K8sResourceView = defineAsyncComponent(() => import('@/views/K8sResourceView.vue'))
const ContainerTopologyView = defineAsyncComponent(() => import('@/views/ContainerTopologyView.vue'))
const K8sPodsView = defineAsyncComponent(() => import('@/views/K8sPodsView.vue'))
const K8sDeploymentsView = defineAsyncComponent(() => import('@/views/K8sDeploymentsView.vue'))
const DockerOverviewView = defineAsyncComponent(() => import('@/views/DockerOverviewView.vue'))
const DockerListView = defineAsyncComponent(() => import('@/views/DockerListView.vue'))
const KnowledgeView = defineAsyncComponent(() => import('@/views/KnowledgeView.vue'))
const KnowledgeDocumentsView = defineAsyncComponent(() => import('@/views/KnowledgeDocumentsView.vue'))
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
const RAGRerankView = defineAsyncComponent(() => import('@/views/RAGRerankView.vue'))
const AnomalyBenchmarkView = defineAsyncComponent(() => import('@/views/AnomalyBenchmarkView.vue'))
const AssetDiscoveryView = defineAsyncComponent(() => import('@/views/AssetDiscoveryView.vue'))
const OpsAnalyticsView = defineAsyncComponent(() => import('@/views/OpsAnalyticsView.vue'))
const DashboardDesignerView = defineAsyncComponent(() => import('@/views/DashboardDesignerView.vue'))
const DiagnosticToolsView = defineAsyncComponent(() => import('@/views/DiagnosticToolsView.vue'))
const TenantManagementView = defineAsyncComponent(() => import('@/views/TenantManagementView.vue'))
const AgentCapabilitiesView = defineAsyncComponent(() => import('@/views/AgentCapabilitiesView.vue'))
const SubAgentsView = defineAsyncComponent(() => import('@/views/SubAgentsView.vue'))
const ImChatopsView = defineAsyncComponent(() => import('@/views/ImChatopsView.vue'))
const EdgeTunnelView = defineAsyncComponent(() => import('@/views/EdgeTunnelView.vue'))
const RolesView = defineAsyncComponent(() => import('@/views/RolesView.vue'))
const ObservabilityCorrelationView = defineAsyncComponent(() => import('@/views/ObservabilityCorrelationView.vue'))
const TraceAnomalyConfigView = defineAsyncComponent(() => import('@/views/TraceAnomalyConfigView.vue'))
const K8sHpaRecommendView = defineAsyncComponent(() => import('@/views/K8sHpaRecommendView.vue'))
const K8sResourceOptimizeView = defineAsyncComponent(() => import('@/views/K8sResourceOptimizeView.vue'))
const K8sCertView = defineAsyncComponent(() => import('@/views/K8sCertView.vue'))
const NetworkTestView = defineAsyncComponent(() => import('@/views/NetworkTestView.vue'))
const BackgroundTasksView = defineAsyncComponent(() => import('@/views/BackgroundTasksView.vue'))
const ContractCheckView = defineAsyncComponent(() => import('@/views/ContractCheckView.vue'))
const RagEvalView = defineAsyncComponent(() => import('@/views/RagEvalView.vue'))
const AuditMatrixView = defineAsyncComponent(() => import('@/views/AuditMatrixView.vue'))
const SecurityAuditView = defineAsyncComponent(() => import('@/views/SecurityAuditView.vue'))
const SecretsVaultView = defineAsyncComponent(() => import('@/views/SecretsVaultView.vue'))
const SkillCenterView = defineAsyncComponent(() => import('@/views/SkillCenterView.vue'))
const MultiClusterView = defineAsyncComponent(() => import('@/views/MultiClusterView.vue'))
const UpgradeJobsView = defineAsyncComponent(() => import('@/views/UpgradeJobsView.vue'))
const NetworkDevicesView = defineAsyncComponent(() => import('@/views/NetworkDevicesView.vue'))
const AIOpsAssistantView = defineAsyncComponent(() => import('@/views/AIOpsAssistantView.vue'))
const SandboxView = defineAsyncComponent(() => import('@/views/SandboxView.vue'))
const AgentManageView = defineAsyncComponent(() => import('@/views/AgentManageView.vue'))
const AgentAutonomousView = defineAsyncComponent(() => import('@/views/AgentAutonomousView.vue'))
const DeployView = defineAsyncComponent(() => import('@/views/DeployView.vue'))
const OfflineRepoView = defineAsyncComponent(() => import('@/views/OfflineRepoView.vue'))
const K8sOfflineDeployView = defineAsyncComponent(() => import('@/views/K8sOfflineDeployView.vue'))
const ComponentStoreHostView = defineAsyncComponent(() => import('@/views/ComponentStoreHostView.vue'))
const MonitorView = defineAsyncComponent(() => import('@/views/MonitorView.vue'))
import request from '@/api/request'

const appStore = useAppStore()
const chatWidgetRef = ref(null)

// 切换数据库重载时，同步读取上次菜单位置，避免首帧闪烁仪表盘
const _savedMenu = localStorage.getItem('aiops-active-menu')
const menuLoading = ref(!!_savedMenu)  // 有待恢复的菜单时，显示 loading 遮罩
// 兼容旧默认页 dashboard（已合并入 monitor-view）
const _MENU_REDIRECT = {
  'agent-chat': 'ai-ops-assistant',
  'pending-actions': 'ai-ops-assistant',
}
const _initialMenu = _MENU_REDIRECT[_savedMenu] || (_savedMenu === 'dashboard' ? 'monitor-view' : (_savedMenu || 'monitor-view'))
const activeView = ref('monitor-view')
const activePath = ref(null)
const currentTitle = ref(_savedMenu ? '' : '实时监控看板')
const activeMenu = ref(_initialMenu)
const showFirstRun = ref(false)
const noticeCount = ref(0)
const notifications = ref([])
const userInfo = ref(null)
let notifTimer = null
const marqueeAlerts = ref([])
let marqueeTimer = null
const marqueeSpeedVal = ref(5)

const marqueeStyle = computed(() => {
  if (marqueeSpeedVal.value <= 0) return { animationPlayState: 'paused' }
  const dur = Math.max(24, 2400 / marqueeSpeedVal.value)
  return { animationDuration: dur + 's' }
})

const speedLabel = computed(() => {
  const v = marqueeSpeedVal.value
  if (v <= 0) return '静止'
  if (v <= 3) return '极慢'
  if (v <= 8) return '慢'
  if (v <= 20) return '中'
  if (v <= 50) return '快'
  return '极快'
})

async function loadMarqueeAlerts() {
  try {
    const data = await request.get('/alerts/api/marquee')
    marqueeAlerts.value = Array.isArray(data) ? data : []
  } catch (e) {
    if (marqueeAlerts.value.length) marqueeAlerts.value = []
  }
}

function goToAlerts() {
  window._navigateTo && window._navigateTo('alerts')
}

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

// 菜单搜索：把树形菜单平铺成叶子节点列表（含父级面包屑路径）
const searchKeyword = ref('')
const flatMenuItems = computed(() => {
  const result = []
  function walk(items, parents) {
    for (const it of (items || [])) {
      const path = [...parents, it.label]
      if (it.type) {
        result.push({ key: it.key, label: it.label, value: it.label, crumbs: parents, type: it.type })
      }
      if (it.items && it.items.length) walk(it.items, path)
    }
  }
  walk(menuGroups.value, [])
  return result
})
function fetchMenuSuggestions(qs, cb) {
  const kw = (qs || '').trim().toLowerCase()
  if (!kw) { cb([]); return }
  cb(flatMenuItems.value.filter(it =>
    it.label.toLowerCase().includes(kw) || it.crumbs.some(c => c.toLowerCase().includes(kw))
  ))
}
function handleSearchSelect(item) {
  if (item && item.key) {
    handleMenuSelect(item.key)
    searchKeyword.value = ''
  }
}

const ICON_MAP = {
  Odometer, ChatDotSquare, DataLine, Tickets, Operation, Monitor,
  Box, Setting, TrendCharts, Coin, Connection, WarningFilled, Search,
  Lightning, User, ToolsIcon, Link, Cpu, DataAnalysis, Cloudy, Warning,
  AlarmClock, Histogram, Folder, Calendar, Notebook, Star, Trophy,
  ScaleToOriginal, FirstAidKit, Finished, CircleCheck, DocumentChecked,
  Guide, Compass, Document, Timer, Key, MagicStick, Wallet, Stamp, Memo,
  Flag, Briefcase, Promotion, PriceTag, Van, Grid, ArrowRight, ArrowLeft,
  ArrowUp, ArrowDown, Check, CirclePlus, Remove, Close, Plus, Minus,
  Delete, Edit, View, Hide, Download, Upload, Printer, CopyDocument,
  Refresh, ChatDotRound, Bell, Brush, Fold, Expand, MoonNight, Sunny,
  DataBoard, Loading, OpIcon, Management, Service, Goods, GoodsFilled,
  DocumentAdd, DocumentCopy, DocumentDelete, FolderAdd, FolderChecked,
  FolderOpened, FolderRemove, Collection, CollectionTag, Postcard, Ticket,
  BriefcaseIcon, Suitcase, SuitcaseLine, Lock
}

function getIcon(name) {
  return ICON_MAP[name] || Monitor
}

const VUE_PAGES = new Set(['roles-manage', 'ai-ops-assistant', 'agent-deploy', 'agent-autonomous', 'ai-deploy', 'audit', 'op-audit', 'menu-config', 'system-posture', 'traces', 'discovery', 'metrics', 'error-budget', 'burn-rate', 'slo-config', 'slo-dashboard', 'sla-agreement', 'oncall-schedule', 'availability-report', 'chaos-experiment', 'chaos-report', 'chaos-scenario', 'alerts', 'asset-list', 'datasources', 'logs', 'incident', 'event-stats', 'event-sources', 'anomaly', 'remediation', 'remediation-workflow', 'script-exec', 'blue-green', 'change-workflow', 'ai-providers', 'feature-store', 'prediction-models', 'users', 'notifications', 'settings', 'integration', 'tags', 'ext-cmdb', 'reports', 'k8s-overview', 'k8s-monitor', 'k8s-statefulsets', 'k8s-daemonsets', 'k8s-services', 'k8s-ingresses', 'k8s-configmaps', 'k8s-secrets', 'k8s-hpas', 'k8s-pvcs', 'k8s-pvs', 'k8s-topology', 'k8s-pods', 'k8s-deployments', 'docker-overview', 'docker-list', 'kb-list', 'kb-documents', 'graph-inference', 'smart-recommend', 'rag-eval', 'runbooks', 'lifecycle', 'topology', 'topology-path', 'openapi', 'workflow-runs', 'workflow-templates', 'agent-workflow-editor', 'agent-workflow-runs', 'helm-releases', 'ansible', 'license', 'k8s-namespaces', 'firemap', 'smart-inspection', 'knowledge-draft', 'remediation-effect', 'agent-eval', 'rag-rerank', 'anomaly-benchmark', 'asset-discovery', 'ops-analytics', 'dashboard-designer', 'diagnostic-tools', 'tenant-management', 'observability-correlation', 'trace-anomaly-config', 'k8s-hpa-recommend', 'k8s-resource-optimize', 'k8s-cert-inspect', 'network-test', 'background-tasks', 'contract-check', 'audit-matrix', 'security-audit', 'middleware-store'])

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

  // 告警走马灯 + 15s 轮询
  loadMarqueeAlerts()
  marqueeTimer = setInterval(loadMarqueeAlerts, 15000)

  // 加载用户信息（含租户）
  await loadUserInfo()

  try {
    const data = await request.get('/api/menu')
    menuGroups.value = Array.isArray(data) ? data : (data.menu || [])
    // 恢复上次菜单位置（刷新或切换数据库后均生效）
    if (_savedMenu) {
      // 旧默认页 dashboard 已合并入 monitor-view，迁移历史存储
      const restoreKey = _savedMenu === 'dashboard' ? 'monitor-view' : _savedMenu
      const item = _findItem(restoreKey)
      if (item) {
        handleMenuSelect(restoreKey)
        if (_savedMenu === 'dashboard') {
          localStorage.setItem('aiops-active-menu', 'monitor-view')
        }
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
  // 首次体验引导: 按「用户名+版本」记录, 每个用户首次登录弹出一次
  const _uname = (userInfo.value && userInfo.value.username) || 'guest'
  const GUIDE_KEY = `aiops_first_run_guide_v1_${_uname}`
  if (!localStorage.getItem(GUIDE_KEY)) {
    showFirstRun.value = true
    localStorage.setItem(GUIDE_KEY, '1')
  }
})

onBeforeUnmount(() => {
  if (notifTimer) {
    clearInterval(notifTimer)
    notifTimer = null
  }
  if (marqueeTimer) {
    clearInterval(marqueeTimer)
    marqueeTimer = null
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
/* 菜单搜索框 */
.sidebar-search {
  flex-shrink: 0;
  padding: 0 12px 10px;
}
.menu-search-input {
  width: 100%;
}
.menu-search-icon {
  color: var(--sidebar-text, #94a3b8);
}
.sidebar-search :deep(.menu-search-input .el-input__wrapper) {
  border-radius: 10px;
  background: var(--sidebar-hover, rgba(0, 0, 0, 0.04));
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.06);
  transition: box-shadow 0.2s;
}
.sidebar-search :deep(.menu-search-input .el-input__wrapper:hover) {
  box-shadow: inset 0 0 0 1px rgba(99, 102, 241, 0.4);
}
.sidebar-search :deep(.menu-search-input .el-input__wrapper.is-focus) {
  box-shadow: inset 0 0 0 1.5px var(--primary, #6366f1);
}
.sidebar-search :deep(.menu-search-input .el-input__inner) {
  font-size: 13px;
  height: 34px;
  color: var(--text-primary, #1f2937);
}
.sidebar-search :deep(.menu-search-input .el-input__inner::placeholder) {
  color: var(--sidebar-text, #94a3b8);
}

/* 告警走马灯 */
.alert-marquee {
  display: flex; align-items: center; gap: 8px;
  padding: 0 16px; height: 32px;
  background: rgba(239, 68, 68, 0.06);
  border-bottom: 1px solid rgba(239, 68, 68, 0.08);
  cursor: pointer;
  overflow: hidden;
  flex-shrink: 0;
}
.alert-marquee:hover { background: rgba(239, 68, 68, 0.08); }
.marquee-icon {
  flex-shrink: 0; font-size: 14px; color: #ef4444;
  display: flex; align-items: center;
}
.marquee-track {
  flex: 1; overflow: hidden; position: relative;
  height: 32px; display: flex; align-items: center;
}
.marquee-content {
  display: flex; gap: 24px; white-space: nowrap;
  animation: marqueeScroll 30s linear infinite;
}
.marquee-item {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--text-primary);
  flex-shrink: 0;
}
.marquee-item.critical { color: #ef4444; }
.marquee-item.warning { color: #f59e0b; }
.marquee-sev {
  display: inline-block; padding: 0 5px; font-size: 10px; font-weight: 700;
  border-radius: 3px; text-transform: uppercase;
  background: rgba(239, 68, 68, 0.12); color: #ef4444;
}
.marquee-item.warning .marquee-sev { background: rgba(245, 158, 11, 0.12); color: #f59e0b; }
.marquee-msg { font-weight: 500; }
.marquee-asset { opacity: 0.7; }
.marquee-time { font-size: 11px; opacity: 0.5; }
.marquee-count {
  flex-shrink: 0; font-size: 11px; color: var(--text-muted); padding-left: 8px;
  border-left: 1px solid rgba(239, 68, 68, 0.12);
  cursor: pointer;
}
.marquee-count:hover { color: var(--text-primary); }
.marquee-speed {
  flex-shrink: 0; display: flex; align-items: center; gap: 6px;
  padding: 0 8px 0 4px; cursor: pointer; user-select: none;
  border-left: 1px solid rgba(239, 68, 68, 0.12);
  height: 20px;
}
.speed-slider {
  width: 60px; height: 3px; -webkit-appearance: none; appearance: none;
  background: rgba(239,68,68,0.15); border-radius: 2px; outline: none;
  cursor: pointer; margin: 0;
}
.speed-slider::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none;
  width: 12px; height: 12px; border-radius: 50%;
  background: #ef4444; border: 2px solid #fff;
  box-shadow: 0 1px 3px rgba(0,0,0,0.2);
  cursor: pointer;
}
.speed-slider::-moz-range-thumb {
  width: 12px; height: 12px; border-radius: 50%;
  background: #ef4444; border: 2px solid #fff;
  box-shadow: 0 1px 3px rgba(0,0,0,0.2);
  cursor: pointer;
}
.speed-label { font-size: 11px; color: var(--text-muted); min-width: 2em; text-align: center; }
@keyframes marqueeScroll {
  0% { transform: translateX(0); }
  100% { transform: translateX(-50%); }
}
</style>

<style>
/* 菜单搜索下拉项（popper teleport 到 body，需用全局样式） */
.menu-search-item {
  padding: 6px 4px;
  line-height: 1.35;
}
.menu-search-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #1f2937);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.menu-search-crumbs {
  font-size: 11px;
  color: var(--text-secondary, rgba(0, 0, 0, 0.45));
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
html[data-theme="dark"] .menu-search-label {
  color: var(--text-primary, #e5e7eb);
}
html[data-theme="dark"] .menu-search-crumbs {
  color: rgba(255, 255, 255, 0.45);
}
</style>
