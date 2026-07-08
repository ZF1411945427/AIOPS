<template>
  <div class="burn-rate">
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="title">预算消耗速率</span>
          <div>
            <button class="btn btn-guide" @click="showGuide = !showGuide">📖 操作说明</button>
            <el-button type="primary" @click="loadData">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="burnRates" stripe>
        <el-table-column prop="service_name" label="服务名" />
        <el-table-column prop="slo_target" label="SLO 目标">
          <template #default="{row}">{{ (row.slo_target * 100).toFixed(2) }}%</template>
        </el-table-column>
        <el-table-column prop="error_budget_total" label="总预算(%)" />
        <el-table-column prop="error_budget_remaining" label="剩余(%)">
          <template #default="{row}">
            <el-tag :type="row.error_budget_remaining > 50 ? 'success' : row.error_budget_remaining > 20 ? 'warning' : 'danger'">
              {{ row.error_budget_remaining.toFixed(2) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="burn_rate_1h" label="1h 消耗率" />
        <el-table-column prop="burn_rate_6h" label="6h 消耗率" />
        <el-table-column prop="burn_rate_24h" label="24h 消耗率" />
        <el-table-column prop="status" label="状态">
          <template #default="{row}">
            <el-tag :type="row.status === 'healthy' ? 'success' : row.status === 'warning' ? 'warning' : 'danger'">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <GuideDrawer v-model="showGuide" title="📖 消耗速率 · 概念说明">
      <section class="guide-section">
        <h4>1. 什么是 Burn Rate（消耗速率）？</h4>
        <p><strong>Burn Rate</strong> 表示你的错误预算正在以多快的速度被"烧掉"。</p>
        <div class="formula">Burn Rate = 实际消耗速度 / 理想消耗速度</div>
        <ul>
          <li><strong>Burn Rate = 1</strong> — 恰好以预期速度消耗，刚好能用满整个窗口期</li>
          <li><strong>Burn Rate > 1</strong> — 消耗过快！比如 1h 消耗率为 2.5，说明过去 1 小时的错误量是预期的 2.5 倍</li>
          <li><strong>Burn Rate &lt; 1</strong> — 消耗较慢，服务比预期更稳定</li>
        </ul>
      </section>
      <section class="guide-section">
        <h4>2. 为什么有三个时间窗口？</h4>
        <div class="key-value-list">
          <div class="kv-row"><span class="kv-key">1h 消耗率</span><span class="kv-val">检测<strong>突发</strong>异常，比如瞬间流量飙升、服务突然挂掉。如果 1h 消耗率很高，说明现在出了大问题</span></div>
          <div class="kv-row"><span class="kv-key">6h 消耗率</span><span class="kv-val">检测<strong>持续</strong>异常，比如慢查询导致请求逐渐失败</span></div>
          <div class="kv-row"><span class="kv-key">24h 消耗率</span><span class="kv-val">检测<strong>长期趋势</strong>，排除短时波动，看整体健康度</span></div>
        </div>
        <div class="tip-box">💡 三个窗口一起看，能快速区分"突发故障"和"慢性问题"：<br>
        1h 高但 24h 正常 → 刚出的故障，赶紧处理；<br>
        1h/6h/24h 都高 → 系统已经出问题很久了！</div>
      </section>
      <section class="guide-section">
        <h4>3. 如何判断严重程度？</h4>
        <ul>
          <li><strong>剩余预算 > 50%</strong> → 正常 <span class="tag-demo" style="background:rgba(16,185,129,0.12);color:#10b981;">healthy</span></li>
          <li><strong>剩余预算 20%~50%</strong> → 需要关注 <span class="tag-demo" style="background:rgba(245,158,11,0.12);color:#d97706;">warning</span></li>
          <li><strong>剩余预算 &lt; 20%</strong> → 危险 <span class="tag-demo" style="background:rgba(239,68,68,0.12);color:#ef4444;">critical</span></li>
        </ul>
        <p>消耗率高 + 剩余少 = 需要<strong>立即响应</strong>的紧急情况。</p>
      </section>
    </GuideDrawer>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue"
import axios from "axios"
import GuideDrawer from '@/components/GuideDrawer.vue'

const showGuide = ref(false)
const burnRates = ref([])

const loadData = async () => {
  try {
    const res = await axios.get("/api/sre/burn-rate")
    burnRates.value = res.data
  } catch (e) {
    console.error(e)
  }
}

onMounted(loadData)
</script>

<style scoped>
.burn-rate { padding: 20px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.title { font-size: 18px; font-weight: bold; }
</style>
