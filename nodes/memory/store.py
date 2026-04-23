"""
全局记忆存储（带 TTL 自动过期）

设计:
  - 按 memory_key 分桶存储，每个桶独立 TTL
  - 每个 key 下存储一条记忆记录（dict），包含时间戳
  - 读取时自动清理过期条目
  - 单例模式，全局共享

用途:
  - 记忆节点写入 → 全局存储
  - 引擎执行前读取 → 注入到 alert_data 上下文
  - 检测器从上下文读取记忆 → 实现跨执行关联
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class MemoryRecord:
    """单条记忆记录"""

    __slots__ = ("data", "created_at", "ttl_seconds", "source_node_id")

    def __init__(
        self,
        data: dict[str, Any],
        ttl_seconds: float,
        source_node_id: str = "",
    ) -> None:
        self.data = data
        self.created_at = time.monotonic()
        self.ttl_seconds = ttl_seconds
        self.source_node_id = source_node_id

    @property
    def is_expired(self) -> bool:
        return (time.monotonic() - self.created_at) > self.ttl_seconds

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.ttl_seconds - (time.monotonic() - self.created_at))


class MemoryStore:
    """
    全局记忆存储（线程安全，单例）。

    按 memory_key 组织记忆桶，每个桶可含多条记录。
    读取时自动清理过期条目。
    """

    _instance: MemoryStore | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        # { memory_key: [MemoryRecord, ...] }
        self._buckets: dict[str, list[MemoryRecord]] = {}
        self._stats = {"writes": 0, "reads": 0, "evictions": 0}

    @classmethod
    def get_instance(cls) -> MemoryStore:
        """获取全局单例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置单例（主要用于测试）"""
        with cls._lock:
            cls._instance = None

    # ── 写入 ──

    def store(
        self,
        memory_key: str,
        data: dict[str, Any],
        ttl_seconds: float = 86400.0,
        source_node_id: str = "",
    ) -> None:
        """
        写入一条记忆记录。

        Args:
            memory_key: 记忆桶键（如 "proxy_upgrade_events"）
            data: 要存储的数据
            ttl_seconds: 生存时间（秒），默认 24h
            source_node_id: 来源节点 ID
        """
        record = MemoryRecord(
            data=data,
            ttl_seconds=ttl_seconds,
            source_node_id=source_node_id,
        )
        bucket = self._buckets.setdefault(memory_key, [])
        bucket.append(record)
        self._stats["writes"] += 1
        logger.debug(
            f"[MemoryStore] Stored to '{memory_key}': "
            f"{len(data)} fields, TTL={ttl_seconds}s, "
            f"bucket_size={len(bucket)}"
        )

    # ── 读取 ──

    def retrieve(self, memory_key: str) -> list[dict[str, Any]]:
        """
        读取指定桶的所有未过期记录。

        自动清理过期条目。

        Returns:
            数据 dict 列表（每个元素是一条记忆记录的 data）
        """
        bucket = self._buckets.get(memory_key, [])
        self._stats["reads"] += 1

        # 清理过期条目
        valid = []
        expired_count = 0
        for record in bucket:
            if record.is_expired:
                expired_count += 1
            else:
                valid.append(record)

        if expired_count > 0:
            self._buckets[memory_key] = valid
            self._stats["evictions"] += expired_count
            logger.debug(
                f"[MemoryStore] Evicted {expired_count} expired records "
                f"from '{memory_key}'"
            )

        return [r.data for r in valid]

    def retrieve_merged(self, memory_key: str) -> dict[str, Any]:
        """
        读取并合并指定桶的所有记录为单个 dict。

        后写入的字段覆盖先写入的同名字段。
        若无有效记录，返回空 dict。
        """
        records = self.retrieve(memory_key)
        merged: dict[str, Any] = {}
        for data in records:
            merged.update(data)
        return merged

    def retrieve_all_merged(self) -> dict[str, Any]:
        """
        读取所有桶的合并结果。

        将每个桶的记录合并，统一输出为一个 dict。
        每个桶的数据放在以 memory_key 为键的子字典中。
        同时在顶层平铺所有字段（方便检测器直接访问）。
        """
        result: dict[str, Any] = {}
        for key in list(self._buckets.keys()):
            merged = self.retrieve_merged(key)
            if merged:
                # 按桶键分组
                result[f"_memory_{key}"] = merged
                # 同时平铺到顶层（方便下游直接用）
                for k, v in merged.items():
                    if k not in result:  # 不覆盖已有的显式字段
                        result[k] = v
        return result

    # ── 管理 ──

    def delete_key(self, memory_key: str) -> int:
        """删除指定桶，返回被删除的记录数"""
        bucket = self._buckets.pop(memory_key, [])
        return len(bucket)

    def clear_all(self) -> None:
        """清空所有记忆"""
        self._buckets.clear()
        logger.info("[MemoryStore] All memory cleared")

    def cleanup_expired(self) -> int:
        """清理所有桶中的过期记录，返回总清理数"""
        total = 0
        keys_to_delete = []
        for key, bucket in self._buckets.items():
            before = len(bucket)
            valid = [r for r in bucket if not r.is_expired]
            self._buckets[key] = valid
            total += before - len(valid)
            if not valid:
                keys_to_delete.append(key)

        for key in keys_to_delete:
            del self._buckets[key]

        if total > 0:
            self._stats["evictions"] += total
            logger.info(f"[MemoryStore] Cleanup: evicted {total} expired records")
        return total

    def get_stats(self) -> dict[str, Any]:
        """获取存储统计信息"""
        bucket_info = {}
        for key, bucket in self._buckets.items():
            valid = [r for r in bucket if not r.is_expired]
            bucket_info[key] = {
                "total_records": len(valid),
                "oldest_remaining_seconds": (
                    min(r.remaining_seconds for r in valid) if valid else 0
                ),
            }
        return {
            "writes": self._stats["writes"],
            "reads": self._stats["reads"],
            "evictions": self._stats["evictions"],
            "buckets": bucket_info,
        }


# 便捷访问函数
def get_memory_store() -> MemoryStore:
    return MemoryStore.get_instance()
