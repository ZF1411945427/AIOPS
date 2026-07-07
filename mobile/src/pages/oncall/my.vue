<template>
    <view class="page-wrap">
        <view class="card status-card">
            <text class="card-title">当前值班状态</text>
            <view v-if="myOncall" class="oncall-status">
                <view class="status-badge on">
                    <text class="status-badge-text">值班中</text>
                </view>
                <text class="remain-time">剩余 {{ remainText }}</text>
                <button class="handover-btn" @tap="handleHandover">交接班</button>
            </view>
            <view v-else class="oncall-status">
                <view class="status-badge off">
                    <text class="status-badge-text">非值班</text>
                </view>
                <text class="text-muted">当前不在值班</text>
            </view>
        </view>

        <view class="card">
            <text class="card-title">各团队值班</text>
            <view v-if="oncallList.length === 0" class="empty-mini">
                <text class="text-muted">暂无值班信息</text>
            </view>
            <view v-for="(item, idx) in oncallList" :key="idx" class="oncall-item" @tap="callMember(item)">
                <view class="flex-col">
                    <text class="oncall-team-name">{{ item.team_name || item.name || '团队' }}</text>
                    <text class="oncall-member">{{ item.current_oncall || '-' }}</text>
                </view>
                <view class="call-icon">拨号</view>
            </view>
        </view>

        <view class="card">
            <view class="flex-between">
                <text class="card-title">值班日历</text>
                <view class="month-nav">
                    <text class="nav-arrow" @tap="prevMonth">‹</text>
                    <text class="month-text">{{ year }}年{{ month + 1 }}月</text>
                    <text class="nav-arrow" @tap="nextMonth">›</text>
                </view>
            </view>
            <view class="calendar-week">
                <text v-for="(w, idx) in weeks" :key="idx" class="week-label">{{ w }}</text>
            </view>
            <view class="calendar-grid">
                <view
                    v-for="(day, idx) in calendarDays"
                    :key="idx"
                    class="day-cell"
                    :class="{ duty: day && day.duty, empty: !day }"
                >
                    <text v-if="day" class="day-text">{{ day.day }}</text>
                    <view v-if="day && day.duty" class="duty-dot"></view>
                </view>
            </view>
        </view>
    </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onPullDownRefresh } from '@dcloudio/uni-app'
import { getCurrentOncall, listOncall } from '@/api/oncall.js'
import { useUserStore } from '@/store/user.js'
const userStore = useUserStore()
const currentData = ref(null)
const oncallList = ref([])
const myOncall = ref(null)
const year = ref(new Date().getFullYear())
const month = ref(new Date().getMonth())
const weeks = ['日', '一', '二', '三', '四', '五', '六']
const dutyDates = ref({})

const remainText = computed(() => {
    if (!myOncall.value) return '-'
    const end = myOncall.value.current_period_end || myOncall.value.end_time || myOncall.value.ends_at
    if (!end) return '-'
    const diff = new Date(end).getTime() - Date.now()
    if (diff <= 0) return '0小时'
    const h = Math.floor(diff / 3600000)
    const m = Math.floor((diff % 3600000) / 60000)
    return h + '小时' + m + '分'
})

const calendarDays = computed(() => {
    const firstDay = new Date(year.value, month.value, 1).getDay()
    const daysInMonth = new Date(year.value, month.value + 1, 0).getDate()
    const arr = []
    for (let i = 0; i < firstDay; i++) arr.push(null)
    for (let d = 1; d <= daysInMonth; d++) {
        const key = year.value + '-' + String(month.value + 1).padStart(2, '0') + '-' + String(d).padStart(2, '0')
        arr.push({ day: d, duty: !!dutyDates.value[key] })
    }
    return arr
})

async function fetchData() {
    try {
        const [cur, list] = await Promise.all([getCurrentOncall(), listOncall()])
        currentData.value = cur
        let raw = Array.isArray(list) ? list : (list.items || [])
        // 从 members 中提取 phone 挂到 item 顶层，供 callMember 直接取 item.phone
        raw = raw.map((o) => {
            if (!o) return o
            const list = parseMembers(o.members)
            let p = ''
            if (Array.isArray(list)) {
                for (const m of list) {
                    if (typeof m === 'object' && m && (m.phone || m.mobile)) {
                        p = m.phone || m.mobile
                        break
                    }
                }
            }
            return { ...o, phone: p }
        })
        oncallList.value = raw
        const username = userStore.userInfo && (userStore.userInfo.username || userStore.userInfo.name)
        const currentOncallName = (cur && cur.current_oncall) || ''
        myOncall.value = null
        if (username) {
            const mine = oncallList.value.find((o) => {
                if (!o) return false
                if (o.current_oncall === username) return true
                const members = parseMembers(o.members)
                return Array.isArray(members) && members.some((m) => {
                    if (typeof m === 'string') return m === username
                    return m && m.username === username
                })
            })
            myOncall.value = mine || (currentOncallName === username ? cur : null)
        }
        buildDutyDates(oncallList.value, username)
    } catch (e) {
        uni.showToast({ title: '加载失败', icon: 'none' })
    }
}

function parseMembers(m) {
    if (!m) return []
    if (Array.isArray(m)) return m
    if (typeof m === 'string') {
        try {
            const parsed = JSON.parse(m)
            return Array.isArray(parsed) ? parsed : []
        } catch (e) {
            return []
        }
    }
    return []
}

