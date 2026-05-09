"""代理合约升级检测器

检测 EIP-1967 标准代理合约的升级操作：
  - Upgraded(address indexed implementation) — 实现合约地址更换
  - AdminChanged(address previousAdmin, address newAdmin) — 管理员更换
  - BeaconUpgraded(address indexed beacon) — Beacon 升级
  - OwnershipTransferred(address indexed from, address indexed to) — 所有权转移

评分矩阵:
  - Upgraded + AdminChanged 同时出现       → 95（高风险复合升级）
  - Upgraded 事件                          → 80
  - AdminChanged / BeaconUpgraded 事件     → 75
  - OwnershipTransferred 到未知地址        → 65
  - OwnershipTransferred 到 zero 地址      → 90（所有权放弃/锁定）
  - OwnershipTransferred 到已知交易所      → 20
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from nodes.base import NodeRegistry, score_to_severity
from nodes.detectors.base import BaseDetector, DetectorConfigMixin, DetectorInputMixin, DetectorOutputMixin
from nodes.detectors.privileged_address import detect_large_fund_outflow

# EIP-1967 标准事件 Topic Hash
PROXY_EVENT_TOPICS: dict[str, str] = {
    # EIP-1967: Upgraded(address indexed implementation)
    "0xbc7cd75a20ee27fd9adebab32041f755214dbc6bffa90cc0225b39da2e5c2d3b": "Upgraded",
    # EIP-1967: AdminChanged(address previousAdmin, address newAdmin)
    "0x7e644d79422f17c01e4894b5f4f588d331ebfa28653d42ae832dc59e38c9798f": "AdminChanged",
    # EIP-1967: BeaconUpgraded(address indexed beacon)
    "0x1cf3b03a6cf19fa2baba4df148e9dcabedea7f8a5c07840e207e5c089be95d3e": "BeaconUpgraded",
    # OpenZeppelin Ownable: OwnershipTransferred(address indexed,address indexed)
    "0x8be0079c531659141344cd1fd0a4f28419497f9722a3daafe3b4186f6b6457e0": "OwnershipTransferred",
    # AccessControl: RoleGranted(bytes32 indexed,address indexed,address indexed)
    "0x2f8788117e7eff1d82e926ec794901d17c78024a50270940304540a733656f0d": "RoleGranted",
    # AccessControl: RoleRevoked(bytes32 indexed,address indexed,address indexed)
    "0xf6391f5c32d9c69d2a47ea670b442974b53935d1edc7fd64eb21e047a839171b": "RoleRevoked",
}

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

# 已知安全地址（不触发告警的转移目标）
KNOWN_SAFE_ADDRESSES: set[str] = {
    "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be",  # Binance
    "0x28c6c06298d514db089934071355e5743bf21d60",  # Binance Hot
}


class ProxyUpgradeOutput(DetectorOutputMixin):
    """代理合约升级检测器输出"""
    pass


class ProxyUpgradeDetector(BaseDetector):
    """
    代理合约升级检测器 — 监控 EIP-1967 代理升级和权限变更事件。

    覆盖场景:
      1. 实现合约替换（Upgraded）— 常见于攻击前埋入后门
      2. 管理员更换（AdminChanged）— 治理攻击
      3. 所有权转移（OwnershipTransferred）— 协议控制权篡夺
      4. 角色变更（RoleGranted / RoleRevoked）— RBAC 权限提升攻击

    评分:
    - Upgraded + AdminChanged 复合         → 95
    - Upgraded (实现合约升级)              → 80
    - AdminChanged / BeaconUpgraded        → 75
    - OwnershipTransferred 到 zero         → 90
    - OwnershipTransferred 到未知地址      → 65
    - RoleGranted 管理员角色               → 70
    """

    name: str = "proxy_upgrade_detector"
    label: str = "代理合约升级检测"

    # ── Pydantic 配置模型 (继承 DetectorConfigMixin，包含共享的 threshold) ──
    class ConfigModel(DetectorConfigMixin):
        check_ownership_transfer: bool = Field(default=True, description="检测 OwnershipTransferred")
        check_role_changes: bool = Field(default=True, description="检测 RoleGranted/RoleRevoked")
        admin_role_hash: str = Field(
            default="0x0000000000000000000000000000000000000000000000000000000000000000",
            description="DEFAULT_ADMIN_ROLE 的 bytes32 哈希",
        )
        large_outflow_threshold_usd: float = Field(
            default=50000.0, ge=0,
            description="控制权事件后视为大额资金外流的 USD 阈值",
        )
        known_protocol_addresses: list[str] = Field(
            default_factory=list,
            description="已知协议内部地址列表，用于区分对外资金流出",
        )

    description: str = (
        "[数据需求: 仅Logs] "
        "检测 EIP-1967 代理合约升级操作：监控 Upgraded / AdminChanged / "
        "BeaconUpgraded / OwnershipTransferred 事件。复合升级+管理员变更给 95 分，"
        "单独升级给 80 分，所有权转移到 zero 地址给 90 分。"
    )
    icon: str = "🔧"
    color: str = "#7c3aed"

    # ── Pydantic 输出模型 ──
    OutputModel: type = ProxyUpgradeOutput

    @staticmethod
    def _extract_topic0(log: dict) -> str:
        topics = log.get("topics", [])
        if not topics:
            return ""
        t = topics[0]
        return (t if isinstance(t, str) else t.hex() if isinstance(t, bytes) else "").lower()

    @staticmethod
    def _extract_address_from_topic(topic: str) -> str:
        """从 32-byte topic 中提取地址（后 40 位）"""
        h = topic.lstrip("0x").lower()
        return "0x" + h[-40:] if len(h) >= 40 else ""

    async def process(self, tx_context: TransactionContext) -> ProxyUpgradeOutput:
        logs: list[dict] = tx_context.logs or []

        if not logs:
            return ProxyUpgradeOutput(
                score=0.0, passed=True, severity="UNKNOWN", labels=[],
                detection={"reason": "no logs in context"}
            )

        issues: list[str] = []
        score = 0.0
        detected_events: list[dict] = []
        score_logs: list[str] = []

        has_upgraded = False
        has_admin_changed = False
        has_control_change = False

        for log in logs:
            topic0 = self._extract_topic0(log)
            event_name = PROXY_EVENT_TOPICS.get(topic0)
            if not event_name:
                continue

            topics = log.get("topics", [])
            contract_addr = (log.get("address") or "").lower()

            if event_name == "Upgraded":
                has_upgraded = True
                has_control_change = True
                impl_addr = self._extract_address_from_topic(
                    topics[1] if len(topics) > 1 else ""
                )
                issues.append(f"PROXY_UPGRADED:{contract_addr}→{impl_addr}")
                score_logs.append(f"proxy upgraded: {contract_addr} -> {impl_addr}")
                score = max(score, 80.0)
                detected_events.append({
                    "event": "Upgraded",
                    "contract": contract_addr,
                    "new_implementation": impl_addr,
                })

            elif event_name == "AdminChanged":
                has_admin_changed = True
                has_control_change = True
                prev_admin = self._extract_address_from_topic(
                    topics[1] if len(topics) > 1 else ""
                )
                new_admin = self._extract_address_from_topic(
                    topics[2] if len(topics) > 2 else ""
                )
                # 尝试从 data 解码（non-indexed 字段）
                data = log.get("data", "0x")
                if data and len(data) >= 66:
                    prev_admin = "0x" + data[26:66]
                    new_admin = "0x" + data[90:130] if len(data) >= 130 else new_admin

                issues.append(f"ADMIN_CHANGED:{prev_admin}→{new_admin}")
                score_logs.append(f"admin changed: {prev_admin} -> {new_admin}")
                score = max(score, 75.0)
                detected_events.append({
                    "event": "AdminChanged",
                    "contract": contract_addr,
                    "previous_admin": prev_admin,
                    "new_admin": new_admin,
                })

            elif event_name == "BeaconUpgraded":
                has_control_change = True
                beacon_addr = self._extract_address_from_topic(
                    topics[1] if len(topics) > 1 else ""
                )
                issues.append(f"BEACON_UPGRADED:{contract_addr}→{beacon_addr}")
                score_logs.append(f"beacon upgraded: {contract_addr} -> {beacon_addr}")
                score = max(score, 75.0)
                detected_events.append({
                    "event": "BeaconUpgraded",
                    "contract": contract_addr,
                    "new_beacon": beacon_addr,
                })

            elif event_name == "OwnershipTransferred" and self.config.get("check_ownership_transfer", True):
                prev_owner = self._extract_address_from_topic(
                    topics[1] if len(topics) > 1 else ""
                )
                new_owner = self._extract_address_from_topic(
                    topics[2] if len(topics) > 2 else ""
                )
                event_detail = {
                    "event": "OwnershipTransferred",
                    "contract": contract_addr,
                    "previous_owner": prev_owner,
                    "new_owner": new_owner,
                }

                if new_owner == ZERO_ADDRESS:
                    # 所有权转给 zero — 锁死或放弃
                    has_control_change = True
                    issues.append(f"OWNERSHIP_RENOUNCED:{contract_addr}")
                    score_logs.append(f"ownership renounced: {contract_addr}")
                    score = max(score, 90.0)
                    event_detail["risk"] = "ownership_renounced"
                elif new_owner.lower() not in KNOWN_SAFE_ADDRESSES:
                    has_control_change = True
                    issues.append(f"OWNERSHIP_TRANSFERRED:{contract_addr}→{new_owner}")
                    score_logs.append(f"ownership transferred to external address: {new_owner}")
                    score = max(score, 65.0)
                    event_detail["risk"] = "unknown_new_owner"
                else:
                    issues.append(f"OWNERSHIP_TO_KNOWN:{new_owner}")
                    score_logs.append(f"ownership transferred to known safe address: {new_owner}")
                    score = max(score, 20.0)
                    event_detail["risk"] = "known_safe"
                detected_events.append(event_detail)

            elif event_name in ("RoleGranted", "RoleRevoked") and self.config.get("check_role_changes", True):
                role_hash = self._extract_address_from_topic(
                    topics[1] if len(topics) > 1 else ""
                )
                account = self._extract_address_from_topic(
                    topics[2] if len(topics) > 2 else ""
                )
                admin_role = self.config.get(
                    "admin_role_hash",
                    "0x0000000000000000000000000000000000000000000000000000000000000000"
                )
                is_admin_role = topics[1].lower().endswith(admin_role.lstrip("0x")) if len(topics) > 1 else False

                if event_name == "RoleGranted" and is_admin_role:
                    has_control_change = True
                    issues.append(f"ADMIN_ROLE_GRANTED:{account}")
                    score_logs.append(f"admin role granted to {account}")
                    score = max(score, 70.0)
                elif event_name == "RoleGranted":
                    has_control_change = True
                    issues.append(f"ROLE_GRANTED:{account}")
                    score_logs.append(f"role granted to {account}")
                    score = max(score, 45.0)
                elif event_name == "RoleRevoked":
                    has_control_change = True
                    issues.append(f"ROLE_REVOKED:{account}")
                    score_logs.append(f"role revoked from {account}")
                    score = max(score, 30.0)

                detected_events.append({
                    "event": event_name,
                    "contract": contract_addr,
                    "role_hash": role_hash,
                    "account": account,
                    "is_admin_role": is_admin_role,
                })

        # 复合攻击加权：Upgraded + AdminChanged 同时出现
        if has_upgraded and has_admin_changed:
            issues.append("COMPOUND_UPGRADE_AND_ADMIN_CHANGE")
            score_logs.append("proxy upgraded and admin changed in same transaction")
            score = max(score, 95.0)

        protocol_addrs = [
            addr.lower()
            for addr in (
                self.config.get("known_protocol_addresses", [])
                or tx_context.get_extra("known_protocol_addresses", [])
                or []
            )
            if isinstance(addr, str) and addr
        ]
        outflow_score = 0.0
        outflow_details: list[dict[str, Any]] = []
        total_outflow_usd = 0.0
        external_outflows: list[dict[str, Any]] = []
        if has_control_change:
            outflow_score, outflow_details, total_outflow_usd = detect_large_fund_outflow(
                tx_context.from_address,
                tx_context.logs or [],
                tx_context.chain_id or 1,
                min_outflow_usd=self.config.get("large_outflow_threshold_usd", 50000.0),
                known_protocol_addresses=protocol_addrs,
            )
            external_outflows = [
                item for item in outflow_details
                if isinstance(item, dict)
            ]
            if total_outflow_usd > 0:
                score_logs.append(f"external outflow after control change: ${total_outflow_usd:,.2f}")
            if outflow_score > 0 and external_outflows:
                issues.append("PRIVILEGED_DRAIN_AFTER_CONTROL_CHANGE")
                score_logs.append("control change followed by external fund outflow")
                score = max(score, 92.0 if has_upgraded or has_admin_changed else 85.0)

        labels = issues if score >= self.config.get("threshold", 50) else []

        # 聚合字段：供记忆节点存储后，下游检测器（如 FundDrain）关联读取
        upgraded_contracts = list({
            e["contract"].lower()
            for e in detected_events
            if "contract" in e and e["contract"]
        })
        new_admins = list({
            addr.lower()
            for e in detected_events
            for key in ("new_admin", "new_owner")
            if (addr := e.get(key, "")) and addr
        })

        return ProxyUpgradeOutput(
            score=score,
            passed=score >= self.config.get("threshold", 50.0),
            severity=score_to_severity(score),
            labels=labels,
            logs=score_logs,
            detection={
                "detected_events": detected_events,
                "detected_issues": issues,
                "has_upgraded": has_upgraded,
                "has_admin_changed": has_admin_changed,
                "has_control_change": has_control_change,
                "outflow_details": outflow_details,
                "outflow_breakdown": {
                    "external_targets": sorted({item["to"].lower() for item in external_outflows if item.get("to")})[:10],
                    "protocol_targets": protocol_addrs[:10],
                    "external_count": len({item["to"].lower() for item in external_outflows if item.get("to")}),
                    "protocol_count": len(protocol_addrs),
                    "total_outflow_usd": round(total_outflow_usd, 2),
                },
                "labels": labels,
                # 聚合字段 — 供 ContextMemoryNode 存储
                "upgraded_contracts": upgraded_contracts,
                "new_admins": new_admins,
            },
        )


NodeRegistry.register(ProxyUpgradeDetector)
