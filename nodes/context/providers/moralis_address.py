"""
Moralis 地址信息 Provider (v3 — 基于 moralis 官方 SDK + apipool 池加载)

通过 Moralis Web3 Data API (evm_api.wallets) 获取地址首次交易时间。
注入字段: address_create_time, address_age_days

Key 来源优先级:
  1. [优先] apipool-server 池 (moralis_pool_identifier)
     → 通过 MoralKeyPoolManager 从远程服务器动态拉取 key 列表
  2. [回退] 直接配置 (MORALIS_API_KEY)
     → 单个字符串或 JSON 数组，兼容旧配置方式

架构:
  ┌─────────────────────────────────────────────────────┐
  │  MoralisAddressProvider (v3)                        │
  │                                                      │
  │  api_keys 属性:                                      │
  │    ├─ ① get_moralis_key_pool().all_keys  (池模式)   │
  │    └─ ② settings.moralis_api_key        (直连回退)    │
  │                                                      │
  │  fetch() → 遍历所有 key, 故障切换调用 SDK            │
  └─────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from nodes.context.provider import ContextProvider

logger = logging.getLogger(__name__)

# chain_id → Moralis 链标识映射
CHAIN_MAP = {
    1: "eth",
    56: "bsc",
    137: "polygon",
    42161: "arbitrum",
    10: "optimism",
    43114: "avalanche",
    250: "fantom",
}

# chain_id → 默认单块时间（秒）
DEFAULT_BLOCK_TIME: dict[int, float] = {
    1: 12,          # Ethereum (post-merge)
    56: 3,          # BSC
    137: 2,         # Polygon
    42161: 0.25,    # Arbitrum (~250ms)
    10: 2,          # Optimism
    43114: 2,       # Avalanche
    250: 1,         # Fantom (1s)
}


def get_block_time(chain_id: int) -> float:
    """获取指定链的单块时间(秒)，优先从配置读取，否则使用默认值"""
    try:
        from config.model import settings
        cfg = settings.block_time_config
        if isinstance(cfg, dict) and str(chain_id) in cfg:
            return float(cfg[str(chain_id)])
        if chain_id in cfg:
            return float(cfg[chain_id])
    except Exception:
        pass
    return DEFAULT_BLOCK_TIME.get(chain_id, 12.0)


class MoralisAddressProvider(ContextProvider):
    """
    Moralis 地址信息提供者（v3 — 支持从 apipool-server 加载 Key）。

    注入字段:
      - address_create_time: str — 地址创建时间 ISO8601 格式
      - address_age_days: int    — 地址创建距今天数

    Key 来源（按优先级）:
      1. apipool-server 池 (moralis_pool_identifier): 远程集中管理
      2. MORALIS_API_KEY 配置 (.env 或代码传入): 本地直连

    配置方式 (.env):
      # 方式一：通过 apipool-server 池管理（推荐）
      MORALIS_POOL_IDENTIFIER=moralis-keys
      APIPOOL_SERVER_URL=http://localhost:8000
      APIPOOL_USERNAME=alice
      APIPOOL_PASSWORD=secret

      # 方式二：直接配置单个/多个 Key（兼容旧版）
      MORALIS_API_KEY=your_single_key
      # 或
      MORALIS_API_KEY=["key1","key2","key3"]
    """

    name = "moralis_address"
    description = (
        "通过 Moralis Web3 Data API 获取地址首次交易时间。"
        "支持 apipool-server 池加载和直接配置两种 Key 来源，自动故障切换。"
    )
    provides = ["address_create_time", "address_age_days"]

    def __init__(self, api_key: str | list[str] | None = None):
        """
        初始化 Provider。

        Args:
            api_key: 单个字符串或列表（直连模式）。
                     None 时先尝试从池加载，再回退到全局配置。
        """
        self._api_keys_raw = api_key  # 直连模式的原始输入
        self._resolved_keys: list[str] | None = None

    @property
    def api_keys(self) -> list[str]:
        """
        获取已解析的 API Key 列表。

        优先级:
          1. 如果有显式传入的 _api_keys_raw (直连模式) → 使用它，永久缓存
          2. 否则尝试从 MoralKeyPoolManager (apipool) 加载 → 不缓存（池动态变化）
          3. 最后回退到 settings.moralis_api_key (直连) → 永久缓存
        """
        # 直连模式的 key 可以安全缓存（不会变化）
        if self._resolved_keys is not None and self._api_keys_raw is not None:
            return self._resolved_keys

        # 优先使用构造时传入的 key（永久缓存）
        if self._api_keys_raw is not None:
            self._resolved_keys = self._normalize_keys(self._api_keys_raw)
            logger.info(f"[MoralisAddress] Using direct keys: {len(self._resolved_keys)} keys")
            return self._resolved_keys

        # 尝试从 apipool 池加载（不缓存 — 池状态可能随时通过 Reload 变化）
        pool_keys = self._load_from_apipool()
        if pool_keys:
            logger.info(f"[MoralisAddress] Loaded {len(pool_keys)} keys from apipool pool")
            return pool_keys

        # 回退到本地配置（永久缓存）
        raw = self._load_from_settings()
        resolved = self._normalize_keys(raw)
        if not raw:  # 原始值为空时不缓存（用户后续可能配置了）
            logger.warning(
                "[MoralisAddress] No keys from pool or local config, "
                "provider will skip fetch()"
            )
        else:
            self._resolved_keys = resolved
            logger.info(f"[MoralisAddress] Fallback to settings.moralis_api_key: {len(resolved)} keys")
        return resolved

    def _load_from_apipool(self) -> list[str]:
        """尝试从 MoralKeyPoolManager 全局单例获取 key"""
        try:
            from nodes.context.providers.moralis_key_pool import get_moralis_key_pool

            mgr = get_moralis_key_pool()
            if mgr is not None and mgr.is_ready:
                return mgr.all_keys
            return []
        except Exception as e:
            logger.debug(f"[MoralisAddress] Apipool pool unavailable: {e}")
            return []

    def _load_from_settings(self) -> str | list[str] | None:
        """从全局 settings 延迟加载 API Key（直连回退）"""
        try:
            from config.model import settings
            return settings.moralis_api_key
        except Exception as e:
            logger.warning(f"[MoralisAddress] Failed to load settings: {e}")
            return None

    @staticmethod
    def _normalize_keys(raw: str | list[str] | None) -> list[str]:
        """将原始输入规范化为 key 列表"""
        if not raw:
            return []

        if isinstance(raw, list):
            seen = set()
            result = []
            for k in raw:
                if k is None or (isinstance(k, str) and not k.strip()):
                    continue
                k_str = str(k).strip()
                if k_str and k_str not in seen:
                    seen.add(k_str)
                    result.append(k_str)
            return result

        if isinstance(raw, str):
            stripped = raw.strip()
            if not stripped:
                return []

            import json
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    seen = set()
                    result = []
                    for item in parsed:
                        s_item = str(item).strip()
                        if s_item and s_item not in seen:
                            seen.add(s_item)
                            result.append(s_item)
                    return result
            except (json.JSONDecodeError, TypeError):
                pass

            return [stripped]

        return []

    async def fetch(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        获取地址创建时间信息。

        策略:
          1. 如果 context 中已有 address_create_time / address_age_days → 跳过
          2. 从 context 提取目标地址
          3. 按优先级遍历所有 API Key（来自池或本地），逐个尝试
          4. 返回第一个成功的结果
        """
        # 1. 检查已有数据
        if context.get("address_create_time") or context.get("address_age_days"):
            return {}

        # 2. 提取目标地址
        target_addr = self._extract_target_address(context)
        if not target_addr:
            logger.debug("[MoralisAddress] No target address in context, skipping")
            return {}

        chain_id = self.extract_chain_id(context)
        keys = self.api_keys

        # DEBUG: 打印完整的 key 加载信息
        logger.info(
            f"[MoralisAddress] fetch() called: "
            f"addr={target_addr[:10]}..., chain={chain_id}, "
            f"keys_count={len(keys)}, "
            f"_api_keys_raw={self._api_keys_raw!r}, "
            f"_resolved_keys_cached={self._resolved_keys is not None}"
        )
        if keys:
            for i, k in enumerate(keys):
                # 只显示前4和后4字符保护 key 安全性
                masked = k[:4] + "..." + k[-4:] if len(k) > 8 else "***"
                logger.info(f"[MoralisAddress]   key[{i}]={masked} (len={len(k)})")

        if not keys:
            logger.warning("[MoralisAddress] No API keys configured, skipping")
            return {}

        # 3. 按 key 逐一尝试（apipool 式故障切换）
        last_error = ""
        for idx, api_key in enumerate(keys):
            try:
                logger.info(f"[MoralisAddress] Trying key[{idx}/{len(keys)}] for {target_addr[:10]}...")
                result = await self._call_moralis_sdk(
                    address=target_addr,
                    chain_id=chain_id,
                    api_key=api_key,
                )
                if result:
                    logger.debug(
                        f"[MoralisAddress] Success with key[{idx}]: "
                        f"addr={target_addr[:10]}..., age={result.get('address_age_days')}d"
                    )
                    return result
                else:
                    logger.debug(
                        f"[MoralisAddress] No data from key[{idx}] "
                        f"(addr={target_addr[:10]}...)"
                    )
            except Exception as e:
                import traceback
                exc_type = type(e).__name__
                exc_args = getattr(e, 'args', None)
                # 对于 httpx 错误，提取额外上下文
                extra = ""
                if hasattr(e, 'response'):
                    resp = e.response
                    extra = f" [HTTP {resp.status_code} {resp.reason_phrase or ''}]"
                    if hasattr(resp, 'url'):
                        extra += f" url={str(resp.url)[:80]}"
                elif hasattr(e, 'request') and hasattr(e.request, 'url'):
                    extra = f" url={str(e.request.url)[:80]}"
                
                last_error = f"{exc_type}: {e}"
                logger.warning(
                    f"[MoralisAddress] key[{idx}/{len(keys)}] failed: "
                    f"{exc_type}: {e}{extra}"
                )
                logger.debug(
                    f"[MoralisAddress] Full traceback for key[{idx}]: "
                    + traceback.format_exc()
                )
                continue

        # 所有 Key 均失败
        if last_error:
            return {"_moralis_address_error": f"All keys exhausted. Last error: {last_error}"}
        return {"_moralis_address_error": "No data returned for this address"}

    def _extract_target_address(self, context: dict[str, Any]) -> str:
        """提取要查询的目标地址（优先 exploiter_address）"""
        exploiter = context.get("exploiter_address", "")
        if isinstance(exploiter, str) and exploiter.startswith("0x"):
            return exploiter.lower()

        addresses = self.extract_addresses(context)
        return addresses[0] if addresses else ""

    async def _call_moralis_sdk(
        self,
        address: str,
        chain_id: int,
        api_key: str,
    ) -> dict[str, Any]:
        """
        通过 Moralis Web3 Data API v2.2 Wallet Chain Activity 获取地址首次交易时间。

        API 文档: https://docs.moralis.com/data-api/evm/wallet/chain-activity
        端点: GET /api/v2.2/wallets/{address}/chains

        响应结构:
          {
            "address": "...",
            "active_chains": {
              "{chain}": {
                "chain": "{chain}",
                "first_transaction": 1234567890,   ← Unix 时间戳（秒）
                "block_number": 18900000,
                "block_timestamp": "2024-01-15T12:30:45Z"
              }
            }
          }

        first_transaction 字段为 Unix 时间戳（整数），直接转换为地址创建时间。
        使用 httpx 异步 HTTP 客户端。每次调用后自动记录 stats 到 apipool。
        """
        import httpx
        import time as _time

        chain_name = CHAIN_MAP.get(chain_id, "eth")
        # 官方文档端点：Wallet Chain Activity
        url = f"https://deep-index.moralis.io/api/v2.2/wallets/{address}/chains"

        key_preview = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "***"
        logger.info(f"[MoralisAddress] GET {url} (key={key_preview}, chain={chain_name})")

        t0 = _time.monotonic()
        is_rate_limit = False
        call_success = False
        data = None

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    url,
                    headers={
                        "accept": "application/json",
                        "X-API-Key": api_key,
                    },
                )

                # 检测速率限制 (Moralis 返回 429)
                if resp.status_code == 429:
                    is_rate_limit = True
                    resp.raise_for_status()

                resp.raise_for_status()
                data = resp.json()

                logger.info(
                    f"[MoralisAddress] Response {resp.status_code}: "
                    f"top_keys={list(data.keys())[:8]}"
                )

            call_success = True

        except Exception as e:
            latency = _time.monotonic() - t0
            # 记录失败事件到 stats
            self._record_moralis_call(api_key, success=False, latency=latency,
                                      method="wallet_chains", is_rate_limit=is_rate_limit)
            raise

        # 记录成功事件到 stats
        latency = _time.monotonic() - t0
        self._record_moralis_call(api_key, success=True, latency=latency, method="wallet_chains")

        # ── 解析响应 ──
        # 实际 API 响应格式 (2026-04):
        # {
        #   "address": "0x...",
        #   "active_chains": [
        #     {
        #       "chain": "eth",
        #       "chain_id": "0x1",
        #       "first_transaction": {
        #         "block_number": "24637043",
        #         "block_timestamp": "2026-03-11T21:55:35.000Z",
        #         "transaction_hash": "0x..."
        #       },
        #       "last_transaction": { ... }
        #     },
        #     ...
        #   ]
        # }
        active_chains = data.get("active_chains") or []

        chain_info = None
        if isinstance(active_chains, dict):
            # 兼容字典格式（旧版/文档版）: { "eth": {...} }
            chain_info = active_chains.get(chain_name) if chain_name else None
        elif isinstance(active_chains, list):
            for item in active_chains:
                if isinstance(item, dict) and item.get("chain") == chain_name:
                    chain_info = item
                    break

        if not chain_info:
            logger.debug(
                f"[MoralisAddress] No activity on chain={chain_name} "
                f"for {address} (ac_type={type(active_chains).__name__})"
            )
            return {}

        # ── 提取 first_transaction ──
        # 实际格式: first_transaction = { block_number, block_timestamp, transaction_hash }
        # 文档截图可能显示为 Unix 整数，兼容两种情况
        ft = chain_info.get("first_transaction")
        if ft and isinstance(ft, dict):
            # 对象格式: { block_timestamp: "2024-01-15T12:30:45.000Z", block_number: "24637043" }
            ts_str = ft.get("block_timestamp")
            bn_str = ft.get("block_number")
            bn = None
            if bn_str is not None:
                try:
                    bn = int(bn_str)
                except (ValueError, TypeError):
                    pass
            if ts_str:
                return self._build_result(address, str(ts_str), bn)
        elif ft is not None:
            # 可能是文档截图中的 Unix 时间戳整数
            try:
                unix_ts = int(ft)
                if unix_ts > 0:
                    return self._build_result_from_unix(address, unix_ts)
            except (ValueError, TypeError):
                pass

        # 回退: 直接从 chain_info 顶层找时间戳字段
        block_ts = self._extract_timestamp_from_data(chain_info)
        if block_ts:
            return self._build_result(address, block_ts)

        logger.debug(
            f"[MoralisAddress] No usable timestamp in "
            f"chain_info keys={list(chain_info.keys())[:6]}"
        )
        return {}

    @staticmethod
    def _record_moralis_call(api_key: str, success: bool, latency: float,
                             method: str = "call", is_rate_limit: bool = False) -> None:
        """记录一次 Moralis API 调用到 apipool StatsCollector"""
        try:
            from nodes.context.providers.moralis_key_pool import get_moralis_key_pool
            mgr = get_moralis_key_pool()
            if mgr is not None and mgr.stats is not None:
                mgr.record_call(
                    api_key=api_key,
                    success=success,
                    latency=latency,
                    method=method,
                    is_rate_limit=is_rate_limit,
                )
        except Exception as e:
            logger.debug(f"[MoralisAddress] Failed to record stats: {e}")

    @staticmethod
    def _extract_first_transaction(data: dict[str, Any]) -> int | None:
        """从 chain info 中提取 first_transaction Unix 时间戳"""
        # 尝试多种字段名变体
        for field in ("first_transaction", "firstTransaction"):
            val = data.get(field)
            if val is not None:
                try:
                    # 可能是字符串或数字
                    if isinstance(val, (int, float)):
                        ts = int(val)
                        return ts if ts > 0 else None
                    sval = str(val).strip()
                    if sval.isdigit():
                        ts = int(sval)
                        return ts if ts > 0 else None
                except (ValueError, TypeError):
                    pass
        return None

    @staticmethod
    def _extract_timestamp_from_data(data: dict[str, Any]) -> str | None:
        """从字典中按优先级提取时间戳字符串字段"""
        for field in (
            "block_timestamp",           # 链活动标准字段
            "blockTimestamp",
            "created_at",
            "createdAt",
            "first_transaction_timestamp",   # 兼容钱包详情
            "firstTransactionTimestamp",
        ):
            val = data.get(field)
            if val:
                sval = str(val).strip()
                if sval and sval not in ("None", "null", "", "0"):
                    return sval
        return None

    @staticmethod
    def _build_result(address: str, create_time_str: str, first_block_number: int | None = None) -> dict[str, Any]:
        """根据 ISO 时间字符串构建标准结果"""
        ct_str = create_time_str.strip()
        if ct_str.endswith("Z"):
            ct_str = ct_str[:-1] + "+00:00"

        ct = datetime.fromisoformat(ct_str)
        if ct.tzinfo is None:
            ct = ct.replace(tzinfo=timezone.utc)

        age_days = (datetime.now(timezone.utc) - ct).days
        result = {
            "address_create_time": ct.isoformat(),
            "address_age_days": age_days,
            "address_queried": address,
        }
        if first_block_number is not None:
            result["first_block_number"] = first_block_number
        return result

    @staticmethod
    def _build_result_from_unix(address: str, unix_ts: int) -> dict[str, Any]:
        """根据 Unix 时间戳构建标准结果"""
        if unix_ts <= 0:
            logger.debug(f"[MoralisAddress] Invalid unix timestamp: {unix_ts}")
            return {}

        try:
            ct = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            logger.warning(f"[MoralisAddress] Cannot parse unix timestamp {unix_ts}: {type(e).__name__}")
            return {}

        age_days = (datetime.now(timezone.utc) - ct).days
        return {
            "address_create_time": ct.isoformat(),
            "address_age_days": age_days,
            "address_queried": address,
        }
