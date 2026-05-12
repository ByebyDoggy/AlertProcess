"""
规则链节点模块

支持两种节点加载方式：
1. 自动发现（推荐）：自动扫描 nodes 目录下的所有节点
2. 手动导入（兼容）：使用硬编码的模块列表
"""

import importlib
import sys
import os
from typing import Iterable

from nodes.base import (
    BaseNode, NodeOutput, NodeCategory, PortDef, PortType, NodeRegistry,
)

__all__ = ["BaseNode", "NodeOutput", "NodeCategory", "PortDef", "PortType", "NodeRegistry"]

# 是否启用自动发现（通过环境变量控制）
_AUTO_DISCOVER_ENABLED = os.environ.get("NODE_AUTO_DISCOVER", "true").lower() == "true"

_REQUIRED_NODE_TYPES = {
    "alert_trigger",
    "gas_price_detector",
    "set_severity_action",
}

# 手动导入模块列表（兼容旧方式，当自动发现失败时使用）
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
    "nodes.detectors.protocol.arbitrary_call",
    "nodes.detectors.protocol.precision_loss",
    "nodes.detectors.protocol.access_control",
    "nodes.detectors.protocol.input_validation",
    "nodes.detectors.protocol.governance_attack",
    "nodes.detectors.protocol.storage_collision",
    "nodes.detectors.protocol.misc",
    "nodes.providers.moralis_address",
    "nodes.providers.arkm_label",
    "nodes.providers.eth_trace",
    "nodes.providers.log_parser",
    "nodes.providers.token_price",
    "nodes.storage.external_storage",
    "nodes.memory.context_memory",
    "nodes.temporal.publisher",
    "nodes.temporal.query",
    "nodes.temporal.match",
    "nodes.logic.combiner",
    "nodes.scripting.script_node",
    "nodes.actions.set_severity",
    "nodes.actions.add_tag",
    "nodes.actions.notify_webhook",
    "nodes.actions.notify_telegram",
    "nodes.actions.update_database",
)


def _import_registry_modules(module_names: Iterable[str], *, force_reload: bool = False) -> None:
    """手动导入模块列表"""
    for mod_name in module_names:
        if force_reload:
            sys.modules.pop(mod_name, None)
        importlib.import_module(mod_name)


def _clear_registry_modules(module_names: Iterable[str]) -> None:
    """清除已导入的模块"""
    for mod_name in module_names:
        sys.modules.pop(mod_name, None)


def _registry_has_required_nodes() -> bool:
    """检查是否已注册必需的节点"""
    return _REQUIRED_NODE_TYPES.issubset(NodeRegistry._nodes)


def init_registry() -> None:
    """
    初始化节点注册表

    优先使用自动发现，失败时降级到手动导入
    """
    if _registry_has_required_nodes():
        return

    if _AUTO_DISCOVER_ENABLED:
        # 尝试自动发现
        try:
            count = NodeRegistry.auto_discover("nodes")
            if count > 0 and _registry_has_required_nodes():
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"[NodeRegistry] Auto-discovery succeeded, loaded {count} nodes")
                return
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"[NodeRegistry] Auto-discovery failed: {e}, falling back to manual import")

    # 降级到手动导入
    _import_registry_modules(_REGISTRY_MODULES)


def force_init_registry() -> None:
    """
    强制重新初始化节点注册表（用于测试和热重载）
    """
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
        "nodes.detectors.protocol.arbitrary_call",
        "nodes.detectors.protocol.precision_loss",
        "nodes.detectors.protocol.access_control",
        "nodes.detectors.protocol.input_validation",
        "nodes.detectors.protocol.governance_attack",
        "nodes.detectors.protocol.storage_collision",
        "nodes.detectors.protocol.misc",
        "nodes.detectors.base",
        "nodes.memory", "nodes.memory.context_memory", "nodes.memory.store",
        "nodes.temporal", "nodes.temporal.publisher", "nodes.temporal.query", "nodes.temporal.match", "nodes.temporal.store", "nodes.temporal.models",
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

    # 使用自动发现或手动导入
    if _AUTO_DISCOVER_ENABLED:
        NodeRegistry.auto_discover("nodes")
    else:
        _import_registry_modules(_REGISTRY_MODULES)
