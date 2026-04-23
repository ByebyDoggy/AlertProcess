/**
 * Pool 配置 API
 * 管理每条链的 apipool-server pool_identifier 配置 + Moralis API Key 池
 */
import apiService from './index.js'

const BASE = '/pool-config'

export const poolConfigApi = {
  /** 获取所有链的 pool 配置 */
  getConfig() {
    return apiService.request(`${BASE}/`)
  },

  /** 获取支持的链列表 */
  getChains() {
    return apiService.request(`${BASE}/chains`)
  },

  /** 获取池运行状态 */
  getStatus() {
    return apiService.request(`${BASE}/status`)
  },

  /** 更新指定链的 pool_identifier */
  updatePoolIdentifier(chainId, poolIdentifier) {
    return apiService.request(`${BASE}/${chainId}`, {
      method: 'PUT',
      body: JSON.stringify({ pool_identifier: poolIdentifier }),
    })
  },

  /** 健康检查 */
  runHealthCheck(chainId = null) {
    let url = `${BASE}/health-check`
    if (chainId) url += `?chain_id=${chainId}`
    return apiService.request(url, { method: 'POST' })
  },

  /** 重新加载配置 */
  reloadConfig() {
    return apiService.request(`${BASE}/reload`, { method: 'POST' })
  },

  /** 测试 RPC URL 连通性 */
  testConnection(url, timeout = 15) {
    return apiService.request(`${BASE}/test-connection`, {
      method: 'POST',
      body: JSON.stringify({ url, timeout }),
    })
  },

  /** 获取 Server 全局配置 */
  getServerConfig() {
    return apiService.request(`${BASE}/server-config`)
  },

  /** 更新 Server 全局配置 (URL / 用户名 / 密码) */
  updateServerConfig({ serverUrl, username, password }) {
    const body = {}
    if (serverUrl !== undefined) body.server_url = serverUrl
    if (username !== undefined) body.username = username
    if (password !== undefined && password !== '******') body.password = password
    return apiService.request(`${BASE}/server-config`, {
      method: 'PUT',
      body: JSON.stringify(body),
    })
  },

  // ── MoralKeyPool 管理 ──

  /** 获取 MoralKeyPool 当前状态 */
  getMoralisStatus() {
    return apiService.request(`${BASE}/moralis-status`)
  },

  /** 更新 moralis_pool_identifier */
  updateMoralisPoolConfig(poolIdentifier) {
    return apiService.request(`${BASE}/moralis-config`, {
      method: 'PUT',
      body: JSON.stringify({ pool_identifier: poolIdentifier }),
    })
  },

  /** 重载 MoralKeyPool（重新认证并拉取 keys） */
  reloadMoralisPool() {
    return apiService.request(`${BASE}/moralis-reload`, { method: 'POST' })
  },

  // ── 区块时间配置（用于地址年龄估算） ──

  /** 获取所有链的区块时间配置 */
  getBlockTimeConfig() {
    return apiService.request(`${BASE}/block-time-config`)
  },

  /** 更新指定链的单块时间(秒) */
  updateBlockTimeConfig(chainId, blockTimeSeconds) {
    return apiService.request(`${BASE}/block-time-config`, {
      method: 'PUT',
      body: JSON.stringify({ chain_id: chainId, block_time_seconds: blockTimeSeconds }),
    })
  },
}

export default poolConfigApi
