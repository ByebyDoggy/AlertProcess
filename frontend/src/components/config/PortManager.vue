<template>
  <div class="space-y-2">
    <label class="block text-xs font-medium text-gray-400">输入端口</label>
    <div class="space-y-1">
      <div
        v-for="(portKey, idx) in portKeys"
        :key="portKey"
        class="flex items-center gap-2 p-2 rounded-lg bg-[#16162a] border border-[#2d2d50]"
      >
        <span class="w-2.5 h-2.5 rounded-full bg-indigo-500 flex-shrink-0"></span>
        <span class="text-xs text-gray-300 flex-1">{{ portKey }}</span>
        <span v-if="isConnected(portKey)" class="text-[10px] text-green-400">已连接</span>
        <button
          v-if="!isConnected(portKey) && portKeys.length > 1"
          @click="removePort(idx)"
          class="text-red-400 hover:text-red-300 text-sm"
        >&times;</button>
      </div>
    </div>
    <button @click="addPort" class="text-xs text-indigo-400 hover:text-indigo-300 transition">
      + 添加端口
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useChainDataStore } from '../../stores/chainData.js'

const props = defineProps({
  nodeId: { type: String, required: true },
  portKeys: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:portKeys'])

const chainDataStore = useChainDataStore()

function isConnected(portKey) {
  return chainDataStore.edges.some(e => e.target === props.nodeId && e.targetPort === portKey)
}

function addPort() {
  const maxIdx = props.portKeys.reduce((max, key) => {
    const match = key.match(/input_(\d+)/)
    return match ? Math.max(max, parseInt(match[1])) : max
  }, -1)
  emit('update:portKeys', [...props.portKeys, `input_${maxIdx + 1}`])
}

function removePort(idx) {
  const updated = [...props.portKeys]
  updated.splice(idx, 1)
  emit('update:portKeys', updated)
}
</script>
