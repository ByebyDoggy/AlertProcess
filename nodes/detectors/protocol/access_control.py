from __future__ import annotations

from typing import Any

from pydantic import Field

from nodes.base import NodeRegistry, score_to_severity
from nodes.detectors.base import DetectorOutputMixin
from nodes.detectors.protocol.base import AttackPattern, BaseProtocolAttackDetector, BehaviorEvidence, CallStackEntry, PatternMatch
from nodes.detectors.protocol.signatures import ACCESS_CONTROL_SIGNATURES, PROXY_UPGRADE_SIGNATURES, lookup_signature
from nodes.models import TransactionContext
from nodes.providers.eth_trace import EthTraceData


ACCESS_CONTROL_PATTERNS: list[AttackPattern] = [
    AttackPattern(
        name="access_control_signature",
        description="匹配 transferOwnership/grantRole/initialize/upgradeTo 等权限相关函数",
        function_selectors=list(ACCESS_CONTROL_SIGNATURES.keys()),
        min_depth=0,
        score_weight=50.0,
    ),
    AttackPattern(
        name="proxy_upgrade_signature",
        description="匹配代理升级相关函数",
        function_selectors=list(PROXY_UPGRADE_SIGNATURES.keys()),
        min_depth=0,
        score_weight=60.0,
    ),
]


