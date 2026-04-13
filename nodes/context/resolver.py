"""
上下文解析器

管理所有 ContextProvider 的注册、缓存和调度。

核心职责:
  1. 注册: Provider 实例注册到全局 resolver
  2. 缓存: 同一执行批次内，相同参数的 Provider 结果只计算一次
  3. 调度: 在节点执行前，按 @require 声明自动填充上下文

缓存策略:
  - 每次规则链执行开始时创建一个新的缓存作用域
  - 缓存 key = (provider_name, chain_id, address_tuple)
  - 同一交易内多次 require 同一 Provider 直接返回缓存
  - 执行结束后缓存自动释放（作用域生命周期）
"""

from __future__ import annotations

import logging
from typing import Any

from nodes.context.provider import ContextProvider

logger = logging.getLogger(__name__)


class ContextResolver:
    """
    上下文解析器 — 管理所有 ContextProvider 的注册、缓存和调度。
    """

    def __init__(self) -> None:
        self._providers: dict[str, ContextProvider] = {}
        # 执行级缓存: key = (provider_name, cache_key) -> dict
        # cache_key 由 Provider 自行生成（通常是地址+chain_id的组合）
        self._cache: dict[tuple[str, str], dict[str, Any]] = {}

    # ── 注册 ──

    def register(self, provider: ContextProvider) -> None:
        """注册一个上下文提供者"""
        if not provider.name:
            raise ValueError(f"Provider {provider.__class__.__name__} must have a non-empty name")
        if provider.name in self._providers:
            existing = self._providers[provider.name]
            if existing is not provider:
                raise ValueError(
                    f"Provider '{provider.name}' already registered by "
                    f"{existing.__class__.__name__}, cannot re-register with "
                    f"{provider.__class__.__name__}"
                )
        self._providers[provider.name] = provider
        logger.info(f"[ContextResolver] Registered provider: {provider.name} "
                     f"({provider.__class__.__name__}, provides: {provider.provides})")

    def get(self, name: str) -> ContextProvider | None:
        """按名称获取 Provider"""
        return self._providers.get(name)

    def all_providers(self) -> dict[str, ContextProvider]:
        """获取所有已注册的 Provider"""
        return dict(self._providers)

    # ── 缓存管理 ──

    def clear_cache(self) -> None:
        """清空执行级缓存（每次规则链执行前调用）"""
        self._cache.clear()

    def _cache_key(self, provider_name: str, context: dict[str, Any]) -> str:
        """
        生成缓存 key。

        默认策略: chain_id + 排序后的地址列表
        Provider 可通过覆盖 get_cache_key() 自定义。
        """
        provider = self._providers.get(provider_name)
        chain_id = provider.extract_chain_id(context) if provider else context.get("chain_id", 1)
        addrs = provider.extract_addresses(context) if provider else []
        return f"{chain_id}:{','.join(addrs)}"

    # ── 核心调度 ──

    async def resolve(
        self,
        provider_names: list[str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        批量解析多个 Provider 的上下文需求。

        Args:
            provider_names: 需要的 Provider 名称列表（来自 @require 声明）
            context: 当前执行上下文

        Returns:
            合并后的上下文字典（所有 Provider 返回值的并集）
        """
        if not provider_names:
            return {}

        merged: dict[str, Any] = {}

        for name in provider_names:
            provider = self._providers.get(name)
            if provider is None:
                logger.warning(f"[ContextResolver] Provider '{name}' not registered, skipping")
                continue

            # 检查缓存
            cache_key = self._cache_key(name, context)
            cache_entry = self._cache.get((name, cache_key))
            if cache_entry is not None:
                logger.debug(f"[ContextResolver] Cache hit for '{name}' (key={cache_key})")
                merged.update(cache_entry)
                continue

            # 调用 Provider
            try:
                result = await provider.fetch(context)
                if result:
                    # 写入缓存
                    self._cache[(name, cache_key)] = result
                    merged.update(result)
                    logger.debug(
                        f"[ContextResolver] Provider '{name}' fetched: "
                        f"{list(result.keys())} (key={cache_key})"
                    )
                else:
                    # 空结果也缓存，避免重复调用
                    self._cache[(name, cache_key)] = {}
            except Exception as e:
                logger.error(
                    f"[ContextResolver] Provider '{name}' fetch failed: {e}",
                    exc_info=True,
                )
                # 记录错误但不中断执行
                merged[f"_{name}_error"] = str(e)

        return merged


# ── 全局单例 ──

_global_resolver: ContextResolver | None = None


def get_context_resolver() -> ContextResolver:
    """获取全局 ContextResolver 单例"""
    global _global_resolver
    if _global_resolver is None:
        _global_resolver = ContextResolver()
    return _global_resolver


def init_context_resolver() -> ContextResolver:
    """
    初始化全局 ContextResolver 并注册所有内置 Provider。
    应在应用启动时调用一次。
    """
    global _global_resolver
    resolver = get_context_resolver()

    # 注册内置 Provider（延迟导入避免循环依赖）
    try:
        from nodes.context.providers.moralis_address import MoralisAddressProvider
        resolver.register(MoralisAddressProvider())
    except ImportError:
        logger.debug("[ContextResolver] MoralisAddressProvider not available")

    try:
        from nodes.context.providers.arkm_label import ARKMLabelProvider
        resolver.register(ARKMLabelProvider())
    except ImportError:
        logger.debug("[ContextResolver] ARKMLabelProvider not available")

    return resolver
