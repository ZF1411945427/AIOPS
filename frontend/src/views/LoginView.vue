<template>
  <div class="login-page">
    <div class="login-bg-pattern" />

    <div class="login-wrap">
      <!-- Brand side -->
      <div class="brand-col">
        <canvas ref="starCanvas" class="starfield" />
        <div class="brand-inner">
          <div class="brand-logo">
            <span class="logo-mark">AI</span>
            <span class="logo-type">Ops</span>
          </div>

          <div class="brand-slogan">
            <span class="slogan-line slogan-line-top">被动告警到主动防御</span>
            <span class="slogan-line slogan-line-bottom">你的 7×24 运维专家</span>
          </div>

          <p class="brand-tagline">
            全栈可观测 · 智能告警 · 自动化修复 · 根因分析
          </p>

          <div class="brand-divider" />

          <div class="brand-metrics">
            <div class="metric-item">
              <span class="metric-num">99.9%</span>
              <span class="metric-label">系统可用率</span>
            </div>
            <div class="metric-item">
              <span class="metric-num">10K+</span>
              <span class="metric-label">资产纳管</span>
            </div>
            <div class="metric-item">
              <span class="metric-num">500+</span>
              <span class="metric-label">告警规则</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Form side -->
      <div class="form-col">
        <div class="form-inner">
          <div class="form-top">
            <h1 class="form-title">欢迎回来</h1>
            <p class="form-desc">登录 AIOps 智能运维平台</p>
          </div>

          <div v-if="errorMsg" class="form-error">
            <span>{{ errorMsg }}</span>
          </div>

          <el-form
            ref="formRef"
            :model="form"
            :rules="rules"
            class="login-form"
            @submit.prevent="handleLogin"
            label-width="0"
          >
            <el-form-item prop="username">
              <el-input
                v-model="form.username"
                placeholder="用户名"
                size="large"
                class="login-input"
              />
            </el-form-item>

            <el-form-item prop="password">
              <el-input
                v-model="form.password"
                type="password"
                placeholder="密码"
                size="large"
                show-password
                class="login-input"
              />
            </el-form-item>

            <div class="form-options">
              <el-checkbox v-model="form.remember" class="login-checkbox">记住我</el-checkbox>
              <a href="/forgot-password" class="forgot-link">忘记密码？</a>
            </div>

            <el-button
              type="primary"
              native-type="submit"
              class="login-btn"
              :loading="loading"
              round
            >
              {{ loading ? '登录中...' : '登录' }}
            </el-button>
          </el-form>

          <div class="form-links">
            <a href="/product" class="form-link">了解产品 →</a>
            <span class="form-link-sep">·</span>
            <a href="/product/overview" class="form-link">产品全景 →</a>
            <span class="form-link-sep">·</span>
            <a href="/register" class="form-link">注册账号</a>
          </div>
        </div>

        <p class="form-copyright">© {{ year }} AIOps. All rights reserved.</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import request from '@/api/request'

const router = useRouter()
const route = useRoute()
const formRef = ref(null)
const loading = ref(false)
const errorMsg = ref(route.query.error || '')
const year = new Date().getFullYear()

/* ─── Starfield ─── */
const starCanvas = ref(null)
let animId = null

