import { request } from './request.js'

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
