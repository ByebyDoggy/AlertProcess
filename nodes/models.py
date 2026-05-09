"""
数据传输基础模型

所有 ContextProvider 节点和 Detector 节点的输入输出都基于此模型。
这是规则链中节点间传递数据的基础模型，包含交易上下文信息和扩展字段。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TransactionContext(BaseModel):
    """
    数据传输基础模型 — 规则链中节点间传递的标准交易上下文。

    所有 ContextProvider 节点和 Detector 节点的输入都是此模型。
    ContextProvider 输出此模型（额外字段填充到 extra 中）。
    Detector 输出此模型（context 端口）+ DetectorResult（detection 端口）。

    Attributes:
        chain_id: 区块链网络 ID（1=ETH, 56=BSC, 137=MATIC）
        tx_hash: 交易的唯一哈希值
        block_number: 交易所在区块号
        from_address: 交易发起者 (from) 地址
        to_address: 交易目标 (to) 地址，空=合约创建
        value: 原生代币转账金额（wei 单位）
        gas_price: 单位 Gas 价格（wei）
        gas_used: 交易消耗的 Gas 总量
        input_data: 交易的 calldata / 方法签名+参数
        timestamp: 交易发生时间 (ISO8601)
        logs: 交易产生的 Event Log 列表
        extra: 扩展上下文字段（Provider 节点注入的数据）
    """
    chain_id: int = Field(default=1, description="区块链网络 ID（1=ETH, 56=BSC, 137=MATIC）")
    tx_hash: str = Field(default="", description="交易的唯一哈希值")
    block_number: int = Field(default=0, description="交易所在区块号")
    from_address: str = Field(default="", description="交易发起者 (from) 地址")
    to_address: str = Field(default="", description="交易目标 (to) 地址，空=合约创建")
    value: int = Field(default=0, description="原生代币转账金额（wei 单位）")
    gas_price: int = Field(default=0, description="单位 Gas 价格（wei）")
    gas_used: int = Field(default=0, description="交易消耗的 Gas 总量")
    input_data: str = Field(default="", description="交易的 calldata / 方法签名+参数")
    timestamp: str = Field(default="", description="交易发生时间 (ISO8601)")
    logs: list[dict[str, Any]] = Field(default_factory=list, description="交易产生的 Event Log 列表")
    extra: dict[str, Any] = Field(default_factory=dict, description="扩展上下文字段（Provider 节点注入的数据）")

    def get_extra(self, key: str, default: Any = None) -> Any:
        """从 extra 中获取字段，带默认值"""
        return self.extra.get(key, default)

    def set_extra(self, key: str, value: Any) -> None:
        """向 extra 中设置字段"""
        if self.extra is None:
            self.extra = {}
        self.extra[key] = value

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TransactionContext":
        """从字典创建 TransactionContext，分离标准字段和 extra"""
        # 标准字段
        standard_fields = {
            "chain_id", "tx_hash", "block_number", "from_address", "to_address",
            "value", "gas_price", "gas_used", "input_data", "timestamp", "logs"
        }
        extra = {}
        for k, v in data.items():
            if k not in standard_fields:
                extra[k] = v
        return cls(
            **{k: v for k, v in data.items() if k in standard_fields},
            extra=extra
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典，将 extra 展开"""
        result = self.model_dump()
        # 将 extra 中的字段展开到顶层
        if self.extra:
            for k, v in self.extra.items():
                result[k] = v
        del result["extra"]
        return result


class DetectorResult(BaseModel):
    """
    Detector 检测结果模型 — Detector 节点的 detection 输出端口。

    用于传递检测结果（score, passed, severity, labels, detection, logs）。
    """
    score: float = Field(ge=0, le=100, description="0-100 风险评分")
    passed: bool = Field(description="评分是否 >= 配置的阈值")
    severity: str = Field(description="UNKNOWN/LOW/MEDIUM/HIGH/CRITICAL")
    labels: list[str] = Field(default_factory=list, description="命中的检测标签列表")
    detection: dict[str, Any] = Field(default_factory=dict, description="各检测器特有的检测结果数据")
    logs: list[str] = Field(default_factory=list, description="评分原因日志，记录各评分步骤的判定依据")
