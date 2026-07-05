<template>
  <div class="settings-page">
    <div class="page-header">
      <h1>系统配置</h1>
      <p>全局键值对配置 · 采集 / 告警 / 探测 / SMTP</p>
    </div>

    <div v-if="loading" class="loading-state">加载中...</div>
    <div v-else class="settings-grid">
      <div v-for="g in groups" :key="g.title" class="panel">
        <div class="panel-head">{{ g.title }}</div>
        <div class="panel-body">
          <div v-for="key in g.keys" :key="key" class="form-row">
            <label>{{ labels[key] || key }}</label>
            <input v-model="form[key]" class="input" :type="key === 'smtp_password' ? 'password' : 'text'">
          </div>
        </div>
      </div>
    </div>

    <div class="actions-bar" v-if="!loading">
      <button class="btn btn-primary" @click="save" :disabled="saving">{{ saving ? '保存中...' : '保存设置' }}</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const saving = ref(false)
const configs = ref({})
const form = ref({})

const labels = {
  background_interval: '后台采集间隔(秒)',
  data_retention_days: '指标数据保留天数',
  alert_retention_days: '告警数据保留天数',
  escalation_minutes: '告警升级时间(分钟)',
  dedup_window_minutes: '告警去重窗口(分钟)',
  storm_threshold: '告警风暴阈值(条/分钟)',
  incident_window_minutes: '故障关联时间窗口(分钟)',
  smtp_host: 'SMTP 服务器地址',
  smtp_port: 'SMTP 端口',
  smtp_user: 'SMTP 用户',
  smtp_password: 'SMTP 密码',
  smtp_recipients: '收件人列表(逗号分隔)',
  asset_probe_enabled: '启用资产定时探测(true/false)',
  asset_probe_interval: '资产探测间隔(秒)',
  asset_probe_timeout: '单次探测超时(秒)',
  metric_collect_enabled: '启用指标采集(true/false)',
  metric_collect_interval: '指标采集间隔(秒)',
}

const groups = computed(() => [
  { title: '指标采集与检测', keys: ['background_interval', 'data_retention_days', 'alert_retention_days', 'metric_collect_enabled', 'metric_collect_interval'] },
  { title: '告警设置', keys: ['escalation_minutes', 'dedup_window_minutes', 'storm_threshold', 'incident_window_minutes'] },
  { title: '资产健康探测', keys: ['asset_probe_enabled', 'asset_probe_interval', 'asset_probe_timeout'] },
  { title: '邮件通知(SMTP)', keys: ['smtp_host', 'smtp_port', 'smtp_user', 'smtp_password', 'smtp_recipients'] },
])

async function load() {
  loading.value = true
  try {
    const data = await request.get('/settings/api/list')
    configs.value = data.configs || {}
    const f = {}
    for (const k in configs.value) f[k] = configs.value[k].value
    form.value = f
  } catch (e) {
    ElMessage.error('加载配置失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    await request.post('/settings/api/update', form.value)
    ElMessage.success('保存成功')
    load()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.message || e))
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.settings-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.settings-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); }
.panel-body { padding: 14px 18px; }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 0.78rem; color: var(--text-secondary, #64748b); margin-bottom: 4px; }
.input { width: 100%; padding: 6px 10px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); font-size: 0.82rem; box-sizing: border-box; }
.actions-bar { margin-top: 16px; }
.btn { padding: 8px 20px; border: 1px solid var(--border-strong, rgba(0,0,0,0.12)); border-radius: 6px; background: var(--bg-card-solid, #fff); color: var(--text, #1e293b); cursor: pointer; font-size: 0.85rem; }
.btn-primary { background: var(--accent, #6366f1); color: #fff; border-color: var(--accent, #6366f1); }
.btn-primary:hover { background: var(--accent-hover, #4f46e5); }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.loading-state { text-align: center; padding: 32px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
</style>
