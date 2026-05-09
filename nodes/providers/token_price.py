"""
TokenPriceProvider 节点

从交易日志中提取代币地址，批量查询价格，并注入到 context 中。
"""

from __future__ import annotations

from typing import Any

from nodes.base import NodeRegistry
from nodes.providers.base import BaseContextProviderNode
from nodes.models import TransactionContext
from detectors.trace.token_price_cache import get_token_price_cache


@NodeRegistry.register
class TokenPriceProviderNode(BaseContextProviderNode):
    """
    代币价格提供者节点

    功能：
    1. 从交易日志中提取所有涉及的代币地址
    2. 批量查询价格（使用 TokenPriceCache）
    3. 将价格数据注入到 context.extra

    提供的数据：
    - token_prices: dict[address, float] - 代币地址到价格的映射
    """

    name = "token_price_provider"
    label = "代币价格查询"
    description = "从交易日志中提取代币地址并批量查询价格"
    icon = "💰"
    color = "#FFC107"

    provides = ["token_prices"]

    async def fetch(self, tx_context: TransactionContext) -> dict[str, Any]:
        """
        从交易日志中提取代币地址并查询价格

        Returns:
            包含 token_prices 的字典
        """
        # 从日志中提取所有代币地址
        token_addresses = self._extract_token_addresses(tx_context)

        # 获取 TokenPriceCache 实例
        price_cache = get_token_price_cache()

        # 批量查询价格
        metadata = await price_cache.batch_fetch(
            chain_id=tx_context.chain_id,
            addresses=list(token_addresses),
            include_native=True,
        )

        # 构建价格映射
        token_prices = {}
        for addr, meta in metadata.items():
            if meta.price_usd is not None:
                token_prices[addr.lower()] = meta.price_usd

        return {
            "token_prices": token_prices,
        }

    def _extract_token_addresses(self, tx_context: TransactionContext) -> set[str]:
        """
        从交易日志中提取所有代币地址

        提取策略：
        1. Transfer 事件：log.address 是代币地址
        2. Swap 事件：log.address 是 DEX 地址（不是代币）
        3. Approval 事件：log.address 是代币地址

        Returns:
            代币地址集合（小写）
        """
        addresses = set()

        # Transfer 事件签名
        TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        # Approval 事件签名
        APPROVAL_TOPIC = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"

        for log in tx_context.logs:
            if not log.get("topics"):
                continue

            topic0 = log["topics"][0]
            if isinstance(topic0, str):
                topic0 = topic0.lower()

            # Transfer 或 Approval 事件，log.address 是代币地址
            if topic0 in (TRANSFER_TOPIC.lower(), APPROVAL_TOPIC.lower()):
                addr = log.get("address", "").lower()
                if addr:
                    addresses.add(addr)

        return addresses
