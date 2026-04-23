import { onMounted, onUnmounted } from 'vue'
import { useChainDataStore } from '../stores/chainData.js'
import { useChainEditorStore } from '../stores/chainEditor.js'
import { useClipboardStore } from '../stores/clipboardStore.js'

/**
 * 键盘快捷键 composable
 * Ctrl+S: 保存
 * Ctrl+C: 复制选中节点到剪贴板
 * Ctrl+V: 从剪贴板粘贴节点到当前画布
 * Delete/Backspace: 删除选中节点/边
 * Escape: 关闭面板、取消选中
 */
export function useKeyboard(options = {}) {
  const chainDataStore = useChainDataStore()
  const editorStore = useChainEditorStore()
  const clipboardStore = useClipboardStore()

  const {
    onSave,
    onToast,
    onPaste,
  } = options

  function handler(e) {
    // 不在输入框中时才处理快捷键
    const tag = document.activeElement?.tagName
    const isInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'

    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault()
      onSave?.()
    }

    // Ctrl+C: 复制选中节点到剪贴板
    if ((e.ctrlKey || e.metaKey) && e.key === 'c' && !isInput) {
      const selectedIds = editorStore.selectedNodeIds
      const selectedSingleId = editorStore.selectedNodeId
      const ids = selectedIds.length > 0 ? selectedIds : (selectedSingleId ? [selectedSingleId] : [])
      if (ids.length === 0) return

      const selectedNodes = chainDataStore.nodes.filter(n => ids.includes(n.id))
      if (selectedNodes.length === 0) return

      clipboardStore.copy(
        selectedNodes,
        chainDataStore.edges,
        chainDataStore.currentChainId,
        chainDataStore.chainName
      )
      onToast?.(`已复制 ${selectedNodes.length} 个节点到剪贴板`, 'info')
      return
    }

    // Ctrl+V: 从剪贴板粘贴
    if ((e.ctrlKey || e.metaKey) && e.key === 'v' && !isInput) {
      e.preventDefault()
      onPaste?.()
      return
    }

    if ((e.key === 'Delete' || e.key === 'Backspace') && !isInput) {
      if (editorStore.showNodeConfig || editorStore.showEdgeConfig) return
      if (editorStore.selectedNodeId) {
        chainDataStore.removeNode(editorStore.selectedNodeId)
        editorStore.clearSelection()
        onToast?.('节点已删除', 'info')
      } else if (editorStore.selectedEdgeId) {
        chainDataStore.removeEdge(editorStore.selectedEdgeId)
        editorStore.clearSelection()
        onToast?.('连接已删除', 'info')
      }
    }

    if (e.key === 'Escape') {
      editorStore.closeNodeConfig()
      editorStore.closeEdgeConfig()
      editorStore.clearSelection()
    }
  }

  onMounted(() => window.addEventListener('keydown', handler))
  onUnmounted(() => window.removeEventListener('keydown', handler))
}
