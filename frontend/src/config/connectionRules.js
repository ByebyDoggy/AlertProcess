/**
 * 数据类型兼容性矩阵 — 与后端 nodes/base.py ALLOWED_TYPE_MAPPING 对齐
 *
 * key: 源端口 data_type
 * value: 可连接的目标端口 data_type 列表
 */
export const ALLOWED_TYPE_MAPPING = {
  context: ['context', 'any'],
  // detection_output: 检测器输出（可兼作评分）
  detection_output: ['detection_output', 'score_output', 'any'],
  // score_output: 评分输出（仅评分/脚本节点产生）
  score_output: ['detection_output', 'score_output', 'any'],
  // logic_output: 逻辑/脚本布尔输出
  logic_output: ['logic_output', 'any'],
  memory_output: ['memory_output', 'context', 'any'],
  // script_output: Python 表达式节点输出（最通用，兼容所有类型）
  script_output: ['script_output', 'detection_output', 'score_output', 'logic_output', 'any'],
}

/**
 * 各节点分类允许接收的输入 data_type
 */
export const CATEGORY_ALLOWED_INPUTS = {
  input: [],
  provider: ['context', 'any'],
  detection: ['context', 'any'],
  logic: ['logic_output', 'context', 'memory_output', 'any'],
  action: ['any'],
  memory: ['detection_output', 'score_output', 'context', 'any'],
  scripting: ['detection_output', 'score_output', 'context', 'any'],
}

/**
 * 端口 data_type → 颜色映射
 */
export const DATA_TYPE_COLORS = {
  context: '#22c55e',
  detection_output: '#f59e0b',
  score_output: '#f97316',
  logic_output: '#ef4444',
  memory_output: '#8b5cf6',
  script_output: '#22c55e',
  any: '#6b7280',
}

/**
 * 检查连线是否合法
 * @param {string} sourceDataType - 源端口 data_type
 * @param {string} targetDataType - 目标端口 data_type
 * @returns {{ valid: boolean, reason?: string }}
 */
export function checkConnectionValid(sourceDataType, targetDataType) {
  const allowed = ALLOWED_TYPE_MAPPING[sourceDataType]
  if (!allowed) return { valid: false, reason: `未知源数据类型: ${sourceDataType}` }
  if (allowed.includes(targetDataType)) return { valid: true }
  return {
    valid: false,
    reason: `${sourceDataType} 不能连接到 ${targetDataType}`,
  }
}
