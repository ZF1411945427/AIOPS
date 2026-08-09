import { request } from './request.js'

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
  return request({ url: '/agent/sessions', hideError: true })
}

export function getHistory(sessionId) {
  return request({ url: `/agent/history/${sessionId}`, hideError: true })
}

export function sendMessage({ sessionId, message }) {
  return request({
    url: '/agent/chat/send',
    method: 'POST',
    timeout: 120000,
    data: { session_id: sessionId || null, message },
  })
}

export function confirmPending(actionId) {
  return request({ url: `/agent/pending/${actionId}/confirm`, method: 'POST' })
}

export function cancelPending(actionId) {
  return request({ url: `/agent/pending/${actionId}/cancel`, method: 'POST' })
}

export function listPending() {
  return request({ url: '/agent/api/pending', hideError: true })
}

export function pendingStatus(actionId) {
  return request({ url: `/agent/pending/${actionId}/status`, hideError: true })
}

export function deleteSession(sessionId) {
  return request({ url: `/agent/session/${sessionId}/delete`, method: 'POST' })
}

export function openAlertAssistant(alertId) {
  return request({ url: `/alerts/api/${alertId}/open-assistant`, method: 'POST' })
}

export function openAssetAssistant(assetId) {
  return request({ url: `/assets/api/${assetId}/open-assistant`, method: 'POST' })
}

let pendingSessionId = ''

export function setPendingSessionId(id) {
  pendingSessionId = id || ''
}

export function takePendingSessionId() {
  const id = pendingSessionId
  pendingSessionId = ''
  return id
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
  openAlertAssistant,
  openAssetAssistant,
  setPendingSessionId,
  takePendingSessionId,
}
