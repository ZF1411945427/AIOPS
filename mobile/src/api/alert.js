import { buildUrl, commonHeaders } from './config.js'

function request({ url, method, data, header }) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: buildUrl(url),
      method: method || 'GET',
      data: data,
      header: commonHeaders(header),
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) resolve(res.data)
        else reject(res)
      },
      fail: reject,
    })
  })
}

export function getList(params) {
  const qs = []
  if (params) {
    if (params.id) qs.push('id=' + encodeURIComponent(params.id))
    if (params.status) qs.push('status=' + encodeURIComponent(params.status))
    if (params.severity) qs.push('severity=' + encodeURIComponent(params.severity))
    if (params.asset_id) qs.push('asset_id=' + encodeURIComponent(params.asset_id))
    if (params.page) qs.push('page=' + encodeURIComponent(params.page))
    if (params.per_page) qs.push('per_page=' + encodeURIComponent(params.per_page))
    else if (params.page_size) qs.push('per_page=' + encodeURIComponent(params.page_size))
  }
  const suffix = qs.length ? '?' + qs.join('&') : ''
  return request({ url: `/alerts/api/list${suffix}` })
}

export function acknowledge(id) {
  return request({ url: `/alerts/api/${id}/acknowledge`, method: 'POST' })
}

export function resolve(id) {
  return request({ url: `/alerts/api/${id}/resolve`, method: 'POST' })
}

export function triggerHeal(id) {
  return request({ url: `/alerts/api/${id}/heal`, method: 'POST' })
}

export function silence(id, payload) {
  return request({ url: `/alerts/api/${id}/silence`, method: 'POST', data: payload || {} })
}

export function batchAcknowledge(ids) {
  return request({ url: '/alerts/api/batch-acknowledge', method: 'POST', data: { ids } })
}

export function batchResolve(ids) {
  return request({ url: '/alerts/api/batch-resolve', method: 'POST', data: { ids } })
}

export default {
  getList,
  acknowledge,
  resolve,
  triggerHeal,
  silence,
  batchAcknowledge,
  batchResolve,
}
