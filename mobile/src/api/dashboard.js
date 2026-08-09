import { request } from './request.js'

export function getDashboard() {
  return request({ url: '/mobile/dashboard' })
}

export default {
  getDashboard,
}
