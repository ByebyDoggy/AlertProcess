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
          <span v-if="chainDataStore.isModified" class="text-xs text-yellow-400/70">未保存</span>
          <button @click="handleImportFile"
            class="px-3 py-1.5 bg-gray-600 hover:bg-gray-500 rounded-lg text-white text-sm font-medium transition">
            导入文件
          </button>
          <button @click="handleExportFile" :disabled="chainDataStore.nodes.length === 0"
            class="px-3 py-1.5 bg-gray-600 hover:bg-gray-500 disabled:bg-[#3d3d60] rounded-lg text-white text-sm font-medium transition">
            导出文件
          </button>
          <button @click="handleSave" :disabled="saving"
            class="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:bg-[#3d3d60] rounded-lg text-white text-sm font-medium transition">
            {{ saving ? '保存中...' : '保存到服务器' }}
          </button>
        </div>
      </div>
    </header>

    <!-- Toolbar -->
    <div class="px-5 py-2 border-b border-[#2d2d50] flex items-center justify-between bg-[#16162a]/80 flex-shrink-0">
      <div class="flex items-center gap-3 flex-wrap">
        <input v-model="chainDataStore.chainName" placeholder="规则链名称..." class="form-input !w-52 !py-1.5">
        <input v-model="chainDataStore.chainDescription" placeholder="描述（可选）..." class="form-input !w-64 !py-1.5">
        <label class="flex items-center gap-1.5 text-gray-400 text-sm cursor-pointer">
          <input type="checkbox" v-model="chainDataStore.chainEnabled" class="w-3.5 h-3.5 rounded"> 启用
        </label>
      </div>
      <div v-if="chainDataStore.currentChainId || chainDataStore.nodes.length > 0" class="flex items-center gap-2">
        <button @click="handleValidate" :disabled="validating"
          class="px-3 py-1.5 bg-emerald-600/80 hover:bg-emerald-600 disabled:bg-[#3d3d60] rounded-lg text-white text-sm font-medium transition">
          {{ validating ? '验证中...' : '验证规则链' }}
        </button>
        <button @click="handleDelete" v-if="chainDataStore.currentChainId" class="px-3 py-1.5 bg-red-600/80 hover:bg-red-600 rounded-lg text-white text-sm transition">
          删除
        </button>
      </div>
    </div>

    <!-- Main content -->
    <div class="flex-1 flex min-h-0">
      <!-- Node palette -->
      <NodePalette />

      <div class="flex-1 flex min-w-0">
        <!-- Chain list sidebar -->
        <Sidebar
          :chains="chainDataStore.chains"
          :current-id="chainDataStore.currentChainId"
          @select="chainDataStore.loadChain"
          @create="chainDataStore.createNew"
          @clear="chainDataStore.clearCanvas"
        />

        <!-- Canvas -->
        <Canvas />
      </div>
    </div>

    <!-- Validation result panel -->
    <div v-if="validationResult" class="border-t border-[#2d2d50] bg-[#16162a]/95 flex-shrink-0 max-h-48 overflow-y-auto">
      <div class="px-5 py-3">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-medium" :class="validationResult.valid ? 'text-emerald-400' : 'text-red-400'">
            {{ validationResult.valid ? '&#10003; 规则链验证通过' : '&#10007; 规则链验证失败' }}
          </span>
          <div class="flex items-center gap-3 text-xs text-gray-500">
            <span>{{ validationResult.stats?.node_count || 0 }} 个节点</span>
            <span>{{ validationResult.stats?.edge_count || 0 }} 条连线</span>
            <button @click="validationResult = null" class="text-gray-500 hover:text-gray-300 ml-2">&#10005;</button>
          </div>
        </div>
        <div v-if="validationResult.errors.length" class="space-y-1">
          <div v-for="(err, i) in validationResult.errors" :key="'e'+i"
               class="flex items-start gap-2 text-xs text-red-400 bg-red-500/10 rounded px-2.5 py-1.5">
            <span class="shrink-0 mt-0.5">&#9679;</span>
            <span>{{ err.message }}</span>
          </div>
        </div>
        <div v-if="validationResult.warnings.length" class="space-y-1 mt-1.5">
          <div v-for="(w, i) in validationResult.warnings" :key="'w'+i"
               class="flex items-start gap-2 text-xs text-yellow-400 bg-yellow-500/10 rounded px-2.5 py-1.5">
            <span class="shrink-0 mt-0.5">&#9650;</span>
            <span>{{ w.message }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Config panels -->
    <NodeConfigPanel
      :node="selectedNode"
      :visible="editorStore.showNodeConfig"
      @save="onNodeConfigSave"
      @close="editorStore.closeNodeConfig"
    />

    <EdgeInfoPanel
      :edge="selectedEdge"
      :visible="editorStore.showEdgeConfig"
      @delete="onEdgeDelete"
      @close="editorStore.closeEdgeConfig"
    />

    <Toast :message="toast.message" :type="toast.type" :visible="toast.visible" />
  </div>
</template>

<script setup>
import { onMounted, reactive, computed, ref } from 'vue'
import { useChainDataStore } from '../stores/chainData.js'
import { useChainEditorStore } from '../stores/chainEditor.js'
import { useNodeTypes } from '../composables/useNodeTypes.js'
import { useKeyboard } from '../composables/useKeyboard.js'
import * as chainApi from '../api/ruleChain.js'

import NodePalette from '../components/palette/NodePalette.vue'
import Sidebar from '../components/layout/Sidebar.vue'
import Canvas from '../components/editor/Canvas.vue'
import NodeConfigPanel from '../components/config/NodeConfigPanel.vue'
import EdgeInfoPanel from '../components/config/EdgeInfoPanel.vue'
import Toast from '../components/common/Toast.vue'

const chainDataStore = useChainDataStore()
const editorStore = useChainEditorStore()

// Load node types
useNodeTypes()

// Toast
const toast = reactive({ message: '', type: 'info', visible: false })
let toastTimer = null
function showToast(msg, type = 'info') {
  if (toastTimer) clearTimeout(toastTimer)
  toast.message = msg
  toast.type = type
  toast.visible = true
  toastTimer = setTimeout(() => { toast.visible = false }, 3000)
}

// Selected node/edge
const selectedNode = computed(() =>
  chainDataStore.nodes.find(n => n.id === editorStore.selectedNodeId) || null
)
const selectedEdge = computed(() =>
  chainDataStore.edges.find(e => e.id === editorStore.selectedEdgeId) || null
)

// Saving state
const saving = ref(false)
const validating = ref(false)
const validationResult = ref(null)

function onNodeConfigSave(updatedNode) {
  chainDataStore.updateNode(updatedNode.id, { label: updatedNode.label })
  chainDataStore.updateNodeConfig(updatedNode.id, updatedNode.config)
  editorStore.closeNodeConfig()
  showToast('节点配置已更新', 'success')
}

function onEdgeDelete() {
  if (editorStore.selectedEdgeId) {
    chainDataStore.removeEdge(editorStore.selectedEdgeId)
    editorStore.clearSelection()
    showToast('连接已删除', 'info')
  }
}

async function handleSave() {
  try {
    saving.value = true
    await chainDataStore.save()
    showToast('保存成功', 'success')
  } catch (e) {
    showToast(`保存失败: ${e.message}`, 'error')
  } finally {
    saving.value = false
  }
}

function handleExportFile() {
  const data = {
    name: chainDataStore.chainName || '未命名规则链',
    description: chainDataStore.chainDescription,
    enabled: chainDataStore.chainEnabled,
    nodes: chainDataStore.nodes,
    edges: chainDataStore.edges,
  }
  const json = JSON.stringify(data, null, 2)
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${data.name}.json`
  a.click()
  URL.revokeObjectURL(url)
  showToast('已导出文件', 'success')
}

function handleImportFile() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.json'
  input.onchange = (e) => {
    const file = e.target.files[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      try {
        const data = JSON.parse(ev.target.result)
        if (!data.nodes || !Array.isArray(data.nodes)) {
          showToast('文件格式错误：缺少 nodes 数组', 'error')
          return
        }
        if (!data.edges || !Array.isArray(data.edges)) {
          showToast('文件格式错误：缺少 edges 数组', 'error')
          return
        }
        chainDataStore.currentChainId = null
        chainDataStore.chainName = data.name || file.name.replace(/\.json$/, '')
        chainDataStore.chainDescription = data.description || ''
        chainDataStore.chainEnabled = data.enabled !== false
        chainDataStore.nodes = data.nodes
        chainDataStore.edges = data.edges
        editorStore.clearSelection()
        showToast(`已导入：${chainDataStore.chainName}（${data.nodes.length} 节点 / ${data.edges.length} 连线）`, 'success')
      } catch (err) {
        showToast(`导入失败：无法解析 JSON 文件`, 'error')
      }
    }
    reader.readAsText(file)
  }
  input.click()
}

async function handleDelete() {
  if (!chainDataStore.currentChainId) return
  if (!confirm('确定要删除这条规则链吗？')) return
  try {
    await chainDataStore.deleteChain(chainDataStore.currentChainId)
    showToast('已删除', 'success')
  } catch (e) {
    showToast(`删除失败: ${e.message}`, 'error')
  }
}

async function handleValidate() {
  if (chainDataStore.nodes.length === 0) {
    showToast('画布为空，无法验证', 'error')
    return
  }
  try {
    validating.value = true
    validationResult.value = null
    const result = await chainApi.validateChain(chainDataStore.nodes, chainDataStore.edges)
    validationResult.value = result
    if (result.valid) {
      showToast(`验证通过：${result.stats?.node_count} 节点 / ${result.stats?.edge_count} 连线`, 'success')
    } else {
      showToast(`验证失败：${result.errors.length} 个错误`, 'error')
    }
  } catch (e) {
    showToast(`验证请求失败: ${e.message}`, 'error')
  } finally {
    validating.value = false
  }
}

// Keyboard shortcuts
useKeyboard({
  onSave: handleSave,
  onToast: showToast,
})

// Initialize
onMounted(() => {
  chainDataStore.fetchChains()
})
</script>
