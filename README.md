# ZK Auto Clock-in System

ZK 多用户自动打卡系统，支持大规模用户管理。

## 项目概述

本仓库包含两个子项目：

| 子项目 | 描述 | 技术栈 |
|--------|------|--------|
| [`ZK-auto-clock-in-python/`](./ZK-auto-clock-in-python/) | **Python Admin** - 管理后台，部署在 VPS | FastAPI, SQLite, APScheduler |
| [`clockin-worker/`](./clockin-worker/) | **Cloudflare Worker** - 打卡执行器 | JavaScript, Cloudflare Workers |

### 系统架构

```
浏览器 → Nginx → FastAPI (Python Admin) → SQLite
                              ↓
                    Cloudflare Worker (clockin-worker)
                              ↓
                        精夏平台 API
```

### 为什么保留 Cloudflare Worker

- **IP 隐藏**：VPS IP 不直接暴露给精夏平台
- **分散请求**：请求来源为 Cloudflare CDN IP
- **降级保护**：即使 VPS 故障，clockin-worker 仍可独立使用

---

## Python Admin (ZK-auto-clock-in-python/)

Python 版本的管理后台，突破 Cloudflare Workers 免费账户的限制，支持大规模用户管理。

### 主要功能

- **用户管理**：支持批量添加、编辑、删除用户
- **自动打卡**：定时任务自动触发打卡，支持手动触发
- **实时推送**：SSE 实时推送打卡进度和结果
- **数据统计**：打卡成功率、历史记录查询
- **健康检查**：系统状态监控、数据库维护
- **诗词 API**：集成古诗词/图片内容服务

### 技术栈

| 类别 | 技术 |
|------|------|
| Web 框架 | FastAPI |
| 数据库 | SQLite + SQLAlchemy + aiosqlite |
| 异步支持 | asyncio + httpx |
| 定时任务 | APScheduler |
| 认证 | JWT (python-jose) |
| 密码加密 | bcrypt |
| 实时推送 | SSE (sse-starlette) |
| 配置管理 | pydantic-settings |
| ASGI 服务器 | Uvicorn |

### 快速开始

#### 方式一：使用快速启动脚本（推荐）

**Windows:**
```bash
cd ZK-auto-clock-in-python
setup_venv.bat
start.bat
```

**Linux/Mac:**
```bash
cd ZK-auto-clock-in-python
bash setup_venv.sh
bash start.sh
```

#### 方式二：手动安装

```bash
cd ZK-auto-clock-in-python

# 1. 创建虚拟环境
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，修改必要配置

# 4. 初始化数据库
python scripts/init_db.py

# 5. 启动应用
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 访问应用

打开浏览器访问：
- **管理面板**：http://localhost:8000/dashboard
- **API 文档**：http://localhost:8000/docs
- **默认账号**：admin / admin

> **重要**：首次登录后请立即修改管理员密码！

### 项目目录结构

```
ZK-auto-clock-in-python/
├── app/
│   ├── main.py                 # FastAPI 应用入口
│   ├── config.py               # 配置管理
│   ├── models/
│   │   └── schemas.py          # Pydantic 数据模型
│   ├── api/                    # API 路由
│   │   ├── auth.py             # 认证相关
│   │   ├── users.py            # 用户管理
│   │   ├── clockin.py          # 打卡操作
│   │   ├── config.py           # 配置管理
│   │   └── maintenance.py      # 维护操作
│   ├── services/               # 业务逻辑层
│   │   ├── clockin_service.py  # 打卡服务
│   │   ├── poetry_service.py   # 诗词/图片服务
│   │   ├── task_service.py     # 任务管理
│   │   └── user_service.py     # 用户服务
│   ├── core/                   # 核心功能
│   │   ├── database.py         # 数据库连接
│   │   ├── scheduler.py        # 定时任务配置
│   │   └── security.py         # 密码加密、JWT
│   └── ui/                     # 前端静态文件
│       ├── pages/              # 页面文件
│       └── assets/             # 静态资源
├── database/                   # 数据库目录
├── logs/                       # 日志目录
├── scripts/                    # 工具脚本
├── requirements.txt            # Python 依赖
├── .env.example                # 环境变量示例
├── setup_venv.sh/bat           # 虚拟环境设置脚本
└── start.sh/bat                # 快速启动脚本
```

### API 端点

| 类别 | 端点 | 说明 |
|------|------|------|
| 认证 | `POST /api/auth/login` | 管理员登录 |
| | `POST /api/auth/logout` | 管理员登出 |
| | `GET /api/auth/me` | 获取当前用户信息 |
| 用户管理 | `GET /api/users/` | 获取所有用户 |
| | `POST /api/users/` | 添加新用户 |
| | `PUT /api/users/{id}` | 更新用户信息 |
| | `DELETE /api/users/{id}` | 删除用户 |
| | `PATCH /api/users/{id}/toggle` | 启用/禁用用户 |
| 打卡操作 | `POST /api/clockin/trigger` | 触发所有用户打卡 |
| | `POST /api/clockin/user/{id}` | 触发指定用户打卡 |
| | `GET /api/clockin/results` | 获取打卡历史 |
| | `GET /api/clockin/stats` | 获取统计数据 |
| | `GET /api/clockin/stream` | SSE 实时推送 |
| 配置管理 | `GET /api/config/` | 获取系统配置 |
| | `PUT /api/config/` | 更新系统配置 |
| 维护 | `POST /api/maintenance/cleanup` | 清理旧数据 |
| | `POST /api/maintenance/backup` | 备份数据库 |
| | `GET /api/maintenance/health` | 健康检查 |
| 诗词 API | `GET /api/poetry/daily` | 获取每日诗词 |
| | `GET /api/poetry/random` | 获取随机诗词 |
| | `GET /api/poetry/image` | 获取每日图片 |

### 常用操作

```bash
# 停止服务：Ctrl + C

# 查看日志
tail -f logs/app.log

# 数据库备份
python scripts/backup_db.py

# 数据库初始化（重置）
python scripts/init_db.py
```

### 环境变量说明

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `APP_NAME` | 应用名称 | ZK Admin |
| `ADMIN_USERNAME` | 管理员用户名 | admin |
| `ADMIN_PASSWORD` | 管理员密码 | admin |
| `CLOCKIN_API_URL` | 打卡 API 地址 | - |
| `CLOCKIN_API_TOKEN` | 打卡 API 令牌 | - |
| `SCHEDULE_CRON` | 定时任务 Cron 表达式 | 0 10 16 * * * (UTC) |
| `RETENTION_DAYS` | 数据保留天数 | 7 |

> 完整配置请参考 [ZK-auto-clock-in-python/.env.example](./ZK-auto-clock-in-python/.env.example)

### 部署

```ini
# systemd 服务示例
[Unit]
Description=ZK Auto Clock-in Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/ZK-auto-clock-in-python
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

### 故障排查

**数据库锁定**
```bash
rm database/*.db-journal
```

**端口被占用**
```bash
lsof -i :8000          # Linux/Mac
netstat -ano | findstr :8000   # Windows
```

**虚拟环境激活失败**
```bash
# Windows PowerShell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## Clockin Worker (clockin-worker/)

Cloudflare Worker 版本的打卡执行器，部署在 Cloudflare 边缘网络。

### 技术栈

- **运行时**: Cloudflare Workers
- **存储**: Workers KV / D1
- **语言**: JavaScript

### 部署

```bash
cd clockin-worker
npx wrangler deploy
```

---

## 开发

### Python Admin

```bash
cd ZK-auto-clock-in-python

# 运行测试
pytest tests/

# 代码格式化
black app/
isort app/
```

---

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
