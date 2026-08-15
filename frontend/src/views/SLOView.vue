<template>
  <div class="slo-view">
    <div class="slo-tabs">
      <button
        v-for="t in tabs"
        :key="t.key"
        :class="['tab-btn', { active: tab === t.key }]"
        @click="switchTab(t.key)"
      >
        {{ t.label }}
      </button>
    </div>

    <div v-show="tab === 'dashboard'" class="tab-pane">
      <SloDashboardView />
    </div>
    <div v-show="tab === 'config'" class="tab-pane">
      <SLOConfigView />
    </div>
    <div v-show="tab === 'budget'" class="tab-pane">
      <ErrorBudgetView />
    </div>
    <div v-show="tab === 'burnrate'" class="tab-pane">
      <BurnRateView />
    </div>
    <div v-show="tab === 'report'" class="tab-pane">
      <AvailabilityReportView />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import SloDashboardView from '@/views/SloDashboardView.vue'
import SLOConfigView from '@/views/SLOConfigView.vue'
import ErrorBudgetView from '@/views/ErrorBudgetView.vue'
import BurnRateView from '@/views/BurnRateView.vue'
import AvailabilityReportView from '@/views/AvailabilityReportView.vue'

const tabs = [
  { key: 'config', label: 'SLO 配置' },
  { key: 'dashboard', label: 'SLO 仪表盘' },
  { key: 'budget', label: '错误预算' },
  { key: 'burnrate', label: '预算消耗' },
  { key: 'report', label: '可用性报表' },
]
const tab = ref('config')

function switchTab(k) {
  tab.value = k
}
</script>

<style scoped>
.slo-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 14px;
  flex-wrap: wrap;
  border-bottom: 1px solid var(--border, rgba(0, 0, 0, 0.08));
  padding-bottom: 8px;
}
.tab-btn {
  padding: 7px 16px;
  border-radius: 8px;
  border: 1px solid var(--border, rgba(0, 0, 0, 0.12));
  background: var(--bg-card, #fff);
  color: var(--text-secondary, #64748b);
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.15s;
}
.tab-btn:hover {
  border-color: var(--primary, #4f46e5);
  color: var(--primary, #4f46e5);
}
.tab-btn.active {
  background: var(--primary, #4f46e5);
  border-color: var(--primary, #4f46e5);
  color: #fff;
}
</style>
