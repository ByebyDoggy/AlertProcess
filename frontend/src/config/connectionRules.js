/**
 * 数据类型兼容性矩阵 — 与后端 nodes/base.py ALLOWED_TYPE_MAPPING 对齐
 *
 * key: 源端口 data_type
 * value: 可连接的目标端口 data_type 列表
 */
export const ALLOWED_TYPE_MAPPING = {
  context: ['context', 'any'],
  detection_output: ['detection_output', 'score_output', 'any'],
  comparison_output: ['comparison_output', 'any'],
  score_output: ['detection_output', 'score_output', 'any'],
  logic_output: ['logic_output', 'comparison_output', 'any'],
}

/**
 * 各节点分类允许接收的输入 data_type
 */
export const CATEGORY_ALLOWED_INPUTS = {
  input: [],
  detection: ['context', 'any'],
  comparison: ['detection_output', 'score_output'],
  scoring: ['detection_output', 'score_output'],
  logic: ['comparison_output', 'logic_output'],
  action: ['any'],
}

/**
 * 端口 data_type → 颜色映射
 */
export const DATA_TYPE_COLORS = {
  context: '#22c55e',
  detection_output: '#f59e0b',
  comparison_output: '#06b6d4',
  score_output: '#f97316',
  logic_output: '#ef4444',
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
