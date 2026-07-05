<template>
  <div class="overview-page">
    <div class="page-header">
      <h1>Docker 容器概览</h1>
      <p>Docker 主机与容器统计 · 运行率 {{ summary.running_rate || 0 }}%</p>
    </div>

    <div v-if="loading" class="loading-state">加载中...</div>
    <div v-else-if="errorMsg" class="error-state">{{ errorMsg }}</div>
    <template v-else>
      <div class="stat-row">
        <div class="stat-card grad-indigo"><div class="stat-num">{{ summary.total || 0 }}</div><div class="stat-label">容器总数</div></div>
        <div class="stat-card grad-green"><div class="stat-num">{{ summary.running || 0 }}</div><div class="stat-label">运行中</div></div>
        <div class="stat-card grad-red"><div class="stat-num">{{ summary.stopped || 0 }}</div><div class="stat-label">已停止</div></div>
        <div class="stat-card grad-blue"><div class="stat-num">{{ summary.host_count || 0 }}</div><div class="stat-label">Docker 主机</div></div>
      </div>

      <div class="grid-2">
        <div class="panel">
          <div class="panel-head">主机分布</div>
          <div class="panel-body">
            <div v-if="hostStats.length" class="host-list">
              <div v-for="h in hostStats" :key="h.host" class="host-item">
                <div class="host-head"><span class="host-name">{{ h.host }}</span><span class="host-meta">{{ h.running }}/{{ h.total }} 运行 · {{ h.running_rate }}%</span></div>
                <div class="bar-track">
                  <div class="bar-run" :style="{ width: (h.total ? h.running / h.total * 100 : 0) + '%' }"></div>
                  <div class="bar-stop" :style="{ width: (h.total ? h.stopped / h.total * 100 : 0) + '%' }"></div>
                </div>
              </div>
            </div>
            <div v-else class="empty-state">暂无主机数据</div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">热门镜像 Top 5</div>
          <div class="panel-body">
            <div v-if="topImages.length" class="image-list">
              <div v-for="(img, idx) in topImages" :key="img.image" class="image-item">
                <div class="image-head"><span class="image-rank">#{{ idx + 1 }}</span><span class="image-name">{{ img.image }}</span><span class="image-count">{{ img.count }}</span></div>
                <div class="bar-track">
                  <div class="bar-grad" :style="{ width: imagePercent(img.count) + '%' }"></div>
                </div>
              </div>
            </div>
            <div v-else class="empty-state">暂无镜像数据</div>
          </div>
        </div>
      </div>

      <div class="panel" style="margin-top:14px;">
        <div class="panel-head">最近创建容器 · {{ recentContainers.length }} 条</div>
        <div class="panel-body">
          <div v-if="recentContainers.length" class="table-wrap">
            <table class="table">
              <thead><tr><th>容器名</th><th>主机</th><th>镜像</th><th>状态</th><th>端口</th><th>创建时间</th></tr></thead>
              <tbody>
                <tr v-for="c in recentContainers" :key="c.id">
                  <td class="name-cell">{{ c.name }}</td>
                  <td>{{ c.host }}</td>
                  <td class="img-cell">{{ c.image }}</td>
                  <td><span class="badge" :class="c.state === 'running' ? 'state-run' : 'state-stop'">{{ c.state }}</span></td>
                  <td class="port-cell">{{ c.ports || '-' }}</td>
                  <td>{{ c.created_at || '-' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="empty-state"><div style="font-size:32px;margin-bottom:8px;">🐳</div><div>暂无容器</div></div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const loading = ref(false)
const errorMsg = ref('')
const summary = ref({})
const hostStats = ref([])
const topImages = ref([])
const recentContainers = ref([])
const maxImageCount = ref(1)

function imagePercent(count) { return maxImageCount.value ? Math.round(count / maxImageCount.value * 100) : 0 }

async function loadOverview() {
  loading.value = true
  errorMsg.value = ''
  try {
    const data = await request.get('/containers/api/overview')
    summary.value = data.summary || {}
    hostStats.value = data.host_stats || []
    topImages.value = data.top_images || []
    recentContainers.value = data.recent_containers || []
    maxImageCount.value = topImages.value.length ? topImages.value[0].count : 1
  } catch (e) {
    errorMsg.value = '加载失败: ' + (e.message || e)
    ElMessage.error(errorMsg.value)
  } finally {
    loading.value = false
  }
}

onMounted(loadOverview)
</script>

<style scoped>
.overview-page { padding: 4px; }
.page-header { margin-bottom: 16px; }
.page-header h1 { font-size: 1.4rem; font-weight: 600; color: var(--text, #1e293b); margin: 0 0 4px; }
.page-header p { color: var(--text-secondary, #64748b); font-size: 0.85rem; margin: 0; }
.stat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
.stat-card { border-radius: 10px; padding: 18px; color: #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.stat-num { font-size: 1.8rem; font-weight: 700; line-height: 1.2; }
.stat-label { font-size: 0.78rem; opacity: 0.9; margin-top: 4px; }
.grad-indigo { background: linear-gradient(135deg, #6366f1, #818cf8); }
.grad-green { background: linear-gradient(135deg, #10b981, #34d399); }
.grad-red { background: linear-gradient(135deg, #ef4444, #f87171); }
.grad-blue { background: linear-gradient(135deg, #3b82f6, #60a5fa); }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.panel { background: var(--bg-card, #fff); border: 1px solid var(--border, rgba(0,0,0,0.07)); border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.panel-head { padding: 12px 18px; border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); font-weight: 600; font-size: 0.9rem; color: var(--text, #1e293b); }
.panel-body { padding: 14px 18px; }
.host-list, .image-list { display: flex; flex-direction: column; gap: 12px; }
.host-item, .image-item { display: flex; flex-direction: column; gap: 4px; }
.host-head, .image-head { display: flex; align-items: center; gap: 8px; font-size: 0.82rem; }
.host-name { font-weight: 600; color: var(--text, #1e293b); }
.host-meta { margin-left: auto; color: var(--text-secondary, #64748b); font-size: 0.76rem; }
.image-rank { font-weight: 700; color: var(--accent, #6366f1); width: 24px; }
.image-name { color: var(--text, #1e293b); flex: 1; word-break: break-all; }
.image-count { color: var(--text-secondary, #64748b); font-weight: 600; }
.bar-track { height: 8px; border-radius: 4px; background: var(--bg-hover, rgba(0,0,0,0.05)); overflow: hidden; display: flex; }
.bar-run { background: linear-gradient(90deg, #10b981, #34d399); height: 100%; }
.bar-stop { background: rgba(239,68,68,0.5); height: 100%; }
.bar-grad { background: linear-gradient(90deg, #6366f1, #a78bfa); height: 100%; border-radius: 4px; }
.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; }
.table th { text-align: left; padding: 10px 12px; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary, #64748b); border-bottom: 1px solid var(--border-strong, rgba(0,0,0,0.12)); text-transform: uppercase; letter-spacing: 0.3px; white-space: nowrap; }
.table td { padding: 10px 12px; font-size: 0.85rem; color: var(--text, #1e293b); border-bottom: 1px solid var(--border, rgba(0,0,0,0.07)); }
.name-cell { font-weight: 600; }
.img-cell, .port-cell { max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.72rem; font-weight: 600; }
.state-run { background: rgba(16,185,129,0.12); color: #10b981; }
.state-stop { background: rgba(239,68,68,0.12); color: #ef4444; }
.loading-state, .empty-state { text-align: center; padding: 24px; color: var(--text-tertiary, #94a3b8); font-size: 0.9rem; }
.error-state { text-align: center; padding: 24px; color: #ef4444; font-size: 0.9rem; }
</style>
