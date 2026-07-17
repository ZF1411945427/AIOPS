<template>
  <div class="availability-report">
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="title">可用性报表</span>
          <div>
            <button class="btn btn-guide" @click="showGuide = !showGuide">📖 操作说明</button>
            <el-button type="success" @click="generateReport" :loading="generating">生成报表</el-button>
            <el-button type="primary" @click="loadData">刷新</el-button>
          </div>
        </div>
      </template>

      <el-row :gutter="20" class="summary-row">
        <el-col :span="6">
          <el-card shadow="never" class="stat-card">
            <div class="stat-value">{{ stats.total }}</div>
            <div class="stat-label">总服务数</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never" class="stat-card">
            <div class="stat-value" style="color:#67C23A">{{ stats.healthy }}</div>
            <div class="stat-label">健康 (≥99.9%)</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never" class="stat-card">
            <div class="stat-value" style="color:#E6A23C">{{ stats.warning }}</div>
            <div class="stat-label">警告 (≥99%)</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never" class="stat-card">
            <div class="stat-value" style="color:#F56C6C">{{ stats.critical }}</div>
            <div class="stat-label">严重 (&lt;99%)</div>
          </el-card>
        </el-col>
      </el-row>

      <el-table :data="reportList" stripe>
        <el-table-column prop="service_name" label="服务名" />
        <el-table-column prop="reported_at" label="报告日期">
          <template #default="{row}">{{ formatTime(row.reported_at) }}</template>
        </el-table-column>
        <el-table-column prop="availability_pct" label="可用性">
          <template #default="{row}">
            <el-tag :type="getAvailType(row.availability_pct)">
              {{ row.availability_pct.toFixed(4) }}%
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_uptime" label="运行时间">
          <template #default="{row}">{{ formatDuration(row.total_uptime) }}</template>
        </el-table-column>
        <el-table-column prop="total_downtime" label="停机时间">
          <template #default="{row}">{{ formatDuration(row.total_downtime) }}</template>
        </el-table-column>
        <el-table-column prop="incident_count" label="故障次数" />
        <el-table-column label="操作" width="100">
          <template #default="{row}">
            <el-button type="danger" size="small" @click="deleteReport(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <GuideDrawer v-model="showGuide" title="📖 可用性报表 · 概念说明">
      <section class="guide-section">
        <h4>1. 可用性是什么？</h4>
        <p><strong>可用性（Availability）</strong>是衡量服务是否"在正常工作"的核心指标。</p>
        <div class="formula">可用性 = 正常运行时间 / 总时间 × 100%</div>
        <p>如果一个月有 30 天，服务停了 3 天：</p>
        <ul>
          <li>可用性 = 27 / 30 = <strong>90%</strong></li>
          <li>这意味着每年有 36.5 天不可用——对正经业务来说不可接受</li>
        </ul>
      </section>
      <section class="guide-section">
        <h4>2. 几个9的含义</h4>
        <div class="key-value-list">
          <div class="kv-row"><span class="kv-key">90%（1个9）</span><span class="kv-val">年停机 36.5 天 — 个人项目</span></div>
          <div class="kv-row"><span class="kv-key">99%（2个9）</span><span class="kv-val">年停机 3.65 天 — 内部工具</span></div>
          <div class="kv-row"><span class="kv-key">99.9%（3个9）</span><span class="kv-val">年停机 8.76 小时 — 商业服务</span></div>
          <div class="kv-row"><span class="kv-key">99.99%（4个9）</span><span class="kv-val">年停机 52.6 分钟 — 关键业务</span></div>
          <div class="kv-row"><span class="kv-key">99.999%（5个9）</span><span class="kv-val">年停机 5.26 分钟 — 电信级</span></div>
        </div>
      </section>
      <section class="guide-section">
        <h4>3. 页面状态阈值</h4>
        <ul>
          <li><span class="tag-demo" style="background:rgba(16,185,129,0.12);color:#10b981;">健康 ≥99.9%</span> — 服务稳定，无需担心</li>
          <li><span class="tag-demo" style="background:rgba(245,158,11,0.12);color:#d97706;">警告 ≥99%</span> — 可用性有所下降，建议排查</li>
          <li><span class="tag-demo" style="background:rgba(239,68,68,0.12);color:#ef4444;">严重 &lt;99%</span> — 可用性严重不达标，需立即处理</li>
        </ul>
      </section>
      <section class="guide-section">
        <h4>4. 报表有什么用？</h4>
        <ul>
          <li><strong>趋势分析</strong> — 看可用性是变好了还是变差了</li>
          <li><strong>SLA 合规审计</strong> — 证明你是否达到了对外承诺的可用性</li>
          <li><strong>故障复盘</strong> — 每次故障后的 downtime 会反映在报表中</li>
          <li><strong>驱动改进</strong> — 持续低的可用性说明需要架构改进（加容错、做冗余）</li>
        </ul>
      </section>
    </GuideDrawer>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from "vue"
import { ElMessage } from "element-plus"
import axios from "axios"
import GuideDrawer from '@/components/GuideDrawer.vue'

const showGuide = ref(false)
const reportList = ref([])
const generating = ref(false)

const stats = computed(() => {
  const list = reportList.value
  return {
    total: list.length,
    healthy: list.filter(r => r.availability_pct >= 99.9).length,
    warning: list.filter(r => r.availability_pct >= 99 && r.availability_pct < 99.9).length,
    critical: list.filter(r => r.availability_pct < 99).length
  }
})

const loadData = async () => {
  try {
    const res = await axios.get("/api/sre/availability")
    reportList.value = res.data
  } catch (e) {
    console.error(e)
  }
}

const generateReport = async () => {
  generating.value = true
  try {
    const res = await axios.post("/api/sre/availability/generate")
    ElMessage.success(res.data.message)
    loadData()
  } catch (e) {
    ElMessage.error("生成失败")
  } finally {
    generating.value = false
  }
}

const deleteReport = async (id) => {
  try {
    await axios.delete(`/api/sre/availability/${id}`)
    ElMessage.success("删除成功")
    loadData()
  } catch (e) {
    ElMessage.error("删除失败")
  }
}

const getAvailType = (pct) => {
  if (pct >= 99.9) return "success"
  if (pct >= 99) return "warning"
  return "danger"
}

const formatTime = (time) => {
  return time ? new Date(time).toLocaleString() : "-"
}

const formatDuration = (seconds) => {
  if (!seconds) return "0s"
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  return `${d}d ${h}h`
}

onMounted(loadData)
</script>

<style scoped>
.availability-report { padding: 20px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.title { font-size: 18px; font-weight: bold; }
.summary-row { margin-bottom: 20px; }
.stat-card { text-align: center; padding: 12px; }
.stat-value { font-size: 28px; font-weight: bold; }
.stat-label { font-size: 12px; color: #999; margin-top: 4px; }
</style>
