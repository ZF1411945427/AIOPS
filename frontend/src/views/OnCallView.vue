<template>
  <div class="oncall">
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="title">值班表</span>
          <el-button type="primary" @click="showCreateDialog">+ 新建值班表</el-button>
        </div>
      </template>
      
      <!-- 当前值班 -->
      <el-alert v-if="currentOncall.current_oncall" :title="`当前值班: ${currentOncall.current_oncall}`" type="success" :closable="false" style="margin-bottom: 20px">
        <template #default>
          <div>{{ currentOncall.team_name }} - {{ formatTime(currentOncall.period_start) }} ~ {{ formatTime(currentOncall.period_end) }}</div>
        </template>
      </el-alert>
      <el-alert v-else title="暂无值班安排" type="info" :closable="false" style="margin-bottom: 20px" />
      
      <!-- 值班表列表 -->
      <el-table :data="oncallList" stripe>
        <el-table-column prop="team_name" label="团队" />
        <el-table-column prop="rotation_type" label="轮值方式">
          <template #default="{row}">
            {{ row.rotation_type === "weekly" ? "周轮值" : "月轮值" }}
          </template>
        </el-table-column>
        <el-table-column prop="current_oncall" label="当前值班人" />
        <el-table-column prop="current_period_start" label="周期开始">
          <template #default="{row}">
            {{ formatTime(row.current_period_start) }}
          </template>
        </el-table-column>
        <el-table-column prop="current_period_end" label="周期结束">
          <template #default="{row}">
            {{ formatTime(row.current_period_end) }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    
    <!-- 新建对话框 -->
    <el-dialog v-model="dialogVisible" title="新建值班表" width="500px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="团队名">
          <el-input v-model="form.team_name" placeholder="如: 运维组" />
        </el-form-item>
        <el-form-item label="轮值方式">
          <el-radio-group v-model="form.rotation_type">
            <el-radio label="weekly">周轮值</el-radio>
            <el-radio label="monthly">月轮值</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="成员">
          <el-input v-model="membersStr" placeholder="用逗号分隔，如: 张三,李四,王五" />
        </el-form-item>
        <el-form-item label="当前值班人">
          <el-select v-model="form.current_oncall" placeholder="选择当前值班人">
            <el-option v-for="m in members" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
        <el-form-item label="周期开始">
          <el-date-picker v-model="form.current_period_start" type="datetime" />
        </el-form-item>
        <el-form-item label="周期结束">
          <el-date-picker v-model="form.current_period_end" type="datetime" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="createOncall">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, computed } from "vue"
import { ElMessage } from "element-plus"
import axios from "axios"

const oncallList = ref([])
const currentOncall = ref({})
const dialogVisible = ref(false)
const form = reactive({
  team_name: "",
  rotation_type: "weekly",
  members: [],
  schedule: [],
  current_oncall: "",
  current_period_start: new Date(),
  current_period_end: new Date()
})
const membersStr = ref("")
const members = computed(() => membersStr.value.split(",").map(m => m.trim()).filter(m => m))

const loadData = async () => {
  try {
    const res = await axios.get("/api/sre/oncall")
    oncallList.value = res.data
  } catch (e) {
    console.error(e)
  }
}

const loadCurrentOncall = async () => {
  try {
    const res = await axios.get("/api/sre/oncall/current")
    currentOncall.value = res.data
  } catch (e) {
    console.error(e)
  }
}

const showCreateDialog = () => {
  form.team_name = ""
  form.rotation_type = "weekly"
  membersStr.value = ""
  form.current_oncall = ""
  form.current_period_start = new Date()
  form.current_period_end = new Date()
  dialogVisible.value = true
}

const createOncall = async () => {
  try {
    await axios.post("/api/sre/oncall", {
      ...form,
      members: members.value,
      schedule: members.value.map((m, i) => ({ order: i, name: m }))
    })
    ElMessage.success("创建成功")
    dialogVisible.value = false
    loadData()
  } catch (e) {
    ElMessage.error("创建失败")
  }
}

const formatTime = (time) => {
  return time ? new Date(time).toLocaleString() : "-"
}

onMounted(() => {
  loadData()
  loadCurrentOncall()
})
</script>

<style scoped>
.oncall {
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
</style>
