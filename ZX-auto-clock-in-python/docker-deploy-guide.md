# Docker Compose 部署指南

本文档对应 ZX Admin 2.0。Compose 只启动一个 Uvicorn 进程，由该进程唯一持有 APScheduler 和进程内后台任务。

## 先确认安全边界

若通过“公网 IP + HTTP”访问后台，传输中的管理员口令、足下账号密码和 Worker Token 等凭据会面临被窃听或篡改的风险，不能视为安全生产入口。能配置域名和 TLS 时，应优先使用 HTTPS、VPN 或可信反向代理。

发布探测不要使用真实打卡账号。

## 准备环境

需要 Docker Engine 与 Docker Compose v2。进入 Python Admin 目录：

```bash
cd ZX-auto-clock-in-python
cp .env.example .env
mkdir -p database logs
```

编辑 `.env`，至少修改以下项目：

```dotenv
APP_ENV=production
DEBUG=false
SECRET_KEY=替换为足够长的随机值
ADMIN_USERNAME=替换为非空管理员名
ADMIN_PASSWORD=替换为强密码
ADMIN_PATH=替换为不易猜测的后台入口路径
DATABASE_URL=sqlite:///database/zx_admin.db
```

生产模式会拒绝默认 `SECRET_KEY`、空管理员名以及空密码或 `admin` 密码。`.env` 不会复制进镜像，也不应提交到 Git。

`CLOCKIN_API_TOKEN` 是旧版后备配置，示例文件故意留空。新版应在“系统设置 → Worker 节点”中添加 Worker 地址和 Token；普通 API 与 2.0 导出都不会回显完整 Token。

## 校验并启动

```bash
docker compose config
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f zx-admin
```

Compose 使用以下运行约束：

- 单个 Uvicorn 进程，避免重复调度和重复后台任务。
- `./database` 挂载到 `/app/database`，保存全新 SQLite。
- `./logs` 挂载到 `/app/logs`。
- `/health` 同时检查 Web 进程和 SQLite 查询能力。
- `.env` 通过 `env_file` 注入，修改后需重启容器。

健康检查：

```bash
curl http://127.0.0.1:8032/health
docker inspect --format '{{.State.Health.Status}}' zx-admin
```

健康响应应包含 `"status":"healthy"` 和 `"database":"ready"`。后台入口不是 `/dashboard`，请访问：

```text
http://服务器IP:8032/你的 ADMIN_PATH
```

## 全新 SQLite 与旧配置导入

新版部署使用全新 SQLite，不对旧数据库做原地迁移。首次启动会自动建表并初始化默认内容源。

需要恢复旧数据时，在旧版后台导出 `1.0` 配置文件，然后在新版“系统设置 → 数据导入导出”中导入。1.0 文件可能包含明文用户密码和 Worker Token：

1. 只在受控设备上短暂保存和传输。
2. 导入响应和日志不会回显密钥。
3. 导入完成后立即安全删除旧文件。
4. 对曾提交、共享或暴露过的 Worker Token 进行轮换。

新版 `2.0` 普通导出使用 `zx-admin-config-YYYY-MM-DD.json` 文件名，不含用户密码或 Worker Token，适合日常保存非敏感配置，但不能独立恢复这些密钥；在全新数据库上仍需重新输入缺失的密码和 Token。旧版 `batch_size`、`batch_delay`、`parallel_tasks` 会在导入后保留，并继续出现在安全导出中。

## 验证数据库持久化

先确认健康状态，再重启容器：

```bash
docker compose exec zx-admin python scripts/check_db.py
docker compose restart zx-admin
docker compose ps
docker compose exec zx-admin python scripts/check_db.py
curl http://127.0.0.1:8032/health
```

重启前后都应能读取同一 `./database/zx_admin.db`。备份时保留宿主机文件：

```bash
docker compose exec zx-admin python scripts/backup_db.py
```

不要用 `docker compose down -v` 作为常规操作。当前 Compose 使用宿主机目录挂载，但任何清理命令执行前都应先确认备份。

## 部署并轮换 Cloudflare Worker Token

Worker 与 Admin 分开部署。仓库不再包含固定 Token，本地 `.dev.vars` 也被 Git 忽略。

```bash
cd ../clockin-worker
npx wrangler secret put API_TOKEN
npx wrangler deploy
```

将同一个新 Token 填入 Admin 的 Worker 节点抽屉。历史已泄露的 Token 不得复用；轮换后逐个测试 Worker 节点。

## 更新与回滚

更新前先备份数据库，然后重新构建：

```bash
docker compose exec zx-admin python scripts/backup_db.py
git pull --ff-only
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8032/health
```

本轮提交按内容源、后台任务、界面、安全导入和部署文档拆分，可按相反顺序逐块回滚。回滚应用版本时不要恢复已泄露的 Token；若新版数据不可用，应切回备份文件或重新创建数据库，而不是对旧 SQLite 做未经验证的原地变更。

## 常见问题

### 容器启动后立即退出

```bash
docker compose logs --tail=200 zx-admin
```

优先检查 `.env` 是否仍使用默认安全配置。Compose 固定以 `APP_ENV=production` 启动，因此弱默认值会按设计拒绝启动。

### 修改 `.env` 后未生效

```bash
docker compose up -d --force-recreate
```

### 健康状态为 unhealthy

```bash
docker compose logs --tail=200 zx-admin
ls -la database logs
curl -i http://127.0.0.1:8032/health
```

确认宿主机目录可写、SQLite 文件未损坏，并检查 8032 端口是否被占用。

### 计划任务重复执行

确认镜像的 Uvicorn 启动参数仍为 `--workers 1`，且没有同时启动第二套 Admin 容器。不要横向扩容此 Compose 服务。
