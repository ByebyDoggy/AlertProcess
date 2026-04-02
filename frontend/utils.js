// 工具函数

/**
 * 生成唯一ID
 */
export function generateId(prefix = 'id') {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
}

/**
 * 格式化时间戳
 */
export function formatTimestamp(timestamp) {
  if (!timestamp) return '-'
  return new Date(timestamp).toLocaleString('zh-CN')
}

/**
 * 缩短哈希值
 */
export function shortenHash(hash, prefixLength = 10, suffixLength = 8) {
  if (!hash) return '-'
  return hash.slice(0, prefixLength) + '...' + hash.slice(-suffixLength)
}

/**
 * 获取严重程度样式类
 */
export function getSeverityClass(severity) {
  const classes = {
    CRITICAL: 'bg-red-600 text-white',
    HIGH: 'bg-orange-500 text-white',
    MEDIUM: 'bg-yellow-500 text-black',
    LOW: 'bg-blue-500 text-white',
    UNKNOWN: 'bg-gray-500 text-white'
  }
  return classes[severity] || classes.UNKNOWN
}

/**
 * 获取风险评分颜色
 */
export function getScoreColor(score) {
  if (score > 400) return 'bg-red-500'
  if (score > 300) return 'bg-orange-500'
  if (score > 200) return 'bg-yellow-500'
  return 'bg-blue-500'
}

/**
 * 获取风险评分文本颜色
 */
export function getScoreTextColor(score) {
  if (score > 400) return 'text-red-500'
  if (score > 300) return 'text-orange-500'
  if (score > 200) return 'text-yellow-500'
  return 'text-blue-500'
}

/**
 * 获取配置摘要
 */
export function getConfigSummary(node, NODE_TYPES) {
  if (!node.config) return '未配置'
  
  const typeConfig = NODE_TYPES[node.type]
  if (!typeConfig) return '未配置'

  switch (node.type) {
    case 'detector':
      const option = typeConfig.configFields[0].options.find(
        opt => opt.value === node.config.detectorType
      )
      return option ? option.label.replace(/[⚡🔐💰🔗⛽📅🏷️🏢]/g, '').trim() : node.config.detectorType
    case 'condition':
      return `${node.config.field || '?'} ${node.config.operator || '?'} ${node.config.value || '?'}`
    case 'action':
      return `${node.config.actionType || '?'}: ${node.config.actionValue || '?'}`
    case 'filter':
      return node.config.expression || '未设置'
    case 'notifier':
      return `${node.config.notifierType || '?'}: ${node.config.targetUrl || '?'}`
    case 'scorer':
      const weights = node.config.weights || {}
      return `严重程度:${weights.severity || 1}, 检测器:${weights.detector || 1}`
    default:
      return '已配置'
  }
}

/**
 * 将节点配置转换为后端格式
 */
export function normalizeChainConfig(nodes, edges) {
  return {
    nodes: nodes.map(node => ({
      id: node.id,
      type: node.type,
      label: node.label,
      config: node.config || {},
      position: node.position
    })),
    edges: edges.map(edge => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label || ''
    }))
  }
}

/**
 * 防抖函数
 */
export function debounce(func, wait) {
  let timeout
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout)
      func(...args)
    }
    clearTimeout(timeout)
    timeout = setTimeout(later, wait)
  }
}

/**
 * 节流函数
 */
export function throttle(func, limit) {
  let inThrottle
  return function(...args) {
    if (!inThrottle) {
      func.apply(this, args)
      inThrottle = true
      setTimeout(() => inThrottle = false, limit)
    }
  }
}

/**
 * 深度克隆对象
 */
export function deepClone(obj) {
  return JSON.parse(JSON.stringify(obj))
}

/**
 * 计算两点之间的距离
 */
export function getDistance(point1, point2) {
  return Math.sqrt(
    Math.pow(point2.x - point1.x, 2) + 
    Math.pow(point2.y - point1.y, 2)
  )
}

/**
 * 获取连接点位置
 */
export function getConnectionPointPosition(node, position) {
  const rect = { width: 180, height: 60 }
  let x = node.position.x
  let y = node.position.y

  switch (position) {
    case 'top':
      x += rect.width / 2
      break
    case 'bottom':
      x += rect.width / 2
      y += rect.height
      break
    case 'left':
      y += rect.height / 2
      break
    case 'right':
      x += rect.width
      y += rect.height / 2
      break
  }

  return { x, y }
}

/**
 * 生成贝塞尔曲线路径
 */
export function getBezierPath(start, end) {
  const midY = (start.y + end.y) / 2
  return `M ${start.x} ${start.y} C ${start.x} ${midY}, ${end.x} ${midY}, ${end.x} ${end.y}`
}
