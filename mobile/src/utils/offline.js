export function setCache(key, data, expireMinutes) {
  const item = {
    data: data,
    ts: Date.now(),
    expire: expireMinutes ? expireMinutes * 60 * 1000 : 0,
  }
  try {
    uni.setStorageSync('cache_' + key, item)
  } catch (e) {}
}

export function getCache(key) {
  try {
    const item = uni.getStorageSync('cache_' + key)
    if (!item) return null
    if (item.expire && Date.now() - item.ts > item.expire) {
      uni.removeStorageSync('cache_' + key)
      return null
    }
    return item.data
  } catch (e) {
    return null
  }
}

export function removeCache(key) {
  try {
    uni.removeStorageSync('cache_' + key)
  } catch (e) {}
}

export function checkNetwork() {
  return new Promise((resolve) => {
    uni.getNetworkType({
      success: (res) => {
        resolve(res.networkType)
      },
      fail: () => {
        resolve('none')
      },
    })
  })
}

export function onNetworkChange(callback) {
  uni.onNetworkStatusChange((res) => {
    if (typeof callback === 'function') {
      callback({
        type: res.networkType,
        isConnected: res.isConnected,
      })
    }
  })
}

export default {
  setCache,
  getCache,
  removeCache,
  checkNetwork,
  onNetworkChange,
}
