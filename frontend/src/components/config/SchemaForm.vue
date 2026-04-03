<template>
  <div class="space-y-3">
    <div v-for="(field, key) in visibleFields" :key="key">
      <label class="block text-xs font-medium text-gray-400 mb-1">
        {{ field.description || field.title || key }}
      </label>

      <!-- Boolean -->
      <label v-if="field.type === 'boolean'" class="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          :checked="!!model[key]"
          @change="update(key, $event.target.checked)"
          class="w-4 h-4 rounded bg-[#16162a] border-[#2d2d50]"
        >
        <span class="text-xs text-gray-300">启用</span>
      </label>

      <!-- Integer / Number -->
      <input
        v-else-if="field.type === 'integer' || field.type === 'number'"
        type="number"
        :value="model[key]"
        :min="field.minimum"
        :max="field.maximum"
        :step="field.type === 'integer' ? 1 : 0.1"
        @input="update(key, $event.target.value === '' ? null : Number($event.target.value))"
        class="form-input"
      />

      <!-- Select (enum) -->
      <select
        v-else-if="field.enum"
        :value="model[key]"
        @change="update(key, $event.target.value)"
        class="form-select"
      >
        <option v-for="opt in field.enum" :key="opt" :value="opt">{{ opt }}</option>
      </select>

      <!-- Textarea (for templates, etc.) -->
      <textarea
        v-else-if="isLongText(key)"
        :value="model[key]"
        :placeholder="field.description || ''"
        rows="3"
        @input="update(key, $event.target.value)"
        class="form-textarea"
      />

      <!-- Array of strings -->
      <div v-else-if="field.type === 'array' && field.items?.type === 'string'" class="space-y-1">
        <div v-for="(item, idx) in (model[key] || [])" :key="idx" class="flex gap-1">
          <input
            :value="item"
            @input="updateArrayItem(key, idx, $event.target.value)"
            class="form-input !py-1 text-xs"
          >
          <button @click="removeArrayItem(key, idx)" class="text-red-400 hover:text-red-300 text-sm px-1">&times;</button>
        </div>
        <button @click="addArrayItem(key)" class="text-xs text-indigo-400 hover:text-indigo-300">+ 添加</button>
      </div>

      <!-- Object (show JSON hint) -->
      <div v-else-if="field.type === 'object'" class="text-xs text-gray-500 p-2 rounded bg-[#0f0f24]">
        <span class="text-gray-400">{{ key }}</span>: 复杂对象类型
        <pre class="mt-1 text-[10px] text-gray-600 max-h-20 overflow-auto">{{ JSON.stringify(model[key] || field.default, null, 2) }}</pre>
      </div>

      <!-- String / default -->
      <input
        v-else
        type="text"
        :value="model[key]"
        :placeholder="field.description || ''"
        @input="update(key, $event.target.value)"
        class="form-input"
      />

      <!-- Min/Max hint for numbers -->
      <div v-if="(field.type === 'integer' || field.type === 'number') && (field.minimum !== undefined || field.maximum !== undefined)"
        class="text-[10px] text-gray-600 mt-0.5">
        <span v-if="field.minimum !== undefined">最小: {{ field.minimum }}</span>
        <span v-if="field.maximum !== undefined"> 最大: {{ field.maximum }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  schema: { type: Object, default: () => ({}) },
  modelValue: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['update:modelValue'])

const model = computed(() => props.modelValue)

const visibleFields = computed(() => {
  const properties = props.schema?.properties || {}
  return properties
})

const LONG_TEXT_KEYS = ['message_template', 'template', 'pattern']

function isLongText(key) {
  return LONG_TEXT_KEYS.some(k => key.toLowerCase().includes(k))
}

function update(key, value) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}

function updateArrayItem(key, index, value) {
  const arr = [...(props.modelValue[key] || [])]
  arr[index] = value
  emit('update:modelValue', { ...props.modelValue, [key]: arr })
}

function addArrayItem(key) {
  const arr = [...(props.modelValue[key] || []), '']
  emit('update:modelValue', { ...props.modelValue, [key]: arr })
}

function removeArrayItem(key, index) {
  const arr = [...(props.modelValue[key] || [])]
  arr.splice(index, 1)
  emit('update:modelValue', { ...props.modelValue, [key]: arr })
}
</script>
