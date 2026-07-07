<template>
    <view class="page-wrap">
        <view v-if="loading" class="loading-state">
            <text class="text-muted">加载中...</text>
        </view>

        <template v-else-if="incident">
            <view class="card">
                <view class="detail-top">
                    <view class="incident-sev" :class="'sev-' + (incident.severity || 'warning')">
                        <text class="sev-tag">{{ incident.severity || 'warning' }}</text>
                    </view>
                    <text class="incident-status" :class="'status-' + incident.status">{{ incident.status === 'open' ? '未解决' : '已解决' }}</text>
                </view>
                <text class="detail-title">{{ incident.title }}</text>
                <view class="detail-grid">
                    <view class="detail-row">
                        <text class="detail-label">资产</text>
                        <text class="detail-value">{{ incident.asset_name || '-' }}</text>
                    </view>
                    <view class="detail-row">
                        <text class="detail-label">告警数</text>
                        <text class="detail-value">{{ incident.alert_count || 0 }}</text>
                    </view>
                    <view class="detail-row">
                        <text class="detail-label">创建时间</text>
                        <text class="detail-value">{{ incident.created_at || '-' }}</text>
                    </view>
                    <view class="detail-row" v-if="incident.resolved_at">
                        <text class="detail-label">解决时间</text>
                        <text class="detail-value">{{ incident.resolved_at }}</text>
                    </view>
                </view>
                <button v-if="incident.status === 'open'" class="btn-primary btn-full" @tap="handleResolve">解决故障单</button>
            </view>

            <view class="card" v-if="alerts.length > 0">
                <text class="card-title">关联告警 ({{ alerts.length }})</text>
                <view v-for="al in alerts" :key="al.id" class="alert-item">
                    <view class="sev-dot" :class="'sev-' + (al.severity || 'low')"></view>
                    <view class="alert-info">
                        <text class="alert-name">{{ al.message || al.name }}</text>
                        <text class="alert-meta">{{ al.metric_name }} {{ al.actual_value }} / {{ al.threshold }}</text>
                    </view>
                    <text class="alert-status" :class="'ast-' + al.status">{{ al.status }}</text>
                </view>
            </view>

            <view class="card" v-if="rca">
                <text class="card-title">根因分析</text>
                <text class="rca-content">{{ rca }}</text>
            </view>
        </template>
    </view>
</template>

<script setup>
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getIncidentDetail, resolveIncident, getIncidentRca } from '@/api/incident.js'

const incident = ref(null)
const alerts = ref([])
const rca = ref('')
const loading = ref(true)

async function fetchDetail(id) {
    loading.value = true
    try {
        const data = await getIncidentDetail(id)
        incident.value = data.incident || data
        alerts.value = data.alerts || []
    } catch (e) {
        uni.showToast({ title: '加载失败', icon: 'none' })
    } finally {
        loading.value = false
    }
}

async function handleResolve() {
    uni.showModal({
        title: '解决故障单',
        content: '确认解决该故障单？',
        success: async (r) => {
            if (r.confirm) {
                try {
                    await resolveIncident(incident.value.id)
                    uni.showToast({ title: '已解决', icon: 'success' })
                    incident.value.status = 'resolved'
                } catch (e) {
                    uni.showToast({ title: '操作失败', icon: 'none' })
                }
            }
        },
    })
}

onLoad((opts) => {
    if (opts && opts.id) {
        fetchDetail(opts.id)
        getIncidentRca(opts.id).then((d) => {
            rca.value = d && d.analysis ? (typeof d.analysis === 'string' ? d.analysis : JSON.stringify(d.analysis, null, 2)) : ''
        }).catch(() => {})
    }
})
</script>

<style lang="scss" scoped>
.card { margin-bottom: 24rpx; }
.detail-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20rpx; }
.incident-sev { padding: 6rpx 24rpx; border-radius: 20rpx; }
.sev-critical { background: rgba($danger, 0.12); }
.sev-high { background: rgba($severity-high, 0.12); }
.sev-warning { background: rgba($warning, 0.12); }
.sev-info { background: rgba($info, 0.12); }
.sev-tag { font-size: $font-xs; font-weight: 600; }
.sev-critical .sev-tag { color: $danger; }
.sev-high .sev-tag { color: $severity-high; }
.sev-warning .sev-tag { color: $warning; }
.sev-info .sev-tag { color: $info; }
.incident-status { font-size: $font-xs; padding: 6rpx 20rpx; border-radius: 20rpx; }
.status-open { background: rgba($warning, 0.12); color: $warning; }
.status-resolved { background: rgba($success, 0.12); color: $success; }
.detail-title { font-size: $font-lg; font-weight: 700; color: $text; margin-bottom: 24rpx; }
.detail-grid { margin-bottom: 24rpx; }
.detail-row { display: flex; justify-content: space-between; padding: 16rpx 0; border-bottom: 2rpx solid $border; }
.detail-label { font-size: $font-sm; color: $text-muted; }
.detail-value { font-size: $font-sm; color: $text; }
.btn-full { width: 100%; margin-top: 16rpx; }
.card-title { font-size: $font-md; font-weight: 600; color: $text; margin-bottom: 20rpx; display: block; }
.alert-item { display: flex; align-items: center; padding: 16rpx 0; border-bottom: 2rpx solid $border; }
.sev-dot { width: 16rpx; height: 16rpx; border-radius: 50%; margin-right: 16rpx; flex-shrink: 0; }
.sev-critical { background: $severity-critical; }
.sev-high { background: $severity-high; }
.sev-medium { background: $severity-medium; }
.sev-low { background: $severity-low; }
.alert-info { flex: 1; display: flex; flex-direction: column; }
.alert-name { font-size: $font-sm; color: $text; }
.alert-meta { font-size: $font-xs; color: $text-muted; margin-top: 4rpx; }
.alert-status { font-size: $font-xs; padding: 4rpx 16rpx; border-radius: 16rpx; }
.ast-triggered { background: rgba($danger, 0.12); color: $danger; }
.ast-acknowledged { background: rgba($warning, 0.12); color: $warning; }
.ast-resolved { background: rgba($success, 0.12); color: $success; }
.rca-content { font-size: $font-sm; color: $text; line-height: 1.6; white-space: pre-wrap; }
</style>
