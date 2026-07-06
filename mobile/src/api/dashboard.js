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

export function getDashboard() {
  return request({ url: '/mobile/dashboard' })
}

export default {
  getDashboard,
}
