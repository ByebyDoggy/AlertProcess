<template>
  <div class="ca-page">
    <!-- 顶部输入栏 -->
    <div class="ca-header">
      <div class="ca-input-group">
        <label class="ca-label">TX HASH</label>
        <input
          v-model="store.txHash"
          type="text"
          placeholder="0x..."
          class="ca-tx-input"
          :disabled="store.isLoading"
          @keyup.enter="handleAnalyze"
        />
      </div>
      <div class="ca-input-group">
        <label class="ca-label">CHAIN</label>
        <select v-model="store.chainId" class="ca-chain-sel" :disabled="store.isLoading">
          <option v-for="c in store.supportedChains" :key="c.chainId" :value="c.chainId">
            {{ c.name }}
          </option>
        </select>
      </div>
      <button
        class="ca-analyze-btn"
        :class="{ loading: store.isLoading }"
        :disabled="store.isLoading || !store.txHash.trim()"
        @click="handleAnalyze"
      >
        {{ store.isLoading ? 'Analyzing...' : 'Analyze' }}
      </button>

      <div v-if="store.hasError" class="ca-error">&#9888; {{ store.error }}</div>
    </div>

    <!-- 纵向主内容区 — 可上下滚动 -->
    <div class="ca-body-vertical">

      <!-- Panel 1: Call Tree (全宽) -->
      <section class="ca-section ca-section-tree">
        <div class="ca-section-hdr" @click="toggleSection('tree')">
          <span class="ca-section-icon">&#9741;</span>
          <span class="ca-section-title">Call Tree</span>
          <span class="ca-section-badge">{{ nodeCount }}</span>
          <span class="ca-section-toggle">{{ sections.tree ? '&#9650;' : '&#9660;' }}</span>
        </div>
        <div v-show="sections.tree" class="ca-section-body">
          <CallTreeView />
        </div>
      </section>

      <!-- Panel 2: Balance Changes (全宽) -->
      <section v-if="store.balanceChanges.length" class="ca-section">
        <BalanceChangesPanel :changes="store.balanceChanges" />
      </section>

      <!-- Panel 3: Token Flows (全宽) -->
      <section class="ca-section">
        <TokenFlowPanel :flows="store.tokenFlows" />
      </section>

      <!-- Panel 4: Behavior Detection (全宽) -->
      <section class="ca-section">
        <BehaviorPanel :isLoading="store.isLoading" />
      </section>

      <!-- Panel 5: Protocols + TX Info (并排) -->
      <section class="ca-section ca-section-meta">
        <div class="ca-meta-grid">
          <!-- 协议列表 -->
          <div v-if="store.protocols.length" class="ca-card">
            <h4 class="ca-card-title">&#128279; Protocols Involved</h4>
            <div class="ca-proto-list">
              <span v-for="(p,i) in store.protocols" :key="i" class="ca-proto-tag" :class="p.category?.toLowerCase()">
                {{ p.name }}
                <span class="ca-proto-cat">({{ p.category }})</span>
              </span>
            </div>
          </div>

          <!-- TX Info -->
          <div v-if="store.txInfo" class="ca-card">
            <h4 class="ca-card-title">&#128196; Transaction Info</h4>
            <div class="ca-tx-grid">
              <span class="ca-tx-item"><b>Status:</b> <span :class="store.txInfo.status ? 'st-ok' : 'st-fail'">{{ store.txInfo.status ? 'SUCCESS' : 'FAILED' }}</span></span>
              <span class="ca-tx-item"><b>Block:</b> {{ fmtNum(store.txInfo.blockNumber) }}</span>
              <span class="ca-tx-item"><b>From:</b> {{ short(store.txInfo.fromAddress) }}</span>
              <span class="ca-tx-item"><b>To:</b> {{ short(store.txInfo.toAddress) }}</span>
              <span class="ca-tx-item"><b>Gas Used:</b> {{ fmtGas(store.txInfo.gasUsed) }}</span>
              <span class="ca-tx-item"><b>Value:</b> {{ fmtEth(store.txInfo.value) }}</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { reactive, computed, onMounted } from 'vue'
import { useTraceStore } from '@/stores/traceAnalysis.js'
import CallTreeView from '@/components/analysis/CallTreeView.vue'
import BehaviorPanel from '@/components/analysis/BehaviorPanel.vue'
import TokenFlowPanel from '@/components/analysis/TokenFlowPanel.vue'
import BalanceChangesPanel from '@/components/analysis/BalanceChangesPanel.vue'

const store = useTraceStore()

const sections = reactive({
  tree: true,
})

onMounted(() => { store.loadSupportedChains() })

async function handleAnalyze() {
  await store.analyzeTransaction()
  // 分析完成后默认展开所有 section
  sections.tree = true
}

function toggleSection(key) {
  sections[key] = !sections[key]
}

// 节点统计
const nodeCount = computed(() => {
  if (!store.root) return 0
  const meta = store.meta || {}
  return meta.totalNodes || '?'
})

function short(a) {
  if (!a) return '?'
  if (!a.startsWith('0x')) return String(a).slice(0, 16)
  return a.slice(0, 10) + '\u2026' + a.slice(-6)
}
function fmtGas(g) { if (!g) return '-'; return Number(typeof g === 'string' ? parseInt(g,16) : g).toLocaleString() }
function fmtEth(v) {
  if (!v) return '0'
  const n = typeof v === 'string' ? parseInt(v,16) : v
  if (n >= 1e18) return `${+(n/1e18).toFixed(6)} ETH`
  if (n > 0) return `${+((n/1e9).toFixed(2))} Gwei`
  return `${n} wei`
}
function fmtNum(n) { return n != null ? Number(n).toLocaleString() : '-' }
</script>

