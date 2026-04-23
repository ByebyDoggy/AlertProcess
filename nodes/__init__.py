"""
规则链节点模块
"""

from nodes.base import (
    BaseNode, NodeOutput, NodeCategory, PortDef, PortType, NodeRegistry,
)

__all__ = ["BaseNode", "NodeOutput", "NodeCategory", "PortDef", "PortType", "NodeRegistry"]


def init_registry() -> None:
    if "alert_trigger" in NodeRegistry._nodes:
        return
    from nodes.triggers import alert_trigger  # noqa: F401
    from nodes.detectors import (  # noqa: F401
        gas_price, address_type, flash_loan, token_approval,
        token_anomaly, address_graph, address_age, arkm_label,
        fund_drain, reentrancy, proxy_upgrade,
    )
    from nodes.providers import (  # noqa: F401
        MoralisAddressProviderNode, ARKMLabelProviderNode,
    )
    from nodes.scripting import script_node  # noqa: F401
    from nodes.actions import (  # noqa: F401
        set_severity, add_tag, notify_webhook, notify_telegram, update_database,
    )


def force_init_registry() -> None:
    import sys
    NodeRegistry.clear()
    modules_to_clear = [
        "nodes.triggers", "nodes.triggers.alert_trigger",
        "nodes.detectors", "nodes.detectors.gas_price", "nodes.detectors.address_type",
        "nodes.detectors.flash_loan", "nodes.detectors.token_approval",
        "nodes.detectors.token_anomaly", "nodes.detectors.address_graph",
        "nodes.detectors.address_age", "nodes.detectors.arkm_label",
        "nodes.detectors.fund_drain", "nodes.detectors.proxy_upgrade",
        "nodes.detectors.reentrancy",
        "nodes.detectors.base",
        "nodes.memory", "nodes.memory.context_memory", "nodes.memory.store",
        "nodes.memory.memory_store", "nodes.memory.memory_recall",
        "nodes.logic", "nodes.logic.base", "nodes.logic.combiner", "nodes.logic.branch",
        "nodes.scripting", "nodes.scripting.script_node", "nodes.scripting.sandbox",
        "nodes.actions", "nodes.actions.set_severity", "nodes.actions.add_tag",
        "nodes.actions.notify_webhook", "nodes.actions.notify_telegram",
        "nodes.actions.update_database", "nodes.actions.base",
    ]
    for mod_name in modules_to_clear:
        sys.modules.pop(mod_name, None)
    from nodes.triggers import alert_trigger  # noqa: F401
    from nodes.detectors import (  # noqa: F401
        gas_price, address_type, flash_loan, token_approval,
        token_anomaly, address_graph, address_age, arkm_label,
        fund_drain, reentrancy, proxy_upgrade,
    )
    from nodes.providers import (  # noqa: F401
        MoralisAddressProviderNode, ARKMLabelProviderNode,
    )
    from nodes.memory import memory_store, memory_recall  # noqa: F401
    from nodes.logic import combiner, branch  # noqa: F401
    from nodes.scripting import script_node  # noqa: F401
    from nodes.actions import (  # noqa: F401
        set_severity, add_tag, notify_webhook, notify_telegram, update_database,
    )



