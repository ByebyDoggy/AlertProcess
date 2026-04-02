import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import apiService from '../api.js'
import { generateId, deepClone } from '../utils.js'
import { DEFAULT_NODE_CONFIG, DEFAULT_NODE_LABELS } from '../config.js'

export const useRuleChainStore = defineStore('ruleChain', () => {
  const chains = ref([])
  const loadingChains = ref(false)

  const currentChainId = ref(null)
  const chainName = ref('')
  const chainDescription = ref('')
  const chainEnabled = ref(true)
  const nodes = ref([])
  const edges = ref([])

  const selectedNodeId = ref(null)
  const selectedEdgeId = ref(null)

  const showNodeConfig = ref(false)
  const showEdgeConfig = ref(false)
  const saving = ref(false)
  const validationErrors = ref([])
  const validationValid = ref(true)

  const selectedNode = computed(() =>
    nodes.value.find(n => n.id === selectedNodeId.value) || null
  )
  const selectedEdge = computed(() =>
    edges.value.find(e => e.id === selectedEdgeId.value) || null
  )
  const isModified = computed(() => {
    if (!currentChainId.value) return nodes.value.length > 0 || edges.value.length > 0
    const chain = chains.value.find(c => c.id === currentChainId.value)
    if (!chain) return true
    const cfg = chain.chain_config || {}
    return (
      chain.name !== chainName.value ||
      chain.description !== chainDescription.value ||
      chain.enabled !== chainEnabled.value ||
      JSON.stringify(cfg.nodes) !== JSON.stringify(nodes.value) ||
      JSON.stringify(cfg.edges) !== JSON.stringify(edges.value)
    )
  })
  const currentChain = computed(() =>
    chains.value.find(c => c.id === currentChainId.value) || null
  )

  // ─── Chain list ───
  async function fetchChains() {
    loadingChains.value = true
    try { chains.value = await apiService.getRuleChains() }
    catch (e) { console.error('Failed to fetch chains:', e) }
    finally { loadingChains.value = false }
  }

  function loadChain(chain) {
    currentChainId.value = chain.id
    chainName.value = chain.name
    chainDescription.value = chain.description || ''
    chainEnabled.value = chain.enabled
    const cfg = chain.chain_config || {}
    nodes.value = deepClone(cfg.nodes || [])
    edges.value = deepClone(cfg.edges || [])
    selectedNodeId.value = null
    selectedEdgeId.value = null
    validationErrors.value = []
  }

  function createNew() {
    currentChainId.value = null
    chainName.value = ''
    chainDescription.value = ''
    chainEnabled.value = true
    nodes.value = []
    edges.value = []
    selectedNodeId.value = null
    selectedEdgeId.value = null
    validationErrors.value = []
  }

  // ─── Node operations ───
  function addNode(type, label, x, y) {
    const node = {
      id: generateId('node'),
      type,
      label: label || DEFAULT_NODE_LABELS[type] || type,
      config: deepClone(DEFAULT_NODE_CONFIG[type] || {}),
      position: { x: Math.max(0, x), y: Math.max(0, y) },
    }
    nodes.value.push(node)
    return node
  }

  function removeNode(nodeId) {
    nodes.value = nodes.value.filter(n => n.id !== nodeId)
    edges.value = edges.value.filter(e => e.source !== nodeId && e.target !== nodeId)
    if (selectedNodeId.value === nodeId) {
      selectedNodeId.value = null
      showNodeConfig.value = false
    }
  }

  function updateNode(nodeId, updates) {
    const idx = nodes.value.findIndex(n => n.id === nodeId)
    if (idx !== -1) nodes.value[idx] = { ...nodes.value[idx], ...updates }
  }

  function updateNodeConfig(nodeId, config) {
    const idx = nodes.value.findIndex(n => n.id === nodeId)
    if (idx !== -1) nodes.value[idx] = { ...nodes.value[idx], config: { ...config } }
  }

  // ─── Edge operations (with port support) ───
  function addEdge(sourceId, sourcePort, targetId, targetPort = 'input') {
    const exists = edges.value.some(e =>
      e.source === sourceId && e.target === targetId && e.sourcePort === sourcePort
    )
    if (exists) return null
    const edge = {
      id: generateId('edge'),
      source: sourceId,
      sourcePort: sourcePort || 'output',
      target: targetId,
      targetPort: targetPort || 'input',
      label: '',
    }
    edges.value.push(edge)
    return edge
  }

  function removeEdge(edgeId) {
    edges.value = edges.value.filter(e => e.id !== edgeId)
    if (selectedEdgeId.value === edgeId) {
      selectedEdgeId.value = null
      showEdgeConfig.value = false
    }
  }

  function updateEdge(edgeId, updates) {
    const idx = edges.value.findIndex(e => e.id === edgeId)
    if (idx !== -1) edges.value[idx] = { ...edges.value[idx], ...updates }
  }

  // ─── Selection ───
  function selectNode(nodeId) {
    selectedNodeId.value = nodeId
    selectedEdgeId.value = null
    showEdgeConfig.value = false
  }
  function selectEdge(edgeId) {
    selectedEdgeId.value = edgeId
    selectedNodeId.value = null
    showNodeConfig.value = false
  }
  function clearSelection() {
    selectedNodeId.value = null
    selectedEdgeId.value = null
  }
  function openNodeConfig(nodeId) { selectedNodeId.value = nodeId; showNodeConfig.value = true }
  function closeNodeConfig() { showNodeConfig.value = false }
  function openEdgeConfig(edgeId) { selectedEdgeId.value = edgeId; showEdgeConfig.value = true }
  function closeEdgeConfig() { showEdgeConfig.value = false }

  // ─── Canvas ───
  function moveNode(nodeId, x, y) {
    const node = nodes.value.find(n => n.id === nodeId)
    if (node) { node.position.x = Math.max(0, x); node.position.y = Math.max(0, y) }
  }
  function clearCanvas() {
    nodes.value = []; edges.value = []
    selectedNodeId.value = null; selectedEdgeId.value = null
  }

  // ─── Persistence ───
  async function validate() {
    try {
      const result = await apiService.validateChain(nodes.value, edges.value)
      validationValid.value = result.valid
      validationErrors.value = result.errors || []
      return result
    } catch (e) {
      validationValid.value = false
      validationErrors.value = [e.message]
      return { valid: false, errors: [e.message] }
    }
  }

  async function save() {
    if (!chainName.value.trim()) throw new Error('请输入规则链名称')
    saving.value = true
    try {
      const data = {
        name: chainName.value,
        description: chainDescription.value,
        enabled: chainEnabled.value,
        nodes: nodes.value,
        edges: edges.value,
      }
      let result
      if (currentChainId.value) {
        result = await apiService.updateRuleChain(currentChainId.value, data)
      } else {
        result = await apiService.createRuleChain(data)
      }
      currentChainId.value = result.id
      await fetchChains()
      return result
    } finally { saving.value = false }
  }

  async function deleteChain(chainId) {
    await apiService.deleteChain(chainId)
    if (currentChainId.value === chainId) createNew()
    await fetchChains()
  }

  return {
    chains, loadingChains,
    currentChainId, chainName, chainDescription, chainEnabled,
    nodes, edges,
    selectedNodeId, selectedEdgeId,
    showNodeConfig, showEdgeConfig,
    saving, validationErrors, validationValid,
    selectedNode, selectedEdge, isModified, currentChain,
    fetchChains, loadChain, createNew,
    addNode, removeNode, updateNode, updateNodeConfig,
    addEdge, removeEdge, updateEdge,
    selectNode, selectEdge, clearSelection,
    openNodeConfig, closeNodeConfig, openEdgeConfig, closeEdgeConfig,
    validate, save, deleteChain, moveNode, clearCanvas,
  }
})
