"""
Moralis 地址信息 Provider 节点

通过 Moralis Web3 Data API (evm_api.wallets) 获取地址首次交易时间。
注入字段到 extra: address_create_time, address_age_days, first_block_number
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import Field

from nodes.base import NodeRegistry
from nodes.providers.base import BaseContextProviderNode
from nodes.models import TransactionContext

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
    1: 12,
    56: 3,
    137: 2,
    42161: 0.25,
    10: 2,
    43114: 2,
    250: 1,
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


class MoralisAddressProviderNode(BaseContextProviderNode):
    """
    Moralis 地址信息 Provider 节点。

    通过 Moralis Web3 Data API 获取地址首次交易时间。
    注入字段到 extra:
      - address_create_time: 地址创建时间 ISO8601 格式
      - address_age_days: 地址创建距今天数
      - first_block_number: 首次交易所在区块号

    配置:
      - moralis_pool_identifier: apipool-server 池标识符（可选）
      - 或通过 MORALIS_API_KEY 环境变量配置
    """

    name: str = "moralis_address_provider"
    label: str = "Moralis 地址查询"
    description: str = "通过 Moralis Web3 Data API 查询地址首次活跃时间，注入 address_create_time、address_age_days 等字段"
    icon: str = "\U0001f30d"
    color: str = "#14b8a6"

    provides = ["address_create_time", "address_age_days", "first_block_number"]

    async def fetch(self, tx_context: TransactionContext) -> dict[str, Any]:
        """
        获取地址创建时间信息。

        策略:
          1. 从 tx_context 提取目标地址
          2. 调用 Moralis API 获取数据
          3. 返回 extra 字段字典
        """
        # 提取目标地址
        target_addr = self._extract_target_address(tx_context)
        if not target_addr:
            logger.debug("[MoralisProviderNode] No target address in context, skipping")
            return {}

        chain_id = tx_context.chain_id or 1
        keys = self._get_api_keys()

        if not keys:
            logger.warning("[MoralisProviderNode] No API keys configured, skipping")
            return {}

        # 尝试所有 key
        last_error = ""
        for idx, api_key in enumerate(keys):
            try:
                result = await self._call_moralis_api(
                    address=target_addr,
                    chain_id=chain_id,
                    api_key=api_key,
                )
                if result:
                    return result
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[MoralisProviderNode] key[{idx}] failed: {e}")
                continue

        # 所有 key 均失败
        if last_error:
            return {"_moralis_address_error": f"All keys exhausted. Last error: {last_error}"}
        return {"_moralis_address_error": "No data returned for this address"}

    def _extract_target_address(self, tx_context: TransactionContext) -> str:
        """提取要查询的目标地址（优先 exploiter_address）"""
        from_addr = tx_context.from_address or ""
        to_addr = tx_context.to_address or ""
        exploiter = tx_context.extra.get("exploiter_address", "") if tx_context.extra else ""

        if exploiter and isinstance(exploiter, str) and exploiter.startswith("0x"):
            return exploiter.lower()
        if from_addr and from_addr.startswith("0x"):
            return from_addr.lower()
        if to_addr and to_addr.startswith("0x"):
            return to_addr.lower()
        return ""

    def _get_api_keys(self) -> list[str]:
        """获取 API Key 列表（优先 apipool 池，再回退到 settings）"""
        # 1. 尝试 apipool 池
        try:
            from nodes.context.providers.moralis_key_pool import get_moralis_key_pool
            mgr = get_moralis_key_pool()
            if mgr is not None and mgr.is_ready:
                keys = mgr.all_keys
                if keys:
                    logger.info(f"[MoralisProviderNode] Loaded {len(keys)} keys from apipool pool")
                    return keys
        except Exception as e:
            logger.debug(f"[MoralisProviderNode] Apipool pool unavailable: {e}")

        # 2. 回退到 settings
        try:
            from config.model import settings
            raw = settings.moralis_api_key
            if not raw:
                return []
            if isinstance(raw, list):
                return [k for k in raw if k and isinstance(k, str) and k.strip()]
            if isinstance(raw, str):
                import json
                try:
                    parsed = json.loads(raw.strip())
                    if isinstance(parsed, list):
                        return [k for k in parsed if k and isinstance(k, str) and k.strip()]
                except json.JSONDecodeError:
                    pass
                return [raw.strip()] if raw.strip() else []
        except Exception as e:
            logger.warning(f"[MoralisProviderNode] Failed to load settings: {e}")

        return []

    async def _call_moralis_api(
        self,
        address: str,
        chain_id: int,
        api_key: str,
    ) -> dict[str, Any]:
        """调用 Moralis API"""
        import httpx

        chain_name = CHAIN_MAP.get(chain_id, "eth")
        url = f"https://deep-index.moralis.io/api/v2.2/wallets/{address}/chains"

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                url,
                headers={
                    "accept": "application/json",
                    "X-API-Key": api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        active_chains = data.get("active_chains") or []

        chain_info = None
        if isinstance(active_chains, dict):
            chain_info = active_chains.get(chain_name)
        elif isinstance(active_chains, list):
            for item in active_chains:
                if isinstance(item, dict) and item.get("chain") == chain_name:
                    chain_info = item
                    break

        if not chain_info:
            return {}

        # 提取 first_transaction
        ft = chain_info.get("first_transaction")
        if ft and isinstance(ft, dict):
            ts_str = ft.get("block_timestamp")
            bn_str = ft.get("block_number")
            bn = None
            if bn_str is not None:
                try:
                    bn = int(bn_str)
                except (ValueError, TypeError):
                    pass
            if ts_str:
                return self._build_result(str(ts_str), bn)

        return {}

    def _build_result(self, create_time_str: str, first_block_number: int | None = None) -> dict[str, Any]:
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
        }
        if first_block_number is not None:
            result["first_block_number"] = first_block_number
        return result


NodeRegistry.register(MoralisAddressProviderNode)
