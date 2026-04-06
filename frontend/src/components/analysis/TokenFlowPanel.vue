<template>
  <div class="tfp">
    <!-- 标题 -->
    <h3 class="tfp-title">
      <span class="tfp-icon">&#128176;</span> Token Flows
    </h3>

    <div v-if="!flows.length" class="tfp-empty">
      <span class="tfp-empty-ic">&#128270;</span> No token transfers detected
    </div>

    <template v-else>
      <!-- 汇总栏 -->
      <div class="tfp-summary">
        <div class="tfp-sum-item tsi-in">
          <span class="tsi-label">IN</span>
          <span class="tsi-val">{{ inTotalFormatted }}</span>
        </div>
        <div class="tfp-divider"></div>
        <div class="tfp-sum-item tsi-out">
          <span class="tsi-label">OUT</span>
          <span class="tsi-val">{{ outTotalFormatted }}</span>
        </div>
        <div class="tfp-divider"></div>
        <div class="tfp-tokens-count">{{ uniqueTokens }} token(s)</div>
      </div>

      <!-- 流列表 — 按 token 分组 -->
      <div v-for="(group, token) in groupedFlows" :key="token" class="tfp-group">
        <div class="tfp-group-hdr">
          <span class="tfp-group-sym">{{ token }}</span>
          <span class="tfp-group-addr">{{ group.address }}</span>
        </div>
        <div class="tfp-flow-list">
          <div
            v-for="(f, i) in group.items"
            :key="i"
            class="tfp-row"
            :class="{ 'row-in': f.direction === 'in', 'row-out': f.direction === 'out' }"
          >
            <!-- 方向箭头 -->
            <span class="tfp-arrow" :class="f.direction">
              {{ f.direction === 'in' ? '&#8594;' : '&#8592;' }}
            </span>

            <!-- 地址/标签 -->
            <div class="tfp-party">
              <span class="tfp-p-label">{{ f.partyLabel }}</span>
              <span class="tfp-p-addr" :title="f.partyAddr">{{ shortAddr(f.partyAddr) }}</span>
            </div>

            <!-- 金额 -->
            <div class="tfp-amount-wrap">
              <span class="tfp-amount">{{ formatAmount(f.amountFormatted || f.amountRaw) }}</span>
              <span v-if="f.amountUsd" class="tfp-usd">≈ ${{ f.amountUsd }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ flows: { type: Array, default: () => [] } })

// 按 tokenSymbol 分组
const groupedFlows = computed(() => {
  const groups = {}
  for (const f of props.flows) {
    const sym = f.tokenSymbol || 'UNKNOWN'
    if (!groups[sym]) {
      groups[sym] = {
        address: f.tokenAddress || '',
        items: [],
      }
    }
    groups[sym].items.push({
      ...f,
      partyLabel: f.direction === 'in'
        ? (f.toLabel || 'Receiver')
        : (f.fromLabel || 'Sender'),
      partyAddr: f.direction === 'in' ? (f.to || f.tokenAddress) : (f.from || f.tokenAddress),
    })
  }
  return groups
})

// 统计
const uniqueTokens = computed(() => Object.keys(groupedFlows.value).length)

const inTotal = computed(() => {
  let sum = 0
  for (const g of Object.values(groupedFlows.value)) {
    for (const item of g.items.filter(x => x.direction === 'in')) {
      const n = parseFloat(item.amountRaw || item.amountFormatted || 0)
      if (!isNaN(n)) sum += n
    }
  }
  return sum
})
const outTotal = computed(() => {
  let sum = 0
  for (const g of Object.values(groupedFlows.value)) {
    for (const item of g.items.filter(x => x.direction === 'out')) {
      const n = parseFloat(item.amountRaw || item.amountFormatted || 0)
      if (!isNaN(n)) sum += n
    }
  }
  return sum
})

function fmtLarge(n) {
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`
  if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`
  if (n >= 1e3) return `${(n / 1e3).toFixed(2)}K`
  return n.toFixed(2)
}
const inTotalFormatted = computed(() => fmtLarge(inTotal.value))
const outTotalFormatted = computed(() => fmtLarge(outTotal.value))

