<template>
  <div class="error-budget">
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="title">错误预算管理</span>
          <div>
            <button class="btn btn-guide" @click="showGuide = !showGuide">📖 操作说明</button>
            <el-button type="primary" @click="showCreateDialog">+ 新建 SLO</el-button>
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
import { ref, onMounted, reactive } from "vue"
import { ElMessage } from "element-plus"
import axios from "axios"
import GuideDrawer from '@/components/GuideDrawer.vue'

const showGuide = ref(false)
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
