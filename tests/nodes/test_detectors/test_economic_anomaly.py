"""tests/nodes/test_detectors/test_economic_anomaly.py — EconomicAnomalyDetector 新增特征测试

测试 USR 攻击驱动的三个新检测维度:
  - detect_zero_cost_token_gain: 零投入+无闪电贷+代币净收益
  - detect_mint_transfer_ratio: 铸造后转出比例
  - detect_proxy_mint_pattern: 代理铸造者模式
"""

import pytest

from nodes.detectors.economic_anomaly import (
    EconomicAnomalyDetector,
    detect_zero_cost_token_gain,
    detect_mint_transfer_ratio,
    detect_proxy_mint_pattern,
    TransferEvent,
    scan_logs,
    ERC20_TRANSFER_TOPIC,
    ZERO_ADDRESS,
)


# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------

ATTACKER = "0x04a288a7789dd6ade935361a4fb1ec5db513caed"
THECOUNTER = "0xa27a69ae180e202fde5d38189a3f24fe24e55861"
TREASURY = "0xacb7027f271b03b502d65feba617a0d817d62b8e"
USR_TOKEN = "0x66a1e37c9b0eaddca17d3662d6c05f4decf3e110"
USDC_TOKEN = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
NORMAL_USER = "0x1234567890abcdef1234567890abcdef12345678"


def _make_transfer(
    from_addr: str, to_addr: str, amount: int,
    token: str = USR_TOKEN, log_index: int = 0,
) -> TransferEvent:
    """构造 TransferEvent"""
    return TransferEvent(
        log_index=log_index,
        token_address=token.lower(),
        from_addr=from_addr.lower(),
        to_addr=to_addr.lower(),
        amount=amount,
        raw={},
    )


def _make_erc20_log(
    from_addr: str, to_addr: str, amount: int,
    contract: str = USR_TOKEN, log_index: int = 0,
) -> dict:
    """构造 ERC-20 Transfer 日志"""
    pad = lambda a: "0x" + a.lower().replace("0x", "").zfill(64)
    return {
        "address": contract,
        "topics": [ERC20_TRANSFER_TOPIC, pad(from_addr), pad(to_addr)],
        "data": hex(amount),
        "logIndex": log_index,
    }


# ---------------------------------------------------------------------------
# detect_zero_cost_token_gain 测试
# ---------------------------------------------------------------------------

class TestDetectZeroCostTokenGain:

    def test_zero_cost_with_large_gain(self):
        """USR攻击场景: tx.value=0, 无Swap, 攻击者获得大量代币"""
        transfers = [
            # 铸造 50M USR 到 TheCounter
            _make_transfer(ZERO_ADDRESS, THECOUNTER, 50_000_000 * 10**18, log_index=1),
            # TheCounter 转出 49.95M USR 给攻击者
            _make_transfer(THECOUNTER, ATTACKER, 49_950_000 * 10**18, log_index=2),
        ]
        # 简单的 mock token_price_cache
        class MockPriceCache:
            def get_price(self, chain_id, token):
                if token.lower() == USR_TOKEN.lower():
                    return 1.0  # USR ≈ $1
                return None
            def get(self, chain_id, token):
                class Meta:
                    decimals = 18
                return Meta()

        score, details = detect_zero_cost_token_gain(
            tx_value_wei=0,
            transfers=transfers,
            swaps=[],
            from_address=ATTACKER,
            token_price_cache=MockPriceCache(),
            chain_id=1,
            native_price=2000.0,
            min_gain_usd=10000.0,
        )
        assert details["detected"] is True
        assert score >= 30.0
        assert details["total_gain_usd"] > 10000.0

    def test_zero_cost_no_gain(self):
        """tx.value=0 但攻击者无代币净收益"""
        transfers = [
            _make_transfer(ATTACKER, NORMAL_USER, 1000 * 10**18, log_index=1),
        ]

        class MockPriceCache:
            def get_price(self, chain_id, token):
                return 1.0
            def get(self, chain_id, token):
                class Meta:
                    decimals = 18
                return Meta()

        score, details = detect_zero_cost_token_gain(
            tx_value_wei=0,
            transfers=transfers,
            swaps=[],
            from_address=ATTACKER,
            token_price_cache=MockPriceCache(),
            chain_id=1,
            native_price=2000.0,
        )
        # 攻击者净收益为负（只有转出，没有转入）
        assert details["detected"] is False

    def test_non_zero_cost_not_detected(self):
        """tx.value > 0 时不触发零投入检测"""
        transfers = [
            _make_transfer(ZERO_ADDRESS, THECOUNTER, 50_000_000 * 10**18, log_index=1),
            _make_transfer(THECOUNTER, ATTACKER, 49_950_000 * 10**18, log_index=2),
        ]

        class MockPriceCache:
            def get_price(self, chain_id, token):
                return 1.0
            def get(self, chain_id, token):
                class Meta:
                    decimals = 18
                return Meta()

        score, details = detect_zero_cost_token_gain(
            tx_value_wei=int(1.0 * 10**18),  # 1 ETH
            transfers=transfers,
            swaps=[],
            from_address=ATTACKER,
            token_price_cache=MockPriceCache(),
            chain_id=1,
            native_price=2000.0,
        )
        assert details.get("reason") == "not_zero_cost"

    def test_has_swap_not_detected(self):
        """有 Swap 事件时不触发零投入检测（可能有闪电贷）"""
        transfers = [
            _make_transfer(ZERO_ADDRESS, THECOUNTER, 50_000_000 * 10**18, log_index=1),
        ]
        from nodes.detectors.economic_anomaly import SwapEvent
        swaps = [SwapEvent(log_index=0, pool_address="0xpool", swap_type="uniswap_v2", raw={})]

        score, details = detect_zero_cost_token_gain(
            tx_value_wei=0,
            transfers=transfers,
            swaps=swaps,
            from_address=ATTACKER,
            token_price_cache=None,
            chain_id=1,
            native_price=2000.0,
        )
        assert details.get("reason") == "not_zero_cost"


