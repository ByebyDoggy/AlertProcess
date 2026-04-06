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
