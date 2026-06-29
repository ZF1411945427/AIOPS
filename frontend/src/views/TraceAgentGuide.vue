<template>
  <div class="workbench-page-shell">
    <div class="section-toolbar">
      <div class="toolbar-head">
        <span class="toolbar-title">链路追踪接入指引</span>
        <span class="toolbar-desc">为各类型服务配置 Agent，接入分布式链路追踪</span>
      </div>
      <div class="workbench-card-actions">
        <el-button size="small" @click="loadStatus" :loading="loading">刷新状态</el-button>
      </div>
    </div>

    <!-- 接入状态卡片 -->
    <div class="status-row">
      <div class="status-card">
        <div class="status-num">{{ status.total_spans || 0 }}</div>
        <div class="status-lbl">Span 总数</div>
      </div>
      <div class="status-card">
        <div class="status-num">{{ status.total_traces || 0 }}</div>
        <div class="status-lbl">调用链数</div>
      </div>
      <div class="status-card">
        <div class="status-num">{{ (status.services || []).length }}</div>
        <div class="status-lbl">已接入服务</div>
      </div>
      <div class="status-card">
        <div class="status-num">{{ status.latest_span_time ? '有数据' : '无数据' }}</div>
        <div class="status-lbl">最近数据</div>
      </div>
    </div>

    <!-- OTLP 端点信息 -->
    <div class="endpoint-banner">
      <div class="endpoint-icon">📡</div>
      <div class="endpoint-info">
        <div class="endpoint-label">OTLP 接收端点</div>
        <div class="endpoint-url">{{ otlpEndpoint }}</div>
        <div class="endpoint-hint">将此地址配置到 OpenTelemetry Collector 或各服务 Agent 的 exporter endpoint</div>
      </div>
      <el-button size="small" type="primary" @click="copyEndpoint">复制地址</el-button>
    </div>

    <!-- 服务类型选择 -->
    <div class="guide-section">
      <div class="section-title">选择服务类型查看接入方式</div>
      <div class="type-tabs">
        <div
          v-for="(g, key) in guides"
          :key="key"
          class="type-tab"
          :class="{ active: activeType === key }"
          @click="activeType = key"
        >
          <span class="type-icon">{{ typeIcons[key] }}</span>
          <span class="type-label">{{ g.title }}</span>
        </div>
      </div>
    </div>

    <!-- 当前选中类型的指引 -->
    <div class="guide-detail" v-if="guides[activeType]">
      <div class="detail-header">
        <span class="detail-title">{{ guides[activeType].title }}</span>
        <el-tag size="small" type="info">{{ guides[activeType].type }}</el-tag>
      </div>
      <div class="detail-steps">
        <div v-for="(step, i) in guides[activeType].steps" :key="i" class="step-block">
          <div class="step-header">步骤 {{ i + 1 }}</div>
          <pre class="step-code">{{ step }}</pre>
          <el-button size="small" text @click="copyText(step)">复制</el-button>
        </div>
      </div>
    </div>

    <!-- 已接入数据源 -->
    <div class="ds-section" v-if="status.jaeger_sources?.length || status.otel_sources?.length">
      <div class="section-title">已配置的链路追踪数据源</div>
      <div class="ds-list">
        <div v-for="ds in (status.jaeger_sources || [])" :key="'j-'+ds.id" class="ds-item">
          <span class="ds-badge jaeger">Jaeger</span>
          <span class="ds-name">{{ ds.name }}</span>
          <span class="ds-endpoint">{{ ds.endpoint }}</span>
          <el-tag size="small" :type="ds.enabled ? 'success' : 'info'">{{ ds.enabled ? '启用' : '禁用' }}</el-tag>
        </div>
        <div v-for="ds in (status.otel_sources || [])" :key="'o-'+ds.id" class="ds-item">
          <span class="ds-badge otel">OTel</span>
          <span class="ds-name">{{ ds.name }}</span>
          <span class="ds-endpoint">{{ ds.endpoint }}</span>
          <el-tag size="small" :type="ds.enabled ? 'success' : 'info'">{{ ds.enabled ? '启用' : '禁用' }}</el-tag>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import request from '@/api/request'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const activeType = ref('java')
const status = ref({})
const guides = ref({})
const otlpEndpoint = ref('')

