<template>
  <div v-if="visible" class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
    <div class="bg-gray-800 rounded-xl p-6 w-full max-w-lg mx-4 border border-gray-700">
      <div class="flex justify-between items-center mb-4">
        <h3 class="text-xl font-bold text-white">配置节点</h3>
        <button @click="$emit('close')" class="text-gray-400 hover:text-white text-2xl">&times;</button>
      </div>
      
      <div v-if="configNode && nodeConfig" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1">节点名称</label>
          <input v-model="configNode.label" 
                 class="w-full bg-gray-700 text-white rounded-lg px-4 py-2 border border-gray-600 focus:border-blue-500 focus:outline-none">
        </div>
        
        <div v-for="field in nodeConfig.configFields" :key="field.key" class="space-y-2">
          <label class="block text-sm font-medium text-gray-300">{{ field.label }}</label>
          
          <input v-if="field.type === 'text'"
                 v-model="configNode.config[field.key]"
                 :placeholder="field.placeholder"
                 class="w-full bg-gray-700 text-white rounded-lg px-4 py-2 border border-gray-600 focus:border-blue-500 focus:outline-none">
          
          <input v-else-if="field.type === 'number'"
                 type="number"
                 v-model="configNode.config[field.key]"
                 class="w-full bg-gray-700 text-white rounded-lg px-4 py-2 border border-gray-600 focus:border-blue-500 focus:outline-none">
          
          <textarea v-else-if="field.type === 'textarea'"
                    v-model="configNode.config[field.key]"
                    :placeholder="field.placeholder"
                    :rows="field.rows || 3"
                    class="w-full bg-gray-700 text-white rounded-lg px-4 py-2 border border-gray-600 focus:border-blue-500 focus:outline-none"></textarea>
          
          <select v-else-if="field.type === 'select'"
                  v-model="configNode.config[field.key]"
                  class="w-full bg-gray-700 text-white rounded-lg px-4 py-2 border border-gray-600 focus:border-blue-500 focus:outline-none">
            <option v-for="option in field.options" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
          
          <div v-else-if="field.type === 'object'" class="space-y-2">
            <div v-for="subField in field.fields" :key="subField.key" class="flex items-center gap-2">
              <span class="text-xs text-gray-400 w-24">{{ subField.label }}</span>
              <input v-if="subField.type === 'number'"
                     type="number"
                     :value="(configNode.config[field.key] || {})[subField.key] || subField.default || 0"
                     @input="updateNestedConfig(field.key, subField.key, Number($event.target.value))"
                     class="flex-1 bg-gray-700 text-white rounded-lg px-3 py-2 border border-gray-600 focus:border-blue-500 focus:outline-none">
            </div>
          </div>
        </div>
        
        <div class="flex justify-end gap-3 mt-6">
          <button @click="$emit('close')" 
                  class="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-white transition">取消</button>
          <button @click="save" 
                  class="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white transition">应用配置</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'NodeConfigEditor',
  props: {
    node: {
      type: Object,
      required: true
    },
    visible: {
      type: Boolean,
      default: false
    }
  },
  emits: ['save', 'close'],
  data() {
    return {
      configNode: null
    }
  },
  computed: {
    nodeConfig() {
      if (!this.node || !this.node.type) return null
      return window.NODE_TYPES[this.node.type]
    }
  },
  watch: {
    visible(newVal) {
      if (newVal) {
        this.configNode = JSON.parse(JSON.stringify(this.node))
      }
    }
  },
  methods: {
    save() {
      this.$emit('save', { ...this.configNode })
    },
    updateConfig(key, value) {
      if (this.configNode) {
        if (!this.configNode.config) {
          this.configNode.config = {}
        }
        this.configNode.config[key] = value
      }
    },
    updateNestedConfig(parentKey, childKey, value) {
      if (this.configNode && this.configNode.config) {
        if (!this.configNode.config[parentKey]) {
          this.configNode.config[parentKey] = {}
        }
        this.configNode.config[parentKey][childKey] = value
      }
    }
  }
}
</script>
