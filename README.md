# ZX Auto Clock-in System

ZX 是一个面向足下教育现代化学习平台的单管理员、多账号自动打卡控制台，包含 FastAPI Admin、SQLite 数据库、原生浏览器后台和独立的 Cloudflare Worker 执行器：Admin 负责账号、内容源与任务编排，Worker 负责与目标平台的打卡接口交互（首页、运动、日精进等）。

内容源支持文字与图片的可视化管理，后台信息架构围绕五个一级页面组织。

## ⚠️ 免责声明

**本项目仅供技术学习、研究与交流用途。**

- 本项目与足下教育（以及其他任何相关平台、组织）**没有任何关联**，亦未获得其任何形式的授权、支持或认可；
- 使用者应遵守所在地区法律法规及目标平台的服务条款，**因下载、部署、使用或滥用本项目所产生的一切后果，均由使用者自行承担**；
- 本项目按“现状”提供，不提供任何明示或默示的保证；
- 如本项目侵犯了任何组织或个人的合法权益，请提交 Issue，我们将及时处理。

继续使用本项目即视为已阅读并同意本声明。

## 安全提示

若通过“公网 IP + HTTP”部署，传输中的管理员口令、足下账号密码和 Worker Token 会面临被窃听或篡改的风险，不能视为安全生产入口；条件允许时应使用 HTTPS、VPN 或可信反向代理。

仓库不包含可用的固定 Worker Token。部署 Worker 时使用：

```bash
cd clockin-worker
npx wrangler secret put API_TOKEN
npx wrangler deploy
```

历史已泄露的 Token 不得复用。

## 当前能力

后台固定为五个一级页面：

- 总览：今日成功、失败、未执行、下次计划、任务进度、Worker 与内容源健康，以及失败重试。
- 用户：本地搜索筛选、单人打卡、编辑、启停和收纳在更多菜单中的删除操作。
- 打卡记录：日期、状态和用户筛选，三类结果摘要与详情抽屉。
- 内容源：文字/图片分组、健康与延迟、排序、复制、编辑、归档、单测和全测。
- 系统设置：计划任务、Worker 节点、2.0 导出、1.0 兼容导入、备份和危险维护操作。

桌面端使用侧栏，手机端使用四项底部导航；内容源和系统设置收进“更多”。高频操作在页面或一级抽屉内完成，危险操作增加一次确认，不使用嵌套弹窗。

前端为原生 HTML/CSS/ES Modules，没有生产构建链或运行时组件 CDN。主题深色优先，并根据系统浅色偏好自动切换。

## 内容源

Admin 将内容源保存为受控数据库配置，只允许公网 HTTPS GET，并支持以下解析模式：

- `json_text`
- `plain_text`
- `json_image`
- `redirect_image`

域名解析结果和每次重定向都会重新执行 SSRF 校验；本机、内网、链路本地和保留地址会被拒绝。文字响应上限为 64 KiB，图片直返只流式检查响应头和有限前缀。

默认来源：

| 类型 | 来源 |
|---|---|
| 文字 | 今日诗词、Hitokoto、QZQI 新一言 |
| 图片 | Bing、Bing 官方 UHD、Komll、LoliAPI、次元图源 |

一次失败进入降级，连续三次标记不可用，成功后立即恢复。实际使用与每小时计划探测都会更新健康状态。

## 持久打卡任务

手动全部、单人打卡、今日失败重试和计划任务复用同一个持久编排服务：

```http
POST /api/clockin/tasks
Content-Type: application/json

{
  "scope": "all | failed | users",
  "date": "YYYY-MM-DD",
  "user_ids": []
}
```

创建成功返回 `202`；同时已有活动任务时返回 `409` 和现有任务编号。前端每两秒读取持久进度。服务重启会把遗留的 `pending/running` 任务标记为中断。

“今日失败”按北京时间当天、每位启用用户的最新结果计算，已成功用户不会被重复处理。

## 架构

```text
Browser Admin
  └─ authenticated HTTP
      └─ FastAPI routes
          └─ application services
              ├─ SQLite / SQLAlchemy async sessions
              ├─ controlled public content sources
              └─ Cloudflare Worker HTTP API
```

运行约束：

- FastAPI 路由保持薄层，业务编排位于 `app/services/`。
- 浏览器只访问 Admin HTTP API，不接触数据库或第三方内容源。
- 后台任务使用独立数据库会话。
- Compose 只运行单个 Uvicorn 进程，避免 APScheduler 和进程内任务重复执行。
- 新部署使用全新 SQLite，通过旧版 `1.0` 配置文件导入，不做旧 SQLite 原地迁移。

仓库结构：

