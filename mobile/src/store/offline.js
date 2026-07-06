import { defineStore } from 'pinia'
import { ref } from 'vue'

export function useOfflineStore() {
  const offlineQueue = ref([])
  const cache = ref({})

  function loadFromStorage() {
    try {
      offlineQueue.value = uni.getStorageSync('offline_queue') || []
      cache.value = uni.getStorageSync('offline_cache') || {}
    } catch (e) {}
  }

  loadFromStorage()

  function persistQueue() {
    uni.setStorageSync('offline_queue', offlineQueue.value)
  }

  function persistCache() {
    uni.setStorageSync('offline_cache', cache.value)
  }

  function addToQueue(action) {
    offlineQueue.value.push({
      ...action,
      timestamp: Date.now(),
    })
    persistQueue()
  }

  async function flushQueue() {
    const failed = []
    for (const action of offlineQueue.value) {
      try {
        if (typeof action.execute === 'function') {
          await action.execute()
        }
      } catch (e) {
        failed.push(action)
      }
    }
    offlineQueue.value = failed
    persistQueue()
    return { total: offlineQueue.value.length + failed.length, failed: failed.length }
  }

  function cacheAlerts(list) {
    cache.value.alerts = { data: list, ts: Date.now() }
    persistCache()
  }

  function cacheAsset(detail) {
    if (!cache.value.assets) cache.value.assets = {}
    cache.value.assets[detail.id || detail.asset_id] = { data: detail, ts: Date.now() }
    persistCache()
  }

  function getCachedAlerts() {
    const c = cache.value.alerts
    if (!c) return null
    return c.data
  }

  function getCachedAsset(id) {
    const a = cache.value.assets && cache.value.assets[id]
    if (!a) return null
    return a.data
  }

  function clearCache() {
    cache.value = {}
    persistCache()
  }

  return {
    offlineQueue,
    cache,
    addToQueue,
    flushQueue,
    cacheAlerts,
    cacheAsset,
    getCachedAlerts,
    getCachedAsset,
    clearCache,
    loadFromStorage,
  }
}

export default useOfflineStore
