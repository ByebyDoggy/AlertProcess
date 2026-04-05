"""
规则链节点模块

提供统一的节点抽象、注册表和数据模型。
所有节点类型（Trigger/Detector/Comparator/Scorer/Logic/Action）均继承自 BaseNode。
"""

from nodes.base import (
    BaseNode,
    NodeOutput,
    NodeCategory,
    PortDef,
    PortType,
    NodeRegistry,
)

__all__ = [
    "BaseNode",
    "NodeOutput",
    "NodeCategory",
    "PortDef",
    "PortType",
    "NodeRegistry",
]


def init_registry() -> None:
    """初始化节点注册表，导入所有节点模块触发 @register 装饰器。

    注意: Python 缓存模块导入，因此 @register 装饰器只在首次导入时触发。
    如果注册表已被清空，需要先清除模块缓存再重新导入。
    """
    # 如果已注册了 alert_trigger，说明已初始化过
    if "alert_trigger" in NodeRegistry._nodes:
        return

    from nodes.triggers import alert_trigger  # noqa: F401
    from nodes.detectors import (  # noqa: F401
        gas_price, address_type, flash_loan, token_approval,
        token_anomaly, address_graph, address_age, arkm_label,
    )
    from nodes.comparators import threshold, range as range_cmp, regex  # noqa: F401
    from nodes.scorers import average, min_max, weighted  # noqa: F401
    from nodes.logic import and_gate, or_gate  # noqa: F401
    from nodes.actions import (  # noqa: F401
        set_severity, add_tag, notify_webhook, notify_telegram, update_database,
    )


def force_init_registry() -> None:
    """强制重新初始化注册表（清除后重新导入所有模块）"""
    import sys
    NodeRegistry.clear()
    # 清除所有节点子模块及父包，确保 @register 装饰器重新执行
    modules_to_clear = [
        "nodes.triggers", "nodes.triggers.alert_trigger",
        "nodes.detectors", "nodes.detectors.gas_price", "nodes.detectors.address_type",
        "nodes.detectors.flash_loan", "nodes.detectors.token_approval",
        "nodes.detectors.token_anomaly", "nodes.detectors.address_graph",
        "nodes.detectors.address_age", "nodes.detectors.arkm_label",
        "nodes.detectors.base",
        "nodes.comparators", "nodes.comparators.threshold", "nodes.comparators.range",
        "nodes.comparators.regex", "nodes.comparators.base",
        "nodes.scorers", "nodes.scorers.average", "nodes.scorers.min_max",
        "nodes.scorers.weighted", "nodes.scorers.base", "nodes.scorers.constant",
        "nodes.logic", "nodes.logic.and_gate", "nodes.logic.or_gate", "nodes.logic.base",
        "nodes.actions", "nodes.actions.set_severity", "nodes.actions.add_tag",
        "nodes.actions.notify_webhook", "nodes.actions.notify_telegram",
        "nodes.actions.update_database", "nodes.actions.base",
    ]
    for mod_name in modules_to_clear:
        sys.modules.pop(mod_name, None)
    # 重新导入触发所有 @register
    from nodes.triggers import alert_trigger  # noqa: F401
    from nodes.detectors import (  # noqa: F401
        gas_price, address_type, flash_loan, token_approval,
        token_anomaly, address_graph, address_age, arkm_label,
    )
    from nodes.comparators import threshold, range as range_cmp, regex  # noqa: F401
    from nodes.scorers import average, min_max, weighted  # noqa: F401
    from nodes.logic import and_gate, or_gate  # noqa: F401
    from nodes.actions import (  # noqa: F401
        set_severity, add_tag, notify_webhook, notify_telegram, update_database,
    )
