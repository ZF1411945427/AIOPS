<template>
    <view class="page-wrap">
        <view class="tab-bar">
            <view
                v-for="tab in tabs"
                :key="tab.value"
                class="tab-item"
                :class="{ active: activeTab === tab.value }"
                @tap="switchTab(tab.value)"
            >
                <text class="tab-text">{{ tab.label }}</text>
            </view>
        </view>

        <scroll-view scroll-y class="list-scroll" @scrolltolower="loadMore" lower-threshold="80">
            <view v-if="list.length === 0 && !loading" class="empty-state">
                <text class="empty-icon">🔔</text>
                <text class="empty-text">暂无告警</text>
            </view>

            <AlertCard
                v-for="item in list"
                :key="item.id"
                :alert="item"
                @click="goDetail(item)"
            />

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
import { onLoad, onShow, onPullDownRefresh } from '@dcloudio/uni-app'
import { getList } from '@/api/alert.js'
import { useOfflineStore } from '@/store/offline.js'
import AlertCard from '@/components/AlertCard.vue'

const tabs = [
    { label: '全部', value: 'all' },
    { label: '待处理', value: 'triggered' },
    { label: '已确认', value: 'acknowledged' },
    { label: '已恢复', value: 'resolved' },
]
const activeTab = ref('all')
const list = ref([])
const page = ref(1)
const loading = ref(false)
const loadingMore = ref(false)
const noMore = ref(false)
const PAGE_SIZE = 20
const offlineStore = useOfflineStore()

async function fetchList(reset = false) {
    if (reset) {
        page.value = 1
        noMore.value = false
    }
    loading.value = true
    try {
        const status = activeTab.value === 'all' ? undefined : activeTab.value
        const data = await getList({ status, page: page.value, per_page: PAGE_SIZE })
        const items = data.alerts || data.items || data || []
        const arr = Array.isArray(items) ? items : []
        if (reset) {
            list.value = arr
        } else {
            list.value = list.value.concat(arr)
        }
        if (arr.length < PAGE_SIZE) noMore.value = true
        offlineStore.cacheAlerts(list.value)
    } catch (e) {
        const cached = offlineStore.getCachedAlerts()
        if (cached && cached.length) {
            list.value = cached
            uni.showToast({ title: '使用缓存数据', icon: 'none' })
        } else {
            uni.showToast({ title: '加载失败', icon: 'none' })
        }
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
    page.value++
    fetchList(false).finally(() => {
        loadingMore.value = false
    })
}

function goDetail(item) {
    if (!item || item.id == null) {
        uni.showToast({ title: '告警信息缺失', icon: 'none' })
        return
    }
    try {
        const app = getApp()
        if (app) {
            app.globalData = app.globalData || {}
            app.globalData.currentAlert = item
        }
    } catch (e) {}
    uni.navigateTo({ url: '/pages/alert/detail?id=' + item.id })
}

const TAB_MAP = { all: 'all', triggered: 'triggered', acknowledged: 'acknowledged', resolved: 'resolved', suppressed: 'all' }

function readAlertTab() {
    try {
        const app = typeof getApp === 'function' ? getApp() : null
        const tab = app && app.globalData && app.globalData.alertTab
        if (tab && TAB_MAP[tab]) {
            activeTab.value = TAB_MAP[tab]
            app.globalData.alertTab = null
            return true
        }
    } catch (e) {}
    return false
}

onLoad(() => {
    readAlertTab()
    fetchList(true)
})

onShow(() => {
    if (readAlertTab()) {
        fetchList(true)
    }
})

onPullDownRefresh(async () => {
    await fetchList(true)
    uni.stopPullDownRefresh()
})
</script>

<style lang="scss" scoped>

.tab-bar {
    display: flex;
    background: $bg-card-solid;
    border-radius: $card-radius;
    padding: 8rpx;
    margin-bottom: 24rpx;
}

.tab-item {
    flex: 1;
    height: $tab-height;
    line-height: $tab-height;
    text-align: center;
    border-radius: 36rpx;
}

.tab-item.active {
    background: $primary;
}

.tab-text {
    font-size: $font-sm;
    color: $text-secondary;
}

.tab-item.active .tab-text {
    color: #fff;
    font-weight: 600;
}

.list-scroll {
    height: calc(100vh - 220rpx);
}

.loading-more {
    text-align: center;
    padding: 32rpx 0;
    font-size: $font-sm;
}
</style>
