<template>
  <div class="task-progress-card" :class="{ 'is-urgent': isUrgent }">
    <div class="tpc-header" @click="toggleCard">
      <div class="tpc-title-wrap">
        <span class="tpc-icon">🤖</span>
        <span class="tpc-title">{{ task?.title || '运维任务进度' }}</span>
        <span v-if="isUrgent" class="tpc-urgent-tag">紧急</span>
      </div>
      <div class="tpc-meta">
        <span class="tpc-count">{{ completedSteps }} / {{ totalSteps || steps.length }}</span>
        <span class="tpc-percent">· {{ percent }}%</span>
        <div class="tpc-progress-bar">
          <div class="tpc-progress-fill" :style="{ width: percent + '%' }"></div>
        </div>
        <button class="tpc-fold-btn" @click.stop="toggleCard" :title="collapsed ? '展开' : '收起'">
          <span v-if="collapsed">∨</span>
          <span v-else>∧</span>
        </button>
      </div>
    </div>

    <div v-show="!collapsed" class="tpc-body">
      <div v-if="!steps.length" class="tpc-empty">暂无任务步骤</div>

      <div v-for="(step, idx) in steps" :key="step.step_id || idx" class="tpc-step" :class="{ 'has-output': step.raw_output }">
        <div class="tpc-step-head" @click="toggleStep(step)">
          <span class="tpc-step-mark" :class="step.status">
            <template v-if="step.status === 'success'">√</template>
            <template v-else-if="step.status === 'failed'">✗</template>
            <span v-else class="tpc-step-spin"></span>
          </span>
          <div class="tpc-step-info">
            <div class="tpc-step-title">{{ step.title }}</div>
            <div class="tpc-step-sub" v-if="step.summary">{{ truncate(step.summary, 120) }}</div>
            <div class="tpc-step-sub tpc-step-meta" v-if="step.duration_ms">
              <span>⏱ {{ step.duration_ms }}ms</span>
              <span v-if="step.tool_name"> · 🔧 {{ step.tool_name }}</span>
            </div>
          </div>
          <button v-if="step.raw_output || step.conclusion || step.anomaly" class="tpc-step-fold" @click.stop="toggleStep(step)">
            <span v-if="step.expanded">收起输出 ∧</span>
            <span v-else>查看输出 ∨</span>
          </button>
        </div>

        <div v-if="step.expanded" class="tpc-step-detail">
          <div class="tpc-section tpc-section-cmd" v-if="step.tool_name">
            <div class="tpc-section-title">① 执行命令摘要</div>
            <div class="tpc-section-body">
              <div class="tpc-cmd-line"><span class="tpc-label">工具：</span>{{ step.tool_name }}</div>
              <div class="tpc-cmd-line" v-if="step.tool_args_text"><span class="tpc-label">参数：</span><code>{{ step.tool_args_text }}</code></div>
              <div class="tpc-cmd-line" v-if="step.summary"><span class="tpc-label">摘要：</span>{{ step.summary }}</div>
            </div>
          </div>

          <div class="tpc-section tpc-section-anomaly" v-if="step.anomaly">
            <div class="tpc-section-title">② 异常识别</div>
            <div class="tpc-section-body tpc-anomaly-body">{{ step.anomaly }}</div>
          </div>

          <div class="tpc-section tpc-section-conclusion" v-if="step.conclusion">
            <div class="tpc-section-title">③ 关注建议</div>
            <div class="tpc-section-body tpc-conclusion-body">{{ step.conclusion }}</div>
          </div>

          <div class="tpc-section tpc-section-raw" v-if="step.raw_output">
            <div class="tpc-section-title">
              原始输出
              <button class="tpc-raw-fold" @click.stop="step.raw_expanded = !step.raw_expanded">
                {{ step.raw_expanded ? '收起 ∧' : '展开 ∨' }}
              </button>
            </div>
            <pre v-if="step.raw_expanded" class="tpc-raw-output">{{ step.raw_output }}</pre>
            <pre v-else class="tpc-raw-output tpc-raw-collapsed">{{ truncate(step.raw_output, 300) }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  steps: { type: Array, default: () => [] },
  task: { type: Object, default: null },
  defaultCollapsed: { type: Boolean, default: false },
})

const collapsed = ref(props.defaultCollapsed)

const isUrgent = computed(() => props.task?.urgency === 'urgent')
const totalSteps = computed(() => props.task?.totalSteps || props.steps.length)
const completedSteps = computed(() => {
  if (props.task?.completedSteps != null) return props.task.completedSteps
  return props.steps.filter(s => s.status === 'success' || s.status === 'failed').length
})
const percent = computed(() => {
  if (props.task?.percent != null) return props.task.percent
  const total = totalSteps.value
  return total ? Math.round((completedSteps.value / total) * 100) : 0
})

function toggleCard() { collapsed.value = !collapsed.value }
function toggleStep(step) { step.expanded = !step.expanded }
function truncate(text, n) {
  if (!text) return ''
  return text.length > n ? text.slice(0, n) + '…' : text
}
</script>