```text
.
├── ZX-auto-clock-in-python/
│   ├── app/
│   │   ├── api/                 # FastAPI 路由
│   │   ├── core/                # 数据库、安全与调度器
│   │   ├── models/              # SQLAlchemy 与 Pydantic 模型
│   │   ├── services/            # 内容源、任务、Worker、导入导出
│   │   └── ui/                  # HTML、CSS 与 ES Modules
│   ├── tests/
│   ├── Dockerfile
│   └── docker-compose.yml
├── clockin-worker/
├── docs/architecture/
└── docs/superpowers/specs/
```

## Docker Compose 部署

进入 Admin 目录并准备配置：

```bash
cd ZX-auto-clock-in-python
cp .env.example .env
mkdir -p database logs
```

生产部署必须修改：

```dotenv
APP_ENV=production
DEBUG=false
SECRET_KEY=替换为足够长的随机值
ADMIN_USERNAME=替换为非空管理员名
ADMIN_PASSWORD=替换为强密码
ADMIN_PATH=替换为不易猜测的入口路径
```

默认 `SECRET_KEY`、空管理员名以及空密码或 `admin` 密码会让生产模式拒绝启动。

启动并验证：

```bash
docker compose config
docker compose build
docker compose up -d
docker compose ps
curl http://127.0.0.1:8032/health
```

访问 `http://服务器IP:8032/你的 ADMIN_PATH`。`./database` 与 `./logs` 会挂载进容器；`/health` 同时验证 Web 进程和 SQLite 查询能力。

完整步骤、旧数据导入、持久化验证和回滚说明见 [Docker Compose 部署指南](ZX-auto-clock-in-python/docker-deploy-guide.md)。

## 本地开发

需要 Python 3.11+ 和 Node.js 20+：

```bash
cd ZX-auto-clock-in-python
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python scripts/init_db.py
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

开发模式允许示例管理员配置，但不得将它用于公网部署。

## 数据导入导出

- `2.0` 普通导出使用 `zx-admin-config-YYYY-MM-DD.json` 文件名，不包含用户密码、Worker Token 或旧 `clockin_api_token`。
- 敏感字段编辑时留空表示保持原值。
- 旧 `1.0` 文件可恢复明文密码和 Token，但导入响应及日志不会回显密钥。
- 旧版批处理配置 `batch_size`、`batch_delay`、`parallel_tasks` 会正常导入，并在安全 `2.0` 导出中保留。
- 导入旧文件后应立即安全删除原文件，并轮换任何曾暴露的 Token。
- 旧远梦、cenguigui、KLapi 会映射到 QZQI；旧 `bing_uhd` 映射到 Bing 官方 UHD；未知来源会回退并产生警告。

## 验证

普通自动化不访问真实打卡账号，也不会把第三方内容源的临时波动当作单元测试失败。

```bash
cd ZX-auto-clock-in-python
python -m pytest -q
python -m compileall -q app scripts
node --test tests/frontend/*.test.mjs
find app/ui/assets/js -type f -name '*.js' -print0 | xargs -0 -n1 node --check
node --check app/ui/assets/login.js
```

端到端与发布验证还包括：

```bash
npx playwright test
docker compose config
docker compose build
```

发布前单独运行实时内容源探测；不要使用真实足下账号执行测试。

```bash
python scripts/probe_content_sources.py
```

默认探测使用系统 DNS，与 Admin 运行时的 SSRF 判定一致。如果开发环境将公网域名透明映射到保留地址，可显式使用固定公网 DoH 只检查第三方来源本身；该结果不能替代部署主机的系统 DNS 验证：

```bash
python scripts/probe_content_sources.py --doh-resolver
```

## 主要 Admin API

| 能力 | 接口 |
|---|---|
| 总览 | `GET /api/dashboard/summary` |
| 内容源 | `GET/POST /api/content-sources` |
| 内容源更新/归档 | `PUT/DELETE /api/content-sources/{id}` |
| 内容源排序 | `PATCH /api/content-sources/priorities` |
| 内容源测试 | `POST /api/content-sources/{id}/test`、`POST /api/content-sources/test-all` |
| 创建任务 | `POST /api/clockin/tasks` |
| 任务列表/详情 | `GET /api/clockin/tasks`、`GET /api/clockin/tasks/{id}` |
| 配置导出/导入 | `GET /api/config/export`、`POST /api/config/import` |
| 健康检查 | `GET /health` |

所有管理 API（登录和健康检查除外）都需要有效管理员会话。

## 明确边界

- 单管理员、50 个以内账号，不提供 RBAC。
- 不允许内容源自定义请求方法、请求头、请求体、脚本或任意表达式。
- 不支持内网内容源。
- 不实施数据库静态加密。
- 不重写 Git 历史。
- Cloudflare Worker 单独部署并单独轮换 Token。

## 许可证

本项目使用 [Apache License 2.0](LICENSE)。
