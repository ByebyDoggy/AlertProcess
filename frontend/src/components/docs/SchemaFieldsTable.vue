<template>
  <div v-if="fields.length" class="mt-1 overflow-x-auto">
    <table class="schema-table">
      <thead>
        <tr><th>字段</th><th>类型</th><th>说明</th><th>默认值</th><th>子字段</th></tr>
      </thead>
      <tbody>
        <tr v-for="f in fields" :key="f.key">
          <td><code>{{ f.key }}</code></td>
          <td><span class="type-badge">{{ f.type }}</span></td>
          <td class="text-gray-400">{{ f.description || '-' }}</td>
          <td class="text-gray-300">{{ f.default ?? '-' }}</td>
          <td>
            <details v-if="f.children && f.children.length" class="inline">
              <summary class="text-xs text-indigo-400 cursor-pointer hover:text-indigo-300">
                {{ f.children.length }} 个子字段
              </summary>
              <SchemaFieldsTable :schema="{ properties: childrenToSchema(f.children) }" />
            </details>
            <span v-else class="text-gray-600">-</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  schema: { type: Object, default: () => ({}) },
})

const fields = computed(() => {
  const props_ = props.schema?.properties
  if (!props_) return []
  const required = props.schema?.required || []
  return Object.entries(props_).map(([key, val]) => ({
    key,
    type: val.type || 'any',
    description: val.description || '',
    default: val.default !== undefined ? formatVal(val.default) : undefined,
    required: required.includes(key),
    children: val.type === 'object' && val.properties
      ? Object.entries(val.properties).map(([ck, cv]) => ({
          key: ck, type: cv.type || 'any', description: cv.description || '', default: cv.default !== undefined ? formatVal(cv.default) : undefined, children: [],
        }))
      : null,
  }))
})

function formatVal(v) {
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

function childrenToSchema(children) {
  const result = {}
  for (const c of children) {
    result[c.key] = { type: c.type, description: c.description }
    if (c.default !== undefined) result[c.key].default = c.default
  }
  return result
}
</script>

<style scoped>
.schema-table {
  @apply w-full text-xs;
}
.schema-table th {
  @apply text-left text-gray-400 font-medium py-1.5 px-2.5 border-b border-[#2d2d50] whitespace-nowrap;
}
.schema-table td {
  @apply py-1.5 px-2.5 border-b border-[#2d2d50]/50 whitespace-nowrap;
}
.schema-table code {
  @apply text-indigo-400 bg-indigo-500/10 px-1 py-0.5 rounded text-[11px];
}
.type-badge {
  @apply px-1.5 py-0.5 rounded text-[10px] bg-[#2d2d50] text-gray-400;
}
</style>
