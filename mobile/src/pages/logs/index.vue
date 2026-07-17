<template>
    <view class="page-wrap">
        <view class="search-bar">
            <input v-model="keyword" class="search-input" placeholder="搜索日志内容..." confirm-type="search" @confirm="search" />
            <view class="level-filter">
                <view
                    v-for="l in levels"
                    :key="l.value"
                    class="level-tag"
                    :class="{ active: activeLevel === l.value }"
                    @tap="switchLevel(l.value)"
                >{{ l.label }}</view>
            </view>
        </view>

        <view class="source-row">
            <picker :value="sourceIndex" :range="sources" range-key="name" @change="onSourceChange">
                <view class="source-picker">
                    <text class="source-label">{{ selectedSource?.name || '全部数据源' }}</text>
                    <text class="picker-arrow">▼</text>
                </view>
            </picker>
            <view class="time-range">
                <picker mode="date" :value="startTime" @change="e => startTime = e.detail.value">
                    <text class="time-text">{{ startTime || '开始时间' }}</text>
                </picker>
                <text class="time-sep">~</text>
                <picker mode="date" :value="endTime" @change="e => endTime = e.detail.value">
                    <text class="time-text">{{ endTime || '结束时间' }}</text>
                </picker>
            </view>
        </view>

        <view class="result-bar" v-if="total > 0">
            <text class="result-count">共 {{ total }} 条</text>
            <text class="export-btn" @tap="exportLogs">导出</text>
        </view>

        <scroll-view scroll-y class="list-scroll" @scrolltolower="loadMore" lower-threshold="80">
            <view v-if="loading && list.length === 0" class="loading-state">
                <text class="text-muted">加载中...</text>
            </view>
            <view v-else-if="list.length === 0 && !loading" class="empty-state">
                <text class="empty-icon">📋</text>
                <text class="empty-text">暂无日志</text>
            </view>

            <view
                v-for="(item, idx) in list"
                :key="idx"
                class="log-card"
                @tap="toggleExpand(idx)"
            >
                <view class="log-header">
                    <view class="log-level" :class="'level-' + (item.level || 'info')">
                        <text class="level-text">{{ (item.level || 'info').toUpperCase() }}</text>
                    </view>
                    <text class="log-source">{{ item.source || item.service || '-' }}</text>
                    <text class="log-time">{{ formatTime(item.timestamp || item.time) }}</text>
                </view>
                <view class="log-message" :class="{ expanded: expandedIdx === idx }">
                    <text class="log-content">{{ item.message || item.msg || item.content || '-' }}</text>
                </view>
                <view v-if="expandedIdx === idx && item.raw" class="log-raw">
                    <text class="raw-label">原始内容</text>
                    <text class="raw-content">{{ item.raw }}</text>
                </view>
            </view>

            <view v-if="loadingMore" class="loading-more">
                <text class="text-muted">加载中...</text>
            </view>
            <view v-else-if="noMore && list.length > 0" class="loading-more">
                <text class="text-muted">没有更多了</text>
            </view>
        </scroll-view>
    </view>
</template>

<script setup>
import { ref } from 'vue'
import { onPullDownRefresh } from '@dcloudio/uni-app'

const keyword = ref('')
const activeLevel = ref('')
const levels = [
    { label: '全部', value: '' },
    { label: 'ERROR', value: 'error' },
    { label: 'WARN', value: 'warning' },
    { label: 'INFO', value: 'info' },
    { label: 'DEBUG', value: 'debug' },
]
const sources = ref([{ name: '全部数据源', value: '' }])
const sourceIndex = ref(0)
const selectedSource = ref(null)
const startTime = ref('')
const endTime = ref('')
const list = ref([])
const page = ref(1)
const loading = ref(false)
const loadingMore = ref(false)
const noMore = ref(false)
const total = ref(0)
const expandedIdx = ref(-1)
const PAGE_SIZE = 30

async function fetchSources() {
    try {
        const res = await uni.request({
            url: '/logs/api/sources',
            method: 'GET',
        })
        if (res.statusCode === 200 && res.data) {
            const raw = res.data.sources || res.data.items || res.data || []
            sources.value = [{ name: '全部数据源', value: '' }, ...raw.slice(0, 10)]
        }
    } catch (e) {
        sources.value = [{ name: '全部数据源', value: '' }]
    }
}

async function search(reset = false) {
    if (reset) {
        page.value = 1
        noMore.value = false
        list.value = []
    }
    loading.value = true
    try {
        const params = {
            page: page.value,
            per_page: PAGE_SIZE,
        }
        if (keyword.value) params.keyword = keyword.value
        if (activeLevel.value) params.level = activeLevel.value
        if (selectedSource.value?.value) params.source = selectedSource.value.value
        if (startTime.value) params.start = startTime.value
        if (endTime.value) params.end = endTime.value

        const res = await uni.request({
            url: '/logs/api/search',
            method: 'GET',
            data: params,
        })
        if (res.statusCode === 200 && res.data) {
            const raw = res.data.logs || res.data.items || res.data.records || res.data || []
            const arr = Array.isArray(raw) ? raw : []
            if (reset) list.value = arr
            else list.value = list.value.concat(arr)
            total.value = res.data.total || list.value.length
            if (arr.length < PAGE_SIZE) noMore.value = true
        }
    } catch (e) {
        uni.showToast({ title: '搜索失败', icon: 'none' })
    } finally {
        loading.value = false
    }
}

