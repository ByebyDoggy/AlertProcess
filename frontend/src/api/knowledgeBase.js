import apiService from './index.js'

/**
 * 知识库 CRUD
 */
export async function getSamples(params = {}) {
  const query = new URLSearchParams()
  if (params.skip != null) query.set('skip', params.skip)
  if (params.limit != null) query.set('limit', params.limit)
  if (params.category) query.set('category', params.category)
  if (params.chain_id != null) query.set('chain_id', params.chain_id)
  if (params.search) query.set('search', params.search)
  if (params.tag) query.set('tag', params.tag)
  const qs = query.toString()
  return apiService.request(`/knowledge-base/${qs ? '?' + qs : ''}`)
}

export async function getSample(id) {
  return apiService.request(`/knowledge-base/${id}`)
}

export async function createSample(data) {
  return apiService.request('/knowledge-base/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateSample(id, data) {
  return apiService.request(`/knowledge-base/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function deleteSample(id) {
  return apiService.request(`/knowledge-base/${id}`, { method: 'DELETE' })
}

/**
 * 导入 / 导出
 */
export async function importSamples(samples) {
  return apiService.request('/knowledge-base/import', {
    method: 'POST',
    body: JSON.stringify({ samples }),
  })
}

export async function exportSamples() {
  return apiService.request('/knowledge-base/export/all')
}

/**
 * 元数据
 */
export async function getCategories() {
  return apiService.request('/knowledge-base/meta/categories')
}

/**
 * 链上数据自动获取 — 根据 chain_id + tx_hash 拉取交易数据
 */
export async function fetchTxData(chainId, txHash) {
  return apiService.request('/knowledge-base/fetch-tx', {
    method: 'POST',
    body: JSON.stringify({ chain_id: chainId, tx_hash: txHash }),
  })
}

/**
 * 快速创建样本 — 仅需 chain_id + tx_hash，后端自动获取链上数据
 */
export async function quickCreateSample({ chain_id, tx_hash, category, tags, description, expected_severity, expected_labels, expected_min_score }) {
  return apiService.request('/knowledge-base/quick-create', {
    method: 'POST',
    body: JSON.stringify({ chain_id, tx_hash, category, tags, description, expected_severity, expected_labels, expected_min_score }),
  })
}

/**
 * 测试运行 (挂在规则链 API 上)
 */
export async function testRunChain(chainId, body) {
  return apiService.request(`/rule-chain/${chainId}/test-run`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
