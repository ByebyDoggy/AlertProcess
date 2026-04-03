import { ref } from 'vue'
import { useChainDataStore } from '../stores/chainData.js'
import { useChainEditorStore } from '../stores/chainEditor.js'

/**
 * 画布拖拽 composable
 * 处理：从面板拖入新节点、画布内移动节点
 *
 * 性能优化：拖拽期间直接操作 DOM style，跳过 Vue 响应式，
 * 仅在 mouseup 时将最终位置写回 store。
 */
export function useDragDrop(canvasRef) {
  const chainDataStore = useChainDataStore()
  const editorStore = useChainEditorStore()
  const draggingNodeId = ref(null)
  const dragOffset = ref({ x: 0, y: 0 })

  function screenToCanvas(clientX, clientY) {
    const cr = canvasRef.value.getBoundingClientRect()
    const zoom = editorStore.zoom
    const panX = editorStore.panX
    const panY = editorStore.panY
    return {
      x: (clientX - cr.left - panX) / zoom,
      y: (clientY - cr.top - panY) / zoom,
    }
  }

  function handleCanvasDrop(event) {
    const nodeType = event.dataTransfer.getData('nodeType')
    if (!nodeType || !canvasRef.value) return

    const pos = screenToCanvas(event.clientX, event.clientY)
    const x = Math.max(0, pos.x - 115)
    const y = Math.max(0, pos.y - 40)

    chainDataStore.addNode(nodeType, x, y)
  }

  /**
   * 开始拖拽已有节点
   * 拖拽期间：直接更新 DOM left/top，不触发 Vue 响应式
   * 松开时：将最终坐标写回 store（触发一次渲染）
   */
  function startNodeDrag(event, node) {
    if (event.target.closest('[data-port-key]')) return
    if (event.target.closest('.node-delete-btn')) return

    draggingNodeId.value = node.id
    const nodeEl = event.target.closest('[data-node-id]')
    if (!nodeEl) return

    const rect = nodeEl.getBoundingClientRect()
    const offsetScreenX = event.clientX - rect.left
    const offsetScreenY = event.clientY - rect.top

    // 画布坐标偏移（屏幕像素偏移 / zoom）
    const zoom = editorStore.zoom
    const offsetCanvasX = offsetScreenX / zoom
    const offsetCanvasY = offsetScreenY / zoom

    let rafId = null

    const onMove = (e) => {
      if (!draggingNodeId.value || !canvasRef.value) return

      if (rafId !== null) return // skip if previous frame not painted
      rafId = requestAnimationFrame(() => {
        rafId = null
        const pos = screenToCanvas(e.clientX, e.clientY)
        const x = Math.max(0, pos.x - offsetCanvasX)
        const y = Math.max(0, pos.y - offsetCanvasY)

        // 直接操作 DOM，跳过 Vue 响应式
        nodeEl.style.left = x + 'px'
        nodeEl.style.top = y + 'px'
      })
    }

    const onUp = () => {
      if (rafId !== null) {
        cancelAnimationFrame(rafId)
        rafId = null
      }

      // 将最终位置写回 store
      if (draggingNodeId.value) {
        const left = parseFloat(nodeEl.style.left)
        const top = parseFloat(nodeEl.style.top)
        if (!isNaN(left) && !isNaN(top)) {
          chainDataStore.updateNodePosition(draggingNodeId.value, left, top)
        }
      }

      draggingNodeId.value = null
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

  return { draggingNodeId, handleCanvasDrop, startNodeDrag }
}
