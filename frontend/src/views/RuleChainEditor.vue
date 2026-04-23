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
          <button @click="handleSave" :disabled="saving || !tabStore.activeTab"
            class="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:bg-[#3d3d60] rounded-lg text-white text-sm font-medium transition">
            {{ saving ? '保存中...' : '保存到服务器' }}
          </button>
        </div>
      </div>
    </header>

    <!-- Toolbar -->
    <div v-if="tabStore.activeTab" class="px-5 py-2 border-b border-[#2d2d50] flex items-center justify-between bg-[#16162a]/80 flex-shrink-0">
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
        <button @click="showTestRun = true" v-if="chainDataStore.currentChainId"
          class="px-3 py-1.5 bg-amber-600/80 hover:bg-amber-600 rounded-lg text-white text-sm font-medium transition">
          &#9889; 测试运行
        </button>
        <button @click="handleDelete" v-if="chainDataStore.currentChainId" class="px-3 py-1.5 bg-red-600/80 hover:bg-red-600 rounded-lg text-white text-sm transition">
          删除
        </button>
      </div>
    </div>

    <!-- Tab Bar -->
    <TabBar
      @switch="handleTabSwitch"
      @close="handleTabClose"
      @closeOthers="handleTabCloseOthers"
      @closeRight="handleTabCloseRight"
    />

    <!-- Main content -->
    <div class="flex-1 flex min-h-0">
      <!-- Chain list sidebar (always visible) -->
      <Sidebar
        :chains="chainDataStore.chains"
        :current-id="chainDataStore.currentChainId"
        @select="handleChainSelect"
        @create="handleCreateNew"
        @clear="chainDataStore.clearCanvas"
        @toggle="handleToggleEnabled"
      />

      <div v-if="tabStore.activeTab" class="flex-1 flex min-w-0">
        <!-- Node palette -->
        <NodePalette />

        <!-- Canvas -->
        <Canvas @open-test="handleOpenNodeTest" />
      </div>

      <!-- Empty state when no tabs are open -->
      <div v-else class="flex-1 flex items-center justify-center text-gray-500">
        <div class="text-center">
          <div class="text-4xl mb-3 opacity-30">&#x1F517;</div>
          <p class="text-sm">点击左侧规则链列表打开编辑器，或新建规则链</p>
        </div>
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
        <div v-if="(validationResult.errors || []).length" class="space-y-1">
          <div v-for="(err, i) in (validationResult.errors || [])" :key="'e'+i"
               class="flex items-start gap-2 text-xs text-red-400 bg-red-500/10 rounded px-2.5 py-1.5">
            <span class="shrink-0 mt-0.5">&#9679;</span>
            <span>{{ err.message || err || '(未知错误)' }}</span>
          </div>
        </div>
        <div v-if="(validationResult.warnings || []).length" class="space-y-1 mt-1.5">
          <div v-for="(w, i) in (validationResult.warnings || [])" :key="'w'+i"
               class="flex items-start gap-2 text-xs text-yellow-400 bg-yellow-500/10 rounded px-2.5 py-1.5">
            <span class="shrink-0 mt-0.5">&#9650;</span>
            <span>{{ w.message || w || '(未知警告)' }}</span>
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

    <TestRunPanel
      v-if="showTestRun"
      :chain-id="chainDataStore.currentChainId"
      @close="showTestRun = false"
    />

    <!-- 单节点测试面板 (n8n 式逐节点调试) -->
    <NodeTestPanel
      v-if="testNodeId"
      :node-id="testNodeId"
      @close="testNodeId = null"
    />

    <!-- 字段选择器 (Object 树浏览选择器) -->
    <FieldPicker
      :visible="fieldPickerVisible"
      :node-id="fieldPickerData.nodeId"
      :input-field="fieldPickerData.inputField"
      :all-fields="fieldPickerAllFields"
      :target-node-label="getTargetNodeLabel(fieldPickerData.nodeId)"
      @close="fieldPickerVisible = false"
      @confirm="onFieldPickerConfirm"
    />
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, reactive, computed, ref, watch } from 'vue'
import { useChainDataStore } from '../stores/chainData.js'
import { useChainEditorStore } from '../stores/chainEditor.js'
import { useTabStore } from '../stores/tabStore.js'
import { useNodeTypes } from '../composables/useNodeTypes.js'
import { useKeyboard } from '../composables/useKeyboard.js'
import * as chainApi from '../api/ruleChain.js'
import { outputSchemaToFields } from '../utils/schemaFields.js'

import NodePalette from '../components/palette/NodePalette.vue'
import Sidebar from '../components/layout/Sidebar.vue'
import Canvas from '../components/editor/Canvas.vue'
import TabBar from '../components/editor/TabBar.vue'
import NodeConfigPanel from '../components/config/NodeConfigPanel.vue'
import EdgeInfoPanel from '../components/config/EdgeInfoPanel.vue'
import Toast from '../components/common/Toast.vue'
import TestRunPanel from '../components/editor/TestRunPanel.vue'
import NodeTestPanel from '../components/editor/NodeTestPanel.vue'
import FieldPicker from '../components/editor/FieldPicker.vue'

