// 配置文件
export const API_BASE_URL = 'http://localhost:8000'

export const API_KEY = localStorage.getItem('api_key') || 'default-api-key'

// 节点类型定义
export const NODE_TYPES = {
  trigger: {
    type: 'trigger',
    label: '触发器',
    icon: '⚡',
    color: 'yellow',
    description: '规则链的起始节点',
    configFields: []
  },
  detector: {
    type: 'detector',
    label: '检测器',
    icon: '🛡️',
    color: 'green',
    description: '执行安全检测',
    configFields: [
      {
        key: 'detectorType',
        label: '检测器类型',
        type: 'select',
        options: [
          { value: 'flash_loan', label: '⚡ Flash Loan 检测' },
          { value: 'token_approval', label: '🔐 Token 授权检测' },
          { value: 'token_anomaly', label: '💰 Token 异常检测' },
          { value: 'address_graph', label: '🔗 地址图谱分析' },
          { value: 'gas_price', label: '⛽ Gas 价格检测' },
          { value: 'address_age', label: '📅 地址年龄检测' },
          { value: 'arkm_label', label: '🏷️ ARKM 标签检测' },
          { value: 'address_type', label: '🏢 地址类型检测' }
        ]
      }
    ]
  },
  condition: {
    type: 'condition',
    label: '条件判断',
    icon: '🔍',
    color: 'blue',
    description: '根据条件分支',
    configFields: [
      {
        key: 'field',
        label: '条件字段',
        type: 'text',
        placeholder: '例如: detector.flash_loan'
      },
      {
        key: 'operator',
        label: '操作符',
        type: 'select',
        options: [
          { value: 'equals', label: '等于' },
          { value: 'not_equals', label: '不等于' },
          { value: 'contains', label: '包含' },
          { value: 'greater_than', label: '大于' },
          { value: 'less_than', label: '小于' },
          { value: 'regex', label: '正则匹配' }
        ]
      },
      {
        key: 'value',
        label: '比较值',
        type: 'text',
        placeholder: '比较值'
      }
    ]
  },
  filter: {
    type: 'filter',
    label: '过滤器',
    icon: '🔽',
    color: 'orange',
    description: '过滤不符合条件的告警',
    configFields: [
      {
        key: 'expression',
        label: '过滤条件',
        type: 'textarea',
        placeholder: '例如: context.gas_price > 100',
        rows: 3
      }
    ]
  },
  action: {
    type: 'action',
    label: '执行动作',
    icon: '⚙️',
    color: 'purple',
    description: '设置属性或标记',
    configFields: [
      {
        key: 'actionType',
        label: '操作类型',
        type: 'select',
        options: [
          { value: 'set_severity', label: '设置严重级别' },
          { value: 'set_score', label: '设置风险评分' },
          { value: 'add_tag', label: '添加标签' },
          { value: 'notify', label: '发送通知' }
        ]
      },
      {
        key: 'actionValue',
        label: '参数值',
        type: 'text',
        placeholder: '例如: CRITICAL 或 HIGH'
      }
    ]
  },
  scorer: {
    type: 'scorer',
    label: '评分',
    icon: '📊',
    color: 'cyan',
    description: '计算风险评分',
    configFields: [
      {
        key: 'weights',
        label: '评分权重',
        type: 'object',
        fields: [
          { key: 'severity', label: '严重程度权重', type: 'number', default: 1 },
          { key: 'detector', label: '检测器权重', type: 'number', default: 1 }
        ]
      }
    ]
  },
  notifier: {
    type: 'notifier',
    label: '通知',
    icon: '📢',
    color: 'red',
    description: '发送告警通知',
    configFields: [
      {
        key: 'notifierType',
        label: '通知类型',
        type: 'select',
        options: [
          { value: 'webhook', label: 'Webhook 通知' },
          { value: 'email', label: '邮件通知' },
          { value: 'slack', label: 'Slack 通知' }
        ]
      },
      {
        key: 'targetUrl',
        label: '目标地址',
        type: 'text',
        placeholder: '例如: https://example.com/webhook'
      }
    ]
  }
}

export const DEFAULT_NODE_CONFIG = {
  trigger: {},
  detector: { detectorType: 'flash_loan' },
  condition: { field: '', operator: 'equals', value: '' },
  filter: { expression: '' },
  action: { actionType: 'set_severity', actionValue: '' },
  scorer: { weights: { severity: 1, detector: 1 } },
  notifier: { notifierType: 'webhook', targetUrl: '' }
}
