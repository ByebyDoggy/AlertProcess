import { onMounted, onUnmounted } from 'vue'
import { useChainDataStore } from '../stores/chainData.js'
import { useChainEditorStore } from '../stores/chainEditor.js'

/**
 * 键盘快捷键 composable
 * Ctrl+S: 保存
 * Delete/Backspace: 删除选中节点/边
 * Escape: 关闭面板、取消选中
 */
export function useKeyboard(options = {}) {
  const chainDataStore = useChainDataStore()
  const editorStore = useChainEditorStore()

  const {
    onSave,
    onToast,
  } = options

  function handler(e) {
    // 不在输入框中时才处理快捷键
    const tag = document.activeElement?.tagName
    const isInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'

    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault()
      onSave?.()
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
