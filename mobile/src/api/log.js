import { buildUrl, commonHeaders } from './config.js'

let cancelMap = {}

function request({ url, method, data, cancelKey }) {
  if (cancelKey && cancelMap[cancelKey]) {
    cancelMap[cancelKey].abort()
  }
  return new Promise((resolve, reject) => {
    const task = uni.request({
      url: buildUrl(url),
      method: method || 'GET',
      data: data,
      header: commonHeaders(),
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) resolve(res.data)
        else reject(res)
      },
      fail: (err) => {
        if (err.errMsg && err.errMsg.indexOf('abort') !== -1) return
        reject(err)
      },
    })
    if (cancelKey) {
      cancelMap[cancelKey] = task
    }
  })
}

export function getLogSources() {
  return request({ url: '/logs/api/sources' })
}

export function searchLogs({ source_id, query, time_range, page, size }) {
  const params = { source_id, query: query || '*', time_range: time_range || '1h', page: page || 1, size: size || 50 }
  const qs = Object.entries(params).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&')
  return request({ url: `/logs/api/search?${qs}`, cancelKey: 'logSearch' })
}
