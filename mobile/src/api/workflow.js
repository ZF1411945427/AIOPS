import { request } from './request.js'

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
