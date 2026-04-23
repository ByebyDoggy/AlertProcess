<template>
  <div class="pool-config">
    <!-- 标题栏 -->
    <div class="pc-header">
      <div class="pc-header-left">
        <span class="pc-icon">&#9881;</span>
        <h1 class="pc-title">Pool Configuration</h1>
        <span class="pc-subtitle">apipool-server Management — RPC Pools &amp; Moralis API Keys</span>
      </div>
      <div class="pc-header-right">
        <button class="pc-btn pc-btn-ghost" @click="handleReload" :disabled="reloading || moralisLoading">
          <span :class="{ 'pc-spin': reloading }">&#8635;</span>
          {{ reloading ? 'Reloading...' : 'Reload' }}
        </button>
        <button
          v-if="activeTab === 'rpc'"
          class="pc-btn pc-btn-ghost"
          @click="handleHealthCheck"
          :disabled="healthLoading"
        >
          <span :class="{ 'pc-spin': healthLoading }">&#8757;</span>
          {{ healthLoading ? 'Checking...' : 'Health Check' }}
        </button>
      </div>
    </div>

    <!-- Server 全局配置（两Tab共享） -->
    <div class="pc-server-config">
      <div class="pc-sc-title">
        <span class="pc-sc-icon">&#9729;</span>
        <span>apipool-server Connection (Shared)</span>
      </div>
      <div class="pc-sc-form">
        <div class="pc-sc-row">
          <label class="pc-sc-label">Server URL</label>
          <input
            ref="serverUrlInput"
            class="pc-sc-input"
            type="text"
            v-model="serverConfig.server_url"
            placeholder="e.g. http://localhost:8000"
            spellcheck="false"
          />
        </div>
        <div class="pc-sc-row">
          <label class="pc-sc-label">Username</label>
          <input
            class="pc-sc-input"
            type="text"
            v-model="serverConfig.username"
            placeholder="apipool username"
            spellcheck="false"
          />
        </div>
        <div class="pc-sc-row">
          <label class="pc-sc-label">Password</label>
          <input
            class="pc-sc-input"
            :type="showPwd ? 'text' : 'password'"
            v-model="serverConfig.password"
            placeholder="apipool password (****** = unchanged)"
            spellcheck="false"
          />
          <button class="pc-sc-toggle" @click="showPwd = !showPwd" :title="showPwd ? 'Hide' : 'Show'">
            {{ showPwd ? '&#128065;' : '&#129482;' }}
          </button>
        </div>
        <div class="pc-sc-actions">
          <button class="pc-btn pc-btn-save" @click="handleSaveServerConfig" :disabled="savingServer">
            {{ savingServer ? '...' : 'Save Connection' }}
          </button>
          <button class="pc-btn pc-btn-ghost" @click="handleReload" :disabled="reloading">
            <span :class="{ 'pc-spin': reloading }">&#8635;</span>
            Reload &amp; Connect
          </button>
        </div>
      </div>
    </div>

    <!-- ════════ TAB BAR ════════ -->
    <div class="pc-tab-bar">
      <button
        :class="['pc-tab', { 'pc-tab-active': activeTab === 'rpc' }]"
        @click="activeTab = 'rpc'"
      >
        &#9670; RPC Pools
        <span v-if="configuredCount > 0" class="pc-tab-badge">{{ configuredCount }}</span>
      </button>
      <button
        :class="['pc-tab', { 'pc-tab-active': activeTab === 'moralis' }]"
        @click="activeTab = 'moralis'"
      >
        &#128274; Moralis Key Pool
        <span v-if="moralisOk" class="pc-tab-badge tag-ok">{{ moralisKeyCount }}</span>
      </button>
    </div>

    <!-- ════════ TAB 1: RPC POOLS ════════ -->
    <div v-show="activeTab === 'rpc'" class="pc-tab-content">
      <!-- 连接状态提示 -->
      <div v-if="serverInfo" class="pc-server-info">
        <span :class="['pc-server-dot', hasValidConfig ? 'dot-ok' : 'dot-unknown']"></span>
        <span class="pc-server-label">Connected:</span>
        <span class="pc-server-url">{{ serverInfo.url || '(not configured)' }}</span>
        <span class="pc-server-badge">{{ configuredCount }}/{{ totalChains }} chains</span>
      </div>

      <!-- 未配置提示 -->
      <div v-if="!loading && configs.length > 0 && !hasValidConfig" class="pc-empty-state">
        <div class="pc-empty-icon">&#9888;</div>
        <div class="pc-empty-text">
          <p class="pc-empty-title">Server Not Configured</p>
          <p class="pc-empty-desc">
            Fill in the apipool-server connection details above (URL, Username, Password),
            then click <strong>Save Connection</strong> followed by <strong>Reload &amp; Connect</strong>.
          </p>
        </div>
      </div>

      <!-- 未配置 pool 提示 -->
      <div v-if="!loading && configs.length > 0 && hasValidConfig && configuredCount === 0" class="pc-empty-state">
        <div class="pc-empty-icon">&#9888;</div>
        <div class="pc-empty-text">
          <p class="pc-empty-title">No RPC Pools Configured</p>
          <p class="pc-empty-desc">
            Set a pool identifier for each chain below. Each identifier corresponds to an RPC pool you created on your apipool-server.
          </p>
        </div>
      </div>

      <!-- 配置列表 -->
      <div v-if="configs.length > 0" class="pc-grid">
        <div
          v-for="chain in configs"
          :key="chain.chain_id"
          :class="['pc-card', { 'pc-card-active': chain.configured, 'pc-card-inactive': !chain.configured }]"
        >
          <div class="pc-card-hdr">
            <div class="pc-chain-info">
              <span class="pc-chain-id">{{ chain.chain_id }}</span>
              <span class="pc-chain-name">{{ chain.chain_name }}</span>
            </div>
            <span :class="['pc-status-dot', chainStatusClass(chain.chain_id)]"></span>
          </div>

          <div class="pc-card-body">
            <label class="pc-label">Pool Identifier</label>
            <div class="pc-input-group">
              <input
                :ref="el => inputRefs[chain.chain_id] = el"
                class="pc-input"
                type="text"
                :value="chain.pool_identifier"
                :placeholder="`e.g. ${defaultPoolId(chain.chain_id)}`"
                @keydown.enter="handleSave(chain.chain_id)"
                spellcheck="false"
              />
              <button
                class="pc-btn pc-btn-save"
                @click="handleSave(chain.chain_id)"
                :disabled="saving[chain.chain_id]"
              >
                {{ saving[chain.chain_id] ? '...' : 'Save' }}
              </button>
            </div>
          </div>

          <div v-if="chain.configured && statusMap[chain.chain_id]" class="pc-card-status">
            <div class="pc-stat">
              <span class="pc-stat-label">Nodes</span>
              <span class="pc-stat-val">{{ statusMap[chain.chain_id].healthyNodes }}/{{ statusMap[chain.chain_id].totalNodes }}</span>
            </div>
            <div v-if="statusMap[chain.chain_id].poolIdentifier" class="pc-stat">
              <span class="pc-stat-label">Pool</span>
              <span class="pc-stat-val pc-stat-pool">{{ statusMap[chain.chain_id].poolIdentifier }}</span>
            </div>
          </div>

          <div v-if="healthMap[chain.chain_id]" class="pc-card-health">
            <span :class="['pc-health-tag', healthMap[chain.chain_id].status === 'ok' ? 'tag-ok' : 'tag-err']">
              {{ healthMap[chain.chain_id].status === 'ok' ? 'Healthy' : 'Error' }}
            </span>
            <span v-if="healthMap[chain.chain_id].error" class="pc-health-err" :title="healthMap[chain.chain_id].error">
              {{ truncateError(healthMap[chain.chain_id].error) }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- ════════ TAB 2: MORALIS KEY POOL ════════ -->
    <div v-show="activeTab === 'moralis'" class="pc-tab-content">

      <!-- Moralis Pool 配置面板 -->
      <div class="pc-moralis-panel">
        <div class="pc-moralis-info">
          <div class="pc-moralis-info-left">
            <span class="pc-moralis-icon">&#128274;</span>
            <div>
              <h3 class="pc-moralis-title">Moralis API Key Pool</h3>
              <p class="pc-moralis-desc">
                Store your Moralis API keys on apipool-server and manage them here.
                The <code>AddressAgeDetector</code> provider will load keys from this pool automatically.
              </p>
            </div>
          </div>
          <div :class="['pc-pool-badge', moralisOk ? 'badge-ok' : 'badge-err']">
            {{ moralisOk ? `${moralisKeyCount} Key${moralisKeyCount !== 1 ? 's' : ''} Ready` : (moralisInitialized ? 'Not Ready' : 'Not Initialized') }}
          </div>
        </div>

        <!-- Pool Identifier 输入 -->
        <div class="pc-moralis-form">
          <div class="pc-sc-row">
            <label class="pc-sc-label">Pool Identifier</label>
            <div class="pc-input-group">
              <input
                ref="moralisInputRef"
                class="pc-input"
                type="text"
                v-model="localMoralisPoolId"
                placeholder='e.g. "moralis-keys"'
                spellcheck="false"
                @keydown.enter="handleSaveMoralisConfig"
              />
              <button
                class="pc-btn pc-btn-save"
                @click="handleSaveMoralisConfig"
                :disabled="savingMoralis"
              >
                {{ savingMoralis ? '...' : 'Save' }}
              </button>
            </div>
          </div>
          <div class="pc-moralis-actions">
            <button class="pc-btn pc-btn-ghost" @click="handleReloadMoralis" :disabled="moralisLoading">
              <span :class="{ 'pc-spin': moralisLoading }">&#8635;</span>
              Reload Keys from Server
            </button>
          </div>
        </div>

        <!-- 状态详情 -->
        <div v-if="moralisStatus" class="pc-moralis-status-grid">
          <div class="pc-ms-item">
            <span class="pc-ms-label">Status</span>
            <span :class="['pc-ms-val', moralisStatus.initialized ? (moralisStatus.is_ready ? 'val-ok' : 'val-warn') : 'val-off']">
              {{ moralisStatus.initialized ? (moralisStatus.is_ready ? 'Ready' : 'Empty/Error') : 'Not Initialized' }}
            </span>
          </div>
          <div class="pc-ms-item">
            <span class="pc-ms-label">Pool ID</span>
            <span class="pc-ms-val val-str">{{ moralisStatus.pool_identifier || '(none)' }}</span>
          </div>
          <div class="pc-ms-item">
            <span class="pc-ms-label">Keys Loaded</span>
            <span :class="['pc-ms-val', moralisStatus.key_count > 0 ? 'val-ok' : 'val-warn']">
              {{ moralisStatus.key_count ?? 0 }}
            </span>
          </div>
          <div class="pc-ms-item">
            <span class="pc-ms-label">Service URL</span>
            <span class="pc-ms-val val-str">{{ moralisStatus.service_url || '(none)' }}</span>
          </div>
        </div>

        <!-- 未初始化提示 -->
        <div v-if="!moralisInitialized && !moralisLoading" class="pc-empty-state">
          <div class="pc-empty-icon">&#128274;</div>
          <div class="pc-empty-text">
            <p class="pc-empty-title">Moralis Pool Not Initialized</p>
            <p class="pc-empty-desc">
              Set the <strong>Pool Identifier</strong> to point to your Moralis API key pool on apipool-server,
              then click <strong>Reload Keys from Server</strong> to connect.
            </p>
          </div>
        </div>

        <!-- 区块时间配置（用于地址年龄区块差估算） -->
        <div class="pc-block-time-section">
          <div class="pc-bt-header">
            <span class="pc-bt-icon">&#9201;</span>
            <div>
              <h3 class="pc-bt-title">Block Time Configuration</h3>
              <p class="pc-bt-desc">
                Configure per-chain block time for address age estimation via block difference.
                Used when both first_block_number and current block_number are available.
                Default values are built-in; customize as needed.
              </p>
            </div>
          </div>

          <div v-if="store.blockTimeLoading" class="pc-loading" style="padding: 12px;">
            <span class="pc-spin">&#8635;</span> Loading block time config...
          </div>

          <div v-else class="pc-bt-grid">
            <div
              v-for="chain in store.blockTimeList"
              :key="chain.chain_id"
              :class="['pc-bt-row', { 'pc-bt-customized': chain.is_customized }]"
            >
              <span class="pc-bt-chain-id">{{ chain.chain_id }}</span>
              <input
                type="number"
                step="0.01"
                min="0.1"
                max="3600"
                class="pc-bt-input"
                :value="chain.block_time_seconds"
                :ref="el => btInputRefs[chain.chain_id] = el"
                @keydown.enter="handleSaveBlockTime(chain.chain_id)"
                spellcheck="false"
              />
              <span class="pc-bt-unit">sec/block</span>
              <button
                class="pc-btn pc-btn-save pc-btn-sm"
                @click="handleSaveBlockTime(chain.chain_id)"
                :disabled="savingBt[chain.chain_id]"
              >
                {{ savingBt[chain.chain_id] ? '...' : 'Save' }}
              </button>
              <span v-if="chain.is_customized" class="pc-bt-tag-custom">custom</span>
              <span v-else class="pc-bt-tag-default">default</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="pc-loading">
      <span class="pc-spin">&#8635;</span> Loading configuration...
    </div>

    <!-- 错误 -->
    <div v-if="error && !loading" class="pc-error">
      <span>&#9888;</span> {{ error }}
    </div>

    <!-- Toast 提示 -->
    <Transition name="fade">
      <div v-if="toast" :class="['pc-toast', `pc-toast-${toast.type}`]">{{ toast.message }}</div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, reactive, watch, onMounted } from 'vue'
