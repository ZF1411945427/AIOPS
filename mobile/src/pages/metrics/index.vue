<template>
    <view class="page-wrap">
        <view v-if="loading" class="loading-state">
            <text class="text-muted">加载指标...</text>
        </view>

        <template v-else>
            <scroll-view scroll-x class="metric-tabs">
                <view v-for="name in metricNames" :key="name" class="metric-tab" :class="{ active: currentMetric === name }" @tap="switchMetric(name)">
                    <text class="metric-tab-text">{{ name }}</text>
                </view>
            </scroll-view>

            <view v-if="!currentMetric" class="empty-state">
                <text class="empty-icon">📊</text>
                <text class="empty-text">请选择上方指标查看趋势</text>
            </view>

            <template v-else>
                <view class="card">
                    <view class="metric-latest-row">
                        <text class="metric-name">{{ currentMetric }}</text>
                        <text class="metric-value">{{ latestValue }}</text>
                    </view>
                    <view class="chart-bars">
                        <view v-for="(pt, idx) in chartData" :key="idx" class="bar-col">
                            <view class="bar" :style="{ height: barHeight(pt.value) + 'rpx' }"></view>
                        </view>
                    </view>
                    <view class="chart-x">
                        <text class="chart-x-label">{{ chartStartTime }}</text>
                        <text class="chart-x-label">{{ chartEndTime }}</text>
                    </view>
                </view>

                <view class="time-selector">
                    <view v-for="t in timeOptions" :key="t.value" class="time-btn" :class="{ active: hours === t.value }" @tap="changeHours(t.value)">
                        <text class="time-btn-text">{{ t.label }}</text>
                    </view>
                </view>
            </template>
        </template>
    </view>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getMetricNames, getMetricData } from '@/api/metrics.js'

const metricNames = ref([])
const currentMetric = ref('')
const chartData = ref([])
const latestValue = ref('-')
const chartStartTime = ref('')
const chartEndTime = ref('')
const loading = ref(true)
const hours = ref(1)

const timeOptions = [
    { label: '1小时', value: 1 },
    { label: '6小时', value: 6 },
    { label: '24小时', value: 24 },
    { label: '7天', value: 168 },
]

async function loadNames() {
    loading.value = true
    try {
        const data = await getMetricNames()
        metricNames.value = Array.isArray(data) ? data : []
        if (metricNames.value.length > 0) {
            currentMetric.value = metricNames.value[0]
            await loadData(metricNames.value[0])
        }
    } catch (e) {
        uni.showToast({ title: '加载指标名失败', icon: 'none' })
    } finally {
        loading.value = false
    }
}

async function loadData(name) {
    try {
        const data = await getMetricData({ name, hours: hours.value })
        const arr = Array.isArray(data) ? data : []
        arr.sort((a, b) => new Date(a.time) - new Date(b.time))
        chartData.value = arr.slice(-120)
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
    }
}

function switchMetric(name) {
    currentMetric.value = name
    loadData(name)
}

function changeHours(val) {
    hours.value = val
    if (currentMetric.value) loadData(currentMetric.value)
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

onMounted(loadNames)
</script>

<style lang="scss" scoped>
.metric-tabs {
    white-space: nowrap; padding: 0 0 16rpx 0;
}
.metric-tab {
    display: inline-block; padding: 12rpx 28rpx; margin-right: 16rpx;
    background: $bg-card-solid; border-radius: 32rpx;
}
.metric-tab.active { background: $primary; }
.metric-tab-text { font-size: $font-xs; color: $text-secondary; }
.metric-tab.active .metric-tab-text { color: #fff; }
.metric-latest-row {
    display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 24rpx;
}
.metric-name { font-size: $font-md; font-weight: 600; color: $text; }
.metric-value { font-size: $font-lg; font-weight: 700; color: $primary; }
.chart-bars {
    display: flex; align-items: flex-end; height: 220rpx; gap: 4rpx; padding: 0 8rpx;
}
.bar-col { flex: 1; display: flex; align-items: flex-end; justify-content: center; height: 200rpx; }
.bar {
    width: 100%; background: linear-gradient(to top, $primary, rgba($primary, 0.4));
    border-radius: 4rpx 4rpx 0 0; min-height: 4rpx;
}
.chart-x { display: flex; justify-content: space-between; margin-top: 8rpx; }
.chart-x-label { font-size: $font-xs; color: $text-muted; }
.time-selector {
    display: flex; gap: 16rpx; margin-top: 24rpx;
}
.time-btn {
    flex: 1; height: 72rpx; line-height: 72rpx; text-align: center;
    background: $bg-card-solid; border-radius: 36rpx;
}
.time-btn.active { background: $primary; }
.time-btn-text { font-size: $font-xs; color: $text-secondary; }
.time-btn.active .time-btn-text { color: #fff; font-weight: 600; }
</style>
