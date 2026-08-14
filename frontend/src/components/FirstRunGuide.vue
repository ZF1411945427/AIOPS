<template>
  <Teleport to="body">
    <Transition name="guide-fade">
      <div v-if="visible" class="guide-overlay" @click.self="maybeClose">
        <div class="guide-card">
          <div class="guide-card-header">
            <div class="guide-brand">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" fill="#6366f1"/>
                <path d="M8 12l3 3 5-5" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              <span>新手引导</span>
            </div>
            <button class="guide-skip-btn" @click="emit('close')">跳过</button>
          </div>

          <div class="guide-steps-bar">
            <div
              v-for="(s, i) in STEPS"
              :key="i"
              class="guide-step-dot"
              :class="{ active: i === current, done: i < current }"
              @click="i < current && (current = i)"
            >
              <span v-if="i < current" class="dot-check">✓</span>
              <span v-else>{{ i + 1 }}</span>
            </div>
          </div>

          <div class="guide-card-body">
            <Transition name="guide-slide" mode="out-in">
              <div :key="current" class="guide-step-content">
                <div class="guide-icon-wrap" :style="{ background: STEPS[current].iconBg }">
                  <span class="guide-icon" v-html="STEPS[current].icon"></span>
                </div>
                <h2 class="guide-step-title">{{ STEPS[current].title }}</h2>
                <p class="guide-step-desc">{{ STEPS[current].desc }}</p>
                <button
                  v-if="STEPS[current].action"
                  class="guide-action-btn"
                  @click="doAction(current)"
                >
                  {{ STEPS[current].action }}
                </button>
              </div>
            </Transition>
          </div>

          <div class="guide-card-footer">
            <button v-if="current > 0" class="guide-btn guide-btn-ghost" @click="current--">
              ← 上一步
            </button>
            <div class="guide-footer-right">
              <span class="guide-progress">{{ current + 1 }} / {{ STEPS.length }}</span>
              <button
                v-if="current < STEPS.length - 1"
                class="guide-btn guide-btn-primary"
                @click="current++"
              >
                下一步 →
              </button>
              <button
                v-else
                class="guide-btn guide-btn-done"
                @click="emit('close')"
              >
                完成，开始使用 →
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({ visible: { type: Boolean, default: false } })
const emit = defineEmits(['close'])

const current = ref(0)

const STEPS = [
  {
    title: '欢迎使用 AIOps',
    desc: '您的智能运维平台，支持资产管理、告警分析、AI 助手等多种能力。带您用 3 步完成基础配置。',
    icon: `<svg width="32" height="32" viewBox="0 0 24 24" fill="none"><path d="M12 2L2 7l10 5 10-5-10-5z" fill="#6366f1" opacity=".2"/><path d="M2 17l10 5 10-5M2 12l10 5 10-5" stroke="#6366f1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    iconBg: 'rgba(99,102,241,0.1)',
    action: null,
  },
  {
    title: '添加第一台服务器',
    desc: '在「资产管理」中添加您的服务器资产，系统会自动采集指标、检测异常。支持 SSH 批量导入。',
    icon: `<svg width="32" height="32" viewBox="0 0 24 24" fill="none"><rect x="2" y="3" width="20" height="6" rx="1" stroke="#10b981" stroke-width="1.8"/><rect x="2" y="11" width="20" height="6" rx="1" stroke="#10b981" stroke-width="1.8"/><circle cx="6" cy="6" r="1" fill="#10b981"/><circle cx="6" cy="14" r="1" fill="#10b981"/><path d="M9 20v2M15 20v2" stroke="#10b981" stroke-width="1.8" stroke-linecap="round"/></svg>`,
    iconBg: 'rgba(16,185,129,0.1)',
    action: '去添加资产',
    nav: 'asset-list',
  },
  {
    title: '配置告警规则',
    desc: '系统内置 8 种告警策略（阈值、异常检测、趋势预测等），点「创建规则」自定义告警条件与接收人。',
    icon: `<svg width="32" height="32" viewBox="0 0 24 24" fill="none"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" stroke="#f59e0b" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M13.73 21a2 2 0 01-3.46 0" stroke="#f59e0b" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    iconBg: 'rgba(245,158,11,0.1)',
    action: '去配置告警',
    nav: 'alert-rules',
  },
  {
    title: '试试 AI 助手',
    desc: '在「AI 助手」提问，系统自动查状态、分析根因。试试：帮我看看系统健康度，或分析最近的告警。',
    icon: `<svg width="32" height="32" viewBox="0 0 24 24" fill="none"><path d="M12 2a7 7 0 017 7c0 2.38-1.19 4.47-3 5.74V17a2 2 0 01-2 2H10a2 2 0 01-2-2v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 017-7z" fill="#8b5cf6" opacity=".2"/><path d="M9 21h6M10 17v4M14 17v4" stroke="#8b5cf6" stroke-width="1.8" stroke-linecap="round"/></svg>`,
    iconBg: 'rgba(139,92,246,0.1)',
    action: '打开 AI 助手',
    nav: 'ai-ops-assistant',
  },
]

