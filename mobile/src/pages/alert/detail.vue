<template>
    <view class="page-wrap">
        <view v-if="loading" class="loading-state">
            <text class="text-muted">加载中...</text>
        </view>

        <template v-if="alert">
            <view class="card">
                <view class="flex-between">
                    <text class="alert-title">{{ alert.metric_name || alert.message || '告警' }}</text>
                    <view class="sev-badge" :class="'sev-' + (alert.severity || 'low')">
                        <text class="sev-text">{{ severityText(alert.severity) }}</text>
                    </view>
                </view>
                <view class="info-grid">
                    <view class="info-row">
                        <text class="info-label">指标</text>
                        <text class="info-value">{{ alert.metric_name || '-' }}</text>
                    </view>
                    <view class="info-row">
                        <text class="info-label">当前值</text>
                        <text class="info-value">{{ alert.actual_value != null ? alert.actual_value : '-' }}</text>
                    </view>
                    <view class="info-row">
                        <text class="info-label">阈值</text>
                        <text class="info-value">{{ alert.threshold != null ? alert.threshold : '-' }}</text>
                    </view>
                    <view class="info-row">
                        <text class="info-label">状态</text>
                        <text class="info-value">{{ statusText(alert.status) }}</text>
                    </view>
                    <view class="info-row">
                        <text class="info-label">资产</text>
                        <text class="info-value">{{ alert.asset_name || alert.asset_id || '-' }}</text>
                    </view>
                    <view class="info-row">
                        <text class="info-label">时间</text>
                        <text class="info-value">{{ alert.created_at || '-' }}</text>
                    </view>
                </view>
                <view v-if="alert.message" class="msg-box">
                    <text class="msg-text">{{ alert.message }}</text>
                </view>
            </view>

            <view class="card">
                <view class="card-title">处置操作</view>
                <view class="action-grid">
                    <button class="action-btn ack" @tap="handleAck">确认告警</button>
                    <button class="action-btn resolve" @tap="handleResolve">解决告警</button>
                    <button class="action-btn silence" @tap="handleSilence">静默</button>
                    <button class="action-btn heal" @tap="handleHeal">触发自愈</button>
                </view>
                <button class="ai-btn" @tap="goAI">
                    <text class="ai-btn-text">AI 根因分析</text>
                </button>
            </view>
        </template>
    </view>
</template>

<script setup>
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getList, acknowledge, resolve } from '@/api/alert.js'
import { setPendingPreset } from '@/api/agent.js'

const alert = ref(null)
const loading = ref(true)

function severityText(s) {
    const map = { critical: '致命', high: '严重', medium: '中等', low: '低', info: '信息' }
    return map[s] || s || '低'
}
function statusText(s) {
    const map = { triggered: '待处理', acknowledged: '已确认', resolved: '已恢复', suppressed: '已静默' }
    return map[s] || s || '-'
}

async function fetchDetail(id) {
    loading.value = true
    try {
        const data = await getList({ per_page: 100 })
        const items = data.alerts || data.items || []
        const arr = Array.isArray(items) ? items : []
        alert.value = arr.find((a) => String(a.id) === String(id)) || null
        if (!alert.value && data.id) alert.value = data
    } catch (e) {
        uni.showToast({ title: '加载失败', icon: 'none' })
    } finally {
        loading.value = false
    }
}

async function handleAck() {
    try {
        await acknowledge(alert.value.id)
        uni.showToast({ title: '已确认', icon: 'success' })
        alert.value.status = 'acknowledged'
    } catch (e) {}
}

async function handleResolve() {
    uni.showModal({
        title: '解决告警',
        content: '确认将该告警标记为已恢复？',
        success: async (r) => {
            if (r.confirm) {
                try {
                    await resolve(alert.value.id)
                    uni.showToast({ title: '已解决', icon: 'success' })
                    alert.value.status = 'resolved'
                } catch (e) {}
            }
        },
    })
}

function handleSilence() {
    uni.showModal({
        title: '静默告警',
        content: '移动端暂不支持直接静默，请通过 AI 助手或 Web 端执行静默操作。',
        showCancel: false,
        success: () => {},
    })
}

function handleHeal() {
    uni.showModal({
        title: '触发自愈',
        content: '确认对该告警触发自愈流程？',
        success: (r) => {
            if (r.confirm) uni.showToast({ title: '自愈已触发', icon: 'success' })
        },
    })
}

function goAI() {
    if (!alert.value || alert.value.id == null) {
        uni.showToast({ title: '告警信息缺失', icon: 'none' })
        return
    }
    const id = alert.value.id
    setPendingPreset('分析告警 #' + id + ' 的根因，并给出处置建议')
    uni.switchTab({ url: '/pages/agent/chat' })
}

onLoad((opts) => {
    if (opts && opts.id != null) {
        try {
            const app = getApp()
            const cached = app && app.globalData && app.globalData.currentAlert
            if (cached && String(cached.id) === String(opts.id)) {
                alert.value = cached
                loading.value = false
                return
            }
        } catch (e) {}
        fetchDetail(opts.id)
    }
})
</script>

<style lang="scss" scoped>

.loading-state {
    padding: 120rpx 0;
    text-align: center;
}

.alert-title {
    font-size: $font-lg;
    font-weight: 700;
    color: $text;
    flex: 1;
    margin-right: 16rpx;
}

.sev-badge {
    padding: 8rpx 24rpx;
    border-radius: 24rpx;
}
.sev-critical { background: rgba($severity-critical, 0.12); }
.sev-high { background: rgba($severity-high, 0.12); }
.sev-medium { background: rgba($severity-medium, 0.12); }
.sev-low { background: rgba($severity-low, 0.12); }
.sev-info { background: rgba($severity-info, 0.12); }

.sev-text {
    font-size: $font-xs;
    font-weight: 600;
}
.sev-critical .sev-text { color: $severity-critical; }
.sev-high .sev-text { color: $severity-high; }
.sev-medium .sev-text { color: $severity-medium; }
.sev-low .sev-text { color: $severity-low; }
.sev-info .sev-text { color: $severity-info; }

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

.msg-box {
    margin-top: 24rpx;
    padding: 24rpx;
    background: $bg-card;
    border-radius: 16rpx;
}

.msg-text {
    font-size: $font-sm;
    color: $text-secondary;
    line-height: 1.6;
}

.card-title {
    font-size: $font-lg;
    font-weight: 600;
    color: $text;
    margin-bottom: 24rpx;
}

.action-grid {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
}

.action-btn {
    width: 48%;
    height: 80rpx;
    line-height: 80rpx;
    border-radius: 40rpx;
    font-size: $font-sm;
    text-align: center;
    margin-bottom: 20rpx;
    border: none;
}
.action-btn::after { border: none; }

.action-btn.ack { background: $primary; color: #fff; }
.action-btn.resolve { background: $success; color: #fff; }
.action-btn.silence { background: $bg-card; color: $text; }
.action-btn.heal { background: $warning; color: #fff; }

.ai-btn {
    width: 100%;
    height: $btn-height;
    line-height: $btn-height;
    background: linear-gradient(90deg, $primary, $primary-light);
    border-radius: $btn-radius;
    margin-top: 8rpx;
    border: none;
}
.ai-btn::after { border: none; }

.ai-btn-text {
    color: #fff;
    font-size: $font-lg;
    font-weight: 600;
}
</style>
