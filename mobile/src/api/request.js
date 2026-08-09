import { buildUrl, commonHeaders } from './config.js'

export function request({ url, method = 'GET', data, header, hideError, timeout }) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: buildUrl(url),
      method,
      data,
      header: commonHeaders(header),
      timeout,
      success: (res) => {
        if (res.statusCode === 401) {
          try {
            uni.removeStorageSync('auth_token')
            uni.removeStorageSync('user_info')
            uni.removeStorageSync('biometric_token')
            uni.removeStorageSync('session_cookie')
          } catch (e) {}
          uni.reLaunch({ url: '/pages/login/index' })
          reject(res)
          return
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
          return
        }
        if (!hideError) {
          const msg = (res.data && (res.data.error || res.data.detail || res.data.message)) || '请求失败'
          uni.showToast({ title: String(msg).slice(0, 50), icon: 'none' })
        }
        reject(res)
      },
      fail: (err) => {
        if (!hideError) uni.showToast({ title: '网络错误', icon: 'none' })
        reject(err)
      },
    })
  })
}

export default request
