"""
脚本上下文 API

为 ScriptNode 中的用户脚本提供安全、稳定、易用的数据访问和工具函数。
脚本只通过该对象读取交易上下文、Provider 注入数据和上游节点输出。
"""

from __future__ import annotations

import re
from functools import cached_property
from typing import Any

from nodes.base import NodeOutput
from nodes.models import TransactionContext
from nodes.primitives.log_parser import ApprovalParser, SwapParser, TransferParser


class ScriptContext:
    """
    脚本执行上下文。

    用户脚本入口示例：
        async def detect(context, inputs):
            calls = context.get_trace_calls(min_depth=1)
            transfers = context.get_transfers()
            return {"score": 80, "passed": True}
    """

    def __init__(
        self,
        tx_context: TransactionContext | dict[str, Any],
        inputs: dict[str, list[NodeOutput]] | None = None,
    ) -> None:
        self.tx_context = (
            tx_context
            if isinstance(tx_context, TransactionContext)
            else TransactionContext.from_dict(tx_context)
        )
        self.inputs = inputs or {}

    @cached_property
    def _extra(self) -> dict[str, Any]:
        return self.tx_context.extra or {}

    def to_dict(self) -> dict[str, Any]:
        """返回展开后的交易上下文字典。"""
        return self.tx_context.to_dict()

    def get_input_outputs(self, port: str | None = None) -> list[NodeOutput]:
        """获取上游节点输出；port 为空时返回所有输入。"""
        if port is not None:
            return list(self.inputs.get(port, []))
        outputs: list[NodeOutput] = []
        for port_outputs in self.inputs.values():
            outputs.extend(port_outputs)
        return outputs

    def get_trace_calls(self, min_depth: int = 0) -> list[dict[str, Any]]:
        """获取标准化 ETH trace 调用栈。"""
        eth_trace = self._extra.get("eth_trace") or self._extra.get("trace") or {}
        raw_traces = eth_trace.get("traces", []) if isinstance(eth_trace, dict) else getattr(eth_trace, "traces", [])

        calls: list[dict[str, Any]] = []
        for entry in raw_traces or []:
            if isinstance(entry, dict):
                action = entry.get("action", {}) or {}
                trace_address = entry.get("trace_address", entry.get("traceAddress", [])) or []
                depth = len(trace_address)
                input_data = action.get("input_data", action.get("input", "0x")) or "0x"
                call_type = action.get("call_type", action.get("callType", entry.get("type", ""))) or ""
                from_addr = action.get("from_addr", action.get("from", "")) or ""
                to_addr = action.get("to_addr", action.get("to", "")) or ""
                value = action.get("value", "0x0") or "0x0"
                gas = action.get("gas", "0x0") or "0x0"
            else:
                action = getattr(entry, "action", None)
                trace_address = getattr(entry, "trace_address", []) or []
                depth = len(trace_address)
                input_data = getattr(action, "input_data", "0x") if action else "0x"
                call_type = getattr(action, "call_type", "") if action else ""
                from_addr = getattr(action, "from_addr", "") if action else ""
                to_addr = getattr(action, "to_addr", "") if action else ""
                value = getattr(action, "value", "0x0") if action else "0x0"
                gas = getattr(action, "gas", "0x0") if action else "0x0"

            if depth < min_depth:
                continue
            calls.append({
                "depth": depth,
                "from_addr": from_addr,
                "to_addr": to_addr,
                "function_selector": input_data[:10] if isinstance(input_data, str) and len(input_data) >= 10 else "",
                "call_type": str(call_type).lower(),
                "value": value,
                "gas": gas,
                "input_data": input_data,
                "trace_address": trace_address,
            })
        return calls

    def get_event_logs(self, event_signature: str | None = None) -> list[dict[str, Any]]:
        """获取事件日志；event_signature 可传 topic0 或事件签名文本。"""
        logs = list(self.tx_context.logs or [])
        if not event_signature:
            return logs

        target = event_signature.lower()
        if not target.startswith("0x"):
            try:
                from eth_utils import event_signature_to_log_topic
                target = "0x" + event_signature_to_log_topic(event_signature).hex()
            except Exception:
                return []

        return [
            log for log in logs
            if log.get("topics") and str(log["topics"][0]).lower() == target
        ]

    def get_transfers(self, token_address: str | None = None) -> list[dict[str, Any]]:
        """获取代币转账记录，优先使用 LogParserProvider 的 parsed_transfers。"""
        transfers = self._extra.get("parsed_transfers") or self._extra.get("transfers")
        if transfers is None:
            transfers = [event.__dict__ for event in TransferParser.parse(self.tx_context.logs or [])]
        if token_address:
            token = token_address.lower()
            return [t for t in transfers if str(t.get("token_address", "")).lower() == token]
        return list(transfers)

    def get_swaps(self) -> list[dict[str, Any]]:
        """获取 Swap 事件，优先使用 LogParserProvider 的 parsed_swaps。"""
        swaps = self._extra.get("parsed_swaps")
        if swaps is None:
            swaps = [event.__dict__ for event in SwapParser.parse(self.tx_context.logs or [])]
        return list(swaps)

    def get_approvals(self) -> list[dict[str, Any]]:
        """获取 Approval 事件，优先使用 LogParserProvider 的 parsed_approvals。"""
        approvals = self._extra.get("parsed_approvals")
        if approvals is None:
            approvals = [event.__dict__ for event in ApprovalParser.parse(self.tx_context.logs or [])]
        return list(approvals)

    def get_token_price(self, token_address: str) -> float:
        """从 Provider 注入的 token_prices 中获取代币价格。"""
        prices = self._extra.get("token_prices") or {}
        token = token_address.lower()
        for key in (token, token_address, token_address.upper()):
            if key in prices:
                try:
                    return float(prices[key])
                except (TypeError, ValueError):
                    return 0.0
        return 0.0

    def decode_function_selector(self, selector: str) -> str:
        """解码函数选择器，优先使用本地签名表。"""
        try:
            from nodes.detectors.protocol.signatures import lookup_signature
            return lookup_signature(selector) or ""
        except Exception:
            return ""

    def calculate_roi(self, inflow: float, outflow: float) -> float:
        """计算 ROI 百分比。"""
        if outflow == 0:
            return 0.0
        return ((inflow - outflow) / outflow) * 100

    def match_pattern(self, pattern: str, text: str) -> bool:
        """正则匹配工具。"""
        return bool(re.search(pattern, text or ""))

    def match_sequence(self, events: list[dict[str, Any]], pattern: list[str]) -> list[dict[str, Any]]:
        """按事件 type/name/function_selector 字段匹配简单有序序列。"""
        if not pattern:
            return []

        matches: list[dict[str, Any]] = []
        for start_index in range(len(events)):
            matched: list[dict[str, Any]] = []
            cursor = start_index
            for expected in pattern:
                found = None
                while cursor < len(events):
                    event = events[cursor]
                    values = {
                        str(event.get("type", "")).lower(),
                        str(event.get("name", "")).lower(),
                        str(event.get("function_selector", "")).lower(),
                    }
                    if expected.lower() in values:
                        found = event
                        matched.append(event)
                        cursor += 1
                        break
                    cursor += 1
                if found is None:
                    matched = []
                    break
            if matched:
                matches.append({
                    "start_index": start_index,
                    "end_index": cursor - 1,
                    "events": matched,
                })
        return matches

    @cached_property
    def _balance_changes_cache(self) -> dict[str, dict[str, float]]:
        """缓存余额变化计算结果。"""
        balance_changes: dict[str, dict[str, float]] = {}
        transfers = self.get_transfers()

        for transfer in transfers:
            token = str(transfer.get("token_address", "")).lower()
            from_addr = str(transfer.get("from_address", "")).lower()
            to_addr = str(transfer.get("to_address", "")).lower()

            try:
                amount = float(transfer.get("amount", 0))
            except (TypeError, ValueError):
                amount = 0.0

            if token not in balance_changes:
                balance_changes[token] = {}

            if from_addr and from_addr != "0x0000000000000000000000000000000000000000":
                balance_changes[token][from_addr] = balance_changes[token].get(from_addr, 0.0) - amount

            if to_addr and to_addr != "0x0000000000000000000000000000000000000000":
                balance_changes[token][to_addr] = balance_changes[token].get(to_addr, 0.0) + amount

        return balance_changes

    def get_balance_changes(self, address: str | None = None, token_address: str | None = None) -> dict[str, Any]:
        """
        获取余额变化。

        Args:
            address: 地址过滤（可选）
            token_address: 代币地址过滤（可选）

        Returns:
            余额变化字典，格式：
            {
                "token_address": {
                    "address": balance_change (float)
                }
            }
        """
        changes = self._balance_changes_cache

        if token_address:
            token = token_address.lower()
            changes = {token: changes.get(token, {})}

        if address:
            addr = address.lower()
            filtered: dict[str, dict[str, float]] = {}
            for token, addr_changes in changes.items():
                if addr in addr_changes:
                    filtered[token] = {addr: addr_changes[addr]}
            changes = filtered

        return changes

    def calculate_price_impact(
        self,
        reserve_in: float,
        reserve_out: float,
        amount_in: float,
        fee_rate: float = 0.003
    ) -> float:
        """
        计算 AMM 价格影响（基于恒定乘积公式）。

        Args:
            reserve_in: 输入代币储备量
            reserve_out: 输出代币储备量
            amount_in: 输入代币数量
            fee_rate: 手续费率（默认 0.3%）

        Returns:
            价格影响百分比（正数表示价格上涨）
        """
        if reserve_in <= 0 or reserve_out <= 0 or amount_in <= 0:
            return 0.0

        amount_in_with_fee = amount_in * (1 - fee_rate)

        price_before = reserve_out / reserve_in

        new_reserve_in = reserve_in + amount_in_with_fee
        amount_out = (reserve_out * amount_in_with_fee) / new_reserve_in
        new_reserve_out = reserve_out - amount_out

        if new_reserve_in <= 0:
            return 0.0

        price_after = new_reserve_out / new_reserve_in

        if price_before == 0:
            return 0.0

        return ((price_after - price_before) / price_before) * 100

    def detect_reentrancy(self, target_contract: str | None = None) -> list[dict[str, Any]]:
        """
        检测重入模式（同一合约在调用栈中多次出现）。

        Args:
            target_contract: 目标合约地址（可选，为空时检测所有合约）

        Returns:
            重入模式列表，每个元素包含：
            - contract: 合约地址
            - depths: 出现的调用深度列表
            - call_indices: 调用索引列表
        """
        calls = self.get_trace_calls()

        contract_calls: dict[str, list[tuple[int, int]]] = {}

        for idx, call in enumerate(calls):
            to_addr = str(call.get("to_addr", "")).lower()
            if not to_addr:
                continue

            if target_contract and to_addr != target_contract.lower():
                continue

            depth = call.get("depth", 0)

            if to_addr not in contract_calls:
                contract_calls[to_addr] = []
            contract_calls[to_addr].append((depth, idx))

        reentrancy_patterns: list[dict[str, Any]] = []

        for contract, call_list in contract_calls.items():
            if len(call_list) < 2:
                continue

            depths = [depth for depth, _ in call_list]
            indices = [idx for _, idx in call_list]

            for i in range(len(call_list) - 1):
                depth1, idx1 = call_list[i]
                depth2, idx2 = call_list[i + 1]

                if depth2 > depth1:
                    reentrancy_patterns.append({
                        "contract": contract,
                        "depths": [depth1, depth2],
                        "call_indices": [idx1, idx2],
                        "pattern": "nested_call"
                    })

        return reentrancy_patterns
