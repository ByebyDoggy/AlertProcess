/**
 * 连线合法性校验辅助函数
 */

import { checkConnectionValid } from '../config/connectionRules.js'

/**
 * 查找端口定义
 * @param {object} nodeTypeDef - 节点类型定义
 * @param {string} portKey - 端口 key
 * @param {'inputs'|'outputs'} portType
 * @returns {object|null}
 */
export function findPortDef(nodeTypeDef, portKey, portType) {
  const ports = nodeTypeDef?.[portType] || []
  return ports.find(p => p.key === portKey) || null
}

/**
 * 获取端口 data_type
 */
export function getPortDataType(nodeTypeDef, portKey, portType) {
  const port = findPortDef(nodeTypeDef, portKey, portType)
  return port?.data_type || 'any'
}

/**
 * 完整校验一条连线是否合法
 */
export function validateConnection(sourceNodeType, sourcePortKey, targetNodeType, targetPortKey) {
  const sourceDataType = getPortDataType(sourceNodeType, sourcePortKey, 'outputs')
  const targetDataType = getPortDataType(targetNodeType, targetPortKey, 'inputs')

  if (!sourceNodeType || !targetNodeType) {
    return { valid: false, reason: '找不到节点类型定义' }
  }

  return checkConnectionValid(sourceDataType, targetDataType)
}

/**
 * 检查目标端口是否已被连接（去重）
 */
export function isTargetPortConnected(edges, targetNodeId, targetPortKey) {
  return edges.some(e => e.target === targetNodeId && e.targetPort === targetPortKey)
}

/**
 * 检查目标端口是否允许多条连线
 */
export function isMultiPort(nodeTypeDef, portKey, portType) {
  const port = findPortDef(nodeTypeDef, portKey, portType)
  return port?.multi === true
}
