<template>
  <div class="availability-report">
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="title">可用性报表</span>
          <div>
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
        <el-table-column prop="report_date" label="报告日期">
          <template #default="{row}">{{ formatTime(row.report_date) }}</template>
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
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from "vue"
import { ElMessage } from "element-plus"
import axios from "axios"

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
