"""
上下文提供者基类

每个 Provider 封装一类外部 API 的调用逻辑（如 Moralis、ARKM 等）。
Provider 负责：
  1. 从 alert_data 中提取所需参数（地址、chain_id 等）
  2. 调用外部 API 获取数据
  3. 返回结构化的上下文字典，注入到节点的 context 中

Provider 的返回值会合并到节点的 merged_context 中，
对节点透明——节点只需从 context 中读取字段即可。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ContextProvider(ABC):
    """
    上下文提供者抽象基类。

    子类必须实现:
      - name: str          提供者唯一标识（与 @require 中的名称对应）
      - description: str   描述
      - provides: list[str] 声明此 Provider 向 context 注入的字段列表
      - fetch(context):    异步获取上下文数据，返回 dict
    """

    name: str = ""
    description: str = ""
    provides: list[str] = []  # 声明注入到 context 的字段名列表

    @abstractmethod
    async def fetch(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        异步获取上下文数据。

        Args:
            context: 当前执行上下文（包含 alert_data 和上游输出合并后的数据）
                     可从中读取 chain_id, from_address 等字段作为 API 参数

        Returns:
            要注入到 context 的字段字典。
            例如: {"address_create_time": "2024-01-01T00:00:00Z", "address_age_days": 365}

        注意:
            - 返回空 dict 表示无需注入
            - 不应修改传入的 context，只返回新字段
            - 如果 API 调用失败，应返回 {"_provider_error": {...}} 而非抛出异常
        """
        ...

    def extract_addresses(self, context: dict[str, Any]) -> list[str]:
        """
        从 context 中提取需要查询的地址列表。

        默认实现提取 from_address / to_address / exploiter_address。
        子类可覆盖以自定义地址提取逻辑。

        Returns:
            去重后的地址列表（小写）
        """
        addrs = set()
        for key in ("from_address", "to_address", "exploiter_address"):
            val = context.get(key, "")
            if val and isinstance(val, str) and val.startswith("0x"):
                addrs.add(val.lower())
        return sorted(addrs)

    def extract_chain_id(self, context: dict[str, Any]) -> int:
        """从 context 提取 chain_id，默认 1 (Ethereum)"""
        return int(context.get("chain_id", 1))
