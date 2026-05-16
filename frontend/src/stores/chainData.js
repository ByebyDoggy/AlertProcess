import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { generateId, deepClone } from '../utils/helpers.js'
import * as chainApi from '../api/ruleChain.js'
import { useNodeTypesStore } from './nodeTypes.js'
import { useTabStore } from './tabStore.js'

const DEFAULT_SEQUENCE_PHASES = [
  {
    id: 'phase_1',
    name: '阶段 1',
    description: '循环开始阶段',
    color: '#8b5cf6',
    x: 60,
    y: 80,
    width: 560,
    height: 320,
  },
  {
    id: 'phase_2',
    name: '阶段 2',
    description: '中间处理阶段',
    color: '#06b6d4',
    x: 680,
    y: 80,
    width: 560,
    height: 320,
  },
  {
    id: 'phase_3',
    name: '阶段 3',
    description: '闭环确认阶段',
    color: '#f59e0b',
    x: 1300,
    y: 80,
    width: 560,
    height: 320,
  },
]

function normalizeSequencePhases(phases = []) {
  return phases.map((phase, index) => ({
    id: phase.id || generateId('phase'),
    name: phase.name || `阶段 ${index + 1}`,
    description: phase.description || '',
    color: phase.color || DEFAULT_SEQUENCE_PHASES[index % DEFAULT_SEQUENCE_PHASES.length]?.color || '#8b5cf6',
    x: Number.isFinite(phase.x) ? phase.x : 60 + index * 620,
    y: Number.isFinite(phase.y) ? phase.y : 80,
    width: Number.isFinite(phase.width) ? phase.width : 560,
    height: Number.isFinite(phase.height) ? phase.height : 320,
  }))
}

