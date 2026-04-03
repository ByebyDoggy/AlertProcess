const API_BASE = ''

class ApiService {
  constructor() {
    this.apiKey = localStorage.getItem('api_key') || 'default-api-key'
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
}

export const apiService = new ApiService()
export default apiService
