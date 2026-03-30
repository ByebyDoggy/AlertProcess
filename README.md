# AlertProcessor

## 项目概述

AlertProcessor 是一个基于 FastAPI 的区块链安全告警处理服务，灵感来自 [Forta Network](https://forta.org/) 和 [BlockSec](https://blocksec.com/)。用于接收、处理和分析区块链交易的安全告警信息。

## 主要功能

- **告警接收与处理**：Webhook 接口接收来自区块链安全监控系统的告警
- **多维度检测框架**：基于插件化的 Detector 架构
  - ARKM 实体标签检测
  - 地址年龄检测
  - Gas 价格异常检测
  - 闪电贷检测
  - Token 授权检测
  - Token 异常检测
  - 地址图谱分析
- **规则引擎**：灵活的可配置规则进行告警筛选和分类
- **评分系统**：多维度风险评分
- **告警通知**：Webhook 通知
- **前端仪表板**：可视化告警管理和分析

## 技术栈

- **后端**：FastAPI、SQLAlchemy、Pydantic
- **前端**：Vue 3、Tailwind CSS、Chart.js
- **数据库**：SQLite
- **区块链**：Web3.py、Moralis API、ARKM Intelligence API

## 项目结构

```
AlertProcessor/
├── main.py                    # FastAPI 应用入口
├── config/                     # 配置管理
│   └── model.py               # Pydantic Settings
├── database/                   # 数据库模型
│   └── models.py
├── models/                     # 核心数据模型
│   └── __init__.py            # AlertInput, DetectionResult, FinalAlert
├── detectors/                   # 插件化检测器
│   ├── base.py                 # Detector 基类 + Registry
│   └── implementations/
│       ├── arkm_label_detector.py
│       ├── address_age_detector.py
│       ├── gas_price_detector.py
│       ├── address_type_detector.py
│       ├── flash_loan_detector.py
│       ├── token_approval_detector.py
│       ├── token_anomaly_detector.py
│       └── address_graph_detector.py
├── rules/                       # 规则引擎
│   └── engine.py
├── scoring/                     # 评分引擎
│   └── engine.py
├── notifiers/                   # 通知渠道
│   └── base.py
├── routers/                     # API 路由
│   └── alert/
│       └── router.py           # /alert/* 端点
├── data_providers/               # 数据提供者
│   ├── base.py
│   └── context_builder.py       # TransactionContext 构建
├── frontend/                    # 前端仪表板
│   ├── index.html
│   ├── api.js
│   ├── package.json
│   └── vite.config.js
├── tests/                       # 单元测试
│   └── test_*.py
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件：

```env
api_key=your-secret-api-key
moralis_api_key=your-moralis-api-key
arkm_cookie=your-arkm-cookie
```

### 3. 启动服务

```bash
python main.py
```

服务将在 http://localhost:8000 启动

### 4. Docker 部署

```bash
docker-compose up -d
```

## API 接口

### 健康检查

```
GET /
```

### 提交告警

```
POST /alert/submit
X-API-Key: your-api-key

{
  "chain_id": 1,
  "tx_hash": "0x...",
  "attacked_address": "0x...",
  "exploiter_address": "0x..."
}
```

### 列出告警

```
GET /alert/alerts?skip=0&limit=100&severity=CRITICAL
X-API-Key: your-api-key
```

### 告警统计

```
GET /alert/stats
X-API-Key: your-api-key
```

## Detector 架构

每个 Detector 实现以下接口：

```python
class Detector(ABC):
    name: str
    config: DetectorConfig
    
    async def detect(
        self, 
        alert: AlertInput, 
        context: TransactionContext
    ) -> DetectionResult
```

### 内置检测器

| 检测器 | 功能 |
|--------|------|
| ARKMLabelDetector | 检查地址是否被标记为恶意实体 |
| AddressAgeDetector | 检测新创建的地址 |
| GasPriceDetector | 检测异常高的 Gas 价格 |
| AddressTypeDetector | 检测空地址和合约创建 |
| FlashLoanDetector | 检测闪电贷攻击 |
| TokenApprovalDetector | 检测可疑的 Token 授权 |
| TokenAnomalyDetector | 检测异常的 Token 转账 |
| AddressGraphDetector | 分析地址与交易所/攻击者的关联 |

## 测试

```bash
pytest tests/ -v
```

## 前端仪表板

访问 http://localhost:8000 查看可视化告警仪表板。

## License

MIT
