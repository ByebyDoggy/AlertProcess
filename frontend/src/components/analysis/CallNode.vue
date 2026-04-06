<template>
  <div class="cn" :data-depth="node.depth">
    <!-- 主行 — 紧凑模式 -->
    <div class="cn-row" :class="rowClass" @click.stop="handleSelect">
      <!-- 展开/折叠按钮 -->
      <button v-if="hasChildren" class="cn-toggle" :class="{ expanded }"
        :title="expanded ? 'Collapse' : 'Expand'" @click.stop="store.toggleNode(nodeKey)">
        {{ expanded ? '&#9660;' : '&#9654;' }}
      </button>
      <span v-else class="cn-spacer"></span>

      <!-- 深度指示器 -->
      <span class="cn-depth">{{ node.depth }}</span>

      <!-- 类型 badge -->
      <span class="cn-type" :class="node.callType">{{ typeLabel }}</span>

      <!-- To 地址 / 标签 -->
      <span class="cn-to">
        <template v-if="node.label"><span class="cn-label">{{ node.label }}</span></template>
        <template v-else-if="node.tokenSymbol"><span class="cn-token">{{ node.tokenSymbol }}</span></template>
        <template v-else><span class="cn-addr">{{ shortAddr(node.toAddress) }}</span></template>
      </span>

      <!-- 函数签名 + 参数（截断显示） -->
      <span v-if="hasFnInfo" class="cn-fn">
        <SignatureTag :selector="node.selector" :functionSig="node.functionSig" />
        <span v-if="paramsDisplay" class="cn-params">({{ paramsDisplay }})</span>
      </span>
      <span v-else-if="showInputHex" class="cn-fn cn-hex">{{ shortInput }}</span>

      <!-- Value -->
      <span v-if="valueDisplay" class="cn-val">value= {{ valueDisplay }}</span>

      <!-- Output 状态 -->
      <span v-if="node.error" class="cn-revert">&#9888; {{ truncateErr }}</span>
      <template v-else-if="hasOutput">
        <span class="cn-out-label">(</span>
        <span class="cn-out-data" :title="fullOutput">{{ outputShort }}</span>
        <span class="cn-out-label">)</span>
      </template>
      <span v-else class="cn-out-empty">()</span>

      <!-- Raw data 按钮 -->
      <button class="cn-raw-btn" title="Show raw data" @click.stop="toggleDetail"
        :class="{ active: detailVisible }">&#9776;</button>
    </div>

    <!-- 详情面板（点击展开/折叠，仿 BlockSec） -->
    <div v-if="detailVisible" class="cn-detail" @click.stop>
      <div class="cn-detail-row" v-for="(field, fi) in detailFields" :key="fi">
        <span class="cn-dk">{{ field.k }}:</span>
        <span class="cn-dv" :class="field.cls">{{ field.v }}</span>
      </div>
    </div>

    <!-- 子节点 -->
    <div v-if="hasChildren && expanded" class="cn-children">
      <CallNode
        v-for="(child, ci) in visibleChildren"
        :key="makeKey(child)"
        :node="child"
        :is-selected="store.selectedNodeId === makeKey(child)"
        @select="store.selectNode(makeKey(child))"
      />
      <div v-if="truncatedCount > 0" class="cn-truncate">... {{ truncatedCount }} more hidden</div>
    </div>

    <!-- Events -->
    <div v-for="(ev, ei) in node.events" :key="'ev-' + ei" class="cn-event">
      <span class="cn-ev-sp"></span>
      <span class="cn-ev-tag">EVENT</span>
      <span class="cn-ev-contract">{{ evContract(ev) }}</span>
      <span class="cn-ev-name">{{ ev.name }}</span>
      <span v-if="hasEvDetail(ev)" class="cn-ev-det">, {{ evDetailShort(ev) }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useTraceStore } from '@/stores/traceAnalysis.js'
import SignatureTag from './SignatureTag.vue'

const props = defineProps({
  node: { type: Object, required: true },
  isSelected: { type: Boolean, default: false },
})
defineEmits(['select'])
const store = useTraceStore()

const detailVisible = ref(false)

