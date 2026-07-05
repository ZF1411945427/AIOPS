<template>
  <div class="license-page">
    <div class="page-header">
      <span class="title">授权管理</span>
      <span class="sub">平台授权许可证状态与续期</span>
    </div>

    <el-card class="status-card" v-loading="loading">
      <template #header>
        <div class="card-header">
          <span class="card-title">授权状态</span>
          <el-tag v-if="status.status === 'active'" type="success" effect="dark">已激活</el-tag>
          <el-tag v-else-if="status.status === 'expired'" type="danger" effect="dark">已过期</el-tag>
          <el-tag v-else-if="status.status === 'locked'" type="warning" effect="dark">已锁定</el-tag>
          <el-tag v-else type="info" effect="dark">未授权</el-tag>
        </div>
      </template>

      <div v-if="status.status === 'active' || status.status === 'expired'" class="info-grid">
        <div class="info-item">
          <span class="label">客户名称</span>
          <span class="value">{{ status.customer || '-' }}</span>
        </div>
        <div class="info-item">
          <span class="label">版本</span>
          <span class="value">
            <el-tag size="small" type="primary">{{ status.edition || '-' }}</el-tag>
          </span>
        </div>
        <div class="info-item">
          <span class="label">签发时间</span>
          <span class="value">{{ status.issued_at || '-' }}</span>
        </div>
        <div class="info-item">
          <span class="label">到期时间</span>
          <span class="value" :class="{ 'warn-text': status.remaining_days < 7 }">
            {{ status.expire_at || '-' }}
          </span>
        </div>
        <div class="info-item">
          <span class="label">最大节点数</span>
          <span class="value">{{ status.max_nodes || '-' }}</span>
        </div>
        <div class="info-item">
          <span class="label">剩余天数</span>
          <span class="value" :class="remainingClass">{{ status.remaining_days }} 天</span>
        </div>
        <div class="info-item full">
          <span class="label">机器指纹</span>
          <span class="value mono">{{ status.fingerprint_masked || '-' }}</span>
        </div>
        <div class="info-item full">
          <span class="label">功能模块</span>
          <span class="value">
            <el-tag
              v-for="f in status.features"
              :key="f"
              size="small"
              style="margin: 2px"
            >{{ f }}</el-tag>
            <span v-if="!status.features || !status.features.length">-</span>
          </span>
        </div>
      </div>

      <div v-else class="no-license">
        <el-empty :description="status.reason || '未授权'">
          <template #image>
            <el-icon :size="64" color="var(--text-secondary,#64748b)">
              <Lock />
            </el-icon>
          </template>
        </el-empty>
      </div>

      <div v-if="status.status === 'active' && status.remaining_days < 7" class="warn-box">
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          :title="`授权将在 ${status.remaining_days} 天后到期，请尽快续期`"
        />
      </div>
      <div v-if="status.status === 'expired'" class="warn-box">
        <el-alert
          type="error"
          :closable="false"
          show-icon
          :title="`授权已于 ${status.expire_at} 到期，平台功能已锁定，请上传新许可证`"
        />
      </div>
      <div v-if="status.status === 'locked'" class="warn-box">
        <el-alert
          type="error"
          :closable="false"
          show-icon
          :title="status.reason || '系统时钟异常，平台已锁定'"
        />
      </div>
      <div v-if="status.status === 'invalid'" class="warn-box">
        <el-alert
          type="error"
          :closable="false"
          show-icon
          :title="status.reason || '授权无效'"
        />
      </div>

      <div v-if="status.status === 'active' || status.status === 'expired'" class="progress-box">
        <div class="progress-label">授权有效期进度</div>
        <el-progress
          :percentage="progressPercent"
          :color="progressColor"
          :stroke-width="10"
        />
      </div>
    </el-card>

    <el-card class="upload-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">上传授权文件</span>
          <el-button size="small" @click="loadStatus" :loading="loading">刷新状态</el-button>
        </div>
      </template>

      <el-upload
        drag
        accept=".lic"
        :auto-upload="true"
        :show-file-list="false"
        :http-request="handleUpload"
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">拖拽 .lic 授权文件到此处，或<em>点击选择</em></div>
        <template #tip>
          <div class="el-upload__tip">仅支持由签发工具生成的 .lic 许可证文件</div>
        </template>
      </el-upload>

      <div v-if="uploadMsg" class="upload-msg" :class="uploadOk ? 'ok' : 'err'">
        {{ uploadMsg }}
      </div>
    </el-card>

    <el-card class="fp-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">机器指纹</span>
          <el-button size="small" type="primary" @click="copyFingerprint">复制指纹</el-button>
        </div>
      </template>
      <div class="fp-tip">签发授权时需提供此机器指纹，许可证将绑定本机，拷贝到其他机器无效。</div>
      <div class="fp-value mono">{{ status.fingerprint || '-' }}</div>
      <div class="fp-actions">
        <el-button size="small" @click="copyFingerprint">复制</el-button>
        <el-button size="small" @click="loadStatus">重新获取</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Lock, UploadFilled } from '@element-plus/icons-vue'
