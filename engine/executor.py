"""
规则链异步执行引擎

执行策略:
- 拓扑排序确定执行顺序
- 分层: 同层（无依赖关系）的节点 asyncio.gather 并发执行
- 根据输出端口（true/false）决定下游路径
- 全链路 async/await，不阻塞事件循环
- ContextProvider 现在作为节点存在，无需 @require 装饰器注入
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any

from engine.context import ExecutionContext, ExecutionLogEntry
from engine.parser import ParsedChain, ParsedEdge
from engine.validator import ChainValidator, ValidationError
from nodes.base import BaseNode, NodeOutput, NodeRegistry

logger = logging.getLogger(__name__)


class ChainExecutor:
    """
    规则链异步执行引擎。
    """

    def __init__(self) -> None:
        self._validator = ChainValidator()

    async def execute(
        self,
        chain: ParsedChain,
        alert_data: dict[str, Any],
        dry_run: bool = False,
    ) -> ExecutionContext:
        """
        异步执行完整规则链。

        Args:
            chain: 解析后的规则链 DAG
            alert_data: 原始告警数据
            dry_run: 是否为测试运行模式（Action 节点仅模拟）

        Returns:
            ExecutionContext 包含所有节点输出、日志和聚合结果
        """
        ctx = ExecutionContext(alert_data=alert_data, dry_run=dry_run)

        # ── 注入记忆上下文 ──
        # 从全局 MemoryStore 读取所有记忆，注入到 alert_data
        try:
            from nodes.memory.store import get_memory_store
            mem_store = get_memory_store()
            mem_context = mem_store.retrieve_all_merged()
            if mem_context:
                ctx.alert_data.update(mem_context)
                logger.debug(
                    f"[ChainExecutor] Injected {len(mem_context)} memory fields "
                    f"into alert_data"
                )
        except Exception as e:
            logger.warning(f"[ChainExecutor] Memory injection failed: {e}")

        # 1. 校验规则链
        validation_errors = self._validator.validate(chain)
        critical_errors = [e for e in validation_errors if e.level == "error"]
        if critical_errors:
            for err in critical_errors:
                ctx.add_error(f"[校验] {err.message}")
            return ctx

        # 2. 分层拓扑排序
        layers = self._topological_layers(chain)
        if not layers:
            ctx.add_error("无法进行拓扑排序（可能存在环路）")
            return ctx

        # 3. 逐层并发执行
        for layer in layers:
            # Dry-run 模式下注入标记
            if dry_run:
                ctx.alert_data["__dry_run__"] = True
            await self._execute_layer(layer, chain, ctx)
            # 如果有错误且不需要继续，可以提前终止
            # 当前设计: 即使某个节点失败，其他独立节点仍继续执行

        return ctx

    async def _execute_layer(
        self,
        layer: list[str],
        chain: ParsedChain,
        ctx: ExecutionContext,
    ) -> None:
        """并发执行同层节点"""
        tasks = [
            asyncio.create_task(self._execute_node(node_id, chain, ctx))
            for node_id in layer
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for node_id, result in zip(layer, results):
            if isinstance(result, Exception):
                ctx.add_error(f"节点 '{node_id}' 执行失败: {result}")

    async def _execute_node(
        self,
        node_id: str,
        chain: ParsedChain,
        ctx: ExecutionContext,
    ) -> None:
        """执行单个节点"""
        node_def = chain.get_node(node_id)
        if not node_def:
            ctx.add_error(f"节点 '{node_id}' 未找到定义")
            return

        # 实例化节点
        try:
            node = NodeRegistry.create(
                node_def.node_type,
                node_id=node_id,
                config=node_def.config,
            )
        except ValueError as e:
            ctx.add_error(f"节点 '{node_id}' 实例化失败: {e}")
            return

        # 收集输入
        inputs = self._collect_inputs(node_id, chain, ctx)

        # 检查是否应该执行此节点（基于上游端口路由）
        if not self._should_execute(node_id, chain, ctx):
            return

        # 执行
        start_time = time.monotonic()
        try:
            output = await node.execute(ctx.alert_data, inputs)
            duration_ms = (time.monotonic() - start_time) * 1000

            ctx.set_output(node_id, output)
            ctx.add_log(ExecutionLogEntry(
                node_id=node_id,
                node_type=node_def.node_type,
                score=output.score,
                passed=output.passed,
                duration_ms=duration_ms,
            ))

            # 如果是 Action 节点，记录动作执行
            if node.category.value == "action":
                ctx.actions_executed.append({
                    "node_id": node_id,
                    "node_type": node_def.node_type,
                    "passed": output.passed,
                    "result": output.context.get("action_result", {}),
                })

        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            ctx.add_log(ExecutionLogEntry(
                node_id=node_id,
                node_type=node_def.node_type,
                score=0,
                passed=False,
                duration_ms=duration_ms,
                error=str(e),
            ))
            ctx.add_error(f"节点 '{node_id}' 执行异常: {e}")

    def _collect_inputs(
        self,
        node_id: str,
        chain: ParsedChain,
        ctx: ExecutionContext,
    ) -> dict[str, list[NodeOutput]]:
        """
        收集指定节点的所有输入。

        如果 edge 上配置了 input_transformer，会对上游输出应用变换。
        变换作用于 NodeOutput.context 字段，替换为表达式求值结果。

        Returns:
            { target_port_key: [NodeOutput, ...] }
        """
        inputs: dict[str, list[NodeOutput]] = defaultdict(list)
        incoming_edges = chain.get_incoming_edges(node_id)

        for edge in incoming_edges:
            source_output = ctx.get_output(edge.source_id)
            if source_output is not None:
                # 应用 input_transformer（如果配置了）
                transformed_output = self._apply_transformer(
                    source_output, edge.input_transformer
                )
                inputs[edge.target_port].append(transformed_output)

        return dict(inputs)

    def _apply_transformer(
        self,
        output: NodeOutput,
        transformer: dict[str, Any] | None,
    ) -> NodeOutput:
        """
        对上游输出应用 input_transformer 变换。

        transformer 格式: {"expression": "...", "language": "python"|"javascript"}
        如果 transformer 为 None 或表达式为空，返回原始输出。

        变换以 output 的完整数据（score/passed/severity/labels + context）作为 input，
        表达式返回的新字典替换 output.context。
        """
        if not transformer:
            return output

        expression = transformer.get("expression", "")
        language = transformer.get("language", "python")

        if not expression or not expression.strip():
            return output

        try:
            from engine.transformer import InputTransformer
            # 构建完整的 input 数据：顶层字段 + context 合并
            # 这样用户可以在表达式中访问 input.score, input.passed, input.xxx 等
            input_data = {
                "score": output.score,
                "passed": output.passed,
                "severity": output.severity,
                "labels": output.labels,
                **output.context,
            }
            transformed_context = InputTransformer.evaluate(
                expression=expression,
                language=language,
                input_data=input_data,
            )
            # 构造新的 NodeOutput，用变换后的 context 替换原始的
            return NodeOutput(
                node_id=output.node_id,
                node_type=output.node_type,
                score=output.score,
                passed=output.passed,
                context=transformed_context,
                labels=output.labels,
                severity=output.severity,
            )
        except Exception as e:
            logger.warning(
                "[ChainExecutor] input_transformer failed on edge from '%s': %s",
                output.node_id, e,
            )
            # 变换失败时返回原始输出（不阻断链路执行）
            return output

    def _should_execute(
        self,
        node_id: str,
        chain: ParsedChain,
        ctx: ExecutionContext,
    ) -> bool:
        """
        判断节点是否应该执行。

        对于通过 true/false 端口连接的边:
        - true 端口: 上游 passed=True 时才执行下游
        - false 端口: 上游 passed=False 时才执行下游

        如果上游节点设置了 early_stop=True，则阻止所有下游执行。
        例外: MEMORY 类别节点不受 early_stop 影响（记忆读取等应独立于单次交易状态）。
        """
        incoming_edges = chain.get_incoming_edges(node_id)
        if not incoming_edges:
            return True

        # MEMORY 类别节点跳过 early_stop 检查（如 MemoryRecall 无输入端口时也需正常输出）
        node_def = chain.get_node(node_id)
        is_memory_node = False
        if node_def and node_def.node_type:
            from nodes.base import NodeRegistry as NR
            node_cls = NR.get(node_def.node_type)
            if node_cls and hasattr(node_cls, "category"):
                from nodes.base import NodeCategory
                is_memory_node = (node_cls.category == NodeCategory.MEMORY)

        # 检查是否有上游节点触发了 early_stop（MEMORY 节点跳过此检查）
        if not is_memory_node:
            for edge in incoming_edges:
                source_output = ctx.get_output(edge.source_id)
                if source_output is not None and getattr(source_output, "early_stop", False):
                    # 上游节点提前停止，阻止下游执行（Memory 除外）
                    return False

        for edge in incoming_edges:
            source_output = ctx.get_output(edge.source_id)
            if source_output is None:
                # 上游未执行，此节点也不执行
                continue

            if edge.source_port == "true" and not source_output.passed:
                return False
            if edge.source_port == "false" and source_output.passed:
                return False

        # 检查是否有任何上游已成功连接到此节点
        for edge in incoming_edges:
            source_output = ctx.get_output(edge.source_id)
            if source_output is not None:
                return True

        return False

    # ------------------------------------------------------------------
    # 拓扑排序辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _topological_layers(chain: ParsedChain) -> list[list[str]]:
        """
        Kahn 算法分层拓扑排序。

        Returns:
            分层列表，每层为可并发执行的节点 ID 列表
        """
        # 计算入度
        in_degree: dict[str, int] = {n.node_id: 0 for n in chain.nodes}
        for edge in chain.edges:
            if edge.target_id in in_degree:
                in_degree[edge.target_id] += 1

        # 找入度为 0 的节点
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        layers: list[list[str]] = []
        visited: set[str] = set()

        while queue:
            layer = sorted(queue)  # 排序保证确定性
            layers.append(layer)
            visited.update(layer)
            queue = []

            # 遍历当前层的所有出边
            for nid in layer:
                for edge in chain.get_outgoing_edges(nid):
                    if edge.target_id not in visited:
                        in_degree[edge.target_id] -= 1
                        if in_degree[edge.target_id] == 0:
                            queue.append(edge.target_id)

        # 检查是否所有节点都被访问（有环则未全部访问）
        all_ids = {n.node_id for n in chain.nodes}
        if visited != all_ids:
            return []  # 有环

        return layers
