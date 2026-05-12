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