const typeIcons = {
  java: '☕',
  python: '🐍',
  go: '🐹',
  nodejs: '🟢',
  k8s: '☸',
  docker: '🐳',
  middleware: '🔌',
  traditional: '🖥',
}

async function loadGuide() {
  try {
    const res = await request.get('/api/v1/traces/agent-guide')
    guides.value = res.guides || {}
    otlpEndpoint.value = res.otlp_endpoint || ''
  } catch (e) {
    ElMessage.error('加载指引失败: ' + (e.message || e))
  }
}

async function loadStatus() {
  loading.value = true
  try {
    const res = await request.get('/api/v1/traces/ingest-status')
    status.value = res
  } catch (e) {
    ElMessage.error('加载状态失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

function copyEndpoint() {
  const fullUrl = window.location.origin + otlpEndpoint.value
  navigator.clipboard.writeText(fullUrl).then(() => {
    ElMessage.success('已复制: ' + fullUrl)
  })
}

function copyText(text) {
  navigator.clipboard.writeText(text).then(() => {
    ElMessage.success('已复制到剪贴板')
  })
}

onMounted(() => {
  loadGuide()
  loadStatus()
})
</script>

<style scoped>
.status-row { display: flex; gap: 10px; margin-bottom: 12px; }
.status-card {
  flex: 1; border-radius: 10px; padding: 14px; text-align: center;
  border: 1px solid rgba(148,163,184,0.12); background: var(--card-bg);
}
.status-num { font-size: 24px; font-weight: 800; color: var(--primary); }
.status-lbl { font-size: 11px; color: var(--text-secondary); margin-top: 4px; }

.endpoint-banner {
  display: flex; align-items: center; gap: 14px;
  padding: 16px 20px; border-radius: 10px; margin-bottom: 16px;
  background: linear-gradient(135deg, rgba(99,102,241,0.08), rgba(99,102,241,0.02));
  border: 1px solid rgba(99,102,241,0.15);
}
.endpoint-icon { font-size: 32px; }
.endpoint-info { flex: 1; }
.endpoint-label { font-size: 12px; color: var(--text-secondary); }
.endpoint-url {
  font-size: 16px; font-weight: 700; color: var(--primary);
  font-family: monospace; margin: 4px 0;
}
.endpoint-hint { font-size: 11px; color: var(--text-muted); }

.guide-section { margin-bottom: 16px; }
.section-title { font-size: 14px; font-weight: 600; margin-bottom: 10px; color: var(--text-primary); }
.type-tabs { display: flex; gap: 8px; flex-wrap: wrap; }
.type-tab {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 14px; border-radius: 8px; cursor: pointer;
  border: 1px solid rgba(148,163,184,0.15); background: var(--card-bg);
  transition: all 0.15s; font-size: 13px;
}
.type-tab:hover { border-color: var(--primary); }
.type-tab.active {
  background: var(--primary); color: #fff; border-color: var(--primary);
}
.type-icon { font-size: 16px; }

.guide-detail {
  border-radius: 10px; border: 1px solid rgba(148,163,184,0.12);
  background: var(--card-bg); padding: 16px 20px; margin-bottom: 16px;
}
.detail-header { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.detail-title { font-size: 15px; font-weight: 700; color: var(--text-primary); }
.detail-steps { display: flex; flex-direction: column; gap: 12px; }
.step-block {
  background: rgba(148,163,184,0.06); border-radius: 8px; padding: 12px 14px;
}
.step-header { font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; }
.step-code {
  font-family: 'Consolas', 'Monaco', monospace; font-size: 12px;
  white-space: pre-wrap; word-break: break-all;
  color: var(--text-primary); margin: 0 0 6px 0; line-height: 1.6;
}

.ds-section { margin-top: 16px; }
.ds-list { display: flex; flex-direction: column; gap: 6px; }
.ds-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 14px; border-radius: 8px;
  border: 1px solid rgba(148,163,184,0.1); background: var(--card-bg);
}
.ds-badge {
  font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 4px;
}
.ds-badge.jaeger { background: #6638b0; color: #fff; }
.ds-badge.otel { background: #425cc7; color: #fff; }
.ds-name { font-size: 13px; font-weight: 600; }
.ds-endpoint { font-size: 11px; color: var(--text-muted); flex: 1; }
</style>
