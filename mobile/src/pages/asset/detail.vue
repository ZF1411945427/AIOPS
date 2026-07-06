<template>
    <view class="page-wrap">
        <view v-if="loading" class="loading-state">
            <text class="text-muted">加载中...</text>
        </view>

        <template v-if="asset">
            <view class="card">
                <view class="flex-between">
                    <text class="asset-name">{{ asset.name || '-' }}</text>
                    <view class="status-dot" :class="online ? 'online' : 'offline'">
                        <text class="status-text">{{ online ? '在线' : '离线' }}</text>
                    </view>
                </view>
                <view class="info-grid">
                    <view class="info-row">
                        <text class="info-label">类型</text>
                        <text class="info-value">{{ asset.ci_type || asset.type || '-' }}</text>
                    </view>
                    <view class="info-row">
                        <text class="info-label">IP 地址</text>
                        <text class="info-value">{{ asset.ip || asset.address || '-' }}</text>
                    </view>
                    <view class="info-row">
                        <text class="info-label">状态</text>
                        <text class="info-value">{{ asset.status || '-' }}</text>
                    </view>
                    <view class="info-row">
                        <text class="info-label">环境</text>
                        <text class="info-value">{{ asset.environment || '-' }}</text>
                    </view>
                </view>
                <view v-if="asset.tags && asset.tags.length" class="tag-row">
                    <view v-for="(tag, idx) in asset.tags" :key="idx" class="tag">
                        <text class="tag-text">{{ tag }}</text>
                    </view>
                </view>
            </view>

            <view class="card">
                <text class="card-title">最近告警</text>
                <view v-if="recentAlerts.length === 0" class="empty-mini">
                    <text class="text-muted">暂无告警</text>
                </view>
                <view v-for="al in recentAlerts" :key="al.id" class="alert-mini" @tap="goAlert(al.id)">
                    <view class="sev-dot" :class="'sev-' + (al.severity || 'low')"></view>
                    <text class="alert-mini-name">{{ al.name || al.message }}</text>
                    <text class="alert-mini-time">{{ al.created_at || '' }}</text>
                </view>
            </view>

            <view class="card">
                <text class="card-title">快捷操作</text>
                <view class="quick-grid">
                    <view class="quick-item" @tap="goScript">
                        <text class="quick-icon">脚本</text>
                        <text class="quick-label">远程脚本</text>
                    </view>
                    <view class="quick-item" @tap="goMetrics">
                        <text class="quick-icon">指标</text>
                        <text class="quick-label">查看指标</text>
                    </view>
                    <view class="quick-item" @tap="goRestart">
                        <text class="quick-icon">重启</text>
                        <text class="quick-label">重启服务</text>
                    </view>
                    <view class="quick-item" @tap="goDiagnose">
                        <text class="quick-icon">AI</text>
                        <text class="quick-label">AI诊断</text>
                    </view>
                </view>
            </view>
        </template>
    </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getAssetDetail } from '@/api/asset.js'
import { getList } from '@/api/alert.js'

const asset = ref(null)
const recentAlerts = ref([])
const loading = ref(true)

const online = computed(() => {
    const s = (asset.value && (asset.value.status || asset.value.health_status || '')).toLowerCase()
    return s === 'online' || s === 'up' || s === 'healthy'
})

async function fetchDetail(id) {
    loading.value = true
    try {
        const data = await getAssetDetail(id)
        asset.value = data.asset || data
        await fetchRecentAlerts(id)
    } catch (e) {
        uni.showToast({ title: '加载失败', icon: 'none' })
    } finally {
        loading.value = false
    }
}

async function fetchRecentAlerts(assetId) {
    try {
        const data = await getList({ per_page: 100 })
        const items = data.alerts || data.items || []
        const arr = Array.isArray(items) ? items : []
        recentAlerts.value = arr
            .filter((a) => String(a.asset_id) === String(assetId))
            .slice(0, 5)
    } catch (e) {
        recentAlerts.value = []
    }
}