function shortAddr(a) {
  if (!a) return '-'
  if (!a.startsWith('0x')) return String(a).slice(0, 10)
  return a.slice(0, 8) + '\u2026' + a.slice(-4)
}
function formatAmount(v) {
  if (!v) return '0'
  const s = String(v)
  const n = parseFloat(s.replace(/,/g, ''))
  if (isNaN(n)) return s
  // 大数字格式化
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(2)}M`
  if (Math.abs(n) >= 1e3) return `${(n / 1e3).toFixed(2)}K`
  // 小数字保留合理精度
  if (Math.abs(n) < 0.01 && n !== 0) return `<${0.001}`
  if (Math.abs(n) < 1) return n.toFixed(4)
  return Number(n.toFixed(4)).toLocaleString()
}
</script>

<style scoped>
.tfp { display: flex; flex-direction: column; gap: 7px; }

/* Title */
.tfp-title {
  margin: 0; font-size: 12px; font-weight: 700; color: #e6edf3;
  display: flex; align-items: center;
}
.tfp-icon { margin-right: 5px; }

/* Empty */
.tfp-empty {
  text-align: center; padding: 16px 8px; color: #484f58;
  font-size: 11.5px; display: flex; align-items: center; justify-content: center; gap: 5px;
}
.tfp-empty-ic { opacity: .5; }

/* ── Summary bar ── */
.tfp-summary {
  display: flex; align-items: center; gap: 6px;
  padding: 7px 10px; background: #0d1117; border: 1px solid #21262d; border-radius: 6px;
}
.tfp-sum-item { display: flex; align-items: baseline; gap: 4px; }
.tsu-label, .tsi-label {
  font-size: 9px; font-weight: 800; letter-spacing: .6px; padding: 1px 5px;
  border-radius: 2px;
}
.tsi-in .tsi-label { background: rgba(63,185,80,.14); color: #3fb950; }
.tsi-out .tsi-label { background: rgba(248,81,73,.13); color: #f85149; }
.tsi-val { font-family: 'JetBrains Mono', monospace; font-size: 11.5px; font-weight: 700; }
.tsi-in .tsi-val { color: #3fb950; }
.tsi-out .tsi-val { color: #f85149; }
.tfp-divider { width: 1px; height: 18px; background: #21262d; flex-shrink: 0; }
.tfp-tokens-count { margin-left: auto; font-size: 10px; color: #484f58; }

/* ── Token Groups ── */
.tfp-group { border: 1px solid #21262d; border-radius: 6px; overflow: hidden; background: #161b22; }
.tfp-group-hdr {
  display: flex; justify-content: space-between; align-items: center;
  padding: 5px 9px; background: rgba(22,27,34,.95); border-bottom: 1px solid #21262d;
}
.tfp-group-sym {
  font-size: 11.5px; font-weight: 700; color: #a379ff;
  font-family: 'JetBrains Mono', monospace;
}
.tfp-group-addr {
  font-size: 9.5px; color: #484f58; font-family: 'JetBrains Mono', monospace;
}

/* ── Individual flow rows ── */
.tfp-flow-list { display: flex; flex-direction: column; }

.tfp-row {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 9px; transition: background .08s;
  border-bottom: 1px solid rgba(33,38,45,.4);
}
.tfp-row:last-child { border-bottom: none; }
.tfp-row:hover { background: rgba(255,255,255,.03); }

/* Direction arrow */
.tfp-arrow {
  font-size: 11px; width: 16px; text-align: center; flex-shrink: 0;
  line-height: 20px; border-radius: 3px; font-weight: bold;
}
.row-in .tfp-arrow { color: #3fb950; background: rgba(63,185,80,.1); }
.row-out .tfp-arrow { color: #f85149; background: rgba(248,81,73,.1); }

/* Party info */
.tfp-party { display: flex; flex-direction: column; min-width: 0; flex: 1; }
.tfp-p-label { font-size: 10px; color: #8b949e; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tfp-p-addr {
  font-size: 9.5px; color: #484f58; font-family: 'JetBrains Mono', monospace;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* Amount */
.tfp-amount-wrap { display: flex; flex-direction: column; align-items: flex-end; flex-shrink: 0; margin-left: auto; }
.tfp-amount {
  font-family: 'JetBrains Mono', monospace; font-size: 11.5px; font-weight: 700; color: #e6edf3;
  white-space: nowrap;
}
.row-in .tfp-amount { color: #56d364; }
.row-out .tfp-amount { color: #ff7b72; }
.tfp-usd {
  font-size: 9px; color: #6e7681; font-family: 'JetBrains Mono', monospace;
  white-space: nowrap;
}
</style>
