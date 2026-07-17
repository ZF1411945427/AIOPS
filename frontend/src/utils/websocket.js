/**
 * WebSocket 实时告警推送工具
 * 连接 /ws/alerts，前端按 user_id 订阅 alert:{user_id} 房间
 * 新告警到达时在浏览器内存中维护一个 alert 队列，通过 callback 推送给调用方
 */
let ws = null
let reconnectTimer = null
let reconnectDelay = 3000
let alertCallbacks = []

export function onAlert(callback) {
  alertCallbacks.push(callback)
  return () => {
    alertCallbacks = alertCallbacks.filter(cb => cb !== callback)
  }
}

export function connectAlertsWs(token) {
  if (ws && ws.readyState === WebSocket.OPEN) return
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${protocol}//${location.host}/ws/alerts?token=${encodeURIComponent(token || '')}`
  ws = new WebSocket(url)
  ws.addEventListener('open', () => {
    console.log('[WS] 告警频道已连接')
    reconnectDelay = 3000
  })
  ws.addEventListener('message', (event) => {
    try {
      const msg = JSON.parse(event.data)
      if (msg.type === 'alert' && msg.data) {
        const alerts = Array.isArray(msg.data) ? msg.data : [msg.data]
        alertCallbacks.forEach(cb => alerts.forEach(a => cb(a)))
      }
    } catch {}
  })
  ws.addEventListener('close', () => {
    ws = null
    reconnectTimer = setTimeout(() => connectAlertsWs(token), reconnectDelay)
    reconnectDelay = Math.min(reconnectDelay * 2, 30000)
  })
  ws.addEventListener('error', () => {
    ws?.close()
  })
}

export function disconnectAlertsWs() {
  clearTimeout(reconnectTimer)
  ws?.close()
  ws = null
}