import { usePoolStore } from '@/stores/poolConfig.js'
import { poolConfigApi } from '@/api/poolConfig.js'

const store = usePoolStore()

// ── State ──
const activeTab = ref('rpc')
const loading = computed(() => store.loading)
const error = computed(() => store.error)
const configs = computed(() => store.configs)
const poolStatus = computed(() => store.poolStatus)
const statusMap = computed(() => store.statusMap)
const healthLoading = computed(() => store.healthLoading)
const healthReports = computed(() => store.healthReports)
const configuredCount = computed(() => configs.value.filter(c => c.configured).length)
const totalChains = computed(() => configs.value.length)
const hasValidConfig = computed(() =>
  !!(serverConfig.server_url && serverConfig.username && serverConfig.password && serverConfig.password !== '******')
)

// Moralis state
const moralisStatus = computed(() => store.moralisStatus)
const moralisLoading = computed(() => store.moralisLoading)
const moralisOk = computed(() => store.moralisOk)
const moralisKeyCount = computed(() => store.moralisKeyCount)
const moralisInitialized = computed(() => store.moralisInitialized)

// ── UI State ──
const reloading = ref(false)
const saving = reactive({})
const inputRefs = reactive({})
const toast = ref(null)
const showPwd = ref(false)
const savingServer = ref(false)
const savingMoralis = ref(false)
const serverUrlInput = ref(null)
const moralisInputRef = ref(null)
const localMoralisPoolId = ref('')
const serverConfig = reactive({
  server_url: '',
  username: '',
  password: '',
})

