import { ref, onUnmounted } from 'vue'
import { useNodeTypesStore } from '../stores/nodeTypes.js'
import { useChainDataStore } from '../stores/chainData.js'
import { useChainEditorStore } from '../stores/chainEditor.js'
import { getPortPosition, getEdgePath, NODE_WIDTH } from '../utils/geometry.js'
import { validateConnection, isTargetPortConnected, isMultiPort } from '../utils/connection.js'

/**
 * 连线逻辑 composable
 * 处理从端口拖出连线、实时校验、完成连线
 */
export function useConnection(canvasRef) {
  const nodeTypesStore = useNodeTypesStore()
  const chainDataStore = useChainDataStore()
  const editorStore = useChainEditorStore()

  /**
   * 开始从某个端口拖拽连线
   */
  function startPortDrag(event, node, portKey, side) {
    event.preventDefault()
    event.stopPropagation()

    const nodeType = nodeTypesStore.getByName(node.type)
    const portType = side === 'right' ? 'outputs' : 'inputs'
    const ports = nodeType?.[portType] || []
    const portDef = ports.find(p => p.key === portKey)
    const dataType = portDef?.data_type || 'any'
    const portIndex = ports.findIndex(p => p.key === portKey)

    editorStore.startConnection(node.id, portKey, side, dataType)

    const onMouseMove = (e) => {
      if (!editorStore.connecting || !canvasRef.value) return

      const cr = canvasRef.value.getBoundingClientRect()
      const zoom = editorStore.zoom
      const panX = editorStore.panX
      const panY = editorStore.panY
      const mx = (e.clientX - cr.left - panX) / zoom
      const my = (e.clientY - cr.top - panY) / zoom

      let from, to
      // 从 DOM 读取起始端口圆圈的真实位置
      const nodeEl = canvasRef.value.querySelector(`[data-node-id="${node.id}"]`)
      if (nodeEl) {
        const portEl = nodeEl.querySelector(`[data-port-key="${portKey}"][data-port-side="${side}"]`)
        if (portEl) {
          const rect = portEl.getBoundingClientRect()
          const px = (rect.left + rect.width / 2 - cr.left) / zoom - panX / zoom
          const py = (rect.top + rect.height / 2 - cr.top) / zoom - panY / zoom
          if (side === 'right') {
            from = { x: px, y: py }
            to = { x: mx, y: my }
          } else {
            from = { x: mx, y: my }
            to = { x: px, y: py }
          }
          editorStore.updateTempLine(getEdgePath(from, to))
          return
        }
      }
      // DOM 未就绪时回退到公式
      if (side === 'right') {
        from = getPortPosition(node, portKey, 'right', Math.max(0, portIndex))
        to = { x: mx, y: my }
      } else {
        from = { x: mx, y: my }
        to = getPortPosition(node, portKey, 'left', Math.max(0, portIndex))
      }
      editorStore.updateTempLine(getEdgePath(from, to))
    }

    const onMouseUp = (e) => {
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)

      if (!editorStore.connecting) return

      // 提前从 dataTransfer 中获取字段映射拖拽数据
      let dragFieldMapping = null
      try {
        const fieldData = e.dataTransfer?.getData?.('application/output-field')
        if (fieldData) {
          const fd = JSON.parse(fieldData)
          dragFieldMapping = { [fd.fieldPath]: { key: fd.fieldKey, type: fd.fieldType, label: fd.fieldLabel } }
        }
      } catch {/* ignore */}

      // 检查是否落在某个端口上
      const targetPortEl = e.target.closest('[data-port-key]')
      if (targetPortEl) {
        const targetNodeEl = targetPortEl.closest('[data-node-id]')
        const targetNodeId = targetNodeEl?.dataset?.nodeId
        const targetPortKey = targetPortEl.dataset?.portKey
        const targetSide = targetPortEl.dataset?.portSide

        if (targetNodeId && targetNodeId !== node.id && targetSide !== side) {
          handleDrop(targetNodeId, targetPortKey, targetSide, dragFieldMapping)
        }
      }

      editorStore.finishConnection()
    }

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  }

  /**
   * 处理连线 drop 到目标端口
   * @param {string} targetNodeId - 目标节点 ID
   * @param {string} targetPortKey - 目标端口 key
   * @param {string} targetSide - 目标端口侧
   * @param {object|null} dragFieldMapping - 从拖拽数据中提取的字段映射（如果有）
   */
  function handleDrop(targetNodeId, targetPortKey, targetSide, dragFieldMapping = null) {
    const src = editorStore.connSource
    if (!src) return

    let sourceId, sourcePort, targetId, targetPort

    if (src.side === 'right' && targetSide === 'left') {
      sourceId = src.nodeId
      sourcePort = src.portKey
      targetId = targetNodeId
      targetPort = targetPortKey
    } else if (src.side === 'left' && targetSide === 'right') {
      // 反向：从输入拖到输出
      sourceId = targetNodeId
      sourcePort = targetPortKey
      targetId = src.nodeId
      targetPort = src.portKey
    } else {
      return
    }

    // 数据类型校验（端口级别 + 字段映射级别）
    const sourceNodeType = nodeTypesStore.getByName(
      chainDataStore.nodes.find(n => n.id === sourceId)?.type
    )
    const targetNodeType = nodeTypesStore.getByName(
      chainDataStore.nodes.find(n => n.id === targetId)?.type
    )

    const validation = validateConnection(sourceNodeType, sourcePort, targetNodeType, targetPort, dragFieldMapping)
    if (!validation.valid) {
      editorStore.updateTempLineValidation(false, validation.reason)
      return
    }

    // 目标端口已连接检查
    if (!isMultiPort(targetNodeType, targetPort, 'inputs') &&
        isTargetPortConnected(chainDataStore.edges, targetId, targetPort)) {
      editorStore.updateTempLineValidation(false, '目标端口已被连接')
      return
    }

    const edge = chainDataStore.addEdge(
      sourceId,
      sourcePort,
      targetId,
      targetPort,
      dragFieldMapping,
      dragFieldMapping && Object.keys(dragFieldMapping).length === 1
        ? {
            language: 'python',
            expression: (() => {
              const [sourcePath, mapping] = Object.entries(dragFieldMapping)[0]
              return `{"${mapping?.targetKey || sourcePath.split('.').pop()}": input.${sourcePath}}`
            })(),
          }
        : null,
    )

    // 如果有字段映射数据，存储到边上
    if (dragFieldMapping && edge) {
      chainDataStore.updateEdge(edge.id, { fieldMapping: dragFieldMapping })
    }

    return edge
  }

  return { startPortDrag, handleDrop }
}
