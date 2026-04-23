<template>
  <Teleport to="body">
    <div v-if="visible" class="fp-overlay" @click.self="handleClose">
      <div class="fp-panel">
        <!-- Header -->
        <div class="fp-header">
          <div class="fp-title-row">
            <span class="fp-icon">&#9776;</span>
            <span class="fp-title">字段选择器</span>
          </div>
          <button class="fp-close" @click="handleClose" title="关闭">&#10005;</button>
        </div>

        <!-- Target info -->
        <div class="fp-target-info">
          <span class="fp-target-label">目标节点</span>
          <span class="fp-target-node">{{ targetNodeLabel }}</span>
          <span class="fp-arrow">&rarr;</span>
          <span class="fp-target-field">
            {{ targetInputField?.label || targetInputField?.key }}
            <span class="fp-target-type" :class="'tag-' + (targetInputField?.type || 'any')">{{ targetInputField?.type || '?' }}</span>
          </span>
        </div>

        <!-- Source tabs (one per upstream node) -->
        <div v-if="sourceNodes.length > 0" class="fp-tabs">
          <button
            v-for="(src, idx) in sourceNodes"
            :key="src.nodeId"
            :class="['fp-tab', { 'fp-tab-active': activeSourceIdx === idx }]"
            @click="activeSourceIdx = idx"
          >
            <span class="fp-tab-node">{{ src.nodeLabel }}</span>
            <span class="fp-tab-type">输出</span>
          </button>
        </div>

        <!-- Object tree -->
        <div class="fp-body">
          <div v-if="!activeSourceData" class="fp-empty-hint">
            <p>上游节点尚未执行测试，无法浏览输出数据。</p>
            <p class="fp-empty-sub">请先对上游节点运行测试（点击节点上的 &#9654; 按钮），然后重新打开选择器。</p>
          </div>

          <div v-else class="fp-tree">
            <FPTreeItem
              :data="activeSourceData"
              :path="activeSourceNodeLabel"
              :depth="0"
              :target-input-type="targetInputField?.type"
              :expanded-set="expandedSet"
              :field-defs="activeSourceFieldDefs"
              @select="handleSelect"
              @toggle="toggleExpand"
            />
          </div>
        </div>

        <!-- Footer -->
        <div class="fp-footer">
          <div class="fp-selected" v-if="selectedPath">
            <span class="fp-sel-label">已选:</span>
            <span class="fp-sel-path">{{ selectedPath }}</span>
            <button class="fp-btn fp-btn-apply" @click="handleConfirm" :disabled="!selectedPath">
              确认映射
            </button>
            <button class="fp-btn fp-btn-ghost" @click="clearSelection">清除</button>
          </div>
          <div v-else class="fp-hint">点击树中的任意属性值来映射到目标输入参数</div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import FPTreeItem from './FPTreeItem.vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  nodeId: { type: String, default: '' },
  inputField: { type: Object, default: null },
  allFields: { type: Array, default: () => [] },
  targetNodeLabel: { type: String, default: '' },  // 新增：从父组件传入
})

const emit = defineEmits(['close', 'confirm'])

const activeSourceIdx = ref(0)
const expandedSet = ref(new Set())
const selectedPath = ref('')
const selectedValue = ref(null)

// ── Computed ──

const sourceNodes = computed(() => {
  return props.allFields.filter(s => s.testOutput != null)
})

const activeSourceNode = computed(() => sourceNodes.value[activeSourceIdx.value] || null)

const activeSourceNodeLabel = computed(() => activeSourceNode.value?.nodeLabel || '?')

const activeSourceData = computed(() => activeSourceNode.value?.testOutput || null)

const activeSourceFieldDefs = computed(() => activeSourceNode.value?.outputFields || [])

// targetNodeLabel 直接使用 props，由父组件传入
const targetNodeLabel = computed(() => props.targetNodeLabel || props.nodeId?.slice(0, 8) || '?')

// ── Actions ──

function toggleExpand(path) {
  if (expandedSet.value.has(path)) {
    expandedSet.value.delete(path)
  } else {
    expandedSet.value.add(path)
  }
  expandedSet.value = new Set(expandedSet.value)
}

function handleSelect({ path, value }) {
  selectedPath.value = path
  selectedValue.value = value
}

function clearSelection() {
  selectedPath.value = ''
  selectedValue.value = null
}

function handleConfirm() {
  if (!selectedPath.value) return
  emit('confirm', {
    path: selectedPath.value,
    value: selectedValue.value,
    sourceNodeId: activeSourceNode.value?.nodeId,
    sourceNodeType: activeSourceNode.value?.nodeType,
    sourceNodeLabel: activeSourceNode.value?.nodeLabel,
    targetNodeId: props.nodeId,
    targetKey: props.inputField?.key,
    targetType: props.inputField?.type,
  })
  clearSelection()
  handleClose()
}

