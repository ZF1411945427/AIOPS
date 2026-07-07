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
    // #ifdef APP-PLUS
    if (uni.getSystemInfoSync().platform === 'android') {
        try {
            const main = plus.android.runtimeMainActivity()
            const Intent = plus.android.importClass('android.content.Intent')
            const NfcAdapter = plus.android.importClass('android.nfc.NfcAdapter')
            const adapter = NfcAdapter.getDefaultAdapter(main)
            if (!adapter) {
                uni.showToast({ title: '设备不支持 NFC', icon: 'none' })
                return
            }
            if (!adapter.isEnabled()) {
                uni.showModal({ title: 'NFC 未开启', content: '请先在系统设置中开启 NFC', showCancel: false })
                return
            }
            uni.showToast({ title: '请将 NFC 标签靠近手机背面', icon: 'none', duration: 3000 })
            // 启用 NFC 读取调度，读取后回调处理
            const tagIntent = new Intent('android.nfc.action.TAG_DISCOVERED')
            main.startActivity(tagIntent)
            // 轮询读取 NFC 标签内容（5秒超时）
            let nfcTimer = null
            nfcTimer = setTimeout(() => {
                uni.showToast({ title: 'NFC 读取超时', icon: 'none' })
            }, 5000)
            // 监听 NFC intent
            plus.globalEvent.addEventListener('newintent', function(e) {
                clearTimeout(nfcTimer)
                const intent = main.getIntent()
                const action = intent.getAction()
                if (action === 'android.nfc.action.TAG_DISCOVERED' || action === 'android.nfc.action.NDEF_DISCOVERED') {
                    const parcelable = intent.getParcelableExtra('android.nfc.extra.TAG')
                    if (parcelable) {
                        const Ndef = plus.android.importClass('android.nfc.tech.Ndef')
                        const ndef = Ndef.get(parcelable)
                        if (ndef) {
                            ndef.connect()
                            const ndefMessage = ndef.getNdefMessage()
                            if (ndefMessage) {
                                const records = ndefMessage.getRecords()
                                if (records && records.length > 0) {
                                    const payload = records[0].getPayload()
                                    const bytes = plus.android.importClass('java.lang.String')
                                    const text = bytes.$new(payload, 'UTF-8')
                                    const code = text.toString().trim()
                                    ndef.close()
                                    if (code) {
                                        queryAsset(code)
                                        return
                                    }
                                }
                            }
                            ndef.close()
                        }
                    }
                    uni.showToast({ title: 'NFC 标签无可用数据', icon: 'none' })
                }
            }, { once: true })
        } catch (err) {
            uni.showToast({ title: 'NFC 读取失败', icon: 'none' })
        }
    } else {
        uni.showToast({ title: 'iOS 暂不支持 NFC 读取', icon: 'none' })
    }
    // #endif
    // #ifndef APP-PLUS
    uni.showToast({ title: '请在 App 中使用 NFC 功能', icon: 'none' })
    // #endif
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
