<template>
    <view class="login-page">
        <view class="hero">
            <view class="logo">AI</view>
            <text class="title">AIOps 移动运维</text>
            <text class="subtitle">智能运维 · 随时随地</text>
        </view>

        <view class="form-card card">
            <view class="field">
                <text class="label">用户名</text>
                <input class="input-field" v-model="username" placeholder="请输入用户名" />
            </view>
            <view class="field">
                <text class="label">密码</text>
                <input class="input-field" v-model="password" password placeholder="请输入密码" />
            </view>

            <view class="server-row flex-between" @tap="showServer = !showServer">
                <text class="server-label">服务器地址</text>
                <text class="server-toggle">{{ showServer ? '收起' : '展开' }}</text>
            </view>
            <view v-if="showServer" class="field">
                <input class="input-field" v-model="serverUrl" placeholder="http://127.0.0.1:8000" />
            </view>

            <button class="btn-primary" :disabled="loading" @tap="handleLogin">
                {{ loading ? '登录中...' : '登录' }}
            </button>

            <view v-if="hasBiometric" class="biometric-row flex-col" @tap="handleBiometric">
                <view class="biometric-icon">指纹</view>
                <text class="biometric-text">使用生物识别登录</text>
            </view>
        </view>

        <text class="copyright">© 2026 AIOps Platform v1.0.0</text>
    </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useUserStore } from '@/store/user.js'
import { getBaseURL } from '@/api/config.js'

const userStore = useUserStore()
const username = ref('')
const password = ref('')
const serverUrl = ref(getBaseURL())
const showServer = ref(false)
const loading = ref(false)

const hasBiometric = computed(() => !!uni.getStorageSync('biometric_token'))

async function handleLogin() {
    if (!username.value || !password.value) {
        uni.showToast({ title: '请输入用户名和密码', icon: 'none' })
        return
    }
    loading.value = true
    try {
        await userStore.login(username.value, password.value, serverUrl.value)
        uni.showToast({ title: '登录成功', icon: 'success' })
        uni.switchTab({ url: '/pages/index/index' })
    } catch (e) {
        uni.showToast({ title: '登录失败：' + (e && e.message ? e.message : '请检查账号'), icon: 'none' })
    } finally {
        loading.value = false
    }
}

async function handleBiometric() {
    try {
        const ok = await userStore.checkBiometric()
        if (ok) {
            uni.showToast({ title: '登录成功', icon: 'success' })
            uni.switchTab({ url: '/pages/index/index' })
        } else {
            uni.showToast({ title: '生物识别登录失败', icon: 'none' })
        }
    } catch (e) {
        uni.showToast({ title: '生物识别登录失败', icon: 'none' })
    }
}
</script>

<style lang="scss" scoped>

.login-page {
    min-height: 100vh;
    background: linear-gradient(180deg, $primary 0%, $primary-dark 40%, $bg 100%);
    padding: 0 48rpx;
    display: flex;
    flex-direction: column;
    align-items: center;
}

.hero {
    width: 100%;
    padding: 140rpx 0 80rpx;
    display: flex;
    flex-direction: column;
    align-items: center;
}

.logo {
    width: 140rpx;
    height: 140rpx;
    border-radius: 36rpx;
    background: rgba(255, 255, 255, 0.2);
    color: #fff;
    font-size: 56rpx;
    font-weight: 800;
    line-height: 140rpx;
    text-align: center;
    margin-bottom: 32rpx;
}

.title {
    color: #fff;
    font-size: $font-xxl;
    font-weight: 700;
    margin-bottom: 12rpx;
}

.subtitle {
    color: rgba(255, 255, 255, 0.8);
    font-size: $font-sm;
}

.form-card {
    width: 100%;
    padding: 40rpx 32rpx;
    margin-top: 20rpx;
}

.field {
    margin-bottom: 28rpx;
}

.label {
    display: block;
    font-size: $font-sm;
    color: $text-secondary;
    margin-bottom: 12rpx;
}

.server-row {
    padding: 16rpx 0;
    margin-bottom: 8rpx;
}

.server-label {
    font-size: $font-sm;
    color: $text-secondary;
}

.server-toggle {
    font-size: $font-sm;
    color: $primary;
}

.btn-primary {
    width: 100%;
    margin-top: 16rpx;
}

.biometric-row {
    align-items: center;
    margin-top: 32rpx;
}

.biometric-icon {
    width: 96rpx;
    height: 96rpx;
    border-radius: 50%;
    background: $bg-card;
    color: $primary;
    font-size: $font-sm;
    line-height: 96rpx;
    text-align: center;
    margin-bottom: 12rpx;
}

.biometric-text {
    font-size: $font-sm;
    color: $text-secondary;
}

.copyright {
    margin-top: auto;
    padding-bottom: 48rpx;
    color: $text-muted;
    font-size: $font-xs;
}
</style>
