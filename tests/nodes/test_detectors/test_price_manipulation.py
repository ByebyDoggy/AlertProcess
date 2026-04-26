"""tests/nodes/test_detectors/test_price_manipulation.py — PriceManipulationDetector 测试

测试维度:
  - detect_intra_block_price_deviation: 单区块极端价格偏移
  - detect_swap_to_drain: 大额 Swap 后大额 Token 转出
"""  # noqa: D205

import pytest

from nodes.detectors.price_manipulation import (
    PriceManipulationDetector,
    detect_intra_block_price_deviation,
    detect_swap_to_drain,
    SwapEvent,
    TransferEvent,
    scan_logs,
    ERC20_TRANSFER_TOPIC,
    UNISWAP_V3_SWAP_TOPIC,
    ZERO_ADDRESS,
)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

ATTACKER = "0xf96eb14171b71ac16200013753dff3e91043b63b"
POOL_ADDR = "0x9f599f3d64a9d99ea21e68127bb6ce99f893da61"
USDT_TOKEN = "0x55d398326f99059ff775485246999027b3197955"
NORMAL_USER = "0x1234567890abcdef1234567890abcdef12345678"


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _make_v3_swap_log(
    amount0: int, amount1: int,
    sender: str = ATTACKER, recipient: str = ATTACKER,
    pool: str = POOL_ADDR, log_index: int = 0,
    sqrt_price_x96: int = 0,
) -> dict:
    """构造 Uniswap V3 Swap 日志"""
    pad = lambda a: "0x" + a.lower().replace("0x", "").zfill(64)

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


def _make_transfer_log(
    from_addr: str, to_addr: str, amount: int,
    token: str = USDT_TOKEN, log_index: int = 0,
) -> dict:
    """构造 ERC-20 Transfer 日志"""
    pad = lambda a: "0x" + a.lower().replace("0x", "").zfill(64)
    return {
        "address": token,
        "topics": [ERC20_TRANSFER_TOPIC, pad(from_addr), pad(to_addr)],
        "data": hex(amount),
        "logIndex": log_index,
    }


def _make_swap_event(
    amount0: int, amount1: int,
    pool: str = POOL_ADDR, log_index: int = 0,
) -> SwapEvent:
    """构造 SwapEvent"""
    return SwapEvent(
        log_index=log_index,
        pool_address=pool,
        swap_type="uniswap_v3",
        raw={},
        amount0=amount0,
        amount1=amount1,
    )


def _make_transfer_event(
    from_addr: str, to_addr: str, amount: int,
    token: str = USDT_TOKEN, log_index: int = 0,
) -> TransferEvent:
    """构造 TransferEvent"""
    return TransferEvent(
        log_index=log_index,
        token_address=token,
        from_addr=from_addr,
        to_addr=to_addr,
        amount=amount,
        raw={},
    )


# ---------------------------------------------------------------------------
# detect_intra_block_price_deviation 测试
# ---------------------------------------------------------------------------

