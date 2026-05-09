"""
外部存储节点（纯输出）

提供实例级隔离的缓存字典，供下游检测器节点读写。
每个存储节点实例持有独立的私有 dict，同规则链多个存储节点互不干扰。
支持 TTL 自动过期清空。
"""

from __future__ import annotations

import logging
import time
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from nodes.base import BaseNode, NodeCategory, NodeOutput, PortDef, NodeRegistry

logger = logging.getLogger(__name__)


class ExternalStorageConfig(BaseModel):
    """外部存储节点配置"""
    ttl_hours: float = Field(
        default=24.0,
        ge=0.0,
        le=8760,
        description="缓存过期时间（小时），0=永不过期，到期自动清空",
    )


class ExternalStorageNode(BaseNode):
    """
    外部存储节点 — 纯输出源，提供带 TTL 的实例级缓存字典。

    特性:
      - 无输入端口：仅作为数据源输出
      - 实例级隔离：每个节点实例持有独立的私有 dict
      - 可变引用传递：下游获取同一 dict 引用，可直接读写
      - TTL 自动过期：超时后缓存自动清空

    典型用例:
      - 时序攻击检测：存储节点输出缓存 dict → 检测器读取/写入历史状态
      - 跨执行关联：多次规则链执行共享同一节点实例的缓存
    """

    name: ClassVar[str] = "external_storage"
    label: ClassVar[str] = "外部存储"
    description: ClassVar[str] = (
        "提供实例级隔离的缓存字典。下游检测器连接后可读写同一引用，"
        "支持 TTL 自动过期。用于时序攻击检测、跨执行状态关联等场景。"
    )
    icon: ClassVar[str] = "\U0001f5c4\U0000fe0f"
    color: ClassVar[str] = "#059669"
    category: NodeCategory = NodeCategory.STORAGE

    ConfigModel: type[BaseModel] = ExternalStorageConfig

    @classmethod
    def get_inputs(cls) -> list[PortDef]:
        return []

    @classmethod
    def get_outputs(cls) -> list[PortDef]:
        return [
            PortDef(
                key="output",
                label="缓存字典",
                data_type="context",
                description="输出可读写的缓存字典引用，下游可直接修改",
            ),
        ]

    def __init__(self, node_id: str = "", config: dict[str, Any] | None = None) -> None:
        super().__init__(node_id=node_id, config=config)
        self._store: dict[str, Any] = {}
        self._created_at: float = time.monotonic()

    @property
    def store(self) -> dict[str, Any]:
        """获取此节点的缓存字典（只读属性，供外部检查）"""
        return self._store

    async def execute(
        self,
        context: dict[str, Any],
        inputs: dict[str, list[NodeOutput]],
    ) -> NodeOutput:
        ttl_hours = self.config.get("ttl_hours", 24.0)
        ttl_seconds = ttl_hours * 3600.0

        # TTL 过期检查
        if ttl_seconds > 0 and (time.monotonic() - self._created_at) > ttl_seconds:
            expired_count = len(self._store)
            self._store.clear()
            self._created_at = time.monotonic()
            logger.info(
                f"[ExternalStorage] TTL expired for '{self.node_id}': "
                f"cleared {expired_count} entries, reset timer"
            )

        logger.debug(
            f"[ExternalStorage] OUTPUT '{self.node_id}': "
            f"dict_size={len(self._store)}, ttl_hours={ttl_hours}"
        )

        return NodeOutput(
            node_id=self.node_id,
            node_type=self.category.value,
            score=0.0,
            passed=True,
            context={
                "_cache_dict": self._store,
                "_storage_key": self.node_id,
                "_storage_ttl_hours": ttl_hours,
                "_storage_entry_count": len(self._store),
            },
            labels=[],
            severity="UNKNOWN",
        )


NodeRegistry.register(ExternalStorageNode)
