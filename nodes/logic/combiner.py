"""Combiner — 数据合并节点

将两个输入源合并为一个统一的上下文输出。
用于将引擎自动注入的记忆数据与上游 context 整合后传给下游检测器，
实现关注点分离：检测器不直接依赖 MemoryStore。

输入:
  - input_0 "主数据":   主交易上下文（context 类型，来自 Provider 或 Trigger）
  - input_1 "关联数据": 关联上下文（memory_output / context 类型，来自 MemoryNode）

输出:
  - output "合并输出": 合并后的完整上下文（data_type="context"）

配置:
  - merge_mode: "deep_merge"(default) | "secondary_prefix"
    deep_merge:       字段级合并，secondary 同名字段覆盖 primary
    secondary_prefix: secondary 的字段加 "_correlated_" 前缀避免冲突

典型用例:
  - 代理升级事件记忆 + 当前交易上下文 → 合并后传入资金外流检测器
  - 异常地址标记记忆 + 当前交易上下文 → 合并后传入地址关联检测器
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from nodes.base import BaseNode, NodeCategory, NodeOutput, PortDef, NodeRegistry

logger = logging.getLogger(__name__)


class CombinerConfigModel(BaseModel):
    """Combiner 配置模型"""
    merge_mode: str = Field(
        default="deep_merge",
        description="合并模式: deep_merge(字段级合并) | secondary_prefix(加前缀避免冲突)",
    )


class CombinerNode(BaseNode):
    """
    Combiner 数据合并节点 — 将两个输入源合并为一个统一的上下文输出。

    两个输入端口:
      - input_0 "主数据":  接收主交易上下文 (context)
      - input_1 "关联数据": 接收关联上下文 (memory_output / context)

    输出端口:
      - output "合并输出": 合并后的完整上下文 (context)

    合并模式:
      - deep_merge:       secondary 字段覆盖 primary 同名字段
      - secondary_prefix: secondary 字段加 "_correlated_" 前缀，避免冲突
    """

    name: str = "combiner"
    label: str = "数据合并 (Combiner)"
    description: str = (
        "将两个输入源合并为一个统一上下文输出。"
        "典型场景：将记忆节点输出的关联数据与当前交易上下文整合后传给检测器，"
        "实现跨交易关联检测，同时保持检测器与记忆系统解耦。"
    )
    icon: str = "\U0001f500"
    color: str = "#06b6d4"

    category: NodeCategory = NodeCategory.PROVIDER

    # ── Pydantic 配置模型 ──
    ConfigModel: type = CombinerConfigModel

    @classmethod
    def get_inputs(cls) -> list[PortDef]:
        return [
            PortDef(key="input_0", label="主数据", data_type="context", required=True),
            PortDef(key="input_1", label="关联数据", data_type="memory_output", required=False),
        ]

    @classmethod
    def get_outputs(cls) -> list[PortDef]:
        return [
            PortDef(key="output", label="合并输出", data_type="context"),
        ]

    async def execute(
        self,
        context: dict[str, Any],
        inputs: dict[str, list[NodeOutput]],
    ) -> NodeOutput:
        # 获取两个输入源
        primary_input: NodeOutput | None = None
        secondary_input: NodeOutput | None = None

        if "input_0" in inputs and inputs["input_0"]:
            primary_input = inputs["input_0"][0]
        if "input_1" in inputs and inputs["input_1"]:
            secondary_input = inputs["input_1"][0]

        # 如果没有主输入，尝试用关联输入作为主数据
        if primary_input is None and secondary_input is not None:
            primary_input, secondary_input = secondary_input, None

        # 两者都没有
        if primary_input is None:
            return NodeOutput(
                node_id=self.node_id,
                node_type=self.category.value,
                score=0.0,
                passed=True,
                context=dict(context),
            )

        # ── 合并上下文 ──
        primary_ctx: dict[str, Any] = dict(primary_input.context or {})
        merge_mode = self.config.get("merge_mode", "deep_merge")

        if secondary_input is not None:
            secondary_ctx: dict[str, Any] = dict(secondary_input.context or {})

            if merge_mode == "secondary_prefix":
                # 加前缀模式：secondary 字段加 "_correlated_" 前缀
                for key, value in secondary_ctx.items():
                    primary_ctx[f"_correlated_{key}"] = value
            else:
                # deep_merge 模式：secondary 覆盖 primary 同名字段
                primary_ctx.update(secondary_ctx)

            logger.info(
                f"[Combiner] Merged contexts: "
                f"primary={len(primary_input.context or {})} fields, "
                f"secondary={len(secondary_input.context or {})} fields, "
                f"merged={len(primary_ctx)} fields, mode={merge_mode}"
            )

        # 输出合并后的上下文
        return NodeOutput(
            node_id=self.node_id,
            node_type=self.category.value,
            score=primary_input.score,
            passed=primary_input.passed,
            context=primary_ctx,
            labels=primary_input.labels,
            severity=primary_input.severity,
        )


NodeRegistry.register(CombinerNode)
