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

export function registerDevice(data) {
  return request({ url: '/mobile/push/register', method: 'POST', data })
}

export function unregisterDevice(deviceId) {
  return request({ url: '/mobile/push/unregister', method: 'POST', data: { device_id: deviceId } })
}

export function diagnose(imageBase64, assetId) {
  return request({ url: '/mobile/vision/diagnose', method: 'POST', data: { image_base64: imageBase64, asset_id: assetId } })
}

export function checkin(data) {
  return request({ url: '/mobile/checkin', method: 'POST', data })
}

export function listDevices() {
  return request({ url: '/mobile/devices' })
}

export function deleteDevice(id) {
  return request({ url: `/mobile/devices/${id}`, method: 'DELETE' })
}

export function listPushLogs() {
  return request({ url: '/mobile/push/logs' })
}

export default {
  registerDevice,
  unregisterDevice,
  diagnose,
  checkin,
  listDevices,
  deleteDevice,
  listPushLogs,
}