// Block Time Config UI state
const btInputRefs = reactive({})
const savingBt = reactive({})

// ── Computed ──

const serverInfo = computed(() => {
  if (poolStatus.value.length > 0) {
    const first = poolStatus.value[0]
    return { url: first.serviceUrl || '' }
  }
  return null
})

const healthMap = computed(() => {
  const map = {}
  for (const r of healthReports.value) { map[r.chain_id] = r }
  return map
})

function chainStatusClass(chainId) {
  const s = statusMap.value[chainId]
  if (!s) return 'dot-unknown'
  if (s.healthyNodes > 0) return 'dot-ok'
  if (s.totalNodes > 0) return 'dot-err'
  return 'dot-unknown'
}

function defaultPoolId(chainId) {
  const defaults = { 1: 'ethereum-rpc', 56: 'bsc-rpc', 137: 'polygon-rpc', 42161: 'arbitrum-rpc', 10: 'optimism-rpc', 43114: 'avalanche-rpc' }
  return defaults[chainId] || `chain-${chainId}-rpc`
}

// ── Actions ──

function showToast(message, type = 'ok', duration = 2500) {
  toast.value = { message, type }
  setTimeout(() => { toast.value = null }, duration)
}

async function handleSave(chainId) {
  const input = inputRefs[chainId]
  if (!input) return
  const val = input.value.trim()
  if (!val) { showToast('Pool identifier cannot be empty', 'err'); return }

  saving[chainId] = true
  try {
    await store.updatePoolIdentifier(chainId, val)
    showToast(`Chain ${chainId} pool updated: ${val}`)
  } catch (e) { showToast(`Failed: ${e.message}`, 'err') }
  finally { saving[chainId] = false }
}

