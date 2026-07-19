<template>
    <view class="page-wrap">
        <view class="card search-card">
            <view class="search-row">
                <input
                    v-model="keyword"
                    class="search-input"
                    placeholder="关键词搜索（支持 * 通配）"
                    confirm-type="search"
                    @confirm="onSearch"
                />
                <button class="search-btn" @tap="onSearch">搜索</button>
            </view>
            <view class="filter-row">
                <view class="filter-item">
                    <text class="filter-label">数据源</text>
                    <picker class="filter-picker" :range="sourceOptions" range-key="label" @change="onSourceChange">
                        <view class="picker-value">{{ currentSourceLabel }}</view>
                    </picker>
                </view>
                <view class="filter-item">
                    <text class="filter-label">时间</text>
                    <picker class="filter-picker" :range="timeOptions" range-key="label" @change="onTimeChange">
                        <view class="picker-value">{{ currentTimeLabel }}</view>
                    </picker>
                </view>
                <view class="filter-item">
                    <text class="filter-label">级别</text>
                    <picker class="filter-picker" :range="levelOptions" range-key="label" @change="onLevelChange">
                        <view class="picker-value">{{ currentLevelLabel }}</view>
                    </picker>
                </view>
            </view>
        </view>

        <view v-if="total > 0" class="result-bar">
            <text class="result-count">共 {{ total }} 条</text>
            <text class="export-btn" @tap="copyAll">复制全部</text>
        </view>

        <view v-if="loading && list.length === 0" class="loading-state">
            <text class="text-muted">加载中...</text>
        </view>

        <template v-else-if="list.length === 0">
            <view class="empty-state">
                <text class="empty-icon">📋</text>
                <text class="empty-text">{{ hasSearched ? '未找到匹配日志' : '请选择数据源后搜索' }}</text>
            </view>
        </template>

        <scroll-view v-else scroll-y class="list-scroll" @scrolltolower="loadMore" lower-threshold="80">
            <view
                v-for="(item, idx) in list"
                :key="idx"
                class="log-card"
                @tap="toggleExpand(idx)"
            >
                <view class="log-head">
                    <view class="log-level-badge" :class="'lvl-' + (item.level || 'info').toLowerCase()">
                        <text class="log-level-text">{{ (item.level || 'INFO').toUpperCase() }}</text>
                    </view>
                    <text class="log-source">{{ item.source || item.service || '-' }}</text>
                    <text class="log-time">{{ formatTime(item.timestamp || item.time) }}</text>
                    <text class="expand-icon">{{ expanded === idx ? '▾' : '▸' }}</text>
                </view>
                <view class="log-msg">
                    <text class="log-msg-text">{{ item.message || item.msg || item.content || '-' }}</text>
                </view>
                <view v-if="expanded === idx && item.raw" class="log-raw">
                    <text class="raw-label">原始内容</text>
                    <text class="raw-content" selectable>{{ formatRaw(item.raw) }}</text>
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
import { ref, computed } from 'vue'
import { onPullDownRefresh } from '@dcloudio/uni-app'
import { getLogSources, searchLogs } from '@/api/log.js'

const keyword = ref('')
const list = ref([])
const loading = ref(false)
const loadingMore = ref(false)
const noMore = ref(false)
const hasSearched = ref(false)
const expanded = ref(-1)
const total = ref(0)

const sources = ref([])
const currentSource = ref('')
const currentTime = ref('1h')
const currentLevel = ref('')
const page = ref(1)
const PAGE_SIZE = 50

const timeOptions = [
    { label: '近 15 分钟', value: '15m' },
    { label: '近 1 小时', value: '1h' },
    { label: '近 6 小时', value: '6h' },
    { label: '近 24 小时', value: '24h' },
    { label: '近 7 天', value: '7d' },
]
const levelOptions = [
    { label: '全部级别', value: '' },
    { label: 'ERROR', value: 'ERROR' },
    { label: 'WARN', value: 'WARN' },
    { label: 'INFO', value: 'INFO' },
    { label: 'DEBUG', value: 'DEBUG' },
]

const sourceOptions = computed(() => {
    const arr = [{ label: '全部数据源', value: '' }]
    sources.value.forEach((s) => {
        const label = typeof s === 'string' ? s : (s.name || s.id || '')
        const value = typeof s === 'string' ? s : (s.id || s.name || '')
        if (value) arr.push({ label, value })
    })
    return arr
})

const currentSourceLabel = computed(() => {
    const found = sourceOptions.value.find((s) => s.value === currentSource.value)
    return found ? found.label : '全部数据源'
})

const currentTimeLabel = computed(() => {
    const found = timeOptions.find((t) => t.value === currentTime.value)
    return found ? found.label : '近 1 小时'
})

const currentLevelLabel = computed(() => {
    const found = levelOptions.find((l) => l.value === currentLevel.value)
    return found ? found.label : '全部级别'
})

async function fetchSources() {
    try {
        const data = await getLogSources()
        const items = Array.isArray(data) ? data : (data.sources || data.items || [])
        sources.value = items || []
    } catch (e) {
        sources.value = []
    }
}

