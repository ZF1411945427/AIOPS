<template>
    <view class="page-wrap">
        <view v-if="loading && !dashboard" class="loading-state">
            <text class="text-muted">加载中...</text>
        </view>

        <template v-if="dashboard">
            <HealthCard
                :score="healthScore"
                :trend="''"
                :trendValue="0"
                :onlineCount="onlineAssets"
                :totalCount="totalAssets"
            />

            <view class="card stat-card" @tap="goAlerts">
                <view class="card-title">告警统计</view>
                <view class="stat-grid">
                    <view class="stat-item">
                        <text class="stat-value">{{ alertsTotal }}</text>
                        <text class="stat-label">今日告警</text>
                    </view>
                    <view class="stat-item">
                        <text class="stat-value warn">{{ alertsTriggered }}</text>
                        <text class="stat-label">待处理</text>
                    </view>
                    <view class="stat-item">
                        <text class="stat-value">{{ alertsSuppressed }}</text>
                        <text class="stat-label">已静默</text>
                    </view>
                </view>
            </view>

            <view class="card" @tap="callOncall">
                <view class="card-title">当前值班</view>
                <view class="flex-between">
                    <view class="flex-col">
                        <text class="oncall-name">{{ oncallName }}</text>
                        <text class="oncall-team text-muted">{{ oncallTeam }}</text>
                    </view>
                    <view class="call-btn">
                        <text class="call-icon">拨号</text>
                    </view>
                </view>
            </view>

            <view class="card" @tap="goWorkflow">
                <view class="card-title">运行工作流</view>
                <view class="stat-grid">
                    <view class="stat-item">
                        <text class="stat-value primary">{{ workflowRunning }}</text>
                        <text class="stat-label">运行中</text>
                    </view>
                    <view class="stat-item">
                        <text class="stat-value danger">{{ workflowFailed }}</text>
                        <text class="stat-label">失败</text>
                    </view>
                </view>
            </view>
        </template>

        <view v-else-if="!loading" class="empty-state">
            <text class="empty-icon">📊</text>
            <text class="empty-text">暂无数据，下拉刷新</text>
        </view>

        <ScanFab @click="goScan" />
    </view>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { onShow, onHide, onPullDownRefresh } from '@dcloudio/uni-app'
import { getDashboard } from '@/api/dashboard.js'
import { useUserStore } from '@/store/user.js'
import HealthCard from '@/components/HealthCard.vue'
import ScanFab from '@/components/ScanFab.vue'

const userStore = useUserStore()
const dashboard = ref(null)
const loading = ref(false)
let pollTimer = null

const healthScore = computed(() => {
  const h = dashboard.value && dashboard.value.health
  if (!h) return 0
  return h.avg_sla != null ? h.avg_sla : 0
})
const onlineAssets = computed(() => {
  const a = dashboard.value && dashboard.value.assets
  return a && a.online != null ? a.online : 0
})
const totalAssets = computed(() => {
  const a = dashboard.value && dashboard.value.assets
  return a && a.total != null ? a.total : 0
})
const alertsTotal = computed(() => {
  const a = dashboard.value && dashboard.value.alerts
  return a && a.total != null ? a.total : 0
})
const alertsTriggered = computed(() => {
  const a = dashboard.value && dashboard.value.alerts
  return a && a.triggered != null ? a.triggered : 0
})
const alertsSuppressed = computed(() => {
  const a = dashboard.value && dashboard.value.alerts
  return a && a.suppressed_total != null ? a.suppressed_total : 0
})
const oncallName = computed(() => {
  const o = dashboard.value && dashboard.value.oncall
  return (o && o.current_oncall) || '暂无'
})
const oncallTeam = computed(() => {
  const o = dashboard.value && dashboard.value.oncall
  if (!o) return ''
  return o.team_name || ''
})
const workflowRunning = computed(() => {
  const w = dashboard.value && dashboard.value.workflows
  if (!w) return 0
  return (w.running_sop || 0) + (w.running_agent || 0)
})
const workflowFailed = computed(() => {
  const w = dashboard.value && dashboard.value.workflows
  if (!w) return 0
  return (w.failed_sop || 0) + (w.failed_agent || 0)
})

async function loadData() {
    loading.value = true
    try {
        dashboard.value = await getDashboard()
    } catch (e) {
        if (!userStore.token) return
        uni.showToast({ title: '加载失败', icon: 'none' })
    } finally {
        loading.value = false
    }
}

function startPoll() {
    stopPoll()
    pollTimer = setInterval(loadData, 5000)
}
function stopPoll() {
    if (pollTimer) {
        clearInterval(pollTimer)
        pollTimer = null
    }
}

function callOncall() {
    const o = dashboard.value && dashboard.value.oncall
    const phone = o && o.phone
    if (!phone) {
        uni.showToast({ title: '无联系电话', icon: 'none' })
        return
    }
    uni.makePhoneCall({ phoneNumber: phone })
}

function goWorkflow() {
    uni.navigateTo({ url: '/pages/workflow/list' })
}

function goAlerts() {
    uni.switchTab({ url: '/pages/alert/list' })
}

function goScan() {
    uni.navigateTo({ url: '/pages/asset/scan' })
}

onMounted(loadData)
onShow(() => startPoll())
onHide(() => stopPoll())
onUnmounted(stopPoll)
onPullDownRefresh(async () => {
    await loadData()
    uni.stopPullDownRefresh()
})
</script>

<style lang="scss" scoped>

.loading-state {
    padding: 120rpx 0;
    text-align: center;
}

.card-title {
    font-size: $font-lg;
    font-weight: 600;
    color: $text;
    margin-bottom: 24rpx;
}

.stat-grid {
    display: flex;
    justify-content: space-around;
}

.stat-item {
    display: flex;
    flex-direction: column;
    align-items: center;
}

.stat-value {
    font-size: $font-xl;
    font-weight: 700;
    color: $text;
}

.stat-value.warn {
    color: $warning;
}
.stat-value.primary {
    color: $primary;
}
.stat-value.danger {
    color: $danger;
}

.stat-label {
    font-size: $font-xs;
    color: $text-muted;
    margin-top: 8rpx;
}

.oncall-name {
    font-size: $font-lg;
    font-weight: 600;
    color: $text;
}

.oncall-team {
    font-size: $font-sm;
    margin-top: 4rpx;
}

.call-btn {
    background: $success;
    color: #fff;
    border-radius: $btn-radius;
    padding: 16rpx 36rpx;
}

.call-icon {
    color: #fff;
    font-size: $font-sm;
}
</style>
