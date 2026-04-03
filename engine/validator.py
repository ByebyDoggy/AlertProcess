"""
规则链配置校验引擎

5 个校验维度:
1. 结构校验 - 单入口、无孤立节点、无环路
2. 端口校验 - 输入/输出端口连接合法性
3. 类型校验 - 数据流类型兼容性（严格约束）
4. 节点校验 - 节点配置是否合法
5. 拓扑校验 - 节点注册、执行顺序、终端节点
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from pydantic import BaseModel

from engine.parser import ParsedChain
from nodes.base import (
    ALLOWED_TYPE_MAPPING,
    CATEGORY_ALLOWED_INPUTS,
    NodeCategory,
    NodeRegistry,
)


class ValidationError(BaseModel):
    """校验错误"""
    node_id: str | None = None
    edge_id: str | None = None
    level: str = "error"          # error / warning
    field: str = ""
    message: str


class ChainValidator:
    """
    规则链配置校验引擎。

    校验流程: structure → ports → data_types → node_configs → topology
    """

    def validate(self, chain: ParsedChain) -> list[ValidationError]:
        errors: list[ValidationError] = []
        errors.extend(self._validate_structure(chain))
        errors.extend(self._validate_ports(chain))
        errors.extend(self._validate_data_types(chain))
        errors.extend(self._validate_node_configs(chain))
        errors.extend(self._validate_topology(chain))
        return errors

    # ------------------------------------------------------------------
    # 1. 结构校验
    # ------------------------------------------------------------------

    def _validate_structure(self, chain: ParsedChain) -> list[ValidationError]:
        errors: list[ValidationError] = []

        # 1.1 单入口
        triggers = [
            n for n in chain.nodes
            if self._get_category(n.node_type) == NodeCategory.INPUT
        ]
        if len(triggers) == 0:
            errors.append(ValidationError(
                level="error", field="structure",
                message="规则链必须包含至少一个 trigger 节点"
            ))
        elif len(triggers) > 1:
            errors.append(ValidationError(
                level="error", field="structure",
                message=f"规则链只能有一个 trigger 节点，当前有 {len(triggers)} 个",
                node_id=triggers[1].node_id,
            ))

        # 1.2 无孤立节点（从 trigger 可达）
        if chain.trigger_node:
            reachable = self._bfs(chain, chain.trigger_node.node_id)
            for node in chain.nodes:
                if node.node_id not in reachable:
                    # 豁免无输入端口的节点（如 trigger、constant_scorer），它们不需要上游输入
                    node_class = NodeRegistry.get(node.node_type)
                    if node_class and not node_class.get_inputs():
                        continue
                    errors.append(ValidationError(
                        level="error", field="structure",
                        message=f"节点 '{node.label or node.node_id}' 不可达（从 trigger 出发）",
                        node_id=node.node_id,
                    ))

        # 1.3 无效用节点（可达 action）
        action_nodes = {
            n.node_id for n in chain.nodes
            if self._get_category(n.node_type) == NodeCategory.ACTION
        }
        if chain.trigger_node and action_nodes:
            # 反向 BFS: 从 action 反向查找可达节点
            useful = set()
            queue = list(action_nodes)
            while queue:
                nid = queue.pop(0)
                if nid in useful:
                    continue
                useful.add(nid)
                for src in chain.reverse_adjacency.get(nid, []):
                    if src not in useful:
                        queue.append(src)
            for node in chain.nodes:
                if node.node_id not in useful:
                    errors.append(ValidationError(
                        level="warning", field="structure",
                        message=f"节点 '{node.label or node.node_id}' 无路径到达 action 节点",
                        node_id=node.node_id,
                    ))

        # 1.4 环路检测
        if self._has_cycle(chain):
            errors.append(ValidationError(
                level="error", field="structure",
                message="规则链存在环路（DAG 不允许环）"
            ))

        # 1.5 无重复边
        seen_edges: set[tuple[str, str, str, str]] = set()
        for edge in chain.edges:
            key = (edge.source_id, edge.source_port, edge.target_id, edge.target_port)
            if key in seen_edges:
                errors.append(ValidationError(
                    level="error", field="structure",
                    message="存在重复的边连接",
                    edge_id=edge.edge_id,
                ))
            seen_edges.add(key)

        return errors

    # ------------------------------------------------------------------
    # 2. 端口校验
    # ------------------------------------------------------------------

    def _validate_ports(self, chain: ParsedChain) -> list[ValidationError]:
        errors: list[ValidationError] = []
        node_id_set = {n.node_id for n in chain.nodes}

        for edge in chain.edges:
            # 2.1 边引用的节点必须存在
            if edge.source_id not in node_id_set:
                errors.append(ValidationError(
                    level="error", field="port",
                    message=f"源节点 '{edge.source_id}' 不存在",
                    edge_id=edge.edge_id,
                ))
                continue
            if edge.target_id not in node_id_set:
                errors.append(ValidationError(
                    level="error", field="port",
                    message=f"目标节点 '{edge.target_id}' 不存在",
                    edge_id=edge.edge_id,
                ))
                continue

            source_node = chain.get_node(edge.source_id)
            target_node = chain.get_node(edge.target_id)
            if not source_node or not target_node:
                continue

            source_class = NodeRegistry.get(source_node.node_type)
            target_class = NodeRegistry.get(target_node.node_type)
            if not source_class or not target_class:
                continue  # 节点类型注册问题由拓扑校验处理

            # 2.2 源端口必须存在
            source_ports = {p.key for p in source_class.get_outputs()}
            if edge.source_port not in source_ports:
                errors.append(ValidationError(
                    level="error", field="port",
                    message=f"源节点 '{source_node.label or source_node.node_id}' "
                            f"没有输出端口 '{edge.source_port}'",
                    node_id=source_node.node_id,
                    edge_id=edge.edge_id,
                ))

            # 2.3 目标端口必须存在
            target_ports = {p.key for p in target_class.get_inputs()}
            if edge.target_port not in target_ports:
                errors.append(ValidationError(
                    level="error", field="port",
                    message=f"目标节点 '{target_node.label or target_node.node_id}' "
                            f"没有输入端口 '{edge.target_port}'",
                    node_id=target_node.node_id,
                    edge_id=edge.edge_id,
                ))

        # 2.4 必需输入端口必须有连接
        for node in chain.nodes:
            node_class = NodeRegistry.get(node.node_type)
            if not node_class:
                continue
            connected_ports = {
                e.target_port for e in chain.get_incoming_edges(node.node_id)
            }
            for port in node_class.get_inputs():
                if port.required and port.key not in connected_ports:
                    errors.append(ValidationError(
                        level="error", field="port",
                        message=f"节点 '{node.label or node.node_id}' 的必需端口 "
                                f"'{port.label} ({port.key})' 未连接",
                        node_id=node.node_id,
                    ))

        # 2.5 非 multi 端口只允许一个连接
        port_connections: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        for edge in chain.edges:
            port_connections[edge.target_id][edge.target_port].append(edge)

        for node in chain.nodes:
            node_class = NodeRegistry.get(node.node_type)
            if not node_class:
                continue
            port_def_map = {p.key: p for p in node_class.get_inputs()}
            for port_key, edges in port_connections[node.node_id].items():
                port_def = port_def_map.get(port_key)
                if port_def and not port_def.multi and len(edges) > 1:
                    errors.append(ValidationError(
                        level="error", field="port",
                        message=f"节点 '{node.label or node.node_id}' 的端口 "
                                f"'{port_def.label} ({port_key})' 不允许多个连接",
                        node_id=node.node_id,
                    ))

        # 2.6 Action 节点不应有输出连接
        for node in chain.nodes:
            node_class = NodeRegistry.get(node.node_type)
            if not node_class:
                continue
            if node_class.category == NodeCategory.ACTION:
                outgoing = chain.get_outgoing_edges(node.node_id)
                if outgoing:
                    errors.append(ValidationError(
                        level="warning", field="port",
                        message=f"Action 节点 '{node.label or node.node_id}' "
                                f"不应有输出连接（终端节点）",
                        node_id=node.node_id,
                    ))

        return errors

    # ------------------------------------------------------------------
    # 3. 数据类型校验
    # ------------------------------------------------------------------

    def _validate_data_types(self, chain: ParsedChain) -> list[ValidationError]:
        errors: list[ValidationError] = []

        for edge in chain.edges:
            source_node = chain.get_node(edge.source_id)
            target_node = chain.get_node(edge.target_id)
            if not source_node or not target_node:
                continue

            source_class = NodeRegistry.get(source_node.node_type)
            target_class = NodeRegistry.get(target_node.node_type)
            if not source_class or not target_class:
                continue

            # 检查目标节点分类是否允许接收源端口的数据类型
            source_category = source_class.category
            target_category = target_class.category

            # 获取源端口定义
            source_port_def = None
            for p in source_class.get_outputs():
                if p.key == edge.source_port:
                    source_port_def = p
                    break
            if not source_port_def:
                continue

            source_data_type = source_port_def.data_type
            allowed_inputs = CATEGORY_ALLOWED_INPUTS.get(target_category, set())

            # "any" 类型的输出可以被任何目标接收
            # 检查源数据类型是否在目标的允许列表中
            if source_data_type not in allowed_inputs and source_data_type != "any":
                # 额外检查: 通过 ALLOWED_TYPE_MAPPING
                allowed_by_mapping = ALLOWED_TYPE_MAPPING.get(source_data_type, set())
                if not allowed_by_mapping.intersection(allowed_inputs) and "any" not in allowed_inputs:
                    errors.append(ValidationError(
                        level="error", field="data_type",
                        message=f"数据类型不兼容: '{source_node.label or source_node.node_id}' "
                                f"输出 '{source_data_type}' 不能连接到 "
                                f"'{target_node.label or target_node.node_id}' "
                                f"(类别: {target_category.value})",
                        node_id=target_node.node_id,
                        edge_id=edge.edge_id,
                    ))

        return errors

    # ------------------------------------------------------------------
    # 4. 节点配置校验
    # ------------------------------------------------------------------

    def _validate_node_configs(self, chain: ParsedChain) -> list[ValidationError]:
        errors: list[ValidationError] = []

        for node in chain.nodes:
            node_class = NodeRegistry.get(node.node_type)
            if not node_class:
                continue

            try:
                instance = node_class(node_id=node.node_id, config=node.config)
                config_errors = instance.validate_config(node.config)
                for err_msg in config_errors:
                    errors.append(ValidationError(
                        level="error", field="config",
                        message=f"节点 '{node.label or node.node_id}' 配置错误: {err_msg}",
                        node_id=node.node_id,
                    ))
            except Exception as exc:
                errors.append(ValidationError(
                    level="error", field="config",
                    message=f"节点 '{node.label or node.node_id}' 配置解析失败: {exc}",
                    node_id=node.node_id,
                ))

        return errors

    # ------------------------------------------------------------------
    # 5. 拓扑校验
    # ------------------------------------------------------------------

    def _validate_topology(self, chain: ParsedChain) -> list[ValidationError]:
        errors: list[ValidationError] = []

        # 5.1 所有节点类型必须在注册表中
        for node in chain.nodes:
            if not NodeRegistry.get(node.node_type):
                errors.append(ValidationError(
                    level="error", field="topology",
                    message=f"未知节点类型: '{node.node_type}'",
                    node_id=node.node_id,
                ))

        # 5.2 终端节点检查
        action_nodes = [
            n for n in chain.nodes
            if self._get_category(n.node_type) == NodeCategory.ACTION
        ]
        if not action_nodes:
            errors.append(ValidationError(
                level="warning", field="topology",
                message="规则链没有 action 节点，执行后不会产生实际效果"
            ))

        return errors

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _get_category(node_type: str) -> NodeCategory | None:
        """获取节点类型的分类"""
        cls = NodeRegistry.get(node_type)
        if cls:
            return cls.category
        return None

    @staticmethod
    def _bfs(chain: ParsedChain, start_id: str) -> set[str]:
        """BFS 遍历，返回从 start_id 可达的所有节点 ID"""
        visited: set[str] = set()
        queue = [start_id]
        while queue:
            nid = queue.pop(0)
            if nid in visited:
                continue
            visited.add(nid)
            for neighbor in chain.adjacency.get(nid, []):
                if neighbor not in visited:
                    queue.append(neighbor)
        return visited

    @staticmethod
    def _has_cycle(chain: ParsedChain) -> bool:
        """检测 DAG 是否有环（DFS 三色标记）"""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {n.node_id: WHITE for n in chain.nodes}

        def dfs(node_id: str) -> bool:
            color[node_id] = GRAY
            for neighbor in chain.adjacency.get(node_id, []):
                if color.get(neighbor, WHITE) == GRAY:
                    return True
                if color.get(neighbor, WHITE) == WHITE and dfs(neighbor):
                    return True
            color[node_id] = BLACK
            return False

        for node in chain.nodes:
            if color[node.node_id] == WHITE:
                if dfs(node.node_id):
                    return True
        return False