async function handleSaveServerConfig() {
  if (!serverConfig.server_url.trim()) { showToast('Server URL is required', 'err'); return }
  savingServer.value = true
  try {
    await poolConfigApi.updateServerConfig({
      serverUrl: serverConfig.server_url.trim(),
      username: serverConfig.username.trim(),
      password: serverConfig.password,
    })
    if (serverConfig.password && serverConfig.password !== '******') {
      serverConfig.password = '******'
    }
    showToast('Server connection saved. Click Reload & Connect to apply.')
  } catch (e) { showToast(`Failed: ${e.message}`, 'err', 3500) }
  finally { savingServer.value = false }
}

async function handleReload() {
  reloading.value = true
  try {
    // 同时重载 RPC 和 Moralis
    if (activeTab.value === 'rpc') {
      const result = await store.reloadConfig()
      showToast(`RPC Reloaded: ${result.totalChains} chains`)
    } else {
      const result = await store.reloadMoralisPool()
      showToast(result.message || 'Moralis pool reloaded')
    }
  } catch (e) { showToast(`Reload failed: ${e.message}`, 'err') }
  finally { reloading.value = false }
}

async function handleHealthCheck() {
  try {
    await store.runHealthCheck()
    const ok = healthReports.value.filter(r => r.status === 'ok').length
    showToast(`Health check: ${ok}/${healthReports.value.length} OK`)
  } catch (e) { showToast(`Health check failed: ${e.message}`, 'err') }
}

