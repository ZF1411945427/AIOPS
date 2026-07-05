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
        <el-table-column label="成员">
          <template #default="{row}">
            <el-tag v-for="m in (row.members || [])" :key="m" size="small" style="margin: 2px">{{ m }}</el-tag>
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
        <el-table-column label="操作" width="160">
          <template #default="{row}">
            <el-button size="small" @click="showEditDialog(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="deleteOncall(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    
    <!-- 新建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑值班表' : '新建值班表'" width="560px">
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
          <el-select
            v-model="form.members"
            multiple
            filterable
            allow-create
            default-first-option
            :reserve-keyword="false"
            placeholder="选择已有成员或输入新成员（可多选）"
            style="width: 100%"
          >
            <el-option v-for="m in memberCandidates" :key="m" :label="m" :value="m" />
          </el-select>
          <div class="hint">已复用 {{ memberCandidates.length }} 名成员，避免重复输入</div>
        </el-form-item>
        <el-form-item label="当前值班人">
          <el-select v-model="form.current_oncall" placeholder="选择当前值班人" filterable>
            <el-option v-for="m in form.members" :key="m" :label="m" :value="m" />
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
        <el-button type="primary" @click="saveOncall">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import axios from "axios"

const oncallList = ref([])
const currentOncall = ref({})
const memberCandidates = ref([])
const dialogVisible = ref(false)
const editingId = ref(null)
const form = reactive({
  team_name: "",
  rotation_type: "weekly",
  members: [],
  schedule: [],
  current_oncall: "",
  current_period_start: new Date(),
  current_period_end: new Date()
})

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

const loadMemberCandidates = async () => {
  try {
    const res = await axios.get("/api/sre/oncall/members")
    memberCandidates.value = res.data.members || []
  } catch (e) {
    console.error(e)
  }
}

const showCreateDialog = () => {
  editingId.value = null
  form.team_name = ""
  form.rotation_type = "weekly"
  form.members = []
  form.current_oncall = ""
  form.current_period_start = new Date()
  form.current_period_end = new Date()
  loadMemberCandidates()
  dialogVisible.value = true
}

const showEditDialog = (row) => {
  editingId.value = row.id
  form.team_name = row.team_name
  form.rotation_type = row.rotation_type
  form.members = [...(row.members || [])]
  form.current_oncall = row.current_oncall
  form.current_period_start = new Date(row.current_period_start)
  form.current_period_end = new Date(row.current_period_end)
  loadMemberCandidates()
  dialogVisible.value = true
}

const saveOncall = async () => {
  try {
    const payload = {
      ...form,
      members: form.members,
      schedule: form.members.map((m, i) => ({ order: i, name: m }))
    }
    if (editingId.value) {
      await axios.put(`/api/sre/oncall/${editingId.value}`, payload)
      ElMessage.success("更新成功")
    } else {
      await axios.post("/api/sre/oncall", payload)
      ElMessage.success("创建成功")
    }
    dialogVisible.value = false
    loadData()
    loadMemberCandidates()
  } catch (e) {
    ElMessage.error("保存失败")
  }
}

const deleteOncall = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除值班表「${row.team_name}」吗？`, "提示", { type: "warning" })
    await axios.delete(`/api/sre/oncall/${row.id}`)
    ElMessage.success("删除成功")
    loadData()
    loadMemberCandidates()
  } catch (e) {
    if (e !== "cancel") ElMessage.error("删除失败")
  }
}

const formatTime = (time) => {
  return time ? new Date(time).toLocaleString() : "-"
}

onMounted(() => {
  loadData()
  loadCurrentOncall()
  loadMemberCandidates()
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
.hint {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>
