"""Gas 价格检测器 — 迁移到新节点架构"""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from nodes.base import NodeRegistry, score_to_severity
from nodes.detectors.base import BaseDetector, DetectorConfigMixin, DetectorOutputMixin
from nodes.models import TransactionContext


class GasPriceOutput(DetectorOutputMixin):
    """Gas 价格检测器输出"""
    pass


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
    description: str = "[数据需求: 仅交易基础字段] 检测交易 Gas 费用是否异常高（如抢 Front-run 或攻击行为）。根据 gas_price × gas_used 计算 USD 成本，支持多链原生代币价格映射，极端 Gas 给 95 分"
    category_var: Any = None  # 使用基类的 category
    icon: str = "\u26fd"
    color: str = "#f59e0b"

    # ── Pydantic 配置模型 (继承 DetectorConfigMixin，包含共享的 threshold) ──
    class ConfigModel(DetectorConfigMixin):
        high_gas_threshold_usd: float = Field(default=100.0, ge=0, description="高 Gas 阈值（USD）")
        extreme_gas_threshold_usd: float = Field(default=500.0, ge=0, description="极端 Gas 阈值（USD）")

        @model_validator(mode='after')
        def _check_thresholds(self):
            if self.extreme_gas_threshold_usd <= self.high_gas_threshold_usd:
                raise ValueError(
                    "extreme_gas_threshold_usd must be > high_gas_threshold_usd"
                )
            return self

    # ── Pydantic 输出模型 ──
    OutputModel: type = GasPriceOutput

    async def process(self, input: DetectorInputMixin) -> GasPriceOutput:
        gas_price_wei = input.gas_price
        gas_used = input.gas_used or 21000

        if not gas_price_wei:
            # 尝试使用 extra 中的 gas_price_gwei
            gas_price_gwei = input.get_extra("gas_price_gwei", 0)
            gas_price_wei = int(gas_price_gwei * 10**9)
            if gas_price_wei == 0:
                return GasPriceOutput(
                    score=0.0, passed=True, severity="UNKNOWN", labels=[],
                    detection={"error": "gas_price not available in context"},
                    logs=["gas_price 为 0，跳过检测"],
                )

        chain_id = input.chain_id or 1

        # 优先使用 TokenPriceProvider 提供的原生代币价格
        token_prices = self.get_token_prices(input)
        native_price = token_prices.get("", 0.0)  # 空字符串 key 表示原生代币

        # 如果 Provider 没有提供原生代币价格，回退到 token_price_instance
        if native_price == 0.0:
            native_price = self.token_price_instance.get_price(chain_id, "") or 0.0

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
        threshold = self.config.get("threshold", 50.0)
        from nodes.base import score_to_severity

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
        return GasPriceOutput(
            score=score, passed=score >= threshold, severity=score_to_severity(score),
            labels=labels, detection=details,
        )


NodeRegistry.register(GasPriceDetector)
