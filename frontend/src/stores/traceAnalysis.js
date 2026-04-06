import { defineStore } from 'pinia'
import { analyzeTransaction, getSupportedChains, searchSignatures, lookupSignatures } from '@/api/trace.js'

export const useTraceStore = defineStore('traceAnalysis', {
  state: () => ({
    // 输入
    txHash: '',
    chainId: 56,
    supportedChains: [],

    // 分析结果
    result: null,
    isLoading: false,
    error: null,

    // UI 状态
    expandedNodes: new Set(),
    filterText: '',
    selectedNodeId: null,

    // 签名查询缓存
    signatureCache: {},
    showUnknownOnly: false,
  }),

  getters: {
    root() { return this.result?.root || null },
    behaviors() { return this.result?.behaviors || [] },
    protocols() { return this.result?.protocols || [] },
    tokenFlows() { return this.result?.tokenFlows || [] },
    balanceChanges() { return this.result?.balanceChanges || [] },
    selectorStats() { return this.result?.selectorStats || [] },
    txInfo() { return this.result?.txInfo || null },
    meta() { return this.result?.meta || {} },

    hasResult() { return !!this.result },
    hasBehaviors() { return this.behaviors.length > 0 },
    hasError() { return !!this.error },

    selectedChainName() {
      const chain = this.supportedChains.find(c => c.chainId === this.chainId)
      return chain ? chain.name : `Chain ${this.chainId}`
    },
  },

  actions: {
    async loadSupportedChains() {
      try {
        const data = await getSupportedChains()
        this.supportedChains = data || []
      } catch (e) {
        console.warn('[TraceStore] Failed to load chains:', e)
      }
    },

    async analyzeTransaction() {
      if (!this.txHash.trim()) {
        this.error = 'Please enter a transaction hash'
        return
      }

      const hash = this.txHash.trim()
      if (!/^0x[0-9a-fA-F]{64}$/.test(hash)) {
        this.error = 'Invalid transaction hash format (must be 66 hex chars starting with 0x)'
        return
      }

      this.isLoading = true
      this.error = null
      this.result = null
      this.expandedNodes.clear()

      try {
        const data = await analyzeTransaction(hash, this.chainId)
        console.log('[TraceStore] API response keys:', Object.keys(data || {}))
        console.log('[TraceStore] meta:', data?.meta, 'root:', !!data?.root)
        this.result = data
        // 默认展开第一层
        if (data?.root?.children) {
          this.expandedNodes.add(this._nodeKey(data.root))
        }
      } catch (e) {
        this.error = e.message || 'Analysis failed'
      } finally {
        this.isLoading = false
      }
    },

    toggleNode(nodeKey) {
      if (this.expandedNodes.has(nodeKey)) {
        this.expandedNodes.delete(nodeKey)
      } else {
        this.expandedNodes.add(nodeKey)
      }
    },

    isExpanded(nodeKey) {
      return this.expandedNodes.has(nodeKey)
    },

    expandAll() {
      if (!this.root) return
      const stack = [this.root]
      while (stack.length > 0) {
        const node = stack.pop()
        if (node.children && node.children.length > 0) {
          this.expandedNodes.add(this._nodeKey(node))
          stack.push(...[...node.children].reverse())
        }
      }
    },

    collapseAll() {
      this.expandedNodes.clear()
      if (this.root) {
        this.expandedNodes.add(this._nodeKey(this.root))
      }
    },

    selectNode(nodeKey) {
      this.selectedNodeId = nodeKey
    },

  async resolveSignature(selector) {
    if (this.signatureCache[selector]) return this.signatureCache[selector]

    try {
      const data = await lookupSignatures(selector)
      if (data && data.total > 0) {
        this.signatureCache[selector] = data
        return data
      }
    } catch (e) {
      console.warn('[TraceStore] Signature query failed:', e)
    }
    return null
  },

    reset() {
      this.result = null
      this.error = null
      this.expandedNodes.clear()
      this.selectedNodeId = null
      this.filterText = ''
    },

    _nodeKey(node) {
      return `${node.depth}-${(node.traceAddress || []).join('-')}-${node.to}`
    },
  },
})
