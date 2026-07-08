<template>
  <div class="slo-config">
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="title">SLO 配置管理</span>
          <div>
            <button class="btn btn-guide" @click="showGuide = !showGuide">📖 操作说明</button>
            <el-button type="primary" @click="showCreateDialog">+ 新建 SLO</el-button>
          </div>
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
        <el-table-column label="操作" width="140" fixed="right">
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

    <GuideDrawer v-model="showGuide" title="📖 SLO · 概念说明">
      <section class="guide-section">
        <h4>1. 什么是 SLO？</h4>
        <p><strong>SLO</strong>（Service Level Objective，服务级别目标）是你对服务<strong>可用性</strong>设定的一个目标值。比如 "这个服务要保证 99.9% 的时间是可用的"。</p>
        <p>SLO 是 SRE 体系的核心——没有 SLO，你就无法判断服务"够不够好"。</p>
      </section>
      <section class="guide-section">
        <h4>2. 目标可用性（几个9的含义）</h4>
        <p>可用性用百分数表示，9 的数量代表了可靠性等级：</p>
        <div class="key-value-list">
          <div class="kv-row"><span class="kv-key">90%（1个9）</span><span class="kv-val">每年允许停机 36.5 天——个人项目级别</span></div>
          <div class="kv-row"><span class="kv-key">99%（2个9）</span><span class="kv-val">每年允许停机 3.65 天——内部工具级别</span></div>
          <div class="kv-row"><span class="kv-key">99.9%（3个9）</span><span class="kv-val">每年允许停机 8.76 小时——一般商业服务</span></div>
          <div class="kv-row"><span class="kv-key">99.99%（4个9）</span><span class="kv-val">每年允许停机 52.6 分钟——关键业务</span></div>
          <div class="kv-row"><span class="kv-key">99.999%（5个9）</span><span class="kv-val">每年允许停机 5.26 分钟——电信级</span></div>
        </div>
        <div class="tip-box">💡 没有 100%——因为服务器会宕机、网络会抖动、代码有 Bug。SLO 的目标是找到一个<strong>成本与可靠性之间的平衡点</strong>。</div>
      </section>
      <section class="guide-section">
        <h4>3. 窗口（观测周期）</h4>
        <p><strong>窗口</strong>指 SLO 的观测周期（天）。窗口越长，数据越平稳，但发现问题的响应也越慢。</p>
        <p>典型配置：<code>30 天</code>（月度 SLO）、<code>7 天</code>（周度 SLO）。</p>
      </section>
      <section class="guide-section">
        <h4>4. 状态判定逻辑</h4>
        <p>SLO 的状态由<strong>错误消耗 vs 窗口期长度</strong>自动计算：</p>
        <ul>
          <li><span class="tag-demo" style="background:rgba(16,185,129,0.12);color:#10b981;">healthy</span> — 错误预算充足，服务正常</li>
          <li><span class="tag-demo" style="background:rgba(245,158,11,0.12);color:#d97706;">warning</span> — 错误消耗较快，需要关注</li>
          <li><span class="tag-demo" style="background:rgba(239,68,68,0.12);color:#ef4444;">critical</span> — 错误预算即将/已经耗尽，需要立即处理</li>
        </ul>
      </section>
      <section class="guide-section">
        <h4>5. SLO 与 SLA 的区别</h4>
        <p><strong>SLO</strong> 是技术团队对自己定的<strong>内部目标</strong>（想做到多少）。</p>
        <p><strong>SLA</strong> 是跟客户签的<strong>合同承诺</strong>（做不到要赔钱）。</p>
        <p>一般 SLA 的目标值比 SLO 更宽松，给自己留缓冲空间。</p>
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
