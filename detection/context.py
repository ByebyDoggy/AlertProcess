from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


_STANDARD_FIELDS = {
    "chain_id",
    "tx_hash",
    "block_number",
    "timestamp",
    "from_address",
    "to_address",
    "value",
    "input_data",
    "logs",
    "trace_calls",
    "transfers",
    "balance_changes",
    "token_prices",
    "token_decimals",
    "address_labels",
    "metadata",
}


def _lower_address(value: Any) -> Any:
    if isinstance(value, str):
        return value.lower()
    return value


def _lower_dict_keys(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key).lower(): item for key, item in value.items()}


def _parse_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 16) if value.lower().startswith("0x") else int(value)
    return int(value)


@dataclass
class DetectionContext:
    chain_id: int | None = None
    tx_hash: str = ""
    block_number: int | None = None
    timestamp: str = ""
    from_address: str = ""
    to_address: str = ""
    value: int = 0
    input_data: str = ""
    logs: list[dict[str, Any]] = field(default_factory=list)
    trace_calls: list[dict[str, Any]] = field(default_factory=list)
    transfers: list[dict[str, Any]] = field(default_factory=list)
    balance_changes: list[dict[str, Any]] = field(default_factory=list)
    token_prices: dict[str, Any] = field(default_factory=dict)
    token_decimals: dict[str, Any] = field(default_factory=dict)
    address_labels: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DetectionContext":
        metadata = dict(data.get("metadata") or {})
        metadata.update({key: value for key, value in data.items() if key not in _STANDARD_FIELDS})

        return cls(
            chain_id=data.get("chain_id"),
            tx_hash=data.get("tx_hash", ""),
            block_number=data.get("block_number"),
            timestamp=data.get("timestamp", ""),
            from_address=_lower_address(data.get("from_address", "")),
            to_address=_lower_address(data.get("to_address", "")),
            value=_parse_int(data.get("value", 0)),
            input_data=data.get("input_data", ""),
            logs=data.get("logs") or [],
            trace_calls=data.get("trace_calls") or [],
            transfers=data.get("transfers") or [],
            balance_changes=data.get("balance_changes") or [],
            token_prices=_lower_dict_keys(data.get("token_prices", {})),
            token_decimals=_lower_dict_keys(data.get("token_decimals", {})),
            address_labels=_lower_dict_keys(data.get("address_labels", {})),
            metadata=metadata,
        )

    def missing_inputs(self, required_inputs: list[str]) -> list[str]:
        missing = []
        for name in required_inputs:
            value = getattr(self, name, self.metadata.get(name))
            if value in (None, {}, [], ""):
                missing.append(name)
        return missing

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        metadata = data.pop("metadata")
        data.update(metadata)
        return data
