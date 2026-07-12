<template>
  <div class="workbench-page-shell">
    <div class="section-toolbar">
      <div class="toolbar-head">
        <span class="toolbar-title">智能体审计</span>
        <span class="toolbar-desc">AI 智能体工具调用记录与执行评估指标</span>
      </div>
      <div class="workbench-card-actions">
        <el-button size="small" @click="loadAll">刷新</el-button>
      </div>
    </div>

    <!-- 评估指标卡片 -->
    <div class="stats-cards" v-loading="statsLoading">
      <div class="stat-card">
        <div class="stat-value">{{ stats.total_calls || 0 }}</div>
        <div class="stat-label">总调用数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" :class="{ 'text-success': stats.success_rate >= 80, 'text-warning': stats.success_rate >= 50 && stats.success_rate < 80, 'text-danger': stats.success_rate < 50 }">{{ stats.success_rate || 0 }}%</div>
        <div class="stat-label">成功率</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ stats.avg_latency_ms || 0 }}ms</div>
        <div class="stat-label">平均耗时</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ stats.p95_latency_ms || 0 }}ms</div>
        <div class="stat-label">P95 耗时</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ stats.session_count || 0 }}</div>
        <div class="stat-label">会话数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ stats.message_count || 0 }}</div>
        <div class="stat-label">消息数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ stats.pending_actions || 0 }}</div>
        <div class="stat-label">待确认动作</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ (stats.tools || []).length }}</div>
        <div class="stat-label">活跃工具数</div>
      </div>
    </div>

    <!-- 工具分布 + 成功率趋势 -->
    <div class="charts-row">
      <div class="chart-card">
        <div class="chart-title">工具调用分布</div>
        <div class="chart-body">
          <div v-if="!stats.tools || !stats.tools.length" class="chart-empty">暂无数据</div>
          <div v-else class="tool-bars">
            <div v-for="t in stats.tools" :key="t.tool_name" class="tool-bar-item">
              <div class="tool-bar-label">
                <span class="tool-name">{{ t.tool_name }}</span>
                <span class="tool-count">{{ t.count }}次 · {{ t.success_rate }}%</span>
              </div>
              <div class="tool-bar-track">
                <div class="tool-bar-fill" :style="{ width: barWidth(t.count) + '%', background: t.success_rate >= 80 ? '#67c23a' : t.success_rate >= 50 ? '#e6a23c' : '#f56c6c' }"></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="chart-card">
        <div class="chart-title">近 7 日成功率趋势</div>
        <div class="chart-body">
          <div v-if="!stats.daily_trend || !stats.daily_trend.length" class="chart-empty">暂无数据</div>
          <div v-else class="trend-chart">
            <div class="trend-bars">
              <div v-for="d in stats.daily_trend" :key="d.date" class="trend-bar-col">
                <div class="trend-bar-value">{{ d.success_rate }}%</div>
                <div class="trend-bar" :style="{ height: trendHeight(d.success_rate) + 'px', background: d.success_rate >= 80 ? '#67c23a' : d.success_rate >= 50 ? '#e6a23c' : '#f56c6c' }"></div>
                <div class="trend-bar-label">{{ d.date.slice(5) }}</div>
                <div class="trend-bar-count">{{ d.count }}次</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 工具调用明细表 -->
    <div class="workbench-card" style="flex:1;display:flex;flex-direction:column;margin-top:12px">
      <div class="card-head">
        <span class="card-title">工具调用明细</span>
        <span class="card-desc">最近 {{ total }} 条记录</span>
      </div>
      <el-table :data="invocations" v-loading="loading" style="width:100%" size="small" :max-height="500">
        <el-table-column prop="created_at" label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="tool_name" label="工具" width="140">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.tool_name }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'" size="small">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="latency_ms" label="耗时" width="80">
          <template #default="{ row }">{{ row.latency_ms }}ms</template>
        </el-table-column>
        <el-table-column prop="request_payload" label="请求参数" min-width="200">
          <template #default="{ row }">
            <div style="font-size:11px;font-family:monospace;max-height:60px;overflow-y:auto;white-space:pre-wrap">{{ formatJson(row.request_payload) }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="response_summary" label="响应摘要" min-width="200">
          <template #default="{ row }">
            <div style="font-size:11px;font-family:monospace;max-height:60px;overflow-y:auto;white-space:pre-wrap">{{ formatJson(row.response_summary) }}</div>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!loading && !invocations.length" style="text-align:center;padding:40px;color:var(--text-muted);font-size:13px">
        暂无工具调用记录
      </div>
      <div v-if="total > 0" style="display:flex;justify-content:flex-end;padding:12px 0">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next"
          small
          @size-change="loadData"
          @current-change="loadData"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import request from '@/api/request'

const loading = ref(false)
const statsLoading = ref(false)
const invocations = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const stats = ref({})

function formatTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('zh-CN')
}

