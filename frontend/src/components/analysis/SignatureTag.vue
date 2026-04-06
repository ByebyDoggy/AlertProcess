<template>
  <span class="st" :class="{ unknown: !sig }">
    <!-- 已知签名：主签名 + 数量标记 -->
    <span v-if="sig" class="st-sig">
      {{ displaySig }}
      <span
        v-if="resolvedSig && resolvedSig.total > 1"
        class="st-count"
        :title="`${resolvedSig.total} candidate signatures`"
        @click.stop="toggleExpand"
      >+{{ resolvedSig.total - 1 }}</span>
    </span>

    <!-- 未知签名：查询按钮 + 展开结果 -->
    <template v-else>
      <span class="st-unknown">[{{ shortSelector }}]</span>
      <button
        class="st-resolve"
        title="Query signature"
        @click.stop="handleResolve"
        :disabled="resolving"
      >{{ resolving ? '\u2026' : '?' }}</button>
      <template v-if="resolvedSig">
        <!-- 主签名（最佳匹配） -->
        <span class="st-resolved st-primary">
          {{ resolvedSig.signatures[0]?.text }}
          <span
            v-if="resolvedSig.total > 1"
            class="st-count"
            :title="`${resolvedSig.total} candidate signatures`"
            @click.stop="toggleExpand"
          >+{{ resolvedSig.total - 1 }}</span>
        </span>
        <!-- 展开的全部候选签名列表 -->
        <div v-if="expanded" class="st-all-sigs">
          <div
            v-for="(item, idx) in resolvedSig.signatures.slice(1)"
            :key="idx"
            class="st-alt-sig"
          >
            <span class="st-alt-text">{{ item.text }}</span>
            <span v-if="item.num_results" class="st-alt-freq">{{ item.num_results.toLocaleString() }} hits</span>
          </div>
        </div>
      </template>
    </template>
  </span>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useTraceStore } from '@/stores/traceAnalysis.js'

const props = defineProps({
  selector: { type: String, default: '' },
  functionSig: { type: String, default: '' },
})

const store = useTraceStore()
const resolving = ref(false)
const resolvedSig = ref(null)
const expanded = ref(false)

const sig = computed(() => props.functionSig)
const shortSelector = computed(() => (props.selector || '').slice(0, 10))

const displaySig = computed(() => {
  if (!props.functionSig) return ''
  const s = props.functionSig
  return s.length > 65 ? s.slice(0, 62) + '...' : s
})

function toggleExpand() {
  expanded.value = !expanded.value
}

async function handleResolve() {
  if (!props.selector || resolving.value) return
  resolving.value = true
  try {
    const data = await store.resolveSignature(props.selector)
    resolvedSig.value = data
  } finally {
    resolving.value = false
  }
}
</script>

<style scoped>
.st {
  font-family: 'JetBrains Mono', 'SF Mono', 'Fira Code', monospace;
  font-size: 11.5px; color: #f0c040;
}
.st.unknown .st-unknown { color: #484f58; font-style: italic; cursor: default; }

.st-resolve {
  margin-left: 4px; padding: 0 4px;
  border: 1px solid #30363d; background: #161b22;
  color: #8b949e; border-radius: 3px; font-size: 10.5px;
  cursor: pointer; line-height: 16px; transition: all .12s;
}
.st-resolve:hover:not(:disabled) { border-color: #d29922; color: #e3b341; }
.st-resolve:disabled { opacity: .5; cursor: not-allowed; }

/* 已解析签名 */
.st-resolved { margin-left: 5px; color: #3fb950; font-style: normal; }
.st-primary { display: inline-flex; align-items: center; gap: 3px; }

/* 候选数量标记 */
.st-count {
  display: inline-flex; align-items: center;
  margin-left: 2px; padding: 0 4px;
  background: rgba(210,153,34,.15); color: #d29922;
  border: 1px solid rgba(210,153,34,.35); border-radius: 8px;
  font-size: 9.5px; line-height: 15px; cursor: pointer;
  user-select: none; transition: background .12s;
}
.st-count:hover { background: rgba(210,153,34,.28); }

/* 展开的全部候选签名 */
.st-all-sigs {
  display: flex; flex-direction: column; gap: 1px;
  margin-top: 4px; padding: 6px 8px;
  background: rgba(33,38,45,.9); border: 1px solid #30363d; border-radius: 4px;
  max-height: 180px; overflow-y: auto;
}
.st-alt-sig {
  display: flex; align-items: center; justify-content: space-between;
  padding: 2px 0; font-size: 11px; line-height: 18px;
}
.st-alt-text { color: #8b949e; }
.st-alt-freq {
  margin-left: 12px; color: #484f58; font-size: 10px; white-space: nowrap;
}
</style>
