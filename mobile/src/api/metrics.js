import { buildUrl, commonHeaders } from './config.js'

function request({ url, method, data }) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: buildUrl(url),
      method: method || 'GET',
      data: data,
      header: commonHeaders(),
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) resolve(res.data)
        else reject(res)
      },
      fail: reject,
    })
  })
}

export function getMetricNames() {
  return request({ url: '/metrics/names' })
}

export function getMetricData({ name, hours }) {
  const qs = []
  if (name) qs.push(`name=${encodeURIComponent(name)}`)
  if (hours) qs.push(`hours=${hours}`)
  const suffix = qs.length ? '?' + qs.join('&') : ''
  return request({ url: `/metrics/data${suffix}` })
}

export function getMetricLatest(assetId) {
  const qs = assetId ? `?asset_id=${assetId}` : ''
  return request({ url: `/metrics/latest${qs}` })
}
