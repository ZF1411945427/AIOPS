const DEFAULT_BASE = 'http://127.0.0.1:8000'

export function getBaseURL() {
  try {
    return uni.getStorageSync('server_base_url') || DEFAULT_BASE
  } catch (e) {
    return DEFAULT_BASE
  }
}

export function setBaseURL(url) {
  uni.setStorageSync('server_base_url', url || DEFAULT_BASE)
}

export function getCookie() {
  try {
    return uni.getStorageSync('session_cookie') || ''
  } catch (e) {
    return ''
  }
}

export function setCookie(cookie) {
  uni.setStorageSync('session_cookie', cookie || '')
}

export function getToken() {
  try {
    return uni.getStorageSync('auth_token') || ''
  } catch (e) {
    return ''
  }
}

export function setToken(t) {
  uni.setStorageSync('auth_token', t || '')
}

export function buildUrl(path) {
  if (!path) return getBaseURL()
  if (path.startsWith('http')) return path
  return getBaseURL().replace(/\/$/, '') + path
}

export function commonHeaders(extra) {
  const h = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) h['Authorization'] = 'Bearer ' + token
  return Object.assign({}, h, extra || {})
}

export default {
  get BASE_URL() { return getBaseURL() },
  getBaseURL,
  setBaseURL,
  getCookie,
  setCookie,
  getToken,
  setToken,
  buildUrl,
  commonHeaders,
}
