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
                <button class="ai-btn" @tap="handleAIAnalyze" :disabled="aiLoading">
                    <text class="ai-btn-text">{{ aiLoading ? '分析中...' : '🤖 AI 自愈分析' }}</text>
                </button>
                <view v-if="aiResult" class="ai-result-card">
                    <view class="ai-result-header">
                        <text class="ai-result-title">AI 分析结果</text>
                        <text class="ai-result-dedup" v-if="aiResult.dedup">（复用已有方案）</text>
                    </view>
                    <view class="ai-result-section">
                        <text class="ai-result-label">根因</text>
                        <text class="ai-result-text">{{ aiResult.root_cause || '无' }}</text>
                    </view>
                    <view class="ai-result-section">
                        <text class="ai-result-label">修复方案</text>
                        <text class="ai-result-text">{{ aiResult.command || aiResult.action_type || '无' }}</text>
                    </view>
                    <view class="ai-result-actions" v-if="aiResult.pending_action_id">
                        <button class="action-btn ack" @tap="confirmRemediation(aiResult.pending_action_id)">确认执行</button>
                        <button class="action-btn silence" @tap="cancelRemediation(aiResult.pending_action_id)">取消</button>
                    </view>
                </view>
                <button class="assistant-btn" @tap="goAI">
                    <text class="assistant-btn-text">💬 AI 根因分析（对话）</text>
                </button>
                <button class="assistant-btn" @tap="openAssistant">
                    <text class="assistant-btn-text">💬 智能助手</text>
                </button>
            </view>
        </template>
    </view>
</template>

<script setup>
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getList, getDetail, acknowledge, resolve, triggerHeal, silence, aiAnalyze, confirmRemediationAction, cancelRemediationAction } from '@/api/alert.js'
import { setPendingPreset, openAlertAssistant, setPendingSessionId } from '@/api/agent.js'

const alert = ref(null)
const loading = ref(true)
const aiLoading = ref(false)
const aiResult = ref(null)

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
        const data = await getDetail(id)
        if (data && data.alert) {
            alert.value = data.alert
        } else if (data && data.id) {
            alert.value = data
        } else {
            alert.value = null
            if (data && data.warning) {
                uni.showToast({ title: data.warning, icon: 'none' })
            }
        }
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
    uni.showActionSheet({
        itemList: ['静默 30 分钟', '静默 1 小时', '静默 4 小时', '静默 24 小时'],
        success: async (res) => {
            const minutesMap = [30, 60, 240, 1440]
            const minutes = minutesMap[res.tapIndex]
            uni.showLoading({ title: '静默中...' })
            try {
                await silence(alert.value.id, { minutes: minutes })
                uni.hideLoading()
                uni.showToast({ title: `已静默 ${minutes} 分钟`, icon: 'success' })
                alert.value.status = 'suppressed'
            } catch (e) {
                uni.hideLoading()
                uni.showToast({ title: '静默失败', icon: 'none' })
            }
        },
    })
}

async function handleHeal() {
    uni.showModal({
        title: '触发自愈',
        content: '确认对该告警触发自愈流程？',
        success: async (r) => {
            if (!r.confirm) return
            uni.showLoading({ title: '自愈执行中...' })
            try {
                const res = await triggerHeal(alert.value.id)
                uni.hideLoading()
                if (res.error) {
                    uni.showToast({ title: res.error, icon: 'none' })
                } else {
                    const stepInfo = (res.steps || []).map(s => (s.success ? '✓' : '✗') + s.action).join(' ')
                    uni.showToast({ title: '自愈完成: ' + stepInfo, icon: 'success' })
                    alert.value.status = 'acknowledged'
                }
            } catch (e) {
                uni.hideLoading()
                uni.showToast({ title: '自愈请求失败', icon: 'none' })
            }
        },
    })
}

