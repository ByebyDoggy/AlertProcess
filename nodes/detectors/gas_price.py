"""Gas 价格检测器 — 迁移到新节点架构"""

from __future__ import annotations

from typing import Any

from nodes.base import NodeRegistry, score_to_severity
from nodes.detectors.base import BaseDetector


class GasPriceDetector(BaseDetector):
    """
    Gas 价格检测器 — 检测异常高的 Gas 费用。

    评分规则:
    - gas_price_usd >= extreme_threshold → 95 分
    - gas_price_usd >= high_threshold    → 50-90 分（线性插值）
    - gas_price_usd < high_threshold     → 0-30 分（线性）
    """

    name: str = "gas_price_detector"
    label: str = "Gas 价格检测"
    description: str = "检测异常高的 Gas 费用"
    category_var: Any = None  # 使用基类的 category
    icon: str = "\u26fd"
    color: str = "#f59e0b"

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "threshold": {
                    "type": "number", "minimum": 0, "maximum": 100,
                    "default": 50, "description": "passed 阈值"
                },
                "high_gas_threshold_usd": {
                    "type": "number", "minimum": 0,
                    "default": 100.0, "description": "高 Gas 阈值（USD）"
                },
                "extreme_gas_threshold_usd": {
                    "type": "number", "minimum": 0,
                    "default": 500.0, "description": "极端 Gas 阈值（USD）"
                },
                "chain_id_to_native_token_price": {
                    "type": "object",
                    "description": "原生代币价格映射（chain_id -> USD）",
                    "default": {"1": 2000.0, "56": 700.0, "137": 1.0}
                },
            },
        }

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        return {
            "threshold": 50,
            "high_gas_threshold_usd": 100.0,
            "extreme_gas_threshold_usd": 500.0,
            "chain_id_to_native_token_price": {1: 2000.0, 56: 700.0, 137: 1.0},
        }

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = []
        high = config.get("high_gas_threshold_usd", 100.0)
        extreme = config.get("extreme_gas_threshold_usd", 500.0)
        if high <= 0:
            errors.append("high_gas_threshold_usd must be > 0")
        if extreme <= high:
            errors.append("extreme_gas_threshold_usd must be > high_gas_threshold_usd")
        threshold = config.get("threshold", 50)
        if not (0 <= threshold <= 100):
            errors.append("threshold must be between 0 and 100")
        return errors

    async def detect(self, context: dict[str, Any]) -> tuple[float, dict[str, Any]]:
        gas_price_wei = context.get("gas_price")
        gas_used = context.get("gas_used", 21000)

        # gas_price 和 gas_used 可能是字符串，转换为 int
        if isinstance(gas_price_wei, str):
            try:
                gas_price_wei = int(gas_price_wei)
            except (ValueError, TypeError):
                gas_price_wei = None
        if isinstance(gas_used, str):
            try:
                gas_used = int(gas_used)
            except (ValueError, TypeError):
                gas_used = 21000

        if gas_price_wei is None:
            # 尝试使用 gas_price_gwei
            gas_price_gwei = context.get("gas_price_gwei", 0)
            gas_price_wei = int(gas_price_gwei * 10**9)
            if gas_price_wei == 0:
                return 0.0, {"error": "gas_price not available in context"}

        chain_id = context.get("chain_id", 1)
        price_map = self.config.get("chain_id_to_native_token_price", {})
        native_price = price_map.get(str(chain_id), price_map.get(chain_id, 0))

        # 计算 total gas cost in USD
        total_gas_eth = (gas_price_wei * gas_used) / 10**18
        total_gas_usd = total_gas_eth * native_price

        # 也计算 per-gas-unit 的 USD
        gas_price_eth = gas_price_wei / 10**18
        gas_price_usd_per_unit = gas_price_eth * native_price

        high_t = self.config.get("high_gas_threshold_usd", 100.0)
        extreme_t = self.config.get("extreme_gas_threshold_usd", 500.0)

        if total_gas_usd >= extreme_t:
            score = 95.0
        elif total_gas_usd >= high_t:
            ratio = (total_gas_usd - high_t) / (extreme_t - high_t)
            score = 50.0 + ratio * 40.0
        else:
            ratio = total_gas_usd / high_t if high_t > 0 else 0
            score = ratio * 30.0

        score = max(0.0, min(100.0, score))
        labels = ["high_gas"] if score >= 50 else []

        details: dict[str, Any] = {
            "gas_price_wei": gas_price_wei,
            "gas_price_eth": gas_price_eth,
            "gas_price_usd": round(gas_price_usd_per_unit, 6),
            "gas_used": gas_used,
            "total_gas_eth": round(total_gas_eth, 8),
            "total_gas_usd": round(total_gas_usd, 4),
            "chain_id": chain_id,
            "native_token_price": native_price,
            "labels": labels,
        }
        return score, details


NodeRegistry.register(GasPriceDetector)
