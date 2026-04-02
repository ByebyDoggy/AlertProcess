import { createApp } from 'vue'
import NodeConfigEditor from './components/NodeConfigEditor.vue'
import RuleChainEditor from './components/RuleChainEditor.vue'
import NodePalette from './components/NodePalette.vue'
import RuleChainList from './components/RuleChainList.vue'
import { NODE_TYPES, DEFAULT_NODE_CONFIG } from './config.js'
import { deepClone } from './utils.js'
import apiService from './api-service.js'

// 将配置和工具函数挂载到 window
window.NODE_TYPES = NODE_TYPES
window.DEFAULT_NODE_CONFIG = DEFAULT_NODE_CONFIG
window.getConfigSummary = (node, NODE_TYPES) => {
  if (!node.config) return '未配置'
  
  const typeConfig = NODE_TYPES[node.type]
  if (!typeConfig) return '未配置'

  switch (node.type) {
    case 'detector':
      const option = typeConfig.configFields[0].options.find(
        opt => opt.value === node.config.detectorType
      )
      return option ? option.label.replace(/[⚡🔐💰🔗⛽📅🏷️🏢]/g, '').trim() : node.config.detectorType
    case 'condition':
      return `${node.config.field || '?'} ${node.config.operator || '?'} ${node.config.value || '?'}`
    case 'action':
      return `${node.config.actionType || '?'}: ${node.config.actionValue || '?'}`
    case 'filter':
      return node.config.expression || '未设置'
    case 'notifier':
      return `${node.config.notifierType || '?'}: ${node.config.targetUrl || '?'}`
    case 'scorer':
      const weights = node.config.weights || {}
      return `严重程度:${weights.severity || 1}, 检测器:${weights.detector || 1}`
    default:
      return '已配置'
  }
}
window.getConnectionPointPosition = (node, position) => {
  const rect = { width: 180, height: 60 }
  let x = node.position.x
  let y = node.position.y

  switch (position) {
    case 'top':
      x += rect.width / 2
      break
    case 'bottom':
      x += rect.width / 2
      y += rect.height
      break
    case 'left':
      y += rect.height / 2
      break
    case 'right':
      x += rect.width
      y += rect.height / 2
      break
  }

  return { x, y }
}

const app = createApp({
  components: {
    NodeConfigEditor,
    RuleChainEditor,
    NodePalette,
    RuleChainList
  },
  data() {
    return {
      canvasContainer: null,
      nodes: [],
      edges: [],
      selectedNode: null,
      showConfigModal: false,
      showEdgeModal: false,
      selectedEdge: null,
      pendingEdgeLabel: '',
      saving: false,
      chainName: '',
      chainDescription: '',
      chainEnabled: true,
      currentChain: null,
      ruleChains: []
    }
  },
  mounted() {
    this.fetchRuleChains()
  },
  methods: {
    // 获取规则链列表
    async fetchRuleChains() {
      try {
        const chains = await apiService.getRuleChains()
        this.ruleChains = chains
      } catch (error) {
        console.error('Failed to fetch rule chains:', error)
      }
    },

    // 加载规则链
    loadChain(chain) {
      this.currentChain = chain
      this.chainName = chain.name
      this.chainDescription = chain.description || ''
      this.chainEnabled = chain.enabled
      
      const config = chain.chain_config || {}
      this.nodes = config.nodes || []
      this.edges = config.edges || []
    },

    // 创建新规则链
    createNewChain() {
      this.currentChain = null
      this.chainName = ''
      this.chainDescription = ''
      this.chainEnabled = true
      this.nodes = []
      this.edges = []
    },

    // 清空画布
    clearCanvas() {
      this.nodes = []
      this.edges = []
    },

    // 保存规则链
    async saveChain() {
      if (!this.chainName.trim()) {
        alert('请输入规则链名称')
        return
      }

      this.saving = true
      try {
        const chainData = {
          name: this.chainName,
          description: this.chainDescription,
          enabled: this.chainEnabled,
          nodes: this.nodes.map(node => ({
            id: node.id,
            type: node.type,
            label: node.label,
            config: node.config || {},
            position: node.position
          })),
          edges: this.edges.map(edge => ({
            id: edge.id,
            source: edge.source,
            target: edge.target,
            label: edge.label || ''
          }))
        }

        if (this.currentChain) {
          await apiService.updateRuleChain(this.currentChain.id, chainData)
        } else {
          await apiService.createRuleChain(chainData)
        }

        await this.fetchRuleChains()
        alert('保存成功')
      } catch (error) {
        console.error('Failed to save chain:', error)
        alert('保存失败: ' + error.message)
      } finally {
        this.saving = false
      }
    },

    // 删除规则链
    async deleteChain(chainId) {
      if (!confirm('确定要删除这条规则链吗？')) return
      
      try {
        await apiService.deleteRuleChain(chainId)
        await this.fetchRuleChains()
        if (this.currentChain && this.currentChain.id === chainId) {
          this.createNewChain()
        }
        alert('删除成功')
      } catch (error) {
        console.error('Failed to delete chain:', error)
        alert('删除失败: ' + error.message)
      }
    },

    // 放置节点
    onDrop(event) {
      const type = event.dataTransfer.getData('nodeType')
      const label = event.dataTransfer.getData('nodeLabel')
      
      if (!type || !this.$refs.canvasContainer) return

      const rect = this.$refs.canvasContainer.getBoundingClientRect()
      const x = event.clientX - rect.left - 90
      const y = event.clientY - rect.top - 30

      const newNode = {
        id: `node_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        type: type,
        label: label,
        position: { x: Math.max(0, x), y: Math.max(0, y) },
        config: deepClone(DEFAULT_NODE_CONFIG[type] || {})
      }

      this.nodes.push(newNode)
    },

    // 节点配置
    openNodeConfig(node) {
      this.selectedNode = node
      this.showConfigModal = true
    },

    saveNodeConfig(updatedNode) {
      const index = this.nodes.findIndex(n => n.id === updatedNode.id)
      if (index !== -1) {
        this.nodes[index] = { ...updatedNode }
      }
      this.showConfigModal = false
    },

    // 边配置
    openEdgeConfig(edge) {
      this.selectedEdge = edge
      this.pendingEdgeLabel = edge.label || ''
      this.showEdgeModal = true
    },

    deleteEdge() {
      if (this.selectedEdge) {
        this.edges = this.edges.filter(e => e.id !== this.selectedEdge.id)
        this.showEdgeModal = false
        this.selectedEdge = null
      }
    },

    saveEdgeLabel() {
      if (this.selectedEdge) {
        const edge = this.edges.find(e => e.id === this.selectedEdge.id)
        if (edge) {
          edge.label = this.pendingEdgeLabel
        }
        this.showEdgeModal = false
      }
    },

    // 选择节点
    onNodeSelect(node) {
      this.selectedNode = node
    },

    // 双击节点打开配置
    onNodeDoubleClick(node) {
      this.openNodeConfig(node)
    },

    // 更新节点和边
    updateNodes(newNodes) {
      this.nodes = newNodes
    },

    updateEdges(newEdges) {
      this.edges = newEdges
    }
  }
})

app.mount('#app')
