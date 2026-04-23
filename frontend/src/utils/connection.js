/**
 * 连线合法性校验辅助函数
 */

import { checkConnectionValid } from '../config/connectionRules.js'
import { outputSchemaToFields, inputSchemaToFields } from './schemaFields.js'

/**
 * 字段类型兼容性矩阵 — 用于字段级别映射的类型检查
 *
 * 支持的类型转换规则：
 * - string ← string (严格)
 * - number ← number | string(可解析为数字)  [宽松]
 * - boolean ← boolean | string('true'/'false')  [宽松]
 * - array ← array (严格)
 * - object ← object (严格)
 * - any   ← 所有类型
 */
const FIELD_TYPE_COMPATIBILITY = {
  string: ['string'],
  number: ['number', 'string'],
  boolean: ['boolean', 'string'],
  array:  ['array'],
  object: ['object'],
  any: ['string', 'number', 'boolean', 'array', 'object', 'any'],
}

/**
 * 检查源输出字段类型是否能赋值给目标输入字段类型
 * @param {string} sourceFieldType - 上游输出字段的 type
 * @param {string} targetFieldType - 下游输入字段的 type（或其 source_field_type 约束）
 * @returns {{ compatible: boolean, reason?: string }}
 */
export function validateFieldType(sourceFieldType, targetFieldType) {
  const allowed = FIELD_TYPE_COMPATIBILITY[targetFieldType] || FIELD_TYPE_COMPATIBILITY['any']
  if (allowed.includes(sourceFieldType)) {
    return { compatible: true }
  }
  return {
    compatible: false,
    reason: `字段类型不匹配: ${sourceFieldType} 不能赋值给 ${targetFieldType}`,
  }
}

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
 *
 * @param {object} sourceNodeType - 源节点类型定义
 * @param {string} sourcePortKey - 源端口 key
 * @param {object} targetNodeType - 目标节点类型定义
 * @param {string} targetPortKey - 目标端口 key
 * @param {object|null} [fieldMapping] - 可选的字段映射（用于字段级别校验）
 */
export function validateConnection(sourceNodeType, sourcePortKey, targetNodeType, targetPortKey, fieldMapping = null) {
  const sourceDataType = getPortDataType(sourceNodeType, sourcePortKey, 'outputs')
  const targetDataType = getPortDataType(targetNodeType, targetPortKey, 'inputs')

  if (!sourceNodeType || !targetNodeType) {
    return { valid: false, reason: '找不到节点类型定义' }
  }

  // 1. 端口级别数据类型检查
  const portCheck = checkConnectionValid(sourceDataType, targetDataType)
  if (!portCheck.valid) {
    return portCheck
  }

  // 2. 字段映射级别类型检查（如果提供了 fieldMapping）
  if (fieldMapping && Object.keys(fieldMapping).length > 0) {
    // Convert input_schemas (per-port Pydantic JSON Schemas) to old input_fields format
    const inputFields = (() => {
      // 优先使用新的 per-port input_schemas，合并所有端口的字段
      if (targetNodeType?.input_schemas && targetNodeType.input_schemas.length > 0) {
        return targetNodeType.input_schemas.flatMap(s => inputSchemaToFields(s))
      }
      // Fallback: 旧格式
      if (targetNodeType?.input_schema) return inputSchemaToFields(targetNodeType.input_schema)
      return targetNodeType?.input_fields || []
    })()
    for (const [sourcePath, mapping] of Object.entries(fieldMapping)) {
      const sourceFieldType = mapping.type
      const targetKey = mapping.targetKey

      // 找到目标输入字段的期望类型
      const targetFieldDef = inputFields.find(f => f.key === targetKey)
      const expectedType = targetFieldDef?.source_field_type || targetFieldDef?.type || ''

      if (expectedType) {
        const typeCheck = validateFieldType(sourceFieldType, expectedType)
        if (!typeCheck.compatible) {
          return {
            valid: false,
            reason: `字段映射类型错误: ${sourcePath}(${sourceFieldType}) -> ${targetKey}(${expectedType}) — ${typeCheck.reason}`,
          }
        }
      }
    }
  }

  return { valid: true }
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