<style scoped>
.task-progress-card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  overflow: hidden;
  max-width: 100%;
}
.task-progress-card.is-urgent { border-color: #fca5a5; box-shadow: 0 0 0 1px #fef2f2, 0 2px 8px rgba(239,68,68,0.08); }
.tpc-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; background: linear-gradient(135deg, #f8fafc, #f1f5f9);
  cursor: pointer; border-bottom: 1px solid #e2e8f0; user-select: none;
}
.task-progress-card.is-urgent .tpc-header { background: linear-gradient(135deg, #fef2f2, #fee2e2); }
.tpc-title-wrap { display: flex; align-items: center; gap: 8px; }
.tpc-icon { font-size: 1rem; }
.tpc-title { font-weight: 600; font-size: 0.92rem; color: #1e293b; }
.tpc-urgent-tag {
  background: #dc2626; color: #fff; font-size: 0.68rem; font-weight: 600;
  padding: 1px 6px; border-radius: 4px; margin-left: 4px;
}
.tpc-meta { display: flex; align-items: center; gap: 8px; font-size: 0.8rem; color: #64748b; }
.tpc-count { font-weight: 600; color: #475569; }
.tpc-percent { color: #10b981; font-weight: 600; }
.tpc-progress-bar {
  width: 80px; height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden;
}
.tpc-progress-fill {
  height: 100%; background: linear-gradient(90deg, #6366f1, #10b981);
  transition: width 0.4s ease; border-radius: 3px;
}
.tpc-fold-btn {
  width: 22px; height: 22px; border: 1px solid #cbd5e1; border-radius: 4px;
  background: #fff; color: #64748b; cursor: pointer; font-size: 0.78rem;
  display: flex; align-items: center; justify-content: center;
}
.tpc-fold-btn:hover { background: #f1f5f9; border-color: #94a3b8; }
.tpc-body { padding: 8px 12px 12px; }
.tpc-empty { padding: 16px; text-align: center; color: #94a3b8; font-size: 0.82rem; }
.tpc-step {
  padding: 8px 10px; margin: 4px 0; border-radius: 8px;
  border: 1px solid transparent; transition: background 0.15s;
}
.tpc-step:hover { background: #f8fafc; }
.tpc-step.has-output { border-color: #e2e8f0; }
.tpc-step-head { display: flex; align-items: flex-start; gap: 8px; cursor: pointer; }
.tpc-step-mark {
  flex-shrink: 0; width: 20px; height: 20px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.78rem; font-weight: 700; margin-top: 1px;
}
.tpc-step-mark.success { background: #dcfce7; color: #16a34a; }
.tpc-step-mark.failed { background: #fee2e2; color: #dc2626; }
.tpc-step-mark.running { background: #dbeafe; color: #2563eb; }
.tpc-step-spin {
  display: inline-block; width: 10px; height: 10px;
  border: 2px solid #bfdbfe; border-top-color: #2563eb;
  border-radius: 50%; animation: tpc-spin 0.6s linear infinite;
}
@keyframes tpc-spin { to { transform: rotate(360deg); } }
.tpc-step-info { flex: 1; min-width: 0; }
.tpc-step-title { font-size: 0.86rem; font-weight: 600; color: #1e293b; }
.tpc-step-sub { font-size: 0.76rem; color: #64748b; margin-top: 2px; line-height: 1.4; word-break: break-all; }
.tpc-step-meta { color: #94a3b8; display: flex; gap: 6px; }
.tpc-step-fold {
  flex-shrink: 0; padding: 3px 8px; border: 1px solid #c7d2fe; border-radius: 6px;
  background: #eef2ff; color: #4f46e5; font-size: 0.72rem; cursor: pointer;
  font-weight: 500; white-space: nowrap; transition: all 0.15s;
}
.tpc-step-fold:hover { background: #e0e7ff; }
.tpc-step-detail {
  margin-top: 8px; padding: 8px 10px; background: #f8fafc;
  border-radius: 6px; border-left: 3px solid #6366f1;
}
.tpc-section { margin-bottom: 10px; }
.tpc-section:last-child { margin-bottom: 0; }
.tpc-section-title {
  font-size: 0.76rem; font-weight: 600; color: #475569;
  margin-bottom: 4px; display: flex; align-items: center; justify-content: space-between;
}
.tpc-section-body { font-size: 0.8rem; color: #334155; line-height: 1.5; }
.tpc-cmd-line { margin-bottom: 3px; }
.tpc-cmd-line code {
  background: #1e293b; color: #e2e8f0; padding: 1px 6px; border-radius: 3px;
  font-size: 0.74rem; word-break: break-all;
}
.tpc-label { color: #64748b; font-weight: 500; }
.tpc-anomaly-body { color: #b91c1c; background: #fef2f2; padding: 6px 8px; border-radius: 4px; }
.tpc-conclusion-body { color: #1d4ed8; background: #eff6ff; padding: 6px 8px; border-radius: 4px; }
.tpc-section-raw { border-top: 1px dashed #cbd5e1; padding-top: 8px; }
.tpc-raw-fold {
  padding: 1px 6px; border: 1px solid #cbd5e1; border-radius: 4px;
  background: #fff; color: #64748b; font-size: 0.68rem; cursor: pointer;
}
.tpc-raw-output {
  margin-top: 6px; padding: 8px; background: #0f172a; color: #94a3b8;
  border-radius: 4px; font-size: 0.72rem; line-height: 1.45;
  max-height: 300px; overflow: auto; white-space: pre-wrap; word-break: break-all;
  font-family: 'Consolas', 'Monaco', monospace;
}
.tpc-raw-collapsed { max-height: 80px; overflow: hidden; }
</style>