const chainDataStore = useChainDataStore()
const editorStore = useChainEditorStore()
const tabStore = useTabStore()

// Test run panel
const showTestRun = ref(false)

// Single node test panel (n8n style)
const testNodeId = ref(null)

// Field picker (Object tree selector)
const fieldPickerVisible = ref(false)
const fieldPickerData = reactive({ nodeId: '', inputField: null })

/** Build upstream output fields list with actual test data for field picker */
const fieldPickerAllFields = computed(() => {
  const result = []
  for (const edge of chainDataStore.edges) {
    if (edge.target !== fieldPickerData.nodeId) continue
    const sourceNode = chainDataStore.nodes.find(n => n.id === edge.source)
    if (!sourceNode) continue
    const sourceType = nodeTypesStore.getByName(sourceNode.type)
    // Convert output_schemas (per-port Pydantic JSON Schemas) to old output_fields format
    const outputFields = (() => {
      // 优先使用新的 per-port output_schemas，合并所有端口的字段
      if (sourceType?.output_schemas && sourceType.output_schemas.length > 0) {
        return sourceType.output_schemas.flatMap(s => outputSchemaToFields(s))
      }
      // Fallback: 旧格式
      if (sourceType?.output_schema) return outputSchemaToFields(sourceType.output_schema)
      return sourceType?.output_fields || []
    })()
    if (!outputFields.length) continue
    // Get cached test output for this node
    const testOutput = chainDataStore.nodeTestResults[edge.source]?.output || null
    result.push({
      nodeId: edge.source,
      nodeType: sourceNode.type,
      nodeLabel: sourceType.label || sourceNode.type,
      outputFields,
      testOutput,
    })
  }
  return result
})

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

// ─── 多标签页切换逻辑 ───
/**
 * 切换标签页前保存当前数据，切换后恢复新标签数据
 */
function handleTabSwitch(tabId) {
  if (tabId === tabStore.activeTabId) return
  // 1. 保存当前标签页数据到快照
  captureViewportAndSave()
  // 2. 切换活跃标签
  tabStore.switchTab(tabId)
  // 3. 从新标签快照恢复数据
  chainDataStore.restoreFromTab(tabStore.activeTab)
  // 4. 恢复视口
  restoreViewport()
  // 5. 清除选中状态
  editorStore.clearSelection()
}

function handleTabClose(tabId) {
  const { closedTab, nextTabId } = tabStore.closeTab(tabId)
  if (!closedTab) return
  // 如果关闭的是当前活跃标签，需要恢复下一个标签的数据
  if (nextTabId) {
    chainDataStore.restoreFromTab(tabStore.activeTab)
    restoreViewport()
  } else {
    // 没有更多标签页
    chainDataStore.createNew()
  }
  editorStore.clearSelection()
}

function handleTabCloseOthers(tabId) {
  captureViewportAndSave()
  tabStore.closeOtherTabs(tabId)
  chainDataStore.restoreFromTab(tabStore.activeTab)
  restoreViewport()
  editorStore.clearSelection()
}

function handleTabCloseRight(tabId) {
  captureViewportAndSave()
  const idx = tabStore.tabs.findIndex(t => t.id === tabId)
  if (idx === -1) return
  // 移除该标签右侧的所有标签
  tabStore.tabs.splice(idx + 1)
  // 如果当前活跃标签被移除了，切换到保留的标签
  if (!tabStore.tabs.find(t => t.id === tabStore.activeTabId)) {
    tabStore.activeTabId = tabId
  }
  chainDataStore.restoreFromTab(tabStore.activeTab)
  restoreViewport()
  editorStore.clearSelection()
}

/** 捕获当前视口状态并保存到 tabStore */
function captureViewportAndSave() {
  chainDataStore.setViewportSnapshot(editorStore.zoom, editorStore.panX, editorStore.panY)
  chainDataStore.saveToTab()
}

/** 从当前活跃标签恢复视口 */
function restoreViewport() {
  const tab = tabStore.activeTab
  if (tab?.viewport) {
    editorStore.setViewport(
      tab.viewport.zoom ?? 1,
      tab.viewport.panX ?? 0,
      tab.viewport.panY ?? 0
    )
  }
}

// ─── Sidebar 交互 ───
/**
 * 点击规则链列表项：打开新标签页或切换到已有标签
 */
function handleChainSelect(chain) {
  if (tabStore.isChainOpen(chain.id)) {
    // 已打开：切换到该标签
    const existing = tabStore.findTabByChainId(chain.id)
    if (existing) handleTabSwitch(existing.id)
  } else {
    // 未打开：先保存当前标签，再打开新标签
    captureViewportAndSave()
    tabStore.openTab(chain)
    chainDataStore.loadChain(chain)
    editorStore.resetView()
    editorStore.clearSelection()
  }
}

