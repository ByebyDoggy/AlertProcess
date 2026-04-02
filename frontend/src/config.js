// Node type definitions - n8n-style with input/output ports and variables
export const NODE_TYPES = {
  trigger: {
    type: 'trigger',
    label: '入口触发器',
    icon: '⚡',
    color: '#f59e0b',
    bgColor: '#f59e0b',
    lightBg: 'rgba(245,158,11,0.12)',
    borderColor: '#f59e0b',
    description: '规则链入口，接收告警数据',
    category: 'flow',
    inputs: [],
    outputs: [
      { key: 'output', label: '告警数据', color: '#f59e0b' },
    ],
    variables: [
      { key: 'chain_id', label: 'Chain ID', type: 'string' },
      { key: 'tx_hash', label: '交易哈希', type: 'string' },
      { key: 'attacked_address', label: '被攻击地址', type: 'string' },
      { key: 'exploiter_address', label: '攻击者地址', type: 'string' },
    ],
    configFields: [],
  },

  detector: {
    type: 'detector',
    label: '安全检测器',
    icon: '🔍',
    color: '#10b981',
    bgColor: '#10b981',
    lightBg: 'rgba(16,185,129,0.12)',
    borderColor: '#10b981',
    description: '执行安全检测分析',
    category: 'detection',
    inputs: [
      { key: 'input', label: '输入', color: '#10b981' },
    ],
    outputs: [
      { key: 'true', label: '检测到', color: '#10b981' },
      { key: 'false', label: '未检测到', color: '#ef4444' },
    ],
    variables: [
      { key: 'detected', label: '是否检测到', type: 'boolean' },
      { key: 'severity', label: '严重程度', type: 'string' },
      { key: 'confidence', label: '置信度', type: 'number' },
      { key: 'alert_type', label: '告警类型', type: 'string' },
      { key: 'metadata', label: '元数据', type: 'object' },
    ],
    configFields: [
      {
        key: 'detectorType',
        label: '检测器类型',
        type: 'select',
        options: [], // populated dynamically from API
        dynamic: true,
      },
    ],
  },

  condition: {
    type: 'condition',
    label: '条件分支',
    icon: '🔀',
    color: '#6366f1',
    bgColor: '#6366f1',
    lightBg: 'rgba(99,102,241,0.12)',
    borderColor: '#6366f1',
    description: 'AND/OR/IF 多条件分支判断',
    category: 'logic',
    inputs: [
      { key: 'input', label: '输入', color: '#6366f1' },
    ],
    outputs: [
      { key: 'true', label: '满足', color: '#10b981' },
      { key: 'false', label: '不满足', color: '#ef4444' },
    ],
    variables: [
      { key: 'result', label: '判断结果', type: 'boolean' },
    ],
    configFields: [
      {
        key: 'logic',
        label: '逻辑方式',
        type: 'select',
        options: [
          { value: 'and', label: 'AND (全部满足)' },
          { value: 'or', label: 'OR (任一满足)' },
          { value: 'if', label: 'IF (单一条件)' },
        ],
      },
      {
        key: 'conditions',
        label: '条件列表',
        type: 'conditions',
      },
    ],
  },

  action: {
    type: 'action',
    label: '执行动作',
    icon: '⚙️',
    color: '#a855f7',
    bgColor: '#a855f7',
    lightBg: 'rgba(168,85,247,0.12)',
    borderColor: '#a855f7',
    description: '设置属性、标注地址、发送告警',
    category: 'action',
    inputs: [
      { key: 'input', label: '输入', color: '#a855f7' },
    ],
    outputs: [
      { key: 'output', label: '输出', color: '#a855f7' },
    ],
    variables: [
      { key: 'action_result', label: '执行结果', type: 'string' },
    ],
    configFields: [
      {
        key: 'actionType',
        label: '操作类型',
        type: 'select',
        options: [
          { value: 'set_severity', label: '设置严重级别' },
          { value: 'set_score', label: '设置风险评分' },
          { value: 'add_tag', label: '添加标签' },
          { value: 'annotate_address', label: '地址标注' },
        ],
      },
      {
        key: 'actionValue',
        label: '参数值',
        type: 'text',
        placeholder: 'CRITICAL / 80 / suspicious',
      },
      {
        key: 'annotationType',
        label: '标注类型',
        type: 'select',
        showWhen: { key: 'actionType', value: 'annotate_address' },
        options: [
          { value: 'hacker', label: '攻击者' },
          { value: 'victim', label: '受害者' },
          { value: 'contract_exploit', label: '合约利用' },
          { value: 'phishing', label: '钓鱼' },
          { value: 'suspicious', label: '可疑' },
          { value: 'safe', label: '安全' },
        ],
      },
    ],
  },

  notifier: {
    type: 'notifier',
    label: '通知推送',
    icon: '📤',
    color: '#ef4444',
    bgColor: '#ef4444',
    lightBg: 'rgba(239,68,68,0.12)',
    borderColor: '#ef4444',
    description: '发送告警通知',
    category: 'output',
    inputs: [
      { key: 'input', label: '输入', color: '#ef4444' },
    ],
    outputs: [],
    variables: [],
    configFields: [
      {
        key: 'notifierType',
        label: '通知类型',
        type: 'select',
        options: [
          { value: 'webhook', label: 'Webhook' },
          { value: 'telegram', label: 'Telegram' },
        ],
      },
      {
        key: 'targetUrl',
        label: '目标地址',
        type: 'text',
        placeholder: 'https://example.com/webhook',
      },
      {
        key: 'messageTemplate',
        label: '消息模板',
        type: 'textarea',
        placeholder: '支持变量: {{trigger.tx_hash}} {{detector.detected}}',
        rows: 3,
      },
    ],
  },
}

// Default node config for each type
export const DEFAULT_NODE_CONFIG = {
  trigger: {},
  detector: { detectorType: 'flash_loan' },
  condition: { logic: 'and', conditions: [{ field: '', operator: 'equals', value: '' }] },
  action: { actionType: 'set_severity', actionValue: '', annotationType: 'suspicious' },
  notifier: { notifierType: 'webhook', targetUrl: '', messageTemplate: '' },
}

// Default node labels
export const DEFAULT_NODE_LABELS = {
  trigger: '入口触发器',
  detector: '安全检测器',
  condition: '条件分支',
  action: '执行动作',
  notifier: '通知推送',
}

// Port colors
export const PORT_COLORS = {
  input: '#6366f1',
  output: '#6366f1',
  true: '#10b981',
  false: '#ef4444',
  default: '#6b7280',
}

// Condition operators
export const CONDITION_OPERATORS = [
  { value: 'equals', label: '等于' },
  { value: 'not_equals', label: '不等于' },
  { value: 'contains', label: '包含' },
  { value: 'greater_than', label: '大于' },
  { value: 'less_than', label: '小于' },
  { value: 'is_true', label: '为真' },
  { value: 'is_false', label: '为假' },
  { value: 'exists', label: '存在' },
  { value: 'regex', label: '正则匹配' },
]

// Severity options
export const SEVERITY_OPTIONS = [
  { value: 'CRITICAL', label: 'CRITICAL', color: '#ef4444' },
  { value: 'HIGH', label: 'HIGH', color: '#f97316' },
  { value: 'MEDIUM', label: 'MEDIUM', color: '#eab308' },
  { value: 'LOW', label: 'LOW', color: '#3b82f6' },
  { value: 'UNKNOWN', label: 'UNKNOWN', color: '#6b7280' },
]
