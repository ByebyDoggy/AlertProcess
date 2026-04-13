<template>
  <div class="bcp">
    <!-- 标题栏 + 折叠 -->
    <div class="bcp-hdr" @click="expanded = !expanded">
      <span class="bcp-icon">&#9783;</span>
      <span class="bcp-title">Balance Changes</span>
      <span class="bcp-count">{{ totalEntries }}</span>
      <span class="bcp-toggle">{{ expanded ? '&#9650;' : '&#9660;' }}</span>
      <button v-if="changes.length" class="bcp-dl-btn" title="Download CSV" @click.stop="downloadCSV">&#8681;</button>
    </div>

    <!-- 无数据 -->
    <div v-if="!effectiveChanges.length && !isLoading" :class="['bcp-body', { 'bcp-collapsed': !expanded }]">
      <div class="bcp-empty" v-if="!hasError">
        <span>&#128270;</span> No balance changes detected
      </div>
      <div class="bcp-error" v-else>
        <span>&#9888;</span> {{ store.balanceError }}
      </div>
    </div>

    <!-- 加载中 -->
    <div v-else-if="isLoading" :class="['bcp-body', { 'bcp-collapsed': !expanded }]">
      <div class="bcp-loading">
        <span class="bp-spin">&#8635;</span> Computing balance changes...
      </div>
    </div>

    <!-- 表格 -->
    <div v-else :class="['bcp-body', { 'bcp-collapsed': !expanded }]">
      <!-- 表头 -->
      <div class="bcp-table-hdr">
        <span class="col-addr">Addresses</span>
        <span class="col-token">Token</span>
        <span class="col-id">TokenID</span>
        <span class="col-bal">Balance</span>
        <span class="col-usd">Value in USD</span>
        <span class="col-total">Total Value in USD</span>
      </div>

      <!-- 按地址分组 -->
      <div v-for="(group, addr) in groupedData" :key="addr" class="bcp-addr-group">
        <div
          v-for="(row, ri) in group.rows"
          :key="ri"
          class="bcp-row"
          :class="{ 'row-first': ri === 0 }"
        >
          <!-- 地址列 (始终占位, 仅第一行显示内容) -->
          <span class="col-addr bcp-addr-cell" :class="{ 'bcp-addr-empty': ri !== 0 }">
            <template v-if="ri === 0">
              <span
                class="bcp-addr-label"
                :title="group.labelFull"
                @mouseenter="showTooltip($event, group.labelFull)"
                @mouseleave="hideTooltip"
                @click.stop="copyToClipboard(addr)"
              >{{ group.label }}</span>
              <span v-if="isSender(addr)" class="bcp-tag-sender">[Sender]</span>
              <span
                class="bcp-addr-hex"
                :title="addr"
                @mouseenter="showTooltip($event, addr)"
                @mouseleave="hideTooltip"
                @click.stop="copyToClipboard(addr)"
              >{{ shortAddr(addr) }}</span>
            </template>
          </span>

          <!-- Token -->
          <span class="col-token">
            <img v-if="row.logoUrl" :src="row.logoUrl" class="bcp-tok-img" @error="e => e.target.style.display='none'" />
            <span v-else class="bcp-tok-icon" :style="{ background: tokenColor(row.tokenSymbol) }"></span>
            {{ row.tokenSymbol }}
          </span>

          <!-- TokenID — 悬浮显示完整地址 + 复制 -->
          <span
            class="col-id"
            :title="row.tokenAddress || '-'"
            @mouseenter="showTooltip($event, row.tokenAddress || '-')"
            @mouseleave="hideTooltip"
            @click.stop="copyToClipboard(row.tokenAddress || '')"
          >
            {{ row.tokenAddress ? shortAddr(row.tokenAddress) : '-' }}
            <span class="bcp-copy-hint">&#8464;</span>
          </span>

          <!-- Balance -->
          <span :class="['col-bal', row.amountRaw >= 0 ? 'bal-pos' : 'bal-neg']">
            {{ signedAmount(row.amountFormatted) }}
          </span>

          <!-- Value USD -->
          <span :class="['col-usd', row.amountRaw >= 0 ? 'bal-pos' : 'bal-neg']">
            {{ formatUSD(row.valueUsd) }}
            <span v-if="row.priceUsd" class="bcp-price-hint" :title="`1 ${row.tokenSymbol} ≈ $${row.priceUsd}`">@${{ formatPrice(row.priceUsd) }}</span>
          </span>

          <!-- Total USD (始终占位, 仅第一行显示内容) -->
          <span class="col-total" :class="[ri === 0 ? (group.totalUsd >= 0 ? 'total-pos' : 'total-neg') : '']">
            {{ ri === 0 ? group.totalUsdFormatted : '' }}
          </span>
        </div>
      </div>
    </div>

    <!-- 悬浮 Tooltip -->
    <Teleport to="body">
      <div v-if="tooltip.visible" class="bcp-tooltip" :style="tooltip.style">
        <span class="bcp-tt-text">{{ tooltip.text }}</span>
        <span class="bcp-tt-copy" @click="copyToClipboard(tooltip.text)" title="Copy">&#8464;</span>
      </div>
    </Teleport>

    <!-- Copy 成功提示 -->
    <Transition name="fade">
      <div v-if="copyNotice" class="bcp-copy-notice">Copied!</div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useTraceStore } from '@/stores/traceAnalysis.js'

