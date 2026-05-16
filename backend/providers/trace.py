from __future__ import annotations

from typing import Any, Protocol


class TraceProvider(Protocol):
    async def get_trace_calls(self, chain_id: int, tx_hash: str) -> list[dict[str, Any]]:
        ...


class StaticTraceProvider:
    def __init__(self, trace_calls_by_tx: dict[tuple[int, str], list[dict[str, Any]]] | None = None) -> None:
        self.trace_calls_by_tx = {
            (chain_id, tx_hash.lower()): list(calls)
            for (chain_id, tx_hash), calls in (trace_calls_by_tx or {}).items()
        }
        self.calls: list[tuple[int, str]] = []

    async def get_trace_calls(self, chain_id: int, tx_hash: str) -> list[dict[str, Any]]:
        key = (chain_id, tx_hash.lower())
        self.calls.append(key)
        return list(self.trace_calls_by_tx.get(key, []))
