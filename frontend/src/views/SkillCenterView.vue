<template>
  <div class="skill-center">
    <div class="page-header">
      <h1>🧩 技能中心</h1>
      <p>技能库（SKILL.md 可执行技能 · 可被 Agent 调用）· 技能市场（私服打包 / 远程社区源）· 调用全程审计</p>
    </div>
    <el-tabs v-model="active" type="border-card" @tab-change="onTabChange">
      <el-tab-pane label="🧩 技能库" name="skills">
        <SkillsView v-if="active === 'skills'" />
      </el-tab-pane>
      <el-tab-pane label="🛍️ 技能市场" name="market">
        <MarketplaceView v-if="active === 'market'" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import SkillsView from '@/views/SkillsView.vue'
import MarketplaceView from '@/views/MarketplaceView.vue'

const active = ref('skills')

function onTabChange(name) {
  if (name === 'skills' || name === 'market') active.value = name
}
</script>

<style scoped>
.skill-center { padding: 20px; }
.page-header h1 { margin: 0 0 6px; }
.page-header p { color: #8b949e; margin: 0 0 16px; font-size: 13px; }
:deep(.el-tabs__content) { padding: 4px; }
</style>