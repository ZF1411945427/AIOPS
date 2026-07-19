<template>
  <div class="error-budget">
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="title">错误预算管理</span>
          <div>
            <button class="btn btn-guide" @click="showGuide = !showGuide">📖 操作说明</button>
            <el-button type="primary" @click="loadData">刷新</el-button>
          </div>
        </div>
      </template>
      
      <!-- 汇总卡片 -->
      <el-row :gutter="20" class="summary-row">
        <el-col :span="6">
          <el-statistic title="总 SLO" :value="summary.total" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="健康" :value="summary.healthy" style="color: #67C23A" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="警告" :value="summary.warning" style="color: #E6A23C" />
        </el-col>
        <el-col :span="6">
          <el-statistic title="严重" :value="summary.critical" style="color: #F56C6C" />
        </el-col>
      </el-row>
      
      <!-- 错误预算列表（从 SLO 实时派生） -->
      <el-table :data="budgetList" stripe>
        <el-table-column prop="service_name" label="服务名" />
        <el-table-column prop="slo_target" label="SLO 目标" width="110">
          <template #default="{row}">{{ (row.slo_target * 100).toFixed(2) }}%</template>
        </el-table-column>
        <el-table-column prop="window_days" label="窗口(天)" width="90" />
        <el-table-column prop="budget_total" label="总预算(%)" width="100">
          <template #default="{row}">{{ row.budget_total.toFixed(1) }}</template>
        </el-table-column>
        <el-table-column prop="budget_consumed" label="已消耗(%)" width="100">
          <template #default="{row}">{{ row.budget_consumed.toFixed(2) }}</template>
        </el-table-column>
        <el-table-column prop="budget_remaining" label="剩余(%)" width="100">
          <template #default="{row}">
            <el-tag :type="row.budget_remaining > 50 ? 'success' : row.budget_remaining > 20 ? 'warning' : 'danger'">
              {{ row.budget_remaining.toFixed(2) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="burn_rate" label="消耗速率" width="100">
          <template #default="{row}">{{ row.burn_rate.toFixed(2) }}x</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{row}">
            <el-tag :type="getStatusType(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="SLO 创建时间" width="170">
          <template #default="{row}">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <GuideDrawer v-model="showGuide" title="📖 错误预算 · 概念说明">
      <section class="guide-section">
        <h4>1. 什么是错误预算？</h4>
        <p><strong>错误预算（Error Budget）</strong>是 SRE 中最核心的概念之一。简单说：</p>
        <div class="formula">错误预算 = 1 - SLO 目标</div>
        <p>如果你承诺 99.9% 可用性（SLO=99.9%），那么你有 <strong>0.1%</strong> 的"犯错空间"——这就是你的错误预算。</p>
        <p>打个比方：就像你答应女朋友"我每个月最多迟到 3 次"，这 3 次就是你的"错误预算"。</p>
      </section>
      <section class="guide-section">
        <h4>2. 错误预算怎么算？</h4>
        <p>用请求量来算更直观：</p>
        <div class="formula">错误预算总额 = 总请求数 × (1 - SLO 目标)</div>
        <p>假设一个服务月请求 100 万次，SLO=99.9%：</p>
        <ul>
          <li>错误预算总额 = 100万 × 0.1% = <strong>1000 次错误</strong></li>
          <li>如果已经发生了 800 次错误，那么剩余预算 = 20%</li>
          <li>剩余预算越少，说明越接近违约风险</li>
        </ul>
      </section>
      <section class="guide-section">
        <h4>3. 三态含义</h4>
        <div class="key-value-list">
          <div class="kv-row"><span class="kv-key"><span class="tag-demo" style="background:rgba(16,185,129,0.12);color:#10b981;">健康</span></span><span class="kv-val">错误预算充足（剩余 > 50%），一切正常</span></div>
          <div class="kv-row"><span class="kv-key"><span class="tag-demo" style="background:rgba(245,158,11,0.12);color:#d97706;">警告</span></span><span class="kv-val">错误预算消耗较快（剩余 20%~50%），需要关注</span></div>
          <div class="kv-row"><span class="kv-key"><span class="tag-demo" style="background:rgba(239,68,68,0.12);color:#ef4444;">严重</span></span><span class="kv-val">错误预算即将或已经耗尽（剩余 &lt; 20%），需要立即行动</span></div>
        </div>
      </section>
      <section class="guide-section">
        <h4>4. 错误预算的作用</h4>
        <ul>
          <li><strong>指导故障响应</strong> — 预算消耗过快说明服务有问题，需要排查</li>
          <li><strong>平衡创新与稳定</strong> — 预算充足时可以大胆上线新功能；预算紧张时应冻结发布、专注稳定性</li>
          <li><strong>量化服务质量</strong> — 用一个数字说清楚"服务到底好不好"</li>
        </ul>
        <div class="tip-box">💡 Google SRE 的核心理念：<strong>错误预算决定了你可以多快发布</strong>。预算没用完 → 可以发布；预算用完了 → 停止发布，先修稳定性。</div>
      </section>
    </GuideDrawer>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue"
import axios from "axios"
import GuideDrawer from '@/components/GuideDrawer.vue'

const showGuide = ref(false)
const budgetList = ref([])
const summary = ref({ total: 0, healthy: 0, warning: 0, critical: 0 })

const loadData = async () => {
  try {
    // 错误预算从 SLO 实时派生（后端 /error-budget 复用 slo_service._calc_burn）
    const [budgetRes, summaryRes] = await Promise.all([
      axios.get("/api/sre/error-budget"),
      axios.get("/api/sre/error-budget/summary"),
    ])
    budgetList.value = budgetRes.data
    summary.value = summaryRes.data
  } catch (e) {
    console.error("加载错误预算失败:", e)
  }
}

const getStatusType = (status) => {
  const map = { healthy: "success", warning: "warning", critical: "danger" }
  return map[status] || "info"
}

const formatTime = (time) => {
  return time ? new Date(time).toLocaleString() : "-"
}

onMounted(loadData)
</script>

<style scoped>
.error-budget {
  padding: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.title {
  font-size: 18px;
  font-weight: bold;
}
.summary-row {
  margin-bottom: 20px;
}
</style>
