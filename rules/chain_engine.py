"""
Rule Chain Engine - 将前端拖拽式 nodes/edges 转换为可执行的检测流水线
"""
from __future__ import annotations
import json
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from models import AlertInput, DetectionResult, TransactionContext, SeverityEnum
from detectors.base import DetectorRegistry
from rules.engine import ConditionEvaluator


# ──────────────── 数据模型 ────────────────

class NodeType(str, Enum):
    TRIGGER = "trigger"
    DETECTOR = "detector"
    CONDITION = "condition"
    FILTER = "filter"
    ACTION = "action"
    SCORER = "scorer"
    NOTIFIER = "notifier"


class ChainNode(BaseModel):
    id: str
    type: str
    label: str = ""
    config: dict = Field(default_factory=dict)
    position: dict = Field(default_factory=lambda: {"x": 0, "y": 0})


class ChainEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str = ""
    condition: Optional[dict] = None


class ChainConfig(BaseModel):
    """规则链完整配置"""
    name: str
    description: str = ""
    enabled: bool = True
    nodes: list[ChainNode] = []
    edges: list[ChainEdge] = []


class NodeResult(BaseModel):
    node_id: str
    success: bool
    detected: bool = False
    output: Any = None
    metadata: dict = Field(default_factory=dict)
    error: Optional[str] = None


class ChainResult(BaseModel):
    success: bool
    chain_name: str
    path: list[str] = []          # 执行路径 (node IDs)
    detections: list[NodeResult] = []
    actions: list[NodeResult] = []
    severity: Optional[str] = None
    score: float = 0.0
    tags: list[str] = []
    errors: list[str] = []


# ──────────────── 链解析器 ────────────────