const props = defineProps({
  changes: { type: Array, default: () => [] },
})

// 支持独立加载模式：未传入 changes 时，从 store 获取数据
const store = useTraceStore()
const effectiveChanges = computed(() => {
  if (props.changes && props.changes.length > 0) return props.changes
  return store.balanceChanges
})
const isLoading = computed(() => props.changes ? false : store.isBalanceLoading)
const hasError = computed(() => props.changes ? false : !!store.balanceError)

const expanded = ref(true)
const copyNotice = ref(false)

// ── Tooltip 状态 ──
const tooltip = reactive({
  visible: false,
  text: '',
  style: { left: '0px', top: '0px' },
})

function showTooltip(event, text) {
  if (!text || text === '-' || text.length <= 16) return
  const rect = event.target.getBoundingClientRect()
  tooltip.text = text
  tooltip.visible = true
  tooltip.style = {
    left: `${Math.min(rect.left, window.innerWidth - 320)}px`,
    top: `${rect.bottom + 6}px`,
  }
}

function hideTooltip() {
  tooltip.visible = false
}

async function copyToClipboard(text) {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    copyNotice.value = true
    setTimeout(() => { copyNotice.value = false }, 1200)
  } catch {
    // fallback
    const ta = document.createElement('textarea')
    ta.value = text; ta.style.position = 'fixed'; document.body.appendChild(ta)
    ta.select(); document.execCommand('copy'); document.body.removeChild(ta)
    copyNotice.value = true
    setTimeout(() => { copyNotice.value = false }, 1200)
  }
}

