import { createRouter, createWebHistory } from 'vue-router'
import AppLayout from '@/layout/AppLayout.vue'
import LoginView from '@/views/LoginView.vue'

const routes = [
    { path: '/error-budget', name: 'ErrorBudget', component: () => import('../views/ErrorBudgetView.vue') },
    { path: '/oncall-schedule', name: 'OnCall', component: () => import('../views/OnCallView.vue') },
  {
    path: '/login',
    name: 'login',
    component: LoginView,
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
