# 第三方API修复总结

## 修复日期
2026-02-27

## 问题说明
原JS项目中的部分第三方API已更新域名，且返回的数据包含Unicode转义序列需要解码。Python重构项目需要与原JS保持一致。

## 关键修复

### 1. API域名更新

#### 文字API
| API名称 | 旧URL（错误） | 新URL（正确） | 状态 |
|---------|--------------|--------------|------|
| cenguigui | `https://api.cenguigui.cn/api/yiyan` | `https://api-v2.cenguigui.cn/api/yiyan/?code=json` | ✅ 已修复 |
| yuanmeng | `https://api.yuanmeng.jiguangd.cn/api/yiyan.php` | `https://api.mmp.cc/api/yiyan?format=json` | ✅ 已修复 |
| klapi | （未实现） | `https://www.klapi.cn/api/yiyan.php?type=json` | ✅ 新增 |

#### 图片API
| API名称 | 旧URL（错误） | 新URL（正确） | 状态 |
|---------|--------------|--------------|------|
| komll | `https://api.komll.com/api/taotu.php?type=json` | `https://api.komll.com/images` | ✅ 已修复 |
| loliapi | `https://www.loliapi.com/acgpic` | `https://www.loliapi.com/acg/` | ✅ 已修复 |
| cimuapi | `https://api.cym.cc/{category}.php` | `https://t.alcy.cc/{category}/` | ✅ 已修复 |

### 2. 302重定向处理

**关键代码修改：**
```python
# 添加 follow_redirects=True 自动跟随重定向
async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
    response = await client.get(url)
    # response.url 包含最终的URL（跟随重定向后）
    final_url = str(response.url)
```

**适用API：**
- loliapi: `https://www.loliapi.com/acg/` → `https://esa-img.xxx.xxx/i/pc/xxx.webp`
- cimuapi: `https://t.alcy.cc/ycy/` → `https://tc.alcy.cc/tc/日期/文件名.webp`
- komll: `https://api.komll.com/images` → 最终图片URL

### 3. Unicode解码

**问题：** cenguigui和yuanmeng返回的文本包含Unicode转义序列
```json
{"code": 200, "msg": "\\u505a\\u4efb\\u4f55\\u4e00\\u4ef6\\u4e8b\\u90fd\\u8981\\u5c3d\\u60c5\\u4eab\\u53d7\\u5b83"}
```

**解决方案：**
```python
@staticmethod
def _decode_unicode(text: str) -> str:
    """解码 Unicode 转义序列"""
    try:
        return json.loads(f'"{text}"')
    except:
        return text
```

**应用API：**
- `cenguigui`: 返回的 `msg` 字段需要解码
- `yuanmeng`: 返回的 `quote` 字段需要解码

### 4. 次元API分类更新

原JS项目使用的是新的次魔API，支持15个分类：

**代码中的分类：**
```python
CIMU_API_CATEGORIES = {
    'ycy': '二次元自适应',
    'moez': '萌版自适应',
    'ai': 'AI自适应',
    'ysz': '原神自适应',
    'pc': 'PC横图',
    'moe': '萌版横图',
    'fj': '风景横图',
    'bd': '白底横图',
    'ys': '原神横图',
    'mp': '移动竖图',
    'moemp': '萌版竖图',
    'ysmp': '原神竖图',
    'aimp': 'AI竖图',
    'tx': '头像方图',
    'lai': '七濑胡桃',
    'xhl': '小狐狸',
    'random': '随机',
}
```

## 测试验证

### 测试脚本
`scripts/test_apis.py` - 测试所有API是否正常工作

### 测试结果
所有9个API（5个文字 + 4个图片）全部正常工作：

**文字API：**
- ✅ poetry_all (今日诗词)
- ✅ hitokoto (一言)
- ✅ cenguigui (Unicode解码正常)
- ✅ yuanmeng (Unicode解码正常)
- ✅ klapi

**图片API：**
- ✅ bing (必应壁纸)
- ✅ loliapi (302重定向正常)
- ✅ cimuapi (302重定向正常，15个分类)
- ✅ komll (302重定向正常)

## 与原JS项目对比

| 功能 | 原JS项目 | Python重构 | 状态 |
|------|---------|-----------|------|
| 文字API数量 | 5个 | 5个 | ✅ 一致 |
| 图片API数量 | 4个 | 4个 | ✅ 一致 |
| Unicode解码 | ✅ | ✅ | ✅ 一致 |
| 302重定向处理 | ✅ | ✅ | ✅ 一致 |
| 次魔API分类 | 15个 | 15个 | ✅ 一致 |

## 使用说明

### 文字备注配置
用户可选择以下API作为打卡备注：
1. `poetry_all` - 今日诗词（推荐）
2. `hitokoto` - 一言（带出处）
3. `cenguigui` - 随机一言
4. `yuanmeng` - 远梦API
5. `klapi` - KLapi

### 图片配置
用户可选择以下图片来源：
1. `bing` - 必应每日壁纸（默认，最稳定）
2. `loliapi` - ACG图片
3. `cimuapi` - 次元图片（15个分类）
4. `komll` - 随机图片

## 注意事项

1. **URL格式注意**：部分API要求末尾带斜杠（如 `loliapi` 和 `cimuapi`）
2. **超时设置**：图片API设置15秒超时，文字API设置10秒
3. **降级策略**：如果自定义图片API失败，会自动降级到必应图片
4. **重试机制**：所有API都有自动重试机制
5. **控制台显示**：Windows控制台可能显示中文乱码，但实际存储到数据库是正确的
