# ZX Auto Clock-in System

ZX 是一个面向**足下教育现代化学习平台**的单管理员、多账号自动打卡系统：你在自己的服务器上跑一个管理面板，添加同学的足下账号，它就会每天定时帮所有人自动完成打卡（首页、运动、日精进三类），文案和配图还能从多个内容源随机抽取，避免千篇一律。

技术栈：FastAPI + SQLite + 原生前端 + Cloudflare Worker。

## ⚠️ 免责声明

**本项目仅供技术学习、研究与交流用途。**

- 本项目与足下教育（以及其他任何相关平台、组织）**没有任何关联**，亦未获得其任何形式的授权、支持或认可；
- 使用者应遵守所在地区法律法规及目标平台的服务条款，**因下载、部署、使用或滥用本项目所产生的一切后果，均由使用者自行承担**；
- 本项目按“现状”提供，不提供任何明示或默示的保证；
- 如本项目侵犯了任何组织或个人的合法权益，请提交 Issue，我们将及时处理。

继续使用本项目即视为已阅读并同意本声明。

## 它是怎么工作的

整个系统只有两个部件，理解了这张图就理解了全部：

```text
┌──────────────┐   HTTP    ┌─────────────────────┐   HTTP    ┌────────────┐
│  ZX Admin     │ ────────> │  Cloudflare Worker   │ ────────> │  足下学习平台 │
│  管理面板      │           │  打卡执行器（免费）     │           │             │
│  你的服务器上  │ <──────── │  Cloudflare 全球网络  │ <──────── │             │
└──────────────┘   结果     └─────────────────────┘   结果     └────────────┘
```

- **ZX Admin（管理面板）**：跑在你自己的服务器或电脑上。存账号、发任务、看记录、设定时。它**不直接**访问足下平台。
- **Cloudflare Worker（打卡执行器）**：部署在 Cloudflare 免费额度上的一个小函数。Admin 把任务交给它，由它去平台执行打卡再把结果带回来。分开部署的好处：平台侧只看到 Cloudflare 的 IP，你服务器不出网直连；Worker 可以部署多个做负载均衡。
- **数据**：全部存在 Admin 服务器本地的一个 SQLite 文件里，不上传任何第三方。

## 功能一览

后台一共五个页面：

| 页面               | 干什么用                                                                                            |
| ------------------ | --------------------------------------------------------------------------------------------------- |
| **总览**     | 今天成功/失败/未执行多少、下次定时时间、正在执行的任务进度、Worker 和内容源健康状况，失败了一键重试 |
| **用户**     | 添加/编辑打卡账号，单人立即打卡，启用停用                                                           |
| **打卡记录** | 按日期、用户、状态筛选，点开看每类打卡的详细结果                                                    |
| **内容源**   | 管理文案和图片的来源（诗词、一言、Bing 壁纸等），测试可用性、调优先级                               |
| **系统设置** | 定时任务、Worker 节点、重试参数、配置导入导出、备份、清理旧记录                                     |

## 准备清单

开始前确认你都有：

- [ ] 一台能联网的机器（1 核 1G 的最低配服务器就够，自己电脑也行）
- [ ] 一个 Cloudflare 账号（免费版即可，Worker 免费额度完全够用）
- [ ] Node.js 18+（用来部署 Worker）
- [ ] Docker（推荐，部署 Admin 最省事）；不用 Docker 的话需要 Python 3.11+
- [ ] 要打卡的足下账号和密码

## 第一步：部署打卡执行器（Cloudflare Worker）

> 只需要做一次，大约 5 分钟。

```bash
cd clockin-worker
npm install

# 1. 登录 Cloudflare（会弹浏览器授权）
npx wrangler login

# 2. 设置访问令牌（Admin 调用 Worker 的凭证）
#    先自己生成一个随机字符串，例如：python -c "import secrets; print(secrets.token_hex(16))"
npx wrangler secret put API_TOKEN
#    粘贴你生成的字符串并回车 —— 记住它，后面 Admin 里还要填

# 3. 部署
npx wrangler deploy
```

部署成功的输出里会有一行 URL，类似：

```text
https://zx-clockin-executor-api-2.你的子域.workers.dev
```

**把这个 URL 和刚才的 Token 记下来**，第二步要用。

<details>
<summary>部署多个 Worker 做冗余（可选）</summary>

改一下 `wrangler.toml` 里的 `name`（比如加个 `-2` 后缀）再 `npx wrangler deploy`，就得到第二个独立 Worker。多个节点会在 Admin 里自动轮询分流，一个挂了另一个顶上。

</details>

## 第二步：部署管理面板（ZX Admin）

### 方式 A：Docker 部署（推荐）

```bash
git clone https://github.com/404-Wont-Fix/ZX-auto-clock-in-python.git
cd ZX-auto-clock-in-python/ZX-auto-clock-in-python

cp .env.example .env
mkdir -p database logs
```

用任意编辑器打开 `.env`，**必须修改**以下四项（生产模式下不改会拒绝启动）：

| 变量               | 改成什么                                                    |
| ------------------ | ----------------------------------------------------------- |
| `SECRET_KEY`     | 一长串随机字符串（同上`secrets.token_hex(32)` 生成）      |
| `ADMIN_USERNAME` | 你的管理员用户名（别用空值）                                |
| `ADMIN_PASSWORD` | 强密码（不能为空，也不能是`admin`）                       |
| `ADMIN_PATH`     | 后台入口路径，如`my-panel-7421`（别人猜不到才有伪装效果） |

然后启动：

```bash
docker compose up -d --build
docker compose ps          # 应显示 running (healthy)
curl http://127.0.0.1:8032/health    # 返回 JSON 即正常
```

