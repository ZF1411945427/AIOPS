<template>
    <view class="page-wrap">
        <view class="tab-bar">
            <view class="tab-item" :class="{ active: activeTab === 'sop' }" @tap="switchTab('sop')">
                <text class="tab-text">SOP 工作流</text>
            </view>
            <view class="tab-item" :class="{ active: activeTab === 'agent' }" @tap="switchTab('agent')">
                <text class="tab-text">智能体工作流</text>
            </view>
        </view>

        <view v-if="list.length === 0 && !loading" class="empty-state">
            <text class="empty-icon">⚙️</text>
            <text class="empty-text">暂无工作流记录</text>
        </view>

        <view v-for="run in list" :key="run.id" class="card">
            <view class="flex-between" @tap="toggleExpand(run.id)">
                <view class="flex-col run-head">
                    <text class="run-title">{{ run.template_name || run.workflow_name || ('Run #' + run.id) }}</text>
                    <text class="run-id text-muted">#{{ run.id }}</text>
                </view>
                <view class="status-badge" :class="'st-' + (run.status || 'pending')">
                    <text class="status-text">{{ run.status || 'pending' }}</text>
                </view>
            </view>

            <view class="run-meta">
                <text class="meta-text">{{ run.triggered_by || '' }}</text>
                <text class="meta-text">{{ run.started_at || run.created_at || '' }}</text>
            </view>

            <view v-if="expandedId === run.id" class="node-list">
                <view v-for="(node, idx) in (run.nodes || run.node_runs || [])" :key="node.id || ('n-' + idx)" class="node-item">
                    <view class="flex-between">
                        <text class="node-name">{{ node.name || node.node_name || ('节点' + (idx + 1)) }}</text>
                        <text class="node-status" :class="'ns-' + (node.status || '')">{{ node.status || '-' }}</text>
                    </view>
                    <text v-if="node.started_at" class="node-duration text-muted">{{ node.started_at }}</text>
                    <button
                        v-if="node.status === 'failed'"
                        class="retry-btn"
                        @tap.stop="handleRetry(run.id, node.id || node.node_run_id)"
                    >
                        重试
                    </button>
                </view>
            </view>
        </view>
    </view>
</template>

<script setup>
import { ref } from 'vue'
import { onPullDownRefresh } from '@dcloudio/uni-app'
import { listRuns, listAgentRuns, retryNode } from '@/api/workflow.js'

const tabs = [
    { value: 'sop', label: 'SOP 工作流' },
    { value: 'agent', label: '智能体工作流' },
]
const activeTab = ref('sop')
const list = ref([])
const loading = ref(false)
const expandedId = ref(null)

async function fetchList() {
    loading.value = true
    try {
        const params = { page: 1, per_page: 30 }
        const data = activeTab.value === 'sop' ? await listRuns(params) : await listAgentRuns(params)
        const items = data.items || data.runs || data || []
        list.value = Array.isArray(items) ? items : []
    } catch (e) {
        uni.showToast({ title: '加载失败', icon: 'none' })
    } finally {
        loading.value = false
    }
}

function switchTab(val) {
    if (activeTab.value === val) return
    activeTab.value = val
    expandedId.value = null
    fetchList()
}

function toggleExpand(id) {
    expandedId.value = expandedId.value === id ? null : id
}

async function handleRetry(runId, nodeRunId) {
    if (!nodeRunId) {
        uni.showToast({ title: '缺少节点信息', icon: 'none' })
        return
    }
    try {
        if (activeTab.value === 'sop') {
            await retryNode(runId, nodeRunId, 'sop')
        } else {
            await retryNode(runId, nodeRunId, 'agent')
        }
        uni.showToast({ title: '已重试', icon: 'success' })
        fetchList()
    } catch (e) {}
}

onPullDownRefresh(async () => {
    await fetchList()
    uni.stopPullDownRefresh()
})

fetchList()
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

.run-head {
    flex: 1;
}

.run-title {
    font-size: $font-md;
    font-weight: 600;
    color: $text;
}

.run-id {
    font-size: $font-xs;
    margin-top: 4rpx;
}

.status-badge {
    padding: 8rpx 20rpx;
    border-radius: 20rpx;
}
.st-completed { background: rgba($success, 0.12); }
.st-failed { background: rgba($danger, 0.12); }
.st-running { background: rgba($primary, 0.12); }
.st-pending { background: rgba($text-muted, 0.12); }

.status-text {
    font-size: $font-xs;
    font-weight: 600;
}
.st-completed .status-text { color: $success; }
.st-failed .status-text { color: $danger; }
.st-running .status-text { color: $primary; }
.st-pending .status-text { color: $text-muted; }

.run-meta {
    display: flex;
    justify-content: space-between;
    margin-top: 16rpx;
}

.meta-text {
    font-size: $font-xs;
    color: $text-muted;
}

.node-list {
    margin-top: 20rpx;
    padding-top: 20rpx;
    border-top: 2rpx solid $border;
}

.node-item {
    padding: 16rpx 0;
    border-bottom: 2rpx solid $border;
}

.node-name {
    font-size: $font-sm;
    color: $text;
}

.node-status {
    font-size: $font-xs;
}
.ns-completed { color: $success; }
.ns-failed { color: $danger; }
.ns-running { color: $primary; }
.ns-pending { color: $text-muted; }

.node-duration {
    font-size: $font-xs;
    display: block;
    margin-top: 4rpx;
}

.retry-btn {
    height: 56rpx;
    line-height: 56rpx;
    padding: 0 24rpx;
    background: $warning;
    color: #fff;
    border-radius: 28rpx;
    font-size: $font-xs;
    margin-top: 12rpx;
    border: none;
}
.retry-btn::after { border: none; }
</style>