function switchLevel(val) {
    activeLevel.value = val
    search(true)
}

function onSourceChange(e) {
    sourceIndex.value = e.detail.value
    selectedSource.value = sources.value[e.detail.value]
    search(true)
}

function toggleExpand(idx) {
    expandedIdx.value = expandedIdx.value === idx ? -1 : idx
}

function loadMore() {
    if (loadingMore.value || noMore.value) return
    loadingMore.value = true
    page.value++
    search(false).finally(() => { loadingMore.value = false })
}

function exportLogs() {
    if (!list.value.length) return
    const text = list.value.map(l =>
        `[${l.timestamp || l.time}] [${l.level || 'info'}] [${l.source || l.service || '-'}] ${l.message || l.msg || l.content || ''}`
    ).join('\n')
    uni.setClipboardData({
        data: text,
        success: () => uni.showToast({ title: '已复制到剪贴板', icon: 'success' }),
    })
}

function formatTime(ts) {
    if (!ts) return '-'
    const d = new Date(ts)
    return d.toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

onPullDownRefresh(async () => {
    await search(true)
    uni.stopPullDownRefresh()
})

fetchSources()
search(true)
</script>

<style lang="scss" scoped>
.search-bar {
    background: $bg-card-solid;
    border-radius: $card-radius;
    padding: 16rpx 20rpx;
    margin-bottom: 16rpx;
}
.search-input {
    width: 100%;
    height: 72rpx;
    background: $bg;
    border: 1px solid $border;
    border-radius: 36rpx;
    padding: 0 24rpx;
    font-size: $font-sm;
    box-sizing: border-box;
    outline: none;
}
.search-input:focus {
    border-color: $primary;
}
.level-filter {
    display: flex;
    gap: 12rpx;
    margin-top: 16rpx;
    flex-wrap: wrap;
}
.level-tag {
    padding: 8rpx 24rpx;
    border-radius: 20rpx;
    background: $bg;
    border: 1px solid $border;
    font-size: $font-xs;
    color: $text-secondary;
    font-weight: 500;
}
.level-tag.active {
    background: $primary;
    border-color: $primary;
    color: #fff;
}
.source-row {
    display: flex;
    gap: 12rpx;
    align-items: center;
    margin-bottom: 16rpx;
}
.source-picker {
    display: flex;
    align-items: center;
    gap: 8rpx;
    background: $bg-card-solid;
    border: 1px solid $border;
    border-radius: 8rpx;
    padding: 12rpx 20rpx;
    flex-shrink: 0;
}
.source-label {
    font-size: $font-sm;
    color: $text;
}
.picker-arrow {
    font-size: 10rpx;
    color: $text-muted;
}
.time-range {
    display: flex;
    align-items: center;
    gap: 8rpx;
    flex: 1;
}
.time-text {
    font-size: $font-xs;
    color: $text-secondary;
    background: $bg-card-solid;
    border: 1px solid $border;
    border-radius: 8rpx;
    padding: 12rpx 16rpx;
}
.time-sep {
    color: $text-muted;
    font-size: $font-xs;
}
.result-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 4rpx 12rpx;
}
.result-count {
    font-size: $font-xs;
    color: $text-muted;
}
.export-btn {
    font-size: $font-xs;
    color: $primary;
    font-weight: 600;
}
.list-scroll {
    height: calc(100vh - 380rpx);
}
.log-card {
    background: $bg-card-solid;
    border-radius: $card-radius;
    padding: 20rpx;
    margin-bottom: 12rpx;
}
.log-header {
    display: flex;
    align-items: center;
    gap: 12rpx;
    margin-bottom: 12rpx;
}
.log-level {
    padding: 4rpx 16rpx;
    border-radius: 8rpx;
    flex-shrink: 0;
}
.level-error { background: rgba($danger, 0.12); }
.level-warning { background: rgba($warning, 0.12); }
.level-info { background: rgba($info, 0.12); }
.level-debug { background: rgba($text-muted, 0.12); }
.level-text {
    font-size: 20rpx;
    font-weight: 700;
}
.level-error .level-text { color: $danger; }
.level-warning .level-text { color: $warning; }
.level-info .level-text { color: $info; }
.level-debug .level-text { color: $text-muted; }
.log-source {
    font-size: $font-xs;
    color: $text-muted;
    flex: 1;
}
.log-time {
    font-size: 22rpx;
    color: $text-muted;
}
.log-message {
    overflow: hidden;
    max-height: 80rpx;
}
.log-message.expanded {
    max-height: none;
}
.log-content {
    font-size: $font-sm;
    color: $text;
    line-height: 1.6;
    word-break: break-all;
}
.log-raw {
    margin-top: 16rpx;
    padding: 16rpx;
    background: $bg;
    border-radius: 8rpx;
}
.raw-label {
    font-size: $font-xs;
    color: $text-muted;
    display: block;
    margin-bottom: 8rpx;
}
.raw-content {
    font-size: $font-xs;
    color: $text-secondary;
    white-space: pre-wrap;
    word-break: break-all;
    font-family: monospace;
}
.loading-more {
    text-align: center;
    padding: 32rpx 0;
}
.loading-state {
    text-align: center;
    padding: 120rpx 0;
}
.empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding-top: 120rpx;
}
.empty-icon { font-size: 80rpx; margin-bottom: 16rpx; }
.empty-text { font-size: $font-sm; color: $text-muted; }
</style>