class TestDetectIntraBlockPriceDeviation:

    def test_v3_large_price_swing(self):
        """V3 池大幅价格偏移（模拟 Cyrus 攻击）"""
        # sqrtPriceX96 = sqrt(price) * 2^96
        # 假设初始价格 2000 USD → sqrt(2000) * 2^96 ≈ 91936095398893916031247961774682953
        sqrt_price_before = 91936095398893916031247961774682953
        # 价格变为 3000 USD (50% 上涨) → sqrt(3000) * 2^96 ≈ 112578944575196385274561939615952319
        sqrt_price_after = 112578944575196385274561939615952319

        def to_int256(val: int) -> str:
            if val < 0:
                val = val + 2**256
            return hex(val)

        swaps = [
            SwapEvent(
                log_index=10, pool_address=POOL_ADDR, swap_type="uniswap_v3",
                raw={
                    "data": ("0x" +
                             to_int256(1000 * 10**18)[2:].zfill(64) +
                             to_int256(-500 * 10**6)[2:].zfill(64) +
                             hex(sqrt_price_before)[2:].zfill(64) +
                             "0" * 64 + "0" * 12),
                },
                amount0=1000 * 10**18, amount1=-500 * 10**6,
            ),
            SwapEvent(
                log_index=20, pool_address=POOL_ADDR, swap_type="uniswap_v3",
                raw={
                    "data": ("0x" +
                             to_int256(-800 * 10**18)[2:].zfill(64) +
                             to_int256(400 * 10**6)[2:].zfill(64) +
                             hex(sqrt_price_after)[2:].zfill(64) +
                             "0" * 64 + "0" * 12),
                },
                amount0=-800 * 10**18, amount1=400 * 10**6,
            ),
        ]

        score, details = detect_intra_block_price_deviation(swaps)
        assert score > 0
        assert len(details) >= 1
        # 价格偏移应 > 10%
        assert abs(details[0]["price_deviation_pct"]) > 10

    def test_v3_small_price_swing(self):
        """V3 池小幅价格偏移不应触发"""
        sqrt_price = int(1.3805e59)
        # 0.5% 价格变化
        sqrt_price2 = int(1.3805e59 * 1.005)

        swaps = [
            SwapEvent(
                log_index=10, pool_address=POOL_ADDR, swap_type="uniswap_v3",
                raw={
                    "data": ("0x" + "0" * 64 + "0" * 64 +
                             hex(sqrt_price)[2:].zfill(64) + "0" * 64 + "0" * 12),
                },
                amount0=100, amount1=-50,
            ),
            SwapEvent(
                log_index=20, pool_address=POOL_ADDR, swap_type="uniswap_v3",
                raw={
                    "data": ("0x" + "0" * 64 + "0" * 64 +
                             hex(sqrt_price2)[2:].zfill(64) + "0" * 64 + "0" * 12),
                },
                amount0=-80, amount1=40,
            ),
        ]

        score, details = detect_intra_block_price_deviation(swaps)
        # 价格偏移 < 10%，不应产生高分
        assert len(details) >= 1
        # 至少有一个小的偏移分数
        assert score <= 15.0

    def test_no_swap_no_detection(self):
        """无 Swap 事件"""
        score, details = detect_intra_block_price_deviation([])
        assert score == 0.0

    def test_single_swap_no_detection(self):
        """单笔 Swap"""
        swaps = [_make_swap_event(100, -50)]
        score, details = detect_intra_block_price_deviation(swaps)
        assert score == 0.0

    def test_diff_pools_no_deviation(self):
        """不同池的 Swap 之间不计算偏移"""
        swaps = [
            _make_swap_event(100, -50, pool="0xpool1", log_index=10),
            _make_swap_event(-80, 40, pool="0xpool2", log_index=20),
        ]
        score, details = detect_intra_block_price_deviation(swaps)
        assert score == 0.0

    def test_v3_without_sqrt_price_data(self):
        """V3 无 sqrtPriceX96 数据时通过 amount 比值 fallback"""
        # 首次 swap 后 ratio = 500/1000 = 0.5
        # 二次 swap 后 ratio = 400/800 = 0.5 → 无变化
        swaps = [
            _make_swap_event(1000, -500, log_index=10),
            _make_swap_event(-800, 400, log_index=20),
        ]
        score, details = detect_intra_block_price_deviation(swaps)
        # 金额比值相同，不应检测到价格偏移
        assert score == 0.0 or abs(details[0]["price_deviation_pct"]) < 0.01


# ---------------------------------------------------------------------------
# detect_swap_to_drain 测试
# ---------------------------------------------------------------------------