浏览器访问 `http://你的服务器IP:8032/你设置的ADMIN_PATH` 就能看到登录页。
（访问其他路径只会看到一个伪装的 nginx 页面，这正是它的用途。）

> 端口 `8032` 想改的话，改 `docker-compose.yml` 里 `ports: - "8032:8000"` 左边的数字。

### 方式 B：手动部署（不用 Docker）

```bash
cd ZX-auto-clock-in-python
python -m venv .venv
source .venv/bin/activate        # Windows 用 .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # 同样编辑上面那四项
python scripts/init_db.py        # 初始化数据库

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

访问 `http://127.0.0.1:8000/你的ADMIN_PATH`。

## 第三步：10 分钟上手配置

部署好后，按顺序做这五件事就能跑起来：

### 3.1 登录后台

用 `.env` 里设置的 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 登录。

### 3.2 添加 Worker 节点

进入 **系统设置 → Worker 节点 → 添加节点**：

- **节点名称**：随便起，比如 `主节点`
- **Worker 地址**：第一步记下的 `https://xxx.workers.dev`
- **API Token**：第一步 `wrangler secret put API_TOKEN` 时设置的字符串

保存后点该行的 ▶ **测试连接**，状态显示「可用」就通了。

### 3.3 添加打卡账号

进入 **用户 → 添加用户**：

- **足下账号 / 密码**：同学在平台的真实账号密码（密码只存在你服务器本地）
- **内容策略**（可选）：运动和日进军的文案可以选「平台默认 / 固定文案 / 内容源随机」三种方式；高级设置里还能选图片来源（Bing 壁纸、二次元图源等）
- 重复操作把所有人的账号都加上

### 3.4 手动测试一次

在 **用户** 页面点某人那一行的 ▶ 立即打卡，完成后到 **打卡记录** 里点开这条记录：
三个格子（首页 / 运动 / 日精进）都是绿色 ✔ 就说明全链路打通了。

### 3.5 开启每日定时

进入 **系统设置 → 计划任务**：

- 设置「每天执行时间」（默认 `00:10`）和时区（默认北京时间）
- 打开「启用计划任务」开关，保存
- 面板会显示「下次执行」时间，到点自动开跑；已打过卡的不会重复执行

需要非每日的排程（如仅工作日）？展开「高级」用自定义 CRON 表达式（格式：`秒 分 时 日 月 周`）。

## 日常使用

- **每天看一眼总览**：失败数不是 0 就点「重试失败」；Worker 显示不可用多半是额度或网络问题，去系统设置点测试/重置。
- **文案不想重样**：内容源页里开几个文字源（今日诗词 / 一言 / QZQI），用户的内容策略选「内容源」即可随机抽取；图片源同理。
- **换机器/重装**：系统设置 → 导出配置（不含密码）+ 创建数据库备份（完整数据），到新机器导入。
- **记录越来越多**：系统设置 → 数据维护 → 清理旧记录（默认只保留 7 天）。

## 常见问题（FAQ）

**打卡全部失败，提示「没有可用的 Worker 节点」**
去 系统设置 → Worker 节点 看状态列。常见原因：① Token 填错（和 `wrangler secret put` 时的值不一致）② Worker 地址复制不完整 ③ Worker 没部署成功。点「测试连接」验证；之前连续失败被标记「不可用」的，修好后点「重置可用状态」。

**忘了后台密码 / 想改管理员**
改 `.env` 里的 `ADMIN_USERNAME`、`ADMIN_PASSWORD`，然后 `docker compose restart`。

**数据存在哪？怎么备份？**
全部在 `database/zx_admin.db` 一个文件里（Docker 部署时挂载在宿主机 `./database` 目录）。系统设置里有「创建数据库备份」按钮，定期备份这个目录即可。

**定时任务没执行？**
先看 系统设置 → 计划任务 里调度器是否显示「运行中」、开关是否打开；再检查时区设置对不对。容器重启后调度器会自动恢复。

**能开多个进程提速吗？**
不要。系统约定只运行单个 Uvicorn 进程（docker compose 配置已固定），开多进程会导致定时任务被重复触发。

**安全建议**
后台走公网 HTTP 时密码是明文传输的，建议：改一个难猜的 `ADMIN_PATH`、用强密码、有条件套一层 HTTPS 反向代理。不要把 `.env` 文件提交到任何仓库。

## 面向开发者

- 前端为原生 HTML/CSS/ES Modules，无框架、无构建链、无运行时 CDN；后端 FastAPI + SQLAlchemy async + APScheduler，业务逻辑在 `app/services/`，路由保持薄层。
- 仓库结构：

```text
.
├── ZX-auto-clock-in-python/   # Admin（FastAPI 后端 + 原生前端）
│   ├── app/api/               # 路由
│   ├── app/services/          # 业务逻辑（打卡编排、内容源、Worker、任务）
│   ├── app/ui/                # 前端（页面 + ES Modules）
│   └── tests/                 # pytest / Node / Playwright
├── clockin-worker/            # Cloudflare Worker 执行器
└── docs/                      # 架构记录与设计规格
```

- 跑测试：

```bash
cd ZX-auto-clock-in-python
python -m pytest -q
node --test tests/frontend/*.test.mjs
npx playwright test          # 端到端
```

- 主要 API（均需管理员会话，除登录和 `/health`）：`/api/dashboard/summary`、`/api/users`、`/api/records`、`/api/content-sources`、`/api/clockin/tasks`、`/api/worker-apis`、`/api/config/export|import`、`/health`。

## 许可证

本项目使用 [Apache License 2.0](LICENSE)。
