"""
协议地址标签库
==============
通过 to 地址匹配已知的 DeFi 协议名称。

数据来源:
  - 手动维护的已知合约地址 (高置信度)
  - 可扩展: 从 DefiLlama / Etherscan labels API 同步

参考文档: docs/dev-plan-trace-analysis.md §3.5 (隐含在 analyzer 中)
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ================================================================
# 已知协议地址标签
# ================================================================

# 以太坊 Mainnet
_PROTOCOLS_ETH: dict[str, dict] = {
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": {
        "name": "Uniswap V2 Router 02",
        "category": "DEX",
    },
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": {
        "name": "Uniswap V3 SwapRouter 02",
        "category": "DEX",
    },
    "0xe592427a0aece92de3edee1f18e0157c05861564": {
        "name": "Uniswap V3 SwapRouter 01",
        "category": "DEX",
    },
    "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad": {
        "name": "Uniswap Universal Router",
        "category": "DEX",
    },
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": {
        "name": "WETH9",
        "category": "Token",
    },
    "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2": {
        "name": "Aave V3 Pool",
        "category": "Lending",
    },
    "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9": {
        "name": "Aave V3 Pool (old)",
        "category": "Lending",
    },
    "0x5c2ed810328349100a66b82b0192e35303d9479a": {
        "name": "1inch V5 AggregationRouter",
        "category": "DEX Aggregator",
    },
    "0xba12222222228d8ba445958a75a0704d566bf2c8": {
        "name": "Balancer Vault V2",
        "category": "DEX",
    },
    "0x99a58482bd75cbab83b27ec03ca68ff489b5788f": {
        "name": "Curve 1Pool",
        "category": "DEX",
    },
}

# BSC (BNB Smart Chain)
_PROTOCOLS_BSC: dict[str, dict] = {
    "0x10ed43c718714eb63d5aa57b78b54704e256024e": {
        "name": "PancakeSwap V2 Router",
        "category": "DEX",
    },
    "0x13f4ea83d0bd40e75c8222255bc855a974568dd4": {
        "name": "PancakeSwap WBNB",
        "category": "Token",
    },
    "0x55d398326f99059ff775485246999027b3197955": {
        "name": "USDT",
        "category": "Token",
    },
    "0x2170ed0880ac9a755fd29b2688956bd959f933f8": {
        "name": "WETH",
        "category": "Token",
    },
    "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c": {
        "name": "WBNB",
        "category": "Token",
    },
    "0xe14fb593ee2f0b2f2f3b519b27a05bf0e66ea3e0": {
        "name": "PancakeSwap MasterChef",
        "category": "Yield",
    },
    "0x0ed7e52944161450477ee417decd3a859b14fd0": {
        "name": "PancakeSwap MiniChefV2",
        "category": "Yield",
    },
    "0x1b81d678ffb9c0263b24a97847620c99d213eb14": {
        "name": "PancakeSwap Smart Router",
        "category": "DEX",
    },
    "0x111111125421ca6dc452d289314280a0f8842a65": {
        "name": "1inch SwapRouter",
        "category": "DEX Aggregator",
    },
    "0x1111111254eeb25477b68fb85ed929f73a960582": {
        "name": "1inch SwapRouter v5",
        "category": "DEX Aggregator",
    },
    "0x05ff2b0db69458a0750badebc4f9e13add608c7f": {
        "name": "PancakeSwap Smart Router V3",
        "category": "DEX",
    },
}

# Token 符号映射 (跨链通用)
_TOKEN_SYMBOLS: dict[str, dict] = {
    # ETH
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": {"symbol": "WETH", "decimals": 18},
    # BSC
    "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c": {"symbol": "WBNB", "decimals": 18},
    "0x55d398326f99059ff775485246999027b3197955": {"symbol": "USDT", "decimals": 18},
    "0x2170ed0880ac9a755fd29b2688956bd959f933f8": {"symbol": "WETH", "decimals": 18},
    "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": {"symbol": "USDC", "decimals": 18},
    "0xe9e7cea3dedca5984780bafc599bd69add087d56": {"symbol": "BUSD", "decimals": 18},
}

# 按 chain_id 分组的注册表
_CHAIN_REGISTRIES: dict[int, dict[str, dict]] = {
    1: _PROTOCOLS_ETH,
    56: _PROTOCOLS_BSC,
}


class ProtocolRegistry:
    """
    协议地址标签注册表

    用法:
        reg = ProtocolRegistry()
        info = reg.match("0x7a250d5630b4cf539739df2c5dacb4c659f2488d", chain_id=1)
        # → {"name": "Uniswap V2 Router 02", "category": "DEX"}
        symbol = reg.get_token_symbol("0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c")
        # → "WBNB"
    """

    def __init__(self, custom_json_path: str | Path | None = None):
        """
        Args:
            custom_json_path: 可选的自定义协议注册表 JSON 文件路径
                              (用于扩展默认注册表)
        """
        self._custom: dict[str, dict] = {}
        if custom_json_path:
            p = Path(custom_json_path)
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    self._custom = json.load(f)
                logger.info(
                    f"[ProtocolRegistry] Loaded {len(self._custom)} custom entries from {p}"
                )

    def match(self, address: str, chain_id: int = 1) -> Optional[dict]:
        """
        通过 to 地址匹配协议信息

        Args:
            address: 合约地址 (大小写不敏感)
            chain_id: 链 ID

        Returns:
            {"name": ..., "category": ...} 或 None
        """
        addr = address.lower().strip()
        if not addr or len(addr) < 40:
            return None

        # 先查自定义注册表
        if addr in self._custom:
            return self._custom[addr]

        # 再查链级注册表
        chain_reg = _CHAIN_REGISTRIES.get(chain_id, {})
        return chain_reg.get(addr)

    def get_label(self, address: str, chain_id: int = 1) -> Optional[str]:
        """仅返回协议名称标签"""
        info = self.match(address, chain_id)
        return info["name"] if info else None

    def get_token_symbol(self, address: str) -> Optional[str]:
        """获取已知 token 的符号"""
        addr = address.lower().strip()
        tok = _TOKEN_SYMBOLS.get(addr)
        return tok["symbol"] if tok else None

    def get_token_decimals(self, address: str) -> int:
        """获取已知 token 的精度"""
        addr = address.lower().strip()
        tok = _TOKEN_SYMBOLS.get(addr)
        return tok["decimals"] if tok else 18

    def all_protocols_for_chain(self, chain_id: int) -> list[dict]:
        """返回某条链上所有已知协议 (供前端展示)"""
        chain_reg = _CHAIN_REGISTRIES.get(chain_id, {})
        results = []
        for addr, info in chain_reg.items():
            results.append({
                "address": addr,
                "name": info["name"],
                "category": info["category"],
            })
        return sorted(results, key=lambda x: x["name"])

    def supported_chains(self) -> list[int]:
        """返回有注册表数据的链 ID 列表"""
        return list(_CHAIN_REGISTRIES.keys())
