<template>
  <div
    ref="canvasRef"
    class="flex-1 canvas-area relative overflow-hidden"
    @drop="onDrop"
    @dragover.prevent
    @click.self="onCanvasClick"
    @wheel="onWheel"
    @mousedown="onMouseDown"
    @contextmenu.prevent
  >
    <!-- Transform container -->
    <div
      class="absolute origin-top-left"
      :style="transformStyle"
    >
      <!-- SVG Layer -->
      <svg class="absolute inset-0" style="z-index: 1; pointer-events: none; overflow: visible;">
        <defs>
          <marker id="arrow-default" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#4a4a7a" />
          </marker>
          <marker id="arrow-selected" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#f59e0b" />
          </marker>
          <marker id="arrow-invalid" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#ef4444" />
          </marker>
        </defs>

        <!-- Edges -->
        <Edge
          v-for="edge in edges"
          :key="edge.id"
          :from="getEdgeFrom(edge)"
          :to="getEdgeTo(edge)"
          :selected="selectedEdgeId === edge.id"
          :label="getEdgeLabel(edge)"
          @click.stop="onEdgeClick(edge)"
        />

        <!-- Temp connection -->
        <TempEdge
          :path="tempLine"
          :visible="connecting"
          :valid="tempLineValid"
        />
      </svg>

      <!-- DOM Layer: Nodes -->
      <NodeCard
        v-for="node in nodes"
        :key="node.id"
        :node="node"
        :selected="selectedNodeId === node.id"
        :style="{ zIndex: draggingNodeId === node.id ? 20 : 10 }"
        @click="onNodeClick"
        @dbl-click="onNodeDblClick"
        @delete="onDeleteNode"
        @start-drag="onNodeDragStart"
        @port-drag="onPortDragStart"
      />

      <!-- Empty state -->
      <div v-if="nodes.length === 0" class="absolute inset-0 flex items-center justify-center pointer-events-none" style="z-index: 0;">
        <div class="empty-canvas-hint">
          <div class="empty-canvas-icon">&#x1F517;</div>
          <div style="color: #6b7280; font-size: 14px; font-weight: 500;">拖拽节点到此处开始构建规则链</div>
          <div style="color: #4a4a7a; font-size: 12px; margin-top: 6px;">
            从左侧面板拖入 告警触发器 作为起点
          </div>
        </div>
      </div>
    </div>

    <!-- Zoom controls -->
    <div class="absolute bottom-4 right-4 flex items-center gap-1.5 bg-[#16162a]/90 border border-[#2d2d50] rounded-lg px-2 py-1" style="z-index: 50;">
      <button @click="handleZoomOut" class="zoom-btn" title="缩小">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><line x1="3" y1="8" x2="13" y2="8" stroke="currentColor" stroke-width="1.5"/></svg>
      </button>
      <span class="text-xs text-gray-400 w-12 text-center select-none">{{ Math.round(zoom * 100) }}%</span>
      <button @click="handleZoomIn" class="zoom-btn" title="放大">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><line x1="8" y1="3" x2="8" y2="13" stroke="currentColor" stroke-width="1.5"/><line x1="3" y1="8" x2="13" y2="8" stroke="currentColor" stroke-width="1.5"/></svg>
      </button>
      <button @click="handleResetView" class="zoom-btn" title="重置视图">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><rect x="3" y="3" width="10" height="10" rx="1.5" stroke="currentColor" stroke-width="1.2"/></svg>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useChainDataStore } from '../../stores/chainData.js'
import { useChainEditorStore } from '../../stores/chainEditor.js'
import { useNodeTypesStore } from '../../stores/nodeTypes.js'
import { useConnection } from '../../composables/useConnection.js'
import { useDragDrop } from '../../composables/useDragDrop.js'
import { getPortPosition } from '../../utils/geometry.js'
import Edge from './Edge.vue'
import NodeCard from './NodeCard.vue'
import TempEdge from './TempEdge.vue'

const emit = defineEmits(['edgeCreated', 'edgeInvalid'])

const canvasRef = ref(null)
const chainDataStore = useChainDataStore()
const editorStore = useChainEditorStore()
const nodeTypesStore = useNodeTypesStore()

const nodes = computed(() => chainDataStore.nodes)
const edges = computed(() => chainDataStore.edges)
const selectedNodeId = computed(() => editorStore.selectedNodeId)
const selectedEdgeId = computed(() => editorStore.selectedEdgeId)
const connecting = computed(() => editorStore.connecting)
const tempLine = computed(() => editorStore.tempLine)
const tempLineValid = computed(() => editorStore.tempLineValid)
const zoom = computed(() => editorStore.zoom)
const panX = computed(() => editorStore.panX)
const panY = computed(() => editorStore.panY)

