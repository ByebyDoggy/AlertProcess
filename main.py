from fastapi import FastAPI
from routers import alertRouter
from config import settings
app = FastAPI(
    title="Alert Webhook Service",
    description="用于接收和处理告警信息的Webhook服务",
    version="1.0.0"
)
# 包含告警路由
app.include_router(alertRouter)


# 根路径，用于健康检查
@app.get("/")
async def root():
    return {"status": "healthy", "message": "Alert Webhook Service is running"}



# 启动应用的代码（如果直接运行该脚本）
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload
    )