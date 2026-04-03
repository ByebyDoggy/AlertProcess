import apiService from './index.js'

/**
 * 从后端 NodeRegistry 加载节点类型 Schema
 */
export async function fetchNodeTypes() {
  return apiService.request('/rule-chain/schema/nodes')
}

/**
 * 加载连线规则
 */
export async function fetchConnectionRules() {
  return apiService.request('/rule-chain/schema/connection-rules')
}
