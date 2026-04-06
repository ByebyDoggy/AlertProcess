<template>
  <div class="bp">
    <h3 class="bp-title">
      <span class="bp-icon">&#9888;</span> Behavior Detection
    </h3>

    <!-- 无检测到 -->
    <div v-if="!behaviors.length && !isLoading" class="bp-empty">
      <span class="bp-ok">&#10003;</span>
      No suspicious patterns detected
    </div>

    <!-- 加载中 -->
    <div v-else-if="isLoading" class="bp-loading">
      <span class="bp-spin">&#8635;</span> Scanning behaviors...
    </div>

    <!-- 行为列表 -->
    <template v-else>
      <div
        v-for="(b, i) in behaviors"
        :key="i"
        class="bp-card"
        :class="'risk-' + (b.riskLevel || 'info')"
      >
        <!-- Header: label + risk badge -->
        <div class="bp-hdr">
          <div class="bp-hdr-left">
            <span class="bp-icon-risk" :class="b.riskLevel">{{ riskIcon(b.riskLevel) }}</span>
            <span class="bp-label">{{ b.label }}</span>
          </div>
          <span class="bp-badge" :class="b.riskLevel">{{ (b.riskLevel || 'INFO').toUpperCase() }}</span>
        </div>

        <!-- Description -->
        <p class="bp-desc">{{ b.description }}</p>

        <!-- Confidence bar -->
        <div class="bp-conf">
          <span>Confidence</span>
          <div class="bp-bar-wrap">
            <div class="bp-bar-fill" :class="b.riskLevel" :style="{width:(b.confidence*100)+'%'}"></div>
          </div>
          <span class="bp-conf-pct">{{ Math.round((b.confidence||0)*100) }}%</span>
        </div>

        <!-- Details (collapsible) -->
        <details v-if="b.details && Object.keys(b.details).length" class="bp-details">
          <summary>View details</summary>
          <pre>{{ formatDetails(b.details) }}</pre>
        </details>

        <!-- Involved addresses -->
        <div v-if="b.involvedAddresses?.length" class="bp-addrs">
          <span class="bp-addr-label">Addresses:</span>
          <span v-for="addr in b.involvedAddresses.slice(0,6)" :key="addr" class="bp-addr">{{ short(addr) }}</span>
          <span v-if="b.involvedAddresses.length > 6" class="bp-addr-more">+{{ b.involvedAddresses.length - 6 }} more</span>
        </div>
      </div>
    </template>

    <!-- 签名库统计 -->
    <div v-if="sigCount !== null" class="bp-stats">
      <span class="bp-stats-label">Signature DB</span>
      <span class="bp-stats-num">{{ sigCount.toLocaleString() }}</span>
      <span class="bp-stats-unit">signatures</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useTraceStore } from '@/stores/traceAnalysis.js'
import { getSignatureStats } from '@/api/trace.js'

defineProps({ isLoading: { type: Boolean, default: false } })
const store = useTraceStore()
const behaviors = computed(() => store.behaviors)
const sigCount = ref(null)

onMounted(async () => {
  try {
    const s = await getSignatureStats()
    sigCount.value = s?.total_signatures || 0
  } catch {}
})

function short(a) {
  if (!a || !a.startsWith('0x')) return a || '?'
  return a.slice(0, 8) + '\u2026' + a.slice(-4)
}
function riskIcon(level) {
  const icons = { info: '&#8505;', low: '&#9745;', medium: '&#9888;', high: '&#9760;', critical: '&#9888;' }
  return icons[level] || icons.info
}
function formatDetails(d) {
  // 简化 JSON 显示，截断长值
  if (!d) return ''
  const simplify = (obj, depth = 0) => {
    if (depth > 2 || typeof obj !== 'object' || obj === null) return String(obj).slice(0, 80)
    const entries = Object.entries(obj).slice(0, 12).map(([k, v]) => {
      let sv = typeof v === 'string' ? v.slice(0, 60) : JSON.stringify(v)?.slice(0, 60)
      return `  ${k}: ${sv}`
    })
    return '{\n' + entries.join('\n') + '\n}'
  }
  return simplify(d)
}
</script>

<style scoped>
.bp { display: flex; flex-direction: column; gap: 8px; }

