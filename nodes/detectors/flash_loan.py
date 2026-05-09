"""Legacy flash-loan detector compatibility wrapper."""

from __future__ import annotations

from nodes.detectors.protocol.flash_loan_trace import LegacyFlashLoanDetector as FlashLoanDetector

__all__ = ["FlashLoanDetector"]
