<template>
  <div class="system-config">
    <div class="sc-header">
      <div>
        <h1 class="sc-title">System Config</h1>
        <p class="sc-subtitle">OpenAI-compatible AI settings for rule-chain generation and MCP tools</p>
      </div>
      <button class="sc-btn sc-btn-ghost" @click="loadConfig" :disabled="loading">
        {{ loading ? 'Loading...' : 'Reload' }}
      </button>
    </div>

    <div class="sc-card">
      <div class="sc-card-header">
        <div>
          <h2 class="sc-card-title">AI Configuration</h2>
          <p class="sc-card-desc">This OpenAI-compatible configuration is shared by rule-chain AI generation and MCP tools. The API key is stored only on the backend and is never returned in plain text.</p>
        </div>
        <span :class="['sc-status', form.enabled ? 'sc-status-on' : 'sc-status-off']">
          {{ form.enabled ? 'Enabled' : 'Disabled' }}
        </span>
      </div>

      <div class="sc-form">
        <label class="sc-check">
          <input type="checkbox" v-model="form.enabled">
          Enable AI features
        </label>

        <div class="sc-row">
          <label>Base URL</label>
          <input v-model="form.base_url" class="sc-input" placeholder="https://api.openai.com/v1" spellcheck="false">
        </div>

        <div class="sc-row">
          <label>API Key</label>
          <input v-model="form.api_key" class="sc-input" :type="showKey ? 'text' : 'password'" placeholder="****** = unchanged" spellcheck="false">
          <button class="sc-toggle" @click="showKey = !showKey">{{ showKey ? 'Hide' : 'Show' }}</button>
        </div>

        <div class="sc-grid">
          <div class="sc-row">
            <label>Model</label>
            <input v-model="form.model" class="sc-input" placeholder="gpt-4.1-mini" spellcheck="false">
          </div>
          <div class="sc-row">
            <label>Timeout Seconds</label>
            <input v-model.number="form.timeout_seconds" class="sc-input" type="number" min="3" max="300">
          </div>
          <div class="sc-row">
            <label>Temperature</label>
            <input v-model.number="form.temperature" class="sc-input" type="number" min="0" max="2" step="0.1">
          </div>
          <div class="sc-row">
            <label>Max Tokens</label>
            <input v-model.number="form.max_tokens" class="sc-input" type="number" min="256" max="32768">
          </div>
        </div>

        <div class="sc-actions">
          <button class="sc-btn sc-btn-save" @click="saveConfig" :disabled="saving">{{ saving ? 'Saving...' : 'Save' }}</button>
          <button class="sc-btn sc-btn-ghost" @click="testConfig" :disabled="testing">{{ testing ? 'Testing...' : 'Test Connection' }}</button>
        </div>
      </div>
    </div>

    <div v-if="message" :class="['sc-message', messageType === 'error' ? 'sc-message-error' : 'sc-message-ok']">
      {{ message }}
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { getAIConfig, testAIConfig, updateAIConfig } from '../api/systemConfig.js'

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const showKey = ref(false)
const message = ref('')
const messageType = ref('info')

const form = reactive({
  enabled: false,
  base_url: '',
  api_key: '',
  model: 'gpt-4.1-mini',
  timeout_seconds: 60,
  temperature: 0.2,
  max_tokens: 4096,
})

function setMessage(text, type = 'info') {
  message.value = text
  messageType.value = type
}

async function loadConfig() {
  loading.value = true
  try {
    const data = await getAIConfig()
    Object.assign(form, data)
    setMessage('')
  } catch (e) {
    setMessage(`Load failed: ${e.message}`, 'error')
  } finally {
    loading.value = false
  }
}

async function saveConfig() {
  saving.value = true
  try {
    const data = await updateAIConfig(form)
    Object.assign(form, data)
    setMessage('AI configuration saved', 'success')
  } catch (e) {
    setMessage(`Save failed: ${e.message}`, 'error')
  } finally {
    saving.value = false
  }
}

async function testConfig() {
  testing.value = true
  try {
    const result = await testAIConfig()
    if (result.success) {
      const latency = result.latency_ms ? ` (${result.latency_ms} ms)` : ''
      const model = result.model ? ` [${result.model}]` : ''
      setMessage(`Connection OK${model}${latency}: ${result.message}`, 'success')
    } else {
      setMessage(result.error?.message || result.message || 'Connection failed', 'error')
    }
  } catch (e) {
    setMessage(`Connection failed: ${e.message}`, 'error')
  } finally {
    testing.value = false
  }
}

onMounted(loadConfig)
</script>

<style scoped>
.system-config { min-height: 100vh; background: #1a1a2e; color: #e2e8f0; padding: 24px; }
.sc-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.sc-title { font-size: 24px; font-weight: 700; margin: 0; }
.sc-subtitle { color: #94a3b8; font-size: 13px; margin-top: 6px; }
.sc-card { background: #16162a; border: 1px solid #2d2d50; border-radius: 14px; max-width: 920px; }
.sc-card-header { display: flex; justify-content: space-between; padding: 20px; border-bottom: 1px solid #2d2d50; }
.sc-card-title { margin: 0; font-size: 18px; }
.sc-card-desc { margin: 6px 0 0; color: #94a3b8; font-size: 13px; }
.sc-status { font-size: 12px; padding: 4px 10px; border-radius: 999px; height: fit-content; }
.sc-status-on { background: rgba(16, 185, 129, .15); color: #34d399; }
.sc-status-off { background: rgba(148, 163, 184, .15); color: #94a3b8; }
.sc-form { padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.sc-row { display: flex; flex-direction: column; gap: 6px; position: relative; }
.sc-row label, .sc-check { color: #cbd5e1; font-size: 13px; }
.sc-check { display: flex; align-items: center; gap: 8px; }
.sc-input { background: #1f1f38; border: 1px solid #3d3d60; color: #e2e8f0; border-radius: 8px; padding: 9px 12px; outline: none; }
.sc-input:focus { border-color: #6366f1; }
.sc-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.sc-toggle { position: absolute; right: 8px; bottom: 6px; background: transparent; color: #94a3b8; border: 0; cursor: pointer; }
.sc-actions { display: flex; gap: 10px; }
.sc-btn { border: 0; border-radius: 8px; color: #fff; padding: 9px 14px; cursor: pointer; }
.sc-btn:disabled { opacity: .5; cursor: not-allowed; }
.sc-btn-save { background: #4f46e5; }
.sc-btn-ghost { background: #374151; }
.sc-message { max-width: 920px; margin-top: 16px; padding: 12px 14px; border-radius: 10px; font-size: 13px; }
.sc-message-ok { background: rgba(16, 185, 129, .12); color: #6ee7b7; }
.sc-message-error { background: rgba(239, 68, 68, .12); color: #fca5a5; }
</style>
