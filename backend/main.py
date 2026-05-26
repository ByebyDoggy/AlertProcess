from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from backend.routers.system_config import systemConfigRouter
from backend.middleware.auth_middleware import JWTAuthMiddleware
from backend.database.models import SessionLocal
from backend.config import settings
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

# Add JWT authentication middleware
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-jwt-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

app.add_middleware(
    JWTAuthMiddleware,
    secret_key=JWT_SECRET_KEY,
    algorithm=JWT_ALGORITHM,
    public_paths=["/api/health", "/docs", "/openapi.json", "/redoc"]
)

# 根路径，用于健康检查
@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "message": "Alert Webhook Service is running"}

app.include_router(systemConfigRouter)

# Legacy startup hooks removed - apipool integration will be reimplemented in script-first platform

# 静态前端文件服务 (仅当 dist 目录存在时)
frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.isdir(frontend_dist):
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """SPA fallback: 返回 index.html 对所有非 API 路径"""
        if full_path.startswith(("alert", "rule-chain", "knowledge-base", "detectors", "pool-config", "system")):
            return {"detail": "Not Found"}
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))



# 启动应用的代码（如果直接运行该脚本）
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload
    )