const nodeKey = computed(() => `${props.node.depth}-${(props.node.traceAddress||[]).join('-')}-${props.node.to}`)
const expanded = computed(() => store.isExpanded(nodeKey.value))
const hasChildren = computed(() => props.node.children && props.node.children.length > 0)
const MAX_CHILDREN = 300
const visibleChildren = computed(() => (props.node.children||[]).slice(0, MAX_CHILDREN))
const truncatedCount = computed(() => (props.node.children||[]).length - MAX_CHILDREN)

// ---- type ----
const typeLabel = computed(() => ({
  call:'CALL', delegatecall:'DELEGATE', staticcall:'STATIC', create:'CREATE'
}[props.node.callType] || props.node.callType?.toUpperCase() || '?'))

const rowClass = computed(() => ({
  selected: props.isSelected,
  reverted: !!props.node.error,
  ['type-' + props.node.callType]: true,
}))

// ---- 显示内容 ----
const hasFnInfo = computed(() => props.node.functionSig || props.node.selector)
const showInputHex = computed(() => props.node.input && props.node.input !== '0x')

const paramsDisplay = computed(() => {
  const p = props.node.params || []
  if (!p.length) return ''
  // 截断参数：只显示前3个，总长度限制60字符
  const parts = p.slice(0, 4).map(param => {
    let v = param.value || ''
    if (param.type_hint === 'address' && v.startsWith('0x')) return `${param.name}=${shortAddr(v)}`
    if (/^\d{10,}$/.test(v)) return `${param.name}=${formatLargeNum(v)}`
    let sv = String(v).length > 20 ? v.slice(0, 17) + '\u2026' : v
    return `${param.name}=${sv}`
  })
  let s = parts.join(', ')
  if (p.length > 4) s += ', ...'
  return s.length > 70 ? s.slice(0, 67) + '\u2026' : s
})

const valueDisplay = computed(() => {
  const val = props.node.value
  if (!val || val === '0x0' || val === 0) return ''
  const n = typeof val === 'string' ? BigInt(val) : BigInt(val)
  if (n >= BigInt(1e18)) return `${(Number(n / BigInt(1e9)) / 1e9).toFixed(4)}`
  if (n >= BigInt(1e9)) return `${(Number(n / BigInt(1e6)) / 1e3).toFixed(2)} Gwei`
  return `${n} wei`
})

// ---- output ----
const hasOutput = computed(() => {
  const o = props.node.outputData || props.node.output
  return o && o !== '0x' && o !== '0x0' && o?.length > 10
})
const outputShort = computed(() => {
  const o = props.node.outputData || props.node.output || ''
  return o.length > 50 ? o.slice(0, 47) + '\u2026' : o
})
const fullOutput = computed(() => props.node.outputData || props.node.output || '')
const truncateErr = computed(() => {
  const e = String(props.node.error || '')
  return e.length > 40 ? e.slice(0, 37) + '\u2026' : e
})

const shortInput = computed(() => {
  const i = props.node.input || ''
  return i.length > 20 ? i.slice(0, 17) + '\u2026' : i
})

// ---- 详情字段（仿 BlockSec 展开）----
const detailFields = computed(() => {
  const n = props.node
  const fields = []

  // From / To
  if (n.fromAddress) fields.push({ k: 'from', v: n.fromAddress, cls: 'dv-addr' })
  if (n.toAddress) fields.push({ k: 'to', v: n.toAddress, cls: 'dv-addr' })
  if (n.label) fields.push({ k: '', v: `[${n.label}]`, cls: 'dv-label' })

  // 函数签名
  if (n.functionSig) fields.push({ k: 'function', v: n.functionSig, cls: 'dv-sig' })

  // 解码后的完整参数
  if (n.params && n.params.length) {
    const paramParts = n.params.map(p => {
      let pv = p.value || ''
      if (p.type_hint === 'address' && pv.startsWith('0x')) pv = shortAddr(pv)
      else if (/^\d{10,}$/.test(pv)) pv = formatLargeNum(pv)
      return { name: p.name, val: pv }
    })
    // 合并为一个字段显示所有参数
    fields.push({
      k: 'data',
      v: paramParts.map(p => `${p.name}= ${p.val}`).join(', '),
      cls: 'dv-data'
    })
  } else if (n.input && n.input !== '0x') {
    fields.push({ k: 'raw data', v: n.input, cls: 'dv-hex' })
  }

  // Value
  if (n.value && n.value !== '0x0') {
    const vn = typeof n.value === 'string' ? parseInt(n.value, 16) : Number(n.value)
    fields.push({ k: 'value', v: `${vn.toLocaleString()} wei (${(vn/1e18).toFixed(6)} ETH)`, cls: 'dv-value' })
  }

  // Gas
  if (n.gasUsed) {
    const g = typeof n.gasUsed === 'number' ? n.gasUsed : parseInt(String(n.gasUsed), 16)
    fields.push({ k: 'gas', v: g.toLocaleString(), cls: 'dv-gas' })
  }

  // Output
  if (hasOutput.value) {
    fields.push({ k: 'output', v: fullOutput.value, cls: 'dv-output' })
  }

  // Error
  if (n.error) {
    fields.push({ k: 'error', v: String(n.error), cls: 'dv-error' })
  }

  return fields
})