async function handleSaveMoralisConfig() {
  const val = localMoralisPoolId.value.trim()
  if (!val) { showToast('Pool Identifier cannot be empty', 'err'); return }

  savingMoralis.value = true
  try {
    await store.updateMoralisPoolConfig(val)
    showToast(`Moralis pool config saved: ${val}. Click Reload Keys.`)
  } catch (e) { showToast(`Failed: ${e.message}`, 'err') }
  finally { savingMoralis.value = false }
}

async function handleReloadMoralis() {
  try {
    const result = await store.reloadMoralisPool()
    showToast(result.message || `Loaded ${result.keyCount || 0} keys`)
  } catch (e) { showToast(`Moralis reload failed: ${e.message}`, 'err') }
}

function truncateError(err) { return err?.length > 60 ? err.slice(0, 60) + '...' : err || '' }

async function handleSaveBlockTime(chainId) {
  const input = btInputRefs[chainId]
  if (!input) return
  const val = parseFloat(input.value)
  if (!val || val <= 0 || val > 3600) { showToast('Block time must be 0.1~3600 seconds', 'err'); return }

  savingBt[chainId] = true
  try {
    await store.updateBlockTime(chainId, val)
    showToast(`Chain ${chainId} block time: ${val}s`)
  } catch (e) { showToast(`Failed: ${e.message}`, 'err') }
  finally { savingBt[chainId] = false }
}

// ── Init ──

// 切换到 Moralis Tab 时自动获取状态
watch(activeTab, (tab) => {
  if (tab === 'moralis' && !moralisLoading.value) {
    store.fetchMoralisStatus()
  }
})

onMounted(async () => {
  // 加载 Server 全局配置
  try {
    const sc = await poolConfigApi.getServerConfig()
    serverConfig.server_url = sc.server_url || ''
    serverConfig.username = sc.username || ''
    serverConfig.password = sc.has_password ? '******' : ''
  } catch (e) { console.warn('Failed to load server config:', e) }

  // 加载链配置 + Moralis 状态 + 区块时间配置
  await Promise.all([
    store.fetchConfig(),
    store.fetchMoralisStatus(),
    store.fetchBlockTimeConfig(),
  ])

  if (configuredCount.value > 0) { store.fetchStatus() }

  localMoralisPoolId.value = store.moralisPoolId || ''
})
</script>

<style scoped>
.pool-config {
  padding: 20px 28px;
  max-width: 960px;
  margin: 0 auto;
  font-family: 'JetBrains Mono', 'SF Mono', 'Cascadia Code', monospace;
}

