"""
日志解析原语

提供可复用的日志解析功能，将原始日志解析为结构化事件对象。
"""

from dataclasses import dataclass
from typing import Any

# ERC-20 Transfer 事件签名
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# ERC-20 Approval 事件签名
APPROVAL_TOPIC = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"

# Uniswap V2 Swap 事件签名
SWAP_V2_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"

# Uniswap V3 Swap 事件签名
SWAP_V3_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"


@dataclass
class TransferEvent:
    """Transfer 事件数据结构"""
    token_address: str
    from_address: str
    to_address: str
    amount: int
    log_index: int


@dataclass
class ApprovalEvent:
    """Approval 事件数据结构"""
    token_address: str
    owner: str
    spender: str
    amount: int
    log_index: int


@dataclass
class SwapEvent:
    """Swap 事件数据结构"""
    dex_address: str
    token_in: str
    token_out: str
    amount_in: int
    amount_out: int
    log_index: int
    version: str  # "v2" or "v3"


class TransferParser:
    """Transfer 事件解析器"""

    @staticmethod
    def parse(logs: list[dict[str, Any]]) -> list[TransferEvent]:
        """
        解析所有 ERC-20 Transfer 事件

        Args:
            logs: 交易日志列表

        Returns:
            解析后的 Transfer 事件列表
        """
        transfers = []

        for log in logs:
            if not log.get("topics"):
                continue

            # 检查是否为 Transfer 事件
            if len(log["topics"]) < 3:
                continue

            topic0 = log["topics"][0]
            if isinstance(topic0, str):
                topic0 = topic0.lower()

            if topic0 != TRANSFER_TOPIC.lower():
                continue

            try:
                # 解析 from 和 to 地址（topics[1] 和 topics[2]）
                from_topic = log["topics"][1]
                to_topic = log["topics"][2]

                # 移除 0x 前缀和前导零，保留最后 40 个字符（地址）
                if isinstance(from_topic, str):
                    from_addr = "0x" + from_topic[-40:]
                else:
                    from_addr = "0x" + hex(from_topic)[2:].zfill(64)[-40:]

                if isinstance(to_topic, str):
                    to_addr = "0x" + to_topic[-40:]
                else:
                    to_addr = "0x" + hex(to_topic)[2:].zfill(64)[-40:]

                # 解析 amount（data 字段）
                data = log.get("data", "0x0")
                if isinstance(data, str):
                    if data.startswith("0x"):
                        data = data[2:]
                    amount = int(data, 16) if data else 0
                else:
                    amount = int(data)

                transfer = TransferEvent(
                    token_address=log["address"].lower(),
                    from_address=from_addr.lower(),
                    to_address=to_addr.lower(),
                    amount=amount,
                    log_index=log.get("logIndex", 0),
                )
                transfers.append(transfer)

            except (ValueError, KeyError, IndexError):
                # 解析失败，跳过此日志
                continue

        return transfers


class ApprovalParser:
    """Approval 事件解析器"""

    @staticmethod
    def parse(logs: list[dict[str, Any]]) -> list[ApprovalEvent]:
        """
        解析所有 ERC-20 Approval 事件

        Args:
            logs: 交易日志列表

        Returns:
            解析后的 Approval 事件列表
        """
        approvals = []

        for log in logs:
            if not log.get("topics"):
                continue

            if len(log["topics"]) < 3:
                continue

            topic0 = log["topics"][0]
            if isinstance(topic0, str):
                topic0 = topic0.lower()

            if topic0 != APPROVAL_TOPIC.lower():
                continue

            try:
                owner_topic = log["topics"][1]
                spender_topic = log["topics"][2]

                if isinstance(owner_topic, str):
                    owner = "0x" + owner_topic[-40:]
                else:
                    owner = "0x" + hex(owner_topic)[2:].zfill(64)[-40:]

                if isinstance(spender_topic, str):
                    spender = "0x" + spender_topic[-40:]
                else:
                    spender = "0x" + hex(spender_topic)[2:].zfill(64)[-40:]

                data = log.get("data", "0x0")
                if isinstance(data, str):
                    if data.startswith("0x"):
                        data = data[2:]
                    amount = int(data, 16) if data else 0
                else:
                    amount = int(data)

                approval = ApprovalEvent(
                    token_address=log["address"].lower(),
                    owner=owner.lower(),
                    spender=spender.lower(),
                    amount=amount,
                    log_index=log.get("logIndex", 0),
                )
                approvals.append(approval)

            except (ValueError, KeyError, IndexError):
                continue

        return approvals


