<template>
    <view class="page-wrap">
        <view class="card">
            <text class="card-title">拍照识障</text>
            <view class="action-row">
                <button class="media-btn" @tap="takePhoto">拍照</button>
                <button class="media-btn" @tap="chooseAlbum">相册</button>
            </view>

            <view v-if="imagePath" class="preview-box">
                <image :src="imagePath" class="preview-img" mode="aspectFit" />
            </view>

            <view v-if="!imagePath" class="empty-preview">
                <text class="text-muted">请拍照或从相册选择图片</text>
            </view>
        </view>

        <view class="card">
            <text class="card-title">关联资产（可选）</text>
            <input class="input-field" v-model="assetId" placeholder="输入资产 ID" />
        </view>

        <button class="btn-primary" :disabled="!imagePath || diagnosing" @tap="handleDiagnose">
            {{ diagnosing ? '诊断中...' : '开始诊断' }}
        </button>

        <view v-if="result" class="card">
            <text class="card-title">诊断结果</text>
            <view class="result-box">
                <text class="result-label">识别结果</text>
                <text class="result-text">{{ result.result || result.diagnosis || '-' }}</text>
            </view>
            <view v-if="result.suggestion || result.advice" class="result-box">
                <text class="result-label">建议处置</text>
                <text class="result-text">{{ result.suggestion || result.advice }}</text>
            </view>
            <view class="result-btns">
                <button class="result-btn heal" @tap="handleHeal">执行自愈</button>
                <button class="result-btn manual" @tap="handleManual">转人工</button>
                <button class="result-btn retake" @tap="handleRetake">重拍</button>
            </view>
        </view>
    </view>
</template>

<script setup>
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { diagnose } from '@/api/mobile.js'

const imagePath = ref('')
const imageBase64 = ref('')
const assetId = ref('')
const result = ref(null)
const diagnosing = ref(false)

function takePhoto() {
    uni.chooseImage({
        count: 1,
        sourceType: ['camera'],
        success: (res) => {
            handleImage(res.tempFilePaths[0])
        },
    })
}

function chooseAlbum() {
    uni.chooseImage({
        count: 1,
        sourceType: ['album'],
        success: (res) => {
            handleImage(res.tempFilePaths[0])
        },
    })
}

function handleImage(path) {
    imagePath.value = path
    result.value = null
    compressImage(path)
}

function compressImage(path) {
    uni.compressImage({
        src: path,
        quality: 60,
        success: (r) => {
            fileToBase64(r.tempFilePath)
        },
        fail: () => {
            fileToBase64(path)
        },
    })
}

function fileToBase64(filePath) {
    // #ifdef H5
    try {
        if (typeof fetch === 'function') {
            fetch(filePath)
                .then((r) => r.blob())
                .then((blob) => {
                    const reader = new FileReader()
                    reader.onloadend = () => {
                        const dataUrl = reader.result
                        imageBase64.value = (dataUrl || '').split(',')[1] || ''
                    }
                    reader.onerror = () => {
                        canvasToBase64(filePath)
                    }
                    reader.readAsDataURL(blob)
                })
                .catch(() => canvasToBase64(filePath))
            return
        }
        canvasToBase64(filePath)
    } catch (e) {
        canvasToBase64(filePath)
    }
    // #endif

    // #ifdef APP-PLUS
    plus.io.resolveLocalFileSystemURL(filePath, (entry) => {
        entry.file((file) => {
            const reader = new plus.io.FileReader()
            reader.onloadend = (e) => {
                const dataUrl = e.target.result
                imageBase64.value = (dataUrl || '').split(',')[1] || dataUrl
            }
            reader.readAsDataURL(file)
        })
    }, () => {
        uni.showToast({ title: '图片处理失败', icon: 'none' })
    })
    // #endif

    // #ifndef H5 || APP-PLUS
    canvasToBase64(filePath)
    // #endif
}

