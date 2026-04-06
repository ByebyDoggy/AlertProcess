import { defineStore } from 'pinia'
import {
  analyzeTransaction, getSupportedChains, searchSignatures, lookupSignatures,
  fetchCallTree, fetchBalanceChanges, fetchTokenFlows, fetchBehaviors,
} from '@/api/trace.js'

export const useTraceStore = defineStore('traceAnalysis', {
  state: () => ({
    // 输入
    txHash: '',
    chainId: 56,
    supportedChains: [],

    // ── 全量分析结果 (兼容原有 /analyze 端点) ──
    result: null,
    isLoading: false,
    error: null,

    // ── 面板独立数据状态 (拆分端点) ──
    // Call Tree
    callTreeData: null,       // { meta, txInfo, root, selectorStats }
    isCallTreeLoading: false,
    callTreeError: null,

    // Balance Changes
    balanceChangesData: [],   // balanceChanges[]
    isBalanceLoading: false,
    balanceError: null,

    // Token Flows
    tokenFlowsData: [],       // tokenFlows[]
    isTokenFlowLoading: false,
    tokenFlowError: null,

    // Fund Flow (BlockSec-style diagram data)
    _fundFlowData: null,       // internal state { transfers: [...] }

    // Behaviors
    behaviorsData: [],        // behaviors[]
    protocolsData: [],        // protocols[]
    isBehaviorLoading: false,
    behaviorError: null,

    // UI 状态
    expandedNodes: new Set(),
    filterText: '',
    selectedNodeId: null,

    // 签名查询缓存
    signatureCache: {},
    showUnknownOnly: false,
  }),

  getters: {
    // ── 兼容 getters (优先使用独立数据，回退到全量结果) ──
    root() { return this.callTreeData?.root || this.result?.root || null },
    behaviors() { return this.behaviorsData.length ? this.behaviorsData : (this.result?.behaviors || []) },
    protocols() { return this.protocolsData.length ? this.protocolsData : (this.result?.protocols || []) },
    tokenFlows() { return this.tokenFlowsData.length ? this.tokenFlowsData : (this.result?.tokenFlows || []) },
    fundFlowData() { return this._fundFlowData },
    balanceChanges() { return this.balanceChangesData.length ? this.balanceChangesData : (this.result?.balanceChanges || []) },
    selectorStats() { return this.callTreeData?.selectorStats || this.result?.selectorStats || [] },
    txInfo() { return this.callTreeData?.txInfo || this.result?.txInfo || null },
    meta() { return this.callTreeData?.meta || this.result?.meta || {} },

    hasResult() { return !!this.result || !!this.callTreeData },
    hasBehaviors() { return this.behaviors.length > 0 },
    hasError() { return !!this.error || !!(this.callTreeError || this.balanceError || this.tokenFlowError || this.behaviorError) },

    selectedChainName() {
      const chain = this.supportedChains.find(c => c.chainId === this.chainId)
      return chain ? chain.name : `Chain ${this.chainId}`
    },

    // 各面板独立 loading 状态
    isAnyPanelLoading() {
      return this.isCallTreeLoading || this.isBalanceLoading || this.isTokenFlowLoading || this.isBehaviorLoading
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

    // ── 面板独立加载 (拆分端点，并发执行) ──

    /**
     * 并发加载所有面板数据 (推荐使用此方法替代 analyzeTransaction)
     * 各面板独立请求后端，互不阻塞，先返回的面板先渲染
     */
    async loadPanelsConcurrent() {
      if (!this.txHash.trim()) {
        this.error = 'Please enter a transaction hash'
        return
      }

      const hash = this.txHash.trim()
      if (!/^0x[0-9a-fA-F]{64}$/.test(hash)) {
        this.error = 'Invalid transaction hash format (must be 66 hex chars starting with 0x)'
        return
      }

      // 重置所有面板状态
      this._resetPanelStates()
      this.error = null

      const cid = this.chainId

      // 并发发起 4 个独立请求，各面板互不等待
      const promises = [
        this._loadCallTree(hash, cid),
        this._loadBalanceChanges(hash, cid),
        this._loadTokenFlows(hash, cid),
        this._loadBehaviors(hash, cid),
      ]

      // 等待全部完成（无论成功失败），用于判断整体状态
      await Promise.allSettled(promises)

      // Call Tree 加载完成后自动展开第一层
      if (this.callTreeData?.root?.children) {
        this.expandedNodes.add(this._nodeKey(this.callTreeData.root))
      }
    },

    async _loadCallTree(hash, cid) {
      this.isCallTreeLoading = true
      this.callTreeError = null
      try {
        const data = await fetchCallTree(hash, cid)
        this.callTreeData = data
        console.log(`[TraceStore] Call tree loaded in ${data.apiElapsedSeconds}s`)
      } catch (e) {
        this.callTreeError = e.message || 'Call tree failed'
        console.warn('[TraceStore] Call tree error:', e)
      } finally {
        this.isCallTreeLoading = false
      }
    },

    async _loadBalanceChanges(hash, cid) {
      this.isBalanceLoading = true
      this.balanceError = null
      try {
        const data = await fetchBalanceChanges(hash, cid)
        this.balanceChangesData = data.balanceChanges || []
        console.log(`[TraceStore] Balance changes loaded: ${this.balanceChangesData.length} entries`)
        // Build fund flow diagram from balance changes data
        this._buildFundFlowFromBalanceChanges(this.balanceChangesData)
      } catch (e) {
        this.balanceError = e.message || 'Balance changes failed'
        console.warn('[TraceStore] Balance changes error:', e)
      } finally {
        this.isBalanceLoading = false
      }
    },

    async _loadTokenFlows(hash, cid) {
      this.isTokenFlowLoading = true
      this.tokenFlowError = null
      try {
        const data = await fetchTokenFlows(hash, cid)
        this.tokenFlowsData = data.tokenFlows || []
        console.log(`[TraceStore] Token flows loaded: ${this.tokenFlowsData.length} flows`)
        // Fund flow diagram is built from balanceChanges instead (has full address info)
      } catch (e) {
        this.tokenFlowError = e.message || 'Token flows failed'
        console.warn('[TraceStore] Token flows error:', e)
      } finally {
        this.isTokenFlowLoading = false
      }
    },

    // Build fund flow from balanceChanges data (has actual from/to addresses)
    _buildFundFlowFromBalanceChanges(changes) {
      if (!changes || !changes.length) { this._fundFlowData = null; return }

      // Group by token: collect per-address net amounts
      var tokenGroups = {}
      for (var i = 0; i < changes.length; i++) {
        var c = changes[i]
        var tk = c.tokenAddress || 'ETH'
        if (!tokenGroups[tk]) tokenGroups[tk] = { symbol: c.tokenSymbol || 'ETH', addrMap: {} }
        var m = tokenGroups[tk].addrMap
        var amt = c.amountRaw || 0
        if (m[c.address] == null) m[c.address] = 0
        m[c.address] += amt
      }

      var transfers = []
      var idCounter = 1

      // For each token, create transfer edges: negative -> positive
      var tKeys = Object.keys(tokenGroups)
      for (var ti = 0; ti < tKeys.length; ti++) {
        var tg = tokenGroups[tKeys[ti]]
        var addrs = Object.keys(tg.addrMap)
        var senders = []
        var receivers = []

        for (var ai = 0; ai < addrs.length; ai++) {
          var val = tg.addrMap[addrs[ai]]
          if (val < 0) senders.push({ addr: addrs[ai], absVal: Math.abs(val) })
          else if (val > 0) receivers.push({ addr: addrs[ai], absVal: val })
        }

        // Create sender->receiver edges proportional to amounts
        var totalSend = 0
        for (var si = 0; si < senders.length; si++) totalSend += senders[si].absVal
        var totalRecv = 0
        for (var ri = 0; ri < receivers.length; ri++) totalRecv += receivers[ri].absVal

        // Simple pairing: each sender sends to each receiver proportionally
        for (var si2 = 0; si2 < senders.length; si2++) {
          var s = senders[si2]
          for (var ri2 = 0; ri2 < receivers.length; ri2++) {
            var r = receivers[ri2]
            // Proportional split based on amounts
            var share = totalRecv > 0 ? r.absVal / totalRecv : 1 / receivers.length
            var amtVal = Math.round(s.absVal * share)
            if (amtVal <= 0) continue
            transfers.push({
              id: idCounter++,
              amount: String(amtVal),
              from: s.addr,
              to: r.addr,
              token: tKeys[ti],
              tokenSymbol: tg.symbol,
              tokenType: tKeys[ti] === 'ETH' ? 0 : 1,
              isReverted: false,
            })
          }
        }
      }

      this._fundFlowData = transfers.length > 0 ? { transfers: transfers } : null
      console.log('[TraceStore] Fund flow built:', transfers.length, 'transfers from', changes.length, 'balance changes')
    },

    async _loadBehaviors(hash, cid) {
      this.isBehaviorLoading = true
      this.behaviorError = null
      try {
        const data = await fetchBehaviors(hash, cid)
        this.behaviorsData = data.behaviors || []
        this.protocolsData = data.protocols || []
        console.log(`[TraceStore] Behaviors loaded: ${this.behaviorsData.length} results`)
      } catch (e) {
        this.behaviorError = e.message || 'Behaviors failed'
        console.warn('[TraceStore] Behaviors error:', e)
      } finally {
        this.isBehaviorLoading = false
      }
    },

    _resetPanelStates() {
      this.callTreeData = null
      this.balanceChangesData = []
      this.tokenFlowsData = []
      this._fundFlowData = null
      this.behaviorsData = []
      this.protocolsData = []
      this.callTreeError = null
      this.balanceError = null
      this.tokenFlowError = null
      this.behaviorError = null
      this.isCallTreeLoading = false
      this.isBalanceLoading = false
      this.isTokenFlowLoading = false
      this.isBehaviorLoading = false
      this.expandedNodes.clear()
      this.selectedNodeId = null
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
      this._resetPanelStates()
      this.filterText = ''
    },

    _nodeKey(node) {
      return `${node.depth}-${(node.traceAddress || []).join('-')}-${node.to}`
    },
  },
})
