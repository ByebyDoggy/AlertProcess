"""
规则链配置解析器

将前端提交的 JSON 配置（nodes + edges）解析为内部 DAG 结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nodes.base import NodeCategory, NodeRegistry


@dataclass
class ParsedNode:
    """解析后的节点"""
    node_id: str
    node_type: str               # NodeRegistry 中的 name
    label: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    position: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedEdge:
    """解析后的边"""
    edge_id: str = ""
    source_id: str = ""
    source_port: str = "output"  # 输出端口 key: "output" / "true" / "false"
    target_id: str = ""
    target_port: str = "input"   # 输入端口 key: "input" / "input_0" / "input_1" / ...


@dataclass
class ParsedChain:
    """解析后的完整规则链 DAG"""
    nodes: list[ParsedNode] = field(default_factory=list)
    edges: list[ParsedEdge] = field(default_factory=list)

    # 预计算的图结构
    _adjacency: dict[str, list[str]] | None = None
    _reverse_adjacency: dict[str, list[str]] | None = None
    _node_map: dict[str, ParsedNode] | None = None
    _trigger_node: ParsedNode | None = None

    @property
    def node_map(self) -> dict[str, ParsedNode]:
        if self._node_map is None:
            self._node_map = {n.node_id: n for n in self.nodes}
        return self._node_map

    @property
    def trigger_node(self) -> ParsedNode | None:
        if self._trigger_node is None:
            for node in self.nodes:
                node_class = NodeRegistry.get(node.node_type)
                if node_class and node_class.category == NodeCategory.INPUT:
                    self._trigger_node = node
                    break
        return self._trigger_node

    @property
    def adjacency(self) -> dict[str, list[str]]:
        """node_id -> [target_node_ids]"""
        if self._adjacency is None:
            adj: dict[str, list[str]] = {n.node_id: [] for n in self.nodes}
            for edge in self.edges:
                adj.setdefault(edge.source_id, []).append(edge.target_id)
            self._adjacency = adj
        return self._adjacency

    @property
    def reverse_adjacency(self) -> dict[str, list[str]]:
        """node_id -> [source_node_ids]"""
        if self._reverse_adjacency is None:
            radj: dict[str, list[str]] = {n.node_id: [] for n in self.nodes}
            for edge in self.edges:
                radj.setdefault(edge.target_id, []).append(edge.source_id)
            self._reverse_adjacency = radj
        return self._reverse_adjacency

    def get_outgoing_edges(self, node_id: str) -> list[ParsedEdge]:
        """获取节点的所有出边"""
        return [e for e in self.edges if e.source_id == node_id]

    def get_incoming_edges(self, node_id: str) -> list[ParsedEdge]:
        """获取节点的所有入边"""
        return [e for e in self.edges if e.target_id == node_id]

    def get_edges_by_source_port(self, node_id: str, source_port: str) -> list[ParsedEdge]:
        """获取节点指定输出端口的出边"""
        return [
            e for e in self.edges
            if e.source_id == node_id and e.source_port == source_port
        ]

    def get_node(self, node_id: str) -> ParsedNode | None:
        return self.node_map.get(node_id)


class ChainParser:
    """
    规则链配置解析器。

    将前端拖拽式 JSON 配置解析为 ParsedChain（内部 DAG）。
    """

    @staticmethod
    def parse(config: dict[str, Any]) -> ParsedChain:
        """
        解析前端 JSON 配置。

        Args:
            config: 前端配置，包含 nodes 和 edges 列表

        Returns:
            ParsedChain 实例
        """
        raw_nodes = config.get("nodes", [])
        raw_edges = config.get("edges", [])

        parsed_nodes = []
        for raw in raw_nodes:
            parsed_nodes.append(ParsedNode(
                node_id=raw.get("id", raw.get("nodeId", "")),
                node_type=raw.get("type", raw.get("nodeType", "")),
                label=raw.get("label", ""),
                config=raw.get("config", raw.get("data", {})),
                position=raw.get("position", raw.get("pos", {})),
            ))

        parsed_edges = []
        for raw in raw_edges:
            parsed_edges.append(ParsedEdge(
                edge_id=raw.get("id", raw.get("edgeId", "")),
                source_id=raw.get("source", raw.get("sourceNodeId", "")),
                source_port=raw.get("sourcePort", raw.get("sourceHandle", "output")),
                target_id=raw.get("target", raw.get("targetNodeId", "")),
                target_port=raw.get("targetPort", raw.get("targetHandle", "input")),
            ))

        return ParsedChain(nodes=parsed_nodes, edges=parsed_edges)

    @staticmethod
    def to_dict(chain: ParsedChain) -> dict[str, Any]:
        """将 ParsedChain 序列化为字典（用于存储到数据库）"""
        return {
            "nodes": [
                {
                    "id": n.node_id,
                    "type": n.node_type,
                    "label": n.label,
                    "config": n.config,
                    "position": n.position,
                }
                for n in chain.nodes
            ],
            "edges": [
                {
                    "id": e.edge_id,
                    "source": e.source_id,
                    "sourcePort": e.source_port,
                    "target": e.target_id,
                    "targetPort": e.target_port,
                }
                for e in chain.edges
            ],
        }