function canvasToBase64(filePath) {
    try {
        uni.getImageInfo({
            src: filePath,
            success: (info) => {
                const canvas = uni.createOffscreenCanvas
                    ? uni.createOffscreenCanvas({ width: info.width, height: info.height, type: '2d' })
                    : null
                if (!canvas) {
                    uni.showToast({ title: '图片处理失败', icon: 'none' })
                    return
                }
                const ctx = canvas.getContext('2d')
                const img = canvas.createImage()
                img.src = filePath
                img.onload = () => {
                    ctx.drawImage(img, 0, 0, info.width, info.height)
                    const dataUrl = canvas.toDataURL('image/jpeg', 0.6)
                    imageBase64.value = (dataUrl || '').split(',')[1] || ''
                }
                img.onerror = () => {
                    uni.showToast({ title: '图片处理失败', icon: 'none' })
                }
            },
            fail: () => {
                uni.showToast({ title: '图片处理失败', icon: 'none' })
            },
        })
    } catch (e) {
        uni.showToast({ title: '图片处理失败', icon: 'none' })
    }
}

async function handleDiagnose() {
    if (!imageBase64.value) {
        uni.showToast({ title: '图片处理中，请稍候', icon: 'none' })
        return
    }
    diagnosing.value = true
    try {
        const data = await diagnose(imageBase64.value, assetId.value || undefined)
        result.value = data
    } catch (e) {
        uni.showToast({ title: '诊断失败：' + (e && e.data && e.data.detail ? e.data.detail : '请重试'), icon: 'none' })
    } finally {
        diagnosing.value = false
    }
}

function handleHeal() {
    uni.showModal({
        title: '执行自愈',
        content: '确认根据诊断结果执行自愈流程？',
        success: (r) => {
            if (r.confirm) uni.showToast({ title: '自愈已触发', icon: 'success' })
        },
    })
}

function handleManual() {
    uni.showToast({ title: '已转人工，请关注后续通知', icon: 'none' })
}

function handleRetake() {
    imagePath.value = ''
    imageBase64.value = ''
    result.value = null
}

onLoad((opts) => {
    if (opts && opts.assetId) assetId.value = opts.assetId
})
</script>

<style lang="scss" scoped>

.card-title {
    font-size: $font-md;
    font-weight: 600;
    color: $text;
    display: block;
    margin-bottom: 24rpx;
}

.action-row {
    display: flex;
    gap: 24rpx;
    margin-bottom: 24rpx;
}

.media-btn {
    flex: 1;
    height: 80rpx;
    line-height: 80rpx;
    background: $bg-card;
    color: $primary;
    border-radius: 40rpx;
    font-size: $font-sm;
    border: none;
}
.media-btn::after { border: none; }

.preview-box {
    width: 100%;
    border-radius: 16rpx;
    overflow: hidden;
}

.preview-img {
    width: 100%;
    height: 400rpx;
}

.empty-preview {
    height: 200rpx;
    display: flex;
    align-items: center;
    justify-content: center;
    background: $bg-card;
    border-radius: 16rpx;
    font-size: $font-sm;
}

.btn-primary {
    width: 100%;
    margin-bottom: 24rpx;
}

.result-box {
    margin-bottom: 24rpx;
}

.result-label {
    font-size: $font-sm;
    color: $text-muted;
    display: block;
    margin-bottom: 8rpx;
}

.result-text {
    font-size: $font-md;
    color: $text;
    line-height: 1.6;
}

.result-btns {
    display: flex;
    gap: 16rpx;
    margin-top: 24rpx;
}

.result-btn {
    flex: 1;
    height: 76rpx;
    line-height: 76rpx;
    border-radius: 38rpx;
    font-size: $font-sm;
    border: none;
}
.result-btn::after { border: none; }

.result-btn.heal { background: $primary; color: #fff; }
.result-btn.manual { background: $warning; color: #fff; }
.result-btn.retake { background: $bg-card; color: $text; }
</style>
