export const THRESHOLDS = {
  cpu_usage: { warn: 70, crit: 85 },
  cpu_iowait: { warn: 30, crit: 50 },
  memory_usage: { warn: 80, crit: 90 },
  swap_usage: { warn: 50, crit: 80 },
  disk_usage: { warn: 80, crit: 90 },
  disk_inode_usage: { warn: 80, crit: 90 },
  loadavg_1min: { warn: 4, crit: 8 },
  loadavg_5min: { warn: 4, crit: 8 },
  loadavg_15min: { warn: 4, crit: 8 },
}

export function metricStatus(name, value) {
  if (value === null || value === undefined) return null
  const t = THRESHOLDS[name]
  if (!t) return null
  const v = typeof value === 'object' ? value.value : value
  if (typeof v !== 'number' || isNaN(v)) return null
  if (v >= t.crit) return 'critical'
  if (v >= t.warn) return 'warning'
  return 'normal'
}

export function statusColor(status) {
  if (status === 'critical') return '#ef4444'
  if (status === 'warning') return '#f59e0b'
  if (status === 'normal') return '#22c55e'
  return null
}

export function formatValue(lv) {
  if (lv === null || lv === undefined) return '—'
  const v = typeof lv === 'object' ? lv.value : lv
  if (v === null || v === undefined) return '—'
  return typeof v === 'number' ? v.toFixed(1) : v
}

export function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  if (isNaN(d.getTime())) return ''
  const mm = (d.getMonth() + 1).toString().padStart(2, '0')
  const dd = d.getDate().toString().padStart(2, '0')
  const hh = d.getHours().toString().padStart(2, '0')
  const mi = d.getMinutes().toString().padStart(2, '0')
  return `${mm}-${dd} ${hh}:${mi}`
}

export function formatAxisTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  if (isNaN(d.getTime())) return ''
  const hh = d.getHours().toString().padStart(2, '0')
  const mi = d.getMinutes().toString().padStart(2, '0')
  return `${hh}:${mi}`
}

export const TIME_RANGES = [
  { value: 1, label: '1 小时' },
  { value: 6, label: '6 小时' },
  { value: 24, label: '24 小时' },
  { value: 72, label: '3 天' },
  { value: 168, label: '7 天' },
]