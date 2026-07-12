import { createRouter, createWebHistory } from 'vue-router'
import { defineAsyncComponent } from 'vue'

const AppLayout = defineAsyncComponent(() => import('@/layout/AppLayout.vue'))

const routes = [
    { path: '/error-budget', name: 'ErrorBudget', component: () => import('../views/ErrorBudgetView.vue') },
    { path: '/oncall-schedule', name: 'OnCall', component: () => import('../views/OnCallView.vue') },
    { path: '/chaos-experiment', name: 'ChaosExperiment', component: () => import('../views/ChaosExperimentView.vue') },
    { path: '/chaos-report', name: 'ChaosReport', component: () => import('../views/ChaosReportView.vue') },
    { path: '/chaos-scenario', name: 'ChaosScenario', component: () => import('../views/ChaosScenarioView.vue') },
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
    meta: { title: '登录' },
  },
  {
    path: '/',
    component: AppLayout,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