function handleClose() {
  clearSelection()
  expandedSet.value.clear()
  activeSourceIdx.value = 0
  emit('close')
}

// Auto-expand first level when source changes
watch(activeSourceNode, () => {
  if (activeSourceData.value) {
    expandedSet.value = new Set(Object.keys(activeSourceData.value))
  }
}, { immediate: true })
</script>

<style scoped>
.fp-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
  animation: fpIn 0.15s ease;
}
@keyframes fpIn { from { opacity: 0; } to { opacity: 1; } }

.fp-panel {
  width: 580px;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  background: #13142c;
  border: 1px solid #2d2d50;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  font-family: 'SF Mono', 'Cascadia Code', 'JetBrains Mono', monospace;
  overflow: hidden;
}

/* Header */
.fp-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid #1e293b; flex-shrink: 0;
}
.fp-title-row { display: flex; align-items: center; gap: 8px; }
.fp-icon { font-size: 16px; color: #6366f1; }
.fp-title { font-size: 14px; font-weight: 700; color: #e2e8f0; }
.fp-close {
  width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
  border-radius: 6px; border: none; background: transparent;
  color: #64748b; cursor: pointer; font-size: 16px;
}
.fp-close:hover { background: rgba(239,68,68,0.15); color: #ef4444; }

/* Target info */
.fp-target-info {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 18px; background: rgba(99,102,241,0.05); border-bottom: 1px solid #1e293b;
  font-size: 11.5px; flex-shrink: 0; flex-wrap: wrap;
}
.fp-target-label { color: #64748b; text-transform: uppercase; letter-spacing: 0.3px; font-weight: 600; font-size: 9.5px; }
.fp-target-node { color: #818cf8; font-weight: 600; }
.fp-arrow { color: #4a5568; }
.fp-target-field { display: flex; align-items: center; gap: 6px; color: #c4b5fd; font-weight: 600; }
.fp-target-type {
  padding: 1px 7px; border-radius: 3px; font-size: 9px; font-weight: 700;
}

/* Tabs */
.fp-tabs {
  display: flex; gap: 4px; padding: 8px 18px 0; border-bottom: 1px solid #1e293b; flex-shrink: 0; overflow-x: auto;
}
.fp-tab {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 14px; border: none; border-bottom: 2px solid transparent;
  background: transparent; cursor: pointer; font-size: 11.5px; font-weight: 600;
  color: #64748b; border-radius: 6px 6px 0 0; transition: all .12s; white-space: nowrap;
}
.fp-tab:hover:not(.fp-tab-active) { background: rgba(99,102,241,.06); color: #94a3b8; }
.fp-tab-active { color: #c4b5fd; border-bottom-color: #6366f1; background: rgba(99,102,241,.08); }
.fp-tab-node { color: inherit; }
.fp-tab-type { opacity: .5; font-size: 9px; text-transform: uppercase; letter-spacing: 0.3px; }

/* Body */
.fp-body { flex: 1; overflow-y: auto; padding: 12px 18px; min-height: 120px; }
.fp-tree { display: flex; flex-direction: column; gap: 2px; }
.fp-empty-hint { color: #4a5568; font-size: 12px; line-height: 1.6; padding: 24px 0; text-align: center; }
.fp-empty-sub { color: #374151; font-size: 11px; margin-top: 8px; }

/* Footer */
.fp-footer { padding: 12px 18px; border-top: 1px solid #1e293b; flex-shrink: 0; }
.fp-selected { display: flex; align-items: center; gap: 10px; }
.fp-sel-label { color: #64748b; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px; }
.fp-sel-path {
  flex: 1; font-size: 11px; color: #34d399; font-family: inherit;
  background: rgba(52,211,153,0.06); padding: 4px 10px; border-radius: 4px;
  word-break: break-all;
}
.fp-hint { color: #4a5568; font-size: 11px; font-style: italic; }

.fp-btn {
  padding: 5px 12px; border-radius: 5px; font-size: 11px; font-weight: 600;
  cursor: pointer; border: none; font-family: inherit;
}
.fp-btn-apply { background: #22c55e; color: #fff; }
.fp-btn-apply:hover:not(:disabled) { background: #16a34a; }
.fp-btn-apply:disabled { opacity: .4; cursor: not-allowed; }
.fp-btn-ghost { background: rgba(255,255,255,.04); color: #94a3b8; border: 1px solid rgba(255,255,255,.08); }
.fp-btn-ghost:hover { background: rgba(255,255,255,.08); color: #c9d1d9; }
</style>
