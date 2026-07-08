<template>
  <div class="sla-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="title">SLA 协议管理</span>
          <div>
            <button class="btn btn-guide" @click="showGuide = !showGuide">📖 操作说明</button>
            <el-button type="primary" @click="showCreateDialog">+ 新建 SLA</el-button>
          </div>
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

    <GuideDrawer v-model="showGuide" title="📖 SLA · 概念说明">
      <section class="guide-section">
        <h4>1. 什么是 SLA？</h4>
        <p><strong>SLA</strong>（Service Level Agreement，服务级别协议）是你跟客户或业务方签订的<strong>正式合同</strong>，里面写明了"我保证这个服务达到什么水平，如果达不到，我承担什么后果"。</p>
        <div class="tip-box">💡 简单区分：<strong>SLO</strong> 是你给自己定的目标，<strong>SLA</strong> 是你对外签的合同。</div>
      </section>
      <section class="guide-section">
        <h4>2. SLO vs SLA 的核心区别</h4>
        <div class="key-value-list">
          <div class="kv-row">
            <span class="kv-key">SLO</span>
            <span class="kv-val"><strong>内部指标</strong>，技术团队自己定的目标。没达到→改进，没有赔偿。<br>例：我们团队希望支付服务可用性达到 99.95%</span>
          </div>
          <div class="kv-row">
            <span class="kv-key">SLA</span>
            <span class="kv-val"><strong>外部合同</strong>，对客户/业务的正式承诺。没达到→赔偿/罚款。<br>例：合同写支付服务可用性不低于 99.9%，否则退还 10% 月费</span>
          </div>
        </div>
        <p>一般 SLA 的目标会比 SLO 低一些（给自己留缓冲），内部先报警处理，避免触发 SLA 违约。</p>
      </section>
      <section class="guide-section">
        <h4>3. 可用性怎么算？</h4>
        <div class="formula">可用性 = 运行时间 / (运行时间 + 停机时间)</div>
        <p>例如：一个月（30天=2592000秒）内，服务停机了 2 小时（7200秒）：</p>
        <ul>
          <li>可用性 = (2592000 - 7200) / 2592000 = <strong>99.72%</strong></li>
          <li>如果 SLA 目标是 99.9%，那这个月就<strong>违约了</strong></li>
        </ul>
      </section>
      <section class="guide-section">
        <h4>4. 处罚等级</h4>
        <ul>
          <li><span class="tag-demo" style="background:rgba(16,185,129,0.12);color:#10b981;">无</span> — 未触发 SLA 违约，服务正常</li>
          <li><span class="tag-demo" style="background:rgba(245,158,11,0.12);color:#d97706;">警告</span> — 接近违约阈值，需关注</li>
          <li><span class="tag-demo" style="background:rgba(239,68,68,0.12);color:#ef4444;">处罚</span> — 已触发 SLA 违约，可能产生财务赔偿或商务影响</li>
        </ul>
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
