import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { generateId, deepClone } from '../utils/helpers.js'
import * as chainApi from '../api/ruleChain.js'
import { useNodeTypesStore } from './nodeTypes.js'
import { useTabStore } from './tabStore.js'

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
    chainEnabled.value = false
    nodes.value = []
    edges.value = []
  }

  // ─── 多标签页数据同步 ───
  /**
   * 将当前编辑数据保存到 tabStore 的活跃标签页快照中
   * 在切换标签页或关闭标签页之前调用
   */
  function saveToTab() {
    const tabStore = useTabStore()
    const tab = tabStore.activeTab
    if (!tab) return
    tabStore.updateTabData(tab.id, {
      name: chainName.value,
      description: chainDescription.value,
      enabled: chainEnabled.value,
      nodes: deepClone(nodes.value),
      edges: deepClone(edges.value),
      nodeTestResults: deepClone(nodeTestResults.value),
      nodeTestInputs: deepClone(nodeTestInputs.value),
      isModified: isModified.value,
      viewport: {
        zoom: _editorZoomSnapshot,
        panX: _editorPanXSnapshot,
        panY: _editorPanYSnapshot,
      },
    })
  }

  /** 视口快照（由 RuleChainEditor 在切换前写入） */
  let _editorZoomSnapshot = 1
  let _editorPanXSnapshot = 0
  let _editorPanYSnapshot = 0

  function setViewportSnapshot(zoom, panX, panY) {
    _editorZoomSnapshot = zoom
    _editorPanXSnapshot = panX
    _editorPanYSnapshot = panY
  }

  /**
   * 从 tabStore 标签页快照恢复编辑数据到当前 store
   * 在切换到新标签页之后调用
   */
  function restoreFromTab(tab) {
    if (!tab) {
      createNew()
      return
    }
    currentChainId.value = tab.chainId
    chainName.value = tab.name
    chainDescription.value = tab.description || ''
    chainEnabled.value = tab.enabled !== false
    nodes.value = deepClone(tab.nodes || [])
    edges.value = deepClone(tab.edges || [])
    nodeTestResults.value = deepClone(tab.nodeTestResults || {})
    nodeTestInputs.value = deepClone(tab.nodeTestInputs || {})
    _dirty.value = false
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

  /**
   * 复制一组节点及其内部连线，返回新节点 ID 列表。
   * @param {string[]} nodeIds - 要复制的节点 ID
   * @param {number} offsetX - x 轴偏移
   * @param {number} offsetY - y 轴偏移
   * @returns {string[]} 新节点 ID 列表
   */
  function duplicateNodes(nodeIds, offsetX = 40, offsetY = 40) {
    const idMap = {} // oldId → newId
    const newNodes = []
    const idSet = new Set(nodeIds)

    // 1. 复制节点
    for (const id of nodeIds) {
      const src = nodes.value.find(n => n.id === id)
      if (!src) continue
      const newId = generateId('node')
      idMap[id] = newId
      newNodes.push({
        ...deepClone(src),
        id: newId,
        position: {
          x: src.position.x + offsetX,
          y: src.position.y + offsetY,
        },
      })
    }

    // 2. 复制内部连线（两端都在选中集合中）
    const newEdges = []
    for (const e of edges.value) {
      if (!idSet.has(e.source) || !idSet.has(e.target)) continue
      newEdges.push({
        ...deepClone(e),
        id: generateId('edge'),
        source: idMap[e.source],
        target: idMap[e.target],
      })
    }

    // 3. 写入 store
    nodes.value = [...nodes.value, ...newNodes]
    edges.value = [...edges.value, ...newEdges]
    markDirty()

    return Object.values(idMap)
  }

  // ─── Edge operations ───
  function addEdge(sourceId, sourcePort, targetId, targetPort, fieldMapping, inputTransformer) {
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
      fieldMapping: fieldMapping || null,
      inputTransformer: inputTransformer || null,
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

  // ─── 节点测试结果（n8n 式逐节点调试） ───
  const nodeTestResults = ref({})          // { [node_id]: { output, duration_ms, error, timestamp } }
  const nodeTestInputs = ref({})            // { [node_id]: alert_data_json_string }  手动设置的输入数据

  function setNodeTestResult(nodeId, result) {
    nodeTestResults.value = { ...nodeTestResults.value, [nodeId]: { ...result, timestamp: Date.now() } }
  }

  function clearNodeTestResult(nodeId) {
    const next = { ...nodeTestResults.value }
    delete next[nodeId]
    nodeTestResults.value = next
  }

  function clearAllTestResults() {
    nodeTestResults.value = {}
    nodeTestInputs.value = {}
  }

  function setNodeTestInput(nodeId, jsonData) {
    nodeTestInputs.value = { ...nodeTestInputs.value, [nodeId]: jsonData }
  }

  function getNodeTestInput(nodeId) {
    return nodeTestInputs.value[nodeId] || null
  }

  function hasUpstreamOutput(nodeId) {
    /** 判断某节点的上游是否有缓存输出 */
    for (const e of edges.value) {
      if (e.target === nodeId && nodeTestResults.value[e.source]) return true
    }
    return false
  }

  function getUpstreamOutputs(nodeId) {
    /** 收集目标节点所有上游的缓存输出 */
    const result = {}
    for (const e of edges.value) {
      if (e.target === nodeId) {
        const cached = nodeTestResults.value[e.source]
        if (cached && cached.output) {
          result[e.source] = cached.output
        }
      }
    }
    return result
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

  /**
   * 切换指定规则链的启用/禁用状态
   * 仅更新后端和列表，不切换当前编辑的链
   */
  async function toggleChainEnabled(chainId, enabled) {
    await chainApi.toggleChainEnabled(chainId, enabled)
    // 更新本地列表中的状态
    const idx = chains.value.findIndex(c => c.id === chainId)
    if (idx !== -1) {
      chains.value[idx] = { ...chains.value[idx], enabled }
      chains.value = [...chains.value]
    }
    // 如果正在编辑该链，也同步当前编辑状态（但不触发脏标记）
    if (currentChainId.value === chainId) {
      chainEnabled.value = enabled
    }
  }

  function clearCanvas() {
    nodes.value = []
    edges.value = []
    markDirty()
  }

  function applyDraft(draft) {
    chainName.value = draft.name || chainName.value || 'AI 生成规则链'
    chainDescription.value = draft.description || chainDescription.value || ''
    nodes.value = deepClone(draft.nodes || [])
    edges.value = deepClone(draft.edges || [])
    currentChainId.value = null
    clearAllTestResults()
    markDirty()
  }

  return {
    chains, loadingChains,
    currentChainId, chainName, chainDescription, chainEnabled,
    nodes, edges,
    currentChain, isModified,
    fetchChains, loadChain, createNew,
    addNode, removeNode, updateNode, updateNodeConfig, updateNodePosition,
    duplicateNodes, markDirty,
    addEdge, removeEdge, updateEdge,
    save, deleteChain, clearCanvas, applyDraft, toggleChainEnabled,
    // 节点测试
    nodeTestResults, nodeTestInputs,
    setNodeTestResult, clearNodeTestResult, clearAllTestResults,
    setNodeTestInput, getNodeTestInput,
    hasUpstreamOutput, getUpstreamOutputs,
    // 多标签页同步
    saveToTab, restoreFromTab, setViewportSnapshot,
  }
})
