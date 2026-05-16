<script setup lang="ts">
import { ref, computed } from 'vue'
import LogViewer from './LogViewer.vue'
import VariableInspector from './VariableInspector.vue'
import type { DebugExecutionResult } from '@/api/debug'

interface Props {
  executionResult: DebugExecutionResult | null
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false
})

// 当前激活的标签页
const activeTab = ref<'logs' | 'variables' | 'performance'>('logs')

// 标签页列表
const tabs = [
  { key: 'logs', label: '执行日志', icon: '📋' },
  { key: 'variables', label: '变量快照', icon: '🔍' },
  { key: 'performance', label: '性能分析', icon: '⚡' }
]

// 格式化执行时间
const formatExecutionTime = (ms: number) => {
  if (ms < 1) return `${ms.toFixed(3)} ms`
  if (ms < 1000) return `${ms.toFixed(2)} ms`
  return `${(ms / 1000).toFixed(2)} s`
}

// 格式化内存
const formatMemory = (mb?: number) => {
  if (!mb) return 'N/A'
  if (mb < 1) return `${(mb * 1024).toFixed(2)} KB`
  return `${mb.toFixed(2)} MB`
}

// 执行状态样式
const getStatusClass = computed(() => {
  if (!props.executionResult) return ''
  return props.executionResult.success
    ? 'text-green-600 bg-green-100'
    : 'text-red-600 bg-red-100'
})

// 执行状态文本
const getStatusText = computed(() => {
  if (!props.executionResult) return ''
  return props.executionResult.success ? '✓ 成功' : '✗ 失败'
})
</script>

