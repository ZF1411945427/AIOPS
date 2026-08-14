import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const { wsMock, wsConstructor } = vi.hoisted(() => {
    const wsMock = {
        addEventListener: vi.fn(),
        close: vi.fn(),
        readyState: 1,
    }
    const wsConstructor = vi.fn(() => wsMock)
    wsConstructor.OPEN = 1
    wsConstructor.CONNECTING = 0
    wsConstructor.CLOSING = 2
    wsConstructor.CLOSED = 3
    return { wsMock, wsConstructor }
})

vi.stubGlobal('WebSocket', wsConstructor)

import { onAlert, connectAlertsWs, disconnectAlertsWs } from './websocket.js'

describe('websocket.js', () => {
    beforeEach(() => {
        vi.clearAllMocks()
    })

    afterEach(() => {
        disconnectAlertsWs()
    })

    it('onAlert registers and returns unsubscriber', () => {
        const cb = vi.fn()
        const unsub = onAlert(cb)
        expect(typeof unsub).toBe('function')
        unsub()
    })

    it('connectAlertsWs creates WebSocket with correct URL', () => {
        connectAlertsWs('test-token')
        expect(wsConstructor).toHaveBeenCalledWith(
            expect.stringMatching(/ws:\/\/.*\/ws\/alerts\?token=test-token/)
        )
        expect(wsMock.addEventListener).toHaveBeenCalledWith('open', expect.any(Function))
        expect(wsMock.addEventListener).toHaveBeenCalledWith('message', expect.any(Function))
        expect(wsMock.addEventListener).toHaveBeenCalledWith('close', expect.any(Function))
    })

    it('connectAlertsWs skips if already open', () => {
        connectAlertsWs('test-token')
        wsConstructor.mockClear()
        wsMock.addEventListener.mockClear()
        connectAlertsWs('test-token')
        expect(wsConstructor).not.toHaveBeenCalled()
    })

    it('message dispatches alert to callbacks', () => {
        const cb = vi.fn()
        onAlert(cb)
        connectAlertsWs('test-token')
        const messageHandler = wsMock.addEventListener.mock.calls.find(
            ([name]) => name === 'message'
        )[1]
        messageHandler({ data: JSON.stringify({ type: 'alert', data: { id: 1, metric_name: 'cpu' } }) })
        expect(cb).toHaveBeenCalledWith({ id: 1, metric_name: 'cpu' })
    })

    it('message ignores non-alert type', () => {
        const cb = vi.fn()
        onAlert(cb)
        connectAlertsWs('test-token')
        const messageHandler = wsMock.addEventListener.mock.calls.find(
            ([name]) => name === 'message'
        )[1]
        messageHandler({ data: JSON.stringify({ type: 'heartbeat' }) })
        expect(cb).not.toHaveBeenCalled()
    })

    it('disconnectAlertsWs cleans up', () => {
        connectAlertsWs('test-token')
        disconnectAlertsWs()
        expect(wsMock.close).toHaveBeenCalled()
        disconnectAlertsWs()  // 第二次调用应安全
    })
})