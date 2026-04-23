import { defineStore } from 'pinia'
import { ref } from 'vue'
import { deepClone, generateId } from '../utils/helpers.js'

/**
 * 跨标签页剪贴板 store
 *
 * 保存从任意标签页复制的节点及其内部连线数据。
 * 粘贴时，生成全新的 ID 并将节点放置到当前画布指定位置。
 * 因为是独立的 Pinia store，切换标签页不会丢失剪贴板内容。
 */
export const useClipboardStore = defineStore('clipboard', () => {
  // ─── 剪贴板数据 ───
  // nodes: 深拷贝的节点数组（保留原始 ID 用于连线映射）
  // edges:  两端均在选中节点集合中的连线
  // sourceChainId: 来源规则链 ID（仅用于展示）
  // sourceChainName: 来源规则链名称
  const nodes = ref([])
  const edges = ref([])
  const sourceChainId = ref(null)
  const sourceChainName = ref('')

  /** 剪贴板是否非空 */
  const hasContent = ref(false)

  /**
   * 将选中的节点和内部连线写入剪贴板
   * @param {object[]} selectedNodes - 选中的节点数组
   * @param {object[]} allEdges - 当前画布所有连线
   * @param {string} chainId - 来源规则链 ID
   * @param {string} chainName - 来源规则链名称
   */
  function copy(selectedNodes, allEdges, chainId, chainName) {
    if (!selectedNodes || selectedNodes.length === 0) return

    const idSet = new Set(selectedNodes.map(n => n.id))

    // 深拷贝节点（保留原始 ID，粘贴时再替换）
    nodes.value = deepClone(selectedNodes)

    // 仅保留两端均在选中集合中的连线
    edges.value = deepClone(
      allEdges.filter(e => idSet.has(e.source) && idSet.has(e.target))
    )

    sourceChainId.value = chainId
    sourceChainName.value = chainName
    hasContent.value = true
  }

  /**
   * 清空剪贴板
   */
  function clear() {
    nodes.value = []
    edges.value = []
    sourceChainId.value = null
    sourceChainName.value = ''
    hasContent.value = false
  }

  /**
   * 粘贴剪贴板内容，返回新建的节点和连线
   * @param {number} offsetX - 相对于原始位置的 X 偏移
   * @param {number} offsetY - 相对于原始位置的 Y 偏移
   * @returns {{ newNodes: object[], newEdges: object[], newNodeIds: string[] }}
   */
  function paste(offsetX = 40, offsetY = 40) {
    if (!hasContent.value || nodes.value.length === 0) {
      return { newNodes: [], newEdges: [], newNodeIds: [] }
    }

    // 1. 为每个原始节点生成新 ID
    const idMap = {} // oldId → newId
    for (const node of nodes.value) {
      idMap[node.id] = generateId('node')
    }

    // 2. 创建新节点（替换 ID 和位置）
    const newNodes = nodes.value.map(src => ({
      ...deepClone(src),
      id: idMap[src.id],
      position: {
        x: src.position.x + offsetX,
        y: src.position.y + offsetY,
      },
    }))

    // 3. 创建新连线（替换 ID 和端点）
    const newEdges = edges.value.map(src => ({
      ...deepClone(src),
      id: generateId('edge'),
      source: idMap[src.source],
      target: idMap[src.target],
    }))

    return {
      newNodes,
      newEdges,
      newNodeIds: newNodes.map(n => n.id),
    }
  }

  /**
   * 粘贴到画布指定位置（将节点整体偏移到目标位置）
   * @param {number} targetX - 目标中心 X（画布坐标）
   * @param {number} targetY - 目标中心 Y（画布坐标）
   * @returns {{ newNodes: object[], newEdges: object[], newNodeIds: string[] }}
   */
  function pasteAt(targetX, targetY) {
    if (!hasContent.value || nodes.value.length === 0) {
      return { newNodes: [], newEdges: [], newNodeIds: [] }
    }

    // 计算原始节点的包围盒中心
    const xs = nodes.value.map(n => n.position.x)
    const ys = nodes.value.map(n => n.position.y)
    const minX = Math.min(...xs)
    const minY = Math.min(...ys)
    // 偏移量：从包围盒左上角移到目标位置
    const offsetX = targetX - minX
    const offsetY = targetY - minY

    const idMap = {} // oldId → newId
    for (const node of nodes.value) {
      idMap[node.id] = generateId('node')
    }

    const newNodes = nodes.value.map(src => ({
      ...deepClone(src),
      id: idMap[src.id],
      position: {
        x: src.position.x + offsetX,
        y: src.position.y + offsetY,
      },
    }))

    const newEdges = edges.value.map(src => ({
      ...deepClone(src),
      id: generateId('edge'),
      source: idMap[src.source],
      target: idMap[src.target],
    }))

    return {
      newNodes,
      newEdges,
      newNodeIds: newNodes.map(n => n.id),
    }
  }

  return {
    nodes, edges,
    sourceChainId, sourceChainName,
    hasContent,
    copy, clear, paste, pasteAt,
  }
})