# ---------------------------------------------------------------------------
# detect_mint_transfer_ratio 测试
# ---------------------------------------------------------------------------

class TestDetectMintTransferRatio:

    def test_high_ratio_mint_transfer(self):
        """USR攻击场景: 铸造 50M, 转出 49.95M (99.9%)"""
        transfers = [
            _make_transfer(ZERO_ADDRESS, THECOUNTER, 50_000_000, log_index=1),
            _make_transfer(THECOUNTER, ATTACKER, 49_950_000, log_index=2),
        ]
        score, details = detect_mint_transfer_ratio(transfers)
        assert score > 0
        assert len(details) >= 1
        assert details[0]["ratio"] >= 0.9

    def test_low_ratio_not_detected(self):
        """正常场景: 铸造后仅小额转出 (10%)"""
        transfers = [
            _make_transfer(ZERO_ADDRESS, THECOUNTER, 1_000_000, log_index=1),
            _make_transfer(THECOUNTER, NORMAL_USER, 100_000, log_index=2),
        ]
        score, details = detect_mint_transfer_ratio(transfers)
        # 转出比例 10%，低于 90% 阈值，不应检测到
        assert score == 0.0
        assert len(details) == 0

    def test_no_mint_no_detection(self):
        """无铸造事件时不检测"""
        transfers = [
            _make_transfer(ATTACKER, NORMAL_USER, 1000, log_index=1),
        ]
        score, details = detect_mint_transfer_ratio(transfers)
        assert score == 0.0

    def test_multiple_mints_multiple_transfers(self):
        """多笔铸造+转出"""
        transfers = [
            _make_transfer(ZERO_ADDRESS, THECOUNTER, 50_000_000, log_index=1),
            _make_transfer(THECOUNTER, ATTACKER, 49_950_000, log_index=2),
            _make_transfer(ZERO_ADDRESS, THECOUNTER, 30_000_000, log_index=3),
            _make_transfer(THECOUNTER, ATTACKER, 29_970_000, log_index=4),
        ]
        score, details = detect_mint_transfer_ratio(transfers)
        assert score > 0
        # 第二笔 mint(30M) 匹配到第一个 transfer(49.95M, index=2) 因为 log_index 不对
        # 所以可能只有1条高比例匹配，取决于匹配逻辑
        assert len(details) >= 1

    def test_transfer_before_mint_not_matched(self):
        """转出在铸造之前不应匹配"""
        transfers = [
            _make_transfer(THECOUNTER, ATTACKER, 49_950_000, log_index=1),
            _make_transfer(ZERO_ADDRESS, THECOUNTER, 50_000_000, log_index=2),
        ]
        score, details = detect_mint_transfer_ratio(transfers)
        # 转出在铸造之前，不应匹配
        assert len(details) == 0


