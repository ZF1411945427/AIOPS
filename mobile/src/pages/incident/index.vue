<template>
    <view class="page-wrap">
        <view class="toolbar-row">
            <button class="create-btn" @tap="goCreate">+ 新建故障单</button>
        </view>

        <view class="tab-bar">
            <view v-for="t in tabs" :key="t.value" class="tab-item" :class="{ active: activeTab === t.value }" @tap="switchTab(t.value)">
                <text class="tab-text">{{ t.label }}</text>
            </view>
        </view>

        <view v-if="loading && list.length === 0" class="loading-state">
            <text class="text-muted">加载中...</text>
        </view>

        <template v-else-if="list.length === 0">
            <view class="empty-state">
                <text class="empty-icon">📋</text>
                <text class="empty-text">暂无故障单</text>
            </view>
        </template>

        <scroll-view v-else scroll-y class="list-scroll" @scrolltolower="loadMore" lower-threshold="80">
            <view v-for="item in list" :key="item.id" class="incident-card" @tap="goDetail(item.id)">
                <view class="incident-top">
                    <view class="incident-sev" :class="'sev-' + (item.severity || 'warning')">
                        <text class="sev-tag">{{ item.severity || 'warning' }}</text>
                    </view>
                    <text class="incident-status" :class="'status-' + item.status">{{ item.status === 'open' ? '未解决' : '已解决' }}</text>
                </view>
                <text class="incident-title">{{ item.title }}</text>
                <view class="incident-meta">
                    <text class="incident-meta-item">{{ item.asset_name || '-' }}</text>
                    <text class="incident-meta-item">告警: {{ item.alert_count || 0 }}</text>
                    <text class="incident-meta-item">{{ item.created_at || '' }}</text>
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
import { getIncidentList } from '@/api/incident.js'

const tabs = [
    { label: '全部', value: '' },
    { label: '未解决', value: 'open' },
    { label: '已解决', value: 'resolved' },
]
const activeTab = ref('')
const list = ref([])
const loading = ref(false)
const loadingMore = ref(false)
const noMore = ref(false)

async function fetchList(reset) {
    if (reset) {
        noMore.value = false
    }
    loading.value = true
    try {
        const data = await getIncidentList(activeTab.value)
        const items = data.incidents || data.items || data || []
        const arr = Array.isArray(items) ? items : []
        list.value = arr
        if (arr.length < 50) noMore.value = true
    } catch (e) {
        uni.showToast({ title: '加载失败', icon: 'none' })
    } finally {
        loading.value = false
    }
}

function switchTab(val) {
    if (activeTab.value === val) return
    activeTab.value = val
    fetchList(true)
}

function loadMore() {
    if (loadingMore.value || noMore.value) return
    loadingMore.value = true
    setTimeout(() => { loadingMore.value = false }, 500)
}

function goCreate() {
    uni.navigateTo({ url: '/pages/incident/create' })
}

function goDetail(id) {
    uni.navigateTo({ url: '/pages/incident/detail?id=' + id })
}

onPullDownRefresh(async () => {
    await fetchList(true)
    uni.stopPullDownRefresh()
})

fetchList(true)
</script>

<style lang="scss" scoped>
.toolbar-row {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 16rpx;
}
.create-btn {
    height: 64rpx;
    line-height: 64rpx;
    padding: 0 32rpx;
    background: $primary;
    color: #fff;
    border-radius: 32rpx;
    font-size: $font-sm;
    border: none;
}
.create-btn::after { border: none; }
.tab-bar {
    display: flex; background: $bg-card-solid; border-radius: $card-radius; padding: 8rpx; margin-bottom: 24rpx;
}
.tab-item {
    flex: 1; height: $tab-height; line-height: $tab-height; text-align: center; border-radius: 36rpx;
}
.tab-item.active { background: $primary; }
.tab-text { font-size: $font-sm; color: $text-secondary; }
.tab-item.active .tab-text { color: #fff; font-weight: 600; }
.list-scroll { height: calc(100vh - 220rpx); }
.incident-card {
    background: $bg-card-solid; border-radius: $card-radius; padding: 28rpx; margin-bottom: 16rpx;
}
.incident-top {
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 16rpx;
}
.incident-sev { padding: 6rpx 20rpx; border-radius: 20rpx; }
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
.incident-title {
    font-size: $font-md; font-weight: 600; color: $text; margin-bottom: 16rpx;
}
.incident-meta { display: flex; gap: 16rpx; flex-wrap: wrap; }
.incident-meta-item { font-size: $font-xs; color: $text-muted; }
.loading-more { text-align: center; padding: 32rpx 0; font-size: $font-sm; }
</style>
