<template>
  <div class="ctv">
    <!-- 工具栏 -->
    <div class="ctv-toolbar">
      <div class="ctv-tb-left">
        <button class="ctv-btn" @click="expandAll" title="Expand All">
          &#9660; Expand
        </button>
        <select v-model="viewMode" class="ctv-select" title="View Mode">
          <option value="default">Default</option>
          <option value="static">Static Call</option>
        </select>
        <label class="ctv-chk"><input type="checkbox" v-model="showGasUsed" /> Gas Used</label>
        <label class="ctv-chk"><input type="checkbox" v-model="showStore" /> SStore</label>
        <label class="ctv-chk"><input type="checkbox" v-model="showSLoad" /> SLoad</label>
      </div>
      <div class="ctv-tb-right">
        <input
          v-model="filterText"
          type="text"
          placeholder="Search by contract label / address ..."
          class="ctv-search"
        />
        <button class="ctv-btn ctv-btn-debug" title="Debug">&#9881; Debug</button>
      </div>
    </div>

    <!-- 树内容区 -->
    <div class="ctv-body" ref="scrollContainer">
      <!-- 空状态 -->
      <div v-if="!store.root && !store.isLoading" class="ctv-empty">
        <span class="ctv-empty-icon">&#128269;</span>
        <p>Enter a transaction hash above to analyze</p>
      </div>

      <!-- 加载中 -->
      <div v-else-if="store.isLoading" class="ctv-loading">
        <span class="ctv-spin">&#8635;</span> Tracing transaction...
      </div>

      <!-- 调用树 -->
      <template v-else>
        <CallNode
          :node="store.root"
          :is-selected="store.selectedNodeId === rootKey"
          @select="handleSelect"
        />

        <!-- 底部统计 -->
        <div class="ctv-footer">
          <span v-if="store.meta.totalEvents">{{ store.meta.totalEvents }} events linked</span>
          <span class="ctv-sep" v-if="store.meta.totalEvents && store.selectorStats.length">|</span>
          <span v-if="store.selectorStats.length">{{ store.selectorStats.length }} unique selectors</span>
          <span class="ctv-sep" v-if="store.meta.elapsedSeconds">|</span>
          <span v-if="store.meta.elapsedSeconds">{{ parseFloat(store.meta.elapsedSeconds).toFixed(2) }}s elapsed</span>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useTraceStore } from '@/stores/traceAnalysis.js'
import CallNode from './CallNode.vue'

const store = useTraceStore()
const scrollContainer = ref(null)

const filterText = computed({
  get: () => store.filterText,
  set: (v) => { store.filterText = v }
})

const viewMode = ref('default')
const showGasUsed = ref(false)
const showStore = ref(false)
const showSLoad = ref(false)

function expandAll() { store.expandAll() }
function collapseAll() { store.collapseAll() }

const rootKey = computed(() => {
  if (!store.root) return ''
  return `0-[]-${store.root.toAddress}`
})

function handleSelect() {
  store.selectNode(rootKey.value)
}
</script>

<style scoped>
.ctv {
  display: flex; flex-direction: column;
  height: 100%; overflow: hidden;
  background: #0d1117;
  border-radius: 8px;
  border: 1px solid #21262d;
}

/* Toolbar */
.ctv-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 10px; gap: 6px;
  background: #161b22; border-bottom: 1px solid #21262d;
  border-radius: 8px 8px 0 0; flex-wrap: wrap;
}
.ctv-tb-left, .ctv-tb-right { display: flex; align-items: center; gap: 6px; }

.ctv-btn {
  padding: 3px 10px; font-size: 11px;
  border: 1px solid #30363d; border-radius: 4px;
  background: #0d1117; color: #8b949e; cursor: pointer;
  transition: all .12s; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
.ctv-btn:hover { border-color: #58a6ff; color: #e6edf3; }
.ctv-btn-debug { font-weight: 700; letter-spacing: .3px; }

.ctv-select {
  padding: 3px 7px; font-size: 11.5px;
  background: #0d1117; border: 1px solid #30363d; border-radius: 4px;
  color: #c9d1d9; cursor: pointer; outline: none;
}

.ctv-chk {
  display: flex; align-items: center; gap: 3px;
  font-size: 11px; color: #8b949e; cursor: pointer; white-space: nowrap;
}
.ctv-chk input { accent-color: #58a6ff; }

.ctv-search {
  padding: 4px 10px; width: 220px; min-width: 140px;
  background: #0d1117; border: 1px solid #30363d; border-radius: 4px;
  color: #c9d1d9; font-size: 11.5px; outline: none; font-family: inherit;
}
.ctv-search:focus { border-color: #58a6ff; box-shadow: 0 0 0 1px rgba(88,166,255,.25); }
.ctv-search::placeholder { color: #484f58; }

/* Body */
.ctv-body {
  flex: 1; overflow-y: auto; overflow-x: hidden;
  padding: 4px 0;
}
.ctv-body::-webkit-scrollbar { width: 6px; }
.ctv-body::-webkit-scrollbar-track { background: transparent; }
.ctv-body::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }

/* Empty / Loading */
.ctv-empty, .ctv-loading {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; height: 260px; color: #484f58; gap: 10px;
}
.ctv-empty-icon { font-size: 36px; opacity: .6; }
.ctv-loading { color: #8b949e; font-size: 13px; }
.ctv-spin { animation: spin 1s linear infinite; display: inline-block; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Footer */
.ctv-footer {
  display: flex; align-items: center; gap: 8px; justify-content: center;
  padding: 6px; border-top: 1px solid #161b22;
  font-size: 10.5px; color: #484f58; font-family: -apple-system, sans-serif;
}
.ctv-sep { color: #21262d; }
</style>
