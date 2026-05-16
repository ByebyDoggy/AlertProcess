<script setup lang="ts">
import { ref, computed } from 'vue'
import type { DebugLog } from '@/api/debug'

interface Props {
  logs: DebugLog[]
  maxHeight?: string
}

const props = withDefaults(defineProps<Props>(), {
  maxHeight: '400px'
})

// 日志级别过滤
const selectedLevel = ref<string>('ALL')
const levels = ['ALL', 'DEBUG', 'INFO', 'WARNING', 'ERROR']

// 搜索关键词
const searchKeyword = ref('')

// 过滤后的日志
const filteredLogs = computed(() => {
  let result = props.logs

  // 按级别过滤
  if (selectedLevel.value !== 'ALL') {
    result = result.filter(log => log.level === selectedLevel.value)
  }

  // 按关键词搜索
  if (searchKeyword.value.trim()) {
    const keyword = searchKeyword.value.toLowerCase()
    result = result.filter(log =>
      log.message.toLowerCase().includes(keyword)
    )
  }

  return result
})

// 日志级别样式
const getLevelClass = (level: string) => {
  const classes: Record<string, string> = {
    DEBUG: 'text-gray-600 bg-gray-100',
    INFO: 'text-blue-600 bg-blue-100',
    WARNING: 'text-yellow-600 bg-yellow-100',
    ERROR: 'text-red-600 bg-red-100'
  }
  return classes[level] || 'text-gray-600 bg-gray-100'
}

// 格式化时间戳
const formatTimestamp = (timestamp: string) => {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', { hour12: false, fractionalSecondDigits: 3 })
}

// 清空搜索
const clearSearch = () => {
  searchKeyword.value = ''
}
</script>

<template>
  <div class="log-viewer">
    <!-- 工具栏 -->
    <div class="toolbar flex items-center gap-3 mb-3 p-3 bg-gray-50 rounded-lg">
      <!-- 级别过滤 -->
      <div class="flex items-center gap-2">
        <label class="text-sm font-medium text-gray-700">级别:</label>
        <select
          v-model="selectedLevel"
          class="px-3 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option v-for="level in levels" :key="level" :value="level">
            {{ level }}
          </option>
        </select>
      </div>

      <!-- 搜索框 -->
      <div class="flex-1 flex items-center gap-2">
        <label class="text-sm font-medium text-gray-700">搜索:</label>
        <div class="relative flex-1 max-w-md">
          <input
            v-model="searchKeyword"
            type="text"
            placeholder="搜索日志消息..."
            class="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            v-if="searchKeyword"
            @click="clearSearch"
            class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
          >
            ✕
          </button>
        </div>
      </div>

      <!-- 统计信息 -->
      <div class="text-sm text-gray-600">
        共 {{ filteredLogs.length }} / {{ logs.length }} 条
      </div>
    </div>

    <!-- 日志列表 -->
    <div
      class="log-list border border-gray-300 rounded-lg overflow-auto bg-white"
      :style="{ maxHeight: props.maxHeight }"
    >
      <div v-if="filteredLogs.length === 0" class="p-4 text-center text-gray-500">
        {{ logs.length === 0 ? '暂无日志' : '没有匹配的日志' }}
      </div>

      <div
        v-for="(log, index) in filteredLogs"
        :key="index"
        class="log-entry border-b border-gray-200 last:border-b-0 hover:bg-gray-50 transition-colors"
      >
        <div class="flex items-start gap-3 p-3">
          <!-- 时间戳 -->
          <div class="text-xs text-gray-500 font-mono whitespace-nowrap">
            {{ formatTimestamp(log.timestamp) }}
          </div>

          <!-- 级别标签 -->
          <div
            class="px-2 py-0.5 text-xs font-semibold rounded whitespace-nowrap"
            :class="getLevelClass(log.level)"
          >
            {{ log.level }}
          </div>

          <!-- 行号 -->
          <div v-if="log.line_number" class="text-xs text-gray-400 font-mono whitespace-nowrap">
            L{{ log.line_number }}
          </div>

          <!-- 消息 -->
          <div class="flex-1 text-sm text-gray-800 break-words font-mono">
            {{ log.message }}
          </div>
        </div>

        <!-- 上下文信息（如果有） -->
        <div v-if="log.context" class="px-3 pb-3">
          <details class="text-xs">
            <summary class="cursor-pointer text-gray-600 hover:text-gray-800">
              查看上下文
            </summary>
            <pre class="mt-2 p-2 bg-gray-100 rounded text-xs overflow-x-auto">{{ JSON.stringify(log.context, null, 2) }}</pre>
          </details>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.log-viewer {
  font-family: 'Courier New', monospace;
}

.log-list {
  font-size: 13px;
}

.log-entry:hover {
  background-color: #f9fafb;
}

/* 滚动条样式 */
.log-list::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.log-list::-webkit-scrollbar-track {
  background: #f1f1f1;
}

.log-list::-webkit-scrollbar-thumb {
  background: #888;
  border-radius: 4px;
}

.log-list::-webkit-scrollbar-thumb:hover {
  background: #555;
}
</style>
