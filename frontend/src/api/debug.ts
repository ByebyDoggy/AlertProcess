/**
 * 调试 API 封装
 *
 * 提供脚本调试相关的 API 调用方法
 */

import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002'

export interface DebugRunRequest {
  script_code: string
  context?: Record<string, any>
  timeout?: number
  capture_variables?: boolean
  capture_logs?: boolean
}

export interface DebugLog {
  timestamp: string
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'
  message: string
  line_number?: number
  context?: Record<string, any>
}

export interface VariableSnapshot {
  name: string
  value: any
  type_name: string
  size_bytes?: number
}

export interface PerformanceMetrics {
  execution_time_ms: number
  memory_peak_mb?: number
  cpu_time_ms?: number
  lines_executed?: number
}

export interface DebugExecutionResult {
  execution_id: string
  success: boolean
  result: any
  error?: string
  logs: DebugLog[]
  variables: VariableSnapshot[]
  performance: PerformanceMetrics
  script_code: string
  started_at: string
  completed_at?: string
}

export interface DebugRunResponse {
  status: string
  data: DebugExecutionResult
}

export interface DebugHistoryItem {
  execution_id: string
  success: boolean
  started_at: string
  execution_time_ms: number
  error?: string
}

/**
 * 在调试模式下运行脚本
 */
export async function debugRunScript(request: DebugRunRequest): Promise<DebugRunResponse> {
  const response = await axios.post(`${API_BASE_URL}/rule-chain/debug/run`, request)
  return response.data
}

/**
 * 获取调试日志
 */
export async function getDebugLogs(executionId: string): Promise<DebugLog[]> {
  const response = await axios.get(`${API_BASE_URL}/rule-chain/debug/logs/${executionId}`)
  return response.data.logs
}

/**
 * 获取变量快照
 */
export async function getDebugVariables(executionId: string): Promise<VariableSnapshot[]> {
  const response = await axios.get(`${API_BASE_URL}/rule-chain/debug/variables/${executionId}`)
  return response.data.variables
}

/**
 * 获取调试历史
 */
export async function getDebugHistory(sessionId: string = 'default', limit: number = 10): Promise<DebugHistoryItem[]> {
  const response = await axios.get(`${API_BASE_URL}/rule-chain/debug/history`, {
    params: { session_id: sessionId, limit }
  })
  return response.data.history
}

/**
 * 清空调试历史
 */
export async function clearDebugHistory(sessionId: string = 'default'): Promise<void> {
  await axios.delete(`${API_BASE_URL}/rule-chain/debug/history/${sessionId}`)
}
