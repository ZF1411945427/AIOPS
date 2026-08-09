<template>
  <div class="autonomous-page">
    <div class="page-header">
      <div>
        <h2>AI Agent 自主巡检</h2>
        <p class="sub">感知 → 分析 → 执行 → 验证，周期自动循环（默认 5 分钟）</p>
      </div>
      <el-button type="primary" :loading="triggering" @click="handleTrigger">
        <el-icon><Refresh /></el-icon>&nbsp;立即巡检
      </el-button>
    </div>

    <el-row :gutter="16" class="stat-row">
      <el-col :span="6"><el-statistic title="巡检次数" :value="stats.total" /></el-col>
      <el-col :span="6"><el-statistic title="发现问题" :value="stats.issues" /></el-col>
      <el-col :span="6"><el-statistic title="执行动作" :value="stats.actions" /></el-col>
      <el-col :span="6"><el-statistic title="成功动作" :value="stats.success" /></el-col>
    </el-row>

    <el-tabs v-model="activeTab" class="autonomous-tabs">
      <el-tab-pane label="巡检历史" name="history">
        <el-table :data="cycles" v-loading="loading" stripe style="width: 100%">
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="summary" label="摘要" min-width="260" />
          <el-table-column label="资产" width="70" prop="asset_count" />
          <el-table-column label="问题" width="70" prop="issue_count" />
          <el-table-column label="动作" width="70" prop="action_count" />
          <el-table-column label="成功" width="70" prop="success_count" />
          <el-table-column label="耗时(ms)" width="90" prop="duration_ms" />
          <el-table-column label="时间" width="160">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button size="small" @click="showDetail(row)">详情</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="动作日志" name="actions">
        <el-table :data="allActions" v-loading="loading" stripe style="width: 100%">
          <el-table-column label="动作" width="120">
            <template #default="{ row }">{{ row.action }}</template>
          </el-table-column>
          <el-table-column prop="asset_id" label="资产" width="70" />
          <el-table-column prop="description" label="描述" min-width="220" />
          <el-table-column prop="command" label="命令" min-width="200" />
          <el-table-column label="通道" width="80">
            <template #default="{ row }">
              <el-tag :type="row.channel === 'tunnel' ? 'success' : 'info'" size="small">{{ row.channel }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="结果" width="70">
            <template #default="{ row }">
              <el-tag :type="row.success ? 'success' : 'danger'" size="small">{{ row.success ? '成功' : '失败' }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="detailDialog" title="巡检详情" width="720px">
      <template v-if="current">
        <div class="detail-summary">{{ current.summary }}</div>
        <h4>发现的问题</h4>
        <el-table :data="current.issues_found" size="small" stripe>
          <el-table-column label="资产" prop="asset_name" min-width="140" />
          <el-table-column label="指标" prop="metric" width="120" />
          <el-table-column label="值" prop="value" width="80" />
          <el-table-column label="级别" width="80">
            <template #default="{ row }">
              <el-tag :type="row.severity === 'critical' ? 'danger' : 'warning'" size="small">{{ row.severity }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="描述" prop="description" min-width="180" />
        </el-table>
        <h4>执行的动作</h4>
        <el-table v-if="current.actions_taken && current.actions_taken.length" :data="current.actions_taken" size="small" stripe>
          <el-table-column label="动作" prop="action" width="130" />
          <el-table-column label="描述" prop="description" min-width="200" />
          <el-table-column label="命令" prop="command" min-width="180" />
          <el-table-column label="结果" width="70">
            <template #default="{ row }">
              <el-tag :type="row.success ? 'success' : 'danger'" size="small">{{ row.success ? 'OK' : 'X' }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="本轮无动作" />
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import request from '@/api/request'

const activeTab = ref('history')
const cycles = ref([])
const loading = ref(false)
const triggering = ref(false)
const detailDialog = ref(false)
const current = ref(null)

const stats = computed(() => {
  let total = 0, issues = 0, actions = 0, success = 0
  for (const c of cycles.value) {
    total++
    issues += c.issue_count || 0
    actions += c.action_count || 0
    success += c.success_count || 0
  }
  return { total, issues, actions, success }
})

const allActions = computed(() => {
  const arr = []
  for (const c of cycles.value) {
    for (const a of (c.actions_taken || [])) {
      arr.push({ ...a, cycle_id: c.cycle_id })
    }
  }
  return arr
})

function statusType(s) {
  if (s === 'success') return 'success'
  if (s === 'partial') return 'warning'
  if (s === 'failed') return 'danger'
  return 'info'
}
function statusLabel(s) {
  return { success: '正常', partial: '部分', failed: '失败', running: '运行中' }[s] || s
}
function formatTime(ts) {
  if (!ts) return '-'
  return ts.replace('T', ' ').substring(0, 19)
}

async function load() {
  loading.value = true
  try {
    const res = await request.get('/agent/autonomous/history', { params: { limit: 50 } })
    cycles.value = res.cycles || []
  } catch (e) {
    console.error('Failed to load autonomous history:', e)
  } finally {
    loading.value = false
  }
}

async function handleTrigger() {
  triggering.value = true
  try {
    await request.post('/agent/autonomous/trigger')
    setTimeout(load, 8000)
  } catch (e) {
    console.error('Trigger failed:', e)
  } finally {
    triggering.value = false
  }
}

function showDetail(row) {
  current.value = row
  detailDialog.value = true
}

onMounted(load)
</script>

<style scoped>
.autonomous-page {
  padding: 20px;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.page-header h2 {
  margin: 0;
}
.sub {
  color: #909399;
  font-size: 13px;
  margin-top: 4px;
}
.stat-row {
  margin-bottom: 16px;
}
.el-statistic {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}
.autonomous-tabs {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
}
.detail-summary {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 6px;
  margin-bottom: 12px;
}
h4 {
  margin: 16px 0 8px;
}
</style>