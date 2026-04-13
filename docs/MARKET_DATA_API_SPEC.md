# MarketDataBase API 需求规格书

> **用途**: AlertProcessor 的 Balance Changes 面板需要从 MarketDataBase 获取代币的**实时价格 + 精度(decimals)**，以计算每笔余额变动的 USD 估值。
>
> **调用方**: AlertProcessor 后端 (`detectors/trace/analyzer.py` -> `compute_balance_changes()`)
>
> **数据流**: AlertProcessor 收集到一笔交易的所有 ERC20/ETH 余额变动后，提取涉及的 token 合约地址列表，一次性批量查询 MarketDataBase 获取价格+精度，然后在内存中缓存结果用于高速刷新场景。

---

## 一、核心需求：Balance Changes 价格计算公式

```
value_usd = (amount_raw / 10^decimals) * price_usd

其中:
  amount_raw  : 链上原始金额 (wei 单位整数)，来自 receipt logs 解码的 Transfer event
  decimals    : 代币精度 (ETH/WETH=18, USDT=6, etc.)
  price_usd   : 该代币当前 USD 价格
```

### 示例计算

| 场景 | token | decimals | amount_raw | price_usd | value_usd |
|------|-------|----------|------------|-----------|-----------|
| 收到 ETH | ETH (native) | 18 | 65361960326939766177 | $3,500.00 | +$228.77 |
| 转出 WETH | WETH | 18 | 2305427700000000000 | $3,499.50 | -$8,068.41 |
| 收到 USDT | USDT | 6 | 15000000 | $1.00 | +$15.00 |
| 转出 UNI | UNI | 18 | 5000000000000000000 | $7.25 | -$36.25 |

---

## 二、所需 API 端点（需 MarketDataBase 新增/改造）

### 端点 1: 批量获取代币完整信息（核心接口）

> **优先级**: P0 — 必须实现
> **建议**: 改造现有 `POST /api/v1/tokens/batch-prices` 或新增端点

#### 请求

```
POST /api/v1/tokens/batch-info
Content-Type: application/json

{
  "contract_addresses": [
    "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",   // WETH
    "0xdAC17F958D2ee523a2206206994597C13D831ec7",   // USDT
    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"     // USDC
  ],
  "chain_name": "ethereum",
  // 可选：是否包含原生代币（ETH/BNB 等），默认 true
  "include_native": true
}
```

#### 响应

```json
{
  "success": true,
  "data": {
    "tokens": {
      "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": {
        "symbol": "WETH",
        "name": "Wrapped Ether",
        "decimals": 18,
        "price_usd": 3499.50,
        "price_usd_24h_change": 2.35,
        "logo_url": "https://example.com/weth.png"
      },
      "0xdac17f958d2ee523a2206206994597c13d831ec7": {
        "symbol": "USDT",
        "name": "Tether USD",
        "decimals": 6,
        "price_usd": 1.00,
        "price_usd_24h_change": 0.01,
        "logo_url": "https://example.com/usdt.png"
      },
      "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": {
        "symbol": "USDC",
        "name": "USD Coin",
        "decimals": 6,
        "price_usd": 1.00,
        "price_usd_24h_change": -0.02,
        "logo_url": "https://example.com/usdc.png"
      }
    },
    // 特殊 key: 原生代币（当 include_native=true 时返回）
    "__native__": {
      "symbol": "ETH",
      "name": "Ethereum",
      "decimals": 18,
      "price_usd": 3500.00,
      "price_usd_24h_change": 2.40,
      "logo_url": "https://example.com/eth.png"
    }
  },
  "metadata": {
    "total_requested": 3,
    "found": 3,
    "not_found": [],
    "data_timestamp": "2026-04-07T12:30:00Z",
    "source": "coingecko"
  }
}
```

#### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `symbol` | string | ✅ | 代币符号，如 "WETH"、"USDT" |
| `name` | string | ❌ | 代币全称 |
| `decimals` | integer | ✅ | 代币精度，如 18、6。**这是 AlertProcessor 最需要的字段之一** |
| `price_usd` | float \| null | ✅ | 当前 USD 价格。查不到时返回 `null`（不报错） |
| `price_usd_24h_change` | float \| null | ❌ | 24小时涨跌幅百分比 |
| `logo_url` | string \| null | ❌ | 代币 Logo URL |

#### 关键行为约定