<template>
  <div class="debug-panel">
    <!-- 加载状态 -->
    <div v-if="loading" class="loading-state p-8 text-center">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-4 border-blue-500 border-t-transparent"></div>
      <p class="mt-4 text-gray-600">正在执行脚本...</p>
    </div>

    <!-- 空状态 -->
    <div v-else-if="!executionResult" class="empty-state p-8 text-center text-gray-500">
      <div class="text-4xl mb-4">🐛</div>
      <p class="text-lg font-medium">暂无调试信息</p>
      <p class="text-sm mt-2">运行脚本后，调试信息将显示在这里</p>
    </div>

    <!-- 调试信息 -->
    <div v-else class="debug-content">
      <!-- 执行摘要 -->
      <div class="execution-summary p-4 bg-gray-50 rounded-lg mb-4">
        <div class="flex items-center justify-between">
          <!-- 状态 -->
          <div class="flex items-center gap-3">
            <span
              class="px-3 py-1 text-sm font-semibold rounded"
              :class="getStatusClass"
            >
              {{ getStatusText }}
            </span>
            <span class="text-sm text-gray-600">
              执行 ID: <code class="text-xs font-mono bg-white px-2 py-0.5 rounded">{{ executionResult.execution_id }}</code>
            </span>
          </div>

          <!-- 性能指标摘要 -->
          <div class="flex items-center gap-4 text-sm">
            <div class="flex items-center gap-2">
              <span class="text-gray-600">⏱️ 执行时间:</span>
              <span class="font-semibold text-gray-800">
                {{ formatExecutionTime(executionResult.performance.execution_time_ms) }}
              </span>
            </div>
            <div v-if="executionResult.performance.memory_peak_mb" class="flex items-center gap-2">
              <span class="text-gray-600">💾 峰值内存:</span>
              <span class="font-semibold text-gray-800">
                {{ formatMemory(executionResult.performance.memory_peak_mb) }}
              </span>
            </div>
          </div>
        </div>

        <!-- 错误信息 -->
        <div v-if="!executionResult.success && executionResult.error" class="mt-3 p-3 bg-red-50 border border-red-200 rounded">
          <div class="flex items-start gap-2">
            <span class="text-red-600 font-semibold">❌ 错误:</span>
            <pre class="flex-1 text-sm text-red-800 font-mono whitespace-pre-wrap">{{ executionResult.error }}</pre>
          </div>
        </div>

        <!-- 执行结果 -->
        <div v-if="executionResult.success && executionResult.result !== null" class="mt-3 p-3 bg-green-50 border border-green-200 rounded">
          <div class="flex items-start gap-2">
            <span class="text-green-600 font-semibold">✓ 结果:</span>
            <pre class="flex-1 text-sm text-green-800 font-mono whitespace-pre-wrap">{{ JSON.stringify(executionResult.result, null, 2) }}</pre>
          </div>
        </div>
      </div>

      <!-- 标签页导航 -->
      <div class="tabs border-b border-gray-300 mb-4">
        <div class="flex gap-1">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            @click="activeTab = tab.key as any"
            class="px-4 py-2 text-sm font-medium transition-colors rounded-t-lg"
            :class="activeTab === tab.key
              ? 'bg-white text-blue-600 border-t-2 border-x border-blue-600 -mb-px'
              : 'text-gray-600 hover:text-gray-800 hover:bg-gray-100'"
          >
            <span class="mr-2">{{ tab.icon }}</span>
            {{ tab.label }}
            <span
              v-if="tab.key === 'logs'"
              class="ml-2 px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-600"
            >
              {{ executionResult.logs.length }}
            </span>
            <span
              v-if="tab.key === 'variables'"
              class="ml-2 px-2 py-0.5 text-xs rounded-full bg-purple-100 text-purple-600"
            >
              {{ executionResult.variables.length }}
            </span>
          </button>
        </div>
      </div>

      <!-- 标签页内容 -->
      <div class="tab-content">
        <!-- 日志查看器 -->
        <div v-show="activeTab === 'logs'">
          <LogViewer :logs="executionResult.logs" max-height="500px" />
        </div>

        <!-- 变量查看器 -->
        <div v-show="activeTab === 'variables'">
          <VariableInspector :variables="executionResult.variables" max-height="500px" />
        </div>

        <!-- 性能分析 -->
        <div v-show="activeTab === 'performance'" class="performance-panel">
          <div class="grid grid-cols-2 gap-4">
            <!-- 执行时间 -->
            <div class="metric-card p-4 bg-white border border-gray-300 rounded-lg">
              <div class="flex items-center gap-3 mb-2">
                <span class="text-2xl">⏱️</span>
                <h3 class="text-sm font-semibold text-gray-700">执行时间</h3>
              </div>
              <div class="text-3xl font-bold text-blue-600">
                {{ formatExecutionTime(executionResult.performance.execution_time_ms) }}
              </div>
              <div class="mt-2 text-xs text-gray-500">
                脚本执行总耗时
              </div>
            </div>

            <!-- 峰值内存 -->
            <div class="metric-card p-4 bg-white border border-gray-300 rounded-lg">
              <div class="flex items-center gap-3 mb-2">
                <span class="text-2xl">💾</span>
                <h3 class="text-sm font-semibold text-gray-700">峰值内存</h3>
              </div>
              <div class="text-3xl font-bold text-purple-600">
                {{ formatMemory(executionResult.performance.memory_peak_mb) }}
              </div>
              <div class="mt-2 text-xs text-gray-500">
                执行过程中的最大内存占用
              </div>
            </div>

            <!-- 日志数量 -->
            <div class="metric-card p-4 bg-white border border-gray-300 rounded-lg">
              <div class="flex items-center gap-3 mb-2">
                <span class="text-2xl">📋</span>
                <h3 class="text-sm font-semibold text-gray-700">日志数量</h3>
              </div>
              <div class="text-3xl font-bold text-green-600">
                {{ executionResult.logs.length }}
              </div>
              <div class="mt-2 text-xs text-gray-500">
                捕获的日志条目总数
              </div>
            </div>

            <!-- 变量数量 -->
            <div class="metric-card p-4 bg-white border border-gray-300 rounded-lg">
              <div class="flex items-center gap-3 mb-2">
                <span class="text-2xl">🔍</span>
                <h3 class="text-sm font-semibold text-gray-700">变量数量</h3>
              </div>
              <div class="text-3xl font-bold text-orange-600">
                {{ executionResult.variables.length }}
              </div>
              <div class="mt-2 text-xs text-gray-500">
                捕获的变量快照数量
              </div>
            </div>
          </div>

          <!-- 时间线 -->
          <div class="timeline mt-6 p-4 bg-white border border-gray-300 rounded-lg">
            <h3 class="text-sm font-semibold text-gray-700 mb-3">执行时间线</h3>
            <div class="space-y-2">
              <div class="flex items-center gap-3 text-sm">
                <span class="text-gray-600">开始时间:</span>
                <span class="font-mono text-gray-800">{{ new Date(executionResult.started_at).toLocaleString('zh-CN') }}</span>
              </div>
              <div v-if="executionResult.completed_at" class="flex items-center gap-3 text-sm">
                <span class="text-gray-600">完成时间:</span>
                <span class="font-mono text-gray-800">{{ new Date(executionResult.completed_at).toLocaleString('zh-CN') }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.debug-panel {
  min-height: 400px;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.metric-card {
  transition: transform 0.2s, box-shadow 0.2s;
}

.metric-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.animate-spin {
  animation: spin 1s linear infinite;
}
</style>