// ---- events ----
function evContract(ev) {
  const addr = ev.raw?.address || ''
  return addr ? shortAddr(addr) : ''
}
function hasEvDetail(ev) {
  const d = ev.decoded || {}
  return Object.keys(d).filter(k => !k.startsWith('_')).length > 0
}
function evDetailShort(ev) {
  const d = ev.decoded || {}
  const parts = Object.entries(d).filter(([k]) => !k.startsWith('_')).map(([k,v]) => `${k}=${v}`)
  const s = parts.join(', ')
  return s.length > 80 ? s.slice(0, 77) + '\u2026' : s
}

// ---- utils ----
function makeKey(nd) { return `${nd.depth}-${(nd.traceAddress||[]).join('-')}-${nd.to}` }
function handleSelect() {
  if (props.isSelected) {
    // 再次点击已选中的节点 → 折叠详情
    detailVisible.value = false
  } else {
    store.selectNode(nodeKey.value)
    detailVisible.value = true
  }
}
function toggleDetail() { detailVisible.value = !detailVisible.value }

function shortAddr(a) { if (!a) return '?'; return a.slice(0, 8) + '\u2026' + a.slice(-4) }

function formatGas(g) {
  if (!g) return '-'
  const n = typeof g === 'number' ? g : parseInt(String(g), 16)
  return Number(n).toLocaleString()
}
function formatLargeNum(s) {
  try {
    const n = BigInt(s)
    if (n >= BigInt(1e18)) return `${(Number(n / BigInt(1e9)) / 1e9).toFixed(4)}`
    if (n >= BigInt(1e9)) return `${(Number(n / BigInt(1e6)) / 1e3).toFixed(2)}K`
    return s.slice(0, 12) + '\u2026'
  } catch { return s.slice(0, 12) + '\u2026' }
}
</script>

<style scoped>
.cn { position: relative; user-select: none; }

/* ── 主行：紧凑模式 ── */
.cn-row {
  display: flex; align-items: center; gap: 5px;
  padding: 1px 8px 1px 4px;
  font-size: 12px; line-height: 21px;
  color: #c8d0dc; border-radius: 3px;
  white-space: nowrap; cursor: pointer;
  transition: background .08s;
  font-family: 'JetBrains Mono', 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
  overflow: hidden;
}
.cn-row:hover { background: rgba(99,102,241,.06); }
.cn-row.selected { background: rgba(99,102,241,.11); outline: 1px solid rgba(99,102,242,.25); outline-offset: -1px; }
.cn-row.reverted { background: rgba(239,68,68,.05); }