class SwapParser:
    """Swap 事件解析器"""

    @staticmethod
    def parse(logs: list[dict[str, Any]]) -> list[SwapEvent]:
        """
        解析所有 DEX Swap 事件（支持 Uniswap V2/V3）

        Args:
            logs: 交易日志列表

        Returns:
            解析后的 Swap 事件列表
        """
        swaps = []

        for log in logs:
            if not log.get("topics"):
                continue

            topic0 = log["topics"][0]
            if isinstance(topic0, str):
                topic0 = topic0.lower()

            if topic0 == SWAP_V2_TOPIC.lower():
                swap = SwapParser._parse_v2_swap(log)
                if swap:
                    swaps.append(swap)
            elif topic0 == SWAP_V3_TOPIC.lower():
                swap = SwapParser._parse_v3_swap(log)
                if swap:
                    swaps.append(swap)

        return swaps

    @staticmethod
    def _parse_v2_swap(log: dict[str, Any]) -> SwapEvent | None:
        """
        解析 Uniswap V2 Swap 事件

        V2 Swap 事件格式:
        event Swap(
            address indexed sender,
            uint amount0In,
            uint amount1In,
            uint amount0Out,
            uint amount1Out,
            address indexed to
        )
        """
        try:
            data = log.get("data", "")
            if isinstance(data, str):
                if data.startswith("0x"):
                    data = data[2:]
            else:
                return None

            # 解析 data 字段（4 个 uint256）
            if len(data) < 256:  # 4 * 64
                return None

            amount0_in = int(data[0:64], 16)
            amount1_in = int(data[64:128], 16)
            amount0_out = int(data[128:192], 16)
            amount1_out = int(data[192:256], 16)

            # 确定输入输出代币和数量
            # 简化处理：假设 amount0In > 0 则 token0 是输入，否则 token1 是输入
            if amount0_in > 0:
                amount_in = amount0_in
                amount_out = amount1_out
                # 实际应该从 pair 合约查询 token0/token1，这里简化为使用 pair 地址
                token_in = log["address"]
                token_out = log["address"]
            else:
                amount_in = amount1_in
                amount_out = amount0_out
                token_in = log["address"]
                token_out = log["address"]

            return SwapEvent(
                dex_address=log["address"].lower(),
                token_in=token_in.lower(),
                token_out=token_out.lower(),
                amount_in=amount_in,
                amount_out=amount_out,
                log_index=log.get("logIndex", 0),
                version="v2",
            )

        except (ValueError, KeyError, IndexError):
            return None

    @staticmethod
    def _parse_v3_swap(log: dict[str, Any]) -> SwapEvent | None:
        """
        解析 Uniswap V3 Swap 事件

        V3 Swap 事件格式:
        event Swap(
            address indexed sender,
            address indexed recipient,
            int256 amount0,
            int256 amount1,
            uint160 sqrtPriceX96,
            uint128 liquidity,
            int24 tick
        )
        """
        try:
            data = log.get("data", "")
            if isinstance(data, str):
                if data.startswith("0x"):
                    data = data[2:]
            else:
                return None

            # 解析 data 字段（amount0, amount1 是 int256）
            if len(data) < 128:  # 至少需要 amount0 和 amount1
                return None

            # int256 需要处理符号位
            amount0_hex = data[0:64]
            amount1_hex = data[64:128]

            amount0 = int(amount0_hex, 16)
            if amount0 >= 2**255:
                amount0 -= 2**256

            amount1 = int(amount1_hex, 16)
            if amount1 >= 2**255:
                amount1 -= 2**256

            # 确定输入输出
            if amount0 < 0:
                # amount0 为负表示 token0 流出（用户获得）
                amount_in = abs(amount1)
                amount_out = abs(amount0)
            else:
                # amount0 为正表示 token0 流入（用户支付）
                amount_in = abs(amount0)
                amount_out = abs(amount1)

            return SwapEvent(
                dex_address=log["address"].lower(),
                token_in=log["address"].lower(),
                token_out=log["address"].lower(),
                amount_in=amount_in,
                amount_out=amount_out,
                log_index=log.get("logIndex", 0),
                version="v3",
            )

        except (ValueError, KeyError, IndexError):
            return None
