<template>
  <div class="burn-rate">
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="title">预算消耗速率</span>
          <el-button type="primary" @click="loadData">刷新</el-button>
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
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue"
import axios from "axios"

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
