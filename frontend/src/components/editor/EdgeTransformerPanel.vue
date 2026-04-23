<template>
  <Teleport to="body">
    <div v-if="visible" class="transformer-overlay" :style="overlayStyle" @click.self="$emit('close')">
      <div class="transformer-panel">
        <!-- Header (draggable) -->
        <div class="panel-header" :class="{ 'is-dragging': isDragging }" @mousedown="onHeaderMouseDown">
          <div class="panel-title">
            <span class="transform-icon">&#8693;</span>
            <span>数据转换</span>
            <span class="source-target-hint">
              {{ sourceLabel }} <span class="arrow">&#8594;</span> {{ targetLabel }}
            </span>
          </div>
          <button class="panel-close-btn" @click="$emit('close')">&times;</button>
        </div>

        <!-- Body -->
        <div class="panel-body">
          <!-- 上游输出数据（原始输入） -->
          <div class="input-data-section">
            <div class="data-section-header">
              <span class="data-icon">&#8592;</span>
              <span>上游输出</span>
              <span class="source-tag">{{ sourceLabel }}</span>
            </div>
            <div v-if="Object.keys(sampleInput).length > 0" class="input-data-list">
              <div v-for="(val, key) in sampleInput" :key="key" class="input-data-row">
                <span class="input-key">{{ key }}</span>
                <span class="input-val">{{ formatPreviewVal(val) }}</span>
              </div>
            </div>
            <div v-else class="no-input-hint">
              上游节点未测试，暂无输入数据
            </div>
          </div>

          <!-- Transformer editor -->
          <InputTransformer
            :modelValue="currentTransformer"
            :sampleInput="sampleInput"
            @update:modelValue="onTransformerUpdate"
          />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, reactive, watch, ref } from 'vue'
import { useChainDataStore } from '../../stores/chainData.js'
import InputTransformer from './InputTransformer.vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  position: { type: Object, default: () => ({ x: 400, y: 200 }) },
  /** 画布 zoom 级别，用于反比例缩放面板尺寸，保持与节点卡片视觉一致 */
  zoom: { type: Number, default: 1 },
  edgeId: { type: String, default: null },
  sourceLabel: { type: String, default: '' },
  targetLabel: { type: String, default: '' },
  outputSchema: { type: Object, default: () => ({}) },
  inputSchema: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['close'])

const chainDataStore = useChainDataStore()

// canvas 视口中的锚点（逻辑坐标，zoom 变化时不变，拖拽时更新）
const canvasAnchor = reactive({ x: 400, y: 200 })

// 面板打开时，从 canvas 逻辑坐标初始化锚点
watch(() => props.visible, (val) => {
  if (val) {
    canvasAnchor.x = props.position.x
    canvasAnchor.y = props.position.y
  }
}, { immediate: true })

// zoom 变化时，同步更新 canvasAnchor（保持面板视觉位置不变）
watch(() => props.zoom, (newZoom, oldZoom) => {
  if (!oldZoom || newZoom === oldZoom) return
  // 面板视觉位置 = canvasAnchor * zoom，需保持不变
  // canvasAnchor_new = canvasAnchor_old * oldZoom / newZoom
  canvasAnchor.x = canvasAnchor.x * oldZoom / newZoom
  canvasAnchor.y = canvasAnchor.y * oldZoom / newZoom
})

// 拖拽逻辑（在屏幕像素坐标中移动，实时换算回 canvas 锚点）
const isDragging = ref(false)
let dragOffsetX = 0
let dragOffsetY = 0

