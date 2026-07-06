<template>
    <view class="page-wrap">
        <view v-if="list.length === 0 && !loading" class="empty-state">
            <text class="empty-icon">✅</text>
            <text class="empty-text">暂无待确认操作</text>
        </view>

        <view v-for="action in list" :key="action.id" class="card">
            <view class="flex-between">
                <text class="action-title">{{ action.title || action.action_type || '待确认操作' }}</text>
                <RiskBadge :level="action.risk_level || 'low'" />
            </view>
            <view v-if="action.action_payload" class="info-row">
                <text class="info-label">操作目标</text>
                <text class="info-value">{{ formatPayload(action.action_payload) }}</text>
            </view>
            <view v-if="action.reason" class="desc-box">
                <text class="desc-text">{{ action.reason }}</text>
            </view>

            <view class="action-btns">
                <button class="reject-btn" @tap="handleReject(action)">拒绝</button>
                <button class="confirm-btn" @tap="handleConfirm(action)">确认</button>
            </view>
        </view>

        <view v-if="showCountdownMask" class="mask" @tap="cancelCountdown">
            <view class="countdown-box" @tap.stop>
                <text class="countdown-title">高危操作确认</text>
                <text class="countdown-desc">该操作风险等级较高，请谨慎确认</text>
                <text class="countdown-time">{{ countdown > 0 ? countdown + 's 后可确认' : '可确认' }}</text>
                <button class="confirm-btn" :disabled="countdown > 0" @tap="doConfirmHigh">
                    {{ countdown > 0 ? '请等待' : '我已知晓，确认执行' }}
                </button>
                <button class="cancel-btn" @tap="cancelCountdown">取消</button>
            </view>
        </view>
    </view>
</template>

<script setup>
import { ref, onUnmounted } from 'vue'
import { onPullDownRefresh } from '@dcloudio/uni-app'
import { listPending, confirmPending, cancelPending } from '@/api/agent.js'
import RiskBadge from '@/components/RiskBadge.vue'

const list = ref([])
const loading = ref(false)
const showCountdownMask = ref(false)
const countdown = ref(3)
const currentAction = ref(null)
let timer = null

function formatPayload(p) {
    if (!p) return '-'
    if (typeof p === 'string') return p
    try {
        return JSON.stringify(p)
    } catch (e) {
        return '-'
    }
}

async function fetchList() {
    loading.value = true
    try {
        const data = await listPending()
        list.value = data.actions || data || []
        if (!Array.isArray(list.value)) list.value = []
    } catch (e) {
        uni.showToast({ title: '加载失败', icon: 'none' })
    } finally {
        loading.value = false
    }
}

function isHighRisk(action) {
    const lvl = (action.risk_level || '').toLowerCase()
    return lvl === 'high' || lvl === 'critical'
}

function handleConfirm(action) {
    if (!action || !action.id) {
        uni.showToast({ title: '操作信息缺失', icon: 'none' })
        return
    }
    if (isHighRisk(action)) {
        currentAction.value = action
        countdown.value = 3
        showCountdownMask.value = true
        timer = setInterval(() => {
            countdown.value--
            if (countdown.value <= 0) {
                clearInterval(timer)
                timer = null
            }
        }, 1000)
    } else {
        doConfirm(action)
    }
}

function doConfirmHigh() {
    if (countdown.value > 0) return
    showCountdownMask.value = false
    if (currentAction.value) {
        doConfirm(currentAction.value)
        currentAction.value = null
    }
}

function cancelCountdown() {
    showCountdownMask.value = false
    if (timer) {
        clearInterval(timer)
        timer = null
    }
    currentAction.value = null
}

async function doConfirm(action) {
    try {
        await confirmPending(action.id)
        uni.showToast({ title: '已确认', icon: 'success' })
        list.value = list.value.filter((a) => a.id !== action.id)
    } catch (e) {}
}

async function handleReject(action) {
    if (!action || !action.id) {
        uni.showToast({ title: '操作信息缺失', icon: 'none' })
        return
    }
    uni.showModal({
        title: '拒绝操作',
        content: '确认拒绝该操作？',
        success: async (r) => {
            if (r.confirm) {
                try {
                    await cancelPending(action.id)
                    uni.showToast({ title: '已拒绝', icon: 'none' })
                    list.value = list.value.filter((a) => a.id !== action.id)
                } catch (e) {}
            }
        },
    })
}

onPullDownRefresh(async () => {
    await fetchList()
    uni.stopPullDownRefresh()
})

onUnmounted(() => {
    if (timer) {
        clearInterval(timer)
        timer = null
    }
})

fetchList()
</script>

<style lang="scss" scoped>

.action-title {
    font-size: $font-lg;
    font-weight: 600;
    color: $text;
    flex: 1;
    margin-right: 16rpx;
}

.info-row {
    display: flex;
    justify-content: space-between;
    padding: 16rpx 0;
}

.info-label {
    font-size: $font-sm;
    color: $text-muted;
}

.info-value {
    font-size: $font-sm;
    color: $text;
}

.desc-box {
    background: $bg-card;
    border-radius: 16rpx;
    padding: 20rpx;
    margin: 16rpx 0;
}

.desc-text {
    font-size: $font-sm;
    color: $text-secondary;
    line-height: 1.6;
}

.action-btns {
    display: flex;
    gap: 24rpx;
    margin-top: 24rpx;
}

.reject-btn {
    flex: 1;
    height: 80rpx;
    line-height: 80rpx;
    background: $bg-card;
    color: $danger;
    border-radius: 40rpx;
    font-size: $font-md;
    border: none;
}
.reject-btn::after { border: none; }

.confirm-btn {
    flex: 1;
    height: 80rpx;
    line-height: 80rpx;
    background: $primary;
    color: #fff;
    border-radius: 40rpx;
    font-size: $font-md;
    border: none;
}
.confirm-btn::after { border: none; }
.confirm-btn[disabled] {
    background: $border;
    color: $text-muted;
}

.mask {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 999;
    display: flex;
    align-items: center;
    justify-content: center;
}

.countdown-box {
    width: 600rpx;
    background: $bg-card-solid;
    border-radius: $card-radius;
    padding: 48rpx 32rpx;
    display: flex;
    flex-direction: column;
    align-items: center;
}

.countdown-title {
    font-size: $font-lg;
    font-weight: 700;
    color: $danger;
    margin-bottom: 16rpx;
}

.countdown-desc {
    font-size: $font-sm;
    color: $text-secondary;
    text-align: center;
    margin-bottom: 24rpx;
}

.countdown-time {
    font-size: $font-md;
    color: $warning;
    margin-bottom: 32rpx;
}

.cancel-btn {
    width: 100%;
    height: 80rpx;
    line-height: 80rpx;
    background: transparent;
    color: $text-muted;
    font-size: $font-md;
    margin-top: 16rpx;
    border: none;
}
.cancel-btn::after { border: none; }
</style>
