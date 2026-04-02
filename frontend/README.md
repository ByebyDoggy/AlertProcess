# 前端应用使用指南

## 项目结构

```
frontend/
├── index.html                    # 主页（告警仪表盘）
├── rule-chain.html              # 旧版规则链配置页面
├── rule-chain-new.html          # 新版规则链配置页面（推荐）
├── app.js                      # Vue 3 应用主文件
├── config.js                   # 配置文件（节点类型、API配置）
├── api-service.js              # API 服务封装
├── utils.js                   # 工具函数
├── components/                # Vue 组件
│   ├── NodeConfigEditor.vue    # 节点配置编辑器
│   ├── RuleChainEditor.vue     # 规则链编辑器
│   ├── NodePalette.vue         # 节点面板
│   └── RuleChainList.vue      # 规则链列表
└── package.json
```

## 启动方式

### 开发模式
```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173

### 生产构建
```bash
npm run build
npm run preview
```

## 功能特性

### 1. 告警仪表盘 (index.html)
- 实时告警列表展示
- 告警统计图表
- 告警详情查看
- 多维度筛选（严重程度、链ID、地址）

### 2. 规则链配置 (rule-chain-new.html)

#### 节点类型
| 类型 | 图标 | 描述 | 配置项 |
|------|------|------|--------|
| 触发器 | ⚡ | 规则链的起始节点 | 无 |
| 检测器 | 🛡️ | 执行安全检测 | 检测器类型（8种） |
| 条件判断 | 🔍 | 根据条件分支 | 字段、操作符、比较值 |
| 过滤器 | 🔽 | 过滤不符合条件的告警 | 过滤表达式 |
| 执行动作 | ⚙️ | 设置属性或标记 | 操作类型、参数值 |
| 评分 | 📊 | 计算风险评分 | 评分权重 |
| 通知 | 📢 | 发送告警通知 | 通知类型、目标地址 |

#### 支持的检测器
- ⚡ Flash Loan 检测
- 🔐 Token 授权检测
- 💰 Token 异常检测
- 🔗 地址图谱分析
- ⛽ Gas 价格检测
- 📅 地址年龄检测
- 🏷️ ARKM 标签检测
- 🏢 地址类型检测

#### 交互操作
1. **拖拽节点**: 从左侧面板拖拽节点到画布
2. **配置节点**: 双击节点打开配置弹窗
3. **移动节点**: 拖拽节点卡片移动位置
4. **连接节点**: 从节点边缘的圆点拖拽到另一个节点
5. **删除连接**: 点击连线打开设置，选择删除
6. **保存规则链**: 点击右上角"保存规则链"按钮
7. **加载规则链**: 从左侧列表选择已保存的规则链

#### 后端数据格式
```json
{
  "name": "规则链名称",
  "description": "描述",
  "enabled": true,
  "nodes": [
    {
      "id": "node_1",
      "type": "detector",
      "label": "检测器",
      "config": {
        "detectorType": "flash_loan"
      },
      "position": {
        "x": 100,
        "y": 100
      }
    }
  ],
  "edges": [
    {
      "id": "edge_1",
      "source": "node_1",
      "target": "node_2",
      "label": "条件满足"
    }
  ]
}
```

## API 接口

### 告警相关
- `GET /alert/alerts` - 获取告警列表
- `GET /alert/stats` - 获取告警统计
- `POST /alert/submit` - 提交告警

### 规则链相关
- `GET /rule-chain/` - 获取规则链列表
- `GET /rule-chain/{id}` - 获取单个规则链
- `POST /rule-chain/` - 创建规则链
- `PUT /rule-chain/{id}` - 更新规则链
- `DELETE /rule-chain/{id}` - 删除规则链

## 技术栈

- **前端框架**: Vue 3 (Composition API)
- **构建工具**: Vite
- **样式框架**: Tailwind CSS
- **图表库**: Chart.js
- **HTTP 客户端**: Axios

## 开发说明

### 组件开发
所有 Vue 组件使用 ES6 模块格式，通过 `<script type="module">` 引入。

### 样式约定
- 使用 Tailwind CSS 类名
- 自定义样式写在 `<style>` 标签中
- 遵循 BEM 命名约定（如果需要）

### API 调用
统一使用 `apiService` 对象的方法：
```javascript
import apiService from './api-service.js'

const chains = await apiService.getRuleChains()
await apiService.createRuleChain(chainData)
```

## 故障排查

### 模块加载错误
确保所有 JS 文件都使用正确的模块导入语法。

### API 连接错误
1. 确认后端服务正在运行（http://localhost:8000）
2. 检查 API Key 配置
3. 查看浏览器控制台错误信息

### CORS 问题
后端需要配置 CORS 允许跨域请求：
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 更新日志

### v2.0.0 (当前版本)
- 重构为 Vue 3 模块化架构
- 改进拖拽连线功能
- 增强节点配置界面
- 优化代码结构和可维护性

### v1.0.0
- 初始版本，单文件 HTML + Vue CDN
- 基本的拖拽和连线功能
