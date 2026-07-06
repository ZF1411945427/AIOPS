<template>
  <view class="alert-card" :class="'sev-' + severity" @click="onClick">
    <view class="sev-bar"></view>
    <view class="card-body">
      <view class="card-header">
        <text class="alert-title">{{ alert.metric_name || alert.title || '告警' }}</text>
        <text class="status-badge" :class="'st-' + (alert.status || 'triggered')">{{ statusText }}</text>
      </view>
      <text v-if="alert.asset_name" class="alert-asset">{{ alert.asset_name }}</text>
      <text v-if="alert.message" class="alert-msg">{{ alert.message }}</text>
      <text class="alert-time">{{ alert.created_at || '' }}</text>
    </view>
  </view>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  alert: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['click'])

const severity = computed(() => props.alert.severity || 'low')

const statusText = computed(() => {
  const m = { triggered: '待处理', acknowledged: '已确认', resolved: '已恢复', suppressed: '已静默' }
  return m[props.alert.status] || props.alert.status || '待处理'
})

function onClick() {
  emit('click', props.alert)
}
</script>

<style lang="scss" scoped>
.alert-card {
  display: flex;
  flex-direction: row;
  background: $bg-card-solid;
  border-radius: $card-radius;
  overflow: hidden;
  margin-bottom: 24rpx;
  box-shadow: $card-shadow;
}

.sev-bar {
  width: 8rpx;
  flex-shrink: 0;
}

.sev-critical .sev-bar { background: $severity-critical; }
.sev-high .sev-bar { background: $severity-high; }
.sev-medium .sev-bar { background: $severity-medium; }
.sev-low .sev-bar { background: $severity-low; }
.sev-info .sev-bar { background: $severity-info; }

.card-body {
  flex: 1;
  padding: 28rpx 32rpx;
  display: flex;
  flex-direction: column;
}

.card-header {
  display: flex;
  flex-direction: row;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12rpx;
}

.alert-title {
  font-size: $font-md;
  font-weight: 600;
  color: $text;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-badge {
  font-size: $font-xs;
  padding: 4rpx 16rpx;
  border-radius: 20rpx;
  color: #fff;
  flex-shrink: 0;
  margin-left: 16rpx;
}

.st-triggered { background: $status-triggered; }
.st-acknowledged { background: $status-acknowledged; }
.st-resolved { background: $status-resolved; }
.st-suppressed { background: $status-suppressed; }

.alert-asset {
  font-size: $font-sm;
  color: $text-secondary;
  margin-bottom: 8rpx;
}

.alert-msg {
  font-size: $font-sm;
  color: $text-secondary;
  line-height: 1.5;
  margin-bottom: 12rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.alert-time {
  font-size: $font-xs;
  color: $text-muted;
}
</style>
