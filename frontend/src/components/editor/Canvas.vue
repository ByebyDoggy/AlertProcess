<template>
  <div
    ref="canvasRef"
    class="flex-1 canvas-area relative overflow-hidden"
    @drop="onDrop"
    @dragover.prevent
    @click.self="onCanvasClick"
    @wheel="onWheel"
    @mousedown="onMouseDown"
    @contextmenu.prevent="onContextMenu"
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
          :multi-selected="isEdgeMultiSelected(edge)"
          :label="getEdgeLabel(edge)"
          :field-mapping="edge.fieldMapping"
          :expression="getExpression(edge)"
          @click.stop="onEdgeClick(edge)"
          @edit-expression="onEditExpression($event, edge)"
          @context-menu="onEdgeContextMenu($event, edge)"
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
        :selected="selectedNodeId === node.id || selectedNodeIds.includes(node.id)"
        :style="{ zIndex: draggingNodeId === node.id ? 20 : 10 }"
        @click="onNodeClick"
        @dbl-click="onNodeDblClick"
        @delete="onDeleteNode"
        @start-drag="onNodeDragStart"
        @port-drag="onPortDragStart"
        @open-test="(nodeId) => $emit('openTest', nodeId)"
        @open-field-picker="onOpenFieldPicker"
      />

      <!-- Selection rectangle (inside transform container for correct coordinates) -->
      <div
        v-if="selectionRect.visible"
        class="selection-rect"
        :style="{
          left: selectionRect.x + 'px',
          top: selectionRect.y + 'px',
          width: selectionRect.w + 'px',
          height: selectionRect.h + 'px',
        }"
      ></div>

    </div>

    <!-- Empty state (outside transform container to stay centered in viewport) -->
    <div v-if="nodes.length === 0" class="absolute inset-0 flex items-center justify-center pointer-events-none" style="z-index: 0;">
      <div class="empty-canvas-hint">
        <div class="empty-canvas-icon">&#x1F517;</div>
        <div style="color: #6b7280; font-size: 14px; font-weight: 500;">拖拽节点到此处开始构建规则链</div>
        <div style="color: #4a4a7a; font-size: 12px; margin-top: 6px;">
          从左侧面板拖入 告警触发器 作为起点
        </div>
      </div>
    </div>

    <!-- Fixed selection rectangle (after mouseup, persists) -->
    <div
      v-show="fixedRectVisible"
      class="fixed-selection-rect"
      :style="fixedSelectionRectStyle"
      @mousedown.stop="onFixedRectDragStart"
      @contextmenu.stop.prevent="onSelectionContextMenu"
    ></div>

    <!-- Context menu for selection -->
    <div
      v-if="contextMenu.visible"
      class="context-menu"
      :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
      @mousedown.stop
    >
      <div class="context-menu-item danger" @click="deleteSelectedNodes">删除选中</div>
      <div class="context-menu-item copy" @click="duplicateSelectedNodes">复制选中</div>
      <div class="context-menu-item" @click="cancelSelection">取消选择</div>
    </div>

    <!-- Context menu for edge (right-click on connection line) -->
    <div
      v-if="edgeContextMenu.visible"
      class="context-menu"
      :style="{ left: edgeContextMenu.x + 'px', top: edgeContextMenu.y + 'px' }"
      @mousedown.stop
    >
      <div class="context-menu-item danger" @click="deleteEdgeFromMenu">删除连线</div>
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
    <!-- Expression Selector (teleported to body) — 替换为边级 Transformer 编辑器 -->
    <EdgeTransformerPanel
      :visible="transformerPanel.visible"
      :position="transformerPanel.position"
      :zoom="zoom"
      :edge-id="transformerPanel.targetEdgeId"
      :source-label="transformerPanel.sourceLabel"
      :target-label="transformerPanel.targetLabel"
      :output-schema="transformerPanel.outputSchema"
      :input-schema="transformerPanel.inputSchema"
      @close="transformerPanel.visible = false"
    />
  </div>
</template>

<script setup>
import { ref, computed, reactive } from 'vue'
import { useChainDataStore } from '../../stores/chainData.js'
import { useChainEditorStore } from '../../stores/chainEditor.js'
import { useNodeTypesStore } from '../../stores/nodeTypes.js'
import { useConnection } from '../../composables/useConnection.js'
import { useDragDrop } from '../../composables/useDragDrop.js'
import { getPortPosition } from '../../utils/geometry.js'
import Edge from './Edge.vue'
import NodeCard from './NodeCard.vue'
import TempEdge from './TempEdge.vue'
import EdgeTransformerPanel from './EdgeTransformerPanel.vue'

