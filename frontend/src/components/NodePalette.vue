<template>
  <div class="w-60 bg-[#1a1a2e] border-r border-[#2d2d50] p-3 overflow-y-auto flex flex-col">
    <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3 px-1">节点组件</h3>
    <div class="space-y-2 flex-1">
      <!-- Flow nodes -->
      <div class="palette-category">流程控制</div>
      <div v-for="nt in flowNodes" :key="nt.type"
        class="palette-item p-2.5 flex items-center gap-2.5"
        draggable="true" @dragstart="onDragStart($event, nt)">
        <div class="w-8 h-8 rounded-lg flex items-center justify-center text-base flex-shrink-0"
          :style="{ background: nt.lightBg, color: nt.color }">
          {{ nt.icon }}
        </div>
        <div class="min-w-0">
          <div class="text-sm text-gray-200 font-medium">{{ nt.label }}</div>
          <div class="text-xs text-gray-500 truncate">{{ nt.description }}</div>
        </div>
      </div>

      <!-- Detection nodes -->
      <div class="palette-category">安全检测</div>
      <div class="palette-item p-2.5 flex items-center gap-2.5"
        draggable="true" @dragstart="onDragStart($event, NODE_TYPES.detector)">
        <div class="w-8 h-8 rounded-lg flex items-center justify-center text-base flex-shrink-0"
          :style="{ background: NODE_TYPES.detector.lightBg, color: NODE_TYPES.detector.color }">
          {{ NODE_TYPES.detector.icon }}
        </div>
        <div class="min-w-0">
          <div class="text-sm text-gray-200 font-medium">{{ NODE_TYPES.detector.label }}</div>
          <div class="text-xs text-gray-500 truncate">{{ NODE_TYPES.detector.description }}</div>
        </div>
      </div>

      <!-- Output nodes -->
      <div class="palette-category">输出</div>
      <div v-for="nt in outputNodes" :key="nt.type"
        class="palette-item p-2.5 flex items-center gap-2.5"
        draggable="true" @dragstart="onDragStart($event, nt)">
        <div class="w-8 h-8 rounded-lg flex items-center justify-center text-base flex-shrink-0"
          :style="{ background: nt.lightBg, color: nt.color }">
          {{ nt.icon }}
        </div>
        <div class="min-w-0">
          <div class="text-sm text-gray-200 font-medium">{{ nt.label }}</div>
          <div class="text-xs text-gray-500 truncate">{{ nt.description }}</div>
        </div>
      </div>
    </div>

    <div class="mt-3 p-2.5 rounded-lg border border-[#2d2d50] bg-[#16162a]">
      <h4 class="text-xs text-gray-400 font-medium mb-1.5">操作指南</h4>
      <ul class="text-xs text-gray-500 space-y-0.5">
        <li>1. 拖入「入口触发器」开始</li>
        <li>2. 从输出端口拖线连接</li>
        <li>3. 双击节点编辑配置</li>
        <li>4. Ctrl+S 保存规则链</li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import { NODE_TYPES } from '../config.js'

const flowNodes = [NODE_TYPES.trigger, NODE_TYPES.condition]
const outputNodes = [NODE_TYPES.action, NODE_TYPES.notifier]

function onDragStart(event, item) {
  event.dataTransfer.setData('nodeType', item.type)
  event.dataTransfer.setData('nodeLabel', item.label)
  event.dataTransfer.effectAllowed = 'copy'
}
</script>
