<template>
  <div ref="canvasRef" class="flex-1 canvas-area relative overflow-hidden"
    @mousemove="onMouseMove" @mouseup="onMouseUp" @drop="onDrop" @dragover.prevent @click.self="onCanvasClick">

    <!-- SVG Layer: edges -->
    <svg class="absolute inset-0 w-full h-full" style="z-index: 1; pointer-events: none;">
      <defs>
        <marker id="arrow-default" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="#4a4a7a" />
        </marker>
        <marker id="arrow-selected" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="#f59e0b" />
        </marker>
        <marker id="arrow-true" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="#10b981" />
        </marker>
        <marker id="arrow-false" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="#ef4444" />
        </marker>
      </defs>

      <!-- Existing edges -->
      <g v-for="edge in edges" :key="edge.id" style="pointer-events: auto; cursor: pointer;"
        @click.stop="onEdgeClick(edge)">
        <path :d="edgePath(edge)"
          :class="['edge-path', edgeClass(edge)]"
          :marker-end="arrowMarker(edge)" />
        <!-- Edge label -->
        <g v-if="edgeLabel(edge)" :transform="`translate(${edgeMidpoint(edge).x}, ${edgeMidpoint(edge).y})`">
          <rect x="-16" y="-9" width="32" height="18" class="edge-label-bg" />
          <text text-anchor="middle" dy="4" class="edge-label-text">{{ edgeLabel(edge) }}</text>
        </g>
      </g>

      <!-- Temp connection line -->
      <path v-if="connecting && tempLine" :d="tempLine" class="temp-edge-path" />
    </svg>

    <!-- DOM Layer: nodes -->
    <div v-for="node in nodes" :key="node.id"
      :class="['n8n-node', selectedNodeId === node.id ? 'selected' : '']"
      :style="{ left: node.position.x + 'px', top: node.position.y + 'px', zIndex: draggingNodeId === node.id ? 20 : 10 }"
      :data-node-id="node.id"
      @mousedown.stop="onNodeMouseDown($event, node)"
      @click.stop="onNodeClick(node)"
      @dblclick.stop="$emit('nodeDblClick', node)">

      <!-- Delete button -->
      <div class="node-delete-btn" @click.stop="$emit('deleteNode', node.id)">&times;</div>

      <!-- Header -->
      <div class="node-header" :style="{ background: nodeHeaderBg(node.type) }">
        <div class="node-header-icon">{{ nodeIcon(node.type) }}</div>
        <span class="node-header-label">{{ node.label }}</span>
        <span class="node-type-badge">{{ nodeType(node.type) }}</span>
      </div>

      <!-- Ports section -->
      <div style="padding: 6px 0;">
        <!-- Input ports -->
        <template v-if="hasInputs(node.type)">
          <div class="port-row input-row">
            <div class="port-dot input-port"
              :style="{ color: portColor('input'), background: isPortConnected(node.id, 'input') ? portColor('input') : '#2d2d50' }"
              @mousedown.stop="onPortMouseDown($event, node, 'input', 'left')"></div>
            <span class="port-label">输入</span>
          </div>
        </template>

        <!-- Output ports -->
        <div v-for="(port, idx) in nodeOutputs(node)" :key="port.key"
          class="port-row output-row">
          <span class="port-label">{{ port.label }}</span>
          <div class="port-dot output-port"
            :style="{ color: port.color, background: isPortConnected(node.id, port.key) ? port.color : '#2d2d50' }"
            @mousedown.stop="onPortMouseDown($event, node, port.key, 'right')"></div>
        </div>
      </div>

      <!-- Body: config summary -->
      <div v-if="configSummary(node)" class="node-body" style="border-top: 1px solid rgba(255,255,255,0.04);">
        {{ configSummary(node) }}
      </div>

      <!-- Output variables hint -->
      <div v-if="nodeVars(node.type).length > 0" class="node-status" style="color: #6366f1;">
        <span class="var-tag" v-for="v in nodeVars(node.type).slice(0, 3)" :key="v.key" style="margin-right: 3px;">
          {{ v.key }}
        </span>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="nodes.length === 0" class="absolute inset-0 flex items-center justify-center" style="z-index: 0;">
      <div class="empty-canvas-hint">
        <div class="empty-canvas-icon">&#x1F517;</div>
        <div style="color: #6b7280; font-size: 14px; font-weight: 500;">拖拽节点到此处开始构建规则链</div>
        <div style="color: #4a4a7a; font-size: 12px; margin-top: 6px;">
          从左侧面板拖入 入口触发器 作为起点
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { NODE_TYPES } from '../config.js'
import { getConfigSummary, getNodeOutputs, getPortPosition, getEdgePath, getEdgeMidpoint } from '../utils.js'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
  selectedNodeId: { type: String, default: null },
  selectedEdgeId: { type: String, default: null },
})
const emit = defineEmits(['dropNew', 'nodeClick', 'edgeClick', 'nodeDblClick', 'deleteNode', 'addEdge', 'moveNode', 'canvasClick'])

