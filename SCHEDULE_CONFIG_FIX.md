# 定时任务配置修复说明

## 问题分析

### 之前的 Bug

**重启服务后，前端设置的定时任务会恢复到 `.env` 文件的配置**

原因：服务启动时，调度器只从环境变量读取配置，不读取数据库。

## 修复内容

### 修改文件
- `app/core/scheduler.py` 的 `start_scheduler()` 函数

### 修复后的行为

✅ **前端修改定时任务** - 立即生效
- 通过 API `PUT /api/config` 更新配置
- 配置保存到数据库
- 调度器立即重新加载

✅ **重启服务后** - 保持数据库配置
- 启动时优先从数据库读取配置
- 如果数据库没有，使用 `.env` 默认值
- 日志会明确显示配置来源

## 日志示例

服务启动时会看到类似日志：

```
从数据库读取 schedule_cron: 0 10 0 * * *
从数据库读取 schedule_enabled: True
从数据库读取 schedule_timezone: Asia/Shanghai
使用时区: Asia/Shanghai (<DstTzInfo 'Asia/Shanghai' LMT+8:06:00 STD>)
定时打卡任务已添加: 0 10 0 * * * (时区: Asia/Shanghai)
下次执行时间: 2026-03-02 00:10:00+08:00
调度器已启动 (时区: Asia/Shanghai)
```

或者如果数据库没有配置：

```
数据库可能尚未初始化，使用环境变量配置: ...
定时打卡任务已添加: 0 10 16 * * * (时区: UTC)
```

## 使用建议

### 首次部署

1. 在 `.env` 文件中设置默认配置：
   ```bash
   SCHEDULE_CRON=0 10 0 * * *
   SCHEDULE_TIMEZONE=Asia/Shanghai
   SCHEDULE_ENABLED=true
   ```

2. 启动服务

3. 如需修改，通过前端或 API 更新，会立即生效并持久化到数据库

### 日常使用

- **推荐方式**：通过前端管理界面或 API 修改配置
- **优势**：无需重启服务，配置立即生效
- **持久化**：配置保存在数据库，重启服务后依然有效

### API 使用示例

**查看当前配置：**
```bash
curl http://localhost:8000/api/config \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**更新定时任务配置：**
```bash
curl -X PUT http://localhost:8000/api/config \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "schedule_cron": "0 30 8 * * *",
    "schedule_timezone": "Asia/Shanghai",
    "schedule_enabled": true
  }'
```

**查看调度器状态：**
```bash
curl http://localhost:8000/api/config/schedule \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 配置优先级

1. **数据库配置**（最高优先级）
   - 通过前端或 API 设置的配置
   - 服务启动时会优先读取

2. **环境变量**（默认值）
   - `.env` 文件中的配置
   - 数据库没有配置时使用

## 总结

现在前端设置的定时任务配置会：
- ✅ 立即生效
- ✅ 保存到数据库
- ✅ 重启服务后保持有效

修复完成！
