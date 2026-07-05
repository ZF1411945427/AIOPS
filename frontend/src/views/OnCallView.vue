<template>
  <div class="oncall">
    <el-card v-loading="loading">
      <template #header>
        <div class="card-header">
          <span class="title">值班表</span>
          <el-button type="primary" @click="showCreateDialog">+ 新建值班表</el-button>
        </div>
      </template>

      <!-- 当前值班（支持多团队同时值班） -->
      <template v-if="currentItems.length">
        <el-alert
          v-for="c in currentItems"
          :key="c.team_name"
          :title="`当前值班: ${c.current_oncall}（${c.team_name}）`"
          type="success"
          :closable="false"
          style="margin-bottom: 12px"
        >
          <template #default>
            <div>{{ formatTime(c.period_start) }} ~ {{ formatTime(c.period_end) }}</div>
          </template>
        </el-alert>
      </template>
      <el-alert v-else title="暂无值班安排" type="info" :closable="false" style="margin-bottom: 20px" />

      <!-- 值班表列表 -->
      <el-table :data="oncallList" stripe>
        <el-table-column prop="team_name" label="团队" />
        <el-table-column prop="rotation_type" label="轮值方式" width="100">
          <template #default="{row}">
            {{ row.rotation_type === "weekly" ? "周轮值" : "月轮值" }}
          </template>
        </el-table-column>
        <el-table-column label="成员">
          <template #default="{row}">
            <el-tag v-for="m in (row.members || [])" :key="m" size="small" style="margin: 2px">{{ m }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="current_oncall" label="当前值班人" width="110" />
        <el-table-column label="周期开始" width="170">
          <template #default="{row}">
            {{ formatTime(row.current_period_start) }}
          </template>
        </el-table-column>
        <el-table-column label="周期结束" width="170">
          <template #default="{row}">
            {{ formatTime(row.current_period_end) }}
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{row}">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{row}">
            <el-button size="small" @click="showEditDialog(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="deleteOncall(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑值班表' : '新建值班表'" width="560px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="团队名" prop="team_name">
          <el-input v-model="form.team_name" placeholder="如: 运维组" />
        </el-form-item>
        <el-form-item label="轮值方式" prop="rotation_type">
          <el-radio-group v-model="form.rotation_type" @change="autoPeriodEnd">
            <el-radio label="weekly">周轮值</el-radio>
            <el-radio label="monthly">月轮值</el-radio>
          </el-radio-group>
          <div class="hint">选择后自动按周期长度计算结束时间</div>
        </el-form-item>
        <el-form-item label="成员" prop="members">
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
        <el-form-item label="当前值班人" prop="current_oncall">
          <el-select v-model="form.current_oncall" placeholder="选择当前值班人" filterable>
            <el-option v-for="m in form.members" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
        <el-form-item label="周期开始" prop="current_period_start">
          <el-date-picker v-model="form.current_period_start" type="date" value-format="YYYY-MM-DD" @change="autoPeriodEnd" style="width: 100%" />
        </el-form-item>
        <el-form-item label="周期结束" prop="current_period_end">
          <el-date-picker v-model="form.current_period_end" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
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
import { ref, onMounted, reactive, computed, watch } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import axios from "axios"

const oncallList = ref([])
const currentOncall = ref({})
const memberCandidates = ref([])
const dialogVisible = ref(false)
const editingId = ref(null)
const loading = ref(false)
const formRef = ref(null)
const form = reactive({
  team_name: "",
  rotation_type: "weekly",
  members: [],
  current_oncall: "",
  current_period_start: new Date().toISOString().slice(0, 10),
  current_period_end: ""
})

const currentItems = computed(() => currentOncall.value.items || [])

const rules = {
  team_name: [{ required: true, message: "请输入团队名", trigger: "blur" }],
  rotation_type: [{ required: true, message: "请选择轮值方式", trigger: "change" }],
  members: [{ required: true, type: "array", min: 1, message: "请至少添加一名成员", trigger: "change" }],
  current_oncall: [
    { required: true, message: "请选择当前值班人", trigger: "change" },
    {
      validator: (rule, value, callback) => {
        if (value && form.members.length && !form.members.includes(value)) {
          callback(new Error("当前值班人必须在成员列表中"))
        } else {
          callback()
        }
      },
      trigger: "change"
    }
  ],
  current_period_start: [{ required: true, message: "请选择周期开始", trigger: "change" }],
  current_period_end: [
    { required: true, message: "请选择周期结束", trigger: "change" },
    {
      validator: (rule, value, callback) => {
        if (value && form.current_period_start && new Date(value) <= new Date(form.current_period_start)) {
          callback(new Error("周期结束必须晚于开始"))
        } else {
          callback()
        }
      },
      trigger: "change"
    }
  ]
}

watch(() => form.members, (val) => {
  if (form.current_oncall && val.length && !val.includes(form.current_oncall)) {
    form.current_oncall = ""
  }
}, { deep: true })

const autoPeriodEnd = () => {
  if (!form.current_period_start) return
  const step = form.rotation_type === "weekly" ? 7 : 30
  const start = new Date(form.current_period_start)
  if (isNaN(start.getTime())) return
  const end = new Date(start.getTime() + step * 86400000)
  form.current_period_end = end.toISOString().slice(0, 10)
}

const buildSchedule = () => {
  if (!form.current_period_start) return []
  const start = new Date(form.current_period_start)
  if (isNaN(start.getTime())) return []
  const step = form.rotation_type === "weekly" ? 7 : 30
  const dayMs = 86400000
  return form.members.map((m, i) => ({
    order: i,
    name: m,
    start: new Date(start.getTime() + i * step * dayMs).toISOString().slice(0, 10),
    end: new Date(start.getTime() + (i + 1) * step * dayMs).toISOString().slice(0, 10)
  }))
}

const loadData = async () => {
  loading.value = true
  try {
    const res = await axios.get("/api/sre/oncall")
    oncallList.value = res.data
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
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
  form.current_period_start = new Date().toISOString().slice(0, 10)
  autoPeriodEnd()
  loadMemberCandidates()
  dialogVisible.value = true
  formRef.value?.clearValidate()
}

const showEditDialog = (row) => {
  editingId.value = row.id
  form.team_name = row.team_name
  form.rotation_type = row.rotation_type
  form.members = [...(row.members || [])]
  form.current_oncall = row.current_oncall
  form.current_period_start = row.current_period_start ? new Date(row.current_period_start).toISOString().slice(0, 10) : ""
  form.current_period_end = row.current_period_end ? new Date(row.current_period_end).toISOString().slice(0, 10) : ""
  loadMemberCandidates()
  dialogVisible.value = true
  formRef.value?.clearValidate()
}

const saveOncall = async () => {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch (e) {
    ElMessage.warning("请完善表单必填项")
    return
  }
  try {
    const payload = {
      team_name: form.team_name,
      rotation_type: form.rotation_type,
      members: form.members,
      schedule: buildSchedule(),
      current_oncall: form.current_oncall,
      current_period_start: form.current_period_start,
      current_period_end: form.current_period_end
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
    loadCurrentOncall()
    loadMemberCandidates()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || "保存失败")
  }
}

const deleteOncall = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除值班表「${row.team_name}」吗？`, "提示", { type: "warning" })
    await axios.delete(`/api/sre/oncall/${row.id}`)
    ElMessage.success("删除成功")
    loadData()
    loadCurrentOncall()
    loadMemberCandidates()
  } catch (e) {
    if (e !== "cancel") ElMessage.error(e?.response?.data?.detail || "删除失败")
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