1. **地址大小写不敏感**: 所有合约地址在请求/响应中统一为 **checksum (EIP-55)** 格式或 **小写**
2. **未找到的地址**: 在响应中**不出现**该 key（或在 `metadata.not_found` 中列出），调用方应将未找到的代币视为 `price_usd=null`
3. **原生代币**: 使用特殊 key `"__native__"` 返回链的原生代币信息（ETH/BNB/MATIC 等），由 `chain_name` 决定
4. **性能要求**: 单次查询 10-50 个地址应在 **<200ms** 内返回（纯本地 DB 查询）
5. **空数组**: 如果 `contract_addresses` 为空数组，仅返回 `__native__` 信息（如果 `include_native=true`）

---

### 端点 2: 按合约地址获取单个代币详情（已有，可能需要增强）

> **优先级**: P1 — 已存在 `GET /api/v1/tokens/by-contract/{addr}`，确认其返回 decimals 即可
> **用途**: 补充查询单个未知 token 的详细信息

#### 请求

```
GET /api/v1/tokens/by-contract/{contract_address}?chain_name=ethereum
```

#### 期望响应（需确认已包含 decimals）

```json
{
  "id": 1234,
  "coingecko_id": "weth",
  "symbol": "WETH",
  "name": "Wrapped Ether",
  "price_usd": 3499.50,
  "price_btc": 0.05812,
  "price_eth": 1.0,
  "market_cap": 28000000000,
  "volume_24h": 450000000,
  "change_24h": 2.35,
  "addresses": [
    {
      "chain_name": "ethereum",
      "contract_address": "0xC02aaA39b223fe8d0A0e5C4F27eAD9083C756Cc2",
      "decimals": 18,
      "is_native": false
    }
  ],
  "logo_url": "...",
  "updated_at": "2026-04-07T12:30:00Z"
}
```

**注意**: 此端点已存在于 MarketDataBase，只需确认 `addresses[].decimals` 字段能正确返回即可。

---

## 三、AlertProcessor 端缓存策略

MarketDataBase 无需关心此部分，但以下说明有助于理解为什么需要上述 API 设计。

### 缓存架构

```
┌─────────────────────────────────────────────────┐
│              AlertProcess 进程内存                │
│                                                   │
│  ┌─────────────────────────────────────────┐     │
│  │      TokenMetadataCache (LRU / TTL)       │     │
│  │                                          │     │
│  │  Key:   (chain_id, contract_addr)         │     │
│  │          "" 表示原生代币                    │     │
│  │  Value: {                                │     │
│  │    symbol: "WETH",                       │     │
│  │    decimals: 18,                        │     │
│  │    price_usd: 3499.50,                  │     │
│  │    fetched_at: timestamp                 │     │
│  │  }                                       │     │
│  │                                          │     │
│  │  TTL: 60s (价格)                         │     │
│  │  TTL: ∞   (symbol/decimals 不变质)       │     │
│  └──────────────────┬──────────────────────┘     │
│                     │                              │
│           命中? ────┼─── Yes → 直接使用              │
│                     │ No                            │
│                     ▼                               │
│        ┌──────────────────────┐                     │
│        │ POST batch-info      │                     │
│        │ → MarketDataBase      │                     │
│        └──────────┬───────────┘                     │
│                   ▼                                  │
│              写入缓存                                 │
└─────────────────────────────────────────────────────┘
```

### 为什么需要内存缓存？

Balance Changes 页面在日志高速刷新时（如监控模式），同一笔交易可能在短时间内被重复解析：
- 同一交易 hash 可能被前端多次轮询
- 不同交易涉及相同的常用代币 (ETH, WETH, USDT, USDC)
- 每次都远程调用 MarketDataBase 会造成不必要的延迟和网络开销

### 缓存伪代码

```python
class TokenMetadataCache:
    """进程内 Token 元数据缓存"""

    def __init__(self):
        self._cache: dict[str, TokenMeta] = {}
        self._price_ttl_seconds = 60   # 价格缓存 60 秒
        # symbol/decimals 永久缓存（不会变化）

    def get(self, chain_id: int, token_address: str) -> TokenMeta | None:
        key = f"{chain_id}:{token_address.lower()}"
        meta = self._cache.get(key)
        if not meta:
            return None
        # 检查价格是否过期
        if (time.time() - meta.fetched_at) > self._price_ttl_seconds:
            return None  # 价格过期，需要刷新
        return meta

    async def batch_fetch(self, chain_id: int, addresses: list[str]) -> dict[str, TokenMeta]:
        """批量获取：先过滤缓存命中的，再批量查询未命中的"""
        uncached = []
        result = {}

        for addr in addresses:
            key = f"{chain_id:{addr.lower()}}"
            cached = self._cache.get(key)
            if cached and not self._is_price_stale(cached):
                result[addr] = cached
            else:
                uncached.append(addr)

        if uncached:
            # 调用 MarketDataBase batch-info 接口
            remote_data = await self._call_market_db(chain_id, uncached)
            for addr, meta in remote_data.items():
                self._cache[f"{chain_id}:{addr}"] = meta
                result[addr] = meta

        return result
```

