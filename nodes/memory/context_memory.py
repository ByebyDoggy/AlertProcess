"""
上下文记忆节点

将上游节点的输出存入全局记忆存储，供后续规则链执行读取。
实现跨执行、跨交易的状态共享。

工作流:
  1. 接收上游节点的 detection/context 输出
  2. 根据 store_fields 配置选取要记忆的字段
  3. 写入 MemoryStore（带 TTL 自动过期）
  4. 输出原样传递给下游（透传模式）

配合引擎注入:
  每次规则链执行前，引擎会自动从 MemoryStore 读取所有记忆
  注入到 alert_data 上下文中，下游检测器可直接使用。

典型用例:
  - 代理升级事件 → 写入记忆 → 后续交易检测器读取升级上下文
  - 异常地址标记 → 写入记忆 → 后续交易关联分析
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from nodes.base import BaseNode, NodeCategory, NodeOutput, PortDef, NodeOutputMixin
from nodes.base import NodeRegistry
from nodes.memory.store import get_memory_store

logger = logging.getLogger(__name__)


class ContextMemoryOutput(NodeOutputMixin):
    """上下文记忆节点输出"""
    pass


class ContextMemoryNode(BaseNode):
    """
    上下文记忆节点 — 持久化上游输出供跨执行关联。

    将上游节点的关键输出存储到全局 MemoryStore，
    引擎每次执行前自动将记忆注入到上下文中。

    配置:
      - memory_key: 记忆桶名称（如 "proxy_upgrade_events"）
      - ttl_hours: 记忆保存时长（小时），到期自动清除
      - store_fields: 要存储的字段列表（空=存储全部）
      - store_mode: "merge"（合并到同一桶）| "append"（追加记录）
    """

    name: str = "context_memory"
    label: str = "上下文记忆"
    description: str = (
        "将上游节点的输出存入全局记忆，供后续规则链读取。"
        "支持 TTL 自动过期，用于跨交易/跨执行的关联检测。"
        "典型场景：记录代理升级事件，后续大额转出时关联分析。"
    )
    icon: str = "🧠"
    color: str = "#8b5cf6"

    category: NodeCategory = NodeCategory.MEMORY

    # ── Pydantic 输出模型 ──
    OutputModel: type = ContextMemoryOutput

    @classmethod
    def get_inputs(cls) -> list[PortDef]:
        return [PortDef(key="input", label="输入", data_type="any", required=True)]

    @classmethod
    def get_outputs(cls) -> list[PortDef]:
        return [PortDef(key="output", label="输出", data_type="memory_output")]

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "memory_key": {
                    "type": "string",
                    "default": "default",
                    "description": "记忆桶名称（如 'proxy_upgrade_events'）",
                },
                "ttl_hours": {
                    "type": "number",
                    "minimum": 0.01,
                    "maximum": 720,
                    "default": 24,
                    "description": "记忆保存时长（小时），到期自动清除",
                },
                "store_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "要存储的字段列表（空=存储全部上游输出）",
                },
                "store_mode": {
                    "type": "string",
                    "enum": ["merge", "append"],
                    "default": "append",
                    "description": "merge=合并到同一桶(覆盖), append=追加新记录",
                },
            },
        }

    @classmethod
    def get_default_config(cls) -> dict[str, Any]:
        return {
            "memory_key": "default",
            "ttl_hours": 24,
            "store_fields": [],
            "store_mode": "append",
        }

    async def execute(
        self,
        context: dict[str, Any],
        inputs: dict[str, list[NodeOutput]],
    ) -> NodeOutput:
        upstream = self._first_input(inputs)
        if upstream is None:
            return NodeOutput(
                node_id=self.node_id,
                node_type="memory",
                score=0,
                passed=True,
                context=context,
            )

        # 合并上下文
        merged = {**context, **upstream.context}

        # 选取要存储的字段
        store_fields: list[str] = self.config.get("store_fields", [])
        if store_fields:
            data_to_store = {
                k: v for k, v in merged.items() if k in store_fields
            }
        else:
            # 存储全部（排除内部字段）
            data_to_store = {
                k: v for k, v in merged.items()
                if not k.startswith("_") and k != "detection"
            }

        # 添加元信息
        data_to_store["_memory_source"] = self.node_id
        data_to_store["_memory_key"] = self.config.get("memory_key", "default")

        # 写入 MemoryStore
        memory_key = self.config.get("memory_key", "default")
        ttl_hours = self.config.get("ttl_hours", 24)
        ttl_seconds = ttl_hours * 3600
        store_mode = self.config.get("store_mode", "append")

        mem_store = get_memory_store()

        if store_mode == "merge":
            # merge 模式：先读取现有数据，合并后重新写入（替换整个桶）
            existing = mem_store.retrieve_merged(memory_key)
            existing.update(data_to_store)
            mem_store.delete_key(memory_key)
            mem_store.store(
                memory_key=memory_key,
                data=existing,
                ttl_seconds=ttl_seconds,
                source_node_id=self.node_id,
            )
        else:
            # append 模式：追加新记录
            mem_store.store(
                memory_key=memory_key,
                data=data_to_store,
                ttl_seconds=ttl_seconds,
                source_node_id=self.node_id,
            )

        logger.info(
            f"[ContextMemory] Stored {len(data_to_store)} fields "
            f"to '{memory_key}' (TTL={ttl_hours}h, mode={store_mode})"
        )

        # 透传给下游（保持上游的 score 和 context）
        return NodeOutput(
            node_id=self.node_id,
            node_type="memory",
            score=upstream.score,
            passed=upstream.passed,
            context={
                **merged,
                "_memory_stored": True,
                "_memory_key": memory_key,
                "_memory_fields_count": len(data_to_store),
            },
            labels=upstream.labels,
            severity=upstream.severity,
        )


NodeRegistry.register(ContextMemoryNode)