const emit = defineEmits(['edgeCreated', 'edgeInvalid', 'openTest', 'openFieldPicker'])

const canvasRef = ref(null)
const chainDataStore = useChainDataStore()
const editorStore = useChainEditorStore()
const nodeTypesStore = useNodeTypesStore()

const nodes = computed(() => chainDataStore.nodes)
const edges = computed(() => chainDataStore.edges)
const selectedNodeId = computed(() => editorStore.selectedNodeId)
const selectedEdgeId = computed(() => editorStore.selectedEdgeId)
const selectedNodeIds = computed(() => editorStore.selectedNodeIds)
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
const { draggingNodeId, dragTick, handleCanvasDrop, startNodeDrag } = useDragDrop(canvasRef)

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

// ─── Edge rendering (DOM-based port position) ───
/**
 * 从 DOM 读取端口圆圈的真实画布坐标。
 * 比 geometry.js 固定公式更准确 — 适配不同节点的动态高度（测试面板、数据面板等）。
 */
function getPortInfo(nodeId, portKey, side) {
  const node = nodes.value.find(n => n.id === nodeId)
  if (!node || !canvasRef.value) return { x: 0, y: 0 }

  // 查找节点卡片内的端口圆圈 DOM 元素
  const nodeEl = canvasRef.value.querySelector(`[data-node-id="${nodeId}"]`)
  if (!nodeEl) {
    return getPortPosition(node, portKey, side, 0)
  }

  const portEl = nodeEl.querySelector(`[data-port-key="${portKey}"][data-port-side="${side}"]`)
  if (!portEl) return { x: 0, y: 0 }

  const rect = portEl.getBoundingClientRect()
  const cx = rect.left + rect.width / 2
  const cy = rect.top + rect.height / 2

  // viewport → canvas 逻辑坐标
  const canvasRect = canvasRef.value.getBoundingClientRect()
  const x = (cx - canvasRect.left) / zoom.value - panX.value / zoom.value
  const y = (cy - canvasRect.top) / zoom.value - panY.value / zoom.value

  return { x, y }
}

