import { request } from './request.js'

export function getAssetDetail(assetId) {
  return request({ url: `/assets/api/${assetId}/detail` })
}

export function scanAsset(code) {
  return request({ url: `/mobile/scan/asset?code=${encodeURIComponent(code)}` })
}

export function listAssets(params) {
  const qs = []
  if (params) {
    if (params.search) qs.push('search=' + encodeURIComponent(params.search))
    if (params.ci_type) qs.push('ci_type=' + encodeURIComponent(params.ci_type))
  }
  const suffix = qs.length ? '?' + qs.join('&') : ''
  return request({ url: `/assets/api/list${suffix}` })
}

export function listCiTypes() {
  return request({ url: '/assets/api/ci-types' })
}

export default {
  getAssetDetail,
  scanAsset,
  listAssets,
  listCiTypes,
}