# ---------------------------------------------------------------------------
# detect_proxy_mint_pattern 测试
# ---------------------------------------------------------------------------

class TestDetectProxyMintPattern:

    def test_proxy_mint_with_high_transfer(self):
        """USR攻击: TheCounter(代理)铸造USR后转给攻击者"""
        transfers = [
            _make_transfer(ZERO_ADDRESS, THECOUNTER, 50_000_000, log_index=1),
            _make_transfer(THECOUNTER, ATTACKER, 49_950_000, log_index=2),
        ]
        score, details = detect_proxy_mint_pattern(transfers)
        assert score > 0
        assert len(details) >= 1
        assert details[0]["proxy_minter"] == THECOUNTER.lower()
        assert details[0]["ratio"] >= 0.9

    def test_no_mint_no_proxy(self):
        """无铸造事件"""
        transfers = [
            _make_transfer(ATTACKER, NORMAL_USER, 1000, log_index=1),
        ]
        score, details = detect_proxy_mint_pattern(transfers)
        assert score == 0.0

    def test_mint_to_zero_addr_no_proxy(self):
        """铸造到零地址不是代理铸造"""
        transfers = [
            _make_transfer(NORMAL_USER, ZERO_ADDRESS, 1_000_000, log_index=1),
        ]
        score, details = detect_proxy_mint_pattern(transfers)
        assert score == 0.0

    def test_proxy_keeps_tokens(self):
        """代理铸造者保留大部分代币（低转出比例）"""
        transfers = [
            _make_transfer(ZERO_ADDRESS, THECOUNTER, 1_000_000, log_index=1),
            _make_transfer(THECOUNTER, ATTACKER, 50_000, log_index=2),  # 仅 5% 转出
        ]
        score, details = detect_proxy_mint_pattern(transfers)
        # 转出比例仅 5%，低于 90% 阈值
        assert score == 0.0

    def test_multiple_proxy_mints(self):
        """多笔代理铸造"""
        transfers = [
            _make_transfer(ZERO_ADDRESS, THECOUNTER, 50_000_000, log_index=1),
            _make_transfer(THECOUNTER, ATTACKER, 49_950_000, log_index=2),
            _make_transfer(ZERO_ADDRESS, THECOUNTER, 30_000_000, log_index=3),
            _make_transfer(THECOUNTER, ATTACKER, 29_970_000, log_index=4),
        ]
        score, details = detect_proxy_mint_pattern(transfers)
        assert score > 0


# ---------------------------------------------------------------------------
# scan_logs 集成测试
# ---------------------------------------------------------------------------

class TestScanLogsWithNewFeatures:

    def test_usr_attack_log_parsing(self):
        """模拟 USR 攻击的 logs 解析"""
        logs = [
            # USR.mint(from=0x0, to=TheCounter, amount=50M)
            _make_erc20_log(ZERO_ADDRESS, THECOUNTER, 50_000_000 * 10**18, USR_TOKEN, 1),
            # USR.transfer(from=TheCounter, to=Exploiter, amount=49.95M)
            _make_erc20_log(THECOUNTER, ATTACKER, 49_950_000 * 10**18, USR_TOKEN, 2),
            # USDC.transfer(from=TheCounter, to=Treasury, amount=100K)
            _make_erc20_log(THECOUNTER, TREASURY, 100_000 * 10**6, USDC_TOKEN, 3),
        ]
        transfers, swaps = scan_logs(logs)
        assert len(transfers) == 3
        assert len(swaps) == 0

        # 验证铸造事件
        mints = [t for t in transfers if t.is_mint]
        assert len(mints) == 1
        assert mints[0].to_addr == THECOUNTER.lower()

        # 验证铸造后转出
        mtt_score, mtt_details = detect_mint_transfer_ratio(transfers)
        assert mtt_score > 0
        assert len(mtt_details) >= 1

        # 验证代理铸造者模式
        pm_score, pm_details = detect_proxy_mint_pattern(transfers)
        assert pm_score > 0