function formatJson(obj) {
  if (!obj) return ''
  try {
    return typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2)
  } catch { return '' }
}

function barWidth(count) {
  const maxCount = Math.max(...(stats.value.tools || []).map(t => t.count), 1)
  return Math.round((count / maxCount) * 100)
}

function trendHeight(rate) {
  return Math.max(4, Math.round((rate / 100) * 80))
}

async function loadData() {
  loading.value = true
  try {
    const data = await request.get('/agent/invocations', { params: { page: page.value, page_size: pageSize.value } })
    invocations.value = data.items || []
    total.value = data.total || 0
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  statsLoading.value = true
  try {
    stats.value = await request.get('/agent/stats')
  } catch (e) {
    console.error(e)
  } finally {
    statsLoading.value = false
  }
}

function loadAll() {
  loadData()
  loadStats()
}

onMounted(loadAll)
</script>

<style scoped>
.stats-cards {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 12px;
  margin-bottom: 12px;
}
.stat-card {
  background: var(--el-bg-color, #fff);
  border: 1px solid var(--el-border-color-light, #e4e7ed);
  border-radius: 8px;
  padding: 16px 12px;
  text-align: center;
}
.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--el-text-color-primary, #303133);
  line-height: 1.2;
}
.stat-label {
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
  margin-top: 6px;
}
.text-success { color: #67c23a; }
.text-warning { color: #e6a23c; }
.text-danger { color: #f56c6c; }

.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.chart-card {
  background: var(--el-bg-color, #fff);
  border: 1px solid var(--el-border-color-light, #e4e7ed);
  border-radius: 8px;
  padding: 16px;
}
.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
  margin-bottom: 12px;
}
.chart-body {
  min-height: 120px;
}
.chart-empty {
  text-align: center;
  color: var(--el-text-color-secondary, #909399);
  font-size: 13px;
  padding: 30px 0;
}
.tool-bars {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 200px;
  overflow-y: auto;
}
.tool-bar-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.tool-bar-label {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}
.tool-name {
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
}
.tool-count {
  color: var(--el-text-color-secondary, #909399);
}
.tool-bar-track {
  height: 6px;
  background: var(--el-fill-color-light, #f5f7fa);
  border-radius: 3px;
  overflow: hidden;
}
.tool-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s;
}

.trend-chart {
  width: 100%;
}
.trend-bars {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  height: 120px;
  padding-top: 8px;
}
.trend-bar-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.trend-bar-value {
  font-size: 10px;
  font-weight: 600;
  color: var(--el-text-color-secondary, #909399);
}
.trend-bar {
  width: 100%;
  max-width: 32px;
  border-radius: 4px 4px 0 0;
  transition: height 0.3s;
  min-height: 4px;
}
.trend-bar-label {
  font-size: 10px;
  color: var(--el-text-color-secondary, #909399);
}
.trend-bar-count {
  font-size: 10px;
  color: var(--el-text-color-secondary, #909399);
}

.card-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
}
.card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
}
.card-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}

@media (max-width: 1200px) {
  .stats-cards { grid-template-columns: repeat(4, 1fr); }
  .charts-row { grid-template-columns: 1fr; }
}
</style>
