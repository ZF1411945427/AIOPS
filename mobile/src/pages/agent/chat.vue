<template>
    <view class="chat-page">
        <view class="chat-header">
            <view class="new-session" @tap="newSession">
                <text class="new-icon">+</text>
                <text class="new-text">新会话</text>
            </view>
        </view>

        <view class="msg-list" id="msg-list">
            <view v-if="messages.length === 0" class="welcome">
                <text class="welcome-title">AI 运维助手</text>
                <text class="welcome-desc">我可以帮你分析告警、生成巡检报告、定位根因</text>
            </view>

            <ChatBubble
                v-for="(msg, idx) in messages"
                :key="msg.id || ('msg-' + idx)"
                :role="msg.role"
                :content="msg.content"
                :toolCalls="msg.toolCalls"
            />

            <view v-if="aiPending" class="typing">
                <text class="text-muted">AI 正在输入...</text>
            </view>

            <view v-for="action in pendingActions" :key="'pa-' + (action.id || action.title)" class="action-card card">
                <text class="action-title">{{ action.title || action.action_type || '待确认操作' }}</text>
                <text v-if="action.reason" class="action-target">{{ action.reason }}</text>
                <view class="action-btns">
                    <button class="confirm-btn" @tap="confirmAction(action)">确认执行</button>
                    <button class="reject-btn" @tap="rejectAction(action)">拒绝</button>
                </view>
            </view>

            <view :id="'anchor-bottom'" class="anchor"></view>
        </view>

        <view class="quick-bar">
            <view class="quick-item" @tap="sendQuick('分析告警')">
                <text class="quick-text">分析告警</text>
            </view>
            <view class="quick-item" @tap="sendQuick('生成巡检报告')">
                <text class="quick-text">巡检报告</text>
            </view>
            <view class="quick-item" @tap="sendQuick('根因分析')">
                <text class="quick-text">根因分析</text>
            </view>
        </view>

        <view class="input-bar">
            <view class="voice-btn" @touchstart="startVoice" @touchend="endVoice">
                <text class="voice-icon">🎤</text>
            </view>
            <input class="msg-input" v-model="inputText" placeholder="输入消息..." confirm-type="send" @confirm="send" />
            <button class="send-btn" :disabled="!inputText.trim() || aiPending" @tap="send">发送</button>
        </view>
    </view>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { onShow, onHide } from '@dcloudio/uni-app'
import { sendMessage, confirmPending, cancelPending, listPending, takePendingPreset } from '@/api/agent.js'
import ChatBubble from '@/components/ChatBubble.vue'

const messages = ref([])
const inputText = ref('')
const sessionId = ref('')
const aiPending = ref(false)
const pendingActions = ref([])
const recorderManager = (typeof uni !== 'undefined' && uni.getRecorderManager) ? uni.getRecorderManager() : null
let voiceRecording = false
let msgSeq = 0

function scrollToBottom() {
    nextTick(() => {
        const el = document.getElementById('msg-list')
        if (el) el.scrollTop = el.scrollHeight
    })
}

function pushUser(text) {
    messages.value.push({ id: 'm' + (msgSeq++), role: 'user', content: text, toolCalls: [] })
}

function pushAI() {
    const msg = { id: 'm' + (msgSeq++), role: 'assistant', content: '', toolCalls: [] }
    messages.value.push(msg)
    return msg
}

async function doSend(text) {
    if (!text || aiPending.value) return
    pushUser(text)
    const aiMsg = pushAI()
    aiPending.value = true
    scrollToBottom()
    try {
        const data = await sendMessage({ sessionId: sessionId.value, message: text })
        if (data.session_id) sessionId.value = data.session_id
        aiMsg.content = data.reply || ''
        if (Array.isArray(data.tool_results)) {
            aiMsg.toolCalls = data.tool_results.map((t) => ({
                name: t.tool_name || t.name || t.tool || '工具调用',
                args: t.args || t.arguments || t.request_payload || '',
                result: t.result || t.response_summary || '',
            }))
        }
        if (Array.isArray(data.pending_actions)) {
            for (const a of data.pending_actions) {
                if (a && a.id) pendingActions.value.push(a)
            }
        }
        if (data.error) uni.showToast({ title: '处理失败', icon: 'none' })
    } catch (e) {
        if (!aiMsg.content) aiMsg.content = '请求失败，请重试'
        uni.showToast({ title: '请求失败', icon: 'none' })
    } finally {
        aiPending.value = false
        scrollToBottom()
    }
}

