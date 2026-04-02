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

/**
 * Get a human-readable summary of a node's config for the node body
 */
export function getConfigSummary(node, nodeTypes) {
  if (!node || !node.config) return ''
  const tc = nodeTypes[node.type]
  if (!tc) return ''

  switch (node.type) {
    case 'trigger':
      return '接收告警数据输入'
    case 'detector': {
      const dt = node.config.detectorType || ''
      if (!dt) return '未配置检测器'
      const opt = tc.configFields[0]?.options?.find(o => o.value === dt)
      return opt ? opt.label : dt
    }
    case 'condition': {
      const logic = node.config.logic || 'and'
      const logicLabel = logic === 'and' ? 'AND' : logic === 'or' ? 'OR' : 'IF'
      const conds = node.config.conditions || []
      return `${logicLabel} (${conds.length} 个条件)`
    }
    case 'action': {
      const at = node.config.actionType || ''
      const av = node.config.actionValue || ''
      const actionLabels = {
        set_severity: '设置级别',
        set_score: '设置评分',
        add_tag: '添加标签',
        annotate_address: '地址标注',
      }
      const label = actionLabels[at] || at
      return av ? `${label}: ${av}` : label
    }
    case 'notifier':
      return node.config.targetUrl || '未配置'
    default:
      return ''
  }
}

/**
 * Build port position for SVG edge drawing
 * node: { id, position: {x, y}, type }
 * portKey: 'input' | 'output' | 'true' | 'false'
 * side: 'left' | 'right'
 */
export function getPortPosition(node, portKey, side, portIndex = 0) {
  const nodeW = 230
  const nodeH = getNodeHeight(node)
  const headerH = 44
  const portSpacing = 22
  const portStartY = headerH + 8 + portIndex * portSpacing + 6

  if (side === 'left') {
    return { x: node.position.x, y: node.position.y + portStartY }
  } else {
    return { x: node.position.x + nodeW, y: node.position.y + portStartY }
  }
}

function getNodeHeight(node) {
  const type = node.type
  const hasInputs = type !== 'trigger'
  const outputs = getNodeOutputs(type, node.config)
  const portRows = (hasInputs ? 1 : 0) + outputs.length
  const hasBody = getConfigSummary(node, {}) !== '' || type === 'condition'
  return 44 + (portRows * 22) + (hasBody ? 24 : 0) + 12
}

export function getNodeOutputs(type, config) {
  switch (type) {
    case 'trigger':
      return [{ key: 'output', label: '告警数据', color: '#f59e0b' }]
    case 'detector':
      return [
        { key: 'true', label: '检测到', color: '#10b981' },
        { key: 'false', label: '未检测到', color: '#ef4444' },
      ]
    case 'condition':
      return [
        { key: 'true', label: '满足', color: '#10b981' },
        { key: 'false', label: '不满足', color: '#ef4444' },
      ]
    case 'action':
      return [{ key: 'output', label: '输出', color: '#a855f7' }]
    case 'notifier':
      return []
    default:
      return []
  }
}

/**
 * Generate Bézier curve path between two port positions
 */
export function getEdgePath(from, to) {
  const dx = Math.abs(to.x - from.x)
  const dy = Math.abs(to.y - from.y)
  const cpOffset = Math.max(dx * 0.4, 60)
  return `M ${from.x} ${from.y} C ${from.x + cpOffset} ${from.y}, ${to.x - cpOffset} ${to.y}, ${to.x} ${to.y}`
}

/**
 * Get edge midpoint for label placement
 */
export function getEdgeMidpoint(from, to) {
  const dx = Math.abs(to.x - from.x)
  const dy = Math.abs(to.y - from.y)
  const cpOffset = Math.max(dx * 0.4, 60)
  // midpoint of cubic bezier at t=0.5
  const mx = 0.125 * from.x + 0.375 * (from.x + cpOffset) + 0.375 * (to.x - cpOffset) + 0.125 * to.x
  const my = 0.125 * from.y + 0.375 * from.y + 0.375 * to.y + 0.125 * to.y
  return { x: mx, y: my }
}

/**
 * Parse variable reference from expression
 * e.g. "trigger.tx_hash" -> { nodeType: 'trigger', key: 'tx_hash' }
 */
export function parseVarRef(expr) {
  if (!expr || typeof expr !== 'string') return null
  const match = expr.match(/^([a-zA-Z0-9_]+)\.([a-zA-Z0-9_.]+)$/)
  if (!match) return null
  return { nodeType: match[1], key: match[2] }
}

/**
 * Build variable expression string
 */
export function buildVarExpr(nodeLabel, key) {
  return `${nodeLabel}.${key}`
}