# ---------------------------------------------------------------------------
# 阴性测试
# ---------------------------------------------------------------------------

class TestNegativeCases:

    def test_normal_transfer_no_detection(self):
        """正常转账不应触发任何新特征"""
        transfers = [
            _make_transfer(ATTACKER, NORMAL_USER, 1000, log_index=1),
            _make_transfer(NORMAL_USER, ATTACKER, 500, log_index=2),
        ]

        # 铸造后转出比例
        mtr_score, _ = detect_mint_transfer_ratio(transfers)
        assert mtr_score == 0.0

        # 代理铸造者模式
        pm_score, _ = detect_proxy_mint_pattern(transfers)
        assert pm_score == 0.0

    def test_normal_mint_with_small_transfer(self):
        """正常铸造+小额转出不应触发高比例检测"""
        transfers = [
            _make_transfer(ZERO_ADDRESS, THECOUNTER, 1_000_000, log_index=1),
            _make_transfer(THECOUNTER, NORMAL_USER, 100_000, log_index=2),  # 10% 转出
        ]

        # 转出比例仅 10%，不应触发
        mtr_score, _ = detect_mint_transfer_ratio(transfers)
        assert mtr_score == 0.0

        # 代理铸造者模式也要求 >90% 转出
        pm_score, _ = detect_proxy_mint_pattern(transfers)
        assert pm_score == 0.0

    def test_empty_transfers(self):
        """空 transfers 不应崩溃"""
        mtr_score, _ = detect_mint_transfer_ratio([])
        assert mtr_score == 0.0

        pm_score, _ = detect_proxy_mint_pattern([])
        assert pm_score == 0.0

        zctg_score, _ = detect_zero_cost_token_gain(
            tx_value_wei=0, transfers=[], swaps=[],
            from_address=ATTACKER, token_price_cache=None,
            chain_id=1, native_price=2000.0,
        )
        assert zctg_score == 0.0


# ---------------------------------------------------------------------------
# 边界测试
# ---------------------------------------------------------------------------

class TestBoundaryConditions:

    def test_exactly_90_percent_ratio(self):
        """恰好 90% 转出比例的边界"""
        transfers = [
            _make_transfer(ZERO_ADDRESS, THECOUNTER, 1_000_000, log_index=1),
            _make_transfer(THECOUNTER, ATTACKER, 900_000, log_index=2),
        ]
        mtr_score, details = detect_mint_transfer_ratio(transfers)
        assert mtr_score > 0
        assert details[0]["ratio"] == 0.9

    def test_just_below_90_percent_ratio(self):
        """略低于 90% 转出比例"""
        transfers = [
            _make_transfer(ZERO_ADDRESS, THECOUNTER, 1_000_000, log_index=1),
            _make_transfer(THECOUNTER, ATTACKER, 899_999, log_index=2),
        ]
        mtr_score, details = detect_mint_transfer_ratio(transfers)
        # 899999/1000000 = 0.899999 < 0.9, 不应触发
        assert mtr_score == 0.0

    def test_zero_amount_mint(self):
        """铸造金额为0"""
        transfers = [
            _make_transfer(ZERO_ADDRESS, THECOUNTER, 0, log_index=1),
            _make_transfer(THECOUNTER, ATTACKER, 0, log_index=2),
        ]
        # amount=0 不会触发高比例（除零保护）
        mtr_score, _ = detect_mint_transfer_ratio(transfers)
        assert mtr_score == 0.0

    def test_gain_just_below_threshold(self):
        """零投入净收益刚好低于阈值"""
        transfers = [
            _make_transfer(THECOUNTER, ATTACKER, 9_000 * 10**18, log_index=1),
        ]

        class MockPriceCache:
            def get_price(self, chain_id, token):
                return 1.0
            def get(self, chain_id, token):
                class Meta:
                    decimals = 18
                return Meta()

        score, details = detect_zero_cost_token_gain(
            tx_value_wei=0,
            transfers=transfers,
            swaps=[],
            from_address=ATTACKER,
            token_price_cache=MockPriceCache(),
            chain_id=1,
            native_price=2000.0,
            min_gain_usd=10000.0,  # 阈值 $10K
        )
        # $9K < $10K 阈值
        assert details["detected"] is False
