<template>
  <div class="w-52 bg-[#1a1a2e] border-r border-[#2d2d50] p-3 overflow-y-auto flex-shrink-0">
    <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3 px-1">已有规则链</h3>
    <div class="space-y-1.5">
      <div
        v-for="chain in chains"
        :key="chain.id"
        @click="$emit('select', chain)"
        :class="[
          'rounded-lg p-2.5 border cursor-pointer transition text-left',
          currentId && currentId === chain.id
            ? 'bg-blue-600/30 border-blue-500'
            : 'bg-gray-750 border-gray-600 hover:bg-gray-600'
        ]"
      >
        <div class="text-sm text-gray-200 font-medium truncate">{{ chain.name }}</div>
        <div class="flex items-center gap-2 mt-0.5">
          <span class="text-xs px-1.5 py-0.5 rounded" :class="chain.enabled ? 'bg-green-500/20 text-green-400' : 'bg-gray-600 text-gray-400'">
            {{ chain.enabled ? '启用' : '禁用' }}
          </span>
          <span class="text-xs text-gray-500">{{ formatTimestamp(chain.updated_at || chain.created_at) }}</span>
        </div>
      </div>
      <div v-if="chains.length === 0" class="text-xs text-gray-500 text-center py-3">
        暂无规则链
      </div>
    </div>

    <div class="flex gap-2 mt-3">
      <button
        @click="$emit('clear')"
        class="flex-1 px-2 py-1.5 bg-gray-700 hover:bg-gray-600 rounded-lg text-white text-xs transition"
      >
        清空画布
      </button>
      <button
        @click="$emit('create')"
        class="flex-1 px-2 py-1.5 bg-green-600 hover:bg-green-700 rounded-lg text-white text-xs transition"
      >
        新建规则链
      </button>
    </div>
  </div>
</template>

<script setup>
import { formatTimestamp } from '../../utils/helpers.js'

defineProps({
  chains: { type: Array, default: () => [] },
  currentId: { type: String, default: null },
})
defineEmits(['select', 'create', 'clear'])
</script>
