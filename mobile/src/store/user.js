import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as authApi from '../api/auth.js'
import { getDeviceId, checkSupport, startAuth } from '../utils/biometric.js'

export function useUserStore() {
  const token = ref('')
  const userInfo = ref(null)
  const biometricToken = ref('')
  const serverUrl = ref('')
  const deviceId = ref('')

  function loadFromStorage() {
    try {
      token.value = uni.getStorageSync('auth_token') || ''
      userInfo.value = uni.getStorageSync('user_info') || null
      biometricToken.value = uni.getStorageSync('biometric_token') || ''
      serverUrl.value = uni.getStorageSync('server_base_url') || ''
      deviceId.value = uni.getStorageSync('device_id') || ''
    } catch (e) {}
  }

  loadFromStorage()

  async function login(username, password, url) {
    serverUrl.value = url || serverUrl.value
    const data = await authApi.login(username, password, serverUrl.value)
    const t = data && data.token ? data.token : ''
    token.value = t
    userInfo.value = data && data.user ? data.user : data
    if (t) uni.setStorageSync('auth_token', t)
    if (userInfo.value) uni.setStorageSync('user_info', userInfo.value)
    try {
      await issueBiometricIfNeeded()
    } catch (e) {}
    return data
  }

  async function issueBiometricIfNeeded() {
    const support = await checkSupport()
    if (!support || !support.length) return
    const did = ensureDeviceId()
    const data = await authApi.issueBiometric(did)
    const bt = data && data.biometric_token ? data.biometric_token : (data && data.token ? data.token : '')
    if (bt) saveBiometric(bt)
  }

  async function logout() {
    try {
      await authApi.logout()
    } catch (e) {}
    token.value = ''
    userInfo.value = null
    biometricToken.value = ''
    try {
      uni.removeStorageSync('auth_token')
      uni.removeStorageSync('user_info')
      uni.removeStorageSync('biometric_token')
      uni.removeStorageSync('session_cookie')
    } catch (e) {}
  }

  function checkLogin() {
    loadFromStorage()
    if (!token.value) {
      uni.reLaunch({ url: '/pages/login/index' })
      return false
    }
    return true
  }

  function saveBiometric(t) {
    biometricToken.value = t
    uni.setStorageSync('biometric_token', t)
  }

  async function checkBiometric() {
    if (!biometricToken.value) return false
    try {
      const support = await checkSupport()
      if (!support || !support.length) return false
      const authResult = await startAuth()
      if (!authResult) return false
      const data = await authApi.biometricLogin(biometricToken.value)
      const tk = data && data.token ? data.token : ''
      token.value = tk
      userInfo.value = data && data.user ? data.user : data
      if (tk) uni.setStorageSync('auth_token', tk)
      if (userInfo.value) uni.setStorageSync('user_info', userInfo.value)
      return true
    } catch (e) {
      return false
    }
  }

  async function biometricLogin() {
    return checkBiometric()
  }

  function ensureDeviceId() {
    if (!deviceId.value) {
      deviceId.value = getDeviceId()
      uni.setStorageSync('device_id', deviceId.value)
    }
    return deviceId.value
  }

  return {
    token,
    userInfo,
    biometricToken,
    serverUrl,
    deviceId,
    login,
    logout,
    checkLogin,
    saveBiometric,
    checkBiometric,
    biometricLogin,
    ensureDeviceId,
    issueBiometricIfNeeded,
    loadFromStorage,
  }
}

export default useUserStore
