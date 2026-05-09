"""
检测器基类

所有检测器节点继承此基类。检测器接收 context 输入，输出 0-100 风险评分。
Detector 有两个输出端口: context (输出 TransactionContext) 和 detection (输出 DetectorResult)。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from nodes.base import (
    BaseNode,
    NodeCategory,
    NodeOutput,
    PortDef,
    score_to_severity,
)
from nodes.models import TransactionContext, DetectorResult


# ---------------------------------------------------------------------------
# Pydantic Mixin 类（模块级定义，供子类继承扩展）
# ---------------------------------------------------------------------------

class DetectorConfigMixin(BaseModel):
    """检测器通用配置 Mixin — threshold 为所有检测器共享的通用配置字段"""
    threshold: float = Field(default=50.0, ge=0, le=100, description="0-100，评分达到此值视为 passed")


class DetectorInputMixin(TransactionContext):
    """检测器通用输入 — TransactionContext（数据传输基础模型）"""
    context: dict[str, Any] = Field(default_factory=dict, description="交易上下文字段")

    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        schema = super().model_json_schema(*args, **kwargs)
        schema.setdefault("properties", {})["context"] = {
            "type": "object",
            "description": "交易上下文字段",
        }
        return schema


class DetectorOutputMixin(BaseModel):
    """检测器通用输出 Mixin"""
    score: float = Field(ge=0, le=100, description="0-100 风险评分")
    passed: bool = Field(description="评分是否 >= 配置的阈值")
    severity: str = Field(description="UNKNOWN/LOW/MEDIUM/HIGH/CRITICAL")
    labels: list[str] = Field(default_factory=list, description="命中的检测标签列表")
    detection: dict[str, Any] = Field(default_factory=dict, description="各检测器特有的检测结果数据")
    logs: list[str] = Field(default_factory=list, description="评分原因日志，记录各评分步骤的判定依据")


# ---------------------------------------------------------------------------
# BaseDetector — 检测器节点基类
# ---------------------------------------------------------------------------

class BaseDetector(BaseNode):
    """
    检测器基类。

    Detector 有两个输出端口:
    - "context": 输出 TransactionContext（数据传输基础模型）
    - "detection": 输出 DetectorResult（检测结果）

    通用配置 (ConfigModel 基类: DetectorConfigMixin):
      threshold: 0-100，评分达到此值视为 passed（所有检测器共享此字段）

    输入: 单端口 "input"，接收 TransactionContext（数据传输基础模型）
    """

    category: NodeCategory = NodeCategory.DETECTION

    # ── Pydantic 配置模型 (子类覆盖时继承 DetectorConfigMixin) ──
    ConfigModel: type[BaseModel] | None = None

    # ── 多端口模型声明 ──
    # 输入: 单端口 "input"，接收 TransactionContext
    InputModel: type[BaseModel] = DetectorInputMixin

    # 输出: 双端口 — context(端口0) 输出 TransactionContext，detection(端口1) 输出 DetectorResult
    OutputModels: list[type[BaseModel]] | None = None
    OutputModel: type[BaseModel] = DetectorOutputMixin

    @classmethod
    def get_inputs(cls) -> list[PortDef]:
        return [
            PortDef(key="input", label="输入", data_type="context", required=True),
            PortDef(key="storage_input", label="外部存储", data_type="context", required=False),
        ]

    @classmethod
    def get_outputs(cls) -> list[PortDef]:
        # 双输出端口: context + detection
        return [
            PortDef(key="context", label="上下文", data_type="context"),
            PortDef(key="detection", label="检测结果", data_type="detection_output"),
        ]

    @classmethod
    def get_output_schemas(cls) -> list[dict[str, Any]]:
        return [TransactionContext.model_json_schema(), DetectorResult.model_json_schema()]

    @classmethod
    def get_output_schema(cls) -> dict[str, Any]:
        return cls.OutputModel.model_json_schema()

    async def execute(
        self,
        context: dict[str, Any],
        inputs: dict[str, list[NodeOutput]],
    ) -> NodeOutput:
        upstream = self._first_input(inputs)

        # 合并上下文
        if upstream:
            merged_context = {**context, **upstream.context}
        else:
            merged_context = dict(context)

        # 合并外部存储缓存字典
        storage_inputs = inputs.get("storage_input")
        if storage_inputs:
            cache_dict = storage_inputs[0].context.get("_cache_dict")
            if cache_dict:
                merged_context["_cache_dict"] = cache_dict

        # 构建 TransactionContext
        tx_context = TransactionContext.from_dict(merged_context)

        # 调用子类 process
        output = await self.process(tx_context)

        score = max(0.0, min(100.0, output.score))
        threshold = self.config.get("threshold", 50.0)
        passed = score >= threshold

        # 输出 context 中包含完整的 TransactionContext（包含 detection）
        return NodeOutput(
            node_id=self.node_id,
            node_type=self.category.value,
            score=score,
            passed=passed,
            context={**tx_context.to_dict(), "detection": output.detection},
            labels=output.labels,
            severity=output.severity,
            logs=output.logs,
        )

    async def process(self, tx_context: TransactionContext) -> DetectorOutputMixin:
        """
        执行检测逻辑（子类实现）。

        Args:
            tx_context: TransactionContext（数据传输基础模型）

        Returns:
            检测器输出模型（score, passed, severity, labels, detection）
        """
        raise NotImplementedError(f"{self.__class__.__name__}.process() not implemented")

    # ── Provider 数据读取辅助方法 ──

    def get_parsed_transfers(self, tx_context: TransactionContext) -> list[dict[str, Any]]:
        """
        从 context 中读取 LogParserProvider 注入的 Transfer 事件列表

        Returns:
            Transfer 事件列表，如果不存在则返回空列表
        """
        return tx_context.extra.get("parsed_transfers", [])

    def get_parsed_swaps(self, tx_context: TransactionContext) -> list[dict[str, Any]]:
        """
        从 context 中读取 LogParserProvider 注入的 Swap 事件列表

        Returns:
            Swap 事件列表，如果不存在则返回空列表
        """
        return tx_context.extra.get("parsed_swaps", [])

    def get_parsed_approvals(self, tx_context: TransactionContext) -> list[dict[str, Any]]:
        """
        从 context 中读取 LogParserProvider 注入的 Approval 事件列表

        Returns:
            Approval 事件列表，如果不存在则返回空列表
        """
        return tx_context.extra.get("parsed_approvals", [])

    def get_token_prices(self, tx_context: TransactionContext) -> dict[str, float]:
        """
        从 context 中读取 TokenPriceProvider 注入的代币价格映射

        Returns:
            代币地址 -> 价格的映射，如果不存在则返回空字典
        """
        return tx_context.extra.get("token_prices", {})
