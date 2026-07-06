<template>
  <view class="chat-row" :class="role">
    <view class="bubble" :class="role">
      <view v-if="role === 'assistant'" class="avatar">AI</view>
      <view class="bubble-content">
        <view class="text-content">
          <text v-for="(seg, i) in segments" :key="i">
            <text v-if="seg.type === 'bold'" class="md-bold">{{ seg.text }}</text>
            <text v-else-if="seg.type === 'code'" class="md-code">{{ seg.text }}</text>
            <text v-else class="md-text">{{ seg.text }}</text>
          </text>
        </view>
        <view v-if="toolCalls && toolCalls.length" class="tool-calls">
          <view v-for="(tc, idx) in toolCalls" :key="tc.id || (tc.name + '-' + idx)" class="tool-card">
            <view class="tool-header">
              <text class="tool-icon">🔧</text>
              <text class="tool-name">{{ tc.name || tc.tool || '工具调用' }}</text>
            </view>
            <text v-if="tc.args || tc.arguments" class="tool-args">{{ tc.args || tc.arguments }}</text>
            <text v-if="tc.result" class="tool-result">{{ tc.result }}</text>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  role: { type: String, default: 'assistant' },
  content: { type: String, default: '' },
  toolCalls: { type: Array, default: () => [] },
})

const segments = computed(() => {
  if (!props.content) return []
  const segs = []
  const lines = props.content.split('\n')
  lines.forEach((line, lineIdx) => {
    const parts = line.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
    for (const p of parts) {
      if (!p) continue
      if (p.startsWith('**') && p.endsWith('**')) {
        segs.push({ type: 'bold', text: p.slice(2, -2) })
      } else if (p.startsWith('`') && p.endsWith('`')) {
        segs.push({ type: 'code', text: p.slice(1, -1) })
      } else if (p) {
        segs.push({ type: 'text', text: p })
      }
    }
    if (lineIdx < lines.length - 1) {
      segs.push({ type: 'text', text: '\n' })
    }
  })
  return segs
})
</script>

<style lang="scss" scoped>
.chat-row {
  display: flex;
  flex-direction: row;
  margin-bottom: 24rpx;
  padding: 0 24rpx;
}

.chat-row.user {
  justify-content: flex-end;
}

.chat-row.assistant {
  justify-content: flex-start;
}

.bubble {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  max-width: 600rpx;
}

.bubble.assistant {
  background: $bg-card-solid;
  border-radius: 24rpx 24rpx 24rpx 8rpx;
  padding: 24rpx;
  box-shadow: $card-shadow;
}

.bubble.user {
  background: $primary;
  border-radius: 24rpx 24rpx 8rpx 24rpx;
  padding: 24rpx;
}

.avatar {
  width: 56rpx;
  height: 56rpx;
  border-radius: 50%;
  background: $primary;
  color: #fff;
  font-size: $font-xs;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-right: 16rpx;
}

.bubble-content {
  flex: 1;
  min-width: 0;
}

.text-content {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
}

.md-text {
  font-size: $font-md;
  line-height: 1.6;
  color: $text;
}

.bubble.user .md-text {
  color: #ffffff;
}

.md-bold {
  font-size: $font-md;
  font-weight: 700;
  color: $text;
}

.bubble.user .md-bold {
  color: #ffffff;
}

.md-code {
  font-size: $font-sm;
  font-family: monospace;
  background: $bg-card;
  color: $primary;
  padding: 2rpx 8rpx;
  border-radius: 6rpx;
}

.bubble.user .md-code {
  background: rgba(255, 255, 255, 0.2);
  color: #ffffff;
}

.tool-calls {
  margin-top: 16rpx;
}

.tool-card {
  background: $bg-card;
  border-radius: 16rpx;
  padding: 20rpx;
  margin-bottom: 12rpx;
  border-left: 6rpx solid $primary;
}

.tool-header {
  display: flex;
  flex-direction: row;
  align-items: center;
  margin-bottom: 8rpx;
}

.tool-icon {
  font-size: $font-sm;
  margin-right: 8rpx;
}

.tool-name {
  font-size: $font-sm;
  font-weight: 600;
  color: $text;
}

.tool-args {
  display: block;
  font-size: $font-xs;
  color: $text-secondary;
  font-family: monospace;
  margin-bottom: 8rpx;
  word-break: break-all;
}

.tool-result {
  display: block;
  font-size: $font-xs;
  color: $success;
  font-family: monospace;
  word-break: break-all;
}
</style>
