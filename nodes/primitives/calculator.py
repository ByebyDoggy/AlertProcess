"""
计算器原语

提供可复用的计算功能，如 ROI 计算、价格影响计算等。
"""

from typing import Dict
from nodes.primitives.log_parser import TransferEvent


class ROICalculator:
    """ROI 计算器"""

    def __init__(self, token_prices: Dict[str, float]):
        """
        Args:
            token_prices: 代币价格字典 {token_address: price_usd}
        """
        self.token_prices = token_prices

    def calculate(
        self,
        transfers: list[TransferEvent],
        tx_value: int,
        attacker_address: str,
    ) -> float:
        """
        计算攻击者的 ROI

        Args:
            transfers: Transfer 事件列表
            tx_value: 交易 value（ETH，单位 wei）
            attacker_address: 攻击者地址

        Returns:
            ROI 百分比（如 150.5 表示 150.5%）
        """
        inflow_usd = 0.0
        outflow_usd = 0.0

        attacker_lower = attacker_address.lower()

        for transfer in transfers:
            # 获取代币价格
            price = self.token_prices.get(transfer.token_address.lower(), 0)
            if price == 0:
                continue

            # 计算美元价值（假设 18 位小数）
            amount_usd = (transfer.amount * price) / 1e18

            # 判断是流入还是流出
            if transfer.to_address.lower() == attacker_lower:
                inflow_usd += amount_usd
            elif transfer.from_address.lower() == attacker_lower:
                outflow_usd += amount_usd

        # 加上 ETH 成本
        eth_price = self.token_prices.get("ETH", 0)
        if eth_price > 0 and tx_value > 0:
            outflow_usd += (tx_value * eth_price) / 1e18

        # 计算 ROI
        if outflow_usd == 0:
            return 0.0

        roi = ((inflow_usd - outflow_usd) / outflow_usd) * 100
        return roi


class PriceImpactCalculator:
    """价格影响计算器"""

    @staticmethod
    def calculate(
        amount_in: int,
        amount_out: int,
        reserve_in: int,
        reserve_out: int,
    ) -> float:
        """
        计算 Swap 的价格影响

        使用恒定乘积公式：x * y = k
        价格影响 = (实际价格 - 理论价格) / 理论价格 * 100

        Args:
            amount_in: 输入代币数量
            amount_out: 输出代币数量
            reserve_in: 输入代币储备量
            reserve_out: 输出代币储备量

        Returns:
            价格影响百分比（如 5.2 表示 5.2%）
        """
        if reserve_in == 0 or reserve_out == 0 or amount_in == 0:
            return 0.0

        # 理论价格（无滑点）
        theoretical_price = reserve_out / reserve_in

        # 实际价格
        actual_price = amount_out / amount_in

        # 价格影响
        price_impact = abs((actual_price - theoretical_price) / theoretical_price) * 100

        return price_impact

    @staticmethod
    def calculate_slippage(
        expected_amount_out: int,
        actual_amount_out: int,
    ) -> float:
        """
        计算滑点

        Args:
            expected_amount_out: 预期输出数量
            actual_amount_out: 实际输出数量

        Returns:
            滑点百分比（如 2.5 表示 2.5%）
        """
        if expected_amount_out == 0:
            return 0.0

        slippage = abs((expected_amount_out - actual_amount_out) / expected_amount_out) * 100
        return slippage
