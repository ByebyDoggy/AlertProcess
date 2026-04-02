<template>
  <div class="w-72 bg-gray-800 border-r border-gray-700 p-4 overflow-y-auto">
    <h3 class="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">节点组件</h3>
    <div class="space-y-2">
      <div v-for="(item, type) in NODE_TYPES" :key="type" 
           class="palette-item bg-gray-700 hover:bg-gray-600 rounded-lg p-3 border border-gray-600"
           draggable="true" @dragstart="onDragStart($event, item)">
        <div class="flex items-center gap-2">
          <span :class="item.iconColor" class="text-lg">{{ item.icon }}</span>
          <div>
            <span class="text-sm text-gray-200">{{ item.label }}</span>
            <div class="text-xs text-gray-400">{{ item.description }}</div>
          </div>
        </div>
      </div>
    </div>

    <div class="mt-6 p-3 bg-gray-700 rounded-lg border border-gray-600">
      <h4 class="text-xs text-gray-300 mb-2">💡 使用说明</h4>
      <ul class="text-xs text-gray-400 space-y-1">
        <li>• 拖拽节点到画布</li>
        <li>• 双击节点进行配置</li>
        <li>• 拖拽节点边缘的圆点进行连线</li>
        <li>• 点击连线可以删除连接</li>
      </ul>
    </div>
  </div>
</template>

<script>
export default {
  name: 'NodePalette',
  data() {
    return {
      NODE_TYPES: window.NODE_TYPES
    }
  },
  methods: {
    onDragStart(event, item) {
      event.dataTransfer.setData('nodeType', item.type)
      event.dataTransfer.setData('nodeLabel', item.label)
    }
  }
}
</script>

<style scoped>
.palette-item {
  cursor: grab;
}

.palette-item:active {
  cursor: grabbing;
}
</style>
