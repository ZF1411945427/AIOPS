import { buildUrl, commonHeaders } from './config.js'

let pendingPreset = ''

export function setPendingPreset(text) {
  pendingPreset = text || ''
}

export function takePendingPreset() {
  const text = pendingPreset
  pendingPreset = ''
  return text
}

export function listSessions() {
  return new Promise((resolve, reject) => {
    uni.request({
      url: buildUrl('/agent/sessions'),
      method: 'GET',
      header: commonHeaders(),
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) resolve(res.data || {})
        else reject(res)
      },
      fail: reject,
    })
  })
}

export function getHistory(sessionId) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: buildUrl(`/agent/history/${sessionId}`),
      method: 'GET',
      header: commonHeaders(),
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) resolve(res.data || {})
        else reject(res)
      },
      fail: reject,
    })
  })
}

export function sendMessage({ sessionId, message }) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: buildUrl('/agent/chat/send'),
      method: 'POST',
      timeout: 120000,
      header: commonHeaders(),
      data: { session_id: sessionId || null, message },
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) resolve(res.data)
        else reject(res)
      },
      fail: reject,
    })
  })
}

export function confirmPending(actionId) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: buildUrl(`/agent/pending/${actionId}/confirm`),
      method: 'POST',
      header: commonHeaders(),
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) resolve(res.data)
        else reject(res)
      },
      fail: reject,
    })
  })
}

export function cancelPending(actionId) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: buildUrl(`/agent/pending/${actionId}/cancel`),
      method: 'POST',
      header: commonHeaders(),
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) resolve(res.data)
        else reject(res)
      },
      fail: reject,
    })
  })
}

export function listPending() {
  return new Promise((resolve, reject) => {
    uni.request({
      url: buildUrl('/agent/api/pending'),
      method: 'GET',
      header: commonHeaders(),
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) resolve(res.data || { actions: [] })
        else reject(res)
      },
      fail: reject,
    })
  })
}

export function pendingStatus(actionId) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: buildUrl(`/agent/pending/${actionId}/status`),
      method: 'GET',
      header: commonHeaders(),
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) resolve(res.data || {})
        else reject(res)
      },
      fail: reject,
    })
  })
}

export function deleteSession(sessionId) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: buildUrl(`/agent/session/${sessionId}/delete`),
      method: 'POST',
      header: commonHeaders(),
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) resolve(res.data)
        else reject(res)
      },
      fail: reject,
    })
  })
}

export default {
  listSessions,
  getHistory,
  sendMessage,
  confirmPending,
  cancelPending,
  listPending,
  pendingStatus,
  deleteSession,
  setPendingPreset,
  takePendingPreset,
}
