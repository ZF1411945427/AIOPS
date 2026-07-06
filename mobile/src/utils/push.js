import { registerDevice } from '../api/mobile.js'

export function initPush() {
  return new Promise((resolve, reject) => {
    uni.getProvider({
      service: 'push',
      success: (res) => {
        const provider = res.provider && res.provider[0]
        if (!provider) {
          resolve(null)
          return
        }
        uni.getClientInfo({
          success: (clientInfo) => {
            const data = {
              device_id: clientInfo.clientId || '',
              platform: uni.getSystemInfoSync().platform || 'unknown',
              push_token: clientInfo.pushToken || '',
              app_version: clientInfo.appVersion || '',
            }
            registerDevice(data)
              .then((result) => resolve({ provider, ...data, result }))
              .catch((err) => resolve({ provider, ...data, error: err }))
          },
          fail: () => resolve(null),
        })
      },
      fail: () => resolve(null),
    })
  })
}

export function onPushReceive(callback) {
  uni.onPushMessage((res) => {
    if (res && res.type === 'receive' && typeof callback === 'function') {
      callback(res.data || {})
    }
  })
}

export function onPushClick(callback) {
  uni.onPushMessage((res) => {
    if (res && res.type === 'click' && typeof callback === 'function') {
      const payload = res.data || {}
      const deepLink = payload.deep_link || payload.deeplink || ''
      if (deepLink) {
        const path = deepLink.replace(/^aiops:\/\//, '/')
        uni.navigateTo({
          url: path,
          fail: () => {
            callback(payload)
          },
        })
      } else {
        callback(payload)
      }
    }
  })
}

export default {
  initPush,
  onPushReceive,
  onPushClick,
}
