<template>
    <view class="page-wrap">
        <view class="hero-card card">
            <text class="hero-title">扫码识别资产</text>
            <text class="hero-desc">扫描二维码或手动输入编码快速定位资产</text>
            <button class="scan-big-btn" @tap="handleScan">
                <text class="scan-big-icon">扫码</text>
                <text class="scan-big-text">点击扫码</text>
            </button>
        </view>

        <view class="card">
            <text class="card-title">手动输入</text>
            <input class="input-field" v-model="code" placeholder="请输入资产编码" />
            <button class="btn-primary" @tap="handleQuery">查询</button>
        </view>

        <view class="card">
            <button class="btn-ghost" @tap="handleNfc">NFC 识别</button>
        </view>

        <view v-if="searching" class="loading-state">
            <text class="text-muted">查询中...</text>
        </view>
    </view>
</template>

<script setup>
import { ref } from 'vue'
import { scanAsset } from '@/api/asset.js'

const code = ref('')
const searching = ref(false)

function handleScan() {
    uni.scanCode({
        onlyFromCamera: false,
        success: (res) => {
            const result = res.result || ''
            if (!result) {
                uni.showToast({ title: '未识别到内容', icon: 'none' })
                return
            }
            queryAsset(result)
        },
        fail: () => {
            uni.showToast({ title: '扫码取消', icon: 'none' })
        },
    })
}

function handleQuery() {
    if (!code.value.trim()) {
        uni.showToast({ title: '请输入编码', icon: 'none' })
        return
    }
    queryAsset(code.value.trim())
}

async function queryAsset(c) {
    searching.value = true
    try {
        const data = await scanAsset(c)
        const asset = data.asset || data
        const assetId = asset && asset.id
        if (assetId) {
            uni.navigateTo({ url: '/pages/asset/detail?id=' + assetId })
        } else {
            uni.showToast({ title: '未找到匹配资产', icon: 'none' })
        }
    } catch (e) {
        const msg = (e && e.data && (e.data.detail || e.data.message)) || '查询失败'
        uni.showToast({ title: String(msg).slice(0, 50), icon: 'none' })
    } finally {
        searching.value = false
    }
}

function handleNfc() {
    uni.showToast({ title: 'NFC 功能开发中', icon: 'none' })
}
</script>

<style lang="scss" scoped>

.hero-card {
    text-align: center;
    padding: 56rpx 32rpx;
}

.hero-title {
    font-size: $font-xl;
    font-weight: 700;
    color: $text;
    display: block;
    margin-bottom: 12rpx;
}

.hero-desc {
    font-size: $font-sm;
    color: $text-muted;
    display: block;
    margin-bottom: 40rpx;
}

.scan-big-btn {
    width: 100%;
    height: 200rpx;
    background: $primary;
    border-radius: $card-radius;
    border: none;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
}
.scan-big-btn::after { border: none; }

.scan-big-icon {
    color: #fff;
    font-size: $font-xl;
    font-weight: 700;
    margin-bottom: 12rpx;
}

.scan-big-text {
    color: rgba(255, 255, 255, 0.9);
    font-size: $font-sm;
}

.card-title {
    font-size: $font-md;
    font-weight: 600;
    color: $text;
    display: block;
    margin-bottom: 20rpx;
}

.btn-primary {
    width: 100%;
    margin-top: 24rpx;
}

.loading-state {
    text-align: center;
    padding: 48rpx 0;
    font-size: $font-sm;
}
</style>
