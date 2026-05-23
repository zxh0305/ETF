# 东方财富登录态配置指南

## 为什么需要登录？

东方财富数据中心的指数PE/PB报表需要登录态才能访问，公开API会返回9501错误（"报表配置不存在"）。

## 获取Cookie步骤

### 方法一：Chrome/Edge浏览器

1. 打开 https://passport.eastmoney.com/ 并登录
2. 按 `F12` 打开开发者工具
3. 切换到 **Application** 标签
4. 左侧找到 **Cookies** → **https://data.eastmoney.com**
5. 找到以下关键Cookie并复制值：
   - `qgqp_b_id` （必需）
   - `HAList` （必需）
   - `st_si` （可选）
   - `st_pvi` （可选）
   - `st_sp` （可选）

6. 将所有Cookie拼接成字符串：
   ```
   qgqp_b_id=xxx; HAList=xxx; st_si=xxx; st_pvi=xxx; st_sp=xxx
   ```

### 方法二：从请求头复制（推荐）

1. 打开 https://data.eastmoney.com/（数据中心首页）
2. 按 `F12` 打开开发者工具
3. 切换到 **Network** 标签
4. 刷新页面
5. 点击任意请求（如 `get?reportName=...`）
6. 在右侧 **Headers** 中找到 **Request Headers**
7. 找到 `Cookie:` 行，复制完整值

## 保存Cookie

运行脚本并粘贴Cookie：

```bash
python3 ~/.qclaw/workspace/etf-agent/scripts/fetch_em_cookie.py
```

或直接传参：

```bash
python3 ~/.qclaw/workspace/etf-agent/scripts/fetch_em_cookie.py "你的Cookie字符串"
```

## Cookie有效期

- 东财Cookie有效期约 **7天**
- 过期后需重新登录获取
- 脚本会自动检测过期并提示

## 验证Cookie

```bash
# 运行脚本会自动测试Cookie有效性
# 成功输出示例：
# ✅ Cookie有效！成功获取指数PE数据
#    返回 5 条记录

# 失败输出示例：
# ❌ Cookie无效或权限不足: 报表配置不存在
```

## 注意事项

1. Cookie包含敏感信息，不要分享给他人
2. Cookie存储在本地：`~/.qclaw/workspace/etf-agent/config/em_cookie.json`
3. 如果测试失败，可能是：
   - Cookie复制不完整
   - 登录态已过期
   - 账号权限不足（需要普通用户即可）