class AccessControlBypassDetector(BaseProtocolAttackDetector):
    name: str = "access_control_bypass_detector"
    label: str = "访问控制绕过检测"
    description: str = (
        "[数据需求: Trace(必需)] 检测访问控制绕过攻击："
        "未授权的所有权转移、角色授予、初始化漏洞、代理升级攻击。"
    )
    icon: str = "🔐"
    color: str = "#ef4444"

    ATTACK_PATTERNS = ACCESS_CONTROL_PATTERNS
    ATTACK_TYPE_LABEL = "access_control_bypass"

    class ConfigModel(BaseProtocolAttackDetector.ConfigModel):
        check_initialization: bool = Field(default=True, description="检查初始化函数调用")
        check_ownership_transfer: bool = Field(default=True, description="检查所有权转移")
        check_role_grant: bool = Field(default=True, description="检查角色授予")
        check_proxy_upgrade: bool = Field(default=True, description="检查代理升级")

    async def analyze_call_stack(
        self,
        call_stack: list[CallStackEntry],
        trace_data: EthTraceData,
        tx_context: TransactionContext,
    ) -> DetectorOutputMixin:
        matches = self._match_patterns(call_stack)
        initialization_calls = self._find_initialization_calls(call_stack)
        ownership_transfers = self._find_ownership_transfers(call_stack)
        role_grants = self._find_role_grants(call_stack)
        proxy_upgrades = self._find_proxy_upgrades(call_stack)
        suspicious_depth = self._check_suspicious_depth(call_stack)
        behavior_evidence = self._collect_behavior_evidence(call_stack, tx_context)

        score = self._calculate_score(
            matches,
            initialization_calls,
            ownership_transfers,
            role_grants,
            proxy_upgrades,
            suspicious_depth,
            behavior_evidence,
        )
        labels = self._build_labels(
            matches,
            initialization_calls,
            ownership_transfers,
            role_grants,
            proxy_upgrades,
            behavior_evidence,
        )
        detection = self._build_detection(
            call_stack,
            matches,
            initialization_calls,
            ownership_transfers,
            role_grants,
            proxy_upgrades,
            suspicious_depth,
            trace_data,
            behavior_evidence,
        )

        threshold = self.config.get("threshold", 50.0)
        return DetectorOutputMixin(
            score=score,
            passed=score >= threshold,
            severity=score_to_severity(score),
            labels=labels,
            detection=detection,
        )

    def _find_initialization_calls(self, call_stack: list[CallStackEntry]) -> list[dict[str, Any]]:
        """查找初始化函数调用"""
        if not self.config.get("check_initialization", True):
            return []

        init_selectors = {
            "0x8129fc1c",  # initialize()
            "0xc4d66de8",  # initialize(address)
            "0x485cc955",  # initialize(address,address)
        }

        result: list[dict[str, Any]] = []
        for entry in call_stack:
            if entry.function_selector in init_selectors:
                result.append({
                    "depth": entry.depth,
                    "to": entry.to_addr,
                    "selector": entry.function_selector,
                    "signature": lookup_signature(entry.function_selector) or "",
                    "call_type": entry.call_type,
                })

        return result

    def _find_ownership_transfers(self, call_stack: list[CallStackEntry]) -> list[dict[str, Any]]:
        """查找所有权转移"""
        if not self.config.get("check_ownership_transfer", True):
            return []

        ownership_selectors = {
            "0xf2fde38b",  # transferOwnership(address)
            "0x715018a6",  # renounceOwnership()
        }

        result: list[dict[str, Any]] = []
        for entry in call_stack:
            if entry.function_selector in ownership_selectors:
                result.append({
                    "depth": entry.depth,
                    "to": entry.to_addr,
                    "selector": entry.function_selector,
                    "signature": lookup_signature(entry.function_selector) or "",
                })

        return result

    def _find_role_grants(self, call_stack: list[CallStackEntry]) -> list[dict[str, Any]]:
        """查找角色授予"""
        if not self.config.get("check_role_grant", True):
            return []

        role_selectors = {
            "0x2f2ff15d",  # grantRole(bytes32,address)
            "0x36568abe",  # renounceRole(bytes32,address)
        }

        result: list[dict[str, Any]] = []
        for entry in call_stack:
            if entry.function_selector in role_selectors:
                result.append({
                    "depth": entry.depth,
                    "to": entry.to_addr,
                    "selector": entry.function_selector,
                    "signature": lookup_signature(entry.function_selector) or "",
                })

        return result

    def _find_proxy_upgrades(self, call_stack: list[CallStackEntry]) -> list[dict[str, Any]]:
        """查找代理升级"""
        if not self.config.get("check_proxy_upgrade", True):
            return []

        upgrade_selectors = {
            "0x3659cfe6",  # upgradeTo(address)
            "0x4f1ef286",  # upgradeToAndCall(address,bytes)
            "0x8f283970",  # changeAdmin(address)
        }

        result: list[dict[str, Any]] = []
        for entry in call_stack:
            if entry.function_selector in upgrade_selectors:
                result.append({
                    "depth": entry.depth,
                    "to": entry.to_addr,
                    "selector": entry.function_selector,
                    "signature": lookup_signature(entry.function_selector) or "",
                })

        return result

    def _check_suspicious_depth(self, call_stack: list[CallStackEntry]) -> dict[str, Any]:
        """检查权限操作是否在可疑的调用深度"""
        sensitive_selectors = set(ACCESS_CONTROL_SIGNATURES.keys()) | set(PROXY_UPGRADE_SIGNATURES.keys())

        deep_calls: list[dict[str, Any]] = []
        for entry in call_stack:
            if entry.function_selector in sensitive_selectors and entry.depth >= 2:
                deep_calls.append({
                    "depth": entry.depth,
                    "to": entry.to_addr,
                    "selector": entry.function_selector,
                    "signature": lookup_signature(entry.function_selector) or "",
                })

        return {
            "has_deep_calls": len(deep_calls) > 0,
            "deep_calls": deep_calls[:10],
            "max_depth": max((c["depth"] for c in deep_calls), default=0),
        }

    def _collect_behavior_evidence(
        self,
        call_stack: list[CallStackEntry],
        tx_context: TransactionContext,
    ) -> list[BehaviorEvidence]:
        evidence: list[BehaviorEvidence] = []
        if self._has_delegatecall(call_stack):
            delegatecalls = [entry for entry in call_stack if entry.call_type == "delegatecall"]
            evidence.append(BehaviorEvidence(
                kind="DELEGATECALL",
                weight=25.0,
                description="delegatecall appears in privileged trace",
                entries=[self._entry_summary(entry) for entry in delegatecalls[:5]],
            ))

        if self._has_proxy_like_multihop(call_stack):
            evidence.append(BehaviorEvidence(
                kind="PROXY_LIKE_MULTIHOP",
                weight=25.0,
                description="top-level target delegates into deeper implementation/admin calls",
                entries=[{"max_depth": self._max_call_depth(call_stack)}],
            ))

        if self._count_unique_contracts(call_stack) >= 3 and self._max_call_depth(call_stack) >= 2:
            evidence.append(BehaviorEvidence(
                kind="MULTI_TARGET_PRIVILEGED_TRACE",
                weight=15.0,
                description="deep trace touches multiple contracts",
                entries=[{"unique_contract_count": self._count_unique_contracts(call_stack)}],
            ))

        if call_stack and tx_context.from_address and call_stack[0].from_addr == tx_context.from_address.lower() and len(call_stack) >= 3:
            evidence.append(BehaviorEvidence(
                kind="EXTERNAL_INITIATED_PRIVILEGED_TRACE",
                weight=10.0,
                description="transaction sender initiates the privileged-looking trace",
                entries=[self._entry_summary(call_stack[0])],
            ))

        return evidence

    def _has_proxy_like_multihop(self, call_stack: list[CallStackEntry]) -> bool:
        if len(call_stack) < 3:
            return False
        root_targets = {entry.to_addr for entry in call_stack if entry.depth == 0 and entry.to_addr}
        has_delegatecall = self._has_delegatecall(call_stack)
        has_deep_call = any(entry.depth >= 2 for entry in call_stack)
        returns_to_root_target = any(entry.depth >= 2 and entry.to_addr in root_targets for entry in call_stack)
        return has_delegatecall and has_deep_call and (returns_to_root_target or self._count_unique_contracts(call_stack) >= 3)

    def _selector_evidence(
        self,
        matches: list[PatternMatch],
        initialization_calls: list[dict[str, Any]],
        ownership_transfers: list[dict[str, Any]],
        role_grants: list[dict[str, Any]],
        proxy_upgrades: list[dict[str, Any]],
    ) -> list[BehaviorEvidence]:
        evidence: list[BehaviorEvidence] = []
        for match in matches:
            if match.matched_selectors:
                evidence.append(BehaviorEvidence(
                    kind=match.pattern_name,
                    weight=match.score_contribution,
                    selector_based=True,
                    description="selector/signature pattern match",
                    entries=[{"selectors": match.matched_selectors}],
                ))
        selector_groups = {
            "INITIALIZATION_SELECTOR": initialization_calls,
            "OWNERSHIP_SELECTOR": ownership_transfers,
            "ROLE_SELECTOR": role_grants,
            "PROXY_UPGRADE_SELECTOR": proxy_upgrades,
        }
        for kind, calls in selector_groups.items():
            if calls:
                evidence.append(BehaviorEvidence(
                    kind=kind,
                    weight=min(20.0, len(calls) * 10.0),
                    selector_based=True,
                    description="known access-control selector match",
                    entries=calls[:5],
                ))
        return evidence

    def _calculate_score(
        self,
        matches: list[PatternMatch],
        initialization_calls: list[dict[str, Any]],
        ownership_transfers: list[dict[str, Any]],
        role_grants: list[dict[str, Any]],
        proxy_upgrades: list[dict[str, Any]],
        suspicious_depth: dict[str, Any],
        behavior_evidence: list[BehaviorEvidence],
    ) -> float:
        selector_evidence = self._selector_evidence(
            matches, initialization_calls, ownership_transfers, role_grants, proxy_upgrades,
        )
        evidence = [*behavior_evidence, *selector_evidence]
        if not evidence:
            return 0.0

        behavior_score = sum(item.weight for item in behavior_evidence)
        selector_bonus = min(20.0, sum(item.weight for item in selector_evidence) * 0.25)
        score = behavior_score + selector_bonus

        if suspicious_depth["has_deep_calls"] and behavior_evidence:
            score += min(10.0, suspicious_depth["max_depth"] * 2.0)

        return min(100.0, self._cap_selector_only_score(score, evidence))

    def _build_labels(
        self,
        matches: list[PatternMatch],
        initialization_calls: list[dict[str, Any]],
        ownership_transfers: list[dict[str, Any]],
        role_grants: list[dict[str, Any]],
        proxy_upgrades: list[dict[str, Any]],
        behavior_evidence: list[BehaviorEvidence],
    ) -> list[str]:
        labels: list[str] = []

        for evidence in behavior_evidence:
            labels.append(f"ACCESS_CONTROL_BEHAVIOR:{evidence.kind}")

        for match in matches:
            for selector in match.matched_selectors[:3]:
                labels.append(f"ACCESS_CONTROL_SIG:{lookup_signature(selector) or selector}")

        if initialization_calls:
            labels.append("INITIALIZATION_CALL")
        if ownership_transfers:
            labels.append("OWNERSHIP_TRANSFER")
        if role_grants:
            labels.append("ROLE_GRANT")
        if proxy_upgrades:
            labels.append("PROXY_UPGRADE")

        return labels

    def _build_detection(
        self,
        call_stack: list[CallStackEntry],
        matches: list[PatternMatch],
        initialization_calls: list[dict[str, Any]],
        ownership_transfers: list[dict[str, Any]],
        role_grants: list[dict[str, Any]],
        proxy_upgrades: list[dict[str, Any]],
        suspicious_depth: dict[str, Any],
        trace_data: EthTraceData,
        behavior_evidence: list[BehaviorEvidence],
    ) -> dict[str, Any]:
        return {
            "attack_type": self.ATTACK_TYPE_LABEL,
            "trace_count": trace_data.trace_count,
            "pattern_matches": [match.model_dump() for match in matches],
            "behavior_evidence": [item.model_dump() for item in behavior_evidence],
            "initialization_calls": initialization_calls,
            "ownership_transfers": ownership_transfers,
            "role_grants": role_grants,
            "proxy_upgrades": proxy_upgrades,
            "suspicious_depth": suspicious_depth,
            "call_stack_summary": [
                {
                    "depth": entry.depth,
                    "from": entry.from_addr[:10] + "..." if entry.from_addr else "",
                    "to": entry.to_addr[:10] + "..." if entry.to_addr else "",
                    "selector": entry.function_selector,
                    "signature": lookup_signature(entry.function_selector) or "",
                    "call_type": entry.call_type,
                }
                for entry in call_stack[:30]
            ],
        }


NodeRegistry.register(AccessControlBypassDetector)