function send() {
    const text = inputText.value.trim()
    if (!text) return
    inputText.value = ''
    doSend(text)
}

function sendQuick(cmd) {
    doSend(cmd)
}

function newSession() {
    messages.value = []
    pendingActions.value = []
    sessionId.value = ''
    aiPending.value = false
    uni.showToast({ title: '已新建会话', icon: 'none' })
}

async function confirmAction(action) {
    if (!action || !action.id) {
        uni.showToast({ title: '操作信息缺失', icon: 'none' })
        return
    }
    try {
        await confirmPending(action.id)
        uni.showToast({ title: '已确认', icon: 'success' })
        pendingActions.value = pendingActions.value.filter((a) => a.id !== action.id)
    } catch (e) {}
}

async function rejectAction(action) {
    if (!action || !action.id) {
        uni.showToast({ title: '操作信息缺失', icon: 'none' })
        return
    }
    try {
        await cancelPending(action.id)
        uni.showToast({ title: '已拒绝', icon: 'none' })
        pendingActions.value = pendingActions.value.filter((a) => a.id !== action.id)
    } catch (e) {}
}

function startVoice() {
    if (!recorderManager) {
        uni.showToast({ title: '当前环境不支持语音', icon: 'none' })
        return
    }
    voiceRecording = true
    recorderManager.start({ duration: 60000, format: 'mp3', sampleRate: 16000, numberOfChannels: 1 })
}

function endVoice() {
    if (!recorderManager || !voiceRecording) return
    voiceRecording = false
    recorderManager.stop()
}

if (recorderManager) {
recorderManager.onStop((res) => {
    if (!res || !res.tempFilePath) {
        uni.showToast({ title: '录音失败', icon: 'none' })
        return
    }
    const fs = uni.getFileSystemManager()
    try {
        const base64 = fs.readFileSync(res.tempFilePath, 'base64')
        transcribeAndSend(base64, res.duration || 0)
    } catch (e) {
        uni.showToast({ title: '读取录音失败', icon: 'none' })
    }
})
}

async function transcribeAndSend(audioBase64, duration) {
    if (duration < 800) {
        uni.showToast({ title: '说话太短', icon: 'none' })
        return
    }
    uni.showLoading({ title: '识别中...' })
    try {
        const { buildUrl, commonHeaders } = await import('@/api/config.js')
        const res = await new Promise((resolve, reject) => {
            uni.request({
                url: buildUrl('/mobile/voice/transcribe'),
                method: 'POST',
                header: commonHeaders(),
                data: { audio_base64: audioBase64 },
                success: (r) => { r.statusCode >= 200 && r.statusCode < 300 ? resolve(r.data) : reject(r) },
                fail: reject,
            })
        })
        const text = (res && (res.text || res.transcript || res.message)) || ''
        if (!text) {
            uni.hideLoading()
            uni.showToast({ title: '未识别到语音', icon: 'none' })
            return
        }
        inputText.value = text
        uni.hideLoading()
        doSend(text)
    } catch (e) {
        uni.hideLoading()
        const msg = (e && e.data && (e.data.detail || e.data.message)) || '语音识别失败'
        uni.showToast({ title: String(msg).slice(0, 50), icon: 'none' })
    }
}

async function loadPending() {
    try {
        const data = await listPending()
        const actions = data.actions || data || []
        if (Array.isArray(actions) && actions.length) {
            pendingActions.value = actions.filter((a) => a && a.id)
        }
    } catch (e) {}
}

