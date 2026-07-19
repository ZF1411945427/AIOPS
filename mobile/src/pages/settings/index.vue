<template>
    <view class="page-wrap">
        <view class="card user-card">
            <view class="avatar">{{ avatarText }}</view>
            <view class="flex-col">
                <text class="user-name">{{ userInfo.username || userInfo.name || '未登录' }}</text>
                <text class="user-role text-muted">{{ userInfo.role || '运维人员' }}</text>
            </view>
        </view>

        <view class="card">
            <view class="setting-row">
                <text class="setting-label">推送通知</text>
                <switch :checked="pushEnabled" @change="togglePush" color="#3B82F6" />
            </view>
            <view class="divider"></view>
            <view class="setting-row" @tap="editServer">
                <text class="setting-label">服务器地址</text>
                <text class="setting-value">{{ serverUrl }}</text>
            </view>
        </view>

        <view class="card">
            <view class="setting-row" @tap="clearCache">
                <text class="setting-label">离线缓存</text>
                <text class="setting-value">{{ cacheSize }}</text>
            </view>
            <view class="divider"></view>
            <text class="setting-label section-title">我的设备</text>
            <view v-if="devices.length === 0" class="empty-mini">
                <text class="text-muted">暂无设备</text>
            </view>
            <view v-for="dev in devices" :key="dev.id" class="device-item">
                <view class="flex-col">
                    <text class="device-name">{{ dev.device_name || dev.device_id || '设备' }}</text>
                    <text class="device-platform text-muted">{{ dev.platform || '' }} {{ dev.app_version || '' }}</text>
                </view>
                <button class="del-btn" @tap="deleteDevice(dev)">删除</button>
            </view>
        </view>

        <view class="card">
            <view class="setting-row">
                <text class="setting-label">关于版本</text>
                <text class="setting-value">v1.0.0</text>
            </view>
        </view>

        <button class="logout-btn" @tap="handleLogout">退出登录</button>
    </view>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { useUserStore } from '@/store/user.js'
import { listDevices, deleteDevice as removeDeviceApi, registerDevice, unregisterDevice } from '@/api/mobile.js'
import { getBaseURL, setBaseURL } from '@/api/config.js'
import { useOfflineStore } from '@/store/offline.js'

const userStore = useUserStore()
const offlineStore = useOfflineStore()
const userInfo = computed(() => userStore.userInfo || {})
const avatarText = computed(() => {
    const n = userInfo.value.username || userInfo.value.name || 'U'
    return n.charAt(0).toUpperCase()
})
const pushEnabled = ref(uni.getStorageSync('push_enabled') !== 'false')
const pushRegistering = ref(false)
const serverUrl = ref(getBaseURL())
const devices = ref([])
const cacheSize = ref('0 KB')

function getDeviceId() {
    let id = uni.getStorageSync('device_id')
    if (!id) {
        id = 'h5-' + Date.now() + '-' + Math.random().toString(36).slice(2, 10)
        uni.setStorageSync('device_id', id)
    }
    return id
}

function getPlatform() {
    try {
        const info = uni.getSystemInfoSync()
        return info.platform || 'h5'
    } catch (e) {
        return 'h5'
    }
}

function getAppVersion() {
    try {
        const info = uni.getSystemInfoSync()
        return info.appVersion || info.appWgtVersion || '1.0.0'
    } catch (e) {
        return '1.0.0'
    }
}

function getPushToken() {
    return new Promise((resolve) => {
        if (typeof uni.getPushClientId === 'function') {
            try {
                uni.getPushClientId({
                    success: (res) => resolve((res && res.cid) || ''),
                    fail: () => resolve(''),
                })
            } catch (e) {
                resolve('')
            }
        } else {
            resolve('')
        }
    })
}

async function togglePush(e) {
    if (pushRegistering.value) return
    const target = e.detail.value
    pushRegistering.value = true
    pushEnabled.value = target
    uni.setStorageSync('push_enabled', target ? 'true' : 'false')
    try {
        const deviceId = getDeviceId()
        const platform = getPlatform()
        const appVersion = getAppVersion()
        // H5/web 端无原生推送通道，仅存本地设置
        if (platform === 'h5' || platform === 'web') {
            uni.showToast({ title: target ? '推送已开启（App 端生效）' : '推送已关闭', icon: 'none' })
            return
        }
        if (target) {
            const pushToken = await getPushToken()
            try {
                await registerDevice({
                    device_id: deviceId,
                    platform: platform,
                    push_token: pushToken || '',
                    app_version: appVersion,
                })
                uni.showToast({ title: '推送已开启', icon: 'success' })
            } catch (err) {
                pushEnabled.value = false
                uni.setStorageSync('push_enabled', 'false')
                uni.showToast({ title: '推送注册失败: ' + (err && err.errMsg ? err.errMsg : '请检查网络'), icon: 'none' })
            }
        } else {
            try {
                await unregisterDevice(deviceId)
                uni.showToast({ title: '推送已关闭', icon: 'none' })
            } catch (err) {
                uni.showToast({ title: '推送已关闭（注销请求失败）', icon: 'none' })
            }
        }
        fetchDevices()
    } finally {
        pushRegistering.value = false
    }
}

