"""
Ingest 输入数据模型 — 统一的数据格式定义
==========================================

本模块是规则链引擎输入数据的**唯一权威来源** (Single Source of Truth)。

数据流（实时处理 + 回测/测试 共享同一套模型）:

  实时处理路径:
    EVMLogListener → POST /ingest/logs (IngestLogsRequest)
      → EventLog.from_ingest_request()   # API LogObject → 统一 EventLog
      → TxLogsGroup.from_event_logs()    # 按 tx_hash 分组
      → AlertData.from_tx_group()        # 构建引擎标准输入
      → ChainExecutor.execute(chain, alert_data.model_dump())

  回测 / 测试路径:
    历史数据 / 手工构造
      → EventLog.from_raw()              # 原始 dict → 统一 EventLog
      → AlertData.from_logs()            # 直接构建引擎标准输入
      → ChainExecutor.execute(chain, alert_data.model_dump())

对外兼容性保证:
  - IngestedLog / TxLogsGroup / MatchedAlert (dataclass) 仍可从 detectors.trace.rule_engine 导入
  - EvmLog / TransactionLogsMap 作为旧名称指向新模型
  - ingest_router 的 LogObject / IngestLogsRequest 等 API 模型保持不变
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ================================================================
# 基础原子模型
# ================================================================

class TransferEvent(BaseModel):
    """从 ERC20 Transfer 事件中提取的摘要"""
    token_address: str = Field(default="", description="Token 合约地址")
    from_address: str = Field(default="", description="发送方地址 (截取前缀后 20 字节)")
    to_address: str = Field(default="", description="接收方地址 (截取前缀后 20 字节)")
    value_raw: int = Field(default=0, description="转账金额 (原始整数，需按 token decimals 处理)")


class EventLog(BaseModel):
    """
    单条 EVM Event Log — 统一日志模型

    同时服务于:
    - API 层接收 (LogObject 转换而来)
    - 内部处理 (原 IngestedLog / EvmLog 的统一替代)
    - 回测构造 (from_raw 从历史数据构建)

    字段命名全部使用 snake_case。
    """

    address: str = Field(default="", description="合约地址")
    topics: list[str] = Field(default_factory=list, description="事件主题数组")
    data: str = Field(default="0x", description="事件编码数据 (hex)")
    block_number: int = Field(default=0, ge=0, description="区块号")
    transaction_hash: str = Field(default="", description="交易 hash")
    log_index: int = Field(default=0, ge=0, description="交易内日志序号")
    transaction_index: int = Field(default=0, ge=0, description="区块内交易索引")
    block_hash: str = Field(default="", description="区块哈希")
    removed: bool = Field(default=False, description="是否被链重组移除")

    # ── 自动小写化校验器 ──

    @field_validator("address", mode="before")
    @classmethod
    def _lower_address(cls, v: Any) -> str:
        if isinstance(v, str):
            return v.lower()
        return str(v).lower()

    @field_validator("topics", mode="before")
    @classmethod
    def _lower_topics(cls, v: Any) -> list[str]:
        if isinstance(v, list):
            return [t.lower() if isinstance(t, str) else t for t in v]
        return []

    # ── 构造方法 ──

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> EventLog:
        """
        从原始 dict 构建（兼容 hex 字符串或整数数值字段）。

        用于回测场景：直接从数据库导出或文件中的原始日志数据构造。
        """
        def _int(val: Any) -> int:
            if isinstance(val, int):
                return val
            if isinstance(val, str) and val.startswith("0x"):
                return int(val, 16)
            try:
                return int(val)
            except (TypeError, ValueError):
                return 0

        return cls(
            address=raw.get("address", ""),
            topics=raw.get("topics", []),
            data=raw.get("data", "0x") or "0x",
            block_number=_int(raw.get("block_number", 0)),
            transaction_hash=raw.get("transaction_hash", ""),
            log_index=_int(raw.get("log_index", 0)),
            transaction_index=_int(raw.get("transaction_index", 0)),
            block_hash=raw.get("block_hash", ""),
            removed=bool(raw.get("removed", False)),
        )

    @classmethod
    def from_ingest_request(cls, log_object_dict: dict[str, Any]) -> EventLog:
        """
        从 ingest_router 的 LogObject.model_dump() 结果构造。

        LogObject 字段已与 EventLog 一致，直接透传即可。
        （保留此方法作为显式的转换入口，未来如字段差异变大只需改此处）
        """
        return cls(**log_object_dict)

    @classmethod
    def from_list(
        cls,
        raw_list: list[dict[str, Any]],
        source: str = "raw",
    ) -> list[EventLog]:
        """
        批量构造。

        Args:
            raw_list: 原始字典列表
            source: "raw" 表示回测数据（用 from_raw），
                    "ingest" 表示来自 API 请求体（用 from_ingest_request）
        """
        factory = cls.from_raw if source == "raw" else cls.from_ingest_request
        return [factory(item) for item in raw_list]

    # ── 序列化方法 ──

    def to_log_dict(self) -> dict[str, Any]:
        """
        转为 alert_data['logs'] 中条目的内部表示。

        注意: 此处输出使用 camelCase 字段名，
        以兼容已有节点代码对 alert_data["logs"][i]["blockNumber"] 等字段的引用。
        未来可逐步迁移节点至 snake_case 后改为 snake_case 输出。
        """
        return {
            "address": self.address,
            "topics": self.topics,
            "data": self.data,
            "blockNumber": self.block_number,
            "transactionHash": self.transaction_hash,
            "logIndex": self.log_index,
            "transactionIndex": self.transaction_index,
            "blockHash": self.block_hash,
            "removed": self.removed,
        }

    def to_snake_dict(self) -> dict[str, Any]:
        """转为 snake_case 字典（用于需要一致命名的场景）"""
        return self.model_dump()


# ================================================================
# 分组模型
# ================================================================

class TxLogsGroup(BaseModel):
    """
    按 tx_hash 分组后的交易日志集合 — 统一分组模型

    替代原:
    - detectors.trace.rule_engine.TxLogsGroup (dataclass)
    - models.ingest.TransactionLogsMap (Pydantic，按 tx 分组的容器)
    """
    tx_hash: str = Field(description="交易 hash")
    chain_id: int = Field(default=1, ge=1, description="来源链 ID")
    chain_name: str = Field(default="", description="来源链名称")
    logs: list[EventLog] = Field(default_factory=list, description="该交易的日志列表")
    block_number: int = Field(default=0, ge=0, description="当前批次最大区块号")

    # ── 构造方法 ──

    @classmethod
    def from_event_logs(
        cls,
        event_logs: list[EventLog],
        tx_hash: str,
        chain_id: int = 1,
        chain_name: str = "",
        block_number: int = 0,
    ) -> TxLogsGroup:
        """从统一的 EventLog 列表构造分组"""
        sorted_logs = sorted(event_logs, key=lambda l: l.log_index)
        return cls(
            tx_hash=tx_hash,
            chain_id=chain_id,
            chain_name=chain_name,
            logs=sorted_logs,
            block_number=block_number,
        )

    # ── 属性 ──

    @property
    def log_count(self) -> int:
        return len(self.logs)

    @property
    def unique_addresses(self) -> set[str]:
        return {log.address for log in self.logs if log.address}

    @property
    def unique_topics(self) -> set[str]:
        topics_set: set[str] = set()
        for log in self.logs:
            for t in log.topics:
                if t:
                    topics_set.add(t.lower())
        return topics_set


# ================================================================
# 引擎标准输入模型 — 核心输出
# ================================================================

# ERC20 Transfer 事件签名 topic（keccak256(Transfer(address,address,uint256))）
_ERC20_TRANSFER_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)


class AlertData(BaseModel):
    """
    规则链引擎的标准输入 — 统一 alert_data 模型

    这是 ChainExecutor.execute() 消费的核心数据结构。
    同时用于:
    - 实时处理: ingest_router 收到日志后构建
    - 回测检验: 用历史数据构建后传入引擎测试规则
    - 前端测试面板: 用户编辑的测试数据

    使用方式::

        # 实时路径
        group = TxLogsGroup.from_event_logs(event_logs, tx_hash=..., chain_id=56)
        alert_data = AlertData.from_tx_group(group)
        result = await executor.execute(parsed_chain, alert_data.model_dump())

        # 回测路径（无需经过 API）
        event_logs = EventLog.from_list(raw_history_data, source="raw")
        alert_data = AlertData.from_logs(
            logs=event_logs,
            tx_hash="0x...",
            chain_id=1,
            block_number=25000000,
        )
        result = await executor.execute(parsed_chain, alert_data.model_dump())
    """

    # ---- 基础标识 ----
    tx_hash: str = Field(default="", description="目标交易 hash")
    chain_id: int = Field(default=1, ge=1, description="来源链 ID")
    chain_name: str = Field(default="", description="来源链名称")
    block_number: int = Field(default=0, ge=0, description="当前批次最大区块号")

    # ---- 日志数据 ----
    logs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="该交易下的所有 Event Log 列表 (camelCase 内部格式)",
    )
    log_count: int = Field(default=0, ge=0, description="日志条数")

    # ---- 聚合特征 ----
    unique_contracts: list[str] = Field(
        default_factory=list,
        description="去重后的合约地址列表（排序后，小写）",
    )
    unique_contract_count: int = Field(default=0, ge=0, description="唯一合约数量")
    unique_topics: list[str] = Field(
        default_factory=list,
        description="去重后的事件主题列表（排序后，小写）",
    )
    unique_topic_count: int = Field(default=0, ge=0, description="唯一主题数量")

    # ---- Transfer 事件摘要 ----
    transfer_events: list[dict[str, Any]] = Field(
        default_factory=list,
        description="提取的 ERC20 Transfer 事件数组",
    )
    transfer_event_count: int = Field(default=0, ge=0, description="Transfer 事件数量")

    # ---- 元信息 ----
    received_at: str = Field(default="", description="ISO-8601 时间戳")

    # ---- 构造方法 ----

    @classmethod
    def from_tx_group(cls, group: TxLogsGroup) -> AlertData:
        """
        从 TxLogsGroup 构建 AlertData（实时处理主路径）

        这是 ingest_router._evaluate_group_with_chains() 应调用的唯一入口。
        """
        logs_data = [log.to_log_dict() for log in group.logs]
        unique_addrs = sorted(group.unique_addresses)
        unique_topics_lst = sorted(group.unique_topics)
        transfers = cls._extract_transfers(group.logs)

        return cls(
            tx_hash=group.tx_hash,
            chain_id=group.chain_id,
            chain_name=group.chain_name,
            block_number=group.block_number or (
                group.logs[0].block_number if group.logs else 0
            ),
            logs=logs_data,
            log_count=len(logs_data),
            unique_contracts=unique_addrs,
            unique_contract_count=len(unique_addrs),
            unique_topics=unique_topics_lst,
            unique_topic_count=len(unique_topics_lst),
            transfer_events=[t.model_dump() for t in transfers],
            transfer_event_count=len(transfers),
            received_at=datetime.now(timezone.utc).isoformat(),
        )

    @classmethod
    def from_logs(
        cls,
        logs: list[EventLog],
        tx_hash: str,
        chain_id: int = 1,
        chain_name: str = "",
        block_number: int = 0,
    ) -> AlertData:
        """
        直接从 EventLog 列表构建 AlertData（回测 / 测试路径）

        无需先构造 TxLogsGroup，一步到位。
        用于前端测试面板、回测脚本等场景。
        """
        logs_data = [log.to_log_dict() for log in logs]
        unique_addrs = sorted({log.address for log in logs if log.address})
        unique_topics_set: set[str] = set()
        for log in logs:
            for t in log.topics:
                if t:
                    unique_topics_set.add(t)
        unique_topics_lst = sorted(unique_topics_set)
        transfers = cls._extract_transfers(logs)

        return cls(
            tx_hash=tx_hash,
            chain_id=chain_id,
            chain_name=chain_name,
            block_number=block_number or (logs[0].block_number if logs else 0),
            logs=logs_data,
            log_count=len(logs_data),
            unique_contracts=unique_addrs,
            unique_contract_count=len(unique_addrs),
            unique_topics=unique_topics_lst,
            unique_topic_count=len(unique_topics_lst),
            transfer_events=[t.model_dump() for t in transfers],
            transfer_event_count=len(transfers),
            received_at=datetime.now(timezone.utc).isoformat(),
        )

    # ---- 私有方法 ----

    @staticmethod
    def _extract_transfers(logs: list[EventLog]) -> list[TransferEvent]:
        """从日志中提取 ERC20 Transfer 事件摘要"""
        events: list[TransferEvent] = []
        for log in logs:
            if not log.topics or log.topics[0].lower() != _ERC20_TRANSFER_TOPIC:
                continue
            try:
                value_raw = int(log.data, 16) if len(log.data) > 2 else 0
            except (ValueError, OverflowError):
                value_raw = 0
            events.append(TransferEvent(
                token_address=log.address,
                from_address=log.topics[1][26:] if len(log.topics) > 1 else "",
                to_address=log.topics[2][26:] if len(log.topics) > 2 else "",
                value_raw=value_raw,
            ))
        return events


# ================================================================
# 兼容性别名 — 供旧代码平滑迁移
# ================================================================

# Pydantic 旧名称别名 (models/ingest.py 原有类名)
EvmLog = EventLog
"""别名，等同于 :class:`EventLog`。建议新代码直接使用 EventLog。"""


def TransactionLogsMap(*args, **kwargs):
    """
    兼容性包装：模拟旧的 TransactionLogsMap 接口签名。

    旧用法: TransactionLogsMap.from_logs(logs, chain_id=1)
    新用法: TxLogsGroup.from_event_logs(logs, tx_hash=h, chain_id=1)
             或 AlertData.from_logs(logs, tx_hash=...)

    此工厂函数在调用 from_logs 等类方法时抛出 DeprecationWarning，
    引导迁移到新的 AlertData / TxLogsGroup API。
    """
    import warnings
    warnings.warn(
        "TransactionLogsMap 已废弃，请使用 AlertData 或 TxLogsGroup。"
        "参见 models.ingest 模块文档。",
        DeprecationWarning,
        stacklevel=2,
    )
    # 返回一个轻量代理对象，仅支持 from_logs 方法并转发
    class _DeprecatedMap:
        @staticmethod
        def from_logs(logs, chain_id=1, chain_name="", block_number=0):
            warnings.warn(
                "TransactionLogsMap.from_logs() 已废弃，"
                "请改用 AlertData.from_logs() 或 TxLogsGroup.from_event_logs()",
                DeprecationWarning,
                stacklevel=2,
            )
            # 返回一个类似旧接口的对象，但底层使用新模型
            groups = {}
            for log in logs:
                h = log.transaction_hash
                if not h:
                    continue
                groups.setdefault(h, []).append(log)
            # 包装成有 .groups 属性和 .to_alert_data() 方法的对象
            class _CompatWrapper:
                def __init__(self, _groups, _cid, _cname, _blk):
                    self.groups = _groups
                    self.chain_id = _cid
                    self.chain_name = _cname
                    self.block_number = _blk

                def to_alert_data(self, tx_hash):
                    group_logs = self.groups.get(tx_hash, [])
                    return AlertData.from_logs(
                        logs=group_logs,
                        tx_hash=tx_hash,
                        chain_id=self.chain_id,
                        chain_name=self.chain_name,
                        block_number=self.block_number,
                    )

                def iter_alert_data(self):
                    for h in self.groups:
                        yield h, self.to_alert_data(h)

            return _CompatWrapper(groups, chain_id, chain_name, block_number)

    return _DeprecatedMap