async function fetchList(reset) {
    if (reset) {
        page.value = 1
        noMore.value = false
        list.value = []
    }
    loading.value = reset
    loadingMore.value = !reset
    hasSearched.value = true
    try {
        const data = await searchLogs({
            source_id: currentSource.value || undefined,
            query: keyword.value || '*',
            time_range: currentTime.value,
            page: page.value,
            size: PAGE_SIZE,
        })
        let arr = data.logs || data.items || data.records || (Array.isArray(data) ? data : [])
        if (!Array.isArray(arr)) arr = []
        if (currentLevel.value) {
            arr = arr.filter((it) => (it.level || '').toUpperCase() === currentLevel.value)
        }
        if (reset) {
            list.value = arr
        } else {
            list.value = list.value.concat(arr)
        }
        total.value = data.total || list.value.length
        if (arr.length < PAGE_SIZE) noMore.value = true
    } catch (e) {
        uni.showToast({ title: '加载失败', icon: 'none' })
    } finally {
        loading.value = false
        loadingMore.value = false
    }
}

function onSearch() {
    fetchList(true)
}

function onSourceChange(e) {
    const idx = e.detail.value
    currentSource.value = sourceOptions.value[idx] ? sourceOptions.value[idx].value : ''
    fetchList(true)
}

function onTimeChange(e) {
    const idx = e.detail.value
    currentTime.value = timeOptions[idx] ? timeOptions[idx].value : '1h'
    fetchList(true)
}

function onLevelChange(e) {
    const idx = e.detail.value
    currentLevel.value = levelOptions[idx] ? levelOptions[idx].value : ''
    fetchList(true)
}

function toggleExpand(idx) {
    expanded.value = expanded.value === idx ? -1 : idx
}

function formatTime(ts) {
    if (!ts) return '-'
    const d = new Date(ts)
    if (isNaN(d.getTime())) return String(ts)
    return d.toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function formatRaw(raw) {
    if (typeof raw === 'string') return raw
    try {
        return JSON.stringify(raw, null, 2)
    } catch (e) {
        return String(raw)
    }
}

function loadMore() {
    if (loadingMore.value || noMore.value) return
    page.value++
    fetchList(false)
}

function copyAll() {
    if (!list.value.length) return
    const text = list.value
        .map((it) => `[${it.timestamp || it.time || ''}] [${(it.level || 'INFO').toUpperCase()}] [${it.source || it.service || '-'}] ${it.message || it.msg || it.content || ''}`)
        .join('\n')
    uni.setClipboardData({
        data: text,
        success: () => uni.showToast({ title: '已复制 ' + list.value.length + ' 条', icon: 'success' }),
    })
}

onPullDownRefresh(async () => {
    await fetchList(true)
    uni.stopPullDownRefresh()
})

fetchSources()
</script>

<style lang="scss" scoped>
.search-card {
    padding: 24rpx;
}
.search-row {
    display: flex;
    align-items: center;
    gap: 16rpx;
}
.search-input {
    flex: 1;
    height: 72rpx;
    background: $bg-card;
    border-radius: 36rpx;
    padding: 0 28rpx;
    font-size: $font-sm;
    color: $text;
}
.search-btn {
    height: 72rpx;
    line-height: 72rpx;
    padding: 0 32rpx;
    background: $primary;
    color: #fff;
    border-radius: 36rpx;
    font-size: $font-sm;
    border: none;
}
.search-btn::after { border: none; }
.filter-row {
    display: flex;
    gap: 16rpx;
    margin-top: 20rpx;
}
.filter-item {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 8rpx;
}
.filter-label {
    font-size: $font-xs;
    color: $text-muted;
}
.filter-picker {
    background: $bg-card;
    border-radius: 16rpx;
    padding: 0 20rpx;
    height: 56rpx;
    line-height: 56rpx;
}
.picker-value {
    font-size: $font-xs;
    color: $text;
}
.result-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8rpx 4rpx 12rpx;
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
    height: calc(100vh - 420rpx);
}
.log-card {
    background: $bg-card-solid;
    border-radius: $card-radius;
    padding: 24rpx;
    margin-bottom: 16rpx;
}
.log-head {
    display: flex;
    align-items: center;
    gap: 16rpx;
    margin-bottom: 12rpx;
    flex-wrap: wrap;
}
.log-level-badge {
    padding: 4rpx 16rpx;
    border-radius: 12rpx;
    flex-shrink: 0;
}
.lvl-error { background: rgba($danger, 0.12); }
.lvl-warn, .lvl-warning { background: rgba($warning, 0.12); }
.lvl-info { background: rgba($primary, 0.12); }
.lvl-debug { background: rgba($text-muted, 0.12); }
.lvl-error .log-level-text { color: $danger; }
.lvl-warn .log-level-text, .lvl-warning .log-level-text { color: $warning; }
.lvl-info .log-level-text { color: $primary; }
.lvl-debug .log-level-text { color: $text-muted; }
.log-level-text {
    font-size: $font-xs;
    font-weight: 600;
}
.log-source {
    font-size: $font-xs;
    color: $text-secondary;
    background: $bg-card;
    padding: 2rpx 12rpx;
    border-radius: 12rpx;
    flex-shrink: 0;
}
.log-time {
    font-size: $font-xs;
    color: $text-muted;
    flex: 1;
}
.expand-icon {
    font-size: $font-sm;
    color: $text-muted;
}
.log-msg {
    margin-top: 8rpx;
}
.log-msg-text {
    font-size: $font-sm;
    color: $text;
    line-height: 1.5;
    word-break: break-all;
}
.log-raw {
    margin-top: 16rpx;
    padding: 20rpx;
    background: $bg-card;
    border-radius: 12rpx;
    max-height: 600rpx;
    overflow: hidden;
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
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-all;
    font-family: monospace;
}
.loading-more {
    text-align: center;
    padding: 32rpx 0;
    font-size: $font-sm;
}
.loading-state {
    padding: 120rpx 0;
    text-align: center;
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
