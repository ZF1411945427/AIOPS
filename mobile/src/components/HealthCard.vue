<template>
  <view class="health-card">
    <view class="health-main">
      <view class="score-row">
        <text class="score-num">{{ score }}</text>
        <text class="score-unit">分</text>
        <view class="trend" :class="trendDir">
          <text class="trend-arrow">{{ trend === 'up' ? '↑' : trend === 'down' ? '↓' : '—' }}</text>
          <text v-if="trendValue" class="trend-val">{{ trendValue }}</text>
        </view>
      </view>
      <text class="health-label">系统健康分</text>
    </view>
    <view class="health-sub">
      <view class="sub-item">
        <text class="sub-val">{{ onlineCount }}</text>
        <text class="sub-label">在线资产</text>
      </view>
      <view class="sub-divider"></view>
      <view class="sub-item">
        <text class="sub-val">{{ totalCount }}</text>
        <text class="sub-label">总资产数</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  score: { type: [Number, String], default: 0 },
  trend: { type: String, default: '' },
  trendValue: { type: [Number, String], default: '' },
  onlineCount: { type: [Number, String], default: 0 },
  totalCount: { type: [Number, String], default: 0 },
})

const trendDir = computed(() => {
  if (props.trend === 'up') return 'trend-up'
  if (props.trend === 'down') return 'trend-down'
  return 'trend-flat'
})
</script>

<style lang="scss" scoped>
.health-card {
  background: $bg-card-solid;
  border-radius: $card-radius;
  padding: 40rpx 32rpx;
  box-shadow: $card-shadow;
  margin-bottom: 24rpx;
}

.health-main {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 32rpx;
}

.score-row {
  display: flex;
  flex-direction: row;
  align-items: baseline;
}

.score-num {
  font-size: $font-xxl;
  font-weight: 700;
  color: $text;
  line-height: 1;
}

.score-unit {
  font-size: $font-md;
  color: $text-muted;
  margin-left: 8rpx;
}

.trend {
  display: flex;
  flex-direction: row;
  align-items: center;
  margin-left: 16rpx;
  padding: 4rpx 12rpx;
  border-radius: 12rpx;
}

.trend-up { background: rgba($success, 0.1); }
.trend-up .trend-arrow, .trend-up .trend-val { color: $success; }

.trend-down { background: rgba($danger, 0.1); }
.trend-down .trend-arrow, .trend-down .trend-val { color: $danger; }

.trend-flat { background: rgba($text-muted, 0.1); }
.trend-flat .trend-arrow, .trend-flat .trend-val { color: $text-muted; }

.trend-arrow {
  font-size: $font-md;
  font-weight: 600;
}

.trend-val {
  font-size: $font-xs;
  margin-left: 4rpx;
}

.health-label {
  font-size: $font-sm;
  color: $text-muted;
  margin-top: 12rpx;
}

.health-sub {
  display: flex;
  flex-direction: row;
  justify-content: center;
  align-items: center;
}

.sub-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
}

.sub-val {
  font-size: $font-xl;
  font-weight: 600;
  color: $primary;
}

.sub-label {
  font-size: $font-xs;
  color: $text-muted;
  margin-top: 8rpx;
}

.sub-divider {
  width: 2rpx;
  height: 60rpx;
  background: $border;
}
</style>
