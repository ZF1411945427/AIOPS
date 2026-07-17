<template>
    <view class="page-wrap">
        <view class="toolbar-fixed">
            <view class="batch-bar" v-if="selected.length">
                <text class="batch-tip">已选 {{ selected.length }} 条</text>
                <button class="batch-btn ack" @tap="batchAck">确认</button>
                <button class="batch-btn resolve" @tap="doBatchResolve">解决</button>
                <button class="batch-btn cancel" @tap="selected = []">取消</button>
            </view>
        </view>

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

            <view v-if="newAlertCount > 0" class="new-alert-bar" @tap="loadNew">
                <text class="new-alert-text">📢 有 {{ newAlertCount }} 条新告警，点击刷新</text>
            </view>

            <view
                v-for="item in list"
                :key="item.id"
                class="alert-row"
                :class="{ selected: selected.includes(item.id) }"
                @tap="toggleSelect(item.id)"
                @longpress="goDetail(item)"
            >
                <view class="alert-checkbox">
                    <view class="checkbox" :class="{ checked: selected.includes(item.id) }"></view>
                </view>
                <AlertCard :alert="item" @click="goDetail(item)" />
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
import { onLoad, onShow, onPullDownRefresh, onHide } from '@dcloudio/uni-app'
import { getList, batchAcknowledge, batchResolve } from '@/api/alert.js'
import { useOfflineStore } from '@/store/offline.js'
import { onWsEvent, connectAlertWs, disconnectAlertWs } from '@/utils/ws.js'
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
const selected = ref([])
const newAlertCount = ref(0)

let unwatchWs = null

function connectWs() {
    try {
        const app = getApp()
        const token = app && app.globalData && app.globalData.token
        connectAlertWs(token || '')
        unwatchWs = onWsEvent((type, data) => {
            if (type === 'alert') {
                if (!list.value.find(a => a.id === data.id)) {
                    newAlertCount.value++
                }
            }
        })
    } catch (e) {}
}

function loadNew() {
    newAlertCount.value = 0
    fetchList(true)
}

function toggleSelect(id) {
    const idx = selected.value.indexOf(id)
    if (idx >= 0) selected.value.splice(idx, 1)
    else selected.value.push(id)
}

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
    selected.value = []
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

async function batchAck() {
    if (!selected.value.length) return
    try {
        await batchAcknowledge(selected.value)
        uni.showToast({ title: '已确认 ' + selected.value.length + ' 条', icon: 'success' })
        selected.value = []
        fetchList(true)
    } catch (e) {
        uni.showToast({ title: '确认失败', icon: 'none' })
    }
}

async function doBatchResolve() {
    if (!selected.value.length) return
    uni.showModal({
        title: '批量解决',
        content: `确认解决选中的 ${selected.value.length} 条告警？`,
        success: async (r) => {
            if (!r.confirm) return
            try {
                await batchResolve(selected.value)
                uni.showToast({ title: '已解决 ' + selected.value.length + ' 条', icon: 'success' })
                selected.value = []
                fetchList(true)
            } catch (e) {
                uni.showToast({ title: '解决失败', icon: 'none' })
            }
        },
    })
}

onLoad(() => {
    readAlertTab()
    fetchList(true)
    connectWs()
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

onHide(() => {
    disconnectAlertWs()
    if (unwatchWs) unwatchWs()
})
</script>

<style lang="scss" scoped>
.toolbar-fixed {
    position: sticky;
    top: 0;
    z-index: 100;
    background: #fff;
}
.batch-bar {
    display: flex;
    align-items: center;
    gap: 16rpx;
    padding: 16rpx 24rpx;
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    border-radius: 12rpx;
    margin-bottom: 12rpx;
}
.batch-tip {
    color: #fff;
    font-size: $font-sm;
    flex: 1;
    font-weight: 600;
}
.batch-btn {
    padding: 8rpx 24rpx;
    border-radius: 20rpx;
    font-size: $font-xs;
    border: none;
    font-weight: 600;
}
.batch-btn.ack { background: rgba(255,255,255,0.25); color: #fff; }
.batch-btn.resolve { background: #fff; color: #6366f1; }
.batch-btn.cancel { background: rgba(255,255,255,0.15); color: rgba(255,255,255,0.7); }
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
.alert-row {
    display: flex;
    align-items: center;
    gap: 12rpx;
}
.alert-row.selected .alert-card-wrap {
    opacity: 0.6;
}
.alert-checkbox {
    flex-shrink: 0;
}
.checkbox {
    width: 36rpx;
    height: 36rpx;
    border: 2px solid $border;
    border-radius: 50%;
    background: #fff;
    transition: all 0.2s;
}
.checkbox.checked {
    background: $primary;
    border-color: $primary;
}
.loading-more {
    text-align: center;
    padding: 32rpx 0;
    font-size: $font-sm;
}
.new-alert-bar {
    background: linear-gradient(135deg, #fef3c7, #fde68a);
    border-radius: 8rpx;
    padding: 16rpx 24rpx;
    margin-bottom: 16rpx;
    text-align: center;
}
.new-alert-text {
    font-size: $font-sm;
    color: #92400e;
    font-weight: 600;
}
</style>
