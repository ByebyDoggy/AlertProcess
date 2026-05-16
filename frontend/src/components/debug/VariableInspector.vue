<script setup lang="ts">
import { ref, computed } from 'vue'
import type { VariableSnapshot } from '@/api/debug'

interface Props {
  variables: VariableSnapshot[]
  maxHeight?: string
}

const props = withDefaults(defineProps<Props>(), {
  maxHeight: '400px'
})

// 搜索关键词
const searchKeyword = ref('')

// 排序方式
const sortBy = ref<'name' | 'type' | 'size'>('name')
const sortOrder = ref<'asc' | 'desc'>('asc')

// 过滤和排序后的变量
const filteredVariables = computed(() => {
  let result = [...props.variables]

  // 按关键词搜索
  if (searchKeyword.value.trim()) {
    const keyword = searchKeyword.value.toLowerCase()
    result = result.filter(v =>
      v.name.toLowerCase().includes(keyword) ||
      v.type_name.toLowerCase().includes(keyword)
    )
  }

  // 排序
  result.sort((a, b) => {
    let compareResult = 0

    switch (sortBy.value) {
      case 'name':
        compareResult = a.name.localeCompare(b.name)
        break
      case 'type':
        compareResult = a.type_name.localeCompare(b.type_name)
        break
      case 'size':
        const sizeA = a.size_bytes || 0
        const sizeB = b.size_bytes || 0
        compareResult = sizeA - sizeB
        break
    }

    return sortOrder.value === 'asc' ? compareResult : -compareResult
  })

  return result
})

// 类型颜色
const getTypeColor = (typeName: string) => {
  const colors: Record<string, string> = {
    int: 'text-green-600 bg-green-100',
    float: 'text-green-600 bg-green-100',
    str: 'text-blue-600 bg-blue-100',
    bool: 'text-orange-600 bg-orange-100',
    list: 'text-purple-600 bg-purple-100',
    dict: 'text-pink-600 bg-pink-100',
    tuple: 'text-purple-600 bg-purple-100',
    set: 'text-purple-600 bg-purple-100',
    NoneType: 'text-gray-600 bg-gray-100'
  }
  return colors[typeName] || 'text-gray-600 bg-gray-100'
}

// 格式化大小
const formatSize = (bytes?: number) => {
  if (!bytes) return 'N/A'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

// 格式化值（处理长字符串）
const formatValue = (value: any) => {
  const str = String(value)
  if (str.length > 100) {
    return str.substring(0, 100) + '...'
  }
  return str
}

// 切换排序
const toggleSort = (field: 'name' | 'type' | 'size') => {
  if (sortBy.value === field) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortBy.value = field
    sortOrder.value = 'asc'
  }
}

// 获取排序图标
const getSortIcon = (field: 'name' | 'type' | 'size') => {
  if (sortBy.value !== field) return '↕'
  return sortOrder.value === 'asc' ? '↑' : '↓'
}
</script>

<template>
  <div class="variable-inspector">
    <!-- 工具栏 -->
    <div class="toolbar flex items-center gap-3 mb-3 p-3 bg-gray-50 rounded-lg">
      <!-- 搜索框 -->
      <div class="flex-1 flex items-center gap-2">
        <label class="text-sm font-medium text-gray-700">搜索:</label>
        <input
          v-model="searchKeyword"
          type="text"
          placeholder="搜索变量名或类型..."
          class="flex-1 max-w-md px-3 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <!-- 统计信息 -->
      <div class="text-sm text-gray-600">
        共 {{ filteredVariables.length }} / {{ variables.length }} 个变量
      </div>
    </div>

    <!-- 变量表格 -->
    <div
      class="variable-table border border-gray-300 rounded-lg overflow-auto bg-white"
      :style="{ maxHeight: props.maxHeight }"
    >
      <table class="w-full text-sm">
        <thead class="bg-gray-100 sticky top-0 z-10">
          <tr>
            <th
              class="px-4 py-2 text-left font-semibold text-gray-700 cursor-pointer hover:bg-gray-200 transition-colors"
              @click="toggleSort('name')"
            >
              变量名 <span class="text-xs">{{ getSortIcon('name') }}</span>
            </th>
            <th
              class="px-4 py-2 text-left font-semibold text-gray-700 cursor-pointer hover:bg-gray-200 transition-colors"
              @click="toggleSort('type')"
            >
              类型 <span class="text-xs">{{ getSortIcon('type') }}</span>
            </th>
            <th class="px-4 py-2 text-left font-semibold text-gray-700">
              值
            </th>
            <th
              class="px-4 py-2 text-right font-semibold text-gray-700 cursor-pointer hover:bg-gray-200 transition-colors"
              @click="toggleSort('size')"
            >
              大小 <span class="text-xs">{{ getSortIcon('size') }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="filteredVariables.length === 0">
            <td colspan="4" class="px-4 py-8 text-center text-gray-500">
              {{ variables.length === 0 ? '暂无变量' : '没有匹配的变量' }}
            </td>
          </tr>

          <tr
            v-for="(variable, index) in filteredVariables"
            :key="index"
            class="border-t border-gray-200 hover:bg-gray-50 transition-colors"
          >
            <!-- 变量名 -->
            <td class="px-4 py-3 font-mono font-semibold text-gray-800">
              {{ variable.name }}
            </td>

            <!-- 类型 -->
            <td class="px-4 py-3">
              <span
                class="px-2 py-1 text-xs font-semibold rounded"
                :class="getTypeColor(variable.type_name)"
              >
                {{ variable.type_name }}
              </span>
            </td>

            <!-- 值 -->
            <td class="px-4 py-3 font-mono text-gray-700">
              <div class="max-w-md overflow-hidden">
                <details v-if="String(variable.value).length > 100">
                  <summary class="cursor-pointer text-blue-600 hover:text-blue-800">
                    {{ formatValue(variable.value) }}
                  </summary>
                  <pre class="mt-2 p-2 bg-gray-100 rounded text-xs overflow-x-auto">{{ variable.value }}</pre>
                </details>
                <span v-else>{{ variable.value }}</span>
              </div>
            </td>

            <!-- 大小 -->
            <td class="px-4 py-3 text-right text-gray-600 font-mono text-xs">
              {{ formatSize(variable.size_bytes) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.variable-inspector {
  font-family: system-ui, -apple-system, sans-serif;
}

.variable-table {
  font-size: 13px;
}

/* 滚动条样式 */
.variable-table::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.variable-table::-webkit-scrollbar-track {
  background: #f1f1f1;
}

.variable-table::-webkit-scrollbar-thumb {
  background: #888;
  border-radius: 4px;
}

.variable-table::-webkit-scrollbar-thumb:hover {
  background: #555;
}

/* 表格样式 */
table {
  border-collapse: collapse;
}

th {
  user-select: none;
}
</style>
