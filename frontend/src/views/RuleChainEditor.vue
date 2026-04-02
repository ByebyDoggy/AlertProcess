<template>
  <div class="h-screen flex flex-col bg-[#1a1a2e]">
    <!-- Header -->
    <header class="bg-[#16162a] border-b border-[#2d2d50] px-5 py-3 flex-shrink-0">
      <div class="flex justify-between items-center">
        <div class="flex items-center gap-4">
          <div>
            <h1 class="text-lg font-bold text-white flex items-center gap-2">
              <span class="text-indigo-400">&#x1F517;</span> 规则链编辑器
            </h1>
            <p class="text-gray-500 text-xs">拖拽式安全检测规则链设计与配置</p>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <div v-if="store.validationErrors.length > 0" class="text-xs text-red-400 max-w-xs truncate">
            {{ store.validationErrors[0] }}
          </div>
          <span v-else-if="store.isModified" class="text-xs text-yellow-400/70">未保存</span>
          <button @click="handleValidate" class="px-3 py-1.5 bg-[#252545] hover:bg-[#2d2d55] rounded-lg text-gray-300 text-sm transition border border-[#2d2d50]">
            验证
          </button>
          <button @click="handleSave" :disabled="store.saving"
            class="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:bg-[#3d3d60] rounded-lg text-white text-sm font-medium transition">
            {{ store.saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </header>

    <!-- Toolbar -->
    <div class="px-5 py-2 border-b border-[#2d2d50] flex items-center justify-between bg-[#16162a]/80 flex-shrink-0">
      <div class="flex items-center gap-3 flex-wrap">
        <input v-model="store.chainName" placeholder="规则链名称..." class="form-input !w-52 !py-1.5">
        <input v-model="store.chainDescription" placeholder="描述（可选）..." class="form-input !w-64 !py-1.5">
        <label class="flex items-center gap-1.5 text-gray-400 text-sm cursor-pointer">
          <input type="checkbox" v-model="store.chainEnabled" class="w-3.5 h-3.5 rounded"> 启用
        </label>
      </div>
      <div v-if="store.currentChainId" class="flex items-center gap-2">
        <button @click="handleDelete" class="px-3 py-1.5 bg-red-600/80 hover:bg-red-600 rounded-lg text-white text-sm transition">
          删除
        </button>
      </div>
    </div>

    <!-- Main content -->
    <div class="flex-1 flex min-h-0">
      <NodePalette />

      <div class="flex-1 flex min-w-0">
        <!-- Chain list sidebar -->
        <div class="w-52 bg-[#1a1a2e] border-r border-[#2d2d50] p-3 overflow-y-auto flex-shrink-0">
          <ChainList :chains="store.chains" :current-id="store.currentChainId"
            @select="store.loadChain" @create="store.createNew" @clear="store.clearCanvas" />
        </div>

        <!-- Canvas -->
        <CanvasEditor
          :nodes="store.nodes" :edges="store.edges"
          :selected-node-id="store.selectedNodeId" :selected-edge-id="store.selectedEdgeId"
          @drop-new="onDropNew"
          @node-click="store.selectNode" @edge-click="onEdgeClick" @canvas-click="store.clearSelection"
          @node-dbl-click="store.openNodeConfig"
          @delete-node="store.removeNode"
          @add-edge="onAddEdge"
          @move-node="store.moveNode" />
      </div>
    </div>

    <!-- Config panels -->
    <NodeConfigEditor :node="store.selectedNode" :visible="store.showNodeConfig"
      @save="onNodeConfigSave" @close="store.closeNodeConfig" />
    <EdgeConfigEditor :edge="store.selectedEdge" :nodes="store.nodes" :visible="store.showEdgeConfig"
      @delete="onEdgeDelete" @close="store.closeEdgeConfig" />
    <Toast :message="toast.message" :type="toast.type" :visible="toast.visible" />
  </div>
</template>

<script setup>
import { onMounted, reactive } from 'vue'
import { useRuleChainStore } from '../stores/ruleChain.js'
import NodePalette from '../components/NodePalette.vue'
import ChainList from '../components/ChainList.vue'
import CanvasEditor from '../components/CanvasEditor.vue'
import NodeConfigEditor from '../components/NodeConfigEditor.vue'
import EdgeConfigEditor from '../components/EdgeConfigEditor.vue'
import Toast from '../components/Toast.vue'

const store = useRuleChainStore()
const toast = reactive({ message: '', type: 'info', visible: false })
let toastTimer = null

function showToast(msg, type = 'info') {
  if (toastTimer) clearTimeout(toastTimer)
  toast.message = msg; toast.type = type; toast.visible = true
  toastTimer = setTimeout(() => { toast.visible = false }, 3000)
}

function onDropNew(type, label, x, y) { store.addNode(type, label, x, y) }

function onEdgeClick(edgeId) {
  store.selectEdge(edgeId)
  store.openEdgeConfig(edgeId)
}

function onAddEdge(sourceId, sourcePort, targetId, targetPort) {
  const edge = store.addEdge(sourceId, sourcePort, targetId, targetPort)
  if (edge) {
    showToast('连接已创建', 'success')
  } else {
    showToast('连接已存在', 'error')
  }
}

function onNodeConfigSave(updatedNode) {
  store.updateNode(updatedNode.id, { label: updatedNode.label })
  store.updateNodeConfig(updatedNode.id, updatedNode.config)
  store.closeNodeConfig()
  showToast('节点配置已更新', 'success')
}

function onEdgeDelete() {
  if (store.selectedEdgeId) {
    store.removeEdge(store.selectedEdgeId)
    showToast('连接已删除', 'info')
  }
}

async function handleValidate() {
  const result = await store.validate()
  if (result.valid) showToast('验证通过', 'success')
  else showToast(`验证失败: ${result.errors.join(', ')}`, 'error')
}

async function handleSave() {
  try { await store.save(); showToast('保存成功', 'success') }
  catch (e) { showToast(`保存失败: ${e.message}`, 'error') }
}

async function handleDelete() {
  if (!store.currentChainId) return
  if (!confirm('确定要删除这条规则链吗？')) return
  try { await store.deleteChain(store.currentChainId); showToast('已删除', 'success') }
  catch (e) { showToast(`删除失败: ${e.message}`, 'error') }
}

onMounted(() => {
  store.fetchChains()

  const handler = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault(); handleSave()
    }
    if (e.key === 'Delete' || e.key === 'Backspace') {
      if (store.showNodeConfig || store.showEdgeConfig) return
      if (document.activeElement?.tagName === 'INPUT' || document.activeElement?.tagName === 'TEXTAREA' || document.activeElement?.tagName === 'SELECT') return
      if (store.selectedNodeId) store.removeNode(store.selectedNodeId)
      else if (store.selectedEdgeId) { store.removeEdge(store.selectedEdgeId); showToast('连接已删除', 'info') }
    }
    if (e.key === 'Escape') {
      store.closeNodeConfig(); store.closeEdgeConfig(); store.clearSelection()
    }
  }
  window.addEventListener('keydown', handler)
})
</script>
