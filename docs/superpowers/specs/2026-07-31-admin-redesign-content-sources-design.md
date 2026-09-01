# Admin 内容源修复与后台完全重设计规格

## 基线与命名

- 实现基线为本仓库 `main` 分支。
- 开发分支为 `codex/admin-redesign-content-sources`；用户 fork 的 `master` 仅保留作旧基线，不参与实现。
- 仓库目录仍使用 `ZX-auto-clock-in-python`，界面产品名沿用上游当前的 `ZX`；本规格中的 Admin 均指同一后台。
- 用户自有的未跟踪文件不属于本次变更。

## 目标与边界

在不修改 `ai.cqzuxia.com` 登录、上传和首页/运动/日精进接口的前提下，修复失效的文字与图片内容源，把来源管理变成后台可配置能力，并完全重做后台信息架构与视觉。

- 一级页面固定为总览、用户、打卡记录、内容源和系统设置。
- 高频操作在页面或一级抽屉完成，只有危险操作增加确认层；禁止嵌套弹窗。
- 前端使用原生 HTML、CSS 和 ES Modules，无前端框架、生产构建链或运行时 CDN 依赖。
- 单管理员、50 个以内账号，不增加 RBAC、Redis、消息队列或额外进程。
- 公网 IP + HTTP 是用户明确接受的部署方式，文档和界面必须标注凭据可被窃听的残余风险，不能描述为安全生产入口。

## 上游 `main` 现状与计划调整

| 能力 | 上游现状 | 本轮处理 |
|---|---|---|
| 侧栏、Hash 路由、用户/Worker 抽屉 | 已有，但基于 Tailwind/DaisyUI CDN 和单体 `app.js` | 保留单入口与路由理念，彻底替换视觉、DOM、CSS 和模块组织 |
| Docker Compose、健康检查、单 Uvicorn 进程 | 已有 | 加固配置、持久卷、环境契约与文档，不重复新建另一套部署 |
| 用户密码不回传 | 部分已有，`User.to_dict()` 已移除密码 | 增加 `password_configured` 并覆盖所有响应/导出测试 |
| Worker Token 脱敏 | 缺失，模型与路由仍返回完整 Token | 改为是否配置与脱敏显示，空值更新保持原密钥 |
| 生产默认配置拒绝启动 | 部分已有 | 补齐默认管理员组合和必要密钥规则，增加测试 |
| Task 表与 TaskService | 已有但未接入路由或编排，活动任务仍只存在内存 | 演进为统一持久打卡任务，不新建第二套任务模型 |
| 内容源 | 硬编码，部分失效源仍在选择项中 | 新增受控数据库模型、健康探测、降级服务与管理 API |
| 前端 `/api/clockin/status/{id}` | 上游 `main` 中不存在该引用 | 不做无效删除，直接接入新的持久任务契约 |
| 自动化测试 | 无已提交测试 | 建立 pytest、Node 内置测试和 Playwright 基线 |

## 可管理内容源

`ContentSource` 记录包含不可变 `key`、名称、`text/image` 类型、启用与归档状态、优先级、HTTPS 地址模板、查询参数、解析模式、值路径、可选出处路径、允许的 `{category}` 值、2–30 秒超时以及最近检查/成功/失败时间、延迟、连续失败次数和最后错误。

解析模式仅允许：

- `json_text`
- `plain_text`
- `json_image`
- `redirect_image`

服务端只允许公网 HTTPS GET。域名解析后的每个地址以及最多三次的每次重定向都必须重新校验，阻止本机、内网、链路本地、组播、保留和未指定地址。文字响应上限 64 KiB；图片直返仅流式检查响应头与有限前缀，不把完整图片载入 Admin 内存。禁止自定义脚本、请求头、请求体、任意表达式和任意 HTTP 方法。

来源选择顺序为：用户指定且未标记不可用的来源 → 同类型健康来源按优先级 → 未知或降级来源 → 固定文案或 Worker 默认图片。一次失败进入降级，连续三次进入不可用，成功立即恢复；实际调用和每小时计划探测共同维护健康状态。

默认文字源为今日诗词、Hitokoto 和 QZQI 新一言；默认图片源为 Bing、Bing 官方 UHD 参数、Komll、LoliAPI 和次元图源。移除 cenguigui、旧远梦、KLapi 和 `bing.img.run`。旧配置导入时，旧远梦/cenguigui/KLapi 映射到 QZQI，旧 `bing_uhd` 映射到官方 UHD；未知来源使用同类型默认源并写入不含密钥的导入警告。

