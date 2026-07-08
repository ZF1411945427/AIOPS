<template>
  <transition name="slide">
    <div v-if="modelValue" class="guide-overlay" @click.self="$emit('update:modelValue', false)">
      <div class="guide-drawer">
        <div class="guide-header">
          <span class="guide-title">{{ title }}</span>
          <button class="guide-close" @click="$emit('update:modelValue', false)">✕</button>
        </div>
        <div class="guide-body">
          <slot />
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '📖 使用说明' }
})
defineEmits(['update:modelValue'])
</script>

<style scoped>
.guide-overlay {
  position: fixed; inset: 0; z-index: 500;
  background: rgba(0,0,0,0.3);
  display: flex; justify-content: flex-end;
}
.guide-drawer {
  width: 520px; max-width: 90vw; height: 100%;
  background: var(--card-bg, #fff);
  box-shadow: -4px 0 24px rgba(0,0,0,0.12);
  display: flex; flex-direction: column;
  animation: guide-slide-in 0.2s ease-out;
}
@keyframes guide-slide-in {
  from { transform: translateX(100%); }
  to { transform: translateX(0); }
}
.guide-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 20px; border-bottom: 1px solid rgba(0,0,0,0.07);
}
.guide-title { font-size: 1rem; font-weight: 700; color: var(--text-primary, #1e293b); }
.guide-close {
  width: 28px; height: 28px; border: none; background: transparent;
  cursor: pointer; font-size: 1.1rem; color: #94a3b8;
  border-radius: 6px; display: flex; align-items: center; justify-content: center;
}
.guide-close:hover { background: rgba(0,0,0,0.05); color: var(--text-primary, #1e293b); }
.guide-body {
  flex: 1; overflow-y: auto; padding: 16px 20px 60px;
}
/* 基础样式 — 由 slot 内内容使用 */
.guide-body :deep(.guide-section) { margin-bottom: 28px; }
.guide-body :deep(.guide-section h4) {
  font-size: 0.9rem; font-weight: 700; color: var(--text-primary, #1e293b);
  margin: 0 0 10px; padding-bottom: 6px;
  border-bottom: 1px solid rgba(0,0,0,0.07);
}
.guide-body :deep(.guide-section h5) {
  font-size: 0.84rem; font-weight: 600; color: var(--text-primary, #1e293b);
  margin: 14px 0 6px;
}
.guide-body :deep(.guide-section p) { font-size: 0.8rem; line-height: 1.7; color: #475569; margin: 0 0 8px; }
.guide-body :deep(.guide-section ul) { margin: 4px 0 10px; padding-left: 18px; }
.guide-body :deep(.guide-section li) { font-size: 0.8rem; line-height: 1.7; color: #475569; margin-bottom: 3px; }
.guide-body :deep(.guide-section code) {
  background: rgba(99,102,241,0.08); padding: 1px 5px; border-radius: 3px;
  font-size: 0.78rem; color: #6366f1; font-family: Consolas, monospace;
}
.guide-body :deep(.guide-section strong) { color: var(--text-primary, #1e293b); }
.guide-body :deep(.guide-section .tag-demo) {
  display: inline-block; padding: 1px 6px; border-radius: 4px;
  font-size: 0.72rem; font-weight: 600;
}
.guide-body :deep(.guide-code) {
  background: #1e293b; color: #e2e8f0; border-radius: 6px;
  padding: 10px 14px; font-size: 0.74rem; font-family: Consolas, monospace;
  white-space: pre-wrap; margin: 4px 0 12px; line-height: 1.6;
  overflow-x: auto;
}
.guide-body :deep(.key-value-list) { display: flex; flex-direction: column; gap: 6px; }
.guide-body :deep(.kv-row) {
  display: flex; gap: 10px;
  padding: 8px 10px; border-radius: 6px;
  background: rgba(0,0,0,0.02); border: 1px solid rgba(0,0,0,0.06);
  align-items: flex-start;
}
.guide-body :deep(.kv-key) {
  font-size: 0.82rem; font-weight: 600; color: var(--text-primary, #1e293b);
  min-width: 80px; flex-shrink: 0;
}
.guide-body :deep(.kv-val) { font-size: 0.76rem; color: #64748b; line-height: 1.5; }
.guide-body :deep(.formula) {
  background: rgba(99,102,241,0.06); padding: 8px 14px; border-radius: 6px;
  font-size: 0.82rem; color: #4f46e5; font-weight: 600;
  text-align: center; margin: 6px 0 10px; font-family: Consolas, monospace;
}
.guide-body :deep(.tip-box) {
  background: rgba(99,102,241,0.06); border-left: 3px solid #6366f1;
  padding: 10px 14px; border-radius: 0 6px 6px 0; margin: 8px 0;
  font-size: 0.78rem; color: #475569; line-height: 1.6;
}
</style>
