/**
 * Pool 配置 Store
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { poolConfigApi } from '@/api/poolConfig.js'

export const usePoolStore = defineStore('poolConfig', () => {
  // ── State ──
  const configs = ref([])           // 所有链的配置
  const poolStatus = ref([])        // 池运行状态
  const healthReports = ref([])     // 健康检查结果
  const loading = ref(false)
  const healthLoading = ref(false)
  const error = ref('')

  // ── Getters ──
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

  // ── Actions ──
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
    // 更新本地状态
    const item = configs.value.find(c => c.chain_id === chainId)
    if (item) {
      item.pool_identifier = poolIdentifier
      item.configured = true
    }
    // 刷新运行状态
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

  return {
    configs,
    poolStatus,
    healthReports,
    loading,
    healthLoading,
    error,
    configuredChains,
    unconfiguredChains,
    statusMap,
    fetchConfig,
    fetchStatus,
    updatePoolIdentifier,
    runHealthCheck,
    reloadConfig,
    testConnection,
  }
})
