/**
 * 节点类型 Fallback 定义 — 后端 API 不可用时使用
 * 数据与 nodes/ 中所有注册节点完全对齐
 *
 * 前端不应硬编码此文件中的数据，仅作为 fallback。
 */

export const CATEGORY_LABELS = {
  input: '输入',
  detection: '安全检测',
  comparison: '比较',
  scoring: '评分',
  logic: '逻辑',
  action: '动作',
}

export const PORT_LABELS = {
  input_0: '输入 1',
  input_1: '输入 2',
  input_2: '输入 3',
  output: '输出',
  true: '满足',
  false: '不满足',
}

export const DATA_TYPE_LABELS = {
  context: '上下文',
  detection_output: '检测输出',
  comparison_output: '比较输出',
  score_output: '评分输出',
  logic_output: '逻辑输出',
  any: '任意',
}
