import { md5 } from './crypto.js'

export function checkSupport() {
  return new Promise((resolve) => {
    uni.checkIsSupportSoterAuthentication({
      success: (res) => {
        resolve(res.supportMode || [])
      },
      fail: () => {
        resolve([])
      },
    })
  })
}

export function startAuth() {
  return new Promise((resolve) => {
    uni.startSoterAuthentication({
      requestAuthModes: ['fingerPrint', 'facial'],
      challenge: 'aiops-' + Date.now(),
      authContent: '请验证身份以登录 AIOps',
      success: (res) => {
        resolve(res.errCode === 0)
      },
      fail: () => {
        resolve(false)
      },
    })
  })
}

export function getDeviceId() {
  try {
    const cached = uni.getStorageSync('device_id')
    if (cached) return cached
  } catch (e) {}
  let info = {}
  try {
    info = uni.getSystemInfoSync()
  } catch (e) {}
  const parts = [
    info.brand || '',
    info.model || '',
    info.system || '',
    info.platform || '',
    info.deviceId || '',
    info.deviceModel || '',
  ]
  const id = md5(parts.join('|'))
  try {
    uni.setStorageSync('device_id', id)
  } catch (e) {}
  return id
}

export default {
  checkSupport,
  startAuth,
  getDeviceId,
}
