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
            : isChainOpen(chain.id)
            ? 'bg-blue-600/10 border-blue-500/30'
            : 'bg-gray-750 border-gray-600 hover:bg-gray-600'
        ]"
      >
        <div class="flex items-center justify-between gap-2">
          <div class="text-sm text-gray-200 font-medium truncate flex-1">{{ chain.name }}</div>
          <!-- 启用/禁用开关 -->
          <button
            @click.stop="$emit('toggle', { id: chain.id, enabled: !chain.enabled })"
            :class="[
              'flex-shrink-0 relative w-9 h-5 rounded-full transition-colors duration-200 focus:outline-none',
              chain.enabled ? 'bg-emerald-500' : 'bg-gray-600'
            ]"
            :title="chain.enabled ? '点击禁用' : '点击启用'"
          >
            <span
              :class="[
                'absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform duration-200',
                chain.enabled ? 'translate-x-4' : ''
              ]"
            ></span>
          </button>
        </div>
        <div class="flex items-center gap-2 mt-1">
          <span class="text-xs px-1.5 py-0.5 rounded" :class="chain.enabled ? 'bg-green-500/20 text-green-400' : 'bg-gray-700 text-gray-400'">
            {{ chain.enabled ? '运行中' : '已停止' }}
          </span>
          <span v-if="isChainOpen(chain.id) && currentId !== chain.id" class="text-xs px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-400">已打开</span>
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
import { useTabStore } from '../../stores/tabStore.js'

const tabStore = useTabStore()

defineProps({
  chains: { type: Array, default: () => [] },
  currentId: { type: String, default: null },
})
defineEmits(['select', 'create', 'clear', 'toggle'])

function isChainOpen(chainId) {
  return tabStore.isChainOpen(chainId)
}
</script>