export const useChainDataStore = defineStore('chainData', () => {
  const chains = ref([])
  const loadingChains = ref(false)

  const currentChainId = ref(null)
  const chainName = ref('')
  const chainDescription = ref('')
  const chainEnabled = ref(true)
  const nodes = ref([])
  const edges = ref([])
  const sequencePhases = ref([])
  const activePhaseId = ref(null)

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
      JSON.stringify(cfg.sequence_phases || []) !== JSON.stringify(sequencePhases.value) ||
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
    const cfg = chain.chain_config || {}
    currentChainId.value = chain.id
    chainName.value = chain.name
    chainDescription.value = chain.description || ''
    chainEnabled.value = chain.enabled
    nodes.value = deepClone(cfg.nodes || [])
    edges.value = deepClone(cfg.edges || [])
    sequencePhases.value = normalizeSequencePhases(cfg.sequence_phases || [])
    activePhaseId.value = sequencePhases.value[0]?.id || null
    nodeTestResults.value = {}
    nodeTestInputs.value = {}
    _dirty.value = false
  }

  function createNew() {
    currentChainId.value = null
    chainName.value = ''
    chainDescription.value = ''
    chainEnabled.value = false
    nodes.value = []
    edges.value = []
    sequencePhases.value = deepClone(DEFAULT_SEQUENCE_PHASES)
    activePhaseId.value = sequencePhases.value[0]?.id || null
    nodeTestResults.value = {}
    nodeTestInputs.value = {}
    _dirty.value = false
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
      sequencePhases: deepClone(sequencePhases.value),
      activePhaseId: activePhaseId.value,
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
    sequencePhases.value = normalizeSequencePhases(tab.sequencePhases || [])
    activePhaseId.value = tab.activePhaseId || sequencePhases.value[0]?.id || null
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
    const activePhase = sequencePhases.value.find(phase => phase.id === activePhaseId.value) || null

    const node = {
      id: generateId('node'),
      type: nodeTypeName,
      label,
      config: {
        ...deepClone(defaultConfig),
        ...(activePhase
          ? {
              sequence_phase_id: activePhase.id,
              sequence_phase_name: activePhase.name,
            }
          : {}),
      },
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
      const node = nodes.value[idx]
      nodes.value[idx] = {
        ...node,
        position: { x, y },
        config: { ...(node.config || {}) },
      }
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
    const activePhase = sequencePhases.value.find(phase => phase.id === activePhaseId.value) || null

    // 1. 复制节点
    for (const id of nodeIds) {
      const src = nodes.value.find(n => n.id === id)
      if (!src) continue
      const newId = generateId('node')
      idMap[id] = newId
      newNodes.push({
        ...deepClone(src),
        id: newId,
        config: {
          ...(deepClone(src.config || {})),
          ...(activePhase
            ? {
                sequence_phase_id: activePhase.id,
                sequence_phase_name: activePhase.name,
              }
            : {}),
        },
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
      sequence_phases: sequencePhases.value,
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

  function getPhaseForNode(node) {
    const phaseId = node.config?.sequence_phase_id
    if (phaseId) {
      return sequencePhases.value.find(phase => phase.id === phaseId) || null
    }
    return null
  }

  function assignNodeToPhase(nodeId, phaseId = activePhaseId.value) {
    const idx = nodes.value.findIndex(n => n.id === nodeId)
    if (idx === -1) return null
    const node = nodes.value[idx]
    const phase = phaseId
      ? sequencePhases.value.find(item => item.id === phaseId) || null
      : null
    const nextConfig = { ...(node.config || {}) }
    if (phase) {
      nextConfig.sequence_phase_id = phase.id
      nextConfig.sequence_phase_name = phase.name
    } else {
      delete nextConfig.sequence_phase_id
      delete nextConfig.sequence_phase_name
    }
    nodes.value[idx] = { ...node, config: nextConfig }
    return phase
  }

  function addSequencePhase(partial = {}) {
    const phase = normalizeSequencePhases([{
      id: generateId('phase'),
      name: partial.name || `阶段 ${sequencePhases.value.length + 1}`,
      description: partial.description || '',
      color: partial.color,
      x: partial.x,
      y: partial.y,
      width: partial.width,
      height: partial.height,
    }])[0]
    sequencePhases.value = [...sequencePhases.value, phase]
    activePhaseId.value = phase.id
    markDirty()
    return phase
  }

  function setActivePhase(phaseId) {
    activePhaseId.value = phaseId
  }

  function updateSequencePhase(phaseId, updates) {
    const idx = sequencePhases.value.findIndex(p => p.id === phaseId)
    if (idx === -1) return
    sequencePhases.value[idx] = { ...sequencePhases.value[idx], ...updates }
    sequencePhases.value = [...sequencePhases.value]
    markDirty()
  }

  function removeSequencePhase(phaseId) {
    sequencePhases.value = sequencePhases.value.filter(p => p.id !== phaseId)
    if (activePhaseId.value === phaseId) {
      activePhaseId.value = sequencePhases.value[0]?.id || null
    }
    for (let idx = 0; idx < nodes.value.length; idx++) {
      const node = nodes.value[idx]
      if (node.config?.sequence_phase_id !== phaseId) continue
      const nextConfig = { ...(node.config || {}) }
      if (activePhaseId.value) {
        const fallbackPhase = sequencePhases.value.find(p => p.id === activePhaseId.value) || null
        if (fallbackPhase) {
          nextConfig.sequence_phase_id = fallbackPhase.id
          nextConfig.sequence_phase_name = fallbackPhase.name
        } else {
          delete nextConfig.sequence_phase_id
          delete nextConfig.sequence_phase_name
        }
      } else {
        delete nextConfig.sequence_phase_id
        delete nextConfig.sequence_phase_name
      }
      nodes.value[idx] = { ...node, config: nextConfig }
    }
    markDirty()
  }

  function clearCanvas() {
    nodes.value = []
    edges.value = []
    sequencePhases.value = deepClone(DEFAULT_SEQUENCE_PHASES)
    activePhaseId.value = sequencePhases.value[0]?.id || null
    clearAllTestResults()
    markDirty()
  }

  function applyDraft(draft) {
    chainName.value = draft.name || chainName.value || 'AI 生成规则链'
    chainDescription.value = draft.description || chainDescription.value || ''
    nodes.value = deepClone(draft.nodes || [])
    edges.value = deepClone(draft.edges || [])
    sequencePhases.value = normalizeSequencePhases(draft.sequence_phases || draft.sequencePhases || DEFAULT_SEQUENCE_PHASES)
    activePhaseId.value = sequencePhases.value[0]?.id || null
    currentChainId.value = null
    clearAllTestResults()
    for (const node of nodes.value) {
      const nextConfig = { ...(node.config || {}) }
      if (!nextConfig.sequence_phase_id && activePhaseId.value) {
        const phase = sequencePhases.value.find(item => item.id === activePhaseId.value) || null
        if (phase) {
          nextConfig.sequence_phase_id = phase.id
          nextConfig.sequence_phase_name = phase.name
          node.config = nextConfig
        }
      }
    }
    markDirty()
  }

  return {
    chains, loadingChains,
    currentChainId, chainName, chainDescription, chainEnabled,
    nodes, edges, sequencePhases, activePhaseId,
    currentChain, isModified,
    fetchChains, loadChain, createNew,
    addNode, removeNode, updateNode, updateNodeConfig, updateNodePosition,
    duplicateNodes, markDirty,
    addEdge, removeEdge, updateEdge,
    save, deleteChain, clearCanvas, applyDraft, toggleChainEnabled,
    getPhaseForNode, assignNodeToPhase, addSequencePhase, setActivePhase, updateSequencePhase, removeSequencePhase,
    // 节点测试
    nodeTestResults, nodeTestInputs,
    setNodeTestResult, clearNodeTestResult, clearAllTestResults,
    setNodeTestInput, getNodeTestInput,
    hasUpstreamOutput, getUpstreamOutputs,
    // 多标签页同步
    saveToTab, restoreFromTab, setViewportSnapshot,
  }
})