function onHeaderMouseDown(e) {
  if (e.target.closest('.panel-close-btn')) return
  e.preventDefault()
  isDragging.value = true
  // 当前面板在屏幕上的像素位置
  const screenX = canvasAnchor.x * props.zoom
  const screenY = canvasAnchor.y * props.zoom
  dragOffsetX = e.clientX - screenX
  dragOffsetY = e.clientY - screenY

  const onMove = (ev) => {
    if (!isDragging.value) return
    const newScreenX = Math.max(0, Math.min(ev.clientX - dragOffsetX, window.innerWidth - 390))
    const newScreenY = Math.max(0, Math.min(ev.clientY - dragOffsetY, window.innerHeight - 460))
    canvasAnchor.x = newScreenX / props.zoom
    canvasAnchor.y = newScreenY / props.zoom
  }
  const onUp = () => {
    isDragging.value = false
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

const overlayStyle = computed(() => ({
  left: (canvasAnchor.x * props.zoom) + 'px',
  top: (canvasAnchor.y * props.zoom) + 'px',
  transform: `scale(${props.zoom})`,
  transformOrigin: 'top left',
}))

/** 当前边的 transformer 配置 */
const currentTransformer = computed(() => {
  if (!props.edgeId) return null
  const edge = chainDataStore.edges.find(e => e.id === props.edgeId)
  return edge?.inputTransformer || null
})

/** 从上游节点的测试结果构建 sampleInput */
const sampleInput = computed(() => {
  if (!props.edgeId) return {}
  const edge = chainDataStore.edges.find(e => e.id === props.edgeId)
  if (!edge) return {}

  const sourceResult = chainDataStore.nodeTestResults[edge.source]?.output
  if (!sourceResult) return {}

  // 合并 score/passed/severity/labels + context
  return {
    score: sourceResult.score,
    passed: sourceResult.passed,
    severity: sourceResult.severity,
    labels: sourceResult.labels || [],
    ...(sourceResult.context || {}),
  }
})

/** 更新边上的 transformer */
function onTransformerUpdate(transformer) {
  if (!props.edgeId) return
  chainDataStore.updateEdge(props.edgeId, { inputTransformer: transformer })
}

/** 格式化预览值 */
function formatPreviewVal(val) {
  if (val === undefined || val === null) return '-'
  if (typeof val === 'boolean') return val ? 'true' : 'false'
  if (Array.isArray(val)) return `[${val.length}]`
  if (typeof val === 'object') return `{${Object.keys(val).length}}`
  const s = String(val)
  return s.length > 18 ? s.substring(0, 17) + '\u2026' : s
}
</script>

<style scoped>
.transformer-overlay {
  position: fixed;
  z-index: 200;
  filter: drop-shadow(0 12px 40px rgba(0,0,0,0.6));
}

.transformer-panel {
  width: 380px;
  background: #1a1a30;
  border: 1px solid rgba(99,102,241,0.28);
  border-radius: 10px;
  overflow: hidden;
  animation: panelIn 0.18s ease-out;
}

@keyframes panelIn {
  from { opacity: 0; transform: translateY(-4px) scale(0.97); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.panel-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px;
  background: rgba(99,102,241,0.08);
  border-bottom: 1px solid rgba(99,102,241,0.15);
  cursor: grab;
  user-select: none;
}
.panel-header.is-dragging {
  cursor: grabbing;
}

.panel-title {
  font-size: 11px; font-weight: 600; color: #a5b4fc;
  display: flex; align-items: center; gap: 6px;
}

.transform-icon { font-size: 14px; }

.source-target-hint {
  font-size: 9px; color: #6b7280; font-weight: 400;
  margin-left: 6px;
}

.arrow { color: #818cf8; margin: 0 2px; }

.panel-close-btn {
  width: 22px; height: 22px; border-radius: 5px; border: none;
  background: rgba(239,68,68,0.1); color: #f87171;
  font-size: 13px; cursor: pointer; display: flex;
  align-items: center; justify-content: center;
}

.panel-close-btn:hover { background: rgba(239,68,68,0.25); }

.panel-body {
  padding: 8px;
  max-height: 520px;
  overflow-y: auto;
}

/* 上游输出数据面板 */
.input-data-section {
  margin-bottom: 4px;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid rgba(99,102,241,0.12);
}

.data-section-header {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: rgba(99,102,241,0.06);
  font-size: 7.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #818cf8;
}

.data-icon { font-size: 9px; }

.source-tag {
  margin-left: auto;
  font-size: 7px;
  color: #6b7280;
  font-weight: 400;
  text-transform: none;
  letter-spacing: 0;
}

.input-data-list {
  background: rgba(15,15,26,0.6);
  max-height: 160px;
  overflow-y: auto;
}

.input-data-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px;
  font-size: 8px;
  line-height: 1.5;
  border-bottom: 1px solid rgba(255,255,255,0.03);
}
.input-data-row:last-child { border-bottom: none; }

.input-key {
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  color: #60a5fa;
  flex-shrink: 0;
  font-size: 7.5px;
}

.input-val {
  color: #6b7280;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: 7.5px;
}

.no-input-hint {
  padding: 6px 8px;
  font-size: 8px;
  color: #4b5563;
  font-style: italic;
  background: rgba(15,15,26,0.4);
}
</style>
