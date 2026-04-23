"""检测器节点模块"""
from nodes.detectors.base import BaseDetector
from nodes.detectors.gas_price import GasPriceDetector
from nodes.detectors.address_type import AddressTypeDetector
from nodes.detectors.flash_loan import FlashLoanDetector
from nodes.detectors.token_approval import TokenApprovalDetector
from nodes.detectors.token_anomaly import TokenAnomalyDetector
from nodes.detectors.address_graph import AddressGraphDetector
from nodes.detectors.address_age import AddressAgeDetector
from nodes.detectors.arkm_label import ARKMLabelDetector
from nodes.detectors.fund_drain import FundDrainDetector

__all__ = [
    "BaseDetector",
    "GasPriceDetector",
    "AddressTypeDetector",
    "FlashLoanDetector",
    "TokenApprovalDetector",
    "TokenAnomalyDetector",
    "AddressGraphDetector",
    "AddressAgeDetector",
    "ARKMLabelDetector",
    "FundDrainDetector",
]
