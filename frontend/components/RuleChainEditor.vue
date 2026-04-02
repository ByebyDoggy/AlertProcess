<template>
  <div class="flex-1 canvas-area relative overflow-hidden" ref="canvasContainer"
       @mousemove="onCanvasMouseMove" @mouseup="onCanvasMouseUp"
       @drop="onDrop" @dragover.prevent>
    <svg class="absolute inset-0 w-full h-full pointer-events-none" style="z-index: 0;">
      <defs>
        <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
          <polygon points="0 0, 10 3.5, 0 7" fill="#6366f1"/>
        </marker>
      </defs>
      <g v-for="edge in edges" :key="edge.id" @click.stop="selectEdge(edge)" class="pointer-events-auto">
        <path :d="getEdgePath(edge)" class="edge-line" 
              marker-end="url(#arrowhead)"
              :class="{ 'ring-2 ring-blue-500': selectedEdge && selectedEdge.id === edge.id }"/>
      </g>
      <path v-if="tempEdge" :d="tempEdge.path" class="temp-edge" pointer-events="none"/>
    </svg>
    
    <div v-for="node in nodes" :key="node.id"
         :class="{'selected': selectedNode && selectedNode.id === node.id}"
         :data-node-id="node.id"
         class="node-card absolute bg-gray-800 rounded-xl p-4 border border-gray-600 shadow-lg min-w-[180px]"
         :style="{ left: node.position.x + 'px', top: node.position.y + 'px' }"
         @mousedown="onNodeMouseDown($event, node)"
         @click.stop="selectNode(node)"
         @dblclick.stop="$emit('node-dblclick', node)">
      <!-- 顶部连接点 -->
      <div class="connection-point" style="top: -6px; left: 50%; transform: translateX(-50%);" 
           @mousedown.stop="onConnectionPointStart($event, node, 'top')"></div>
      <!-- 底部连接点 -->
      <div class="connection-point" style="bottom: -6px; left: 50%; transform: translateX(-50%);" 
           @mousedown.stop="onConnectionPointStart($event, node, 'bottom')"></div>
      <!-- 左侧连接点 -->
      <div class="connection-point" style="left: -6px; top: 50%; transform: translateY(-50%);" 
           @mousedown.stop="onConnectionPointStart($event, node, 'left')"></div>
      <!-- 右侧连接点 -->
      <div class="connection-point" style="right: -6px; top: 50%; transform: translateY(-50%);" 
           @mousedown.stop="onConnectionPointStart($event, node, 'right')"></div>
      
      <div class="flex items-center gap-2 mb-2">
        <span :class="NODE_TYPES[node.type]?.iconColor || 'text-gray-400'" class="text-xl">
          {{ NODE_TYPES[node.type]?.icon || '📦' }}
        </span>
        <span class="font-medium text-white text-sm">{{ node.label }}</span>
      </div>
      <div class="text-xs text-gray-400">
        {{ NODE_TYPES[node.type]?.label || node.type }}
      </div>
      <div v-if="node.config" class="text-xs text-blue-400 mt-1 truncate">
        {{ window.getConfigSummary(node, NODE_TYPES) }}
      </div>
      <button @click.stop="deleteNode(node.id)" 
              class="absolute -top-2 -right-2 w-6 h-6 bg-red-500 hover:bg-red-600 rounded-full text-white text-sm flex items-center justify-center">×</button>
    </div>

    <div v-if="nodes.length === 0" class="absolute inset-0 flex items-center justify-center pointer-events-none">
      <div class="text-center text-gray-500">
        <div class="text-4xl mb-2">📋</div>
        <div>从左侧拖拽节点到此处开始配置规则链</div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'RuleChainEditor',
  props: {
    nodes: {
      type: Array,
      default: () => []
    },
    edges: {
      type: Array,
      default: () => []
    }
  },
  emits: ['update:nodes', 'update:edges', 'node-select', 'edge-select', 'node-dblclick', 'drop'],
  data() {
    return {
      canvasContainer: null,
      selectedNode: null,
      selectedEdge: null,
      isDragging: false,
      isConnecting: false,
      dragNode: null,
      dragOffset: { x: 0, y: 0 },
      connectionStart: null,
      tempEdge: null,
      NODE_TYPES: window.NODE_TYPES
    }
  },
  mounted() {
    this.canvasContainer = this.$refs.canvasContainer
  },
  methods: {
    onNodeMouseDown(event, node) {
      if (event.target.tagName === 'BUTTON') return
      
      this.isDragging = true
      this.dragNode = node
      this.selectedNode = node
      this.$emit('node-select', node)
      
      const rect = event.target.closest('.node-card').getBoundingClientRect()
      this.dragOffset.x = event.clientX - rect.left
      this.dragOffset.y = event.clientY - rect.top

      const onMouseMove = (e) => {
        if (!this.isDragging || !this.dragNode || !this.canvasContainer) return
        
        const canvasRect = this.canvasContainer.getBoundingClientRect()
        const newX = e.clientX - canvasRect.left - this.dragOffset.x
        const newY = e.clientY - canvasRect.top - this.dragOffset.y
        
        this.dragNode.position = {
          x: Math.max(0, newX),
          y: Math.max(0, newY)
        }
      }

      const onMouseUp = () => {
        this.isDragging = false
        this.dragNode = null
        document.removeEventListener('mousemove', onMouseMove)
        document.removeEventListener('mouseup', onMouseUp)
      }

      document.addEventListener('mousemove', onMouseMove)
      document.addEventListener('mouseup', onMouseUp)
    },

    onCanvasMouseMove(event) {
      if (!this.isConnecting || !this.connectionStart || !this.canvasContainer) return

      const rect = this.canvasContainer.getBoundingClientRect()
      const mouseX = event.clientX - rect.left
      const mouseY = event.clientY - rect.top

      const startNode = this.nodes.find(n => n.id === this.connectionStart.nodeId)
      if (!startNode) return

      const startPos = window.getConnectionPointPosition(startNode, this.connectionStart.position)
      this.tempEdge = {
        path: `M ${startPos.x} ${startPos.y} L ${mouseX} ${mouseY}`
      }
    },

    onCanvasMouseUp(event) {
      if (this.isConnecting) {
        const target = event.target.closest('.node-card')
        if (target) {
          const nodeId = target.dataset?.nodeId
          if (nodeId && nodeId !== this.connectionStart?.nodeId) {
            this.finishConnection(nodeId)
          }
        }
        
        this.isConnecting = false
        this.connectionStart = null
        this.tempEdge = null
      }
    },

    onConnectionPointStart(event, node, position) {
      event.preventDefault()
      event.stopPropagation()
      this.isConnecting = true
      this.connectionStart = { nodeId: node.id, position }
      this.tempEdge = null
    },

    finishConnection(targetNodeId) {
      if (!this.connectionStart || this.connectionStart.nodeId === targetNodeId) return

      const sourceNodeId = this.connectionStart.nodeId
      
      const edge = {
        id: `edge_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        source: sourceNodeId,
        target: targetNodeId,
        label: ''
      }

      const newEdges = [...this.edges, edge]
      this.$emit('update:edges', newEdges)
      
      this.isConnecting = false
      this.connectionStart = null
      this.tempEdge = null
    },

    selectNode(node) {
      this.selectedNode = node
      this.$emit('node-select', node)
    },

    selectEdge(edge) {
      this.selectedEdge = edge
      this.$emit('edge-select', edge)
    },

    deleteNode(nodeId) {
      const newNodes = this.nodes.filter(n => n.id !== nodeId)
      const newEdges = this.edges.filter(e => e.source !== nodeId && e.target !== nodeId)
      this.$emit('update:nodes', newNodes)
      this.$emit('update:edges', newEdges)
      
      if (this.selectedNode && this.selectedNode.id === nodeId) {
        this.selectedNode = null
      }
    },

    getEdgePath(edge) {
      const sourceNode = this.nodes.find(n => n.id === edge.source)
      const targetNode = this.nodes.find(n => n.id === edge.target)
      
      if (!sourceNode || !targetNode) return ''

      const sx = sourceNode.position.x + 90
      const sy = sourceNode.position.y + 30
      const tx = targetNode.position.x + 90
      const ty = targetNode.position.y

      const midY = (sy + ty) / 2
      return `M ${sx} ${sy} C ${sx} ${midY}, ${tx} ${midY}, ${tx} ${ty}`
    },

    onDrop(event) {
      this.$emit('drop', event)
    }
  }
}
</script>

<style scoped>
.canvas-area {
  background-image: radial-gradient(circle, #374151 1px, transparent 1px);
  background-size: 20px 20px;
}

.node-card {
  cursor: move;
  user-select: none;
  transition: box-shadow 0.2s, transform 0.2s;
}

.node-card:hover {
  box-shadow: 0 8px 25px rgba(0,0,0,0.3);
  transform: scale(1.02);
}

.node-card.selected {
  box-shadow: 0 0 0 3px #3b82f6;
}

.edge-line {
  stroke: #6366f1;
  stroke-width: 2;
  fill: none;
  cursor: pointer;
}

.edge-line:hover {
  stroke: #818cf8;
  stroke-width: 3;
}

.connection-point {
  width: 12px;
  height: 12px;
  background: #3b82f6;
  border: 2px solid white;
  border-radius: 50%;
  position: absolute;
  cursor: crosshair;
  opacity: 0;
  transition: opacity 0.2s;
}

.node-card:hover .connection-point {
  opacity: 1;
}

.connection-point:hover {
  transform: scale(1.3);
  background: #60a5fa;
}

.temp-edge {
  stroke: #3b82f6;
  stroke-width: 2;
  stroke-dasharray: 5,5;
  fill: none;
}
</style>