<style scoped>
.ca-page {
  display: flex; flex-direction: column;
  min-height: 100%;
  padding: 0;
}

/* Header — 固定在顶部 */
.ca-header {
  display: flex; align-items: flex-end; gap: 10px;
  flex-shrink: 0;
  background: #161b22; border: 1px solid #21262d; border-radius: 8px;
  padding: 10px 14px; margin: 12px 16px 0;
}
.ca-input-group { display: flex; flex-direction: column; gap: 4px; }
.ca-label {
  font-size: 11px; font-weight: 700; color: #8b949e; text-transform: uppercase; letter-spacing: .7px;
}
.ca-tx-input {
  width: 420px; min-width: 260px;
  padding: 7px 12px;
  background: #0d1117; border: 1px solid #30363d; border-radius: 6px;
  color: #c9d1d9; font-size: 13px;
  font-family: 'JetBrains Mono', 'SF Mono', monospace; outline: none; transition: border-color .15s;
}
.ca-tx-input:focus { border-color: #58a6ff; box-shadow: 0 0 0 2px rgba(88,166,255,.15); }
.ca-tx-input:disabled { opacity: .55; cursor: not-allowed; }

.ca-chain-sel {
  width: 150px; padding: 7px 9px;
  background: #0d1117; border: 1px solid #30363d; border-radius: 6px;
  color: #c9d1d9; font-size: 13px; outline: none; cursor: pointer;
}

.ca-analyze-btn {
  height: 36px; padding: 0 22px;
  font-size: 13px; font-weight: 600; letter-spacing: .3px;
  background: linear-gradient(135deg, #238636, #2ea043);
  color: white; border: none; border-radius: 6px; cursor: pointer;
  transition: all .15s; white-space: nowrap; align-self: flex-end;
}
.ca-analyze-btn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 3px 12px rgba(46,160,67,.35); }
.ca-analyze-btn:disabled { opacity: .5; cursor: not-allowed; }
.ca-analyze-btn.loading { animation: caPulse 1.2s ease-in-out infinite; background: linear-gradient(135deg, #1f6feb, #388bfd); }
@keyframes caPulse { 0%,100%{opacity:1} 50%{opacity:.7} }

.ca-error {
  margin-left: auto; padding: 5px 12px;
  background: rgba(248,81,73,.08); border: 1px solid rgba(248,81,73,.25); border-radius: 5px;
  color: #f85149; font-size: 12px; align-self: center; max-width: 360px;
}

/* ── 纵向主体：不限制高度，内容自然撑开，页面整体可滚动（仿 BlockSec）── */
.ca-body-vertical {
  display: flex; flex-direction: column;
  gap: 0;
  padding: 16px 16px 40px;
}

/* ── Section 面板 ── */
.ca-section {
  background: #161b22; border: 1px solid #21262d; border-radius: 8px;
  margin-bottom: 12px; overflow: hidden;
}
.ca-section:last-child { margin-bottom: 0; }

/* 可折叠 Section header */
.ca-section-hdr {
  display: flex; align-items: center; gap: 7px;
  padding: 9px 14px; cursor: pointer; user-select: none;
  transition: background .12s; border-bottom: 1px solid rgba(33,38,45,.5);
}
.ca-section-hdr:hover { background: rgba(255,255,255,.03); }
.ca-section-icon { font-size: 13px; }
.ca-section-title {
  font-size: 12.5px; font-weight: 700; color: #e6edf3;
  letter-spacing: .15px; flex: 1;
}
.ca-section-badge {
  font-size: 9.5px; font-weight: 700; color: #484f58;
  background: #0d1117; padding: 1px 7px; border-radius: 8px;
}
.ca-section-toggle { color: #6b7280; font-size: 11px; }

/* Section body */
.ca-section-body { overflow-x: auto; }

/* Tree section — 给一个合理的最大高度，内部可独立滚动 */
.ca-section-tree .ca-section-body {
  max-height: 600px; overflow-y: auto; overflow-x: auto;
}
.ca-section-tree .ca-section-body::-webkit-scrollbar { width: 5px; height: 5px; }
.ca-section-tree .ca-section-body::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }

/* Meta grid (Protocols + TX Info 并排) */
.ca-section-meta { padding: 10px 12px; }
.ca-meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

/* Cards */
.ca-card { background: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 10px 12px; }
.ca-card-title {
  margin: 0 0 8px; font-size: 11.5px; font-weight: 700; color: #8b949e;
  text-transform: uppercase; letter-spacing: .5px;
}
.ca-proto-list { display: flex; flex-wrap: wrap; gap: 4px; }
.ca-proto-tag {
  font-size: 10.5px; padding: 2px 7px; border-radius: 3px;
  background: #161b22; border: 1px solid #30363d; color: #8b949e;
}
.ca-proto-tag.dex { border-color: #388bfd; color: #79c0ff; }
.ca-proto-tag.lending { border-color: #d29922; color: #e3b341; }
.ca-proto-cat { color: #484f58; margin-left: 2px; }

.ca-tx-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 3px 14px; }
.ca-tx-item { font-size: 11px; color: #8b949e; line-height: 1.65; }
.ca-tx-item b { color: #c9d1d9; }
.st-ok { color: #3fb950; font-weight: 600; }
.st-fail { color: #f85149; font-weight: 600; }

/* Responsive */
@media (max-width: 900px) {
  .ca-meta-grid { grid-template-columns: 1fr; }
  .ca-header { flex-wrap: wrap; }
  .ca-tx-input { width: 100%; min-width: unset; }
}
</style>