function editServer() {
    uni.showModal({
        title: '服务器地址',
        editable: true,
        placeholderText: '请输入服务器地址',
        content: serverUrl.value,
        success: (r) => {
            if (r.confirm && r.content) {
                setBaseURL(r.content)
                serverUrl.value = r.content
                uni.showToast({ title: '已保存', icon: 'success' })
            }
        },
    })
}

function calcCacheSize() {
    try {
        const info = uni.getStorageInfoSync()
        const kb = Math.round((info.currentSize || 0))
        cacheSize.value = kb < 1024 ? kb + ' KB' : (kb / 1024).toFixed(1) + ' MB'
    } catch (e) {
        cacheSize.value = '0 KB'
    }
}

function clearCache() {
    uni.showModal({
        title: '清除缓存',
        content: '确认清除离线缓存数据？',
        success: (r) => {
            if (r.confirm) {
                try {
                    const keys = uni.getStorageInfoSync().keys || []
                    const keep = ['session_cookie', 'auth_token', 'server_base_url', 'biometric_token', 'user_info', 'device_id', 'push_enabled']
                    keys.forEach((k) => {
                        if (keep.indexOf(k) < 0) {
                            uni.removeStorageSync(k)
                        }
                    })
                    calcCacheSize()
                    uni.showToast({ title: '已清除', icon: 'success' })
                } catch (e) {
                    uni.showToast({ title: '清除失败', icon: 'none' })
                }
            }
        },
    })
}

async function fetchDevices() {
    try {
        const data = await listDevices()
        const items = data.items || data.devices || data || []
        devices.value = Array.isArray(items) ? items : []
    } catch (e) {
        devices.value = []
    }
}

async function deleteDevice(dev) {
    uni.showModal({
        title: '删除设备',
        content: '确认删除该设备？删除后将不再接收推送',
        success: async (r) => {
            if (r.confirm) {
                try {
                    await removeDeviceApi(dev.id)
                    uni.showToast({ title: '已删除', icon: 'success' })
                    fetchDevices()
                } catch (e) {}
            }
        },
    })
}

function handleLogout() {
    uni.showModal({
        title: '退出登录',
        content: '确认退出当前账号？',
        success: async (r) => {
            if (r.confirm) {
                try {
                    await userStore.logout()
                    uni.reLaunch({ url: '/pages/login/index' })
                } catch (e) {
                    uni.reLaunch({ url: '/pages/login/index' })
                }
            }
        },
    })
}

onMounted(() => {
    calcCacheSize()
    fetchDevices()
})
onShow(() => {
    calcCacheSize()
})
</script>

<style lang="scss" scoped>

.user-card {
    display: flex;
    align-items: center;
    gap: 24rpx;
}

.avatar {
    width: 96rpx;
    height: 96rpx;
    border-radius: 50%;
    background: $primary;
    color: #fff;
    font-size: $font-xl;
    font-weight: 700;
    line-height: 96rpx;
    text-align: center;
}

.user-name {
    font-size: $font-lg;
    font-weight: 600;
    color: $text;
}

.user-role {
    font-size: $font-sm;
    margin-top: 4rpx;
}

.setting-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16rpx 0;
}

.setting-label {
    font-size: $font-md;
    color: $text;
}

.setting-value {
    font-size: $font-sm;
    color: $text-muted;
}

.section-title {
    display: block;
    margin-top: 16rpx;
    margin-bottom: 16rpx;
}

.empty-mini {
    padding: 24rpx 0;
    text-align: center;
    font-size: $font-sm;
}

.device-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20rpx 0;
    border-bottom: 2rpx solid $border;
}

.device-name {
    font-size: $font-sm;
    color: $text;
}

.device-platform {
    font-size: $font-xs;
    margin-top: 4rpx;
}

.del-btn {
    height: 56rpx;
    line-height: 56rpx;
    padding: 0 24rpx;
    background: transparent;
    color: $danger;
    border-radius: 28rpx;
    font-size: $font-xs;
    border: 2rpx solid $danger;
}
.del-btn::after { border: none; }

.logout-btn {
    width: 100%;
    height: $btn-height;
    line-height: $btn-height;
    background: $bg-card-solid;
    color: $danger;
    border-radius: $btn-radius;
    font-size: $font-lg;
    font-weight: 600;
    margin-top: 24rpx;
    border: none;
}
.logout-btn::after { border: none; }
</style>
