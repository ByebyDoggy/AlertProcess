<template>
  <div class="pool-config">
    <!-- 标题栏 -->
    <div class="pc-header">
      <div class="pc-header-left">
        <span class="pc-icon">&#9881;</span>
        <h1 class="pc-title">Pool Configuration</h1>
        <span class="pc-subtitle">apipool-server Pool Identifier Management</span>
      </div>
      <div class="pc-header-right">
        <button class="pc-btn pc-btn-ghost" @click="handleReload" :disabled="reloading">
          <span :class="{ 'pc-spin': reloading }">&#8635;</span>
          {{ reloading ? 'Reloading...' : 'Reload' }}
        </button>
        <button class="pc-btn pc-btn-ghost" @click="handleHealthCheck" :disabled="healthLoading">
          <span :class="{ 'pc-spin': healthLoading }">&#8757;</span>
          {{ healthLoading ? 'Checking...' : 'Health Check' }}
        </button>
      </div>
    </div>

    <!-- Server 全局配置 -->
    <div class="pc-server-config">
      <div class="pc-sc-title">
        <span class="pc-sc-icon">&#9729;</span>
        <span>apipool-server Connection</span>
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
            Reload & Connect
          </button>
        </div>
      </div>
    </div>

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
        <p class="pc-empty-title">No Pools Configured</p>
        <p class="pc-empty-desc">
          Set a pool identifier for each chain below. Each identifier corresponds to a pool you created on your apipool-server.
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
        <!-- 卡片头部 -->
        <div class="pc-card-hdr">
          <div class="pc-chain-info">
            <span class="pc-chain-id">{{ chain.chain_id }}</span>
            <span class="pc-chain-name">{{ chain.chain_name }}</span>
          </div>
          <span :class="['pc-status-dot', chainStatusClass(chain.chain_id)]"></span>
        </div>

        <!-- Pool Identifier 输入 -->
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

        <!-- 运行状态 -->
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

        <!-- 健康检查结果 -->
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
import { ref, computed, reactive, onMounted } from 'vue'
import { usePoolStore } from '@/stores/poolConfig.js'
import { poolConfigApi } from '@/api/poolConfig.js'

const store = usePoolStore()

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

const reloading = ref(false)
const saving = reactive({})
const inputRefs = reactive({})
const toast = ref(null)
const showPwd = ref(false)
const savingServer = ref(false)
const serverUrlInput = ref(null)
const serverConfig = reactive({
  server_url: '',
  username: '',
  password: '',
})

// 服务器信息
const serverInfo = computed(() => {
  if (poolStatus.value.length > 0) {
    const first = poolStatus.value[0]
    return {
      url: first.serviceUrl || '',
    }
  }
  return null
})

