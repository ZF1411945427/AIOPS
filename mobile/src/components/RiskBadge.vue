<template>
  <view class="risk-badge" :class="'lvl-' + level">
    <text class="risk-text">{{ text }}</text>
  </view>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  level: { type: String, default: 'low' },
})

const text = computed(() => {
  const m = { critical: '极高危', high: '高风险', medium: '中风险', low: '低风险' }
  return m[props.level] || props.level
})
</script>

<style lang="scss" scoped>
.risk-badge {
  display: inline-flex;
  align-items: center;
  padding: 4rpx 16rpx;
  border-radius: 12rpx;
}

.risk-text {
  font-size: $font-xs;
  font-weight: 600;
  color: #ffffff;
  line-height: 1.4;
}

.lvl-critical { background: #7C1D1D; }
.lvl-high { background: $risk-high; }
.lvl-medium { background: $risk-medium; }
.lvl-low { background: $risk-low; }
</style>
