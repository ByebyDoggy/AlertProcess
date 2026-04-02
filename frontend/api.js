const API_BASE = '/api'
const API_KEY = 'dev-api-key'

const api = {
  async request(method, endpoint, data = null, params = null) {
    const url = new URL(`${API_BASE}${endpoint}`, window.location.origin)
    
    if (params) {
      Object.keys(params).forEach(key => {
        if (params[key] !== null && params[key] !== undefined) {
          url.searchParams.append(key, params[key])
        }
      })
    }

    const options = {
      method,
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY
      }
    }

    if (data && method !== 'GET') {
      options.body = JSON.stringify(data)
    }

    const response = await fetch(url, options)
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }))
      throw new Error(error.detail || `HTTP ${response.status}`)
    }
    
    return response.json()
  },

  async getAlerts({ skip = 0, limit = 100, severity = null, chainId = null } = {}) {
    return this.request('GET', '/alert/alerts', null, { skip, limit, severity, chain_id: chainId })
  },

  async getAlert(alertId) {
    return this.request('GET', `/alert/alerts/${alertId}`)
  },

  async getStats() {
    return this.request('GET', '/alert/stats')
  },

  async submitAlert(alertData) {
    return this.request('POST', '/alert/submit', alertData)
  },

  async healthCheck() {
    return this.request('GET', '/')
  },

  async getRuleChains() {
    return this.request('GET', '/rule-chain/')
  },

  async getRuleChain(chainId) {
    return this.request('GET', `/rule-chain/${chainId}`)
  },

  async createRuleChain(chainData) {
    return this.request('POST', '/rule-chain/', chainData)
  },

  async updateRuleChain(chainId, chainData) {
    return this.request('PUT', `/rule-chain/${chainId}`, chainData)
  },

  async deleteRuleChain(chainId) {
    return this.request('DELETE', `/rule-chain/${chainId}`)
  }
}

window.ApiService = api
