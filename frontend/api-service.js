import { API_BASE_URL, API_KEY } from './config.js'

class ApiService {
  constructor() {
    this.baseUrl = API_BASE_URL
    this.headers = {
      'X-API-Key': API_KEY,
      'Content-Type': 'application/json'
    }
  }

  async request(url, options = {}) {
    const config = {
      ...options,
      headers: {
        ...this.headers,
        ...options.headers
      }
    }

    try {
      const response = await fetch(`${this.baseUrl}${url}`, config)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      return await response.json()
    } catch (error) {
      console.error('API request failed:', error)
      throw error
    }
  }

  // 告警相关 API
  async getAlerts(params = {}) {
    const queryParams = new URLSearchParams(params)
    return this.request(`/alert/alerts?${queryParams}`)
  }

  async getStats() {
    return this.request('/alert/stats')
  }

  async submitAlert(data) {
    return this.request('/alert/submit', {
      method: 'POST',
      body: JSON.stringify(data)
    })
  }

  // 规则链相关 API
  async getRuleChains() {
    return this.request('/rule-chain/')
  }

  async getRuleChain(chainId) {
    return this.request(`/rule-chain/${chainId}`)
  }

  async createRuleChain(data) {
    return this.request('/rule-chain/', {
      method: 'POST',
      body: JSON.stringify(data)
    })
  }

  async updateRuleChain(chainId, data) {
    return this.request(`/rule-chain/${chainId}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    })
  }

  async deleteRuleChain(chainId) {
    return this.request(`/rule-chain/${chainId}`, {
      method: 'DELETE'
    })
  }

  // 设置 API Key
  setApiKey(key) {
    this.headers['X-API-Key'] = key
    localStorage.setItem('api_key', key)
  }
}

// 创建全局实例
const apiService = new ApiService()

// 兼容旧版代码
window.ApiService = apiService

export default apiService
