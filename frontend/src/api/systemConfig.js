import apiService from './index.js'

const BASE = '/system'

export async function getAIConfig() {
  return apiService.request(`${BASE}/ai-config`)
}

export async function updateAIConfig(payload) {
  const body = { ...payload }
  if (body.api_key === '******') delete body.api_key
  return apiService.request(`${BASE}/ai-config`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export async function testAIConfig(prompt = undefined) {
  const body = {}
  if (prompt !== undefined) body.prompt = prompt
  return apiService.request(`${BASE}/ai-config/test`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
