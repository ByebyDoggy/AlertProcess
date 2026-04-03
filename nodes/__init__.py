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
    """初始化节点注册表，导入所有节点模块触发 @register 装饰器"""
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
