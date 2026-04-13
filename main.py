from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from routers import alertRouter
from routers.rule_chain.router import ruleChainRouter
from routers.knowledge_base import knowledgeBaseRouter
from routers.detectors import trace_router, ingest_router
from routers.pool_config.pool_config_router import poolConfigRouter
from database.models import SessionLocal
from config import settings
import os
import logging

# 配置根日志级别 — SignatureDB 的 [TIMING] 和 [API] 日志需要 INFO 级别可见
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
# 降低 uvicorn/access 默认日志噪音
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

import nodes
from nodes.base import NodeRegistry

# 初始化节点注册表
nodes.init_registry()

# 初始化上下文解析器（注册所有内置 Provider）
from nodes.context import init_context_resolver
init_context_resolver()

app = FastAPI(
    title="Alert Webhook Service",
    description="用于接收和处理告警信息的Webhook服务",
    version="1.0.0"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 根路径，用于健康检查
@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "message": "Alert Webhook Service is running"}

app.include_router(alertRouter)
app.include_router(ruleChainRouter)
app.include_router(knowledgeBaseRouter)
app.include_router(trace_router)
app.include_router(ingest_router)
app.include_router(poolConfigRouter)


# ──────────────── 启动时加载预置知识库样本 ────────────────

@app.on_event("startup")
async def seed_knowledge_base():
    """应用启动时，如果知识库为空则加载预置样本"""
    import json as _json
    from database.models import KnowledgeBaseDB
    from pathlib import Path

    db = SessionLocal()
    try:
        count = db.query(KnowledgeBaseDB).count()
        if count > 0:
            return

        sample_file = Path(__file__).parent / "data" / "sample_alerts.json"
        if not sample_file.exists():
            return

        with open(sample_file, "r", encoding="utf-8") as f:
            samples = _json.load(f)

        for sample in samples:
            row = KnowledgeBaseDB(
                title=sample["title"],
                description=sample.get("description"),
                category=sample.get("category", "uncategorized"),
                tags=_json.dumps(sample.get("tags", [])),
                chain_id=sample.get("chain_id", 1),
                tx_hash=sample.get("tx_hash", ""),
                attacked_address=sample.get("attacked_address"),
                exploiter_address=sample.get("exploiter_address"),
                alert_data=_json.dumps(sample["alert_data"]),
                expected_severity=sample.get("expected_severity"),
                expected_labels=_json.dumps(sample.get("expected_labels", [])),
                expected_min_score=sample.get("expected_min_score"),
                source=sample.get("source", "preset"),
                tx_explorer_url=sample.get("tx_explorer_url"),
            )
            db.add(row)

        db.commit()
    except Exception as e:
        print(f"[seed] 加载预置样本失败: {e}")
    finally:
        db.close()


@app.on_event("startup")
async def start_token_price_cache():
    """应用启动时，初始化 TokenPriceCache 并开启后台全量价格刷新"""
    try:
        from detectors.trace.token_price_cache import get_token_price_cache
        cache = get_token_price_cache()
        await cache.start_background_refresh()
        print("[startup] TokenPriceCache background refresh started (5min interval)")
    except Exception as e:
        print(f"[startup] TokenPriceCache init failed (non-fatal): {e}")


@app.on_event("shutdown")
async def cleanup_token_price_cache():
    """应用关闭时，停止价格缓存后台任务和 HTTP 客户端"""
    try:
        from detectors.trace.token_price_cache import get_token_price_cache
        cache = get_token_price_cache()
        await cache.close()
        print("[shutdown] TokenPriceCache cleaned up")
    except Exception as e:
        print(f"[shutdown] TokenPriceCache cleanup error: {e}")

# 静态前端文件服务 (仅当 dist 目录存在时)
frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.isdir(frontend_dist):
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """SPA fallback: 返回 index.html 对所有非 API 路径"""
        if full_path.startswith(("alert", "rule-chain", "knowledge-base", "detectors", "pool-config")):
            return {"detail": "Not Found"}
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))



# 启动应用的代码（如果直接运行该脚本）
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload
    )