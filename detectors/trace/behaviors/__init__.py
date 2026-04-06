"""
行为检测器模块
==============
所有行为检测器都继承自 detectors.trace.analyzer.TxTraceAnalyzer，
并重写 detect_behaviors() 方法添加特定检测逻辑。

可用检测器:
  - flash_loan:   闪电贷检测 (Aave/Balancer/UniswapV3)
  - arbitrage:    DEX 套利检测
  - token_flow:   Token 流转分析
"""

from detectors.trace.behaviors.base_behavior import BaseBehaviorDetector
from detectors.trace.behaviors.flash_loan import FlashLoanDetector
from detectors.trace.behaviors.token_flow import TokenFlowDetector

__all__ = [
    "BaseBehaviorDetector",
    "FlashLoanDetector",
    "TokenFlowDetector",
]