/**
 * 新建规则链：打开空白标签页
 */
function handleCreateNew() {
  captureViewportAndSave()
  tabStore.openNewTab()
  chainDataStore.createNew()
  editorStore.resetView()
  editorStore.clearSelection()
}

// ─── 保存/删除/导入导出 ───
async function handleSave() {
  try {
    saving.value = true
    const oldChainId = chainDataStore.currentChainId
    await chainDataStore.save()
    // 保存后同步标签页名称和 chainId
    if (tabStore.activeTab) {
      tabStore.updateTabName(tabStore.activeTab.id, chainDataStore.chainName)
      // 新建链首次保存后更新 chainId
      if (!oldChainId && chainDataStore.currentChainId) {
        tabStore.updateTabChainId(tabStore.activeTab.id, chainDataStore.currentChainId)
      }
      // 保存成功后清除脏标记
      tabStore.updateTabData(tabStore.activeTab.id, { isModified: false })
    }
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
        // 导入到当前标签页
        chainDataStore.currentChainId = null
        chainDataStore.chainName = data.name || file.name.replace(/\.json$/, '')
        chainDataStore.chainDescription = data.description || ''
        chainDataStore.chainEnabled = data.enabled !== false
        chainDataStore.nodes = data.nodes
        chainDataStore.edges = data.edges
        editorStore.clearSelection()
        // 更新标签页名称
        if (tabStore.activeTab) {
          tabStore.updateTabName(tabStore.activeTab.id, chainDataStore.chainName)
        }
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
    const chainId = chainDataStore.currentChainId
    await chainDataStore.deleteChain(chainId)
    // 关闭对应标签页
    const { nextTabId } = tabStore.closeTabByChainId(chainId)
    if (nextTabId) {
      chainDataStore.restoreFromTab(tabStore.activeTab)
      restoreViewport()
    } else {
      chainDataStore.createNew()
    }
    showToast('已删除', 'success')
  } catch (e) {
    showToast(`删除失败: ${e.message}`, 'error')
  }
}

function handleOpenNodeTest(nodeId) {
  testNodeId.value = nodeId
}

/** 获取目标节点显示标签 */
function getTargetNodeLabel(nodeId) {
  if (!nodeId) return ''
  const node = chainDataStore.nodes.find(n => n.id === nodeId)
  if (!node) return nodeId.slice(0, 8)
  const nt = nodeTypesStore.getByName(node.type)
  return (nt && nt.label) || node.type
}

/** 字段选择器打开事件 */
function onOpenFieldPicker(data) {
  fieldPickerData.nodeId = data.nodeId
  fieldPickerData.inputField = data.inputField
  fieldPickerVisible = true
}

/** 字段选择器确认回调 — 将选中的字段映射写入边 */
function onFieldPickerConfirm(mappingInfo) {
  const edge = chainDataStore.edges.find(
    e => e.target === mappingInfo.targetNodeId && e.source === mappingInfo.sourceNodeId
  )
  if (edge) {
    const currentMapping = edge.fieldMapping || {}
    currentMapping[mappingInfo.path] = {
      key: mappingInfo.path.split('.').pop(),
      type: typeof mappingInfo.value === 'object' ? 'object' :
            Array.isArray(mappingInfo.value) ? 'array' : typeof mappingInfo.value,
      label: mappingInfo.path,
      targetKey: mappingInfo.targetKey,
    }
    chainDataStore.updateEdge(edge.id, { fieldMapping: currentMapping })
    showToast(`字段映射: ${mappingInfo.path} \u2192 ${mappingInfo.targetKey}`, 'success')
  }
}

async function handleToggleEnabled({ id, enabled }) {
  try {
    await chainDataStore.toggleChainEnabled(id, enabled)
    showToast(`规则链已${enabled ? '启用' : '禁用'}`, 'success')
  } catch (e) {
    showToast(`${enabled ? '启用' : '禁用'}失败: ${e.message}`, 'error')
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
    console.log('[validate] result:', JSON.stringify(result, null, 2))
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

// Watch chainName changes to sync tab name
watch(() => chainDataStore.chainName, (name) => {
  if (tabStore.activeTab) {
    tabStore.updateTabName(tabStore.activeTab.id, name)
  }
})

// Watch isModified to sync tab dirty indicator
watch(() => chainDataStore.isModified, (mod) => {
  if (tabStore.activeTab) {
    tabStore.updateTabData(tabStore.activeTab.id, { isModified: mod })
  }
})

// Keyboard shortcuts
useKeyboard({
  onSave: handleSave,
  onToast: showToast,
})

// Initialize
onMounted(() => {
  chainDataStore.fetchChains()
})

// Cleanup
onUnmounted(() => {
  tabStore.clearAllTabs()
})
</script>
