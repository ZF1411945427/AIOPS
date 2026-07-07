<template>
    <view class="page-wrap">
        <view class="card">
            <text class="section-title">运维工具</text>
            <view class="tool-grid">
                <view class="tool-item" @tap="goLogs">
                    <view class="tool-icon blue">📋</view>
                    <text class="tool-name">日志搜索</text>
                    <text class="tool-desc">关键词检索服务器日志</text>
                </view>
                <view class="tool-item" @tap="goMetrics">
                    <view class="tool-icon green">📊</view>
                    <text class="tool-name">指标监控</text>
                    <text class="tool-desc">查看 CPU/内存等指标趋势</text>
                </view>
                <view class="tool-item" @tap="goIncidents">
                    <view class="tool-icon orange">🚨</view>
                    <text class="tool-name">故障单管理</text>
                    <text class="tool-desc">查看和处理事件故障单</text>
                </view>
                <view class="tool-item" @tap="goScan">
                    <view class="tool-icon purple">📷</view>
                    <text class="tool-name">扫码识别</text>
                    <text class="tool-desc">扫描二维码定位资产</text>
                </view>
                <view class="tool-item" @tap="goWorkflow">
                    <view class="tool-icon teal">⚙️</view>
                    <text class="tool-name">工作流</text>
                    <text class="tool-desc">查看 SOP/Agent 运行状态</text>
                </view>
                <view class="tool-item" @tap="goOncall">
                    <view class="tool-icon pink">📞</view>
                    <text class="tool-name">我的值班</text>
                    <text class="tool-desc">值班排班与交接</text>
                </view>
            </view>
        </view>
    </view>
</template>

<script setup>
function goLogs() { uni.navigateTo({ url: '/pages/logs/index' }) }
function goMetrics() { uni.navigateTo({ url: '/pages/metrics/index' }) }
function goIncidents() { uni.navigateTo({ url: '/pages/incident/index' }) }
function goScan() { uni.navigateTo({ url: '/pages/asset/scan' }) }
function goWorkflow() { uni.navigateTo({ url: '/pages/workflow/list' }) }
function goOncall() { uni.navigateTo({ url: '/pages/oncall/my' }) }
</script>

<style lang="scss" scoped>
.section-title {
    font-size: $font-lg; font-weight: 600; color: $text; display: block; margin-bottom: 24rpx;
}
.tool-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 20rpx;
}
.tool-item {
    background: $bg; border-radius: $card-radius; padding: 28rpx 20rpx;
    display: flex; flex-direction: column; align-items: center; text-align: center;
}
.tool-icon {
    width: 88rpx; height: 88rpx; line-height: 88rpx; text-align: center;
    border-radius: 50%; font-size: 40rpx; margin-bottom: 16rpx;
}
.tool-icon.blue { background: rgba($primary, 0.12); }
.tool-icon.green { background: rgba($success, 0.12); }
.tool-icon.orange { background: rgba($warning, 0.12); }
.tool-icon.purple { background: rgba(139, 92, 246, 0.12); }
.tool-icon.teal { background: rgba(20, 184, 166, 0.12); }
.tool-icon.pink { background: rgba(236, 72, 153, 0.12); }
.tool-name {
    font-size: $font-sm; font-weight: 600; color: $text; margin-bottom: 8rpx;
}
.tool-desc {
    font-size: $font-xs; color: $text-muted; line-height: 1.4;
}
</style>