function goAlert(id) {
    uni.navigateTo({ url: '/pages/alert/detail?id=' + id })
}

function goScript() {
    uni.showToast({ title: '请前往 Web 端执行', icon: 'none' })
}

function goMetrics() {
    uni.showToast({ title: '指标视图开发中', icon: 'none' })
}

function goRestart() {
    uni.showModal({
        title: '重启服务',
        content: '确认重启该资产上的服务？',
        success: (r) => {
            if (r.confirm) uni.showToast({ title: '已提交', icon: 'success' })
        },
    })
}

function goDiagnose() {
    const id = asset.value && asset.value.id
    uni.navigateTo({ url: '/pages/asset/diagnose?assetId=' + id })
}

onLoad((opts) => {
    if (opts && opts.id) fetchDetail(opts.id)
})
</script>

<style lang="scss" scoped>

.loading-state {
    padding: 120rpx 0;
    text-align: center;
}

.asset-name {
    font-size: $font-xl;
    font-weight: 700;
    color: $text;
    flex: 1;
    margin-right: 16rpx;
}

.status-dot {
    display: flex;
    align-items: center;
    padding: 8rpx 20rpx;
    border-radius: 24rpx;
}
.status-dot.online { background: rgba($success, 0.12); }
.status-dot.offline { background: rgba($text-muted, 0.12); }

.status-dot::before {
    content: '';
    width: 16rpx;
    height: 16rpx;
    border-radius: 50%;
    margin-right: 12rpx;
}
.status-dot.online::before { background: $success; }
.status-dot.offline::before { background: $text-muted; }

.status-text {
    font-size: $font-xs;
}
.status-dot.online .status-text { color: $success; }
.status-dot.offline .status-text { color: $text-muted; }

.info-grid {
    margin-top: 24rpx;
}

.info-row {
    display: flex;
    justify-content: space-between;
    padding: 16rpx 0;
    border-bottom: 2rpx solid $border;
}

.info-label {
    font-size: $font-sm;
    color: $text-muted;
}

.info-value {
    font-size: $font-sm;
    color: $text;
}

.tag-row {
    display: flex;
    flex-wrap: wrap;
    gap: 16rpx;
    margin-top: 24rpx;
}

.tag {
    padding: 8rpx 20rpx;
    background: $bg-card;
    border-radius: 20rpx;
}

.tag-text {
    font-size: $font-xs;
    color: $text-secondary;
}

.card-title {
    font-size: $font-md;
    font-weight: 600;
    color: $text;
    display: block;
    margin-bottom: 24rpx;
}

.empty-mini {
    padding: 32rpx 0;
    text-align: center;
    font-size: $font-sm;
}

.alert-mini {
    display: flex;
    align-items: center;
    padding: 20rpx 0;
    border-bottom: 2rpx solid $border;
}

.sev-dot {
    width: 16rpx;
    height: 16rpx;
    border-radius: 50%;
    margin-right: 16rpx;
    flex-shrink: 0;
}
.sev-critical { background: $severity-critical; }
.sev-high { background: $severity-high; }
.sev-medium { background: $severity-medium; }
.sev-low { background: $severity-low; }

.alert-mini-name {
    flex: 1;
    font-size: $font-sm;
    color: $text;
}

.alert-mini-time {
    font-size: $font-xs;
    color: $text-muted;
}

.quick-grid {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
}

.quick-item {
    width: 48%;
    background: $bg-card;
    border-radius: 16rpx;
    padding: 28rpx 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    margin-bottom: 20rpx;
}

.quick-icon {
    width: 80rpx;
    height: 80rpx;
    line-height: 80rpx;
    text-align: center;
    background: $primary;
    color: #fff;
    border-radius: 50%;
    font-size: $font-sm;
    margin-bottom: 16rpx;
}

.quick-label {
    font-size: $font-sm;
    color: $text;
}
</style>
