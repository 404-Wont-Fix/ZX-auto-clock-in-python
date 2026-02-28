# Docker 部署指南

## 部署架构

本应用使用 **Python APScheduler** + **Docker 自动重启** 的方案，确保：
- ✅ 定时任务稳定执行
- ✅ 进程崩溃自动重启
- ✅ 数据持久化存储
- ✅ 日志统一管理

## 快速部署

### 1. 准备工作

```bash
# 克隆代码
git clone <repository-url>
cd ZK-auto-clock-in-python

# 复制环境变量配置
cp .env.example .env

# 编辑配置文件（重要！）
vim .env
```

### 2. 关键配置项

```bash
# .env 文件必须修改的配置

# 管理员账号密码
ADMIN_USERNAME=your_admin_name
ADMIN_PASSWORD=your_strong_password

# 管理路径（安全功能：建议修改为随机字符串）
ADMIN_PATH=my-secret-admin-123

# clockin-worker API 地址
CLOCKIN_API_URL=https://your-worker.workers.dev
CLOCKIN_API_TOKEN=your-worker-token

# 定时任务（北京时间 0:10 = UTC 16:10）
SCHEDULE_CRON=0 10 16 * * *

# 数据保留天数
RETENTION_DAYS=30
```

### 3. 启动服务

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 查看运行状态
docker-compose ps
```

### 4. 访问应用

```
# 管理面板入口
http://your-server-ip:8000/my-secret-admin-123

# API 健康检查
curl http://your-server-ip:8000/health
```

## 定时任务说明

### 当前配置

程序使用 **Python APScheduler** 在容器内部执行定时任务：

| 任务 | Cron 表达式 | 北京时间 | 功能 |
|------|-------------|----------|------|
| 打卡任务 | `0 10 16 * * *` | 00:10 | 自动执行所有用户打卡 |
| 清理任务 | `0 3 * * *` | 11:00 | 清理过期数据 |

### 修改定时时间

编辑 `.env` 文件：

```bash
# Cron 格式: 秒 分 时 日 月 周 (UTC 时间)
# 北京时间 = UTC - 8 小时

# 示例：改为北京时间 8:30 (UTC 0:30)
SCHEDULE_CRON=0 30 0 * * *

# 示例：改为每天执行两次（8:00 和 20:00 北京时间）
SCHEDULE_CRON=0 0 0,12 * * *
```

**注意**：修改后需要重启容器：
```bash
docker-compose restart
```

### 为什么不使用 Linux cron？

| 对比项 | Python APScheduler | Linux cron |
|--------|-------------------|------------|
| 实现复杂度 | ✅ 已实现，开箱即用 | ❌ 需要额外开发 CLI |
| 时区处理 | ✅ 配置简单，统一管理 | ❌ 需要注意容器时区 |
| 日志管理 | ✅ 统一在应用日志中 | ❌ 分散在不同位置 |
| 动态配置 | ✅ 修改环境变量即可 | ❌ 需要进入容器修改 crontab |
| 故障恢复 | ✅ Docker 自动重启 | ⚠️ 需要额外监控 |
| 开发体验 | ✅ 本地/生产环境一致 | ❌ 环境差异大 |

## 高可用保障

### 1. Docker 自动重启

```yaml
restart: always  # 崩溃时自动重启
```

### 2. 健康检查

```yaml
healthcheck:
  test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()"]
  interval: 30s
  timeout: 10s
  retries: 3
```

### 3. 资源限制

防止内存泄漏导致系统崩溃：
```yaml
deploy:
  resources:
    limits:
      cpus: '1'
      memory: 512M
```

## 运维命令

```bash
# 查看日志（实时）
docker-compose logs -f zk-admin

# 查看定时任务执行日志
docker-compose logs -f zk-admin | grep "定时打卡"

# 重启服务
docker-compose restart

# 停止服务
docker-compose stop

# 完全删除（数据不会丢失，因为使用了 volume）
docker-compose down

# 进入容器调试
docker-compose exec zk-admin bash

# 查看容器资源占用
docker stats zk-admin

# 备份数据库
docker-compose exec zk-admin cp database/zk_admin.db database/backup_$(date +%Y%m%d).db
```

## 监控建议

### 1. 日志监控

```bash
# 监控定时任务执行
tail -f logs/*.log | grep "定时打卡"

# 监控错误日志
tail -f logs/*.log | grep "ERROR"
```

### 2. 容器状态

```bash
# 检查容器是否在运行
docker-compose ps

# 检查健康状态
docker inspect zk-admin | grep -A 10 Health
```

### 3. 数据库检查

```bash
# 进入容器
docker-compose exec zk-admin bash

# 检查数据库
python scripts/check_db.py

# 查看最近打卡结果
python scripts/check_result.py
```

## 常见问题

### Q1: 定时任务没有执行？

```bash
# 1. 检查时区设置
docker-compose exec zk-admin date

# 2. 查看调度器日志
docker-compose logs | grep "调度器"

# 3. 检查配置
docker-compose exec zk-admin cat /app/.env | grep SCHEDULE_CRON
```

### Q2: 容器频繁重启？

```bash
# 查看详细日志
docker-compose logs --tail=100

# 检查资源限制
docker stats zk-admin

# 可能是内存不足，调整 docker-compose.yml 中的 memory 限制
```

### Q3: 数据丢失？

```bash
# 数据存储在 volume 中，即使容器删除也不会丢失
# 但建议定期备份数据库

docker-compose exec zk-admin bash
cd database
cp zk_admin.db backup_$(date +%Y%m%d_%H%M%S).db
```

### Q4: 如何升级版本？

```bash
# 1. 备份数据
docker-compose exec zk-admin cp database/zk_admin.db database/backup.db

# 2. 拉取最新代码
git pull

# 3. 重新构建并启动
docker-compose up -d --build

# 4. 验证
docker-compose logs -f
```

## 生产环境建议

### 1. 使用 Nginx 反向代理

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 2. 配置 HTTPS

使用 Let's Encrypt + Certbot 免费证书。

### 3. 日志轮转

已经在 `docker-compose.yml` 中配置：
```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

### 4. 定期备份

```bash
# 添加到系统 crontab
0 2 * * * cd /path/to/ZK-auto-clock-in-python && docker-compose exec zk-admin bash -c "cp database/zk_admin.db database/backup_$(date +\%Y\%m\%d).db"
```

### 5. 监控告警

- 使用 Prometheus + Grafana 监控容器状态
- 配置钉钉/企业微信告警
- 监控关键指标：容器状态、健康检查、定时任务执行情况
