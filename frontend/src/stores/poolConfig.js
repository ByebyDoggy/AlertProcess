/**
 * Pool 配置 Store
 * 管理 RPC Pool 配置 + Moralis API Key 池状态 + 区块时间配置
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { poolConfigApi } from '@/api/poolConfig.js'

export const usePoolStore = defineStore('poolConfig', () => {
  // ── RPC Pool State ──
  const configs = ref([])           // 所有链的配置
  const poolStatus = ref([])        // 池运行状态
  const healthReports = ref([])     // 健康检查结果
  const loading = ref(false)
  const healthLoading = ref(false)
  const error = ref('')

  // ── MoralKeyPool State ──
  const moralisStatus = ref(null)   // MoralKeyPool 状态快照
  const moralisLoading = ref(false)
  const moralisPoolId = ref('')     // 当前配置的 pool_identifier

  // ── Block Time Config State ──
  const blockTimeConfig = ref({})   // chain_id → { chain_id, block_time_seconds, default_seconds, is_customized }
  const blockTimeLoading = ref(false)

  // ── RPC Getters ──
  const configuredChains = computed(() =>
    configs.value.filter(c => c.configured)
  )

  const unconfiguredChains = computed(() =>
    configs.value.filter(c => !c.configured)
  )

  const statusMap = computed(() => {
    const map = {}
    for (const s of poolStatus.value) {
      map[s.chainId] = s
    }
    return map
  })

  // ── Moralis Getters ──
  const moralisOk = computed(() =>
    moralisStatus.value && (moralisStatus.value.is_ready || false)
  )
  const moralisKeyCount = computed(() =>
    moralisStatus.value ? (moralisStatus.value.key_count || 0) : 0
  )
  const moralisInitialized = computed(() =>
    moralisStatus.value ? !!moralisStatus.value.initialized : false
  )

  // ── Block Time Getters ──
  const blockTimeList = computed(() =>
    Object.values(blockTimeConfig.value).sort((a, b) => a.chain_id - b.chain_id)
  )

  // ── RPC Actions ──
  async function fetchConfig() {
    loading.value = true
    error.value = ''
    try {
      configs.value = await poolConfigApi.getConfig()
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function fetchStatus() {
    try {
      poolStatus.value = await poolConfigApi.getStatus()
    } catch (e) {
      console.warn('[poolStore] Failed to fetch status:', e.message)
    }
  }

  async function updatePoolIdentifier(chainId, poolIdentifier) {
    const result = await poolConfigApi.updatePoolIdentifier(chainId, poolIdentifier)
    const item = configs.value.find(c => c.chain_id === chainId)
    if (item) {
      item.pool_identifier = poolIdentifier
      item.configured = true
    }
    await fetchStatus()
    return result
  }

  async function runHealthCheck(chainId = null) {
    healthLoading.value = true
    try {
      healthReports.value = await poolConfigApi.runHealthCheck(chainId)
    } finally {
      healthLoading.value = false
    }
  }

  async function reloadConfig() {
    const result = await poolConfigApi.reloadConfig()
    await fetchConfig()
    await fetchStatus()
    return result
  }

  async function testConnection(url, timeout = 15) {
    return await poolConfigApi.testConnection(url, timeout)
  }

  // ── MoralKeyPool Actions ──

  async function fetchMoralisStatus() {
    try {
      moralisStatus.value = await poolConfigApi.getMoralisStatus()
      if (moralisStatus.value) {
        moralisPoolId.value = moralisStatus.value.pool_identifier || ''
      }
    } catch (e) {
      console.warn('[poolStore] Failed to fetch moralis status:', e.message)
    }
  }

  async function updateMoralisPoolConfig(poolIdentifier) {
    const result = await poolConfigApi.updateMoralisPoolConfig(poolIdentifier)
    moralisPoolId.value = poolIdentifier
    return result
  }

  async function reloadMoralisPool() {
    moralisLoading.value = true
    try {
      const result = await poolConfigApi.reloadMoralisPool()
      await fetchMoralisStatus()
      return result
    } finally {
      moralisLoading.value = false
    }
  }

  // ── Block Time Config Actions ──

  async function fetchBlockTimeConfig() {
    blockTimeLoading.value = true
    try {
      const data = await poolConfigApi.getBlockTimeConfig()
      blockTimeConfig.value = data.chains || {}
    } catch (e) {
      console.warn('[poolStore] Failed to fetch block time config:', e.message)
    } finally {
      blockTimeLoading.value = false
    }
  }

  async function updateBlockTime(chainId, blockTimeSeconds) {
    const result = await poolConfigApi.updateBlockTimeConfig(chainId, blockTimeSeconds)
    // 更新本地状态
    const key = String(chainId)
    if (blockTimeConfig.value[key]) {
      blockTimeConfig.value[key].block_time_seconds = blockTimeSeconds
      blockTimeConfig.value[key].is_customized =
        Math.abs(blockTimeSeconds - (blockTimeConfig.value[key].default_seconds || 0)) > 0.001
    }
    return result
  }

  return {
    // State
    configs,
    poolStatus,
    healthReports,
    loading,
    healthLoading,
    error,
    moralisStatus,
    moralisLoading,
    moralisPoolId,
    blockTimeConfig,
    blockTimeLoading,

    // Getters - RPC
    configuredChains,
    unconfiguredChains,
    statusMap,
    // Getters - Moralis
    moralisOk,
    moralisKeyCount,
    moralisInitialized,
    // Getters - Block Time
    blockTimeList,

    // Actions - RPC
    fetchConfig,
    fetchStatus,
    updatePoolIdentifier,
    runHealthCheck,
    reloadConfig,
    testConnection,
    // Actions - Moralis
    fetchMoralisStatus,
    updateMoralisPoolConfig,
    reloadMoralisPool,
    // Actions - Block Time
    fetchBlockTimeConfig,
    updateBlockTime,
  }
})
