import apiService from './index.js'

/**
 * 规则链 CRUD
 */
export async function getRuleChains() {
  return apiService.request('/rule-chain/')
}

export async function getRuleChain(id) {
  return apiService.request(`/rule-chain/${id}`)
}

export async function createRuleChain(data) {
  return apiService.request('/rule-chain/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateRuleChain(id, data) {
  return apiService.request(`/rule-chain/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function deleteRuleChain(id) {
  return apiService.request(`/rule-chain/${id}`, { method: 'DELETE' })
}

/**
 * 切换规则链启用/禁用状态
 */
export async function toggleChainEnabled(id, enabled) {
  return apiService.request(`/rule-chain/${id}`, {
    method: 'PUT',
    body: JSON.stringify({ enabled }),
  })
}

/**
 * 验证规则链
 */
export async function validateChain(nodes, edges) {
  return apiService.request('/rule-chain/validate', {
    method: 'POST',
    body: JSON.stringify({ nodes, edges }),
  })
}

/**
 * 单节点测试（n8n 式逐节点调试）
 */
export async function testNode(nodes, edges, targetNodeId, upstreamOutputs = {}, alertData = null) {
  return apiService.request('/rule-chain/test-node', {
    method: 'POST',
    body: JSON.stringify({
      nodes,
      edges,
      target_node_id: targetNodeId,
      upstream_outputs: upstreamOutputs,
      alert_data: alertData,
    }),
  })
}

/**
 * 输入转换器 (Input Transformer) API
 */
export async function validateTransformer(expression, language = 'python') {
  return apiService.request('/rule-chain/transformer/validate', {
    method: 'POST',
    body: JSON.stringify({ expression, language }),
  })
}

export async function previewTransformer(expression, language = 'python', sampleInput = {}) {
  return apiService.request('/rule-chain/transformer/preview', {
    method: 'POST',
    body: JSON.stringify({ expression, language, sample_input: sampleInput }),
  })
}