const edgeEndpointsCache = computed(() => {
  // 依赖 dragTick：拖拽节点时 DOM 位置变了但 store 未更新，
  // 递增 dragTick 强制此 computed 每帧重算，从 DOM 读取最新端口位置
  void dragTick.value
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

// ─── Shift+Left-click Selection ───
const NODE_WIDTH = 300
const NODE_HEADER_H = 47

const selectionRect = reactive({ visible: false, x: 0, y: 0, w: 0, h: 0 })
// Fixed rect: 每个属性独立 ref，避免 reactive 对象被意外覆盖导致响应性丢失
const fixedRectVisible = ref(false)
const fixedRectX = ref(0)
const fixedRectY = ref(0)
const fixedRectW = ref(0)
const fixedRectH = ref(0)
const contextMenu = reactive({ visible: false, x: 0, y: 0 })
/** 连线右键菜单：记录目标 edge 引用，用于删除 */
const edgeContextMenu = reactive({ visible: false, x: 0, y: 0, targetEdgeId: null })

const fixedSelectionRectStyle = computed(() => {
  if (!fixedRectVisible.value) return {}
  const s = zoom.value
  return {
    left: (fixedRectX.value * s + panX.value) + 'px',
    top: (fixedRectY.value * s + panY.value) + 'px',
    width: (fixedRectW.value * s) + 'px',
    height: (fixedRectH.value * s) + 'px',
  }
})

// 标志：刚完成框选操作，用于阻止后续 click 事件清除选中状态
let justFinishedSelection = false

function screenToCanvas(clientX, clientY) {
  const cr = canvasRef.value.getBoundingClientRect()
  return {
    x: (clientX - cr.left - panX.value) / zoom.value,
    y: (clientY - cr.top - panY.value) / zoom.value,
  }
}

function findNodesInRect(rx, ry, rw, rh) {
  return nodes.value.filter(n => {
    const nx = n.position.x
    const ny = n.position.y
    // 估算节点高度：header + 可能的面板
    const nodeEl = canvasRef.value?.querySelector(`[data-node-id="${n.id}"]`)
    const nh = nodeEl ? nodeEl.offsetHeight : 80
    return nx < rx + rw && nx + NODE_WIDTH > rx && ny < ry + rh && ny + nh > ry
  }).map(n => n.id)
}

function findEdgesBetweenNodes(nodeIds) {
  const idSet = new Set(nodeIds)
  return edges.value.filter(e => idSet.has(e.source) && idSet.has(e.target)).map(e => e.id)
}

/** 判断一条连线是否属于框选（两端节点都在 selectedNodeIds 中） */
function isEdgeMultiSelected(edge) {
  if (selectedNodeIds.value.length === 0) return false
  const ids = selectedNodeIds.value
  return ids.includes(edge.source) && ids.includes(edge.target)
}

// ─── Pan (middle mouse button) ───
const isPanning = ref(false)
let panStartX = 0
let panStartY = 0
let panStartPanX = 0
let panStartPanY = 0

function onMouseDown(e) {
  // Close context menu on any click
  contextMenu.visible = false
  edgeContextMenu.visible = false

  // Shift + Left button: start selection rectangle
  if (e.button === 0 && e.shiftKey) {
    e.preventDefault()
    const start = screenToCanvas(e.clientX, e.clientY)
    selectionRect.x = start.x
    selectionRect.y = start.y
    selectionRect.w = 0
    selectionRect.h = 0
    selectionRect.visible = true

    // Clear any existing fixed selection
    fixedRectVisible.value = false
    editorStore.setSelectedNodes([])

    const onMove = (ev) => {
      const current = screenToCanvas(ev.clientX, ev.clientY)
      selectionRect.x = Math.min(start.x, current.x)
      selectionRect.y = Math.min(start.y, current.y)
      selectionRect.w = Math.abs(current.x - start.x)
      selectionRect.h = Math.abs(current.y - start.y)
    }

    const onUp = () => {
      selectionRect.visible = false

      // Find nodes inside the selection rectangle
      const hitIds = findNodesInRect(selectionRect.x, selectionRect.y, selectionRect.w, selectionRect.h)
      if (hitIds.length > 0) {
        editorStore.setSelectedNodes(hitIds)
        // Show fixed selection rect
        fixedRectX.value = selectionRect.x
        fixedRectY.value = selectionRect.y
        fixedRectW.value = selectionRect.w
        fixedRectH.value = selectionRect.h
        fixedRectVisible.value = true
        // 标记刚完成框选，阻止后续 click 事件清除
        justFinishedSelection = true
        requestAnimationFrame(() => { justFinishedSelection = false })
      } else {
        fixedRectVisible.value = false
      }

      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    return
  }

  // Click on empty canvas: clear selection
  if (e.button === 0 && !e.shiftKey && fixedRectVisible.value && !justFinishedSelection) {
    // Check if click is outside the fixed selection rect
    const click = screenToCanvas(e.clientX, e.clientY)
    const isInside = click.x >= fixedRectX.value && click.x <= fixedRectX.value + fixedRectW.value
      && click.y >= fixedRectY.value && click.y <= fixedRectY.value + fixedRectH.value
    if (!isInside) {
      fixedRectVisible.value = false
      editorStore.setSelectedNodes([])
    }
  }

  if (e.button !== 1) return // only middle button for pan
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
  // 粘贴态：点击任意位置解除副本选中，选中当前点击节点
  if (justDuplicated) {
    justDuplicated = false
    fixedRectVisible.value = false
    editorStore.setSelectedNodes([])
  }
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

/** 右键点击连线：显示删除菜单 */
function onEdgeContextMenu(svgEvent, edge) {
  // SVG 事件没有 clientX/clientY，需要从原始事件获取
  const e = svgEvent.originalEvent || svgEvent
  const rect = canvasRef.value.getBoundingClientRect()
  edgeContextMenu.x = (e.clientX || e.x) - rect.left
  edgeContextMenu.y = (e.clientY || e.y) - rect.top
  edgeContextMenu.targetEdgeId = edge.id
  edgeContextMenu.visible = true
}

/** 从右键菜单删除连线 */
function deleteEdgeFromMenu() {
  if (!edgeContextMenu.targetEdgeId) return
  chainDataStore.removeEdge(edgeContextMenu.targetEdgeId)
  if (editorStore.selectedEdgeId === edgeContextMenu.targetEdgeId) editorStore.clearSelection()
  edgeContextMenu.visible = false
  edgeContextMenu.targetEdgeId = null
}

function onCanvasClick() {
  // 粘贴态：点击空白解除副本选中
  if (justDuplicated) {
    justDuplicated = false
    fixedRectVisible.value = false
    editorStore.setSelectedNodes([])
    contextMenu.visible = false
    edgeContextMenu.visible = false
    return
  }
  // 如果刚完成框选操作，跳过本次 click（click 在 mouseup 之后触发，会清除刚设置的选中状态）
  if (justFinishedSelection) return
  editorStore.clearSelection()
  fixedRectVisible.value = false
  contextMenu.visible = false
  edgeContextMenu.visible = false
}

// ─── Fixed selection rect drag ───
function onFixedRectDragStart(e) {
  if (e.button !== 0) return
  e.preventDefault()
  e.stopImmediatePropagation() // 阻止 canvas onMouseDown 收到此事件

  const startClient = { x: e.clientX, y: e.clientY }
  const startRect = { x: fixedRectX.value, y: fixedRectY.value }
  const startPositions = {}
  for (const id of selectedNodeIds.value) {
    const n = nodes.value.find(nd => nd.id === id)
    if (n) startPositions[id] = { x: n.position.x, y: n.position.y }
  }

  let rafId = null

  const onMove = (ev) => {
    if (rafId !== null) return
    rafId = requestAnimationFrame(() => {
      rafId = null
      const dx = (ev.clientX - startClient.x) / zoom.value
      const dy = (ev.clientY - startClient.y) / zoom.value

      // Move the fixed rect
      fixedRectX.value = startRect.x + dx
      fixedRectY.value = startRect.y + dy

      // Move all selected nodes via DOM (performance)
      for (const id of selectedNodeIds.value) {
        const sp = startPositions[id]
        if (!sp) continue
        const nodeEl = canvasRef.value?.querySelector(`[data-node-id="${id}"]`)
        if (nodeEl) {
          nodeEl.style.left = (sp.x + dx) + 'px'
          nodeEl.style.top = (sp.y + dy) + 'px'
        }
      }
      // 递增 dragTick 强制连线重算
      dragTick.value++
    })
  }

  const onUp = () => {
    if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null }

    // Write final positions back to store
    for (const id of selectedNodeIds.value) {
      const nodeEl = canvasRef.value?.querySelector(`[data-node-id="${id}"]`)
      if (nodeEl) {
        const left = parseFloat(nodeEl.style.left)
        const top = parseFloat(nodeEl.style.top)
        if (!isNaN(left) && !isNaN(top)) {
          chainDataStore.updateNodePosition(id, left, top)
        }
      }
    }
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }

  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

// ─── Context menu ───
function onContextMenu(e) {
  if (selectedNodeIds.value.length > 0 && fixedRectVisible.value) {
    // Check if right-click is inside the fixed selection rect
    const click = screenToCanvas(e.clientX, e.clientY)
    const isInside = click.x >= fixedRectX.value && click.x <= fixedRectX.value + fixedRectW.value
      && click.y >= fixedRectY.value && click.y <= fixedRectY.value + fixedRectH.value
    if (isInside) {
      e.preventDefault()
      contextMenu.x = e.clientX - canvasRef.value.getBoundingClientRect().left
      contextMenu.y = e.clientY - canvasRef.value.getBoundingClientRect().top
      contextMenu.visible = true
      return
    }
  }
  // Default: clear selection
  fixedRectVisible.value = false
  editorStore.setSelectedNodes([])
}

function onSelectionContextMenu(e) {
  contextMenu.x = e.clientX - canvasRef.value.getBoundingClientRect().left
  contextMenu.y = e.clientY - canvasRef.value.getBoundingClientRect().top
  contextMenu.visible = true
}

function deleteSelectedNodes() {
  const ids = [...selectedNodeIds.value]
  const edgeIds = findEdgesBetweenNodes(ids)
  // Remove edges first, then nodes
  edges.value = edges.value.filter(e => !edgeIds.includes(e.id))
  for (const id of ids) {
    chainDataStore.removeNode(id)
  }
  fixedRectVisible.value = false
  editorStore.setSelectedNodes([])
  contextMenu.visible = false
}

function cancelSelection() {
  fixedRectVisible.value = false
  editorStore.setSelectedNodes([])
  contextMenu.visible = false
}

// ─── Duplicate selected nodes ───
/** 标记：刚完成复制操作，副本处于"粘贴态"，下次点击解除选中 */
let justDuplicated = false

function duplicateSelectedNodes() {
  if (selectedNodeIds.value.length === 0) return
  const OFFSET_X = 40
  const OFFSET_Y = 40
  const newNodeIds = chainDataStore.duplicateNodes(selectedNodeIds.value, OFFSET_X, OFFSET_Y)

  // 更新框选矩形位置到副本区域
  fixedRectX.value += OFFSET_X
  fixedRectY.value += OFFSET_Y

  // 选中新复制的节点
  editorStore.setSelectedNodes(newNodeIds)

  // 标记粘贴态：下次任意点击解除副本选中
  justDuplicated = true
  contextMenu.visible = false
}

function onDrop(event) {
  handleCanvasDrop(event)
}

/** 字段选择器打开事件 — 向上传递给父组件 */
function onOpenFieldPicker(data) {
  emit('openFieldPicker', data)
}

// ─── Edge Transformer Panel State ───
const transformerPanel = reactive({
  visible: false,
  position: { x: 400, y: 200 },
  targetEdgeId: null,
  sourceLabel: '',
  targetLabel: '',
  outputSchema: {},
  inputSchema: {},
})

/** 获取边的表达式文本（显示在连线上方的标记） */
function getExpression(edge) {
  const t = edge.inputTransformer
  if (t?.expression) return t.expression
  return ''
}

/** 点击连线 → 打开边级 Transformer 编辑面板 */
function onEditExpression({ x, y }, edge) {
  transformerPanel.visible = true
  transformerPanel.position = { x, y }
  transformerPanel.targetEdgeId = edge.id

  // 收集源节点信息
  const sourceNode = nodes.value.find(n => n.id === edge.source)
  const targetNode = nodes.value.find(n => n.id === edge.target)
  const sourceType = sourceNode ? nodeTypesStore.getByName(sourceNode.type) : null
  const targetType = targetNode ? nodeTypesStore.getByName(targetNode.type) : null

  transformerPanel.sourceLabel = sourceType?.label || sourceNode?.type || '?'
  transformerPanel.targetLabel = targetType?.label || targetNode?.type || '?'

  // 根据 sourcePort 选择对应的输出 schema
  const sourcePortKey = edge.sourcePort
  const sourceOutputs = sourceType?.outputs || []
  const sourcePortIdx = sourceOutputs.findIndex(p => p.key === sourcePortKey)
  const outputSchemas = sourceType?.output_schemas || []
  transformerPanel.outputSchema = (sourcePortIdx >= 0 && outputSchemas[sourcePortIdx])
    ? outputSchemas[sourcePortIdx]
    : (sourceType?.output_schema || {})

  // 根据 targetPort 选择对应的输入 schema
  const targetPortKey = edge.targetPort
  const targetInputs = targetType?.inputs || []
  const targetPortIdx = targetInputs.findIndex(p => p.key === targetPortKey)
  const inputSchemas = targetType?.input_schemas || []
  transformerPanel.inputSchema = (targetPortIdx >= 0 && inputSchemas[targetPortIdx])
    ? inputSchemas[targetPortIdx]
    : (targetType?.input_schema || {})
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

/* Selection rectangle (during drag) */
.selection-rect {
  position: absolute;
  border: 1.5px dashed #818cf8;
  background: rgba(129, 140, 248, 0.08);
  pointer-events: none;
  z-index: 30;
  border-radius: 3px;
}

/* Fixed selection rectangle (after mouseup) */
.fixed-selection-rect {
  position: absolute;
  border: 1.5px solid #818cf8;
  background: rgba(129, 140, 248, 0.04);
  cursor: grab;
  z-index: 25;
  border-radius: 4px;
  transition: background 0.12s;
}
.fixed-selection-rect:hover {
  background: rgba(129, 140, 248, 0.08);
}
.fixed-selection-rect:active {
  cursor: grabbing;
}

/* Context menu */
.context-menu {
  position: absolute;
  z-index: 100;
  background: #1e1e38;
  border: 1px solid #2d2d50;
  border-radius: 8px;
  padding: 4px;
  min-width: 140px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
}
.context-menu-item {
  padding: 7px 14px;
  font-size: 12px;
  color: #c4c8d4;
  cursor: pointer;
  border-radius: 5px;
  transition: all 0.1s;
}
.context-menu-item:hover {
  background: rgba(99, 102, 241, 0.15);
  color: #e2e8f0;
}
.context-menu-item.danger:hover {
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
}
.context-menu-item.copy:hover {
  background: rgba(34, 197, 94, 0.15);
  color: #4ade80;
}
</style>
