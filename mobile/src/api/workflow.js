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

export function listRuns(params) {
  const qs = []
  if (params) {
    if (params.status) qs.push('status=' + encodeURIComponent(params.status))
    if (params.page) qs.push('page=' + encodeURIComponent(params.page))
    if (params.per_page) qs.push('per_page=' + encodeURIComponent(params.per_page))
    else if (params.page_size) qs.push('per_page=' + encodeURIComponent(params.page_size))
  }
  const suffix = qs.length ? '?' + qs.join('&') : ''
  return request({ url: `/workflow/api/runs${suffix}` })
}

export function getRunDetail(id) {
  return request({ url: `/workflow/api/runs/${id}` })
}

export function listAgentRuns(params) {
  const qs = []
  if (params) {
    if (params.status) qs.push('status=' + encodeURIComponent(params.status))
    if (params.page) qs.push('page=' + encodeURIComponent(params.page))
    if (params.per_page) qs.push('per_page=' + encodeURIComponent(params.per_page))
    else if (params.page_size) qs.push('per_page=' + encodeURIComponent(params.page_size))
  }
  const suffix = qs.length ? '?' + qs.join('&') : ''
  return request({ url: `/agent-workflow/api/runs${suffix}` })
}

export function getAgentRunDetail(id) {
  return request({ url: `/agent-workflow/api/runs/${id}` })
}

export function retryNode(runId, nodeRunId, type) {
  if (type === 'sop') {
    return request({ url: `/workflow/api/runs/${runId}/node/${nodeRunId}/retry`, method: 'POST' })
  }
  return request({ url: `/agent-workflow/api/runs/${runId}/node/${nodeRunId}/retry`, method: 'POST' })
}

export default {
  listRuns,
  getRunDetail,
  listAgentRuns,
  getAgentRunDetail,
  retryNode,
}
