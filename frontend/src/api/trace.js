import apiService from './index.js'

const TRACE_BASE = '/detectors/trace'

/**
 * 分析交易调用链
 */
export async function analyzeTransaction(txHash, chainId = 1, runBehaviorDetect = true) {
  return apiService.request(`${TRACE_BASE}/analyze`, {
    method: 'POST',
    body: JSON.stringify({
      tx_hash: txHash,
      chain_id: chainId,
      run_behavior_detect: runBehaviorDetect,
    }),
  })
}

/**
 * 使用闪电贷检测器分析交易
 */
export async function analyzeWithFlashDetection(txHash, chainId = 1) {
  return apiService.request(`${TRACE_BASE}/analyze-with-flash-detect`, {
    method: 'POST',
    body: JSON.stringify({ tx_hash: txHash, chain_id: chainId }),
  })
}

/**
 * 获取支持链列表
 */
export async function getSupportedChains() {
  return apiService.request(`${TRACE_BASE}/supported-chains`)
}

/**
 * 签名搜索 (前缀模糊)
 */
export async function searchSignatures(prefix, limit = 20) {
  return apiService.request(`${TRACE_BASE}/signatures?prefix=${encodeURIComponent(prefix)}&limit=${limit}`)
}

/**
 * 精确查询 selector 的全部候选签名
 * ?hex=0xa9059cbb → {selector, signatures: [{text, num_results}], total, source}
 */
export async function lookupSignatures(hex) {
  return apiService.request(`${TRACE_BASE}/signatures?hex=${encodeURIComponent(hex)}`)
}

/**
 * 签名库统计
 */
export async function getSignatureStats() {
  return apiService.request(`${TRACE_BASE}/stats`)
}

// ── 拆分端点: 各面板独立数据获取 ──

/**
 * 获取调用树数据 (CallTreeView 独立使用)
 */
export async function fetchCallTree(txHash, chainId = 1) {
  return apiService.request(`${TRACE_BASE}/call-tree`, {
    method: 'POST',
    body: JSON.stringify({ tx_hash: txHash, chain_id: chainId }),
  })
}

/**
 * 获取余额变化数据 (BalanceChangesPanel 独立使用)
 */
export async function fetchBalanceChanges(txHash, chainId = 1) {
  return apiService.request(`${TRACE_BASE}/balance-changes`, {
    method: 'POST',
    body: JSON.stringify({ tx_hash: txHash, chain_id: chainId }),
  })
}

/**
 * 获取 Token 流转数据 (TokenFlowPanel 独立使用)
 */
export async function fetchTokenFlows(txHash, chainId = 1) {
  return apiService.request(`${TRACE_BASE}/token-flows`, {
    method: 'POST',
    body: JSON.stringify({ tx_hash: txHash, chain_id: chainId }),
  })
}

/**
 * 获取行为检测结果 (BehaviorPanel 独立使用)
 */
export async function fetchBehaviors(txHash, chainId = 1) {
  return apiService.request(`${TRACE_BASE}/behaviors`, {
    method: 'POST',
    body: JSON.stringify({ tx_hash: txHash, chain_id: chainId }),
  })
}