/* Title */
.bp-title {
  margin: 0; font-size: 12.5px; font-weight: 700; color: #e6edf3;
  display: flex; align-items: center;
}
.bp-icon { color: #d29922; margin-right: 4px; }

/* Empty state */
.bp-empty {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  padding: 14px 8px; color: #3fb950; font-size: 11.5px;
  background: rgba(63,185,80,.04); border: 1px solid rgba(63,185,80,.1); border-radius: 6px;
}
.bp-ok { font-weight: bold; }

/* Loading */
.bp-loading {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  padding: 14px 8px; color: #8b949e; font-size: 11.5px;
}
.bp-spin { animation: spin 1s linear infinite; display: inline-block; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Card */
.bp-card {
  background: #161b22; border: 1px solid #21262d; border-radius: 7px; padding: 10px 12px;
  transition: border-color .15s, box-shadow .15s;
}
.bp-card:hover { border-color: #30363d; }
.bp-card.risk-critical { border-left: 3px solid #f85149; }
.bp-card.risk-high { border-left: 3px solid #ff7b72; }
.bp-card.risk-medium { border-left: 3px solid #d29922; }
.bp-card.risk-low { border-left: 3px solid #3fb950; }
.bp-card.risk-info { border-left: 3px solid #58a6ff; }

/* Card header */
.bp-hdr { display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px; }
.bp-hdr-left { display: flex; align-items: center; gap: 5px; }

.bp-icon-risk {
  font-size: 13px; line-height: 18px; width: 20px; text-align: center;
}
.bp-icon-risk.critical { color: #f85149; }
.bp-icon-risk.high { color: #ff7b72; }
.bp-icon-risk.medium { color: #d29922; }
.bp-icon-risk.low { color: #3fb950; }
.bp-icon-risk.info { color: #58a6ff; }

.bp-label { font-weight: 600; font-size: 12px; color: #e6edf3; }

/* Badge */
.bp-badge {
  font-size: 8.5px; font-weight: 800; letter-spacing: .6px;
  padding: 2px 7px; border-radius: 3px; text-transform: uppercase;
}
.bp-badge.critical { background: rgba(248,81,73,.15); color: #f85149; }
.bp-badge.high { background: rgba(255,123,114,.13); color: #ff7b72; }
.bp-badge.medium { background: rgba(210,153,34,.14); color: #d29922; }
.bp-badge.low { background: rgba(63,185,80,.14); color: #3fb950; }
.bp-badge.info { background: rgba(88,166,255,.12); color: #79c0ff; }

/* Description */
.bp-desc { font-size: 11px; color: #8b949e; line-height: 1.5; margin: 0 0 7px; }

/* Confidence bar */
.bp-conf { display: flex; align-items: center; gap: 7px; margin-bottom: 6px; }
.bp-conf > span:first-child { font-size: 10px; color: #6e7681; min-width: 60px; }
.bp-conf-pct { font-size: 10px; color: #6e7681; min-width: 30px; text-align: right; font-family: 'JetBrains Mono', monospace; font-weight: 600; }
.bp-bar-wrap { flex: 1; height: 4px; background: #0d1117; border-radius: 2px; overflow: hidden; }
.bp-bar-fill { height: 100%; border-radius: 2px; transition: width .35s ease-out; }
.bp-bar-fill.critical { background: linear-gradient(90deg, #da3633, #f85149); }
.bp-bar-fill.high { background: linear-gradient(90deg, #c93d36, #ff7b72); }
.bp-bar-fill.medium { background: linear-gradient(90deg, #9e6a03, #d29922); }
.bp-bar-fill.low { background: linear-gradient(90deg, #238636, #3fb950); }
.bp-bar-fill.info { background: linear-gradient(90deg, #1f6feb, #58a6ff); }

/* Collapsible details */
.bp-details summary {
  cursor: pointer; font-size: 10px; color: #6e7681; user-select: none;
  padding: 2px 0; outline: none;
}
.bp-details summary:hover { color: #8b949e; }
.bp-details pre {
  font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #8b949e;
  margin: 5px 0 0; max-height: 120px; overflow-y: auto; white-space: pre-wrap;
  word-break: break-all; background: #0d1117; padding: 7px 9px; border-radius: 4px;
}

/* Addresses */
.bp-addrs { display: flex; flex-wrap: wrap; align-items: center; gap: 3px; margin-top: 5px; }
.bp-addr-label { font-size: 9.5px; color: #484f58; margin-right: 3px; font-weight: 500; }
.bp-addr {
  font-size: 9.5px; font-family: 'JetBrains Mono', monospace;
  background: #0d1117; color: #79c0ff; padding: 1px 5px; border-radius: 3px;
  border: 1px solid #21262d;
}
.bp-addr-more { font-size: 9px; color: #484f58; }

/* Stats footer */
.bp-stats {
  display: flex; align-items: center; justify-content: center; gap: 5px;
  padding: 6px 0; font-size: 10.5px; color: #484f58; border-top: 1px solid #161b22;
  margin-top: 2px;
}
.bp-stats-label { color: #484f58; }
.bp-stats-num { color: #8b949e; font-weight: 700; font-family: 'JetBrains Mono', monospace; }
.bp-stats-unit { color: #484f58; }
</style>