class TestDetectSwapToDrain:

    def test_large_swap_followed_by_drain(self):
        """大额 Swap 后紧接大额 Token 转出（Cyrus 攻击模式）"""
        swaps = [
            _make_swap_event(1_798 * 10**18, -1_212_462 * 10**6, log_index=10),
        ]
        transfers = [
            _make_transfer_event(POOL_ADDR, ATTACKER, 454_169 * 10**6, log_index=30),
        ]
        score, patterns = detect_swap_to_drain(swaps, transfers, ATTACKER)
        assert score > 0
        assert len(patterns) >= 1
        assert patterns[0]["pool"] == POOL_ADDR
        assert patterns[0]["to"] == ATTACKER.lower()

    def test_small_swap_no_detection(self):
        """小额 Swap 不应触发"""
        swaps = [
            _make_swap_event(100, -50, log_index=10),  # 极小金额
        ]
        transfers = [
            _make_transfer_event(POOL_ADDR, ATTACKER, 1000 * 10**6, log_index=20),
        ]
        score, patterns = detect_swap_to_drain(swaps, transfers, ATTACKER)
        assert score == 0.0

    def test_no_transfer_after_swap(self):
        """Swap 后无转出"""
        swaps = [
            _make_swap_event(1_798 * 10**18, -1_212_462 * 10**6, log_index=10),
        ]
        score, patterns = detect_swap_to_drain(swaps, [], ATTACKER)
        assert score == 0.0

    def test_transfer_before_swap(self):
        """转出在 Swap 之前"""
        swaps = [
            _make_swap_event(1_798 * 10**18, -1_212_462 * 10**6, log_index=20),
        ]
        transfers = [
            _make_transfer_event(POOL_ADDR, ATTACKER, 454_169 * 10**6, log_index=10),
        ]
        score, patterns = detect_swap_to_drain(swaps, transfers, ATTACKER)
        assert score == 0.0

    def test_empty_swaps(self):
        """空 Swap 列表"""
        score, patterns = detect_swap_to_drain([], [], ATTACKER)
        assert score == 0.0

    def test_multiple_swaps_multiple_drains(self):
        """多笔 Swap + 多笔转出"""
        swaps = [
            _make_swap_event(1_000 * 10**18, -500 * 10**6, log_index=10),
            _make_swap_event(-800 * 10**18, 400 * 10**6, log_index=30),
        ]
        transfers = [
            _make_transfer_event(POOL_ADDR, ATTACKER, 100_000 * 10**6, log_index=40),
            _make_transfer_event(POOL_ADDR, NORMAL_USER, 50_000 * 10**6, log_index=50),
        ]
        score, patterns = detect_swap_to_drain(swaps, transfers, ATTACKER)
        assert score > 0
        assert len(patterns) >= 1


# ---------------------------------------------------------------------------
# scan_logs 集成测试
# ---------------------------------------------------------------------------

class TestScanLogsIntegration:

    def test_cyrus_attack_log_parsing(self):
        """模拟 Cyrus 攻击的 logs 解析"""
        sqrt_price = int(1.3805e59)
        logs = [
            # Swap 1: 1,798 ETH → USDT (价格操纵)
            _make_v3_swap_log(
                amount0=1_798 * 10**18, amount1=-1_212_462 * 10**6,
                sqrt_price_x96=sqrt_price, log_index=10,
            ),
            # USDT Transfer: 池→攻击合约 (454K USDT)
            _make_transfer_log(POOL_ADDR, ATTACKER, 454_169 * 10**6, log_index=20),
        ]
        transfers, swaps = scan_logs(logs)
        assert len(transfers) == 1
        assert len(swaps) == 1
        assert swaps[0].amount0 > 0
        assert swaps[0].amount1 < 0
        assert transfers[0].token_address == USDT_TOKEN.lower()
        assert transfers[0].amount == 454_169 * 10**6


# ---------------------------------------------------------------------------
# 阴性测试
# ---------------------------------------------------------------------------

class TestNegativeCases:

    def test_normal_no_detection(self):
        """正常交易不应触发任何检测"""
        swaps = [
            _make_swap_event(100, -50),  # 小额 Swap
        ]
        transfers = [
            _make_transfer_event(ATTACKER, NORMAL_USER, 1000, log_index=20),
        ]

        pd_score, _ = detect_intra_block_price_deviation([])
        assert pd_score == 0.0

        std_score, _ = detect_swap_to_drain(swaps, transfers, ATTACKER)
        assert std_score == 0.0