// 按地址分组
const groupedData = computed(() => {
  const changes = effectiveChanges.value
  const groups = {}
  for (let i = 0; i < changes.length; i++) {
    const c = changes[i]
    const addr = c.address?.toLowerCase() || ''
    if (!groups[addr]) {
      groups[addr] = { label: '', labelFull: '', rows: [], totalNet: 0, totalUsd: 0 }
    }
    groups[addr].rows.push(c)
    groups[addr].totalNet += (c.amountRaw || 0)
    groups[addr].totalUsd += (c.valueUsd || 0)
  }

  // 格式化每个组的地址标签
  const entries = Object.entries(groups)
  for (let i = 0; i < entries.length; i++) {
    const addr = entries[i][0]
    const g = entries[i][1]
    // 找第一个有 label 的行作为标签
    const firstLabel = g.rows[0]?.addressLabel || ''
    if (firstLabel && firstLabel !== short_addr(addr)) {
      g.label = firstLabel
      g.labelFull = `${firstLabel} (${addr})`
    } else {
      g.label = short_addr(addr)
      g.labelFull = addr
    }

    // 格式化 Total USD — 汇总所有 token 的 USD 估值
    let usdStr = '-'
    if (g.totalUsd !== 0) {
      const prefix = g.totalUsd >= 0 ? '+' : '-'
      usdStr = `${prefix}$${Math.abs(g.totalUsd).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
    }
    g.totalUsdFormatted = usdStr
  }

  return groups
})

const totalEntries = computed(() => effectiveChanges.value.length)

function isSender(addr) { return false }

function signedAmount(fmt) {
  if (!fmt) return '0'
  const s = String(fmt)
  return s.startsWith('+') || s.startsWith('-') ? s : `+${s}`
}

function formatUSD(v) {
  if (v == null || v === 0) return '-'
  const prefix = v >= 0 ? '$' : '-$'
  return `${prefix}${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

function formatPrice(v) {
  if (v == null) return '-'
  if (v >= 1) return v.toLocaleString(undefined, { maximumFractionDigits: 2 })
  if (v >= 0.001) return v.toFixed(4)
  return v.toExponential(2)
}

function short_addr(a) {
  if (!a || a === '-') return a
  if (!a.startsWith('0x')) return a.slice(0, 12)
  return a.slice(0, 10) + '\u2026' + a.slice(-4)
}

function shortAddr(a) { return short_addr(a) }

const TOKEN_COLORS = {
  ETH: '#627EEA',
  WETH: '#627EEA',
  USDT: '#26A17B',
  USDC: '#2775CA',
  DAI: '#F5AC37',
  BNB: '#F3BA2F',
  WBTC: '#F7931A',
}

function tokenColor(sym) {
  return TOKEN_COLORS[sym] || '#4B5563'
}

function downloadCSV() {
  const changes = effectiveChanges.value
  if (!changes.length) return
  const headers = ['Address','Label','Token','Token ID','Balance Raw','Balance Formatted','Value USD','Price USD','Logo URL']
  const rows = changes.map(c => [
    c.address,
    c.addressLabel,
    c.tokenSymbol,
    c.tokenAddress || '-',
    c.amountRaw,
    c.amountFormatted,
    c.valueUsd ?? '',
    c.priceUsd ?? '',
    c.logoUrl ?? '',
  ])
  const csv = [headers.join(','), ...rows.map(r => r.map(v => `"${v}"`).join(','))].join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = 'balance_changes.csv'; a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.bcp { background: #161b22; border: 1px solid #21262d; border-radius: 8px; overflow: hidden; position: relative; }

/* ── Header ── */
.bcp-hdr {
  display: flex; align-items: center; gap: 7px;
  padding: 9px 14px; cursor: pointer;
  user-select: none; transition: background .12s;
  border-bottom: 1px solid #21262d;
}
.bcp-hdr:hover { background: rgba(255,255,255,.03); }
.bcp-icon { font-size: 14px; }
.bcp-title {
  font-size: 13px; font-weight: 700; color: #e6edf3;
  letter-spacing: .2px; flex: 1;
}
.bcp-count {
  font-size: 10px; font-weight: 600; color: #484f58;
  background: #0d1117; padding: 1px 7px; border-radius: 8px;
}
.bcp-toggle { color: #6b7280; font-size: 11px; transition: transform .15s; }
.bcp-dl-btn {
  background: none; border: 1px solid transparent; color: #484f58;
  cursor: pointer; font-size: 14px; padding: 2px 5px; border-radius: 4px;
  transition: all .12s;
}
.bcp-dl-btn:hover { border-color: #30363d; color: #8b949e; }

/* ── Body ── */
.bcp-body {
  max-height: 480px; overflow-y: auto;
  transition: max-height .25s ease;
}
.bcp-collapsed { max-height: 0; overflow: hidden; }

/* Empty state */
.bcp-empty {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  padding: 20px 8px; color: #484f58; font-size: 11.5px;
}

/* Loading */
.bcp-loading {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  padding: 20px 8px; color: #8b949e; font-size: 11.5px;
}
.bp-spin { animation: spin 1s linear infinite; display: inline-block; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Error */
.bcp-error {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  padding: 14px 8px; color: #f85149; font-size: 11.5px;
}

/* ── Table Header ── */
.bcp-table-hdr {
  display: flex; align-items: center; gap: 4px;
  padding: 6px 12px; background: rgba(22,27,34,.95);
  border-bottom: 1px solid #21262d;
  position: sticky; top: 0; z-index: 2;
}
.bcp-table-hdr > span {
  font-size: 10px; font-weight: 700; color: #6e7681;
  text-transform: uppercase; letter-spacing: .5px;
}

/* Column widths */
.col-addr   { width: 24%; min-width: 180px; }
.col-token  { width: 11%; min-width: 80px; }
.col-id     { width: 19%; min-width: 140px; }
.col-bal    { width: 18%; min-width: 130px; text-align: right; }
.col-usd    { width: 13%; min-width: 95px; text-align: right; }
.col-total  { width: 15%; min-width: 110px; text-align: right; }

/* ── Rows ── */
.bcp-addr-group { border-bottom: 1px solid rgba(33,38,45,.35); }
.bcp-row {
  display: flex; align-items: center; gap: 4px;
  padding: 5px 12px; transition: background .08s;
  font-family: 'JetBrains Mono', 'SF Mono', 'Cascadia Code', monospace;
  font-size: 11.5px;
}
.bcp-row:hover { background: rgba(255,255,255,.02); }
.bcp-row.row-first { padding-top: 7px; }

/* Address cell */
.bcp-addr-cell {
  display: flex; flex-direction: column; gap: 1px; align-items: flex-start;
  line-height: 1.4;
}
.bcp-addr-cell.bcp-addr-empty { visibility: hidden; pointer-events: none; }
.bcp-addr-label {
  font-weight: 700; color: #a78bfa; font-size: 11.5px;
  cursor: pointer; transition: color .12s; position: relative;
}
.bcp-addr-label:hover { color: #c084fc; text-decoration: underline; }
.bcp-addr-hex { color: #484f58; font-size: 9.5px; cursor: help; transition: color .12s; }
.bcp-addr-hex:hover { color: #8b949e; }
.bcp-tag-sender {
  font-size: 8px; font-weight: 700; color: #fbbf24;
  background: rgba(251,179,36,.1); padding: 0 4px; border-radius: 2px;
  margin-left: 4px;
}

/* Token cell */
.col-token { display: flex; align-items: center; gap: 5px; color: #c9d1d9; font-weight: 500; white-space: nowrap; }
.bcp-tok-icon {
  width: 15px; height: 15px; border-radius: 50%; flex-shrink: 0;
  display: inline-block;
}
.bcp-tok-img {
  width: 15px; height: 15px; border-radius: 50%; flex-shrink: 0;
  display: inline-block; object-fit: cover;
}

/* Token ID — 可点击复制 */
.col-id {
  cursor: pointer; transition: color .12s;
  display: inline-flex; align-items: center; gap: 3px;
}
.col-id:hover { color: #58a6ff; }
.bcp-copy-hint { font-size: 10px; color: #30363d; opacity: 0; transition: opacity .12s; }
.col-id:hover .bcp-copy-hint { opacity: 1; }

/* Balance / USD */
.bal-neg { color: #f85149; }
.bal-pos { color: #3fb950; }
.col-bal, .col-usd { text-align: right; font-weight: 600; }
.bcp-price-hint {
  font-size: 9px; color: #484f58; font-weight: 400; margin-left: 3px;
  cursor: help;
}

/* Total */
.total-neg { color: #f85149; font-weight: 700; background: rgba(248,81,73,.06);
  padding: 1px 6px; border-radius: 3px; }
.total-pos { color: #3fb950; font-weight: 700; background: rgba(63,185,80,.06);
  padding: 1px 6px; border-radius: 3px; }

/* Scrollbar */
.bcp-body::-webkit-scrollbar { width: 5px; }
.bcp-body::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }

/* ── Floating Tooltip ── */
.bcp-tooltip {
  position: fixed; z-index: 9999;
  display: flex; align-items: center; gap: 6px;
  padding: 5px 10px; border-radius: 5px;
  background: #1e2329; border: 1px solid #3d4450;
  box-shadow: 0 4px 16px rgba(0,0,0,.4);
  font-family: 'JetBrains Mono', monospace; font-size: 11px;
  color: #c9d1d9; pointer-events: auto;
  animation: ttIn .12s ease;
}
@keyframes ttIn { from { opacity: 0; transform: translateY(3px); } }
.bcp-tt-text { max-width: 280px; word-break: break-all; line-height: 1.4; }
.bcp-tt-copy {
  cursor: pointer; color: #58a6ff; font-size: 12px; flex-shrink: 0;
  padding: 1px 3px; border-radius: 3px; transition: background .1s;
}
.bcp-tt-copy:hover { background: rgba(88,166,255,.12); }

/* ── Copy Notice ── */
.fade-enter-active, .fade-leave-active { transition: opacity .25s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
.bcp-copy-notice {
  position: fixed; bottom: 20px; right: 20px; z-index: 10000;
  padding: 6px 16px; border-radius: 6px;
  background: #238636; color: white;
  font-size: 12px; font-weight: 600;
  box-shadow: 0 3px 12px rgba(35,134,54,.3);
  animation: cnPop .2s ease;
}
@keyframes cnPop { from { opacity: 0; transform: translateY(8px); } }
</style>
