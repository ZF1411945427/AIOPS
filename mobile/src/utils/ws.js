/**
 * 移动端 WebSocket 实时告警推送
 * 连接 /ws/alerts，按 user_id 订阅房间，新告警通过事件派发
 */
let ws = null
let reconnectTimer = null
let reconnectDelay = 3000
let listeners = []

function emit(type, data) {
  listeners.forEach(fn => {
    try { fn(type, data) } catch (e) {}
  })
}

export function onWsEvent(fn) {
  listeners.push(fn)
  return () => { listeners = listeners.filter(f => f !== fn) }
}

export function connectAlertWs(token) {
  if (ws && ws.readyState === 1) return
  const host = import.meta.env.VITE_API_BASE || 'localhost:8000'
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${protocol}//${host}/ws/alerts?token=${encodeURIComponent(token || '')}`
  ws = new UniWebSocket(url)
  ws.onOpen(() => {
    console.log('[WS] 告警频道已连接')
    reconnectDelay = 3000
  })
  ws.onMessage((event) => {
    try {
      const msg = JSON.parse(event.data)
      if (msg.type === 'alert' && msg.data) {
        const alerts = Array.isArray(msg.data) ? msg.data : [msg.data]
        alerts.forEach(a => emit('alert', a))
      }
      if (msg.type === 'connected') {
        emit('connected', msg)
      }
    } catch (e) {}
  })
  ws.onClose(() => {
    ws = null
    reconnectTimer = setTimeout(() => connectAlertWs(token), reconnectDelay)
    reconnectDelay = Math.min(reconnectDelay * 2, 30000)
  })
  ws.onError(() => {
    ws?.close()
  })
}

export function disconnectAlertWs() {
  clearTimeout(reconnectTimer)
  if (ws) {
    ws.close()
    ws = null
  }
}

function UniWebSocket(url) {
  const tasks = []
  let socket = null
  let _onOpen = null
  let _onMessage = null
  let _onClose = null
  let _onError = null

  function send(data) {
    if (socket && socket.readyState === 1) {
      socket.send(data)
    } else {
      tasks.push(['send', data])
    }
  }

  uni.connectSocket({
    url,
    success: () => {
      socket = {
        readyState: 0,
        send,
        close: () => {
          uni.closeSocket()
          _onClose && _onClose({ type: 'close' })
        },
      }
      tasks.push(['open'])
      uni.onSocketOpen(() => {
        socket.readyState = 1
        _onOpen && _onOpen({ type: 'open' })
        tasks.forEach(([action, data]) => {
          if (action === 'send') socket.send(data)
        })
        tasks.length = 0
      })
      uni.onSocketMessage((res) => {
        _onMessage && _onMessage({ data: res.data })
      })
      uni.onSocketClose(() => {
        socket.readyState = 3
        _onClose && _onClose({ type: 'close' })
      })
      uni.onSocketError(() => {
        _onError && _onError({ type: 'error' })
      })
    },
    fail: () => {
      _onError && _onError({ type: 'error' })
    },
  })

  return {
    onOpen: fn => (_onOpen = fn),
    onMessage: fn => (_onMessage = fn),
    onClose: fn => (_onClose = fn),
    onError: fn => (_onError = fn),
    send,
    close: () => socket?.close(),
  }
}