---

## 四、与现有 API 的差异对比

| 对比项 | 现有 `batch-prices` | 新增 `batch-info` |
|--------|---------------------|-------------------|
| **路径** | `POST /api/v1/tokens/batch-prices` | `POST /api/v1/tokens/batch-info` |
| **返回价格** | ✅ `float \| null` | ✅ `float \| null` |
| **返回 decimals** | ❌ 无 | ✅ `integer` |
| **返回 symbol** | ❌ 无 | ✅ `string` |
| **返回 name** | ❌ 无 | ✅ `string` (可选) |
| **返回原生代币** | ❌ 不支持 | ✅ `"__native__"` key |
| **返回 not_found 列表** | ❌ 隐式 (值为null) | ✅ 显式 `metadata.not_found` |
| **数据源标记** | ❌ 无 | ✅ `metadata.source` |
| **时间戳** | ❌ 无 | ✅ `metadata.data_timestamp` |

### 建议：两种实现方案

**方案 A（推荐）**: 新增 `batch-info` 端点，保留原有 `batch-prices` 不动
- 优点：向后兼容，不影响其他消费者
- 实现：复用底层 Repository 查询，只是多返回几个字段

**方案 B**: 扩展现有 `batch-prices`，增加 `include_metadata=true` 参数
- 优点：减少端点数量
- 缺点：破坏已有契约，需通知所有调用方

---

## 五、错误处理规范

| 错误场景 | HTTP Status | Response Body |
|---------|-------------|---------------|
| contract_addresses 为空且 include_native=false | 400 | `{"detail": "At least one address or include_native is required"}` |
| chain_name 无效 | 400 | `{"detail": "Unsupported chain: xxx"}` |
| 地址格式非法（非 0x 开头） | 400 | `{"detail": "Invalid address format: xxx"}` |
| 服务内部错误 | 500 | `{"detail": "Internal server error", "error": "..."}` |

**重要**: 对于单个地址查不到的情况，**不应返回 404 或错误**，而是在响应中该地址对应 `null` 或直接省略。批量接口的设计原则是"尽力返回"，不要因个别失败导致整体失败。

---

## 六、测试用例参考

### Case 1: 正常批量查询（含已知和未知地址）

```json
// Request
{
  "contract_addresses": [
    "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",   // WETH ✓
    "0xdAC17F958D2ee523a2206206994597C13D831ec7",   // USDT ✓
    "0x000000000000000000000000000000000000dead"     // 不存在的合约 ✗
  ],
  "chain_name": "ethereum"
}

// Expect: 返回 2 个 token 信息，dead 地址不出现在 tokens 中，
//         metadata.not_found = ["0x0000...dead"]
```

### Case 2: 仅查询原生代币

```json
// Request
{
  "contract_addresses": [],
  "chain_name": "ethereum",
  "include_native": true
}

// Expect: 仅返回 __native__ (ETH) 信息
```

### Case 3: 大小写混合输入

```json
// Request: 输入混合大小写的地址
{
  "contract_addresses": ["0xc02aAa39B223Fe8D0A0e5c4F27eaD9083c756Cc2"]
}

// Expect: 统一以 checksum 格式（或小写）作为 response key 返回
```

---

## 七、实现 Checklist（供 MarketDataBase 开发参考）

- [ ] 新增 `POST /api/v1/tokens/batch-info` 端点
- [ ] 请求体模型: `BatchInfoRequest(addresses, chain_name, include_native)`
- [ ] 响应体模型: `BatchInfoResponse(tokens dict, metadata)`
- [ ] 从 `token_addresses` 表 JOIN `tokens` 表一次查询所有地址（避免 N+1）
- [ ] 原生代币通过 `chains.native_token_symbol` + `tokens.symbol` 匹配获取
- [ ] 未找到的地址记录到 `metadata.not_found`
- [ ] 添加单元测试覆盖以上 3 个 case
- [ ] 更新 API.md 文档

---

## 八、未来扩展（不在本期范围）

以下功能暂不需要，但值得预留设计空间：

1. **历史价格**: 某个时间点的价格（用于历史交易的准确回溯估价）。当前使用最新快照价格即可。
2. **多链支持**: 当前主要用 `chain_name="ethereum"`，后续可扩展 BSC/Polygon 等。
3. **WebSocket 推送**: 价格变更实时推送，替代 TTL 轮询。当前 60s TTL 足够。
4. **DEX 价格**: Uniswap V3 Pool 实时价格，补充长尾代币。当前 CoinGecko 数据源足够覆盖主流代币。