class ChainParser:
    """
    将前端 nodes/edges 图结构解析为可执行的 DAG
    
    前端概念 -> 后端执行映射:
    
    Node Types:
      trigger    -> 入口节点, 不执行逻辑
      detector   -> DetectorRegistry.get(name).detect()
      condition  -> ConditionEvaluator.evaluate_condition()
      filter     -> 条件过滤 (布尔表达式)
      action     -> 修改 severity/tags/score
      scorer     -> 计算风险评分
      notifier   -> 发送通知
    
    Edge Labels:
      (空/默认)  -> 顺序执行
      "true"     -> 条件为真时走此边
      "false"    -> 条件为假时走此边
      自定义     -> 自定义分支标签
    """
    
    @classmethod
    def get_detector_map(cls) -> dict[str, str]:
        """动态构建 前端 type_key -> detector name 映射"""
        from detectors.base import DetectorRegistry
        return DetectorRegistry.build_detector_type_map()
    
    def __init__(self, chain_config: ChainConfig):
        self.config = chain_config
        self.nodes_map: dict[str, ChainNode] = {n.id: n for n in chain_config.nodes}
        self.adj: dict[str, list[tuple[str, ChainEdge]]] = {}  # node_id -> [(target_id, edge)]
        self.reverse_adj: dict[str, list[str]] = {}
        self._build_graph()
    
    def _build_graph(self):
        for node in self.config.nodes:
            self.adj.setdefault(node.id, [])
            self.reverse_adj.setdefault(node.id, [])
        for edge in self.config.edges:
            self.adj.setdefault(edge.source, []).append((edge.target, edge))
            self.reverse_adj.setdefault(edge.target, []).append(edge.source)
    
    def find_trigger(self) -> Optional[ChainNode]:
        """找到入口触发器节点"""
        # 优先找 type=trigger 且无入边的节点
        for node in self.config.nodes:
            if node.type == NodeType.TRIGGER:
                return node
        # 没有显式 trigger 则找无入边的第一个节点
        for node in self.config.nodes:
            if not self.reverse_adj.get(node.id):
                return node
        return self.config.nodes[0] if self.config.nodes else None
    
    def get_next_nodes(self, node_id: str, node_result: NodeResult) -> list[str]:
        """
        根据当前节点执行结果, 决定走哪些边
        
        - condition 节点: 根据检测结果选择 "true"/"false" 边
        - detector 节点: detected=True 走 "true"/默认边, detected=False 走 "false" 边
        - 其他节点: 走所有出边
        """
        edges = self.adj.get(node_id, [])
        if not edges:
            return []
        
        node = self.nodes_map.get(node_id)
        if not node:
            return [t for t, _ in edges]
        
        # condition 节点: 按标签分支
        if node.type == NodeType.CONDITION:
            result_value = node_result.detected or node_result.success
            label = "true" if result_value else "false"
            for target_id, edge in edges:
                if edge.label.lower() == label:
                    return [target_id]
            # 没有匹配标签的边, 走无标签边
            unlabeled = [t for t, e in edges if not e.label]
            return unlabeled if unlabeled else [t for t, _ in edges]
        
        # detector 节点: 类似条件分支
        if node.type == NodeType.DETECTOR:
            if node_result.detected:
                # 优先走 "true" 标签边
                for target_id, edge in edges:
                    if edge.label.lower() == "true":
                        return [target_id]
            else:
                for target_id, edge in edges:
                    if edge.label.lower() == "false":
                        return [target_id]
        
        # filter 节点: 通过则继续, 不通过则终止
        if node.type == NodeType.FILTER:
            if node_result.detected:
                return [t for t, _ in edges]
            return []  # 终止当前分支
        
        # 其他节点: 走所有出边
        return [t for t, _ in edges]
    
    def validate(self) -> tuple[bool, list[str]]:
        """验证规则链配置是否合法"""
        errors = []
        node_ids = set(self.nodes_map.keys())
        
        # 1. 至少有一个节点
        if not self.config.nodes:
            errors.append("规则链至少需要一个节点")
            return False, errors
        
        # 2. 有且仅有一个入口
        triggers = [n for n in self.config.nodes if n.type == NodeType.TRIGGER]
        if len(triggers) > 1:
            errors.append(f"只能有一个触发器节点, 当前有 {len(triggers)} 个")
        
        # 3. 检查边的 source/target 都存在
        for edge in self.config.edges:
            if edge.source not in node_ids:
                errors.append(f"边 '{edge.id}' 的源节点 '{edge.source}' 不存在")
            if edge.target not in node_ids:
                errors.append(f"边 '{edge.id}' 的目标节点 '{edge.target}' 不存在")
        
        # 4. 检测器类型是否有效
        for node in self.config.nodes:
            if node.type == NodeType.DETECTOR:
                dtype = node.config.get("detectorType", "")
                if dtype and dtype not in self.get_detector_map():
                    errors.append(f"检测器类型 '{dtype}' 不支持")
        
        # 5. 检查环路 (简单 DFS)
        visited = set()
        stack = set()
        def has_cycle(nid):
            if nid in stack:
                return True
            if nid in visited:
                return False
            visited.add(nid)
            stack.add(nid)
            for tid, _ in self.adj.get(nid, []):
                if has_cycle(tid):
                    return True
            stack.remove(nid)
            return False
        
        for nid in node_ids:
            if has_cycle(nid):
                errors.append("规则链中存在环路")
                break
        
        return len(errors) == 0, errors
    
    def to_rule_config(self) -> dict:
        """
        将链配置转换为可读的规则描述 (用于展示/文档)
        返回结构化的规则树
        """
        trigger = self.find_trigger()
        if not trigger:
            return {"error": "No trigger node"}
        
        def describe_node(node: ChainNode) -> dict:
            desc = {"id": node.id, "type": node.type, "label": node.label}
            if node.type == NodeType.DETECTOR:
                desc["detector"] = self.get_detector_map().get(
                    node.config.get("detectorType", ""), "unknown"
                )
            elif node.type == NodeType.CONDITION:
                desc["condition"] = {
                    "field": node.config.get("field", ""),
                    "operator": node.config.get("operator", ""),
                    "value": node.config.get("value", ""),
                }
            elif node.type == NodeType.ACTION:
                desc["action"] = {
                    "type": node.config.get("actionType", ""),
                    "value": node.config.get("actionValue", ""),
                }
            return desc
        
        def build_tree(nid: str, visited: set) -> dict:
            if nid in visited:
                return {"id": nid, "type": "cycle_ref"}
            visited.add(nid)
            
            node = self.nodes_map[nid]
            tree = describe_node(node)
            children = []
            for tid, edge in self.adj.get(nid, []):
                child = build_tree(tid, set(visited))
                child["edge_label"] = edge.label or "(default)"
                children.append(child)
            if children:
                tree["next"] = children
            return tree
        
        return {
            "chain_name": self.config.name,
            "trigger": describe_node(trigger),
            "tree": build_tree(trigger.id, set()),
        }


