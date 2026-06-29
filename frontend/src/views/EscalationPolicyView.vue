<template>
  <div class="escalation-policy">
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="title">升级策略管理</span>
          <el-button type="primary" @click="showCreateDialog">+ 新建策略</el-button>
        </div>
      </template>

      <el-table :data="policyList" stripe>
        <el-table-column prop="name" label="策略名" />
        <el-table-column prop="levels" label="升级级别">
          <template #default="{row}">
            <el-tag v-for="(l, i) in parseList(row.levels)" :key="i" style="margin-right:4px">{{ l }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="wait_minutes" label="等待时间(分)">
          <template #default="{row}">
            <span v-for="(w, i) in parseList(row.wait_minutes)" :key="i">
              {{ w }}分{{ i < parseList(row.wait_minutes).length - 1 ? ' → ' : '' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="notify_channels" label="通知渠道">
          <template #default="{row}">
            <el-tag v-for="(c, i) in parseList(row.notify_channels)" :key="i" type="info" style="margin-right:4px">{{ c }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="80">
          <template #default="{row}">
            <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '禁用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{row}">
            <el-button type="danger" size="small" @click="deletePolicy(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" title="新建升级策略" width="500px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="策略名">
          <el-input v-model="form.name" placeholder="如: 严重告警升级" />
        </el-form-item>
        <el-form-item label="升级级别">
          <el-input v-model="levelsStr" placeholder="用逗号分隔，如: L1,L2,L3" />
        </el-form-item>
        <el-form-item label="等待时间(分)">
          <el-input v-model="waitStr" placeholder="用逗号分隔，如: 5,15,30" />
        </el-form-item>
        <el-form-item label="通知渠道">
          <el-input v-model="channelsStr" placeholder="用逗号分隔，如: 短信,邮件,电话" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="createPolicy">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive } from "vue"
import { ElMessage } from "element-plus"
import axios from "axios"

const policyList = ref([])
const dialogVisible = ref(false)
const levelsStr = ref("")
const waitStr = ref("")
const channelsStr = ref("")
const form = reactive({
  name: "",
  levels: [],
  wait_minutes: [],
  notify_channels: [],
  is_active: true
})

const loadData = async () => {
  try {
    const res = await axios.get("/api/sre/escalation")
    policyList.value = res.data
  } catch (e) {
    console.error(e)
  }
}

const showCreateDialog = () => {
  form.name = ""
  levelsStr.value = ""
  waitStr.value = ""
  channelsStr.value = ""
  dialogVisible.value = true
}

const createPolicy = async () => {
  try {
    await axios.post("/api/sre/escalation", {
      ...form,
      levels: levelsStr.value.split(",").map(s => s.trim()).filter(Boolean),
      wait_minutes: waitStr.value.split(",").map(s => parseInt(s.trim())).filter(n => !isNaN(n)),
      notify_channels: channelsStr.value.split(",").map(s => s.trim()).filter(Boolean),
      is_active: true
    })
    ElMessage.success("创建成功")
    dialogVisible.value = false
    loadData()
  } catch (e) {
    ElMessage.error("创建失败")
  }
}

const deletePolicy = async (id) => {
  try {
    await axios.delete(`/api/sre/escalation/${id}`)
    ElMessage.success("删除成功")
    loadData()
  } catch (e) {
    ElMessage.error("删除失败")
  }
}

const parseList = (val) => {
  if (!val) return []
  if (Array.isArray(val)) return val
  try { return JSON.parse(val) } catch { return [] }
}

onMounted(loadData)
</script>

<style scoped>
.escalation-policy { padding: 20px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.title { font-size: 18px; font-weight: bold; }
</style>
