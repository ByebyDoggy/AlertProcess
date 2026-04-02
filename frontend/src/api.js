// API service
const API_BASE = ''

class ApiService {
  constructor() {
    this.apiKey = localStorage.getItem('api_key') || 'default-api-key'
    this._detectorCache = null
  }

  _headers() {
    return {
      'Content-Type': 'application/json',
      'X-API-Key': this.apiKey,
    }
  }

  async request(url, options = {}) {
    const config = {
      ...options,
      headers: { ...this._headers(), ...options.headers },
    }
    const resp = await fetch(`${API_BASE}${url}`, config)
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }))
      throw new Error(err.detail || `HTTP ${resp.status}`)
    }
    return resp.json()
  }

  setApiKey(key) {
    this.apiKey = key
    localStorage.setItem('api_key', key)
  }

  // Rule Chain CRUD
  async getRuleChains() {
    return this.request('/rule-chain/')
  }

  async getRuleChain(id) {
    return this.request(`/rule-chain/${id}`)
  }

  async createRuleChain(data) {
    return this.request('/rule-chain/', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async updateRuleChain(id, data) {
    return this.request(`/rule-chain/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    })
  }

  async deleteRuleChain(id) {
    return this.request(`/rule-chain/${id}`, { method: 'DELETE' })
  }

  // Validation
  async validateChain(nodes, edges) {
    return this.request('/rule-chain/validate', {
      method: 'POST',
      body: JSON.stringify({ nodes, edges }),
    })
  }

  // Schema - node types (for general structure)
  async getNodeTypes() {
    return this.request('/rule-chain/schema/node-types')
  }

  // Schema - all detectors with detailed config (for dynamic form)
  async getDetectors() {
    if (this._detectorCache) return this._detectorCache
    const data = await this.request('/rule-chain/schema/detectors')
    this._detectorCache = data
    return data
  }

  // Invalidate detector cache (e.g. after adding new detectors)
  invalidateDetectorCache() {
    this._detectorCache = null
  }

  // Alerts
  async getAlerts(params = {}) {
    const qp = new URLSearchParams(params).toString()
    return this.request(`/alert/alerts?${qp}`)
  }

  async getStats() {
    return this.request('/alert/stats')
  }
}

export const apiService = new ApiService()
export default apiService
