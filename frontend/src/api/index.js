const API_BASE = ''

class ApiService {
  constructor() {}

  _headers() {
    const token = localStorage.getItem('chaindetector_token')
    const headers = {
      'Content-Type': 'application/json',
    }
    if (token) {
      headers.Authorization = `Bearer ${token}`
    }
    return headers
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
}

export const apiService = new ApiService()
export default apiService