function parseSchedule(s) {
    if (!s) return []
    if (Array.isArray(s)) return s
    if (typeof s === 'string') {
        try {
            const parsed = JSON.parse(s)
            return Array.isArray(parsed) ? parsed : []
        } catch (e) {
            return []
        }
    }
    return []
}

function buildDutyDates(list, username) {
    const map = {}
    const arr = Array.isArray(list) ? list : []
    arr.forEach((o) => {
        if (!o) return
        const schedule = parseSchedule(o.schedule)
        schedule.forEach((entry) => {
            if (!entry) return
            const d = typeof entry === 'string' ? entry : (entry.date || entry.start || entry.time)
            if (typeof d === 'string') map[d.slice(0, 10)] = true
        })
    })
    dutyDates.value = map
}

function prevMonth() {
    month.value--
    if (month.value < 0) {
        month.value = 11
        year.value--
    }
}
function nextMonth() {
    month.value++
    if (month.value > 11) {
        month.value = 0
        year.value++
    }
}

async function callMember(item) {
    let phone = (item && (item.phone || item.mobile)) || extractPhone(item) || findPhoneFromCurrent(item)
    if (!phone) {
        try {
            const cur = await getCurrentOncall()
            phone = (cur && cur.phone) || ''
        } catch (e) {}
    }
    if (!phone) {
        uni.showToast({ title: '暂无联系电话', icon: 'none' })
        return
    }
    uni.makePhoneCall({ phoneNumber: phone })
}


function findPhoneFromCurrent(item) {
    if (!item || !currentData.value || !currentData.value.items) return ''
    const match = currentData.value.items.find(c => c.current_oncall === item.current_oncall)
    return (match && match.phone) || ''
}

function extractPhone(item) {
    if (!item) return ''
    const members = parseMembers(item.members)
    for (const m of members) {
        if (typeof m === 'object' && m && (m.phone || m.mobile)) {
            return m.phone || m.mobile
        }
    }
    return ''
}

function handleHandover() {
    uni.showModal({
        title: '交接班',
        content: '确认进行交接班操作？',
        success: (r) => {
            if (r.confirm) uni.showToast({ title: '交接班已提交', icon: 'success' })
        },
    })
}

onPullDownRefresh(async () => {
    await fetchData()
    uni.stopPullDownRefresh()
})

fetchData()
</script>

<style lang="scss" scoped>
.page-wrap {
    background: #ff00ff !important;
    min-height: 100vh;
}

.card-title {
    font-size: $font-lg;
    font-weight: 600;
    color: $text;
    margin-bottom: 24rpx;
}

.status-card .oncall-status {
    display: flex;
    align-items: center;
    gap: 24rpx;
    flex-wrap: wrap;
}

.status-badge {
    padding: 12rpx 28rpx;
    border-radius: 24rpx;
}
.status-badge.on { background: rgba($success, 0.12); }
.status-badge.off { background: rgba($text-muted, 0.12); }

.status-badge-text {
    font-size: $font-sm;
    font-weight: 600;
}
.status-badge.on .status-badge-text { color: $success; }
.status-badge.off .status-badge-text { color: $text-muted; }

.remain-time {
    font-size: $font-md;
    color: $text;
}

.handover-btn {
    height: 64rpx;
    line-height: 64rpx;
    padding: 0 32rpx;
    background: $primary;
    color: #fff;
    border-radius: 32rpx;
    font-size: $font-sm;
    border: none;
    margin-left: auto;
}
.handover-btn::after { border: none; }

.empty-mini {
    padding: 32rpx 0;
    text-align: center;
    font-size: $font-sm;
}

.oncall-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 24rpx 0;
    border-bottom: 2rpx solid $border;
}

.oncall-team-name {
    font-size: $font-sm;
    color: $text-muted;
    margin-bottom: 4rpx;
}

.oncall-member {
    font-size: $font-md;
    color: $text;
    font-weight: 600;
}

.call-icon {
    background: $success;
    color: #fff;
    font-size: $font-xs;
    padding: 12rpx 28rpx;
    border-radius: 28rpx;
}

.month-nav {
    display: flex;
    align-items: center;
    gap: 16rpx;
}

.nav-arrow {
    font-size: $font-lg;
    color: $primary;
    width: 56rpx;
    text-align: center;
}

.month-text {
    font-size: $font-sm;
    color: $text;
}

.calendar-week {
    display: flex;
    margin-bottom: 16rpx;
}

.week-label {
    flex: 1;
    text-align: center;
    font-size: $font-xs;
    color: $text-muted;
}

.calendar-grid {
    display: flex;
    flex-wrap: wrap;
}

.day-cell {
    width: calc(100% / 7);
    height: 80rpx;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    position: relative;
}

.day-text {
    font-size: $font-sm;
    color: $text;
}

.day-cell.duty .day-text {
    color: $primary;
    font-weight: 700;
}

.duty-dot {
    width: 12rpx;
    height: 12rpx;
    border-radius: 50%;
    background: $primary;
    margin-top: 6rpx;
}

.day-cell.empty {
    background: $bg-card;
    opacity: 0.3;
}
</style>
