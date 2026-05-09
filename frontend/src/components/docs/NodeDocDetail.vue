<template>
  <div v-if="node" class="doc-detail space-y-5">
    <!-- Header -->
    <div class="rounded-xl border border-[#2d2d50] bg-[#1e1e38]/80 p-5 backdrop-blur-sm">
      <div class="flex items-center gap-3 mb-3">
        <span class="text-2xl" :style="{ color: node.color || '#818cf8' }">{{ node.icon || '&#9679;' }}</span>
        <div>
          <h2 class="text-lg font-semibold text-gray-100">{{ node.label }}</h2>
          <p class="text-xs text-gray-500 font-mono">{{ node.name }}</p>
        </div>
        <span class="ml-auto px-2.5 py-1 rounded-full text-xs font-medium border"
              :style="{ borderColor: node.color + '60', color: node.color, background: node.color + '15' }">
          {{ node.category_label }}
        </span>
      </div>
      <p v-if="node.description" class="text-sm text-gray-300 leading-relaxed">{{ node.description }}</p>
      <div class="mt-3 flex flex-wrap gap-4 text-xs text-gray-500">
        <span>基类: <code class="text-indigo-400 bg-indigo-500/10 px-1.5 py-0.5 rounded">{{ node.base_class }}</code></span>
        <span>模块: <code class="text-indigo-400 bg-indigo-500/10 px-1.5 py-0.5 rounded">{{ node.module }}</code></span>
      </div>
    </div>

    <!-- Context Dependencies -->
    <div v-if="node.required_providers && node.required_providers.length" class="doc-section">
      <h3 class="section-title">上下文依赖</h3>
      <div class="section-body">
        <div class="flex flex-wrap gap-2">
          <span v-for="p in node.required_providers" :key="p"
                class="px-2.5 py-1 rounded-full text-xs bg-amber-500/10 text-amber-400 border border-amber-500/30">
            {{ p }}
          </span>
        </div>
        <p class="text-xs text-gray-500 mt-2">此节点需要上游连接对应的 Provider 节点来注入上下文数据</p>
      </div>
    </div>

    <!-- Provides -->
    <div v-if="node.provides && node.provides.length" class="doc-section">
      <h3 class="section-title">数据注入</h3>
      <div class="section-body">
        <div class="flex flex-wrap gap-2">
          <span v-for="p in node.provides" :key="p"
                class="px-2.5 py-1 rounded-full text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
            {{ p }}
          </span>
        </div>
        <p class="text-xs text-gray-500 mt-2">此节点向上下文 extra 中注入以上字段，供下游节点使用</p>
      </div>
    </div>

    <!-- Input Ports -->
    <div v-if="node.inputs && node.inputs.length" class="doc-section">
      <h3 class="section-title">输入端口</h3>
      <div class="section-body overflow-x-auto">
        <table class="doc-table">
          <thead>
            <tr><th>Key</th><th>标签</th><th>数据类型</th><th>必填</th><th>多输入</th><th>说明</th></tr>
          </thead>
          <tbody>
            <tr v-for="(port, i) in node.inputs" :key="'in-'+i">
              <td><code>{{ port.key }}</code></td>
              <td>{{ port.label }}</td>
              <td><span class="type-badge">{{ port.data_type }}</span></td>
              <td>{{ port.required ? '&#10003;' : '-' }}</td>
              <td>{{ port.multi ? '&#10003;' : '-' }}</td>
              <td class="text-gray-400">{{ port.description || '-' }}</td>
            </tr>
          </tbody>
        </table>
        <!-- Input Schema Details -->
        <details v-for="(schema, i) in node.input_schemas" :key="'ischema-'+i" class="mt-2 schema-details">
          <summary class="text-xs text-indigo-400 cursor-pointer hover:text-indigo-300">
            {{ node.inputs[i]?.label || ('端口 ' + i) }} 输入模型字段
          </summary>
          <SchemaFieldsTable :schema="schema" />
        </details>
      </div>
    </div>

    <!-- Output Ports -->
    <div v-if="node.outputs && node.outputs.length" class="doc-section">
      <h3 class="section-title">输出端口</h3>
      <div class="section-body overflow-x-auto">
        <table class="doc-table">
          <thead>
            <tr><th>Key</th><th>标签</th><th>数据类型</th><th>说明</th></tr>
          </thead>
          <tbody>
            <tr v-for="(port, i) in node.outputs" :key="'out-'+i">
              <td><code>{{ port.key }}</code></td>
              <td>{{ port.label }}</td>
              <td><span class="type-badge">{{ port.data_type }}</span></td>
              <td class="text-gray-400">{{ port.description || '-' }}</td>
            </tr>
          </tbody>
        </table>
        <!-- Output Schema Details -->
        <details v-for="(schema, i) in node.output_schemas" :key="'oschema-'+i" class="mt-2 schema-details">
          <summary class="text-xs text-indigo-400 cursor-pointer hover:text-indigo-300">
            {{ node.outputs[i]?.label || ('端口 ' + i) }} 输出模型字段
          </summary>
          <SchemaFieldsTable :schema="schema" />
        </details>
      </div>
    </div>

    <!-- Config Parameters -->
    <div v-if="hasConfig" class="doc-section">
      <h3 class="section-title">配置参数</h3>
      <div class="section-body overflow-x-auto">
        <table class="doc-table">
          <thead>
            <tr><th>字段</th><th>类型</th><th>默认值</th><th>约束</th><th>说明</th></tr>
          </thead>
          <tbody>
            <tr v-for="(prop, key) in configProperties" :key="'cfg-'+key">
              <td><code>{{ key }}</code></td>
              <td><span class="type-badge">{{ prop.type }}</span></td>
              <td class="text-gray-300">{{ formatDefault(prop.default) }}</td>
              <td class="text-xs text-gray-500">{{ formatConstraints(prop) }}</td>
              <td class="text-gray-400">{{ prop.description || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Empty state -->
  <div v-else class="flex items-center justify-center h-full text-gray-500">
    <div class="text-center">
      <div class="text-3xl mb-3 opacity-30">&#128218;</div>
      <p class="text-sm">从左侧选择一个节点查看文档</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import SchemaFieldsTable from './SchemaFieldsTable.vue'

const props = defineProps({
  node: { type: Object, default: null },
})

const configProperties = computed(() => {
  return props.node?.config_schema?.properties || {}
})

const hasConfig = computed(() => {
  return Object.keys(configProperties.value).length > 0
})

function formatDefault(val) {
  if (val === undefined || val === null) return '-'
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function formatConstraints(prop) {
  const parts = []
  if (prop.minimum !== undefined) parts.push('min: ' + prop.minimum)
  if (prop.maximum !== undefined) parts.push('max: ' + prop.maximum)
  if (prop.enum) parts.push('enum: [' + prop.enum.join(', ') + ']')
  return parts.join(', ') || '-'
}
</script>

<style scoped>
.doc-section {
  @apply rounded-xl border border-[#2d2d50] bg-[#1e1e38]/60 backdrop-blur-sm overflow-hidden;
}
.section-title {
  @apply px-4 py-2.5 text-sm font-semibold text-gray-200 bg-[#16162a]/80 border-b border-[#2d2d50];
}
.section-body {
  @apply p-4;
}
.doc-table {
  @apply w-full text-xs;
}
.doc-table th {
  @apply text-left text-gray-400 font-medium py-2 px-3 border-b border-[#2d2d50] whitespace-nowrap;
}
.doc-table td {
  @apply py-2 px-3 border-b border-[#2d2d50]/50 whitespace-nowrap;
}
.doc-table code {
  @apply text-indigo-400 bg-indigo-500/10 px-1.5 py-0.5 rounded text-xs;
}
.type-badge {
  @apply px-1.5 py-0.5 rounded text-[10px] bg-[#2d2d50] text-gray-400;
}
.schema-details {
  @apply rounded-lg border border-[#2d2d50] bg-[#16162a]/50 p-2;
}
</style>
