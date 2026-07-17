<template>
    <view class="page-wrap">
        <view class="form-card">
            <view class="form-item">
                <text class="form-label">标题 *</text>
                <input v-model="form.title" class="form-input" placeholder="请输入故障单标题" />
            </view>

            <view class="form-item">
                <text class="form-label">严重级别 *</text>
                <view class="sev-picker">
                    <view
                        v-for="s in severityOptions"
                        :key="s.value"
                        class="sev-option"
                        :class="{ active: form.severity === s.value }"
                        @tap="form.severity = s.value"
                    >
                        <text class="sev-dot" :class="'dot-' + s.value"></text>
                        <text class="sev-name">{{ s.label }}</text>
                    </view>
                </view>
            </view>

            <view class="form-item">
                <text class="form-label">影响范围</text>
                <input v-model="form.impact" class="form-input" placeholder="如: 订单支付服务" />
            </view>

            <view class="form-item">
                <text class="form-label">紧急联系人</text>
                <input v-model="form.contact" class="form-input" placeholder="姓名 + 电话" />
            </view>

            <view class="form-item">
                <text class="form-label">描述</text>
                <textarea v-model="form.description" class="form-textarea" placeholder="请详细描述故障现象..." />
            </view>

            <view class="form-item">
                <text class="form-label">关联资产</text>
                <input v-model="assetKeyword" class="form-input" placeholder="搜索资产名称或IP" @confirm="searchAsset" />
                <view v-if="assetResults.length" class="asset-list">
                    <view
                        v-for="a in assetResults"
                        :key="a.id"
                        class="asset-item"
                        @tap="selectAsset(a)"
                    >
                        <text class="asset-name">{{ a.name }}</text>
                        <text class="asset-ip">{{ a.ip || '-' }}</text>
                    </view>
                </view>
                <view v-if="form.asset_id" class="selected-asset">
                    <text class="sel-label">已选:</text>
                    <text class="sel-name">{{ form.asset_name }}</text>
                    <text class="sel-remove" @tap="form.asset_id = null; form.asset_name = ''">✕</text>
                </view>
            </view>
        </view>

        <view class="submit-row">
            <button class="submit-btn" :disabled="submitting" @tap="submit">
                {{ submitting ? '提交中...' : '提交故障单' }}
            </button>
        </view>
    </view>
</template>

<script setup>
import { ref } from 'vue'

const severityOptions = [
    { label: '严重', value: 'critical' },
    { label: '警告', value: 'warning' },
    { label: '提示', value: 'info' },
]

const form = ref({
    title: '',
    severity: 'warning',
    impact: '',
    contact: '',
    description: '',
    asset_id: null,
    asset_name: '',
})

const assetKeyword = ref('')
const assetResults = ref([])
const submitting = ref(false)

async function searchAsset() {
    if (!assetKeyword.value.trim()) return
    try {
        const res = await uni.request({
            url: '/assets/api/list',
            method: 'GET',
            data: { keyword: assetKeyword.value, per_page: 10 },
        })
        if (res.statusCode === 200 && res.data) {
            assetResults.value = res.data.items || res.data.assets || []
        }
    } catch (e) {
        assetResults.value = []
    }
}

function selectAsset(a) {
    form.value.asset_id = a.id
    form.value.asset_name = a.name
    assetResults.value = []
    assetKeyword.value = ''
}

async function submit() {
    if (!form.value.title.trim()) {
        uni.showToast({ title: '请输入标题', icon: 'none' })
        return
    }
    submitting.value = true
    try {
        const res = await uni.request({
            url: '/incidents/api/create',
            method: 'POST',
            data: {
                title: form.value.title,
                severity: form.value.severity,
                impact: form.value.impact,
                contact: form.value.contact,
                description: form.value.description,
                asset_id: form.value.asset_id,
            },
        })
        if (res.statusCode === 200 || res.statusCode === 201) {
            uni.showToast({ title: '提交成功', icon: 'success' })
            setTimeout(() => uni.navigateBack(), 1000)
        } else {
            uni.showToast({ title: '提交失败', icon: 'none' })
        }
    } catch (e) {
        uni.showToast({ title: '提交失败', icon: 'none' })
    } finally {
        submitting.value = false
    }
}
</script>

<style lang="scss" scoped>
.page-wrap {
    padding: 24rpx;
    background: #f5f7fa;
    min-height: 100vh;
}
.form-card {
    background: #fff;
    border-radius: $card-radius;
    padding: 32rpx;
    margin-bottom: 32rpx;
}
.form-item {
    margin-bottom: 32rpx;
}
.form-label {
    display: block;
    font-size: $font-sm;
    color: $text-secondary;
    margin-bottom: 12rpx;
    font-weight: 600;
}
.form-input {
    width: 100%;
    height: 80rpx;
    border: 1px solid $border;
    border-radius: 8rpx;
    padding: 0 20rpx;
    font-size: $font-sm;
    box-sizing: border-box;
    background: #fafafa;
}
.form-input:focus {
    border-color: $primary;
    background: #fff;
}
.form-textarea {
    width: 100%;
    min-height: 200rpx;
    border: 1px solid $border;
    border-radius: 8rpx;
    padding: 20rpx;
    font-size: $font-sm;
    box-sizing: border-box;
    background: #fafafa;
    line-height: 1.6;
}
.sev-picker {
    display: flex;
    gap: 24rpx;
}
.sev-option {
    display: flex;
    align-items: center;
    gap: 12rpx;
    padding: 12rpx 24rpx;
    border: 1px solid $border;
    border-radius: 8rpx;
    background: #fafafa;
}
.sev-option.active {
    border-color: $primary;
    background: rgba($primary, 0.06);
}
.sev-dot {
    width: 16rpx;
    height: 16rpx;
    border-radius: 50%;
}
.dot-critical { background: $danger; }
.dot-warning { background: $warning; }
.dot-info { background: $info; }
.sev-name {
    font-size: $font-sm;
    color: $text;
}
.asset-list {
    margin-top: 12rpx;
    background: #fff;
    border: 1px solid $border;
    border-radius: 8rpx;
    overflow: hidden;
}
.asset-item {
    display: flex;
    justify-content: space-between;
    padding: 20rpx 24rpx;
    border-bottom: 1px solid $border;
}
.asset-item:last-child { border-bottom: none; }
.asset-name {
    font-size: $font-sm;
    color: $text;
    font-weight: 500;
}
.asset-ip {
    font-size: $font-xs;
    color: $text-muted;
}
.selected-asset {
    display: flex;
    align-items: center;
    gap: 12rpx;
    margin-top: 12rpx;
    padding: 12rpx 20rpx;
    background: rgba($primary, 0.06);
    border-radius: 8rpx;
}
.sel-label {
    font-size: $font-xs;
    color: $text-muted;
}
.sel-name {
    flex: 1;
    font-size: $font-sm;
    color: $primary;
    font-weight: 500;
}
.sel-remove {
    color: $text-muted;
    font-size: $font-sm;
    padding: 4rpx 12rpx;
}
.submit-row {
    padding: 0 32rpx;
}
.submit-btn {
    width: 100%;
    height: 88rpx;
    line-height: 88rpx;
    background: $primary;
    color: #fff;
    border-radius: 44rpx;
    font-size: $font-md;
    font-weight: 600;
    border: none;
    text-align: center;
}
.submit-btn::after { border: none; }
.submit-btn[disabled] {
    opacity: 0.6;
}
</style>
