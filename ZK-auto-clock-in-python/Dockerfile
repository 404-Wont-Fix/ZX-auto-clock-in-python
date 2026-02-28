FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建必要的目录
RUN mkdir -p database logs

# 暴露端口
EXPOSE 8000

# 启动命令（单进程，自动重启策略由 docker-compose 管理）
# 生产环境建议使用多个 worker
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
