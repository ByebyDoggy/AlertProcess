/**
 * 画布几何计算
 */

const NODE_WIDTH = 300
const HEADER_HEIGHT = 44
const PORT_ROW_HEIGHT = 26
const PORT_START_Y = HEADER_HEIGHT + 8 + 6
/** 端口圆圈半径偏移（port-anchor 的 left:-7px / right:-7px，圆心距节点边缘 7px） */
const PORT_ANCHOR_OFFSET = 7

/**
 * 计算端口在画布中的绝对位置
 *
 * 坐标指向 port-anchor 圆圈的圆心，
 * 与 .input-port-anchor(left:-7px) / .output-port-anchor(right:-7px) 对齐。
 */
export function getPortPosition(node, portKey, side, portIndex = 0) {
  const y = node.position.y + PORT_START_Y + portIndex * PORT_ROW_HEIGHT

  if (side === 'left') {
    return { x: node.position.x - PORT_ANCHOR_OFFSET, y }
  }
  return { x: node.position.x + NODE_WIDTH + PORT_ANCHOR_OFFSET, y }
}

/**
 * 生成两点间的 Bezier 曲线 SVG path
 */
export function getEdgePath(from, to) {
  const dx = Math.abs(to.x - from.x)
  const cpOffset = Math.max(dx * 0.4, 60)
  return `M ${from.x} ${from.y} C ${from.x + cpOffset} ${from.y}, ${to.x - cpOffset} ${to.y}, ${to.x} ${to.y}`
}

/**
 * 计算 Bezier 曲线中点（用于放置标签）
 */
export function getEdgeMidpoint(from, to) {
  const dx = Math.abs(to.x - from.x)
  const cpOffset = Math.max(dx * 0.4, 60)
  const mx = 0.125 * from.x + 0.375 * (from.x + cpOffset) + 0.375 * (to.x - cpOffset) + 0.125 * to.x
  const my = 0.125 * from.y + 0.375 * from.y + 0.375 * to.y + 0.125 * to.y
  return { x: mx, y: my }
}

export { NODE_WIDTH, HEADER_HEIGHT, PORT_ROW_HEIGHT, PORT_START_Y }