const canvasRef = ref(null)
const draggingNodeId = ref(null)
const dragOffset = ref({ x: 0, y: 0 })
const connecting = ref(false)
const connSource = ref(null) // { nodeId, portKey, side }
const tempLine = ref('')

// ─── Helpers ───
function nodeIcon(type) { return NODE_TYPES[type]?.icon || '?' }
function nodeType(type) { return NODE_TYPES[type]?.label || type }
function configSummary(node) { return getConfigSummary(node, NODE_TYPES) }
function nodeOutputs(node) { return getNodeOutputs(node.type, node.config) }
function nodeVars(type) { return NODE_TYPES[type]?.variables || [] }
function hasInputs(type) { return type !== 'trigger' }
function nodeHeaderBg(type) { return NODE_TYPES[type]?.lightBg || 'rgba(99,102,241,0.12)' }
function portColor(key) {
  const colors = { input: '#6366f1', output: '#6366f1', true: '#10b981', false: '#ef4444' }
  return colors[key] || '#6b7280'
}

function isPortConnected(nodeId, portKey) {
  return props.edges.some(e => {
    if (portKey === 'input') return e.target === nodeId && e.targetPort === 'input'
    return e.source === nodeId && e.sourcePort === portKey
  })
}

// ─── Edge rendering ───
function edgePath(edge) {
  const src = props.nodes.find(n => n.id === edge.source)
  const tgt = props.nodes.find(n => n.id === edge.target)
  if (!src || !tgt) return ''
  const srcOutputs = getNodeOutputs(src.type, src.config)
  const srcIdx = srcOutputs.findIndex(p => p.key === (edge.sourcePort || 'output'))
  const from = getPortPosition(src, edge.sourcePort || 'output', 'right', Math.max(0, srcIdx))
  const to = getPortPosition(tgt, edge.targetPort || 'input', 'left', 0)
  return getEdgePath(from, to)
}

function edgeMidpoint(edge) {
  const src = props.nodes.find(n => n.id === edge.source)
  const tgt = props.nodes.find(n => n.id === edge.target)
  if (!src || !tgt) return { x: 0, y: 0 }
  const srcOutputs = getNodeOutputs(src.type, src.config)
  const srcIdx = srcOutputs.findIndex(p => p.key === (edge.sourcePort || 'output'))
  const from = getPortPosition(src, edge.sourcePort || 'output', 'right', Math.max(0, srcIdx))
  const to = getPortPosition(tgt, edge.targetPort || 'input', 'left', 0)
  return getEdgeMidpoint(from, to)
}

function edgeClass(edge) {
  const cls = []
  if (props.selectedEdgeId === edge.id) cls.push('selected')
  if (edge.sourcePort === 'true' || edge.label?.toLowerCase() === 'true') cls.push('edge-true')
  else if (edge.sourcePort === 'false' || edge.label?.toLowerCase() === 'false') cls.push('edge-false')
  return cls
}

function edgeLabel(edge) {
  if (edge.sourcePort === 'true') return '是'
  if (edge.sourcePort === 'false') return '否'
  if (edge.label) return edge.label
  return ''
}

function arrowMarker(edge) {
  if (props.selectedEdgeId === edge.id) return 'url(#arrow-selected)'
  if (edge.sourcePort === 'true' || edge.label?.toLowerCase() === 'true') return 'url(#arrow-true)'
  if (edge.sourcePort === 'false' || edge.label?.toLowerCase() === 'false') return 'url(#arrow-false)'
  return 'url(#arrow-default)'
}

