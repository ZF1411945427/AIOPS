<template>
  <div class="slo-config">
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="title">SLO 配置管理</span>
          <el-button type="primary" @click="showCreateDialog">+ 新建 SLO</el-button>
        </div>
      </template>

      <el-table :data="sloList" stripe>
        <el-table-column prop="service_name" label="服务名" />
        <el-table-column prop="slo_target" label="目标可用性">
          <template #default="{row}">{{ (row.slo_target * 100).toFixed(2) }}%</template>
        </el-table-column>
        <el-table-column prop="window_days" label="窗口(天)" />
        <el-table-column prop="total_requests" label="总请求" />
        <el-table-column prop="error_requests" label="错误请求" />
        <el-table-column prop="status" label="状态">
          <template #default="{row}">
            <el-tag :type="getStatusType(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{row}">
            <el-button type="primary" size="small" @click="editSlo(row)">编辑</el-button>
            <el-button type="danger" size="small" @click="deleteSlo(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑 SLO' : '新建 SLO'" width="450px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="服务名">
          <el-input v-model="form.service_name" placeholder="如: payment-service" />
        </el-form-item>
        <el-form-item label="目标可用性">
          <el-input-number v-model="form.slo_target" :min="0.9" :max="0.99999" :step="0.001" :precision="5" />
        </el-form-item>
        <el-form-item label="窗口(天)">
          <el-input-number v-model="form.window_days" :min="1" :max="365" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveSlo">{{ isEdit ? '更新' : '确定' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive } from "vue"
import { ElMessage } from "element-plus"
import axios from "axios"

const sloList = ref([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const editingId = ref(null)
const form = reactive({
  service_name: "",
  slo_target: 0.999,
  window_days: 30
})

const loadData = async () => {
  try {
    const res = await axios.get("/api/sre/slo")
    sloList.value = res.data
  } catch (e) {
    console.error(e)
  }
}

const showCreateDialog = () => {
  isEdit.value = false
  editingId.value = null
  form.service_name = ""
  form.slo_target = 0.999
  form.window_days = 30
  dialogVisible.value = true
}

const editSlo = (row) => {
  isEdit.value = true
  editingId.value = row.id
  form.service_name = row.service_name
  form.slo_target = row.slo_target
  form.window_days = row.window_days
  dialogVisible.value = true
}

const saveSlo = async () => {
  try {
    if (isEdit.value && editingId.value) {
      await axios.put(`/api/sre/slo/${editingId.value}`, form)
      ElMessage.success("更新成功")
    } else {
      await axios.post("/api/sre/slo", form)
      ElMessage.success("创建成功")
    }
    dialogVisible.value = false
    loadData()
  } catch (e) {
    ElMessage.error("操作失败")
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

onMounted(loadData)
</script>

<style scoped>
.slo-config { padding: 20px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.title { font-size: 18px; font-weight: bold; }
</style>