const transformStyle = computed(() => ({
  transform: `translate(${panX.value}px, ${panY.value}px) scale(${zoom.value})`,
}))

const { startPortDrag } = useConnection(canvasRef)
const { draggingNodeId, handleCanvasDrop, startNodeDrag } = useDragDrop(canvasRef)

// ─── Zoom ───
function onWheel(e) {
  if (!e.ctrlKey && !e.metaKey) return
  e.preventDefault()
  const delta = e.deltaY > 0 ? -0.1 : 0.1
  const newZoom = Math.max(0.2, Math.min(3, zoom.value + delta))

  // Zoom toward cursor
  const rect = canvasRef.value.getBoundingClientRect()
  const mouseX = e.clientX - rect.left
  const mouseY = e.clientY - rect.top
  const scale = newZoom / zoom.value
  const newPanX = mouseX - scale * (mouseX - panX.value)
  const newPanY = mouseY - scale * (mouseY - panY.value)

  editorStore.setZoom(newZoom)
  editorStore.panX = newPanX
  editorStore.panY = newPanY
}

function handleZoomIn() {
  editorStore.setZoom(zoom.value + 0.15)
}

function handleZoomOut() {
  editorStore.setZoom(zoom.value - 0.15)
}

function handleResetView() {
  editorStore.resetView()
}

// ─── Edge rendering (memoized) ───
function getPortInfo(nodeId, portKey, side) {
  const node = nodes.value.find(n => n.id === nodeId)
  if (!node) return { x: 0, y: 0 }

  const nodeType = nodeTypesStore.getByName(node.type)
  const portType = side === 'left' ? 'inputs' : 'outputs'

  let portIndex = 0
  if (side === 'left' && node.config?.inputPorts) {
    portIndex = node.config.inputPorts.indexOf(portKey)
    if (portIndex === -1) portIndex = 0
  } else {
    const ports = nodeType?.[portType] || []
    portIndex = ports.findIndex(p => p.key === portKey)
    if (portIndex === -1) portIndex = 0
  }

  return getPortPosition(node, portKey, side, Math.max(0, portIndex))
}

const edgeEndpointsCache = computed(() => {
  const map = {}
  for (const edge of edges.value) {
    map[edge.id] = {
      from: getPortInfo(edge.source, edge.sourcePort || 'output', 'right'),
      to: getPortInfo(edge.target, edge.targetPort || 'input_0', 'left'),
    }
  }
  return map
})

function getEdgeFrom(edge) {
  return edgeEndpointsCache.value[edge.id]?.from || { x: 0, y: 0 }
}

function getEdgeTo(edge) {
  return edgeEndpointsCache.value[edge.id]?.to || { x: 0, y: 0 }
}

function getEdgeLabel(edge) {
  if (edge.sourcePort === 'true') return '满足'
  if (edge.sourcePort === 'false') return '不满足'
  return edge.label || ''
}

// ─── Pan (middle mouse button) ───
const isPanning = ref(false)
let panStartX = 0
let panStartY = 0
let panStartPanX = 0
let panStartPanY = 0

function onMouseDown(e) {
  if (e.button !== 1) return // only middle button
  e.preventDefault()
  isPanning.value = true
  panStartX = e.clientX
  panStartY = e.clientY
  panStartPanX = editorStore.panX
  panStartPanY = editorStore.panY

  const onMove = (ev) => {
    if (!isPanning.value) return
    editorStore.panX = panStartPanX + (ev.clientX - panStartX)
    editorStore.panY = panStartPanY + (ev.clientY - panStartY)
  }
  const onUp = () => {
    isPanning.value = false
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

// ─── Event handlers ───
function onNodeClick(nodeId) {
  editorStore.selectNode(nodeId)
}

function onNodeDblClick(node) {
  editorStore.openNodeConfig(node.id)
}

function onDeleteNode(nodeId) {
  chainDataStore.removeNode(nodeId)
  if (editorStore.selectedNodeId === nodeId) editorStore.clearSelection()
}

function onNodeDragStart(event, node) {
  startNodeDrag(event, node)
}

function onPortDragStart(event, node, portKey, side) {
  startPortDrag(event, node, portKey, side)
}

function onEdgeClick(edge) {
  editorStore.selectEdge(edge.id)
  editorStore.openEdgeConfig(edge.id)
}

function onCanvasClick() {
  editorStore.clearSelection()
}

function onDrop(event) {
  handleCanvasDrop(event)
}
</script>

<style scoped>
.zoom-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  color: #9ca3af;
  cursor: pointer;
  transition: all 0.15s;
  border: none;
  background: transparent;
}
.zoom-btn:hover {
  color: #e5e7eb;
  background: rgba(255, 255, 255, 0.08);
}
.canvas-area {
  cursor: default;
}
.canvas-area:active {
  cursor: default;
}
</style>
