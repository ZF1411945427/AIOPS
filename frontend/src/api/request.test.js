import { describe, it, expect, vi, beforeEach } from 'vitest'

const mocks = vi.hoisted(() => ({
    warning: vi.fn(),
}))

vi.mock('element-plus', () => ({
    ElMessage: { warning: mocks.warning },
}))

import request from './request.js'

describe('request.js axios instance', () => {
    beforeEach(() => {
        mocks.warning.mockClear()
    })

    it('is an axios instance', () => {
        expect(request.defaults.withCredentials).toBe(true)
        expect(request.defaults.timeout).toBe(30000)
    })

    it('response interceptor returns data and triggers warning on warning field', async () => {
        const response = { data: { warning: 'K8s cluster unavailable' } }
        const handler = request.interceptors.response.handlers[0]
        const result = handler.fulfilled(response)
        expect(mocks.warning).toHaveBeenCalledWith('K8s cluster unavailable')
        expect(result).toBe(response.data)
    })

    it('response interceptor returns non-warning data silently', async () => {
        const response = { data: { items: [] } }
        const handler = request.interceptors.response.handlers[0]
        const result = handler.fulfilled(response)
        expect(mocks.warning).not.toHaveBeenCalled()
        expect(result).toBe(response.data)
    })

    it('error interceptor extracts detail field', async () => {
        const handler = request.interceptors.response.handlers[0]
        const error = { response: { data: { detail: '认证失败' } } }
        await expect(handler.rejected(error)).rejects.toThrow('认证失败')
    })

    it('error interceptor extracts message field', async () => {
        const handler = request.interceptors.response.handlers[0]
        const error = { response: { data: { message: '网络错误' } } }
        await expect(handler.rejected(error)).rejects.toThrow('网络错误')
    })

    it('error interceptor falls back to error.message', async () => {
        const handler = request.interceptors.response.handlers[0]
        const error = { message: 'Request failed with status code 500' }
        await expect(handler.rejected(error)).rejects.toThrow('Request failed')
    })

    it('error interceptor navigates to license on license_status 403', async () => {
        const navigate = vi.fn()
        window._navigateTo = navigate
        const handler = request.interceptors.response.handlers[0]
        const error = { response: { status: 403, data: { license_status: 'expired', detail: '授权失效' } } }
        await expect(handler.rejected(error)).rejects.toThrow('授权失效')
        expect(navigate).toHaveBeenCalledWith('license')
        delete window._navigateTo
    })
})