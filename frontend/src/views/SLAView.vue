<template>
  <div class="sla-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="title">SLA 协议管理</span>
          <el-button type="primary" @click="showCreateDialog">+ 新建 SLA</el-button>
        </div>
      </template>

      <el-table :data="slaList" stripe>
        <el-table-column prop="service_name" label="服务名" />
        <el-table-column prop="sla_target" label="SLA 目标">
          <template #default="{row}">{{ (row.sla_target * 100).toFixed(2) }}%</template>
        </el-table-column>
        <el-table-column prop="achieved_sla" label="实际达成">
          <template #default="{row}">
            <el-tag :type="row.achieved_sla >= row.sla_target ? 'success' : 'danger'">
              {{ (row.achieved_sla * 100).toFixed(4) }}%
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="uptime_seconds" label="运行时间">
          <template #default="{row}">{{ formatDuration(row.uptime_seconds) }}</template>
        </el-table-column>
        <el-table-column prop="downtime_seconds" label="停机时间">
          <template #default="{row}">{{ formatDuration(row.downtime_seconds) }}</template>
        </el-table-column>
        <el-table-column prop="penalty" label="处罚">
          <template #default="{row}">
            <el-tag :type="row.penalty === 'none' ? 'success' : row.penalty === 'warning' ? 'warning' : 'danger'">
              {{ row.penalty === 'none' ? '无' : row.penalty === 'warning' ? '警告' : '处罚' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{row}">
            <el-button type="danger" size="small" @click="deleteSla(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" title="新建 SLA 记录" width="500px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="服务名">
          <el-input v-model="form.service_name" placeholder="如: payment-service" />
        </el-form-item>
        <el-form-item label="SLA 目标">
          <el-input-number v-model="form.sla_target" :min="0.9" :max="0.99999" :step="0.001" :precision="5" />
        </el-form-item>
        <el-form-item label="运行时间(秒)">
          <el-input-number v-model="form.uptime_seconds" :min="0" :max="8640000" />
        </el-form-item>
        <el-form-item label="停机时间(秒)">
          <el-input-number v-model="form.downtime_seconds" :min="0" :max="864000" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="createSla">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive } from "vue"
import { ElMessage } from "element-plus"
import axios from "axios"

const slaList = ref([])
const dialogVisible = ref(false)
const form = reactive({
  service_name: "",
  sla_target: 0.999,
  uptime_seconds: 0,
  downtime_seconds: 0
})

const loadData = async () => {
  try {
    const res = await axios.get("/api/sre/sla")
    slaList.value = res.data
  } catch (e) {
    console.error(e)
  }
}

const showCreateDialog = () => {
  form.service_name = ""
  form.sla_target = 0.999
  form.uptime_seconds = 0
  form.downtime_seconds = 0
  dialogVisible.value = true
}

const createSla = async () => {
  try {
    await axios.post("/api/sre/sla", form)
    ElMessage.success("创建成功")
    dialogVisible.value = false
    loadData()
  } catch (e) {
    ElMessage.error("创建失败")
  }
}

const deleteSla = async (id) => {
  try {
    await axios.delete(`/api/sre/sla/${id}`)
    ElMessage.success("删除成功")
    loadData()
  } catch (e) {
    ElMessage.error("删除失败")
  }
}

const formatDuration = (seconds) => {
  if (!seconds) return "0s"
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  const parts = []
  if (d) parts.push(`${d}d`)
  if (h) parts.push(`${h}h`)
  if (m) parts.push(`${m}m`)
  if (s) parts.push(`${s}s`)
  return parts.join(" ") || "0s"
}

onMounted(loadData)
</script>

<style scoped>
.sla-view { padding: 20px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.title { font-size: 18px; font-weight: bold; }
</style>
