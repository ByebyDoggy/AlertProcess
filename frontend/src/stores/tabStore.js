import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * VS Code 风格多标签页管理 store
 *
 * 每个标签页对应一条规则链的编辑器实例，维护独立的编辑状态
 * (节点、连线、视口位置等)。切换标签时，chainData store 的数据
 * 从对应标签页快照中恢复。
 */
export const useTabStore = defineStore('tabs', () => {
  // ─── 标签页列表 ───
  const tabs = ref([])       // { id, chainId, name, description, enabled, nodes, edges, sequencePhases, nodeTestResults, nodeTestInputs, viewport: { zoom, panX, panY }, isModified }
  const activeTabId = ref(null)

  // ─── 计算属性 ───
  const activeTab = computed(() =>
    tabs.value.find(t => t.id === activeTabId.value) || null
  )

  const activeChainId = computed(() =>
    activeTab.value?.chainId || null
  )

  const tabCount = computed(() => tabs.value.length)

  /**
   * 判断指定规则链是否已打开
   */
  function isChainOpen(chainId) {
    return tabs.value.some(t => t.chainId === chainId)
  }

  /**
   * 查找指定规则链的标签页
   */
  function findTabByChainId(chainId) {
    return tabs.value.find(t => t.chainId === chainId) || null
  }

  /**
   * 打开一个规则链标签页
   * @param {object} chain - 规则链对象 { id, name, description, enabled, chain_config }
   * @returns {string} 标签页 ID
   */
  function openTab(chain) {
    // 如果已经打开，直接切换
    const existing = findTabByChainId(chain.id)
    if (existing) {
      activeTabId.value = existing.id
      return existing.id
    }

    const cfg = chain.chain_config || {}
    const tabId = `tab-${chain.id}`

    const tab = {
      id: tabId,
      chainId: chain.id,
      name: chain.name || '未命名',
      description: chain.description || '',
      enabled: chain.enabled !== false,
      nodes: JSON.parse(JSON.stringify(cfg.nodes || [])),
      edges: JSON.parse(JSON.stringify(cfg.edges || [])),
      sequencePhases: JSON.parse(JSON.stringify(cfg.sequence_phases || [])),
      activePhaseId: (cfg.sequence_phases || [])[0]?.id || null,
      nodeTestResults: {},
      nodeTestInputs: {},
      viewport: { zoom: 1, panX: 0, panY: 0 },
      isModified: false,
    }

    tabs.value.push(tab)
    activeTabId.value = tabId
    return tabId
  }

  /**
   * 打开一个新建空白标签页
   * @param {string} [tempId] - 临时 ID（用于新建但尚未保存的链）
   * @returns {string} 标签页 ID
   */
  function openNewTab(tempId) {
    const tabId = tempId || `tab-new-${Date.now()}`
    const tab = {
      id: tabId,
      chainId: null,
      name: '新建规则链',
      description: '',
      enabled: false,
      nodes: [],
      edges: [],
      sequencePhases: [],
      activePhaseId: null,
      nodeTestResults: {},
      nodeTestInputs: {},
      viewport: { zoom: 1, panX: 0, panY: 0 },
      isModified: false,
    }

    tabs.value.push(tab)
    activeTabId.value = tabId
    return tabId
  }

  /**
   * 切换到指定标签页
   */
  function switchTab(tabId) {
    if (tabs.value.some(t => t.id === tabId)) {
      activeTabId.value = tabId
    }
  }

  /**
   * 关闭指定标签页
   * @param {string} tabId
   * @returns {{ closedTab, nextTabId }} 被关闭的标签页和下一个激活标签
   */
  function closeTab(tabId) {
    const idx = tabs.value.findIndex(t => t.id === tabId)
    if (idx === -1) return { closedTab: null, nextTabId: null }

    const closedTab = tabs.value[idx]
    tabs.value.splice(idx, 1)

    // 如果关闭的是当前激活标签，自动切换到相邻标签
    let nextTabId = null
    if (activeTabId.value === tabId) {
      if (tabs.value.length > 0) {
        // 优先切到右侧，否则切到左侧
        const nextIdx = Math.min(idx, tabs.value.length - 1)
        nextTabId = tabs.value[nextIdx].id
        activeTabId.value = nextTabId
      } else {
        activeTabId.value = null
      }
    } else {
      nextTabId = activeTabId.value
    }

    return { closedTab, nextTabId }
  }

  /**
   * 关闭除指定标签外的所有标签
   */
  function closeOtherTabs(tabId) {
    const keep = tabs.value.find(t => t.id === tabId)
    if (!keep) return
    tabs.value = [keep]
    activeTabId.value = tabId
  }

  /**
   * 更新标签页的编辑数据（从 chainData store 同步过来）
   */
  function updateTabData(tabId, data) {
    const tab = tabs.value.find(t => t.id === tabId)
    if (!tab) return
    Object.assign(tab, data)
  }

  /**
   * 更新标签页名称（重命名时同步）
   */
  function updateTabName(tabId, name) {
    const tab = tabs.value.find(t => t.id === tabId)
    if (tab) tab.name = name
  }

  /**
   * 保存成功后更新标签页的 chainId（新建链首次保存）
   */
  function updateTabChainId(tabId, chainId) {
    const tab = tabs.value.find(t => t.id === tabId)
    if (tab) {
      tab.chainId = chainId
      tab.id = `tab-${chainId}`
      if (activeTabId.value === tabId) {
        activeTabId.value = tab.id
      }
    }
  }

  /**
   * 关闭指定规则链的标签（用于删除链时）
   */
  function closeTabByChainId(chainId) {
    const tab = findTabByChainId(chainId)
    if (tab) return closeTab(tab.id)
    return { closedTab: null, nextTabId: null }
  }

  /**
   * 清除所有标签
   */
  function clearAllTabs() {
    tabs.value = []
    activeTabId.value = null
  }

  return {
    tabs, activeTabId,
    activeTab, activeChainId, tabCount,
    isChainOpen, findTabByChainId,
    openTab, openNewTab,
    switchTab, closeTab, closeOtherTabs,
    updateTabData, updateTabName, updateTabChainId,
    closeTabByChainId, clearAllTabs,
  }
})
