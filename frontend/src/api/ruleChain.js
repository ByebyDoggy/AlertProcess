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
 * 验证规则链
 */
export async function validateChain(nodes, edges) {
  return apiService.request('/rule-chain/validate', {
    method: 'POST',
    body: JSON.stringify({ nodes, edges }),
  })
}
