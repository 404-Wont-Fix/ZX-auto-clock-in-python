# ZK Auto Clock-in - Python 版本

ZK 多用户自动打卡系统的 Python 实现，部署在 VPS 云服务器上。

## 项目简介

这是原 admin-worker 的 Python 重构版本，突破 Cloudflare Workers 免费账户的限制，支持大规模用户管理。

## 系统架构

```
浏览器 → Nginx → FastAPI → SQLite
              ↓
      clockin-worker (中间层)
              ↓
        精夏平台 API
```

### 为什么保留 clockin-worker

- **IP 隐藏**：VPS IP 不直接暴露给精夏平台
- **分散请求**：请求来源为 Cloudflare CDN IP
- **降级保护**：即使 VPS 故障，clockin-worker 仍可独立使用

## 技术栈

- **Web 框架**：FastAPI
- **数据库**：SQLite + SQLAlchemy
- **异步支持**：asyncio + httpx
- **定时任务**：APScheduler
- **认证**：JWT

## 快速开始

### 1. 创建虚拟环境

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Linux/Mac:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，修改必要配置
```

### 4. 初始化数据库

```bash
python scripts/init_db.py
```

### 5. 启动应用

```bash
# 开发模式（自动重载）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 生产模式
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 6. 访问应用

打开浏览器访问：
- 管理面板：http://localhost:8000/dashboard
- API 文档：http://localhost:8000/docs

## 目录结构

```
ZK-auto-clock-in-python/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 应用入口
│   ├── config.py               # 配置管理
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── database.py         # SQLAlchemy 模型
│   │   └── schemas.py          # Pydantic 模型
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── auth.py             # 认证 API
│   │   ├── users.py            # 用户管理 API
│   │   ├── clockin.py          # 打卡操作 API
│   │   ├── config.py           # 配置管理 API
│   │   └── maintenance.py      # 维护 API
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── user_service.py     # 用户业务逻辑
│   │   ├── clockin_service.py  # 打卡业务逻辑
│   │   ├── task_service.py     # 任务管理
│   │   ├── poetry_service.py   # 诗词/图片 API
│   │   └── scheduler_service.py # 定时任务
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── database.py         # 数据库连接
│   │   ├── security.py         # 密码加密、JWT
│   │   └── scheduler.py        # APScheduler 配置
│   │
│   └── ui/                     # 前端静态文件
│       ├── index.html
│       ├── login.html
│       ├── 404.html
│       └── assets/
│
├── database/
│   └── zk_admin.db             # SQLite 数据库文件
│
├── logs/                       # 日志文件
│
├── scripts/                    # 工具脚本
│   ├── init_db.py              # 数据库初始化
│   ├── migrate_from_cf.py      # 从 CF Workers 迁移
│   └── backup_db.py            # 数据库备份
│
├── tests/                      # 测试
│
├── requirements.txt
├── .env.example
└── README.md
```

## API 端点

### 认证
- `POST /api/auth/login` - 管理员登录
- `POST /api/auth/logout` - 管理员登出
- `GET /api/auth/me` - 获取当前用户信息

### 用户管理
- `GET /api/users` - 获取所有用户
- `POST /api/users` - 添加新用户
- `PUT /api/users/{id}` - 更新用户信息
- `DELETE /api/users/{id}` - 删除用户
- `PATCH /api/users/{id}/toggle` - 启用/禁用用户

### 打卡操作
- `POST /api/clockin/trigger` - 触发所有用户打卡
- `POST /api/clockin/user/{id}` - 触发指定用户打卡
- `GET /api/clockin/status/{id}` - 查询任务状态
- `GET /api/clockin/results` - 获取打卡历史
- `GET /api/clockin/stats` - 获取统计数据
- `GET /api/clockin/stream` - SSE 实时推送

### 配置管理
- `GET /api/config` - 获取系统配置
- `PUT /api/config` - 更新系统配置

### 维护
- `POST /api/maintenance/cleanup` - 清理旧数据
- `POST /api/maintenance/backup` - 备份数据库
- `GET /api/maintenance/health` - 健康检查

## 环境变量

详见 `.env.example` 文件。

## 数据库备份

```bash
# 手动备份
python scripts/backup_db.py

# 定时备份（crontab）
0 3 * * * /path/to/venv/bin/python /path/to/scripts/backup_db.py
```

## 从 Cloudflare Workers 迁移

```bash
# 1. 导出 KV 数据
# 2. 运行迁移脚本
python scripts/migrate_from_cf.py kv_export.json
```

## 开发

### 运行测试

```bash
pytest tests/
```

### 代码格式化

```bash
black app/
isort app/
```

## 部署

详细的部署方案请参考 `REFACTOR_ADMIN_WORKER.md` 文档。

## 许可证

MIT

## 贡献

欢迎提交 Issue 和 Pull Request！
