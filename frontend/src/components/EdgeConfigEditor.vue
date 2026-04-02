<template>
  <Teleport to="body">
    <div v-if="visible && edge" class="fixed inset-0 bg-black/60 modal-overlay flex items-center justify-center z-50" @click.self="$emit('close')">
      <div class="bg-[#1e1e38] rounded-xl p-5 w-full max-w-sm mx-4 border border-[#2d2d50] shadow-2xl">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-base font-bold text-white">连接详情</h3>
          <button @click="$emit('close')" class="text-gray-500 hover:text-white text-2xl leading-none">&times;</button>
        </div>
        <div class="space-y-3">
          <!-- Connection info -->
          <div class="p-3 rounded-lg bg-[#16162a] border border-[#2d2d50] space-y-1.5">
            <div class="flex items-center gap-2 text-xs">
              <span class="text-gray-400 w-10">源:</span>
              <span class="text-white truncate">{{ sourceInfo }}</span>
            </div>
            <div class="flex items-center gap-2 text-xs">
              <span class="text-gray-400 w-10">目标:</span>
              <span class="text-white truncate">{{ targetInfo }}</span>
            </div>
            <div v-if="edge.sourcePort" class="flex items-center gap-2 text-xs">
              <span class="text-gray-400 w-10">端口:</span>
              <span :style="{ color: portColor(edge.sourcePort) }" class="font-medium">{{ portLabel(edge.sourcePort) }}</span>
            </div>
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

const props = defineProps({
  edge: { type: Object, default: null },
  visible: { type: Boolean, default: false },
  nodes: { type: Array, default: () => [] },
})
defineEmits(['save', 'delete', 'close'])

const sourceInfo = computed(() => {
  const n = props.nodes.find(n => n.id === props.edge?.source)
  return n ? n.label : props.edge?.source?.substring(0, 16) || '?'
})

const targetInfo = computed(() => {
  const n = props.nodes.find(n => n.id === props.edge?.target)
  return n ? n.label : props.edge?.target?.substring(0, 16) || '?'
})

function portLabel(key) {
  const labels = { input: '输入', output: '输出', true: '检测到/满足', false: '未检测到/不满足' }
  return labels[key] || key
}

function portColor(key) {
  const colors = { input: '#6366f1', output: '#6366f1', true: '#10b981', false: '#ef4444' }
  return colors[key] || '#6b7280'
}
</script>