/* ── Header ── */
.pc-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
.pc-header-left { display: flex; align-items: center; gap: 10px; }
.pc-icon { font-size: 20px; color: #6366f1; }
.pc-title { font-size: 18px; font-weight: 700; color: #e2e8f0; margin: 0; letter-spacing: -0.3px; }
.pc-subtitle { font-size: 11px; color: #475569; margin-left: 4px; }
.pc-header-right { display: flex; gap: 6px; }

/* ── Buttons ── */
.pc-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 6px 14px; border-radius: 6px; font-size: 12px;
  font-weight: 600; cursor: pointer; transition: all .12s;
  border: 1px solid transparent; font-family: inherit;
}
.pc-btn:disabled { opacity: .5; cursor: not-allowed; }
.pc-btn-ghost { background: rgba(99,102,241,.06); color: #818cf8; border-color: rgba(99,102,241,.15); }
.pc-btn-ghost:hover:not(:disabled) { background: rgba(99,102,241,.12); border-color: rgba(99,102,241,.3); }
.pc-btn-save { background: #6366f1; color: #fff; border: none; border-radius: 0 5px 5px 0; padding: 7px 16px; }
.pc-btn-save:hover:not(:disabled) { background: #4f46e5; }

/* ── Server Config Panel ── */
.pc-server-config {
  padding: 18px 20px; border-radius: 8px; margin-bottom: 16px;
  background: #0f172a; border: 1px solid rgba(99,102,241,.12);
}
.pc-sc-title { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 700; color: #c4b5fd; margin-bottom: 14px; }
.pc-sc-icon { font-size: 15px; }
.pc-sc-form { display: grid; gap: 10px; }
.pc-sc-row { display: flex; align-items: center; gap: 12px; }
.pc-sc-label { width: 90px; font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: .3px; flex-shrink: 0; }
.pc-sc-input {
  flex: 1; padding: 7px 12px; border-radius: 6px;
  background: #0c1222; border: 1px solid #21262d;
  color: #c9d1d9; font-size: 12px; font-family: inherit;
  transition: border-color .12s;
}
.pc-sc-input:focus { outline: none; border-color: #6366f1; }
.pc-sc-input::placeholder { color: #30363d; }
.pc-sc-toggle {
  width: 32px; height: 30px; display: flex; align-items: center; justify-content: center;
  background: transparent; border: 1px solid #21262d; border-radius: 6px;
  cursor: pointer; color: #64748b; font-size: 14px;
  transition: all .12s; flex-shrink: 0;
}
.pc-sc-toggle:hover { background: rgba(99,102,241,.08); color: #818cf8; border-color: #30363d; }
.pc-sc-actions { display: flex; gap: 8px; margin-top: 8px; padding-left: 102px; }

/* ── Tab Bar ── */
.pc-tab-bar {
  display: flex; gap: 4px; margin-bottom: 16px;
  border-bottom: 1px solid #1e293b; padding-bottom: 0;
}
.pc-tab {
  display: flex; align-items: center; gap: 7px;
  padding: 10px 20px; border: none; border-bottom: 2px solid transparent;
  background: transparent; cursor: pointer;
  font-family: inherit; font-size: 13px; font-weight: 600;
  color: #64748b; transition: all .15s; border-radius: 6px 6px 0 0;
}
.pc-tab:hover:not(.pc-tab-active) { background: rgba(99,102,241,.04); color: #94a3b8; }
.pc-tab-active { color: #c4b5fd; border-bottom-color: #6366f1; background: rgba(99,102,241,.05); }
.pc-tab-badge {
  font-size: 10px; padding: 1px 7px; border-radius: 8px; font-weight: 700;
  background: rgba(100,116,139,.15); color: #64748b;
}
.pc-tab-active .pc-tab-badge { background: rgba(99,102,241,.15); color: #818cf8; }

/* ── Tab Content ── */
.pc-tab-content { animation: fadeIn .15s ease; }

@keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

/* ── Server Info ── */
.pc-server-info {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 14px; border-radius: 6px; margin-bottom: 16px;
  background: rgba(99,102,241,.04); border: 1px solid rgba(99,102,241,.1);
  font-size: 11.5px;
}
.pc-server-dot { width: 7px; height: 7px; border-radius: 50%; background: #3fb950; flex-shrink: 0; }
.pc-server-label { color: #64748b; font-weight: 600; }
.pc-server-url { color: #94a3b8; }
.pc-server-badge { margin-left: auto; background: rgba(99,102,241,.1); color: #818cf8; padding: 1px 8px; border-radius: 8px; font-size: 10px; font-weight: 700; }

/* ── Empty State ── */
.pc-empty-state {
  display: flex; gap: 16px; padding: 24px; border-radius: 8px;
  background: rgba(251,191,36,.04); border: 1px solid rgba(251,191,36,.12);
  margin-bottom: 16px;
}
.pc-empty-icon { font-size: 28px; color: #fbbf24; }
.pc-empty-title { font-size: 13px; font-weight: 700; color: #e2e8f0; margin: 0 0 4px; }
.pc-empty-desc { font-size: 11.5px; color: #64748b; line-height: 1.6; margin: 0; }
.pc-empty-desc code { background: rgba(99,102,241,.1); color: #818cf8; padding: 1px 5px; border-radius: 3px; font-size: 10.5px; }

/* ── Grid ── */
.pc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }

/* ── Card ── */
.pc-card {
  border-radius: 8px; overflow: hidden; transition: all .15s;
  border: 1px solid #1e293b;
}
.pc-card-active { background: #0f172a; border-color: rgba(99,102,241,.15); }
.pc-card-inactive { background: #0c1222; border-color: #1e293b; opacity: .7; }
.pc-card:hover { border-color: rgba(99,102,241,.25); }

.pc-card-hdr { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; border-bottom: 1px solid #1e293b; }
.pc-chain-info { display: flex; align-items: center; gap: 8px; }
.pc-chain-id { font-size: 10px; font-weight: 700; color: #6366f1; background: rgba(99,102,241,.1); padding: 2px 7px; border-radius: 4px; }
.pc-chain-name { font-size: 13px; font-weight: 600; color: #e2e8f0; }

.pc-status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot-ok { background: #3fb950; box-shadow: 0 0 6px rgba(63,185,80,.3); }
.dot-err { background: #f85149; box-shadow: 0 0 6px rgba(248,81,73,.3); }
.dot-unknown { background: #475569; }

/* ── Card Body ── */
.pc-card-body { padding: 10px 14px; }
.pc-label { font-size: 9.5px; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: .5px; display: block; margin-bottom: 5px; }
.pc-input-group { display: flex; }
.pc-input {
  flex: 1; padding: 7px 10px; border-radius: 5px 0 0 5px;
  background: #0d1117; border: 1px solid #21262d; border-right: none;
  color: #c9d1d9; font-size: 12px; font-family: inherit;
  transition: border-color .12s;
}
.pc-input:focus { outline: none; border-color: #6366f1; }
.pc-input::placeholder { color: #30363d; }

/* ── Card Status ── */
.pc-card-status { display: flex; gap: 12px; padding: 8px 14px; border-top: 1px solid #1e293b; font-size: 10.5px; }
.pc-stat { display: flex; flex-direction: column; gap: 1px; }
.pc-stat-label { color: #475569; font-weight: 600; text-transform: uppercase; }
.pc-stat-val { color: #94a3b8; font-weight: 500; }
.pc-stat-pool { color: #818cf8; }

/* ── Card Health ── */
.pc-card-health { display: flex; align-items: center; gap: 8px; padding: 6px 14px; border-top: 1px solid #1e293b; font-size: 10.5px; }
.pc-health-tag { padding: 1px 8px; border-radius: 3px; font-weight: 700; text-transform: uppercase; letter-spacing: .3px; }
.tag-ok { background: rgba(63,185,80,.1); color: #3fb950; }
.tag-err { background: rgba(248,81,73,.1); color: #f85149; }
.pc-health-err { color: #64748b; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ════════ MORALIS PANEL STYLES ════════ */

.pc-moralis-panel {
  padding: 18px 22px; border-radius: 8px;
  background: #0f172a; border: 1px solid rgba(168,85,247,.12);
}

.pc-moralis-info {
  display: flex; align-items: flex-start; justify-content: space-between;
  margin-bottom: 18px; padding-bottom: 14px;
  border-bottom: 1px solid rgba(255,255,255,.04);
}

.pc-moralis-info-left {
  display: flex; gap: 12px; align-items: flex-start;
}

.pc-moralis-icon { font-size: 26px; margin-top: 2px; }

.pc-moralis-title {
  font-size: 15px; font-weight: 700; color: #e2e8f0; margin: 0 0 4px;
}

.pc-moralis-desc {
  font-size: 11.5px; color: #64748b; line-height: 1.55; margin: 0; max-width: 520px;
}
.pc-moralis-desc code {
  background: rgba(168,85,247,.1); color: #c084fc; padding: 1px 5px;
  border-radius: 3px; font-size: 10.5px;
}

.pc-pool-badge {
  padding: 4px 12px; border-radius: 12px; font-size: 11px; font-weight: 700;
  white-space: nowrap; flex-shrink: 0;
}
.badge-ok { background: rgba(63,185,80,.12); color: #3fb950; }
.badge-err { background: rgba(251,191,36,.12); color: #fbbf24; }

.pc-moralis-form { margin-bottom: 16px; }
.pc-moralis-actions {
  display: flex; gap: 8px; margin-top: 8px; padding-left: 102px;
}

/* Status Grid */
.pc-moralis-status-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px; margin-bottom: 12px;
}

.pc-ms-item {
  padding: 8px 12px; border-radius: 6px;
  background: rgba(0,0,0,.2); border: 1px solid rgba(255,255,255,.04);
  display: flex; flex-direction: column; gap: 3px;
}

.pc-ms-label { font-size: 9.5px; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: .4px; }
.pc-ms-val { font-size: 12px; font-weight: 500; word-break: break-all; }

.val-ok { color: #3fb950; }
.val-warn { color: #fbbf24; }
.val-err { color: #f85149; }
.val-off { color: #475569; }
.val-str { color: #94a3b8; }

/* ── Loading / Error ── */
.pc-loading { display: flex; align-items: center; justify-content: center; gap: 6px; padding: 40px; color: #8b949e; font-size: 13px; }
.pc-error { display: flex; align-items: center; gap: 6px; padding: 12px 16px; border-radius: 6px; background: rgba(248,81,73,.06); border: 1px solid rgba(248,81,73,.15); color: #f85149; font-size: 12px; }

/* ── Spin ── */
.pc-spin { animation: spin 1s linear infinite; display: inline-block; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Toast ── */
.pc-toast {
  position: fixed; bottom: 24px; right: 24px; z-index: 10000;
  padding: 8px 20px; border-radius: 6px; font-size: 12px; font-weight: 600;
  box-shadow: 0 4px 16px rgba(0,0,0,.3);
  animation: toastIn .2s ease;
}
.pc-toast-ok { background: #238636; color: #fff; }
.pc-toast-err { background: #da3633; color: #fff; }
@keyframes toastIn { from { opacity: 0; transform: translateY(8px); } }

/* ── Fade ── */
.fade-enter-active, .fade-leave-active { transition: opacity .25s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* ════════ BLOCK TIME CONFIG STYLES ════════ */

.pc-block-time-section {
  margin-top: 18px;
  padding: 18px 22px;
  border-radius: 8px;
  background: rgba(99,102,241,.03);
  border: 1px solid rgba(99,102,241,.08);
}

.pc-bt-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(255,255,255,.04);
}

.pc-bt-icon { font-size: 22px; margin-top: 2px; }

.pc-bt-title {
  font-size: 14px;
  font-weight: 700;
  color: #e2e8f0;
  margin: 0 0 3px;
}

.pc-bt-desc {
  font-size: 11.5px;
  color: #64748b;
  line-height: 1.55;
  margin: 0;
  max-width: 600px;
}

.pc-bt-grid { display: flex; flex-direction: column; gap: 6px; }

.pc-bt-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  border-radius: 6px;
  background: rgba(0,0,0,.15);
  border: 1px solid transparent;
  transition: all .12s;
}
.pc-bt-row:hover { border-color: rgba(99,102,241,.15); }
.pc-bt-customized { background: rgba(168,85,247,.05); border-color: rgba(168,85,247,.1); }

.pc-bt-chain-id {
  width: 36px;
  font-size: 10px;
  font-weight: 700;
  color: #a78bfa;
  background: rgba(167,139,250,.1);
  padding: 2px 6px;
  border-radius: 4px;
  text-align: center;
  flex-shrink: 0;
}

.pc-bt-input {
  width: 80px;
  padding: 5px 8px;
  border-radius: 5px;
  background: #0c1222;
  border: 1px solid #21262d;
  color: #c9d1d9;
  font-size: 12px;
  font-family: inherit;
  text-align: right;
  transition: border-color .12s;
}
.pc-bt-input:focus { outline: none; border-color: #6366f1; }

.pc-bt-unit { font-size: 11px; color: #475569; flex-shrink: 0; }

.pc-btn-sm { padding: 4px 10px; font-size: 11px; }

.pc-bt-tag-custom {
  margin-left: auto;
  font-size: 9px;
  font-weight: 700;
  color: #c084fc;
  background: rgba(192,132,252,.1);
  padding: 1px 7px;
  border-radius: 8px;
  text-transform: uppercase;
  letter-spacing: .3px;
}

.pc-bt-tag-default {
  margin-left: auto;
  font-size: 9px;
  font-weight: 700;
  color: #475569;
  background: rgba(100,116,139,.08);
  padding: 1px 7px;
  border-radius: 8px;
  text-transform: uppercase;
  letter-spacing: .3px;
}
</style>