onShow(() => {
    try {
        const pb = document.querySelector('uni-page-body')
        if (pb) {
            const navH = document.querySelector('uni-page-head')?.offsetHeight || 44
            const tabH = document.querySelector('uni-tabbar')?.offsetHeight || 50
            pb.style.height = (window.innerHeight - navH - tabH) + 'px'
            pb.style.overflow = 'hidden'
        }
    } catch (e) {}
    loadPending()
    const preset = takePendingPreset()
    if (preset) doSend(preset)
})

onHide(() => {
    try {
        const pb = document.querySelector('uni-page-body')
        if (pb) {
            pb.style.height = ''
            pb.style.overflow = ''
        }
    } catch (e) {}
})
</script>

<style lang="scss" scoped>

.chat-page {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
    background: $bg;
}

.chat-header {
    padding: 16rpx 24rpx;
    background: $bg-card-solid;
    border-bottom: 2rpx solid $border;
}

.new-session {
    display: inline-flex;
    align-items: center;
}

.new-icon {
    color: $primary;
    font-size: $font-lg;
    font-weight: 700;
    margin-right: 8rpx;
}

.new-text {
    color: $primary;
    font-size: $font-sm;
}

.msg-list {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    padding: 24rpx;
}

.welcome {
    text-align: center;
    padding: 120rpx 0;
}

.welcome-title {
    font-size: $font-xl;
    font-weight: 700;
    color: $text;
    display: block;
    margin-bottom: 16rpx;
}

.welcome-desc {
    font-size: $font-sm;
    color: $text-muted;
}

.typing {
    padding: 16rpx 24rpx;
    font-size: $font-sm;
}

.action-card {
    margin: 16rpx 0;
}

.action-title {
    font-size: $font-md;
    font-weight: 600;
    color: $text;
    display: block;
    margin-bottom: 8rpx;
}

.action-target {
    font-size: $font-sm;
    color: $text-secondary;
    display: block;
    margin-bottom: 20rpx;
}

.action-btns {
    display: flex;
    gap: 24rpx;
}

.confirm-btn {
    flex: 1;
    height: 76rpx;
    line-height: 76rpx;
    background: $primary;
    color: #fff;
    border-radius: 38rpx;
    font-size: $font-sm;
    border: none;
}
.confirm-btn::after { border: none; }

.reject-btn {
    flex: 1;
    height: 76rpx;
    line-height: 76rpx;
    background: $bg-card;
    color: $danger;
    border-radius: 38rpx;
    font-size: $font-sm;
    border: none;
}
.reject-btn::after { border: none; }

.anchor {
    height: 4rpx;
}

.quick-bar {
    display: flex;
    flex-shrink: 0;
    padding: 16rpx 24rpx;
    gap: 16rpx;
    background: $bg-card-solid;
}

.quick-item {
    padding: 12rpx 28rpx;
    background: $bg-hover;
    border-radius: 32rpx;
}

.quick-text {
    font-size: $font-xs;
    color: $primary;
}

.input-bar {
    display: flex;
    flex-shrink: 0;
    align-items: center;
    padding: 16rpx 24rpx;
    background: $bg-card-solid;
    border-top: 2rpx solid $border;
    gap: 16rpx;
}

.voice-btn {
    width: 72rpx;
    height: 72rpx;
    line-height: 72rpx;
    text-align: center;
    border-radius: 50%;
    background: $bg-card;
}

.voice-icon {
    font-size: 36rpx;
}

.msg-input {
    flex: 1;
    height: 76rpx;
    background: $bg-card;
    border-radius: 38rpx;
    padding: 0 28rpx;
    font-size: $font-sm;
}

.send-btn {
    height: 76rpx;
    line-height: 76rpx;
    padding: 0 36rpx;
    background: $primary;
    color: #fff;
    border-radius: 38rpx;
    font-size: $font-sm;
    border: none;
}
.send-btn::after { border: none; }
.send-btn[disabled] {
    background: $border;
    color: $text-muted;
}
</style>
