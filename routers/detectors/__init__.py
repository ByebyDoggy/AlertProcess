"""Detectors 路由模块 — 包含交易分析等检测器相关 API"""
from routers.detectors.trace_router import trace_router
from routers.detectors.ingest_router import ingest_router

__all__ = ["trace_router", "ingest_router"]
