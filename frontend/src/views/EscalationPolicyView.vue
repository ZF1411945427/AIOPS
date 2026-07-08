<template>
  <div class="escalation-policy">
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="title">升级策略管理</span>
          <div>
            <button class="btn btn-guide" @click="showGuide = !showGuide">📖 操作说明</button>
            <el-button type="primary" @click="showCreateDialog">+ 新建策略</el-button>
          </div>
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

    <GuideDrawer v-model="showGuide" title="📖 升级策略 · 概念说明">
      <section class="guide-section">
        <h4>1. 什么是升级策略？</h4>
        <p><strong>升级策略（Escalation Policy）</strong>定义了：当告警发生且没人处理时，<strong>事情会如何一步步升级</strong>，直到有人响应为止。</p>
        <p>简单的说就是：<strong>L1 没人看 → 找 L2 → L2 也没看 → 找 L3 → ...</strong></p>
      </section>
      <section class="guide-section">
        <h4>2. 升级流程示例</h4>
        <p>一条典型的升级链：</p>
        <div class="guide-code" style="color:#e2e8f0; padding:10px 14px; margin:6px 0;">
告警触发
  ↓ (等待 5 分钟)
L1 值班人收到短信通知
  ↓ (5 分钟内未确认)
L2 技术主管收到电话通知
  ↓ (15 分钟内未确认)
L3 运维经理收到电话 + 邮件通知
  ↓ (30 分钟内未确认)
L4 总监 → 启动应急响应流程
        </div>
      </section>
      <section class="guide-section">
        <h4>3. 三个关键配置</h4>
        <div class="key-value-list">
          <div class="kv-row">
            <span class="kv-key">升级级别</span>
            <span class="kv-val">定义了哪些角色参与（如 L1=值班工程师, L2=技术主管, L3=运维经理）。级别越高，处理问题的人资历越深（但也越贵、人数越少）</span>
          </div>
          <div class="kv-row">
            <span class="kv-key">等待时间</span>
            <span class="kv-val">在每个级别等待多久。通常在 L1 等短一点（5分钟），L2 等长一点（15分钟）。等待时间决定了"多快能联系到人"</span>
          </div>
          <div class="kv-row">
            <span class="kv-key">通知渠道</span>
            <span class="kv-val">不同级别用不同渠道通知。L1 用短信/App 推送（便宜但容易错过），L3 用电话（成本高但必达）</span>
          </div>
        </div>
      </section>
      <section class="guide-section">
        <h4>4. 为什么要设计升级策略？</h4>
        <ul>
          <li><strong>避免告警无人处理</strong> — 值班人可能在忙/睡觉/没信号</li>
          <li><strong>确保及时响应</strong> — 升级链保证事情总有人兜底</li>
          <li><strong>分层处理</strong> — 简单问题 L1 解决，复杂问题升级到更专业的人</li>
          <li><strong>可审计</strong> — 每次升级都有记录，方便事后复盘</li>
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
