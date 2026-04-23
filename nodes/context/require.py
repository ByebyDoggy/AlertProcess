"""
@require 装饰器

用于声明节点所需的额外上下文环境。

用法:
    @require("moralis_address")
    class AddressAgeDetector(BaseDetector):
        ...

    @require("moralis_address", "arkm_label")
    class MyDetector(BaseDetector):
        ...

效果:
  - 节点类被标记为需要指定的上下文 Provider
  - ChainExecutor 在执行节点前，自动调用 ContextResolver 填充上下文
  - 未标注 @require 的节点默认只使用 eth_logs 上下文（零 API 调用）

原理:
  - 装饰器在类上设置 __required_providers__ 属性
  - BaseNode 提供类方法 get_required_providers() 读取此属性
  - ChainExecutor 在执行前检查此属性并调用 ContextResolver
"""

from __future__ import annotations

from typing import Any


def require(*provider_names: str):
    """
    声明节点所需的上下文 Provider。

    Args:
        *provider_names: Provider 名称，与 ContextResolver 中注册的名称对应

    Returns:
        类装饰器

    示例:
        @require("moralis_address")
        class AddressAgeDetector(BaseDetector):
            async def process(self, input):
                # input.context 中已包含 address_create_time, address_age_days 等字段
                age = input.context.get("address_age_days")
                ...
    """
    if not provider_names:
        raise ValueError("@require() requires at least one provider name")

    for name in provider_names:
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Provider name must be a non-empty string, got: {name!r}")

    def decorator(cls: type) -> type:
        # 合并：如果类已有 @require（多重装饰），追加而非覆盖
        existing = getattr(cls, "__required_providers__", ())
        # 去重并保持顺序
        seen = set(existing)
        merged = list(existing)
        for name in provider_names:
            if name not in seen:
                merged.append(name)
                seen.add(name)

        cls.__required_providers__ = tuple(merged)
        return cls

    return decorator