# ──────────────── 链执行器 ────────────────

class ChainExecutor:
    """
    执行解析后的规则链
    
    按拓扑顺序执行节点, 支持:
    - 检测器节点: 调用对应检测器
    - 条件节点: 评估条件, 选择分支
    - 动作节点: 设置 severity/tags
    - 评分节点: 计算风险分数
    - 通知节点: 发送通知
    """
    
    def __init__(self, chain_config: ChainConfig):
        self.parser = ChainParser(chain_config)
        self.config = chain_config
    
    async def execute(
        self,
        alert: AlertInput,
        context: TransactionContext,
    ) -> ChainResult:
        """
        执行完整规则链
        
        Args:
            alert: 告警输入
            context: 交易上下文
        
        Returns:
            ChainResult: 执行结果
        """
        # 验证链配置
        valid, errors = self.parser.validate()
        if not valid:
            return ChainResult(
                success=False, chain_name=self.config.name, errors=errors
            )
        
        result = ChainResult(success=True, chain_name=self.config.name)
        
        # 获取入口节点
        trigger = self.parser.find_trigger()
        if not trigger:
            return ChainResult(
                success=False, chain_name=self.config.name,
                errors=["未找到触发器节点"]
            )
        
        # BFS 执行
        queue = [trigger.id]
        visited = set()
        detections_map: dict[str, DetectionResult] = {}
        all_detections: list[DetectionResult] = []
        current_severity: Optional[str] = None
        current_tags: list[str] = []
        current_score: float = 0.0
        
        while queue and queue[0] not in visited:
            node_id = queue.pop(0)
            if node_id in visited:
                continue
            visited.add(node_id)
            
            node = self.parser.nodes_map.get(node_id)
            if not node:
                continue
            
            result.path.append(node_id)
            
            # 跳过 trigger 节点
            if node.type == NodeType.TRIGGER:
                next_nodes = self.parser.get_next_nodes(
                    node_id, NodeResult(node_id=node_id, success=True)
                )
                queue.extend(n for n in next_nodes if n not in visited)
                continue
            
            # 执行节点
            node_result = await self._execute_node(node, alert, context, all_detections)
            
            # 收集结果
            if node.type == NodeType.DETECTOR and node_result.output:
                if isinstance(node_result.output, DetectionResult):
                    detections_map[node_id] = node_result.output
                    all_detections.append(node_result.output)
                result.detections.append(node_result)
            
            elif node.type == NodeType.ACTION:
                result.actions.append(node_result)
                # 应用 action
                action_type = node.config.get("actionType", "")
                action_value = node.config.get("actionValue", "")
                if action_type == "set_severity" and action_value:
                    current_severity = action_value
                elif action_type == "add_tag" and action_value:
                    if action_value not in current_tags:
                        current_tags.append(action_value)
                elif action_type == "set_score":
                    try:
                        current_score = float(action_value)
                    except (ValueError, TypeError):
                        pass
            
            elif node.type == NodeType.CONDITION:
                node_result.detected = bool(node_result.success)
            
            elif node.type == NodeType.FILTER:
                node_result.detected = node_result.success
            
            # 记录错误
            if node_result.error:
                result.errors.append(f"[{node.label or node.id}] {node_result.error}")
            
            # 决定下一个节点
            next_nodes = self.parser.get_next_nodes(node_id, node_result)
            queue.extend(n for n in next_nodes if n not in visited)
        
        # 汇总结果
        result.severity = current_severity
        result.tags = current_tags
        result.score = current_score
        if result.errors:
            result.success = False
        
        return result
    
    async def _execute_node(
        self,
        node: ChainNode,
        alert: AlertInput,
        context: TransactionContext,
        all_detections: list[DetectionResult],
    ) -> NodeResult:
        """执行单个节点"""
        try:
            if node.type == NodeType.DETECTOR:
                return await self._exec_detector(node, alert, context)
            elif node.type == NodeType.CONDITION:
                return self._exec_condition(node, context, all_detections)
            elif node.type == NodeType.FILTER:
                return self._exec_filter(node, context, all_detections)
            elif node.type == NodeType.SCORER:
                return self._exec_scorer(node, context, all_detections)
            elif node.type == NodeType.NOTIFIER:
                return self._exec_notifier(node)
            elif node.type == NodeType.ACTION:
                return self._exec_action(node)
            else:
                return NodeResult(node_id=node.id, success=True)
        except Exception as e:
            return NodeResult(node_id=node.id, success=False, error=str(e))
    
    async def _exec_detector(
        self, node: ChainNode, alert: AlertInput, context: TransactionContext
    ) -> NodeResult:
        detector_type = node.config.get("detectorType", "flash_loan")
        detector_name = ChainParser.get_detector_map().get(detector_type, "")
        
        detector = DetectorRegistry.get(detector_name)
        if not detector:
            return NodeResult(
                node_id=node.id, success=False,
                error=f"检测器 '{detector_name}' 未注册"
            )
        
        detection = await detector.detect(alert, context)
        return NodeResult(
            node_id=node.id,
            success=True,
            detected=detection.detected,
            output=detection,
            metadata={"detector_name": detector_name, "detected": detection.detected}
        )
    
    def _exec_condition(
        self, node: ChainNode, context: TransactionContext, detections: list[DetectionResult]
    ) -> NodeResult:
        condition = {
            "field": node.config.get("field", ""),
            "operator": node.config.get("operator", "equals"),
            "value": node.config.get("value"),
        }
        result, matched = ConditionEvaluator.evaluate_condition(
            condition, context, detections, {}
        )
        return NodeResult(
            node_id=node.id, success=result, detected=result,
            metadata={"condition": condition, "matched": matched}
        )
    
    def _exec_filter(
        self, node: ChainNode, context: TransactionContext, detections: list[DetectionResult]
    ) -> NodeResult:
        expression = node.config.get("expression", "")
        # 将 expression 作为 condition field 直接评估
        # 前端传来的 expression 格式: "detector.flash_loan_detector" (简单字段检查)
        field = expression.strip()
        value = None
        if "." in field:
            parts = field.split(".", 1)
            if parts[0] == "detector" or parts[0] == "detection":
                det_name = parts[1].split(".")[0]
                for d in detections:
                    if d.detector_name == det_name:
                        value = d.detected
                        break
        
        passed = bool(value) if value is not None else False
        return NodeResult(
            node_id=node.id, success=passed, detected=passed,
            metadata={"expression": expression, "passed": passed}
        )
    
    def _exec_scorer(
        self, node: ChainNode, context: TransactionContext, detections: list[DetectionResult]
    ) -> NodeResult:
        weights = node.config.get("weights", {})
        severity_w = weights.get("severity", 1)
        detector_w = weights.get("detector", 1)
        
        # 简单评分: 每个检测到的告警 +50, 乘以权重
        detected_count = sum(1 for d in detections if d.detected)
        score = detected_count * 50 * severity_w * detector_w
        score = min(100.0, max(0.0, score))
        
        return NodeResult(
            node_id=node.id, success=True,
            output={"score": score},
            metadata={"score": score, "detected_count": detected_count}
        )
    
    def _exec_notifier(self, node: ChainNode) -> NodeResult:
        # 通知节点仅标记, 实际发送由外层处理
        notifier_type = node.config.get("notifierType", "webhook")
        target = node.config.get("targetUrl", "")
        return NodeResult(
            node_id=node.id, success=True,
            metadata={"notifier_type": notifier_type, "target": target}
        )
    
    def _exec_action(self, node: ChainNode) -> NodeResult:
        return NodeResult(
            node_id=node.id, success=True,
            metadata={"action_type": node.config.get("actionType", "")}
        )


# ──────────────── 链管理器 ────────────────

class ChainRegistry:
    """管理所有已加载的规则链"""
    
    _chains: dict[str, ChainExecutor] = {}
    
    @classmethod
    def load(cls, chain_config: ChainConfig, chain_id: str = ""):
        """加载一条规则链"""
        cid = chain_id or chain_config.name
        cls._chains[cid] = ChainExecutor(chain_config)
    
    @classmethod
    def unload(cls, chain_id: str):
        """卸载规则链"""
        cls._chains.pop(chain_id, None)
    
    @classmethod
    def get(cls, chain_id: str) -> Optional[ChainExecutor]:
        return cls._chains.get(chain_id)
    
    @classmethod
    def list_chains(cls) -> list[str]:
        return list(cls._chains.keys())
    
    @classmethod
    def clear(cls):
        cls._chains.clear()
