# AlertProcessor

## 项目概述
AlertProcessor是一个基于FastAPI的区块链安全告警处理服务，用于接收、处理和评估区块链交易的安全告警信息。该服务通过一系列处理器对告警进行多维度分析，包括利用者地址标签检查、创建时间分析和交易费用评估等，以确定告警的可信度和风险级别。

## 主要功能

- **告警接收与处理**：提供Webhook接口接收区块链安全告警信息
- **多维度风险评估**：
  - 利用者地址标签检查（使用ARKM Intelligence API）
  - 受害者地址标签检查
  - 利用者地址创建时间分析（使用Moralis API）
  - 交易Gas价格异常检测
  - 空地址检测
- **数据库存储**：使用SQLite存储告警信息和合约地址数据
- **Docker支持**：提供完整的Docker部署方案
- **配置管理**：支持环境变量和配置文件的灵活配置

## 技术栈

- **后端框架**：FastAPI
- **数据库**：SQLite + SQLAlchemy
- **配置管理**：Pydantic Settings
- **区块链接口**：Web3.py、Moralis API、ARKM Intelligence API
- **部署**：Docker、Docker Compose

## 项目结构

```
AlertProcessor/
├── main.py                 # FastAPI应用入口
├── config/                 # 配置相关模块
│   ├── __init__.py
│   └── model.py            # 配置模型定义
├── database/               # 数据库相关模块
│   ├── __init__.py
│   └── models.py           # 数据库模型定义
├── processor/              # 告警处理器模块
│   ├── __init__.py
│   ├── core.py             # 处理器基类
│   ├── chained_processor.py # 链式处理器
│   ├── exploiter_arkm_label_check.py # 利用者标签检查
│   ├── victim_label_check.py # 受害者标签检查
│   ├── exploiter_create_time.py # 利用者创建时间检查
│   ├── gas_price_check.py  # Gas价格检查
│   ├── null_address_detector.py # 空地址检测
│   └── models.py           # 处理器相关数据模型
├── routers/                # API路由模块
│   ├── __init__.py
│   └── alert/              # 告警相关路由
│       └── router.py
├── .env                    # 本地开发配置
├── .env.docker             # Docker环境配置
├── Dockerfile              # Docker构建文件
├── docker-compose.yml      # Docker Compose配置
└── requirements.txt        # Python依赖列表
```

## 安装与运行

### 本地开发环境

1. **创建虚拟环境**
```bash
python -m venv .venv
```

2. **激活虚拟环境**
```bash
# Windows
.\.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate
```

3. **安装依赖**
```bash
pip install -r requirements.txt
```

4. **配置环境变量**
编辑`.env`文件，填写必要的API密钥和配置参数

5. **启动服务**
```bash
python main.py
```

### Docker部署

1. **构建Docker镜像**
```bash
docker-compose build
```

2. **启动服务**
```bash
docker-compose up -d
```

3. **查看服务日志**
```bash
docker-compose logs -f
```

## API接口

### 告警接收接口
- **URL**: `/alert`
- **Method**: `POST`
- **请求体**:
  ```json
  {
    "chain_id": 1,
    "attacked_address": "0x123...",
    "exploiter_address": "0x456...",
    "tx_hash": "0x789..."
  }
  ```
- **响应**:
  ```json
  {
    "alert_id": "uuid-string",
    "status": "received",
    "message": "Alert received and processing started"
  }
  ```

### 健康检查接口
- **URL**: `/`
- **Method**: `GET`
- **响应**:
  ```json
  {
    "status": "healthy",
    "message": "Alert Webhook Service is running"
  }
  ```

## 处理器链

系统使用链式处理器模式，按顺序应用多个处理器对告警进行分析：

1. `ExploiterARKMLabelCheckAlertProcessor` - 检查利用者地址的标签信息
2. `VictimARKMLabelCheckAlertProcessor` - 检查受害者地址的标签信息
3. `ExploiterCreateTimeProcessor` - 分析利用者地址的创建时间
4. `TransactionGasPriceCheckAlertProcessor` - 检查交易Gas价格是否异常

每个处理器返回的结果包含：
- `need_more_check`: 是否需要继续后续处理器检查
- `score`: 风险评分
- `process_details`: 处理详情

## 配置说明

主要配置参数位于`.env`文件：

- `api_key`: API访问密钥
- `database_url`: 数据库连接URL
- `host`/`port`: 服务监听地址和端口
- `moralis_api_key`: Moralis API密钥
- `arkm_cookie`: ARKM Intelligence API cookie
- `chainId_to_provider_url`: 各链的RPC提供者URL

在Docker环境中，可通过`.env.docker`文件或环境变量覆盖默认配置。

## 注意事项

1. **API密钥配置**：确保正确配置Moralis和ARKM Intelligence的API密钥，否则相关处理器可能无法正常工作

2. **数据库权限**：在Docker部署时，确保数据目录具有正确的读写权限

3. **环境变量优先级**：环境变量始终优先于配置文件设置

4. **Docker环境检测**：服务会通过`DOCKER_ENV`环境变量检测是否在Docker环境中运行，从而决定是否加载`.env`文件

## 日志和监控

系统使用Python标准日志模块记录关键操作和错误信息。在Docker部署时，可以通过`docker-compose logs`查看服务日志。

## 许可证

[MIT License](https://opensource.org/licenses/MIT)
        