function initStarfield() {
  const canvas = starCanvas.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const dpr = window.devicePixelRatio || 1
  let w = canvas.parentElement.clientWidth
  let h = canvas.parentElement.clientHeight
  canvas.width = w * dpr
  canvas.height = h * dpr
  canvas.style.width = w + 'px'
  canvas.style.height = h + 'px'
  ctx.scale(dpr, dpr)

  const cx = w / 2
  const cy = h / 2
  const MAX_RADIUS = Math.sqrt(w * w + h * h) / 2 + 80

  const stars = []
  const STAR_COUNT = 200
  const BRAND_COLOR = [199, 81, 46]

  for (let i = 0; i < STAR_COUNT; i++) {
    const useBrand = Math.random() < 0.12
    const dist = Math.random() * MAX_RADIUS
    const angle = Math.random() * Math.PI * 2
    stars.push({
      dist,
      angle,
      x: cx + Math.cos(angle) * dist,
      y: cy + Math.sin(angle) * dist,
      r: 0.4 + Math.random() * 2.0,
      baseAlpha: 0.3 + Math.random() * 0.7,
      speed: (0.08 + Math.random() * 0.25) * (1 - dist / MAX_RADIUS * 0.6),
      phase: Math.random() * Math.PI * 2,
      color: useBrand ? BRAND_COLOR : null,
    })
  }

  function draw(t) {
    ctx.clearRect(0, 0, w, h)

    for (const s of stars) {
      s.angle += s.speed * 0.016
      s.x = cx + Math.cos(s.angle) * s.dist
      s.y = cy + Math.sin(s.angle) * s.dist

      if (s.x < -50 || s.x > w + 50 || s.y < -50 || s.y > h + 50) {
        s.dist = Math.random() * MAX_RADIUS
        s.angle = Math.random() * Math.PI * 2
        s.x = cx + Math.cos(s.angle) * s.dist
        s.y = cy + Math.sin(s.angle) * s.dist
      }

      const a = s.baseAlpha * (0.5 + 0.5 * Math.sin(t * 1.2 + s.phase))
      ctx.beginPath()
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2)
      if (s.color) {
        ctx.fillStyle = `rgba(${s.color[0]},${s.color[1]},${s.color[2]},${a})`
      } else {
        ctx.fillStyle = `rgba(255,255,255,${a})`
      }
      ctx.fill()
    }
  }

  let start = null
  function loop(ts) {
    if (!start) start = ts
    draw((ts - start) / 1000)
    animId = requestAnimationFrame(loop)
  }

  animId = requestAnimationFrame(loop)

  const ro = new ResizeObserver(() => {
    w = canvas.parentElement.clientWidth
    h = canvas.parentElement.clientHeight
    canvas.width = w * dpr
    canvas.height = h * dpr
    canvas.style.width = w + 'px'
    canvas.style.height = h + 'px'
    ctx.scale(dpr, dpr)
  })
  ro.observe(canvas.parentElement)
  return ro
}

let resizeObserver = null

onMounted(() => {
  resizeObserver = initStarfield()
})

onBeforeUnmount(() => {
  if (animId) cancelAnimationFrame(animId)
  if (resizeObserver) resizeObserver.disconnect()
})

const form = reactive({
  username: '',
  password: '',
  remember: false,
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  errorMsg.value = ''

  try {
    const res = await request.post('/login', {
      username: form.username,
      password: form.password,
    })
    if (res?.ok || res?.success) {
      ElMessage.success('登录成功')
      router.push('/')
    } else {
      errorMsg.value = res?.message || '登录失败，请检查用户名和密码'
    }
  } catch (e) {
    errorMsg.value = e.message || '登录失败，请检查网络连接'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  position: relative;
  width: 100%;
  min-height: 100vh;
  display: flex;
  background: #F8F9FA;
  font-family: 'Plus Jakarta Sans', -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  overflow: hidden;
}

.login-bg-pattern {
  position: absolute;
  inset: 0;
  background-image:
    radial-gradient(circle at 20% 50%, rgba(199,81,46,0.03) 0%, transparent 50%),
    radial-gradient(circle at 80% 20%, rgba(13,148,136,0.03) 0%, transparent 50%),
    radial-gradient(circle at 50% 80%, rgba(199,81,46,0.02) 0%, transparent 50%);
  pointer-events: none;
}

.login-wrap {
  position: relative;
  z-index: 1;
  display: flex;
  width: 100%;
  min-height: 100vh;
}

/* ─── Brand side ─── */
.brand-col {
  flex: 0 0 65%;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 96px 64px;
  background: linear-gradient(160deg, #111827 0%, #1F2937 100%);
  position: relative;
  overflow: hidden;
}

.brand-col::before {
  content: '';
  position: absolute;
  top: -40%;
  right: -20%;
  width: 600px;
  height: 600px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(199,81,46,0.15) 0%, transparent 70%);
  pointer-events: none;
}

.brand-col::after {
  content: '';
  position: absolute;
  bottom: -30%;
  left: -10%;
  width: 400px;
  height: 400px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(13,148,136,0.1) 0%, transparent 70%);
  pointer-events: none;
}

.starfield {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 0;
}

.brand-inner {
  position: relative;
  z-index: 1;
  max-width: 480px;
  width: 100%;
}

.brand-logo {
  display: flex;
  align-items: baseline;
  gap: 0;
  margin-bottom: 48px;
}

.logo-mark {
  font-size: 28px;
  font-weight: 800;
  color: #C7512E;
  letter-spacing: -0.02em;
}

.logo-type {
  font-size: 28px;
  font-weight: 400;
  color: rgba(255,255,255,0.6);
  letter-spacing: -0.02em;
}

.brand-slogan {
  display: flex;
  flex-direction: column;
  gap: 0;
  margin-bottom: 20px;
}

.slogan-line {
  font-size: clamp(36px, 4vw, 52px);
  font-weight: 700;
  line-height: 1.15;
  letter-spacing: -0.03em;
  color: #FFFFFF;
}

.slogan-line-bottom {
  color: #C7512E;
  font-weight: 800;
}

.brand-tagline {
  font-size: 15px;
  color: rgba(255,255,255,0.5);
  line-height: 1.6;
  margin-bottom: 40px;
  max-width: 360px;
}

.brand-divider {
  width: 48px;
  height: 3px;
  background: #C7512E;
  border-radius: 2px;
  margin-bottom: 32px;
}

.brand-metrics {
  display: flex;
  gap: 40px;
}

.metric-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metric-num {
  font-size: 28px;
  font-weight: 700;
  color: #FFFFFF;
  letter-spacing: -0.02em;
  line-height: 1;
}

.metric-label {
  font-size: 12px;
  color: rgba(255,255,255,0.4);
  font-weight: 500;
}

/* ─── Form side ─── */
.form-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  align-items: center;
  padding: 96px 80px 64px;
  background: #F8F9FA;
}