## 持久任务与失败补救

统一任务入口为：

```json
POST /api/clockin/tasks
{
  "scope": "all | failed | users",
  "date": "YYYY-MM-DD",
  "user_ids": []
}
```

- 创建返回 `202` 与任务编号；浏览器每两秒读取持久进度。
- 同时只允许一个 `pending/running` 打卡任务，冲突返回 `409` 与现有任务编号。
- 今日失败按 `Asia/Shanghai` 当天、每个启用用户的最新结果计算；成功用户不得重复处理。
- 手动全部、单人、失败重试和定时任务复用同一个编排服务。
- 后台执行使用独立数据库会话；服务启动时把遗留 `pending/running` 任务标记为 `interrupted`。
- 旧 `/trigger` 与 `/user/{id}` 在新版 UI 不再使用；兼容保留与否以 API 测试和最小迁移风险决定，不允许形成两套编排逻辑。

## 完全重做后台

桌面端为深色优先的侧栏控制台，系统偏好浅色时自动切换。使用中性实体面板、单一强调色、语义状态色和内联线性 SVG；不使用渐变、玻璃效果、Emoji 操作按钮或运行时 CSS 组件库。

- 总览：今日成功/失败/未执行、下次计划、持久任务进度、Worker/内容源健康、失败用户和一键重试。
- 用户：客户端搜索筛选，行内打卡/编辑/启停，删除收进更多菜单；抽屉分账号、内容策略和高级设置。
- 打卡记录：日期、状态、用户筛选，行内三类结果摘要，详情抽屉。
- 内容源：按文字/图片分组，显示优先级、健康、延迟和错误；支持新增、复制、编辑、排序、归档、单测和全测。新地址必须测试成功才能启用，也可先保存为停用。
- 系统设置：计划任务、Worker 节点、导入导出和危险维护操作采用页内分区，Worker 编辑使用抽屉。
- 手机端底部导航显示总览、用户、记录、更多；内容源和系统设置收进更多，仍不超过三层。

## API、安全与数据交换

新增接口：

- `GET/POST /api/content-sources`
- `PUT/DELETE /api/content-sources/{id}`，删除语义为归档
- `PATCH /api/content-sources/priorities`
- `POST /api/content-sources/{id}/test`
- `POST /api/content-sources/test-all`
- `GET /api/dashboard/summary`
- `POST /api/clockin/tasks`
- `GET /api/clockin/tasks/{id}`
- `GET /api/clockin/tasks?status=active`

敏感字段规则：

- 用户响应只返回 `password_configured`，不返回密码。
- Worker 响应只返回 `token_configured` 与 `token_masked`，不返回完整 Token。
- 编辑时敏感字段留空表示保持原值。
- 新版 `2.0` 普通导出不包含用户密码和 Worker Token。
- 导入兼容旧 `1.0` 明文配置；密钥不得回显或记录，界面提示导入后删除旧文件。
- 移除源码、初始化文件、`.env.example` 和 Wrangler 配置中的固定 Token；Worker Token 使用 `wrangler secret put API_TOKEN`。
- 生产环境遇到默认 `SECRET_KEY`、默认 `admin/admin` 或缺失的必要安全配置时拒绝启动。
- 不实施数据库静态加密，不重写 Git 历史。

## 验证与发布

- pytest 模拟 HTTP 覆盖四种解析模式、JSON 点路径、分类模板、超时、重定向、响应上限、SSRF、健康状态、降级顺序、CRUD、启用前测试、归档引用、每小时探测和默认初始化。
- pytest 覆盖任务 `202/409`、进度恢复、启动中断、北京时间失败筛选、独立会话及成功用户不重复重试。
- pytest 覆盖用户/Worker 响应与 2.0 导出不泄密、1.0 导入恢复密钥且日志无密钥、生产默认配置拒绝启动。
- Node 内置测试覆盖前端纯逻辑；Playwright 覆盖五页、抽屉、任务进度、内容源管理、键盘、系统明暗主题和桌面/手机布局。
- 发布验证包括 `python -m pytest -q`、JavaScript 语法与 Node 测试、Playwright、`docker compose config`、镜像构建、容器重启后的 SQLite 持久化和 `/health`。
- 实时内容源探测独立于单元测试；外部源波动不使普通测试失败。禁止使用真实打卡账号验证本轮明确排除的足下平台接口。