function doAction(i) {
  const nav = STEPS[i].nav
  if (nav) {
    emit('close')
    setTimeout(() => {
      try { window._navigateTo(nav) } catch {}
    }, 300)
  }
}

function maybeClose() {}
</script>

<style scoped>
.guide-overlay {
  position: fixed; inset: 0; z-index: 9000;
  background: rgba(15, 23, 42, 0.55);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
}

.guide-card {
  width: 460px; max-width: 92vw;
  background: #fff;
  border-radius: 20px;
  box-shadow: 0 24px 80px rgba(0,0,0,0.22), 0 0 0 1px rgba(255,255,255,0.1);
  overflow: hidden;
  display: flex; flex-direction: column;
}

.guide-card-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 20px 24px 16px;
  border-bottom: 1px solid #f1f5f9;
}

.guide-brand {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; font-weight: 600; color: #1e293b;
}

.guide-skip-btn {
  font-size: 12px; color: #94a3b8; background: none; border: none;
  cursor: pointer; padding: 4px 8px; border-radius: 6px;
  transition: color .15s, background .15s;
}
.guide-skip-btn:hover { color: #64748b; background: #f8fafc; }

.guide-steps-bar {
  display: flex; align-items: center; justify-content: center;
  gap: 10px; padding: 16px;
}

.guide-step-dot {
  width: 28px; height: 28px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 600;
  border: 2px solid #e2e8f0;
  color: #94a3b8;
  cursor: default;
  transition: all .25s;
}
.guide-step-dot.active {
  border-color: #6366f1;
  background: #6366f1;
  color: #fff;
  transform: scale(1.15);
  cursor: default;
}
.guide-step-dot.done {
  border-color: #10b981;
  background: #10b981;
  color: #fff;
  cursor: pointer;
}
.dot-check { font-size: 11px; }

.guide-card-body {
  padding: 8px 32px 24px;
  min-height: 240px;
  display: flex; align-items: center; justify-content: center;
}

.guide-step-content {
  display: flex; flex-direction: column; align-items: center;
  text-align: center; gap: 12px; width: 100%;
}

.guide-icon-wrap {
  width: 68px; height: 68px; border-radius: 18px;
  display: flex; align-items: center; justify-content: center;
  margin-bottom: 4px;
}

.guide-step-title {
  font-size: 18px; font-weight: 700; color: #0f172a;
  margin: 0; letter-spacing: -.02em;
}

.guide-step-desc {
  font-size: 13px; color: #64748b; line-height: 1.7;
  margin: 0; max-width: 340px;
}

.guide-action-btn {
  margin-top: 4px;
  background: #f8fafc; border: 1px solid #e2e8f0;
  border-radius: 10px; padding: 8px 18px;
  font-size: 13px; font-weight: 500; color: #1e293b;
  cursor: pointer;
  transition: all .15s;
}
.guide-action-btn:hover {
  background: #f1f5f9; border-color: #cbd5e1;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

.guide-card-footer {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 24px 20px;
  border-top: 1px solid #f1f5f9;
}

.guide-footer-right {
  display: flex; align-items: center; gap: 12px;
  margin-left: auto;
}

.guide-progress {
  font-size: 11px; color: #94a3b8;
}

.guide-btn {
  border: none; border-radius: 10px;
  font-size: 13px; font-weight: 500;
  cursor: pointer; padding: 8px 18px;
  transition: all .15s;
}
.guide-btn-ghost {
  background: none; color: #64748b;
}
.guide-btn-ghost:hover { color: #1e293b; background: #f8fafc; }
.guide-btn-primary {
  background: #6366f1; color: #fff;
}
.guide-btn-primary:hover {
  background: #4f46e5;
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(99,102,241,0.35);
}
.guide-btn-done {
  background: #10b981; color: #fff;
}
.guide-btn-done:hover {
  background: #059669;
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(16,185,129,0.35);
}

/* transitions */
.guide-fade-enter-active, .guide-fade-leave-active { transition: opacity .15s; }
.guide-fade-enter-from, .guide-fade-leave-to { opacity: 0; pointer-events: none; }

.guide-slide-enter-active { transition: all .3s ease-out; }
.guide-slide-leave-active { transition: all .2s ease-in; }
.guide-slide-enter-from { opacity: 0; transform: translateX(24px); }
.guide-slide-leave-to { opacity: 0; transform: translateX(-24px); }
</style>
