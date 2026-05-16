from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BlockSecAttackEvent:
    blocksec_id: int | None = None
    project: str = ""
    project_logo: str = ""
    loss: float | None = None
    media: str = ""
    root_cause: str = ""
    poc: str = ""
    rescued: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BlockSecBasicInfo:
    chain_id: int
    tx_hash: str
    block_number: int | None = None
    sender: str = ""
    receiver: str = ""
    timestamp: int | None = None
    calldata: str = ""
    gas_used: int | None = None
    event_count: int | None = None
    int_txn_count: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BlockSecAssetChange:
    token_address: str = ""
    token_symbol: str = ""
    amount: str = ""
    value_usd: float | None = None
    sign: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BlockSecAccountChange:
    account: str
    total_value_usd: float | None = None
    sign: bool | None = None
    extremum: bool = False
    assets: list[BlockSecAssetChange] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BlockSecBalanceChangeSummary:
    accounts: list[BlockSecAccountChange] = field(default_factory=list)
    largest_inflow: BlockSecAccountChange | None = None
    largest_outflow: BlockSecAccountChange | None = None
    net_value_by_account: dict[str, float] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BlockSecInvocationNode:
    node_id: str
    parent_id: str = ""
    depth: int = 0
    from_address: str = ""
    to_address: str = ""
    call_type: str = ""
    selector: str = ""
    value: str = ""
    children: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BlockSecInvocationFlow:
    nodes: list[BlockSecInvocationNode] = field(default_factory=list)
    root_ids: list[str] = field(default_factory=list)
    max_depth: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BlockSecAnalysisResult:
    chain_id: int
    tx_hash: str
    attack_event: BlockSecAttackEvent | None = None
    basic_info: BlockSecBasicInfo | None = None
    balance_changes: BlockSecBalanceChangeSummary | None = None
    invocation_flow: BlockSecInvocationFlow | None = None
    fundflow: dict[str, Any] | None = None

    def to_alert_data_blocksec(self) -> dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "tx_hash": self.tx_hash,
            "attack_event": self.attack_event.raw if self.attack_event else None,
            "basic_info": self.basic_info.raw if self.basic_info else None,
            "balance_changes": self.balance_changes.raw if self.balance_changes else None,
            "invocation_flow": self.invocation_flow.raw if self.invocation_flow else None,
            "fundflow": self.fundflow,
        }