// ─── Node dragging ───
function onNodeMouseDown(event, node) {
  if (event.target.closest('.port-dot')) return
  if (event.target.closest('.node-delete-btn')) return
  draggingNodeId.value = node.id
  emit('nodeClick', node.id)
  const rect = event.target.closest('.n8n-node').getBoundingClientRect()
  dragOffset.value = { x: event.clientX - rect.left, y: event.clientY - rect.top }
  const onMove = (e) => {
    if (!draggingNodeId.value || !canvasRef.value) return
    const cr = canvasRef.value.getBoundingClientRect()
    emit('moveNode', draggingNodeId.value, e.clientX - cr.left - dragOffset.value.x, e.clientY - cr.top - dragOffset.value.y)
  }
  const onUp = () => {
    draggingNodeId.value = null
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

function onNodeClick(node) { emit('nodeClick', node.id) }

// ─── Port connection ───
function onPortMouseDown(event, node, portKey, side) {
  event.preventDefault()
  event.stopPropagation()
  connecting.value = true
  connSource.value = { nodeId: node.id, portKey, side }
  tempLine.value = ''
}

function onMouseMove(event) {
  if (!connecting.value || !connSource.value || !canvasRef.value) return
  const src = props.nodes.find(n => n.id === connSource.value.nodeId)
  if (!src) return
  const cr = canvasRef.value.getBoundingClientRect()
  const mx = event.clientX - cr.left, my = event.clientY - cr.top

  if (connSource.value.side === 'right') {
    const outputs = getNodeOutputs(src.type, src.config)
    const idx = outputs.findIndex(p => p.key === connSource.value.portKey)
    const from = getPortPosition(src, connSource.value.portKey, 'right', Math.max(0, idx))
    tempLine.value = getEdgePath(from, { x: mx, y: my })
  } else {
    const from = getPortPosition(src, connSource.value.portKey, 'left', 0)
    tempLine.value = getEdgePath({ x: mx, y: my }, from)
  }
}

function onMouseUp(event) {
  if (!connecting.value || !connSource.value) return
  // Check if dropped on a port dot
  const targetPort = event.target.closest('.port-dot')
  if (targetPort) {
    const targetNode = targetPort.closest('.n8n-node')
    const targetId = targetNode?.dataset?.nodeId
    if (targetId && targetId !== connSource.value.nodeId) {
      // Determine source/target ports
      const isTargetInput = targetPort.classList.contains('input-port')
      const isSourceOutput = connSource.value.side === 'right'
      const isSourceInput = connSource.value.side === 'left'

      let sourceId, sourcePort, targetNodeId, targetPortKey
      if (isSourceOutput && isTargetInput) {
        sourceId = connSource.value.nodeId
        sourcePort = connSource.value.portKey
        targetNodeId = targetId
        targetPortKey = 'input'
      } else if (isSourceInput && !isTargetInput) {
        // reverse: from target output to source input
        sourceId = targetId
        sourcePort = connSource.value.portKey // this is the target port key
        targetNodeId = connSource.value.nodeId
        targetPortKey = 'input'
      } else {
        // output -> output or input -> input: try to figure it out
        if (isSourceOutput) {
          sourceId = connSource.value.nodeId
          sourcePort = connSource.value.portKey
          targetNodeId = targetId
          targetPortKey = 'input'
        } else {
          sourceId = targetId
          sourcePort = connSource.value.portKey
          targetNodeId = connSource.value.nodeId
          targetPortKey = 'input'
        }
      }
      emit('addEdge', sourceId, sourcePort, targetNodeId, targetPortKey)
    }
  }
  connecting.value = false
  connSource.value = null
  tempLine.value = ''
}

function onEdgeClick(edge) { emit('edgeClick', edge.id) }
function onCanvasClick() { emit('canvasClick') }

function onDrop(event) {
  const type = event.dataTransfer.getData('nodeType')
  const label = event.dataTransfer.getData('nodeLabel')
  if (!type || !canvasRef.value) return
  const rect = canvasRef.value.getBoundingClientRect()
  emit('dropNew', type, label, Math.max(0, event.clientX - rect.left - 115), Math.max(0, event.clientY - rect.top - 40))
}
</script>
