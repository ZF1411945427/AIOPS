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

export function getIncidentList(status) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : ''
  return request({ url: `/incidents/api/list${qs}` })
}

export function getIncidentDetail(id) {
  return request({ url: `/incidents/api/${id}` })
}

export function resolveIncident(id) {
  return request({ url: `/incidents/api/${id}/resolve`, method: 'POST' })
}

export function getIncidentRca(id) {
  return request({ url: `/incidents/api/${id}/rca` })
}