import request from '@/api/request'

const loading = ref(false)
const uploadMsg = ref('')
const uploadOk = ref(false)
const status = ref({
  status: 'invalid',
  valid: false,
  reason: '',
  remaining_days: 0,
  fingerprint: '',
  fingerprint_masked: '',
  customer: '',
  edition: '',
  issued_at: '',
  expire_at: '',
  max_nodes: 0,
  features: [],
})

const remainingClass = computed(() => {
  if (status.value.remaining_days < 0) return 'err-text'
  if (status.value.remaining_days < 7) return 'warn-text'
  return ''
})

const progressPercent = computed(() => {
  if (!status.value.issued_at || !status.value.expire_at) return 0
  const start = new Date(status.value.issued_at).getTime()
  const end = new Date(status.value.expire_at).getTime()
  const now = Date.now()
  if (end <= start) return 0
  let p = ((now - start) / (end - start)) * 100
  if (p < 0) p = 0
  if (p > 100) p = 100
  return Math.round(p)
})

const progressColor = computed(() => {
  if (status.value.remaining_days < 7) return '#f59e0b'
  if (status.value.status !== 'active') return '#ef4444'
  return '#10b981'
})

async function loadStatus() {
  loading.value = true
  try {
    const data = await request.get('/license/api/status')
    status.value = data
    uploadMsg.value = ''
  } catch (e) {
    ElMessage.error(e.message || '获取授权状态失败')
  } finally {
    loading.value = false
  }
}

async function handleUpload(option) {
  const file = option.file
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.lic')) {
    ElMessage.warning('请上传 .lic 授权文件')
    return
  }
  const formData = new FormData()
  formData.append('file', file)
  uploadMsg.value = ''
  try {
    const res = await fetch('/license/api/upload', {
      method: 'POST',
      body: formData,
      credentials: 'include',
    })
    const data = await res.json()
    if (data.ok) {
      uploadOk.value = true
      uploadMsg.value = data.message || '授权上传成功'
      ElMessage.success(uploadMsg.value)
      await loadStatus()
    } else {
      uploadOk.value = false
      uploadMsg.value = data.message || '授权上传失败'
      ElMessage.error(uploadMsg.value)
    }
  } catch (e) {
    uploadOk.value = false
    uploadMsg.value = e.message || '上传失败'
    ElMessage.error(uploadMsg.value)
  }
}

async function copyFingerprint() {
  if (!status.value.fingerprint) {
    ElMessage.warning('暂无指纹')
    return
  }
  try {
    await navigator.clipboard.writeText(status.value.fingerprint)
    ElMessage.success('指纹已复制到剪贴板')
  } catch (e) {
    ElMessage.warning('复制失败，请手动选择指纹文本复制')
  }
}

onMounted(() => {
  loadStatus()
})
</script>

<style scoped>
.license-page {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  color: var(--text, #1e293b);
}
.page-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.page-header .title {
  font-size: 20px;
  font-weight: 700;
}
.page-header .sub {
  font-size: 13px;
  color: var(--text-secondary, #64748b);
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.card-title {
  font-weight: 600;
}
.status-card,
.upload-card,
.fp-card {
  background: var(--bg-card, #fff);
  border: 1px solid var(--border, rgba(0, 0, 0, 0.07));
}
.info-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px 24px;
}
.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.info-item.full {
  grid-column: 1 / -1;
}
.info-item .label {
  font-size: 12px;
  color: var(--text-secondary, #64748b);
}
.info-item .value {
  font-size: 14px;
  font-weight: 500;
}
.mono {
  font-family: 'JetBrains Mono', Consolas, monospace;
  letter-spacing: 0.04em;
}
.warn-text {
  color: #f59e0b;
  font-weight: 600;
}
.err-text {
  color: #ef4444;
  font-weight: 600;
}
.no-license {
  padding: 20px 0;
}
.warn-box {
  margin-top: 16px;
}
.progress-box {
  margin-top: 16px;
}
.progress-label {
  font-size: 12px;
  color: var(--text-secondary, #64748b);
  margin-bottom: 8px;
}
.upload-msg {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 6px;
  font-size: 13px;
}
.upload-msg.ok {
  background: rgba(16, 185, 129, 0.1);
  color: #059669;
}
.upload-msg.err {
  background: rgba(239, 68, 68, 0.1);
  color: #dc2626;
}
.fp-tip {
  font-size: 12px;
  color: var(--text-secondary, #64748b);
  margin-bottom: 10px;
}
.fp-value {
  padding: 12px 14px;
  background: rgba(99, 102, 241, 0.06);
  border: 1px solid var(--border, rgba(0, 0, 0, 0.07));
  border-radius: 6px;
  font-size: 14px;
  word-break: break-all;
}
.fp-actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}
</style>
