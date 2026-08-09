import { request } from './request.js'

export function getIncidentList(status, params) {
  const qs = []
  if (status) qs.push('status=' + encodeURIComponent(status))
  if (params) {
    if (params.page) qs.push('page=' + encodeURIComponent(params.page))
    if (params.per_page) qs.push('per_page=' + encodeURIComponent(params.per_page))
    else if (params.page_size) qs.push('per_page=' + encodeURIComponent(params.page_size))
  }
  const suffix = qs.length ? '?' + qs.join('&') : ''
  return request({ url: `/incidents/api/list${suffix}` })
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