// 健康检查结果映射
const healthMap = computed(() => {
  const map = {}
  for (const r of healthReports.value) {
    map[r.chain_id] = r
  }
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
  const defaults = {
    1: 'ethereum-rpc',
    56: 'bsc-rpc',
    137: 'polygon-rpc',
    42161: 'arbitrum-rpc',
    10: 'optimism-rpc',
    43114: 'avalanche-rpc',
  }
  return defaults[chainId] || `chain-${chainId}-rpc`
}

function showToast(message, type = 'ok', duration = 2500) {
  toast.value = { message, type }
  setTimeout(() => { toast.value = null }, duration)
}

async function handleSave(chainId) {
  const input = inputRefs[chainId]
  if (!input) return
  const val = input.value.trim()
  if (!val) {
    showToast('Pool identifier cannot be empty', 'err')
    return
  }

  saving[chainId] = true
  try {
    await store.updatePoolIdentifier(chainId, val)
    showToast(`Chain ${chainId} pool updated: ${val}`)
  } catch (e) {
    showToast(`Failed: ${e.message}`, 'err')
  } finally {
    saving[chainId] = false
  }
}

async function handleSaveServerConfig() {
  if (!serverConfig.server_url.trim()) {
    showToast('Server URL is required', 'err')
    return
  }
  savingServer.value = true
  try {
    await poolConfigApi.updateServerConfig({
      serverUrl: serverConfig.server_url.trim(),
      username: serverConfig.username.trim(),
      password: serverConfig.password,
    })
    // 如果密码已保存，显示为 ****** 避免明文暴露
    if (serverConfig.password && serverConfig.password !== '******') {
      const savedPwd = serverConfig.password
      serverConfig.password = '******'
    }
    showToast('Server connection config saved. Click Reload & Connect to apply.')
  } catch (e) {
    showToast(`Failed: ${e.message}`, 'err', 3500)
  } finally {
    savingServer.value = false
  }
}

async function handleReload() {
  reloading.value = true
  try {
    const result = await store.reloadConfig()
    showToast(`Reloaded: ${result.totalChains} chains`)
  } catch (e) {
    showToast(`Reload failed: ${e.message}`, 'err')
  } finally {
    reloading.value = false
  }
}

async function handleHealthCheck() {
  try {
    await store.runHealthCheck()
    const ok = healthReports.value.filter(r => r.status === 'ok').length
    showToast(`Health check: ${ok}/${healthReports.value.length} OK`)
  } catch (e) {
    showToast(`Health check failed: ${e.message}`, 'err')
  }
}

function truncateError(err) {
  if (!err) return ''
  return err.length > 60 ? err.slice(0, 60) + '...' : err
}

onMounted(async () => {
  // 加载 Server 全局配置
  try {
    const sc = await poolConfigApi.getServerConfig()
    serverConfig.server_url = sc.server_url || ''
    serverConfig.username = sc.username || ''
    serverConfig.password = sc.has_password ? '******' : ''
  } catch (e) {
    console.warn('Failed to load server config:', e)
  }
  
  // 加载链配置
  await store.fetchConfig()
  if (configuredCount.value > 0) {
    store.fetchStatus()
  }
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
.pc-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 18px;
}
.pc-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.pc-icon { font-size: 20px; color: #6366f1; }
.pc-title {
  font-size: 18px; font-weight: 700; color: #e2e8f0;
  margin: 0; letter-spacing: -0.3px;
}
.pc-subtitle {
  font-size: 11px; color: #475569; margin-left: 4px;
}
.pc-header-right {
  display: flex; gap: 6px;
}

/* ── Buttons ── */
.pc-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 6px 14px; border-radius: 6px; font-size: 12px;
  font-weight: 600; cursor: pointer; transition: all .12s;
  border: 1px solid transparent; font-family: inherit;
}
.pc-btn:disabled { opacity: .5; cursor: not-allowed; }
.pc-btn-ghost {
  background: rgba(99,102,241,.06); color: #818cf8;
  border-color: rgba(99,102,241,.15);
}
.pc-btn-ghost:hover:not(:disabled) {
  background: rgba(99,102,241,.12); border-color: rgba(99,102,241,.3);
}
.pc-btn-save {
  background: #6366f1; color: #fff; border: none; border-radius: 0 5px 5px 0;
  padding: 7px 16px;
}
.pc-btn-save:hover:not(:disabled) { background: #4f46e5; }

/* ── Server Config Panel ── */
.pc-server-config {
  padding: 18px 20px; border-radius: 8px; margin-bottom: 16px;
  background: #0f172a; border: 1px solid rgba(99,102,241,.12);
}
.pc-sc-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; font-weight: 700; color: #c4b5fd; margin-bottom: 14px;
}
.pc-sc-icon { font-size: 15px; }
.pc-sc-form { display: grid; gap: 10px; }
.pc-sc-row {
  display: flex; align-items: center; gap: 12px;
}
.pc-sc-label {
  width: 90px; font-size: 11px; font-weight: 600; color: #64748b;
  text-transform: uppercase; letter-spacing: .3px; flex-shrink: 0;
}
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
.pc-sc-actions {
  display: flex; gap: 8px; margin-top: 8px; padding-left: 102px;
}

/* ── Server Info ── */
.pc-server-info {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 14px; border-radius: 6px; margin-bottom: 16px;
  background: rgba(99,102,241,.04); border: 1px solid rgba(99,102,241,.1);
  font-size: 11.5px;
}
.pc-server-dot {
  width: 7px; height: 7px; border-radius: 50%; background: #3fb950;
  flex-shrink: 0;
}
.pc-server-label { color: #64748b; font-weight: 600; }
.pc-server-url { color: #94a3b8; }
.pc-server-badge {
  margin-left: auto; background: rgba(99,102,241,.1); color: #818cf8;
  padding: 1px 8px; border-radius: 8px; font-size: 10px; font-weight: 700;
}

/* ── Empty State ── */
.pc-empty-state {
  display: flex; gap: 16px; padding: 24px; border-radius: 8px;
  background: rgba(251,191,36,.04); border: 1px solid rgba(251,191,36,.12);
  margin-bottom: 16px;
}
.pc-empty-icon { font-size: 28px; color: #fbbf24; }
.pc-empty-title { font-size: 13px; font-weight: 700; color: #e2e8f0; margin: 0 0 4px; }
.pc-empty-desc { font-size: 11.5px; color: #64748b; line-height: 1.6; margin: 0; }
.pc-empty-desc code {
  background: rgba(99,102,241,.1); color: #818cf8; padding: 1px 5px;
  border-radius: 3px; font-size: 10.5px;
}

/* ── Grid ── */
.pc-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

/* ── Card ── */
.pc-card {
  border-radius: 8px; overflow: hidden; transition: all .15s;
  border: 1px solid #1e293b;
}
.pc-card-active { background: #0f172a; border-color: rgba(99,102,241,.15); }
.pc-card-inactive { background: #0c1222; border-color: #1e293b; opacity: .7; }
.pc-card:hover { border-color: rgba(99,102,241,.25); }

.pc-card-hdr {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px; border-bottom: 1px solid #1e293b;
}
.pc-chain-info { display: flex; align-items: center; gap: 8px; }
.pc-chain-id {
  font-size: 10px; font-weight: 700; color: #6366f1;
  background: rgba(99,102,241,.1); padding: 2px 7px; border-radius: 4px;
}
.pc-chain-name { font-size: 13px; font-weight: 600; color: #e2e8f0; }

/* Status dots */
.pc-status-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
}
.dot-ok { background: #3fb950; box-shadow: 0 0 6px rgba(63,185,80,.3); }
.dot-err { background: #f85149; box-shadow: 0 0 6px rgba(248,81,73,.3); }
.dot-unknown { background: #475569; }

/* ── Card Body ── */
.pc-card-body { padding: 10px 14px; }
.pc-label {
  font-size: 9.5px; font-weight: 700; color: #475569;
  text-transform: uppercase; letter-spacing: .5px;
  display: block; margin-bottom: 5px;
}
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
.pc-card-status {
  display: flex; gap: 12px; padding: 8px 14px;
  border-top: 1px solid #1e293b; font-size: 10.5px;
}
.pc-stat { display: flex; flex-direction: column; gap: 1px; }
.pc-stat-label { color: #475569; font-weight: 600; text-transform: uppercase; }
.pc-stat-val { color: #94a3b8; font-weight: 500; }
.pc-stat-pool { color: #818cf8; }

/* ── Card Health ── */
.pc-card-health {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 14px; border-top: 1px solid #1e293b; font-size: 10.5px;
}
.pc-health-tag {
  padding: 1px 8px; border-radius: 3px; font-weight: 700;
  text-transform: uppercase; letter-spacing: .3px;
}
.tag-ok { background: rgba(63,185,80,.1); color: #3fb950; }
.tag-err { background: rgba(248,81,73,.1); color: #f85149; }
.pc-health-err { color: #64748b; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ── Loading / Error ── */
.pc-loading {
  display: flex; align-items: center; justify-content: center;
  gap: 6px; padding: 40px; color: #8b949e; font-size: 13px;
}
.pc-error {
  display: flex; align-items: center; gap: 6px;
  padding: 12px 16px; border-radius: 6px;
  background: rgba(248,81,73,.06); border: 1px solid rgba(248,81,73,.15);
  color: #f85149; font-size: 12px;
}

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
</style>
