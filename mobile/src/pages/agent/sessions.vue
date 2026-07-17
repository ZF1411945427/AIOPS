<template>
    <view class="page-wrap">
        <view class="page-header">
            <text class="page-title">历史会话</text>
            <text class="page-count">共 {{ sessions.length }} 条</text>
        </view>

        <view v-if="loading" class="loading-state">
            <text class="text-muted">加载中...</text>
        </view>
        <view v-else-if="sessions.length === 0" class="empty-state">
            <text class="empty-icon">💬</text>
            <text class="empty-text">暂无历史会话</text>
        </view>

        <scroll-view v-else scroll-y class="list-scroll">
            <view
                v-for="s in sessions"
                :key="s.id"
                class="session-card"
                @tap="openSession(s)"
            >
                <view class="session-left">
                    <text class="session-title">{{ s.title || '新会话' }}</text>
                    <text class="session-time">{{ formatTime(s.last_message_at || s.created_at) }}</text>
                </view>
                <view class="session-right">
                    <text class="session-delete" @tap.stop="deleteSession(s.id)">删除</text>
                </view>
            </view>
        </scroll-view>
    </view>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const sessions = ref([])
const loading = ref(false)

async function loadSessions() {
    loading.value = true
    try {
        const res = await uni.request({
            url: '/agent/sessions',
            method: 'GET',
        })
        if (res.statusCode === 200 && res.data) {
            sessions.value = res.data.sessions || res.data.items || []
        }
    } catch (e) {
        uni.showToast({ title: '加载失败', icon: 'none' })
    } finally {
        loading.value = false
    }
}

function openSession(s) {
    try {
        const app = getApp()
        if (app) {
            app.globalData = app.globalData || {}
            app.globalData.pendingAgentSessionId = s.id
        }
    } catch (e) {}
    uni.navigateBack()
}

async function deleteSession(id) {
    uni.showModal({
        title: '删除会话',
        content: '确认删除该会话？',
        success: async (r) => {
            if (!r.confirm) return
            try {
                await uni.request({
                    url: `/agent/session/${id}/delete`,
                    method: 'POST',
                })
                sessions.value = sessions.value.filter(s => s.id !== id)
                uni.showToast({ title: '已删除', icon: 'success' })
            } catch (e) {
                uni.showToast({ title: '删除失败', icon: 'none' })
            }
        },
    })
}

function formatTime(ts) {
    if (!ts) return ''
    const d = new Date(ts)
    return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) + ' ' +
        d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

onMounted(loadSessions)
</script>

<style lang="scss" scoped>
.page-wrap {
    background: #f5f7fa;
    min-height: 100vh;
    padding: 0;
}
.page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 32rpx 32rpx 16rpx;
}
.page-title {
    font-size: $font-lg;
    font-weight: 700;
    color: $text;
}
.page-count {
    font-size: $font-xs;
    color: $text-muted;
}
.loading-state {
    text-align: center;
    padding: 120rpx 0;
}
.empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding-top: 160rpx;
}
.empty-icon { font-size: 100rpx; margin-bottom: 20rpx; }
.empty-text { font-size: $font-sm; color: $text-muted; }
.list-scroll {
    height: calc(100vh - 120rpx);
}
.session-card {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #fff;
    padding: 28rpx 32rpx;
    border-bottom: 2rpx solid $border;
}
.session-left {
    flex: 1;
    overflow: hidden;
}
.session-title {
    display: block;
    font-size: $font-md;
    color: $text;
    font-weight: 600;
    margin-bottom: 8rpx;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.session-time {
    font-size: $font-xs;
    color: $text-muted;
}
.session-delete {
    font-size: $font-xs;
    color: $danger;
    padding: 8rpx 16rpx;
}
</style>
