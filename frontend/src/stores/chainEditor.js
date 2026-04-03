import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useChainEditorStore = defineStore('chainEditor', () => {
  const selectedNodeId = ref(null)
  const selectedEdgeId = ref(null)
  const showNodeConfig = ref(false)
  const showEdgeConfig = ref(false)
  const saving = ref(false)
  const validationErrors = ref([])
  const validationValid = ref(true)

  // 临时连线状态
  const connecting = ref(false)
  const connSource = ref(null) // { nodeId, portKey, side, dataType }
  const tempLine = ref('')

  // 临时连线校验状态
  const tempLineValid = ref(true)
  const tempLineReason = ref('')

  // 画布缩放和平移
  const zoom = ref(1)
  const panX = ref(0)
  const panY = ref(0)

  const selectedNode = computed(() => null) // 需要注入 chainData store
  const selectedEdge = computed(() => null)

  function selectNode(nodeId) {
    selectedNodeId.value = nodeId
    selectedEdgeId.value = null
    showEdgeConfig.value = false
  }

  function selectEdge(edgeId) {
    selectedEdgeId.value = edgeId
    selectedNodeId.value = null
    showNodeConfig.value = false
  }

  function clearSelection() {
    selectedNodeId.value = null
    selectedEdgeId.value = null
  }

  function openNodeConfig(nodeId) {
    selectedNodeId.value = nodeId
    showNodeConfig.value = true
    showEdgeConfig.value = false
  }

  function closeNodeConfig() {
    showNodeConfig.value = false
  }

  function openEdgeConfig(edgeId) {
    selectedEdgeId.value = edgeId
    showEdgeConfig.value = true
    showNodeConfig.value = false
  }

  function closeEdgeConfig() {
    showEdgeConfig.value = false
  }

  function startConnection(nodeId, portKey, side, dataType) {
    connecting.value = true
    connSource.value = { nodeId, portKey, side, dataType }
    tempLine.value = ''
    tempLineValid.value = true
    tempLineReason.value = ''
  }

  function updateTempLine(path) {
    tempLine.value = path
  }

  function updateTempLineValidation(valid, reason = '') {
    tempLineValid.value = valid
    tempLineReason.value = reason
  }

  function finishConnection() {
    connecting.value = false
    connSource.value = null
    tempLine.value = ''
    tempLineValid.value = true
    tempLineReason.value = ''
  }

  function cancelConnection() {
    connecting.value = false
    connSource.value = null
    tempLine.value = ''
    tempLineValid.value = true
    tempLineReason.value = ''
  }

  function setZoom(newZoom) {
    zoom.value = Math.max(0.2, Math.min(3, newZoom))
  }

  function resetView() {
    zoom.value = 1
    panX.value = 0
    panY.value = 0
  }

  return {
    selectedNodeId, selectedEdgeId,
    showNodeConfig, showEdgeConfig,
    saving, validationErrors, validationValid,
    selectedNode, selectedEdge,
    connecting, connSource, tempLine, tempLineValid, tempLineReason,
    zoom, panX, panY,
    selectNode, selectEdge, clearSelection,
    openNodeConfig, closeNodeConfig,
    openEdgeConfig, closeEdgeConfig,
    startConnection, updateTempLine, updateTempLineValidation,
    finishConnection, cancelConnection,
    setZoom, resetView,
  }
})
