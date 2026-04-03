export function generateId(prefix = 'id') {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`
}

export function deepClone(obj) {
  return JSON.parse(JSON.stringify(obj))
}

export function formatTimestamp(ts) {
  if (!ts) return '-'
  return new Date(ts).toLocaleString('zh-CN')
}