.form-inner {
  width: 100%;
  max-width: 360px;
  flex: 1;
}

.form-top {
  margin-bottom: 40px;
}

.form-title {
  font-size: 28px;
  font-weight: 700;
  color: #111827;
  letter-spacing: -0.02em;
  margin-bottom: 8px;
}

.form-desc {
  font-size: 15px;
  color: #6B7280;
  line-height: 1.5;
}

.form-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 24px;
  color: #DC2626;
  background: rgba(220,38,38,0.06);
  border: 1px solid rgba(220,38,38,0.1);
}

/* ─── Form fields ─── */
.login-form {
  width: 100%;
}

.login-form :deep(.el-form-item) {
  margin-bottom: 20px;
}

.login-form :deep(.el-input__wrapper) {
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  box-shadow: none;
  border-radius: 10px;
  padding: 4px 16px;
  transition: border-color 0.2s, box-shadow 0.2s;
  height: 50px;
}

.login-form :deep(.el-input__wrapper:hover) {
  border-color: #9CA3AF;
}

.login-form :deep(.el-input__wrapper.is-focus) {
  border-color: #C7512E;
  box-shadow: 0 0 0 3px rgba(199,81,46,0.08);
}

.login-form :deep(.el-input__inner) {
  color: #111827;
  font-size: 14px;
  font-weight: 500;
  font-family: inherit;
}

.login-form :deep(.el-input__inner::placeholder) {
  color: #9CA3AF;
  font-weight: 400;
}

.form-options {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 28px;
}

.login-checkbox :deep(.el-checkbox__label) {
  font-size: 13px;
  color: #6B7280;
  font-weight: 500;
}

.login-checkbox :deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
  background: #C7512E;
  border-color: #C7512E;
}

.forgot-link {
  font-size: 13px;
  color: #9CA3AF;
  text-decoration: none;
  transition: color 0.2s;
  font-weight: 500;
}

.forgot-link:hover {
  color: #C7512E;
}

.login-btn {
  width: 100%;
  height: 50px;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.5px;
  background: #111827;
  border: none;
  border-radius: 10px;
  transition: all 0.2s;
  font-family: inherit;
}

.login-btn:hover {
  background: #1F2937;
  box-shadow: 0 4px 16px rgba(0,0,0,0.1);
}

.login-btn:active {
  transform: scale(0.98);
}

.login-btn :deep(.el-button__loading) {
  font-size: 14px;
}

.form-links {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12px;
  margin-top: 32px;
}

.form-link {
  font-size: 13px;
  color: #9CA3AF;
  text-decoration: none;
  transition: color 0.2s;
  font-weight: 500;
}

.form-link:hover {
  color: #C7512E;
}

.form-link-sep {
  color: #D1D5DB;
  font-size: 13px;
}

.form-copyright {
  text-align: center;
  color: #D1D5DB;
  font-size: 12px;
  margin-top: auto;
  padding-top: 48px;
}

/* ─── Responsive ─── */
@media (max-width: 900px) {
  .login-wrap {
    flex-direction: column;
  }

  .brand-col {
    flex: none;
    padding: 48px 32px;
    min-height: 40vh;
  }

  .brand-logo {
    margin-bottom: 40px;
  }

  .brand-metrics {
    gap: 24px;
  }

  .metric-num {
    font-size: 22px;
  }

  .brand-col::before,
  .brand-col::after {
    display: none;
  }

  .form-col {
    padding: 48px 32px;
  }

  .form-copyright {
    padding-top: 32px;
  }
}
</style>
