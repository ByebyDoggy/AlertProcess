"""
规则链节点模块
"""

import importlib
import sys
from typing import Iterable

from nodes.base import (
    BaseNode, NodeOutput, NodeCategory, PortDef, PortType, NodeRegistry,
)

__all__ = ["BaseNode", "NodeOutput", "NodeCategory", "PortDef", "PortType", "NodeRegistry"]

_REQUIRED_NODE_TYPES = {
    "alert_trigger",
    "gas_price_detector",
    "set_severity_action",
}

_REGISTRY_MODULES: tuple[str, ...] = (
    "nodes.triggers.alert_trigger",
    "nodes.detectors.gas_price",
    "nodes.detectors.address_type",
    "nodes.detectors.token_approval",
    "nodes.detectors.token_anomaly",
    "nodes.detectors.address_graph",
    "nodes.detectors.address_age",
    "nodes.detectors.arkm_label",
    "nodes.detectors.fund_drain",
    "nodes.detectors.reentrancy",
    "nodes.detectors.proxy_upgrade",
    "nodes.detectors.economic_anomaly",
    "nodes.detectors.price_manipulation",
    "nodes.detectors.privileged_address",
    "nodes.detectors.strategy_drain",
    "nodes.detectors.protocol.flash_loan_trace",
    "nodes.detectors.protocol.oracle_manipulation",
    "nodes.detectors.protocol.reentrancy_trace",
    "nodes.detectors.protocol.indirection_layer",
    "nodes.providers.moralis_address",
    "nodes.providers.arkm_label",
    "nodes.providers.eth_trace",
    "nodes.providers.log_parser",
    "nodes.providers.token_price",
    "nodes.storage.external_storage",
    "nodes.memory.context_memory",
    "nodes.logic.combiner",
    "nodes.scripting.script_node",
    "nodes.actions.set_severity",
    "nodes.actions.add_tag",
    "nodes.actions.notify_webhook",
    "nodes.actions.notify_telegram",
    "nodes.actions.update_database",
)


def _import_registry_modules(module_names: Iterable[str], *, force_reload: bool = False) -> None:
    for mod_name in module_names:
        if force_reload:
            sys.modules.pop(mod_name, None)
        importlib.import_module(mod_name)



def _clear_registry_modules(module_names: Iterable[str]) -> None:
    for mod_name in module_names:
        sys.modules.pop(mod_name, None)



def _registry_has_required_nodes() -> bool:
    return _REQUIRED_NODE_TYPES.issubset(NodeRegistry._nodes)



def init_registry() -> None:
    if _registry_has_required_nodes():
        return
    _import_registry_modules(_REGISTRY_MODULES)



def force_init_registry() -> None:
    NodeRegistry.clear()
    modules_to_clear = [
        "nodes.triggers", "nodes.triggers.alert_trigger",
        "nodes.detectors", "nodes.detectors.gas_price", "nodes.detectors.address_type",
        "nodes.detectors.token_approval",
        "nodes.detectors.token_anomaly", "nodes.detectors.address_graph",
        "nodes.detectors.address_age", "nodes.detectors.arkm_label",
        "nodes.detectors.fund_drain", "nodes.detectors.proxy_upgrade",
        "nodes.detectors.reentrancy", "nodes.detectors.economic_anomaly",
        "nodes.detectors.price_manipulation", "nodes.detectors.privileged_address",
        "nodes.detectors.strategy_drain",
        "nodes.detectors.protocol", "nodes.detectors.protocol.base",
        "nodes.detectors.protocol.signatures",
        "nodes.detectors.protocol.flash_loan_trace",
        "nodes.detectors.protocol.oracle_manipulation",
        "nodes.detectors.protocol.reentrancy_trace",
        "nodes.detectors.protocol.indirection_layer",
        "nodes.detectors.base",
        "nodes.memory", "nodes.memory.context_memory", "nodes.memory.store",
        "nodes.logic", "nodes.logic.base", "nodes.logic.combiner",
        "nodes.providers", "nodes.providers.eth_trace", "nodes.providers.arkm_label",
        "nodes.providers.moralis_address", "nodes.providers.log_parser",
        "nodes.providers.token_price",
        "nodes.storage", "nodes.storage.external_storage",
        "nodes.scripting", "nodes.scripting.script_node", "nodes.scripting.sandbox",
        "nodes.actions", "nodes.actions.set_severity", "nodes.actions.add_tag",
        "nodes.actions.notify_webhook", "nodes.actions.notify_telegram",
        "nodes.actions.update_database", "nodes.actions.base",
    ]
    _clear_registry_modules(modules_to_clear)
    _import_registry_modules(_REGISTRY_MODULES)
