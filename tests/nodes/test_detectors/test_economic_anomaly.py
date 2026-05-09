"""tests/nodes/test_detectors/test_economic_anomaly.py — EconomicAnomalyDetector 新增特征测试

测试 USR 攻击驱动的三个新检测维度:
  - detect_zero_cost_token_gain: 零投入+无闪电贷+代币净收益
  - detect_mint_transfer_ratio: 铸造后转出比例
  - detect_proxy_mint_pattern: 代理铸造者模式

测试 Cyrus Finance 攻击驱动的检测:
  - detect_swap_reverse_pattern: 同池双向交换（价格操纵信号）
"""

import pytest

from nodes.detectors.economic_anomaly import (
    EconomicAnomalyDetector,
    detect_zero_cost_token_gain,
    detect_mint_transfer_ratio,
    detect_proxy_mint_pattern,
    detect_zero_cost_proxy_pattern,
    detect_zero_cost_high_ratio_mint,
    detect_low_cost_high_roi_mint_loop,
    detect_swap_reverse_pattern,
    TransferEvent,
    SwapEvent,
    scan_logs,
    ERC20_TRANSFER_TOPIC,
    UNISWAP_V2_SWAP_TOPIC,
    UNISWAP_V3_SWAP_TOPIC,
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
# Swap 日志构造辅助函数
# ---------------------------------------------------------------------------


POOL_ADDR = "0x9f599f3d64a9d99ea21e68127bb6ce99f893da61"


def _make_v3_swap_log(
    amount0: int, amount1: int,
    sender: str = ATTACKER,
    recipient: str = ATTACKER,
    pool: str = POOL_ADDR,
    log_index: int = 0,
    sqrt_price_x96: int = 0,
) -> dict:
    """构造 Uniswap V3 Swap 日志。
    amount0/amount1 使用补码表示有符号 int256。
    """
    pad = lambda a: "0x" + a.lower().replace("0x", "").zfill(64)
    # 将有符号整数编码为 uint256 补码
    def to_int256(val: int) -> str:
        if val < 0:
            val = val + 2**256
        return hex(val)

    liquidity = 0
    tick = 0
    data = (to_int256(amount0)[2:].zfill(64) +
            to_int256(amount1)[2:].zfill(64) +
            hex(sqrt_price_x96)[2:].zfill(64) +
            hex(liquidity)[2:].zfill(64) +
            hex(tick)[2:].zfill(12))
    return {
        "address": pool,
        "topics": [UNISWAP_V3_SWAP_TOPIC, pad(sender), pad(recipient)],
        "data": "0x" + data,
        "logIndex": log_index,
    }


def _make_v2_swap_log(
    amount0_in: int, amount1_in: int,
    amount0_out: int, amount1_out: int,
    sender: str = ATTACKER,
    recipient: str = ATTACKER,
    pool: str = POOL_ADDR,
    log_index: int = 0,
) -> dict:
    """构造 Uniswap V2 Swap 日志"""
    pad = lambda a: "0x" + a.lower().replace("0x", "").zfill(64)
    data = (hex(amount0_in)[2:].zfill(64) +
            hex(amount1_in)[2:].zfill(64) +
            hex(amount0_out)[2:].zfill(64) +
            hex(amount1_out)[2:].zfill(64))
    return {
        "address": pool,
        "topics": [UNISWAP_V2_SWAP_TOPIC, pad(sender), pad(recipient)],
        "data": "0x" + data,
        "logIndex": log_index,
    }


# ---------------------------------------------------------------------------
# detect_swap_reverse_pattern 测试
# ---------------------------------------------------------------------------

class TestDetectSwapReversePattern:

    def test_v3_same_pool_reverse_swap(self):
        """V3 同一池双向交换: A→B then B→A"""
        swaps = [
            SwapEvent(log_index=10, pool_address=POOL_ADDR, swap_type="uniswap_v3",
                      raw={}, amount0=1000, amount1=-500),   # token0出, token1入
            SwapEvent(log_index=11, pool_address=POOL_ADDR, swap_type="uniswap_v3",
                      raw={}, amount0=-800, amount1=400),    # token0入, token1出（反向, 紧邻）
        ]
        score, patterns = detect_swap_reverse_pattern(swaps)
        assert score > 0
        assert len(patterns) == 1
        assert patterns[0]["pool"] == POOL_ADDR
        assert patterns[0]["has_gap_operations"] is False  # 紧邻无 gap

    def test_v3_same_direction_no_detection(self):
        """V3 同一池同向交换不应检测"""
        swaps = [
            SwapEvent(log_index=10, pool_address=POOL_ADDR, swap_type="uniswap_v3",
                      raw={}, amount0=1000, amount1=-500),
            SwapEvent(log_index=20, pool_address=POOL_ADDR, swap_type="uniswap_v3",
                      raw={}, amount0=500, amount1=-250),  # 同方向
        ]
        score, patterns = detect_swap_reverse_pattern(swaps)
        assert score == 0.0
        assert len(patterns) == 0

    def test_v3_reverse_with_gap_and_large_amount(self):
        """Cyrus 攻击模式: 双向 Swap 中间有其他操作"""
        swaps = [
            SwapEvent(log_index=10, pool_address=POOL_ADDR, swap_type="uniswap_v3",
                      raw={}, amount0=1_798 * 10**18, amount1=-1_212_462 * 10**6),  # 1,798 ETH → USDT
            SwapEvent(log_index=30, pool_address=POOL_ADDR, swap_type="uniswap_v3",
                      raw={}, amount0=-537 * 10**18, amount1=760_000 * 10**6),      # USDT → ETH (反向)
        ]
        score, patterns = detect_swap_reverse_pattern(swaps)
        assert score > 0
        assert len(patterns) == 1
        assert patterns[0]["gap_between"] == 19  # 30 - 10 - 1
        assert patterns[0]["has_gap_operations"] is True  # 中间有其他操作
        assert patterns[0]["forward_abs"] >= 1_798 * 10**18  # 大额

    def test_v2_reverse_swap(self):
        """V2 同一池双向交换"""
        swaps = [
            SwapEvent(log_index=10, pool_address=POOL_ADDR, swap_type="uniswap_v2",
                      raw={}, amount0=500, amount1=-1000),   # token0出500, token1入1000
            SwapEvent(log_index=20, pool_address=POOL_ADDR, swap_type="uniswap_v2",
                      raw={}, amount0=-400, amount1=800),    # 反向: token0入400, token1出800
        ]
        score, patterns = detect_swap_reverse_pattern(swaps)
        assert score > 0
        assert len(patterns) == 1

    def test_diff_pool_no_detection(self):
        """不同池之间的 Swap 不应检测（不同token对）"""
        swaps = [
            SwapEvent(log_index=10, pool_address="0xpool1", swap_type="uniswap_v3",
                      raw={}, amount0=1000, amount1=-500),
            SwapEvent(log_index=20, pool_address="0xpool2", swap_type="uniswap_v3",
                      raw={}, amount0=-800, amount1=400),
        ]
        score, patterns = detect_swap_reverse_pattern(swaps)
        assert score == 0.0

    def test_single_swap_no_detection(self):
        """单笔 Swap 不应触发"""
        swaps = [
            SwapEvent(log_index=10, pool_address=POOL_ADDR, swap_type="uniswap_v3",
                      raw={}, amount0=1000, amount1=-500),
        ]
        score, patterns = detect_swap_reverse_pattern(swaps)
        assert score == 0.0

    def test_empty_swaps_no_detection(self):
        """空列表不应触发"""
        score, patterns = detect_swap_reverse_pattern([])
        assert score == 0.0

    def test_scan_logs_v3_reverse_pattern(self):
        """通过 scan_logs 解析 V3 Swap 后进行反向检测"""
        # 模拟 Cyrus 攻击的两个 V3 Swap
        logs = [
            _make_v3_swap_log(
                amount0=1_798 * 10**18, amount1=-1_212_462 * 10**6,
                log_index=10,
            ),
            _make_v3_swap_log(
                amount0=-537 * 10**18, amount1=760_000 * 10**6,
                log_index=30,
            ),
        ]
        transfers, swaps = scan_logs(logs)
        assert len(swaps) == 2
        assert swaps[0].amount0 > 0
        assert swaps[0].amount1 < 0
        assert swaps[1].amount0 < 0
        assert swaps[1].amount1 > 0

        score, patterns = detect_swap_reverse_pattern(swaps)
        assert score > 0
        assert len(patterns) == 1

    def test_scan_logs_v2_reverse_pattern(self):
        """通过 scan_logs 解析 V2 Swap 后进行反向检测"""
        logs = [
            _make_v2_swap_log(
                amount0_in=0, amount1_in=1000, amount0_out=500, amount1_out=0,
                log_index=10,
            ),
            _make_v2_swap_log(
                amount0_in=400, amount1_in=0, amount0_out=0, amount1_out=800,
                log_index=20,
            ),
        ]
        transfers, swaps = scan_logs(logs)
        assert len(swaps) == 2
        assert swaps[0].amount0 > 0  # 500 out
        assert swaps[1].amount0 < 0  # 400 in

        score, patterns = detect_swap_reverse_pattern(swaps)
        assert score > 0
        assert len(patterns) == 1


class TestP1EconomicAnomalyCorrelations:

    def _mock_price_cache(self):
        class MockPriceCache:
            def get_price(self, chain_id, token):
                token = token.lower()
                if token == "":
                    return 2000.0
                if token == USR_TOKEN.lower():
                    return 1.0
                if token == USDC_TOKEN.lower():
                    return 1.0
                return None

            def get(self, chain_id, token):
                class Meta:
                    decimals = 18 if token.lower() == USR_TOKEN.lower() else 6
                return Meta()

        return MockPriceCache()

    def test_zero_cost_proxy_pattern_detected(self):
        zero_cost_details = {
            "detected": True,
            "gains": [{"token": USR_TOKEN.lower(), "gain_usd": 49_950_000.0}],
        }
        proxy_patterns = [{
            "token": USR_TOKEN.lower(),
            "proxy_minter": THECOUNTER.lower(),
            "final_receivers": [{"to": ATTACKER.lower(), "amount": 49_950_000}],
            "ratio": 0.999,
        }]
        score, details = detect_zero_cost_proxy_pattern(zero_cost_details, proxy_patterns)
        assert score > 0
        assert len(details) == 1
        assert details[0]["proxy_minter"] == THECOUNTER.lower()

    def test_zero_cost_high_ratio_mint_detected(self):
        zero_cost_details = {
            "detected": True,
            "gains": [{"token": USR_TOKEN.lower(), "gain_usd": 49_950_000.0}],
        }
        mint_patterns = [{
            "token": USR_TOKEN.lower(),
            "mint_to": THECOUNTER.lower(),
            "transfer_to": ATTACKER.lower(),
            "ratio": 0.999,
        }]
        score, details = detect_zero_cost_high_ratio_mint(zero_cost_details, mint_patterns)
        assert score > 0
        assert len(details) == 1
        assert details[0]["transfer_to"] == ATTACKER.lower()

    def test_low_cost_high_roi_mint_loop_detected(self):
        roi_details = {"roi": 120.0}
        mint_patterns = [{"token": USR_TOKEN.lower(), "ratio": 0.999}]
        proxy_patterns = [{"token": USR_TOKEN.lower(), "proxy_minter": THECOUNTER.lower()}]
        score, details = detect_low_cost_high_roi_mint_loop(roi_details, mint_patterns, proxy_patterns)
        assert score > 0
        assert details["detected"] is True
        assert details["proxy_mint_count"] == 1

    @pytest.mark.asyncio
    async def test_detector_outputs_p1_mint_loop_signals(self):
        logs = [
            _make_erc20_log(ZERO_ADDRESS, THECOUNTER, 50_000_000 * 10**18, USR_TOKEN, 1),
            _make_erc20_log(THECOUNTER, ATTACKER, 49_950_000 * 10**18, USR_TOKEN, 2),
            _make_erc20_log(THECOUNTER, TREASURY, 100_000 * 10**6, USDC_TOKEN, 3),
            _make_erc20_log(TREASURY, ATTACKER, 200_000 * 10**6, USDC_TOKEN, 4),
        ]
        det = EconomicAnomalyDetector(node_id="e1")
        det._token_price_cache = self._mock_price_cache()
        from nodes.detectors.base import DetectorInputMixin
        tx = DetectorInputMixin(
            from_address=ATTACKER,
            to_address=THECOUNTER,
            chain_id=1,
            value=0,
            logs=logs,
        )

        output = await det.process(tx)

        assert "ZERO_COST_PROXY_MINT_PATTERN" in output.detection["signals"]
        assert "ZERO_COST_HIGH_RATIO_MINT" in output.detection["signals"]
        assert output.detection["signal_scores"]["zero_cost_proxy_pattern"] > 0
        assert output.detection["signal_scores"]["zero_cost_high_ratio_mint"] > 0


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

        srp_score, _ = detect_swap_reverse_pattern([])
        assert srp_score == 0.0


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