async function handleAIAnalyze() {
    if (!alert.value || !alert.value.id) {
        uni.showToast({ title: '告警信息缺失', icon: 'none' })
        return
    }
    aiLoading.value = true
    aiResult.value = null
    try {
        const data = await aiAnalyze(alert.value.id)
        if (data.ok) {
            const a = data.analysis || data
            aiResult.value = {
                root_cause: a.root_cause || '',
                command: a.command || '',
                action_type: a.action_type || '',
                risk_level: a.risk_level || 'medium',
                pending_action_id: data.pending_action_id || a.pending_action_id,
                dedup: data.dedup || false,
            }
            uni.showToast({ title: data.dedup ? '已有方案，可确认执行' : 'AI 分析完成', icon: 'success' })
        } else {
            uni.showToast({ title: data.error || 'AI 分析失败', icon: 'none' })
        }
    } catch (e) {
        uni.showToast({ title: 'AI 分析请求失败', icon: 'none' })
    } finally {
        aiLoading.value = false
    }
}

async function confirmRemediation(actionId) {
    uni.showLoading({ title: '执行中...' })
    try {
        const data = await confirmRemediationAction(actionId)
        uni.hideLoading()
        if (data.success) {
            uni.showToast({ title: '执行成功: ' + (data.output || ''), icon: 'success' })
            aiResult.value = null
            alert.value.status = 'acknowledged'
        } else {
            uni.showToast({ title: '执行失败: ' + (data.output || data.error || ''), icon: 'none' })
        }
    } catch (e) {
        uni.hideLoading()
        uni.showToast({ title: '执行请求失败', icon: 'none' })
    }
}

async function cancelRemediation(actionId) {
    uni.showModal({
        title: '取消操作',
        content: '确认取消该修复方案？',
        success: async (r) => {
            if (!r.confirm) return
            try {
                await cancelRemediationAction(actionId)
                uni.showToast({ title: '已取消', icon: 'none' })
                aiResult.value = null
            } catch (e) {
                uni.showToast({ title: '取消失败', icon: 'none' })
            }
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

async function openAssistant() {
    if (!alert.value || alert.value.id == null) {
        uni.showToast({ title: '告警信息缺失', icon: 'none' })
        return
    }
    uni.showLoading({ title: '创建会话...' })
    try {
        const data = await openAlertAssistant(alert.value.id)
        if (data.session_id) {
            setPendingSessionId(data.session_id)
            uni.switchTab({ url: '/pages/agent/chat' })
        }
    } catch (e) {
        uni.showToast({ title: '打开助手失败', icon: 'none' })
    } finally {
        uni.hideLoading()
    }
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

.assistant-btn {
    width: 100%;
    height: $btn-height;
    line-height: $btn-height;
    background: $bg-card;
    color: $primary;
    border-radius: $btn-radius;
    margin-top: 16rpx;
    border: 2rpx solid $primary;
}
.assistant-btn::after { border: none; }

.assistant-btn-text {
    color: $primary;
    font-size: $font-md;
    font-weight: 600;
}

.ai-result-card {
    margin-top: 24rpx;
    padding: 24rpx;
    background: rgba($primary, 0.04);
    border: 2rpx solid rgba($primary, 0.12);
    border-radius: 16rpx;
}

.ai-result-header {
    display: flex;
    align-items: center;
    gap: 8rpx;
    margin-bottom: 16rpx;
}

.ai-result-title {
    font-size: $font-md;
    font-weight: 700;
    color: $primary;
}

.ai-result-dedup {
    font-size: $font-xs;
    color: $text-muted;
}

.ai-result-section {
    margin-bottom: 12rpx;
}

.ai-result-label {
    font-size: $font-xs;
    color: $text-muted;
    display: block;
    margin-bottom: 4rpx;
}

.ai-result-text {
    font-size: $font-sm;
    color: $text;
    line-height: 1.5;
}

.ai-result-actions {
    display: flex;
    gap: 16rpx;
    margin-top: 16rpx;
}
.ai-result-actions .action-btn {
    width: auto;
    flex: 1;
}
</style>
