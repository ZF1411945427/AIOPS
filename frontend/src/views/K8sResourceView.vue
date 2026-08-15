<template>
  <div class="k8s-resource-view">
    <div class="rtype-tabs">
      <button
        v-for="t in types"
        :key="t.key"
        :class="['tab-btn', { active: resourceType === t.key }]"
        @click="resourceType = t.key"
      >
        {{ t.label }}
      </button>
    </div>

    <K8sResourceListView :resource-type="resourceType" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import K8sResourceListView from '@/views/K8sResourceListView.vue'

const types = [
  { key: 'namespaces', label: 'Namespace' },
  { key: 'statefulsets', label: 'StatefulSet' },
  { key: 'daemonsets', label: 'DaemonSet' },
  { key: 'services', label: 'Service' },
  { key: 'ingresses', label: 'Ingress' },
  { key: 'configmaps', label: 'ConfigMap' },
  { key: 'secrets', label: 'Secret' },
  { key: 'hpas', label: 'HPA' },
  { key: 'pvcs', label: 'PVC' },
  { key: 'pvs', label: 'PV' },
]
const resourceType = ref('namespaces')
</script>

<style scoped>
.rtype-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 14px;
  flex-wrap: wrap;
  border-bottom: 1px solid var(--border, rgba(0, 0, 0, 0.08));
  padding-bottom: 8px;
}
.tab-btn {
  padding: 7px 14px;
  border-radius: 8px;
  border: 1px solid var(--border, rgba(0, 0, 0, 0.12));
  background: var(--bg-card, #fff);
  color: var(--text-secondary, #64748b);
  font-size: 0.82rem;
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
