<template>
  <div class="awf-node-card" :class="nodeType">
    <Handle type="target" :position="Position.Left" />
    <div class="node-header" :style="{borderLeftColor: meta.color}">
      <span class="node-icon" :style="{background: meta.color}">{{ meta.icon }}</span>
      <span class="node-label">{{ data.label || id }}</span>
    </div>
    <div class="node-type-tag">{{ meta.label }}</div>
    <button class="edit-btn" @click.stop="$emit('edit')">编辑</button>
    <Handle type="source" :position="Position.Right" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'

const props = defineProps({
  id: String,
  type: String,
  data: Object,
  nodeTypeMap: Object,
})

defineEmits(['edit'])

const meta = computed(() => props.nodeTypeMap?.[props.type] || { label: props.type, icon: '?', color: '#94a3b8' })
const nodeType = computed(() => props.type)
</script>

<style scoped>
.awf-node-card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px 12px;
  min-width: 140px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  position: relative;
  cursor: pointer;
  transition: box-shadow 0.15s;
}
.awf-node-card:hover { box-shadow: 0 3px 8px rgba(0,0,0,0.15); }
.awf-node-card.llm { border-left: 3px solid #6366f1; }
.awf-node-card.start { border-left: 3px solid #10b981; }
.awf-node-card.end { border-left: 3px solid #64748b; }
.awf-node-card.knowledge { border-left: 3px solid #14b8a6; }
.awf-node-card.tool { border-left: 3px solid #f59e0b; }
.awf-node-card.condition { border-left: 3px solid #ec4899; }
.awf-node-card.code { border-left: 3px solid #8b5cf6; }
.awf-node-card.http { border-left: 3px solid #06b6d4; }
.node-header { display: flex; align-items: center; gap: 6px; }
.node-icon { display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; border-radius: 4px; color: #fff; font-size: 0.62rem; font-weight: 600; }
.node-label { font-size: 0.82rem; font-weight: 500; color: #1e293b; }
.node-type-tag { font-size: 0.68rem; color: #64748b; margin-top: 2px; }
.edit-btn { position: absolute; top: 4px; right: 4px; font-size: 0.65rem; padding: 1px 5px; border: 1px solid #e2e8f0; border-radius: 3px; background: #f8fafc; cursor: pointer; color: #64748b; }
.edit-btn:hover { background: #e2e8f0; }
</style>
