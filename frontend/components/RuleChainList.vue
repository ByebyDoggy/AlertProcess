<template>
  <div>
    <h3 class="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">已有规则链</h3>
    <div class="space-y-2">
      <div v-for="chain in chains" :key="chain.id"
           @click="selectChain(chain)"
           :class="{'bg-blue-600': currentChain && currentChain.id === chain.id}"
           class="bg-gray-700 hover:bg-gray-600 rounded-lg p-3 border border-gray-600 cursor-pointer transition">
        <div class="text-sm text-gray-200">{{ chain.name }}</div>
        <div class="text-xs text-gray-400 mt-1">{{ chain.enabled ? '已启用' : '已禁用' }}</div>
      </div>
      <div v-if="chains.length === 0" class="text-xs text-gray-500 text-center py-2">
        暂无规则链
      </div>
    </div>
    
    <div class="flex gap-2 mt-4">
      <button @click="clearCanvas" 
              class="flex-1 px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-white text-sm transition">
        清空画布
      </button>
      <button @click="createNew" 
              class="flex-1 px-3 py-2 bg-green-600 hover:bg-green-700 rounded-lg text-white text-sm transition">
        新建规则链
      </button>
    </div>
  </div>
</template>

<script>
export default {
  name: 'RuleChainList',
  props: {
    chains: {
      type: Array,
      default: () => []
    },
    currentChain: {
      type: Object,
      default: null
    }
  },
  emits: ['select', 'create', 'clear'],
  methods: {
    selectChain(chain) {
      this.$emit('select', chain)
    },
    createNew() {
      this.$emit('create')
    },
    clearCanvas() {
      this.$emit('clear')
    }
  }
}
</script>