/* 折叠按钮 */
.cn-toggle {
  width: 14px; height: 14px; border: none; background: transparent;
  color: #6b7280; cursor: pointer; font-size: 8px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 2px; flex-shrink: 0; opacity: .7;
}
.cn-toggle:hover { color: #9ca3af; background: rgba(255,255,255,.06); }
.cn-spacer { width: 14px; flex-shrink: 0; }

/* 深度 */
.cn-depth { color: #4b5563; min-width: 22px; text-align: right; font-weight: 500; font-size: 11px; flex-shrink: 0; }

/* Type badge */
.cn-type {
  font-size: 9.5px; font-weight: 700; letter-spacing: .5px;
  padding: 0 5px; border-radius: 2px; flex-shrink: 0;
  min-width: 48px; text-align: center; line-height: 16px;
}
.cn-type.call { background: rgba(59,130,246,.13); color: #60a5fa; }
.cn-type.delegatecall { background: rgba(245,158,11,.14); color: #fbbf24; }
.cn-type.staticcall { background: rgba(20,184,166,.14); color: #2dd4bf; }
.cn-type.create { background: rgba(34,197,94,.14); color: #4ade80; }

/* To 地址 */
.cn-to { flex-shrink: 0; max-width: 140px; overflow: hidden; text-overflow: ellipsis; min-width: 40px; }
.cn-label { color: #a78bfa; font-weight: 600; }
.cn-token { color: #34d399; font-weight: 600; }
.cn-addr { color: #9ca3af; }

/* 函数签名+参数 */
.cn-fn { flex: 1; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.cn-params { color: #8692a0; margin-left: 1px; }
.cn-hex { color: #6b7280; font-style: italic; }

/* Value */
.cn-val { color: #fb923c; flex-shrink: 0; font-size: 11px; }

/* Output */
.cn-out-label { color: #4b5563; flex-shrink: 0; }
.cn-out-data { color: #6ee7b7; max-width: 120px; overflow: hidden; text-overflow: ellipsis; font-style: italic; flex-shrink: 0; }
.cn-out-empty { color: #374151; flex-shrink: 0; }

/* Revert */
.cn-revert { color: #f87171; font-size: 10.5px; background: rgba(239,68,68,.08);
  padding: 0 4px; border-radius: 2px; flex-shrink: 0; max-width: 200px; overflow: hidden; text-overflow: ellipsis; }

/* Raw data 按钮 */
.cn-raw-btn {
  margin-left: auto; padding: 0 4px; border: 1px solid transparent;
  background: transparent; color: #484f58; cursor: pointer;
  font-size: 12px; line-height: 16px; border-radius: 3px;
  flex-shrink: 0; transition: all .15s; opacity: 0;
}
.cn-row:hover .cn-raw-btn { opacity: 1; }
.cn-raw-btn:hover { border-color: #58a6ff; color: #58a6ff; background: rgba(88,166,255,.08); }
.cn-raw-btn.active { border-color: #d29922; color: #d29922; opacity: 1; }

/* ── 详情面板（仿 BlockSec）── */
.cn-detail {
  margin: 2px 0 2px 38px; padding: 8px 12px;
  background: rgba(22,27,34,.95); border: 1px solid #21262d; border-radius: 5px;
  display: flex; flex-direction: column; gap: 3px;
  font-size: 11.5px; font-family: 'JetBrains Mono', 'SF Mono', monospace;
  animation: slideIn .12s ease;
}
@keyframes slideIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: none; } }
.cn-detail-row { display: flex; gap: 6px; align-items: baseline; line-height: 18px; }
.cn-dk { color: #7dd3fc; min-width: 52px; flex-shrink: 0; font-weight: 600; }
.cn-dv { color: #c9d1d9; word-break: break-all; }
.dv-addr { color: #a78bfa; }
.dv-label { color: #c084fc; font-weight: 600; }
.dv-sig { color: #fbbf24; font-weight: 500; }
.dv-data { color: #8692a0; }
.dv-hex { color: #4b5563; word-break: break-all; font-size: 10.5px; }
.dv-value { color: #fb923c; }
.dv-gas { color: #6b7280; }
.dv-output { color: #6ee7b7; word-break: break-all; font-size: 10.5px; max-height: 60px; overflow-y: auto; }
.dv-error { color: #f87171; word-break: break-all; }

/* ── 子节点 ── */
.cn-children { margin-left: 26px; }

/* ── Events ── */
.cn-event {
  display: flex; align-items: center; gap: 4px;
  padding: 0 8px 0 36px; font-size: 11px; line-height: 18px;
  color: #7dd3fc; font-family: 'JetBrains Mono', 'SF Mono', monospace;
}
.cn-ev-sp { width: 20px; }
.cn-ev-tag { font-size: 8px; font-weight: 800; letter-spacing: .4px; padding: 0 3px;
  border-radius: 2px; background: rgba(125,211,252,.12); color: #38bdf8; flex-shrink: 0; }
.cn-ev-contract { color: #a78bfa; font-weight: 500; flex-shrink: 0; }
.cn-ev-name { color: #34d399; font-weight: 600; flex-shrink: 0; }
.cn-ev-det { color: #64748b; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ── 截断提示 ── */
.cn-truncate { padding: 2px 8px 2px 26px; color: #6b7280; font-style: italic; font-size: 11px; }
</style>
