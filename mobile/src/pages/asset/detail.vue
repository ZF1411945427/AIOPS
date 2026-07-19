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

            <view class="card" v-if="showMetrics">
                <view class="flex-between">
                    <text class="card-title">指标监控</text>
                    <text class="close-btn" @tap="showMetrics = false">✕</text>
                </view>
                <view v-if="metricsLoading" class="loading-mini">
                    <text class="text-muted">加载指标中...</text>
                </view>
                <template v-else>
                    <view v-if="metricsNames.length === 0" class="empty-mini">
                        <text class="text-muted">暂无指标数据</text>
                    </view>
                    <view v-else>
                        <scroll-view scroll-x class="metric-tabs">
                            <view
                                v-for="name in metricsNames"
                                :key="name"
                                class="metric-tab"
                                :class="{ active: currentMetric === name }"
                                @tap="switchMetric(name)"
                            >
                                <text class="metric-tab-text">{{ name }}</text>
                            </view>
                        </scroll-view>
                        <view v-if="currentMetric" class="metric-chart">
                            <view class="metric-latest">
                                <text class="metric-name">{{ currentMetric }}</text>
                                <text class="metric-value">{{ latestValue }}</text>
                            </view>
                            <view class="chart-bars">
                                <view
                                    v-for="(pt, idx) in chartData"
                                    :key="idx"
                                    class="bar-col"
                                >
                                    <view
                                        class="bar"
                                        :style="{ height: barHeight(pt.value) + 'rpx' }"
                                    ></view>
                                </view>
                            </view>
                            <view class="chart-x">
                                <text class="chart-x-label">{{ chartStartTime }}</text>
                                <text class="chart-x-label">{{ chartEndTime }}</text>
                            </view>
                        </view>
                    </view>
                </template>
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
                    <view class="quick-item" @tap="goDiagnose">
                        <text class="quick-icon">AI</text>
                        <text class="quick-label">AI诊断</text>
                    </view>
                    <view class="quick-item" @tap="openAssistant">
                        <text class="quick-icon">💬</text>
                        <text class="quick-label">智能助手</text>
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
import { buildUrl, commonHeaders } from '@/api/config.js'
import { openAssetAssistant, setPendingSessionId } from '@/api/agent.js'

const asset = ref(null)
const recentAlerts = ref([])
const loading = ref(true)

// 指标相关
const showMetrics = ref(false)
const metricsLoading = ref(false)
const metricsNames = ref([])
const currentMetric = ref('')
const chartData = ref([])
const latestValue = ref('-')
const chartStartTime = ref('')
const chartEndTime = ref('')

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
    if (showMetrics.value) {
        showMetrics.value = false
        return
    }
    showMetrics.value = true
    metricsLoading.value = true
    metricsNames.value = []
    currentMetric.value = ''
    chartData.value = []
    latestValue.value = '-'
    fetchMetricsNames()
}

async function fetchMetricsNames() {
    const id = asset.value && asset.value.id
    if (!id) {
        metricsLoading.value = false
        return
    }
    try {
        const data = await new Promise((resolve, reject) => {
            uni.request({
                url: buildUrl('/metrics/names'),
                method: 'GET',
                header: commonHeaders(),
                success: (r) => { r.statusCode >= 200 && r.statusCode < 300 ? resolve(r.data) : reject(r) },
                fail: reject,
            })
        })
        const names = Array.isArray(data) ? data : []
        metricsNames.value = names
        if (names.length > 0) {
            switchMetric(names[0])
        } else {
            metricsLoading.value = false
        }
    } catch (e) {
        metricsLoading.value = false
        uni.showToast({ title: '获取指标列表失败', icon: 'none' })
    }
}

async function switchMetric(name) {
    currentMetric.value = name
    metricsLoading.value = true
    const id = asset.value && asset.value.id
    if (!id) { metricsLoading.value = false; return }
    try {
        const data = await new Promise((resolve, reject) => {
            uni.request({
                url: buildUrl(`/metrics/data?asset_id=${id}&name=${encodeURIComponent(name)}&hours=6`),
                method: 'GET',
                header: commonHeaders(),
                success: (r) => { r.statusCode >= 200 && r.statusCode < 300 ? resolve(r.data) : reject(r) },
                fail: reject,
            })
        })
        const arr = Array.isArray(data) ? data : []
        // 按时间正序
        arr.sort((a, b) => new Date(a.time) - new Date(b.time))
        chartData.value = arr.slice(-60)  // 最近60个点
        if (arr.length > 0) {
            const last = arr[arr.length - 1]
            latestValue.value = (last.value !== undefined ? last.value : '-') + (last.unit ? ' ' + last.unit : '')
            chartStartTime.value = formatTime(arr[0].time)
            chartEndTime.value = formatTime(last.time)
        } else {
            latestValue.value = '暂无数据'
            chartStartTime.value = ''
            chartEndTime.value = ''
        }
    } catch (e) {
        chartData.value = []
        latestValue.value = '加载失败'
    } finally {
        metricsLoading.value = false
    }
}

function formatTime(t) {
    if (!t) return ''
    const d = new Date(t)
    return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2)
}

function barHeight(val) {
    if (val === undefined || val === null) return 2
    const vals = chartData.value.map((p) => Math.abs(p.value || 0))
    const maxV = Math.max(...vals, 0.001)
    const h = Math.abs(val) / maxV * 200
    return Math.max(4, Math.min(200, h))
}

function goDiagnose() {
    const id = asset.value && asset.value.id
    uni.navigateTo({ url: '/pages/asset/diagnose?assetId=' + id })
}

async function openAssistant() {
    const id = asset.value && asset.value.id
    if (!id) {
        uni.showToast({ title: '资产信息缺失', icon: 'none' })
        return
    }
    uni.showLoading({ title: '创建会话...' })
    try {
        const data = await openAssetAssistant(id)
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

.close-btn {
    font-size: 36rpx;
    color: $text-muted;
    padding: 8rpx 16rpx;
}

.loading-mini {
    padding: 32rpx 0;
    text-align: center;
}

.metric-tabs {
    white-space: nowrap;
    padding: 16rpx 0;
}

.metric-tab {
    display: inline-block;
    padding: 12rpx 28rpx;
    margin-right: 16rpx;
    background: $bg-card;
    border-radius: 32rpx;
}

.metric-tab.active {
    background: $primary;
}

.metric-tab-text {
    font-size: $font-xs;
    color: $text-secondary;
}

.metric-tab.active .metric-tab-text {
    color: #fff;
}

.metric-chart {
    margin-top: 24rpx;
}

.metric-latest {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 24rpx;
}

.metric-name {
    font-size: $font-md;
    font-weight: 600;
    color: $text;
}

.metric-value {
    font-size: $font-lg;
    font-weight: 700;
    color: $primary;
}

.chart-bars {
    display: flex;
    align-items: flex-end;
    height: 220rpx;
    gap: 4rpx;
    padding: 0 8rpx;
}

.bar-col {
    flex: 1;
    display: flex;
    align-items: flex-end;
    justify-content: center;
    height: 200rpx;
}

.bar {
    width: 100%;
    background: linear-gradient(to top, $primary, rgba($primary, 0.4));
    border-radius: 4rpx 4rpx 0 0;
    min-height: 4rpx;
}

.chart-x {
    display: flex;
    justify-content: space-between;
    margin-top: 8rpx;
}

.chart-x-label {
    font-size: $font-xs;
    color: $text-muted;
}
</style>
