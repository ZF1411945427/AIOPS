<template>
  <view class="scan-fab" @click="onClick">
    <view class="fab-icon">
      <view class="icon-corner tl"></view>
      <view class="icon-corner tr"></view>
      <view class="icon-corner bl"></view>
      <view class="icon-corner br"></view>
      <view class="icon-line"></view>
    </view>
  </view>
</template>

<script setup>
const emit = defineEmits(['click'])

function onClick() {
  emit('click')
}
</script>

<style lang="scss" scoped>
.scan-fab {
  position: fixed;
  right: 40rpx;
  bottom: 120rpx;
  width: 112rpx;
  height: 112rpx;
  border-radius: 50%;
  background: $primary;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8rpx 24rpx rgba(59, 130, 246, 0.4);
  z-index: 999;
}

.fab-icon {
  width: 56rpx;
  height: 56rpx;
  position: relative;
}

.icon-corner {
  position: absolute;
  width: 16rpx;
  height: 16rpx;
  border: 4rpx solid #ffffff;
}

.icon-corner.tl {
  top: 0;
  left: 0;
  border-right: none;
  border-bottom: none;
}

.icon-corner.tr {
  top: 0;
  right: 0;
  border-left: none;
  border-bottom: none;
}

.icon-corner.bl {
  bottom: 0;
  left: 0;
  border-right: none;
  border-top: none;
}

.icon-corner.br {
  bottom: 0;
  right: 0;
  border-left: none;
  border-top: none;
}

.icon-line {
  position: absolute;
  left: 8rpx;
  right: 8rpx;
  top: 50%;
  height: 4rpx;
  background: #ffffff;
  transform: translateY(-50%);
}
</style>
