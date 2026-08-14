<template>
  <div class="ai-assistant-tabs">
    <el-tabs v-model="activeTab" class="agent-tabs">
      <el-tab-pane label="智能助手" name="chat">
        <AgentChatView />
      </el-tab-pane>
      <el-tab-pane label="待确认动作" name="pending">
        <PendingActionsView />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import AgentChatView from '@/views/AgentChatView.vue'
import PendingActionsView from '@/views/PendingActionsView.vue'

const activeTab = ref('chat')
</script>

<style scoped>
.ai-assistant-tabs {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.agent-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.agent-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: auto;
}
.agent-tabs :deep(.el-tab-pane) {
  height: 100%;
}
.agent-tabs :deep(.el-tabs__header) {
  margin-bottom: 8px;
}
</style>
