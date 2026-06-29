<template>
  <div class="error-budget">
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="title">错误预算管理</span>
          <el-button type="primary" @click="showCreateDialog">+ 新建 SLO</el-button>
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
      
      <!-- SLO 列表 -->
      <el-table :data="sloList" stripe>
        <el-table-column prop="service_name" label="服务名" />
        <el-table-column prop="slo_target" label="目标可用性">
          <template #default="{row}">
            {{ (row.slo_target * 100).toFixed(2) }}%
          </template>
        </el-table-column>
        <el-table-column prop="window_days" label="窗口(天)" />
        <el-table-column prop="status" label="状态">
          <template #default="{row}">
            <el-tag :type="getStatusType(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间">
          <template #default="{row}">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作">
          <template #default="{row}">
            <el-button type="danger" size="small" @click="deleteSlo(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    
    <!-- 新建对话框 -->
    <el-dialog v-model="dialogVisible" title="新建 SLO" width="400px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="服务名">
          <el-input v-model="form.service_name" placeholder="如: payment-service" />
        </el-form-item>
        <el-form-item label="目标可用性">
          <el-input-number v-model="form.slo_target" :min="0.9" :max="0.999" :step="0.001" />
        </el-form-item>
        <el-form-item label="窗口(天)">
          <el-input-number v-model="form.window_days" :min="1" :max="90" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="createSlo">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive } from "vue"
import { ElMessage } from "element-plus"
import axios from "axios"

const sloList = ref([])
const summary = ref({ total: 0, healthy: 0, warning: 0, critical: 0 })
const dialogVisible = ref(false)
const form = reactive({
  service_name: "",
  slo_target: 0.999,
  window_days: 30
})

const loadData = async () => {
  try {
    const res = await axios.get("/api/sre/slo")
    sloList.value = res.data
    // 计算汇总
    summary.value.total = res.data.length
    summary.value.healthy = res.data.filter(s => s.status === "healthy").length
    summary.value.warning = res.data.filter(s => s.status === "warning").length
    summary.value.critical = res.data.filter(s => s.status === "critical").length
  } catch (e) {
    console.error(e)
  }
}

const showCreateDialog = () => {
  form.service_name = ""
  form.slo_target = 0.999
  form.window_days = 30
  dialogVisible.value = true
}

const createSlo = async () => {
  try {
    await axios.post("/api/sre/slo", form)
    ElMessage.success("创建成功")
    dialogVisible.value = false
    loadData()
  } catch (e) {
    ElMessage.error("创建失败")
  }
}

const deleteSlo = async (id) => {
  try {
    await axios.delete(`/api/sre/slo/${id}`)
    ElMessage.success("删除成功")
    loadData()
  } catch (e) {
    ElMessage.error("删除失败")
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
