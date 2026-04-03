import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { generateId, deepClone } from '../utils/helpers.js'
import * as chainApi from '../api/ruleChain.js'
import { useNodeTypesStore } from './nodeTypes.js'

export const useChainDataStore = defineStore('chainData', () => {
  const chains = ref([])
  const loadingChains = ref(false)

  const currentChainId = ref(null)
  const chainName = ref('')
  const chainDescription = ref('')
  const chainEnabled = ref(true)
  const nodes = ref([])
  const edges = ref([])

  // 脏标记：避免 isModified 每次 JSON.stringify
  const _dirty = ref(false)
  function markDirty() { _dirty.value = true }

  const currentChain = computed(() =>
    chains.value.find(c => c.id === currentChainId.value) || null
  )

  const isModified = computed(() => {
    if (_dirty.value) return true
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

  // ─── Chain list ───
  async function fetchChains() {
    loadingChains.value = true
    try {
      chains.value = await chainApi.getRuleChains()
    } catch (e) {
      console.error('Failed to fetch chains:', e)
    } finally {
      loadingChains.value = false
    }
  }

  function loadChain(chain) {
    currentChainId.value = chain.id
    chainName.value = chain.name
    chainDescription.value = chain.description || ''
    chainEnabled.value = chain.enabled
    const cfg = chain.chain_config || {}
    nodes.value = deepClone(cfg.nodes || [])
    edges.value = deepClone(cfg.edges || [])
    _dirty.value = false
  }

  function createNew() {
    currentChainId.value = null
    chainName.value = ''
    chainDescription.value = ''
    chainEnabled.value = true
    nodes.value = []
    edges.value = []
  }

  // ─── Node operations ───
  function addNode(nodeTypeName, x, y) {
    const nodeTypesStore = useNodeTypesStore()
    const nodeType = nodeTypesStore.getByName(nodeTypeName)
    const label = nodeType?.label || nodeTypeName
    const defaultConfig = nodeType?.default_config || {}

    const node = {
      id: generateId('node'),
      type: nodeTypeName,
      label,
      config: deepClone(defaultConfig),
      position: { x: Math.max(0, x), y: Math.max(0, y) },
    }

    // 多输入端口：初始化 inputPorts 列表
    const multiInputs = (nodeType?.inputs || []).filter(p => p.multi)
    if (multiInputs.length > 0) {
      // 默认使用类型定义中的端口
      const definedPorts = nodeType.inputs.filter(p => p.key.startsWith('input_')).map(p => p.key)
      node.config.inputPorts = definedPorts.length > 0 ? [...definedPorts] : ['input_0']
    }

    nodes.value.push(node)
    markDirty()
    return node
  }

  function removeNode(nodeId) {
    nodes.value = nodes.value.filter(n => n.id !== nodeId)
    edges.value = edges.value.filter(e => e.source !== nodeId && e.target !== nodeId)
    markDirty()
  }

  function updateNode(nodeId, updates) {
    const idx = nodes.value.findIndex(n => n.id === nodeId)
    if (idx !== -1) nodes.value[idx] = { ...nodes.value[idx], ...updates }
    markDirty()
  }

  function updateNodeConfig(nodeId, config) {
    const idx = nodes.value.findIndex(n => n.id === nodeId)
    if (idx !== -1) nodes.value[idx] = { ...nodes.value[idx], config: { ...config } }
    markDirty()
  }

  /** 仅更新节点位置（拖拽结束时调用，精确触发一次响应式更新） */
  function updateNodePosition(nodeId, x, y) {
    const idx = nodes.value.findIndex(n => n.id === nodeId)
    if (idx !== -1) {
      nodes.value[idx] = { ...nodes.value[idx], position: { x, y } }
      markDirty()
    }
  }

  // ─── Edge operations ───
  function addEdge(sourceId, sourcePort, targetId, targetPort) {
    // 去重检查：同一源到同一目标端口
    const exists = edges.value.some(e =>
      e.target === targetId && e.targetPort === targetPort
    )
    if (exists) return null

    const edge = {
      id: generateId('edge'),
      source: sourceId,
      sourcePort: sourcePort || 'output',
      target: targetId,
      targetPort: targetPort || 'input_0',
      label: '',
    }
    edges.value.push(edge)
    markDirty()
    return edge
  }

  function removeEdge(edgeId) {
    edges.value = edges.value.filter(e => e.id !== edgeId)
    markDirty()
  }

  function updateEdge(edgeId, updates) {
    const idx = edges.value.findIndex(e => e.id === edgeId)
    if (idx !== -1) edges.value[idx] = { ...edges.value[idx], ...updates }
    markDirty()
  }

  // ─── Persistence ───
  async function save() {
    if (!chainName.value.trim()) throw new Error('请输入规则链名称')
    const data = {
      name: chainName.value,
      description: chainDescription.value,
      enabled: chainEnabled.value,
      nodes: nodes.value,
      edges: edges.value,
    }
    let result
    if (currentChainId.value) {
      result = await chainApi.updateRuleChain(currentChainId.value, data)
    } else {
      result = await chainApi.createRuleChain(data)
    }
    currentChainId.value = result.id
    _dirty.value = false
    await fetchChains()
    return result
  }

  async function deleteChain(chainId) {
    await chainApi.deleteRuleChain(chainId)
    if (currentChainId.value === chainId) createNew()
    await fetchChains()
  }

  function clearCanvas() {
    nodes.value = []
    edges.value = []
  }

  return {
    chains, loadingChains,
    currentChainId, chainName, chainDescription, chainEnabled,
    nodes, edges,
    currentChain, isModified,
    fetchChains, loadChain, createNew,
    addNode, removeNode, updateNode, updateNodeConfig, updateNodePosition,
    addEdge, removeEdge, updateEdge,
    save, deleteChain, clearCanvas,
  }
})
