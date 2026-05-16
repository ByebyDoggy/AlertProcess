<template>
  <Teleport to="body">
    <div
      v-if="visible && edge"
      class="fixed inset-0 bg-black/60 modal-overlay flex items-center justify-center z-50"
      @click.self="$emit('close')"
    >
      <div class="bg-[#1e1e38] rounded-xl p-5 w-full max-w-sm mx-4 border border-[#2d2d50] shadow-2xl">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-base font-bold text-white">连接详情</h3>
          <button @click="$emit('close')" class="text-gray-500 hover:text-white text-2xl leading-none">&times;</button>
        </div>

        <div class="space-y-3">
          <div class="p-3 rounded-lg bg-[#16162a] border border-[#2d2d50] space-y-1.5">
            <div class="flex items-center gap-2 text-xs">
              <span class="text-gray-400 w-16">源节点:</span>
              <span class="text-white truncate">{{ sourceLabel }}</span>
            </div>
            <div class="flex items-center gap-2 text-xs">
              <span class="text-gray-400 w-16">源端口:</span>
              <span class="font-medium" :style="{ color: sourcePortColor }">{{ sourcePortLabel }}</span>
            </div>
            <div class="flex items-center gap-2 text-xs">
              <span class="text-gray-400 w-16">目标节点:</span>
              <span class="text-white truncate">{{ targetLabel }}</span>
            </div>
            <div class="flex items-center gap-2 text-xs">
              <span class="text-gray-400 w-16">目标端口:</span>
              <span class="font-medium" :style="{ color: targetPortColor }">{{ targetPortLabel }}</span>
            </div>
          </div>

          <!-- Data type info -->
          <div v-if="typeInfo" class="p-3 rounded-lg bg-[#16162a] border border-[#2d2d50]">
            <div class="text-[10px] text-gray-500 mb-1">数据类型</div>
            <div class="text-xs text-gray-300">{{ typeInfo }}</div>
          </div>

          <div v-if="mappingInfo" class="p-3 rounded-lg bg-[#16162a] border border-[#2d2d50]">
            <div class="text-[10px] text-gray-500 mb-1">字段映射</div>
            <div class="text-xs text-emerald-300 whitespace-pre-wrap">{{ mappingInfo }}</div>
          </div>

          <div v-if="transformerInfo" class="p-3 rounded-lg bg-[#16162a] border border-[#2d2d50]">
            <div class="text-[10px] text-gray-500 mb-1">输入转换表达式</div>
            <div class="text-xs text-indigo-300 whitespace-pre-wrap break-all">{{ transformerInfo }}</div>
          </div>
        </div>

        <div class="flex justify-end gap-2 mt-5">
          <button @click="$emit('delete')" class="px-4 py-2 bg-red-600/80 hover:bg-red-600 rounded-lg text-white text-sm transition">删除</button>
          <button @click="$emit('close')" class="px-4 py-2 bg-[#16162a] hover:bg-[#252545] rounded-lg text-gray-300 text-sm transition border border-[#2d2d50]">关闭</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { computed } from 'vue'
import { useChainDataStore } from '../../stores/chainData.js'
import { useNodeTypesStore } from '../../stores/nodeTypes.js'
import { DATA_TYPE_COLORS } from '../../config/connectionRules.js'

const props = defineProps({
  edge: { type: Object, default: null },
  visible: { type: Boolean, default: false },
})
defineEmits(['delete', 'close'])

const chainDataStore = useChainDataStore()
const nodeTypesStore = useNodeTypesStore()

const sourceNode = computed(() => chainDataStore.nodes.find(n => n.id === props.edge?.source))
const targetNode = computed(() => chainDataStore.nodes.find(n => n.id === props.edge?.target))
const sourceNodeType = computed(() => nodeTypesStore.getByName(sourceNode.value?.type))
const targetNodeType = computed(() => nodeTypesStore.getByName(targetNode.value?.type))

const sourceLabel = computed(() => sourceNode.value?.label || props.edge?.source?.substring(0, 16) || '?')
const targetLabel = computed(() => targetNode.value?.label || props.edge?.target?.substring(0, 16) || '?')

function getPortDef(nodeType, portKey, portType) {
  const ports = nodeType?.[portType] || []
  return ports.find(p => p.key === portKey)
}

const sourcePortDef = computed(() => getPortDef(sourceNodeType.value, props.edge?.sourcePort, 'outputs'))
const targetPortDef = computed(() => getPortDef(targetNodeType.value, props.edge?.targetPort, 'inputs'))

const sourcePortLabel = computed(() => sourcePortDef.value?.label || props.edge?.sourcePort || 'output')
const targetPortLabel = computed(() => targetPortDef.value?.label || props.edge?.targetPort || 'input')
const sourcePortColor = computed(() => DATA_TYPE_COLORS[sourcePortDef.value?.data_type] || '#6b7280')
const targetPortColor = computed(() => DATA_TYPE_COLORS[targetPortDef.value?.data_type] || '#6b7280')

const typeInfo = computed(() => {
  if (!sourcePortDef.value) return ''
  return `${sourcePortDef.value.data_type} → ${targetPortDef.value?.data_type || '?'}`
})

const mappingInfo = computed(() => {
  const mapping = props.edge?.fieldMapping
  if (!mapping || Object.keys(mapping).length === 0) return ''
  return Object.entries(mapping)
    .map(([sourcePath, target]) => `${sourcePath} → ${target?.targetKey || '?'}`)
    .join('\n')
})

const transformerInfo = computed(() => {
  const transformer = props.edge?.inputTransformer
  if (!transformer?.expression) return ''
  return transformer.expression
})
</script>
