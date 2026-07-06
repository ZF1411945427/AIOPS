import { buildUrl, commonHeaders, setCookie, setBaseURL, setToken } from './config.js'

export function login(username, password, serverUrl) {
  if (serverUrl) setBaseURL(serverUrl)
  return new Promise((resolve, reject) => {
    uni.request({
      url: buildUrl('/login'),
      method: 'POST',
      data: { username, password },
      header: { 'Content-Type': 'application/json' },
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          const data = res.data || {}
          if (data.token) setToken(data.token)
          const setCookieHeader = res.header['Set-Cookie'] || res.header['set-cookie'] || ''
          if (setCookieHeader) {
            const cookie = Array.isArray(setCookieHeader) ? setCookieHeader[0] : setCookieHeader
            setCookie(cookie.split(';')[0])
          }
          resolve(data)
        } else {
          reject(res)
        }
      },
      fail: reject,
    })
  })
}

export function logout() {
  return new Promise((resolve, reject) => {
    uni.request({
      url: buildUrl('/logout'),
      method: 'GET',
      header: commonHeaders(),
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) resolve(res.data)
        else reject(res)
      },
      fail: reject,
    })
  })
}

export function issueBiometric(deviceId) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: buildUrl('/mobile/auth/biometric/issue'),
      method: 'POST',
      data: { device_id: deviceId },
      header: commonHeaders(),
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) resolve(res.data)
        else reject(res)
      },
      fail: reject,
    })
  })
}

export function biometricLogin(token) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: buildUrl('/mobile/auth/biometric'),
      method: 'POST',
      data: { biometric_token: token },
      header: { 'Content-Type': 'application/json' },
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          const data = res.data || {}
          if (data.token) setToken(data.token)
          const setCookieHeader = res.header['Set-Cookie'] || res.header['set-cookie'] || ''
          if (setCookieHeader) {
            const cookie = Array.isArray(setCookieHeader) ? setCookieHeader[0] : setCookieHeader
            setCookie(cookie.split(';')[0])
          }
          resolve(data)
        } else {
          reject(res)
        }
      },
      fail: reject,
    })
  })
}

export function getMe() {
  return new Promise((resolve, reject) => {
    uni.request({
      url: buildUrl('/me'),
      method: 'GET',
      header: commonHeaders(),
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) resolve(res.data)
        else reject(res)
      },
      fail: reject,
    })
  })
}

export default {
  login,
  logout,
  issueBiometric,
  biometricLogin,
  getMe,
}
