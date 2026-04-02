# 使用官方Python镜像作为基础镜像
FROM python:3.13-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制requirements.txt文件并安装Python依赖（root用户执行，无权限问题）
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# 复制项目文件（不包括.env文件）
COPY . .

# 创建数据目录并设置root权限（确保root可读写）
RUN mkdir -p /app/data && chmod 777 /app/data

# 【关键修改】删除非root用户创建和切换逻辑，默认以root用户运行
# （原USER appuser语句已删除，Docker默认用root用户）

# 暴露应用端口
EXPOSE 8000

# 使用uvicorn启动FastAPI应用（root用户运行）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]