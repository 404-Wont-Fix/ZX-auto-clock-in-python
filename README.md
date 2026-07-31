# ZX Auto Clock-in System

<div align="center">

---

## 📋 目录

- [项目简介](#项目简介)
- [为什么做这个项目](#为什么做这个项目)
- [系统架构](#系统架构)
- [功能特性](#功能特性)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [Docker 部署（推荐）](#docker-部署推荐)
- [传统部署（systemd）](#传统部署systemd)
- [开发文档](#开发文档)
- [常见问题](#常见问题)
- [贡献指南](#贡献指南)
- [许可证](#许可证)

---

## 🎯 项目简介

**ZX Auto Clock-in System** 是一个企业级的自动化打卡管理平台，专为需要管理大量用户打卡需求的场景设计。系统采用前后端分离架构，支持高并发、高可用的分布式打卡执行。

本系统包含两个核心组件：

1. **ZX Admin** - 基于 FastAPI 的管理后台（Python）
2. **Clockin Worker** - 基于 Cloudflare Workers 的打卡执行器（JavaScript）

### 核心亮点

- 🐳 **Docker 支持** - 一键部署，环境隔离，自动重启
- 🚀 **高性能** - 异步架构支持大规模用户并发打卡
- 🔄 **智能重试** - 多轮重试机制，错误类型识别，自适应延迟策略
- 📊 **实时监控** - SSE 实时推送打卡进度和任务状态
- 🎨 **内容丰富** - 集成古诗词、精美图片等多种打卡内容
- 🔐 **安全可靠** - JWT 认证、路径隐藏、健康监控
- ⚖️ **负载均衡** - 多 Worker API 轮询调度，自动故障转移
- 📈 **数据统计** - 打卡成功率分析、历史记录查询、每日汇总

---

## 💡 为什么做这个项目

### 业务痛点

1. **人工打卡效率低下**

   - 每天需要手动为多个用户打卡，耗时耗力
   - 容易遗漏或忘记打卡
   - 无法统一管理和监控打卡状态
2. **现有方案的局限性**

   - Cloudflare Workers 免费版有 CPU 时间限制（10ms）
   - 无法处理大规模用户的批量打卡
   - 缺乏友好的管理界面和统计数据
3. **企业级需求**

   - 需要支持多用户、多账号管理
   - 需要可靠的重试和容错机制
   - 需要详细的日志和数据分析

### 解决方案

本系统通过 **VPS + Cloudflare Workers 混合架构** 完美解决了上述问题：

| 方面     | 传统方案        | 本系统              |
| -------- | --------------- | ------------------- |
| 用户规模 | 受限（~10用户） | 无限制（异步并发）  |
| IP 安全  | VPS IP 暴露     | Cloudflare CDN 伪装 |
| 故障恢复 | 单点故障        | 多 API 冗余         |
| 管理界面 | 无或简陋        | 完整 Web 管理后台   |
| 实时监控 | 无              | SSE 实时推送        |
| 数据分析 | 无              | 完整统计和报表      |

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户浏览器                               │
│                    (访问管理面板 / API)                          │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP/HTTPS
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Nginx (可选)                                │
│                   反向代理 + SSL 终止                            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  ZX Admin (FastAPI)                              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  API Routes (FastAPI + Pydantic)                         │   │
│  │  - 认证授权 (JWT)                                         │   │
│  │  - 用户管理 (CRUD)                                        │   │
│  │  - 打卡操作 (异步并发)                                    │   │
│  │  - 数据统计 (聚合分析)                                    │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Business Logic Layer                                    │   │
│  │  - ClockinService (核心打卡逻辑)                          │   │
│  │  - WorkerApiService (API 负载均衡)                        │   │
│  │  - ActiveTaskService (任务追踪)                          │   │
│  │  - PoetryService (内容服务)                               │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Scheduler (APScheduler)                                 │   │
│  │  - 定时任务 (Cron)                                        │   │
│  │  - 数据清理 (自动归档)                                    │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Database (SQLite + SQLAlchemy)                          │   │
│  │  - 用户数据                                               │   │
│  │  - 打卡记录                                               │   │
│  │  - 统计汇总                                               │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP API Call
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│           Cloudflare Workers (负载均衡层)                        │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐                │
│  │ Worker API │  │ Worker API │  │ Worker API │  (多个实例)     │
│  │     #1     │  │     #2     │  │     #3     │                │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘                │
│        │                │                │                      │
│        └────────────────┴────────────────┘                      │
│                    (轮询调度 + 健康检查)                          │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      平台 API                                 │
│                   (实际打卡目标平台)                              │
└─────────────────────────────────────────────────────────────────┘
```

### 核心设计原则

1. **关注点分离** - 管理后台负责调度和监控，Worker 负责执行
2. **异步优先** - 全异步架构，最大化并发性能
3. **故障隔离** - Worker 故障不影响主系统，支持自动切换
4. **可扩展性** - 支持动态添加 Worker API 实例

---

## ✨ 功能特性

### 核心功能

#### 1. 用户管理

- ✅ 批量添加/编辑/删除用户
- ✅ 启用/禁用用户账号
- ✅ 用户打卡统计和成功率
- ✅ 自定义打卡配置（内容源、图片源等）

#### 2. 智能打卡系统

- ✅ **手动触发** - 一键打卡所有用户或指定用户
- ✅ **定时任务** - Cron 表达式配置自动打卡
- ✅ **并发控制** - 可配置最大并发数，避免过载
- ✅ **智能重试** - 多轮重试机制，错误类型识别
  - 超时错误：标准延迟重试
  - 频率限制（429）：加长延迟重试
  - 连接错误：短延迟快速重试
- ✅ **多轮重试** - 失败用户自动进入下一轮重试（最多3轮）

#### 3. Worker API 管理

- ✅ 多 API 负载均衡（Round-robin）
- ✅ 可用状态监控（`available` 字段，综合成功率和连续失败次数）
- ✅ 自动故障转移（跳过不可用的 API）
- ✅ 统计数据展示（总请求、成功数、成功率进度条）
- ✅ 动态添加/删除/启用/禁用 API

#### 4. 实时任务监控

- ✅ 概览页实时活动任务展示（3 秒轮询）
- ✅ 顶部栏活动任务徽标（快速感知执行状态）
- ✅ 活动任务列表（用户、Worker API、耗时）
- ✅ 底部状态栏（下次打卡时间、Worker 健康数）

#### 5. 内容服务集成

**评论内容源**：

- 📖 今日诗词（`jinrishici`，支持多种诗词分类）
- 💬 一言（`hitokoto`）
- 🌙 远梦API（`yuanmeng`）
- 🔗 KLapi（`klapi`）
- ✏️ 自定义内容（`custom`）

**图片内容源**：

- 🖼️ Bing 每日图片（`bing`，默认）
- 🌟 Bing UHD 高清壁纸（`bing_uhd`）
- 🎮 Komll API（`komll`）
- 🎨 LoliAPI ACG（`loliapi`）
- 🖌️ 次元API（`cimuapi`，支持分类筛选）

#### 6. 数据统计与报表

- ✅ 打卡成功率统计
- ✅ 历史记录查询（按日期、用户、状态筛选）
- ✅ 每日打卡汇总
- ✅ 用户打卡次数统计
- ✅ Worker API 性能分析

#### 7. 系统维护

- ✅ 数据库备份（一键导出）
- ✅ 数据清理（自动归档旧数据）
- ✅ 健康检查端点
- ✅ 日志查看和导出

#### 8. 安全特性

- ✅ JWT Token 认证（24小时有效期）
- ✅ Session 令牌验证（双重验证）
- ✅ 密码 bcrypt 加密存储
- ✅ 管理路径自定义（隐藏真实路径）
- ✅ CORS 跨域保护

---

## 🛠️ 技术栈

### ZX Admin (Python)

| 类别                  | 技术选型          | 说明                       |
| --------------------- | ----------------- | -------------------------- |
| **Web 框架**    | FastAPI 0.109     | 高性能异步 Web 框架        |
| **ASGI 服务器** | Uvicorn           | 支持 HTTP/1.1 和 WebSocket |
| **数据库**      | SQLite 3          | 轻量级关系型数据库         |
| **ORM**         | SQLAlchemy 2.0    | Python 最流行的 ORM        |
| **异步驱动**    | aiosqlite         | SQLAlchemy 异步适配器      |
| **数据验证**    | Pydantic v2       | 数据解析和验证             |
| **配置管理**    | pydantic-settings | 类型安全的配置管理         |
| **认证授权**    | python-jose       | JWT Token 生成/验证        |
| **密码加密**    | passlib + bcrypt  | 密码哈希和验证             |
| **HTTP 客户端** | httpx             | 现代化的异步 HTTP 客户端   |
| **定时任务**    | APScheduler       | Python 定时任务库          |
| **实时推送**    | sse-starlette     | Server-Sent Events 支持    |
| **时区处理**    | pytz              | 时区转换和处理             |

### 前端 (Admin UI)

| 类别                 | 技术选型           | 说明                               |
| -------------------- | ------------------ | ---------------------------------- |
| **CSS 框架**   | Tailwind CSS (CDN) | 原子化 CSS，无需构建               |
| **组件库**     | DaisyUI 4.x        | Tailwind 组件插件，内置 light 主题 |
| **JavaScript** | Vanilla JS         | 无框架依赖，单文件 SPA             |
| **布局**       | 侧边栏导航 SPA     | 5 个视图页面，hash 路由            |
| **设计风格**   | 浅色卡片式         | Linear/Notion 风格，柔和配色       |

### Clockin Worker (JavaScript)

| 类别                  | 技术选型            | 说明                 |
| --------------------- | ------------------- | -------------------- |
| **运行时**      | Cloudflare Workers  | 边缘计算平台         |
| **开发工具**    | Wrangler            | Cloudflare 官方 CLI  |
| **语言**        | JavaScript (ES2022) | 现代 JavaScript 特性 |
| **HTTP 客户端** | fetch API           | 原生 fetch           |

### DevOps

- **版本控制**: Git
- **反向代理**: Nginx (可选)
- **进程管理**: systemd / supervisor
- **SSL 证书**: Let's Encrypt (可选)

---

## 🚀 快速开始

### 环境要求

**Docker 部署（推荐）**：

- Docker 20.10+
- Docker Compose 2.0+
- 操作系统：Linux / macOS / Windows
- 内存：最低 512MB，推荐 1GB+
- 磁盘：最低 500MB 可用空间

**传统部署**：

- Python 3.11 或更高版本
- Node.js 18.x 或更高版本（仅部署 Worker 时需要）
- 操作系统：Linux / macOS / Windows

### 方式一：Docker 部署（最推荐）

```bash
# 1. 克隆仓库
git clone https://github.com/yourusername/ZK-auto-clock-in-python.git
cd ZK-auto-clock-in-python

# 2. 配置环境变量
cp .env.example .env
vim .env  # 编辑配置，至少配置 CLOCKIN_API_URL 和 CLOCKIN_API_TOKEN

# 3. 启动容器
docker-compose up -d

# 4. 访问应用
# 管理面板: http://localhost:8032/dashboard
# 默认账号: admin / admin（在 .env 中配置）
```

**Docker 优势**：一键启动、环境隔离、自动重启、易于维护 🎉

### 方式二：快速启动脚本（本地开发）

#### Windows

```powershell
# 进入项目目录
cd ZK-auto-clock-in-python

# 自动设置虚拟环境
.\setup_venv.bat

# 启动应用
.\start.bat
```

#### Linux / macOS

```bash
# 进入项目目录
cd ZK-auto-clock-in-python

# 自动设置虚拟环境
bash setup_venv.sh

# 启动应用
bash start.sh
```

### 方式二：手动安装

#### 1. 克隆仓库

```bash
git clone https://github.com/yourusername/ZK-auto-clock-in-python.git
cd ZK-auto-clock-in-python/ZK-auto-clock-in-python
```

#### 2. 创建虚拟环境

```bash
# Python 3.11+
python3 -m venv venv

# 激活虚拟环境
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate
```

#### 3. 安装依赖

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### 4. 配置环境变量

```bash
# 复制示例配置文件
cp .env.example .env

# 编辑配置文件
vim .env  # 或使用其他编辑器
```

**必要配置项**：

```bash
# 管理员账号（请修改为强密码）
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_password

# Clockin Worker API（必填）
CLOCKIN_API_URL=https://your-worker.workers.dev
CLOCKIN_API_TOKEN=your_worker_token

# 定时任务（Cron 表达式，默认北京时间 0:10）
SCHEDULE_CRON=0 10 0 * * *
SCHEDULE_TIMEZONE=Asia/Shanghai

# 数据保留天数
RETENTION_DAYS=7
```

#### 5. 初始化数据库

```bash
python scripts/init_db.py
```

#### 6. 启动应用

```bash
# 开发模式（自动重载）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 生产模式（4个工作进程）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 访问应用

启动成功后，在浏览器中访问：

| 界面               | 地址                            | 说明               |
| ------------------ | ------------------------------- | ------------------ |
| **管理面板** | http://localhost:8000/dashboard | 用户管理、打卡操作 |
| **API 文档** | http://localhost:8000/docs      | Swagger 交互式文档 |
| **替代文档** | http://localhost:8000/redoc     | ReDoc 文档         |

**默认账号**：

- 用户名：`admin`
- 密码：`admin`

⚠️ **重要**：请在部署前修改 .env 文件中的默认密码！

---

## 📦 部署指南

### 部署架构概览

```
Internet
    │
    ▼
┌─────────────┐
│   Nginx     │ (可选，反向代理 + SSL)
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│  Docker / systemd   │ (容器化/进程管理)
└──────┬──────────────┘
       │
       ▼
┌─────────────┐
│  Uvicorn    │ (ASGI 服务器)
│  (FastAPI)  │
└─────────────┘
```

---

## 🐳 Docker 部署（推荐）

Docker 部署是最简单、最推荐的方式，具有以下优势：

- ✅ **环境隔离** - 不污染宿主系统环境
- ✅ **一键部署** - 无需手动安装 Python 和依赖
- ✅ **自动重启** - 容器崩溃自动恢复
- ✅ **易于升级** - 重构镜像即可更新
- ✅ **资源限制** - 可限制 CPU 和内存使用

### 快速开始（Docker）

#### 1. 安装 Docker

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# CentOS/RHEL
sudo yum install -y docker
sudo systemctl start docker
sudo systemctl enable docker

# 验证安装
docker --version
docker-compose --version
```

#### 2. 配置环境变量

```bash
cd ZK-auto-clock-in-python

# 复制配置文件
cp .env.example .env

# 编辑配置（必须配置 Worker API）
vim .env
```

**最小配置**：

```bash
# 管理员账号
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_password

# Worker API（必填）
CLOCKIN_API_URL=https://your-worker.workers.dev
CLOCKIN_API_TOKEN=your_worker_token

# 定时任务
SCHEDULE_CRON=0 10 0 * * *
SCHEDULE_TIMEZONE=Asia/Shanghai
```

#### 3. 启动容器

```bash
# 构建并启动（后台运行）
docker-compose up -d

# 查看日志
docker-compose logs -f

# 查看运行状态
docker-compose ps
```

#### 4. 访问应用

- **管理面板**: http://localhost:8032/dashboard
- **API 文档**: http://localhost:8032/docs
- **默认账号**: admin / admin（在 .env 中配置）

⚠️ **重要**: 在使用时请修改配置文件中的默认账号密码！！

### Docker 常用命令

```bash
# 启动服务
docker-compose up -d

# 停止服务
docker-compose stop

# 重启服务
docker-compose restart

# 查看日志（实时）
docker-compose logs -f zk-admin

# 查看最近 100 行日志
docker-compose logs --tail=100 zk-admin

# 进入容器（调试用）
docker-compose exec zk-admin bash

# 在容器中执行命令
docker-compose exec zk-admin python scripts/backup_db.py

# 重新构建镜像（代码更新后）
docker-compose up -d --build

# 停止并删除容器
docker-compose down

# 停止并删除容器+数据卷（谨慎使用！）
docker-compose down -v

# 查看资源使用情况
docker stats zk-admin
```

### Docker Compose 配置说明

`docker-compose.yml` 关键配置：

| 配置项                      | 说明                           | 默认值            |
| --------------------------- | ------------------------------ | ----------------- |
| `ports`                   | 端口映射（宿主机:容器）        | `8032:8000`     |
| `restart`                 | 重启策略                       | `always`        |
| `volumes`                 | 数据挂载（数据库、日志、配置） | 见下方            |
| `TZ`                      | 时区                           | `Asia/Shanghai` |
| `healthcheck`             | 健康检查                       | 每 30s 检查一次   |
| `deploy.resources.limits` | 资源限制                       | 1核 / 512MB       |

**数据卷挂载**：

```yaml
volumes:
  - ./database:/app/database      # 数据库持久化
  - ./logs:/app/logs              # 日志文件
  - ./.env:/app/.env              # 配置文件（热更新）
```

### 修改端口映射

如果需要修改对外端口（如改为 8080）：

```bash
# 编辑 docker-compose.yml
vim docker-compose.yml

# 修改 ports 部分
ports:
  - "8080:8000"  # 宿主机端口改为 8080

# 重启服务
docker-compose up -d
```

### 多实例部署

如果需要运行多个实例（负载均衡）：

```bash
# 复制 docker-compose.yml 为 docker-compose.scale.yml
# 修改服务名称和端口
vim docker-compose.scale.yml

# 启动多个实例
docker-compose -f docker-compose.yml -f docker-compose.scale.yml up -d --scale zk-admin=3
```

### Docker 故障排查

#### 1. 容器无法启动

```bash
# 查看详细日志
docker-compose logs zk-admin

# 检查配置文件
cat .env

# 验证端口是否被占用
netstat -tuln | grep 8032
```

#### 2. 数据库丢失

```bash
# 检查数据卷是否正确挂载
docker-compose exec zk-admin ls -la /app/database

# 从宿主机备份恢复
cp database/zk_admin.db.backup database/zk_admin.db
docker-compose restart zk-admin
```

#### 3. 内存不足

```bash
# 查看资源使用
docker stats zk-admin

# 调整 docker-compose.yml 中的内存限制
deploy:
  resources:
    limits:
      memory: 1G  # 增加到 1GB
```

#### 4. 时区不正确

```bash
# 检查容器时区
docker-compose exec zk-admin date

# 确保 docker-compose.yml 中设置了 TZ=Asia/Shanghai
```

### Docker 升级

```bash
# 1. 备份数据
docker-compose exec zk-admin python scripts/backup_db.py
cp -r database database.backup

# 2. 拉取最新代码
git pull

# 3. 重新构建并启动
docker-compose up -d --build

# 4. 清理旧镜像（可选）
docker image prune -f
```

---

## 📦 传统部署（systemd）

如果你不想使用 Docker，也可以使用传统的 systemd 部署方式。

#### 1. 安装 Wrangler

```bash
npm install -g wrangler
```

#### 2. 登录 Cloudflare

```bash
wrangler login
```

#### 3. 配置 Worker

编辑 `clockin-worker/wrangler.toml`：

```toml
name = "zk-clockin-executor-01"  # 修改为你的 Worker 名称
main = "worker.js"
compatibility_date = "2026-02-24"

workers_dev = true
preview_urls_setting = "disabled"

[vars]
ENVIRONMENT = "production"
API_TOKEN = "your-secure-token-here"  # 修改为安全的 Token
ENABLE_LOGGING = "false"  # 生产环境建议关闭日志
```

#### 4. 部署 Worker

```bash
cd clockin-worker
wrangler deploy
```

部署成功后会显示：

```
Published zk-clockin-executor-01 (1.23 sec)
  https://zk-clockin-executor-01.your-subdomain.workers.dev
```

#### 5. 部署多个 Worker（推荐）

为了高可用，建议部署多个 Worker 实例：

```bash
# 修改 wrangler.toml 中的 name
# 重新部署
wrangler deploy
```

记录每个 Worker 的 URL 和 Token，稍后需要在 Admin 中配置。

### 二、部署 ZK Admin

#### 1. 服务器环境准备

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y  # Ubuntu/Debian

# 安装 Python 3.11+
sudo apt install python3.11 python3.11-venv python3-pip -y

# 安装 Nginx（可选）
sudo apt install nginx -y

# 安装 git
sudo apt install git -y
```

#### 2. 部署应用

```bash
# 克隆代码
git clone https://github.com/yourusername/ZK-auto-clock-in-python.git
cd ZK-auto-clock-in-python/ZK-auto-clock-in-python

# 创建虚拟环境
python3.11 -m venv venv
source venv/bin/activate

# 安装依赖
pip install --upgrade pip
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
vim .env  # 编辑配置

# 初始化数据库
python scripts/init_db.py
```

#### 3. 创建 systemd 服务

创建服务文件 `/etc/systemd/system/zk-clockin.service`：

```ini
[Unit]
Description=ZK Auto Clock-in Service
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/path/to/ZK-auto-clock-in-python/ZK-auto-clock-in-python
Environment="PATH=/path/to/ZK-auto-clock-in-python/ZK-auto-clock-in-python/venv/bin"
ExecStart=/path/to/ZK-auto-clock-in-python/ZK-auto-clock-in-python/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4
Restart=always
RestartSec=10

# 日志
StandardOutput=append:/var/log/zk-clockin/app.log
StandardError=append:/var/log/zk-clockin/error.log

[Install]
WantedBy=multi-user.target
```

创建日志目录：

```bash
sudo mkdir -p /var/log/zk-clockin
sudo chown www-data:www-data /var/log/zk-clockin
```

启动服务：

```bash
# 重载 systemd 配置
sudo systemctl daemon-reload

# 启动服务
sudo systemctl start zk-clockin

# 设置开机自启
sudo systemctl enable zk-clockin

# 查看状态
sudo systemctl status zk-clockin

# 查看日志
sudo journalctl -u zk-clockin -f
```

#### 4. 配置 Nginx（可选）

创建 Nginx 配置 `/etc/nginx/sites-available/zk-clockin`：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 重定向到 HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL 证书（使用 Let's Encrypt）
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # SSL 配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;

    # 日志
    access_log /var/log/nginx/zk-clockin-access.log;
    error_log /var/log/nginx/zk-clockin-error.log;

    # 反向代理到 FastAPI
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket 支持（SSE）
        proxy_buffering off;
        proxy_cache off;
    }

    # 静态文件缓存
    location /assets {
        proxy_pass http://127.0.0.1:8000;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

启用配置：

```bash
# 创建符号链接
sudo ln -s /etc/nginx/sites-available/zk-clockin /etc/nginx/sites-enabled/

# 测试配置
sudo nginx -t

# 重载 Nginx
sudo systemctl reload nginx
```

#### 5. 配置 SSL（Let's Encrypt）

```bash
# 安装 Certbot
sudo apt install certbot python3-certbot-nginx -y

# 获取证书
sudo certbot --nginx -d your-domain.com

# 自动续期
sudo certbot renew --dry-run
```

### 三、配置 Worker API

登录管理后台，添加 Worker API：

1. 访问 `https://your-domain.com/admin`
2. 登录后点击左侧侧边栏 "Worker API"
3. 点击右上角 "+ 添加 API"
4. 填写信息：
   - **名称**: `Worker 01`
   - **URL**: `https://zk-clockin-executor-01.your-subdomain.workers.dev`
   - **Token**: `your-secure-token`
5. 点击 "保存配置"

重复以上步骤添加多个 Worker API。

### 四、验证部署

1. **健康检查**：访问 `https://your-domain.com/api/maintenance/health`
2. **测试打卡**：添加测试用户，手动触发打卡
3. **查看日志**：
   ```bash
   sudo journalctl -u zk-clockin -f
   tail -f /path/to/ZK-auto-clock-in-python/ZK-auto-clock-in-python/logs/app.log
   ```

---

## 👨‍💻 开发文档

### 项目结构

```
ZK-auto-clock-in-python/
├── ZK-auto-clock-in-python/          # Python Admin
│   ├── app/
│   │   ├── api/                       # API 路由
│   │   │   ├── auth.py               # 认证相关
│   │   │   ├── users.py              # 用户管理
│   │   │   ├── clockin.py            # 打卡操作
│   │   │   ├── config.py             # 配置管理
│   │   │   ├── maintenance.py        # 维护操作
│   │   │   └── worker_api.py         # Worker API 管理
│   │   ├── services/                  # 业务逻辑层
│   │   │   ├── clockin_service.py    # 打卡核心逻辑
│   │   │   ├── user_service.py       # 用户 CRUD
│   │   │   ├── poetry_service.py     # 内容服务
│   │   │   ├── worker_api_service.py # Worker API 管理
│   │   │   ├── active_task_service.py# 任务追踪
│   │   │   └── config_service.py     # 配置管理
│   │   ├── models/                    # 数据模型
│   │   │   ├── database.py           # SQLAlchemy 模型
│   │   │   └── schemas.py            # Pydantic 模型
│   │   ├── core/                      # 核心功能
│   │   │   ├── database.py           # 数据库连接
│   │   │   ├── security.py           # 安全工具
│   │   │   └── scheduler.py          # 定时任务
│   │   ├── ui/                        # 前端界面 (Tailwind + DaisyUI)
│   │   │   ├── pages/                # HTML 页面
│   │   │   │   ├── index.html        # 主 SPA（侧边栏 + 5 个视图）
│   │   │   │   ├── login.html        # 登录页
│   │   │   │   └── 404.html          # Nginx 伪装页
│   │   │   ├── assets/               # 静态资源
│   │   │   │   ├── app.js            # SPA 逻辑（路由、数据、渲染）
│   │   │   │   ├── styles.css        # 自定义样式补充
│   │   │   │   ├── login.css         # 登录页样式
│   │   │   │   └── login.js          # 登录逻辑
│   │   │   └── html.js               # HTML 导出模块（未使用）
│   │   ├── config.py                  # 配置管理
│   │   └── main.py                    # 应用入口
│   ├── database/                      # 数据库文件
│   ├── logs/                          # 日志文件
│   ├── scripts/                       # 工具脚本
│   ├── tests/                         # 测试代码
│   ├── requirements.txt               # Python 依赖
│   ├── .env.example                   # 环境变量示例
│   ├── setup_venv.sh/bat              # 虚拟环境设置脚本
│   └── start.sh/bat                   # 快速启动脚本
├── clockin-worker/                    # Cloudflare Worker
│   ├── modules/                       # 功能模块
│   │   ├── clockin/                  # 打卡逻辑
│   │   ├── image.js                  # 图片处理
│   │   ├── upload.js                 # 文件上传
│   │   ├── auth.js                   # 认证验证
│   │   └── utils/                    # 工具函数
│   ├── worker.js                      # Worker 入口
│   ├── wrangler.toml                  # Worker 配置
│   └── package.json                   # NPM 配置
├── CLAUDE.md                          # Claude Code 指导文档
└── README.md                          # 本文件
```

### 开发环境搭建

```bash
# 1. 克隆仓库
git clone https://github.com/yourusername/ZK-auto-clock-in-python.git
cd ZK-auto-clock-in-python

# 2. 设置 Python Admin
cd ZK-auto-clock-in-python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/init_db.py

# 3. 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 4. 本地开发 Worker（另一个终端）
cd clockin-worker
npm install
wrangler dev --local
```

### 开发命令

```bash
# 运行测试
pytest tests/

# 代码格式化
black app/
isort app/

# 类型检查
mypy app/

# 数据库操作
python scripts/init_db.py          # 初始化数据库
python scripts/backup_db.py        # 备份数据库
python scripts/check_db.py         # 检查数据库完整性
python scripts/check_result.py     # 检查打卡结果

# API 测试
python scripts/test_api.py
python scripts/test_apis.py
```

### 添加新功能

#### 1. 添加新的 API 端点

```python
# 1. 在 app/models/schemas.py 中定义请求/响应模型
class NewFeatureRequest(BaseModel):
    name: str
    value: int

class NewFeatureResponse(BaseModel):
    success: bool
    data: Optional[dict]

# 2. 在 app/services/ 中创建服务方法
class NewFeatureService:
    @staticmethod
    async def do_something(db: AsyncSession, params: NewFeatureRequest) -> dict:
        # 业务逻辑
        return {'success': True, 'data': {}}

# 3. 在 app/api/ 中创建路由
from fastapi import APIRouter, Depends
from app.core.database import get_db
from app.models.schemas import NewFeatureRequest, NewFeatureResponse
from app.services.new_feature_service import NewFeatureService

router = APIRouter(prefix='/api/new-feature', tags=['New Feature'])

@router.post('/', response_model=NewFeatureResponse)
async def create_new_feature(
    request: NewFeatureRequest,
    db: AsyncSession = Depends(get_db)
):
    result = await NewFeatureService.do_something(db, request)
    return result

# 4. 在 app/main.py 中注册路由
from app.api.new_feature import router as new_feature_router
app.include_router(new_feature_router)
```

#### 2. 添加新的数据库模型

```python
# 在 app/models/database.py 中
class NewModel(Base):
    __tablename__ = 'new_models'

    id = Column(String, primary_key=True, default=lambda: generate_uuid())
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
```

### 前端架构

管理面板采用 **侧边栏导航 SPA** 设计，基于 **Tailwind CSS + DaisyUI** 组件库：

```
┌─────────────────────────────────────────────────┐
│  侧边栏 (220px)  │  顶部栏 (标题 + 任务徽标)   │
│                   │                             │
│  ⚡ 打卡系统       │  主内容区 (hash 路由切换)   │
│                   │                             │
│  📊 概览           │  ┌─────┬─────┬─────┬─────┐ │
│  👥 用户管理       │  │统计 │统计 │统计 │统计 │ │
│  📋 打卡记录       │  └─────┴─────┴─────┴─────┘ │
│  🔗 Worker API    │  快速操作卡片               │
│  ⚙ 系统设置       │  今日打卡概况               │
│                   │                             │
│  🚪 退出           │  底部状态栏                 │
└───────────────────┴─────────────────────────────┘
```

**5 个视图页面**：

- **概览** (`#/dashboard`): 统计卡片 + 活动任务 + 快速操作 + 今日概况
- **用户管理** (`#/users`): 搜索/筛选/排序表格 + 右侧抽屉编辑
- **打卡记录** (`#/records`): 日期范围筛选 + 按日分组 + 3 类型状态指示器
- **Worker API** (`#/apis`): 卡片网格 + 健康状态 + 成功率进度条
- **系统设置** (`#/settings`): 打卡配置 + 定时任务 + 数据管理

**3 个打卡类型指标**（H/S/D）：

- 用户表格每行显示首页/运动/每日 3 个打卡状态
- 记录详情展示每个类型的执行结果和备注
- 数据来源：`ClockinResult.details` JSON 字段（`{home, sports, daily}`）

**设计系统**：

- 浅色主题，白色卡片 (`#FFFFFF`)，灰色画布 (`#F8F9FA`)
- 主色 `#4A90E2`，成功 `#52C41A`，错误 `#FF4D4F`
- 极轻阴影 (`0 1px 3px rgba(0,0,0,0.04)`)，12px 圆角

### 调试技巧

1. **启用调试日志**：在 `.env` 中设置 `DEBUG=true` 和 `LOG_LEVEL=DEBUG`
2. **查看 SQL 语句**：临时修改 `main.py` 中的日志级别
3. **测试单个 API**：使用 Swagger 文档 (`/docs`) 或 `curl`
4. **查看活动任务**：访问 `/api/clockin/active-tasks`
5. **监控 Worker 健康**：侧边栏 → "Worker API" 查看各节点状态

### 代码规范

- **Python**: 遵循 PEP 8，使用 Black 和 isort 格式化
- **命名**: 使用 snake_case（变量/函数）和 PascalCase（类）
- **注释**: 关键逻辑必须添加注释
- **类型注解**: 所有函数必须添加类型提示
- **错误处理**: 服务层返回 `{'success': bool, 'error': str}`

---

## ❓ 常见问题

### Docker 相关问题

#### 1. Docker 容器无法启动

**问题**：`docker-compose up` 后容器立即退出

**解决方案**：

```bash
# 查看详细日志
docker-compose logs zk-admin

# 常见原因1：.env 文件不存在或配置错误
ls -la .env
cat .env

# 常见原因2：端口被占用
netstat -tuln | grep 8032
# 修改 docker-compose.yml 中的端口映射

# 常见原因3：数据库目录权限问题
chmod -R 755 database logs
```

#### 2. Docker 容器内存不足

**问题**：容器被 OOM Killer 杀死

**解决方案**：

```bash
# 编辑 docker-compose.yml，增加内存限制
deploy:
  resources:
    limits:
      memory: 1G  # 从 512M 增加到 1G

# 重启容器
docker-compose up -d
```

#### 3. Docker 数据持久化失败

**问题**：重启容器后数据丢失

**解决方案**：

```bash
# 确认数据卷挂载正确
docker-compose ps
# 查看 MOUNTS 部分，应该有：
# ./database -> /app/database
# ./logs -> /app/logs

# 检查宿主机目录
ls -la database/
ls -la logs/

# 数据备份
docker-compose exec zk-admin python scripts/backup_db.py
```

#### 4. 修改 .env 后不生效

**问题**：修改了 .env 文件，但容器内配置没有更新

**解决方案**：

```bash
# 方法1：重启容器（推荐）
docker-compose restart zk-admin

# 方法2：重新构建（如果修改了 Dockerfile）
docker-compose up -d --build

# 方法3：进入容器验证配置
docker-compose exec zk-admin cat /app/.env
```

#### 5. 查看 Docker 容器日志

**解决方案**：

```bash
# 实时查看所有日志
docker-compose logs -f

# 查看最近 100 行
docker-compose logs --tail=100 zk-admin

# 查看特定时间的日志
docker-compose logs --since 2024-01-01T00:00:00 zk-admin

# 导出日志到文件
docker-compose logs zk-admin > logs/docker.log
```

#### 6. Docker 容器时间不正确

**问题**：容器内时间与宿主机不一致

**解决方案**：

```bash
# 1. 检查容器时区
docker-compose exec zk-admin date

# 2. 确保 docker-compose.yml 中设置了 TZ
environment:
  - TZ=Asia/Shanghai

# 3. 重启容器
docker-compose restart zk-admin
```

### 传统部署问题

### 7. 数据库锁定错误

**问题**：`sqlite3.OperationalError: database is locked`

**解决方案**：

```bash
rm database/*.db-journal
# 或重启应用
sudo systemctl restart zk-clockin
```

### 8. 端口被占用

**问题**：`Error: Address already in use`

**解决方案**：

```bash
# Linux/Mac
lsof -i :8000
kill -9 <PID>

# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

### 9. 打卡全部失败

**问题**：所有用户打卡都显示 "没有可用的 Worker API"

**解决方案**：

1. 检查侧边栏 → "Worker API"，确保至少有一个 API 已启用
2. 测试 Worker URL：`curl https://your-worker.workers.dev`
3. 检查 Worker Token 是否正确
4. 查看 Worker 日志：`wrangler tail`

### 10. 频率限制（429错误）

**问题**：大量用户打卡时出现 429 错误

**解决方案**：

1. 在 `.env` 中增加 `CLOCKIN_RATE_LIMIT_DELAY=15`
2. 减少 `PARALLEL_TASKS=2`
3. 部署更多 Worker API 实例

### 11. 虚拟环境激活失败（Windows）

**问题**：PowerShell 提示无法运行脚本

**解决方案**：

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 12. 定时任务未执行

**问题**：到了设定时间但没有自动打卡

**解决方案**：

1. 检查 `.env` 中的 `SCHEDULE_ENABLED=true`
2. 验证 Cron 表达式是否正确：[Cron 验证工具](https://crontab.guru/)
3. 查看应用日志：`tail -f logs/app.log`
4. 确认时区设置：`SCHEDULE_TIMEZONE`

### 13. 忘记管理员密码

**解决方案**：

```bash
# 管理员账号和密码存储在 .env 文件中
vim .env
# 修改 ADMIN_PASSWORD 为新密码
# 重启服务使配置生效
sudo systemctl restart zk-clockin  # 传统部署
docker-compose restart zk-admin     # Docker 部署
```

---

## 🤝 贡献指南

欢迎贡献代码、报告问题或提出建议！

### 如何贡献

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

### 开发规范

- 遵循现有代码风格
- 添加必要的测试
- 更新相关文档
- 提交信息清晰明了

---

## 📄 许可证

本项目采用 [MIT 许可证](LICENSE)。

---

## 🙏 致谢

- [FastAPI](https://fastapi.tiangolo.com/) - 现代化的 Python Web 框架
- [Cloudflare Workers](https://workers.cloudflare.com/) - 边缘计算平台
- [SQLAlchemy](https://www.sqlalchemy.org/) - Python SQL 工具包和 ORM
- [APScheduler](https://github.com/agronholm/apscheduler) - Python 定时任务库

---

## 📞 联系方式

- **Issues**: [GitHub Issues](https://github.com/yourusername/ZK-auto-clock-in-python/issues)
- **Email**: your-email@example.com

---

<div align="center">
