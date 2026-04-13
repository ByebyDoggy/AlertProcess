"""
Moralis 地址信息 Provider

通过 Moralis API 获取地址创建时间等链上数据。
注入字段: address_create_time, address_age_days
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from nodes.context.provider import ContextProvider

logger = logging.getLogger(__name__)


class MoralisAddressProvider(ContextProvider):
    """
    Moralis 地址信息提供者。

    注入字段:
      - address_create_time: str — 地址创建时间 ISO8601 格式
      - address_age_days: int    — 地址创建距今天数

    API 调用:
      - Moralis `/{address}` 端点获取首次交易时间
    """

    name = "moralis_address"
    description = "通过 Moralis API 获取地址创建时间和年龄"
    provides = ["address_create_time", "address_age_days"]

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key

    @property
    def api_key(self) -> str | None:
        """延迟获取 API key（从全局配置）"""
        if self._api_key is None:
            try:
                from config.model import settings
                self._api_key = settings.moralis_api_key
            except Exception:
                pass
        return self._api_key

    async def fetch(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        获取地址创建时间信息。

        策略:
          1. 如果 context 中已有 address_create_time / address_age_days，跳过
          2. 从 context 提取地址列表
          3. 对每个地址调用 Moralis API
          4. 返回第一个有效结果
        """
        # 1. 检查已有数据
        if context.get("address_create_time") or context.get("address_age_days"):
            return {}

        # 2. 提取地址
        addresses = self.extract_addresses(context)
        if not addresses:
            return {}

        chain_id = self.extract_chain_id(context)

        # 3. 优先查询 exploiter_address（如果有的话）
        target_addr = (
            context.get("exploiter_address", "").lower()
            or addresses[0]
        )

        # 4. 尝试从 Moralis API 获取
        if not self.api_key:
            logger.debug("[MoralisAddress] No API key configured, skipping")
            return {}

        result = await self._fetch_from_moralis(target_addr, chain_id)
        return result

    async def _fetch_from_moralis(
        self, address: str, chain_id: int
    ) -> dict[str, Any]:
        """调用 Moralis API 获取地址首次交易时间"""
        import httpx

        # Moralis chain 标识映射
        chain_map = {
            1: "eth",
            56: "bsc",
            137: "polygon",
            42161: "arbitrum",
            10: "optimism",
            43114: "avalanche",
            250: "fantom",
        }
        chain = chain_map.get(chain_id, "eth")

        url = f"https://deep-index.moralis.io/api/v2/{address}?chain={chain}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    url,
                    headers={
                        "accept": "application/json",
                        "X-API-Key": self.api_key,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            # 解析创建时间
            first_tx = data.get("first_transaction_timestamp")
            if not first_tx:
                # 尝试从 holder 数据推断
                created_at = data.get("created_at")
                if created_at:
                    first_tx = created_at

            if first_tx:
                create_time_str = str(first_tx)
                # 解析 ISO 时间
                try:
                    if create_time_str.endswith("Z"):
                        create_time_str = create_time_str[:-1] + "+00:00"
                    ct = datetime.fromisoformat(create_time_str)
                    if ct.tzinfo is None:
                        ct = ct.replace(tzinfo=timezone.utc)
                    age_days = (datetime.now(timezone.utc) - ct).days

                    return {
                        "address_create_time": ct.isoformat(),
                        "address_age_days": age_days,
                        "address_queried": address,
                    }
                except (ValueError, TypeError) as e:
                    logger.warning(f"[MoralisAddress] Failed to parse timestamp: {e}")
                    return {}

            return {}

        except httpx.HTTPStatusError as e:
            logger.warning(
                f"[MoralisAddress] API error for {address}: "
                f"{e.response.status_code}"
            )
            return {"_moralis_address_error": f"HTTP {e.response.status_code}"}
        except Exception as e:
            logger.error(f"[MoralisAddress] Unexpected error: {e}", exc_info=True)
            return {"_moralis_address_error": str(e)}
