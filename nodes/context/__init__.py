"""
节点上下文解析器模块

提供 @require 装饰器和 ContextProvider 基础设施，实现：
1. 默认上下文为 eth_logs（纯日志数据，无需 API 调用）
2. 通过 @require("provider_name") 声明额外上下文需求
3. 执行引擎在节点执行前按需填充上下文（延迟 API 调用）
4. 同一执行批次内缓存已获取的上下文，避免重复 API 调用

架构:
  ContextProvider (ABC)     — 上下文提供者基类，封装特定 API 的调用逻辑
  ContextResolver           — 注册表 + 缓存 + 调度，管理所有 Provider
  @require("provider")      — 类装饰器，声明节点所需的额外上下文
"""

from nodes.context.provider import ContextProvider
from nodes.context.resolver import ContextResolver, get_context_resolver, init_context_resolver
from nodes.context.require import require

__all__ = [
    "ContextProvider",
    "ContextResolver",
    "get_context_resolver",
    "init_context_resolver",
    "require",
]
