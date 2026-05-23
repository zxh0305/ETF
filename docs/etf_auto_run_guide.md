# ETF全流程自动化运行指南

**文档版本**: v1.0  
**更新时间**: 2026-04-18  
**项目路径**: `~/.qclaw/workspace/etf-agent/`

---

## 一、概述

### 1.1 目标

实现 **每天 09:20 自动采集、自动分析、自动生成简报** 的一体化流程，全程无需人工干预。

### 1.2 当前流程

```
09:20 自动触发
     │
     ├─ Step1: 行情采集     → data/etf_spot_latest.json
     │
     ├─ Step2: 估值补全     → data/etf_valuation_latest.json
     │
     ├─ Step3: 低估筛选     → output/low_valuation_candidates_latest.json
     │                      → output/low_valuation_report_latest.md
     │
     ├─ Step4: 结果对比     → output/change_report_latest.json
     │
     └─ Step5: 简报生成     → output/dialog_brief_latest.txt  ← 最终交付物
```

### 1.3 当前约束

> ⚠️ **重要说明**
> - 当前**不实现**微信、企微、邮件、短信等外部推送
> - 当前**仅生成本地**最终简报文件 `output/dialog_brief_latest.txt`
> - 该文件是后续"对话框推送"的内容来源
> - 后续扩展时，只需读取该文件内容并调用推送接口即可

---

## 二、文件结构

```
etf-agent/
├── scripts/
│   ├── etf_data_collector.py          # Step1: 行情采集
│   ├── etf_valuation_enricher.py     # Step2: 估值补全
│   ├── agent2_etf_screener.py        # Step3: 低估筛选
│   ├── agent3_etf_comparator.py      # Step4: 结果对比
│   ├── generate_dialog_brief.py      # Step5: 简报生成
│   ├── run_etf_full_pipeline.py      # 总控脚本（Python）
│   └── run_etf_full_pipeline.sh       # Shell启动脚本
├── data/
│   ├── etf_spot_latest.json           # 行情数据
│   └── etf_valuation_latest.json     # 估值数据
├── output/
│   ├── low_valuation_candidates_latest.json  # 候选ETF
│   ├── low_valuation_report_latest.md        # Markdown报告
│   ├── change_report_latest.json             # 变化报告
│   └── dialog_brief_latest.txt               # 对话框简报 ← 核心输出
├── config/
│   └── agent2_rules.json            # 筛选规则配置
├── logs/                              # 日志目录（自动创建）
└── docs/
    └── etf_auto_run_guide.md         # 本文档
```

---

## 三、手动运行

### 3.1 方式一：Shell脚本（推荐）

```bash
cd ~/.qclaw/workspace/etf-agent

# 完整流程（自动跳过已有输出）
./scripts/run_etf_full_pipeline.sh

# 强制重跑所有步骤（忽略已有输出）
./scripts/run_etf_full_pipeline.sh --force
```

### 3.2 方式二：直接运行Python

```bash
cd ~/.qclaw/workspace/etf-agent

# 完整流程
python3 scripts/run_etf_full_pipeline.py

# 强制重跑
python3 scripts/run_etf_full_pipeline.py --force
```

### 3.3 方式三：单步执行

```bash
# 只运行行情采集（Step1）
python3 scripts/run_etf_full_pipeline.py --step step1

# 只运行低估筛选（Step3）
python3 scripts/run_etf_full_pipeline.py --step step3

# 只运行简报生成（Step5）
python3 scripts/run_etf_full_pipeline.py --step step5
```

### 3.4 各脚本独立运行

```bash
# 单独运行各步骤（不用总控脚本）
cd ~/.qclaw/workspace/etf-agent

# Step1: 行情采集
python3 scripts/etf_data_collector.py

# Step2: 估值补全
python3 scripts/etf_valuation_enricher.py

# Step3: 低估筛选
python3 scripts/agent2_etf_screener.py

# Step4: 结果对比
python3 scripts/agent3_etf_comparator.py

# Step5: 简报生成
python3 scripts/generate_dialog_brief.py
```

---

## 四、定时调度配置（cron）

### 4.1 打开crontab编辑器

```bash
crontab -e
```

### 4.2 添加定时任务

#### 方案一：每天09:20执行（推荐）

```cron
# ETF全流程自动化 - 每天09:20
20 9 * * * cd ~/.qclaw/workspace/etf-agent && /bin/bash scripts/run_etf_full_pipeline.sh >> logs/cron.log 2>&1
```

#### 方案二：每天09:20执行（使用绝对路径）

```cron
# ETF全流程自动化 - 每天09:20（绝对路径）
20 9 * * * /bin/bash /Users/zhangxianghao/.qclaw/workspace/etf-agent/scripts/run_etf_full_pipeline.sh >> /Users/zhangxianghao/.qclaw/workspace/etf-agent/logs/cron.log 2>&1
```

#### 方案三：仅工作日09:20执行（周一至周五）

```cron
# ETF全流程自动化 - 工作日09:20
20 9 * * 1-5 cd ~/.qclaw/workspace/etf-agent && /bin/bash scripts/run_etf_full_pipeline.sh >> logs/cron.log 2>&1
```

### 4.3 cron表达式说明

| 表达式 | 含义 |
|--------|------|
| `20 9 * * *` | 每天09:20 |
| `20 9 * * 1-5` | 每周一至周五09:20 |
| `0 18 * * *` | 每天18:00 |

### 4.4 验证crontab配置

```bash
# 查看当前crontab
crontab -l

# 删除所有crontab（谨慎使用）
crontab -r
```

### 4.5 macOS注意事项

macOS需要确保cron服务开启：

```bash
# 查看cron状态
sudo launchctl list | grep cron

# 如果需要，手动启动cron
sudo launchctl start com.vix.cron
```

> 💡 **提示**: macOS推荐使用 `launchd` 或确保cron在"系统偏好设置 > 安全性与隐私 > 隐私 > 全盘访问"中授权。

---

## 五、日志查看

### 5.1 日志目录

```
~/.qclaw/workspace/etf-agent/logs/
├── run_20260418_092000.log     # 每次完整运行
├── run_20260418_092001.log
├── cron.log                     # cron重定向输出
└── report_20260418_092000.json # 执行报告
```

### 5.2 实时查看日志

```bash
# 查看最新日志
tail -f ~/.qclaw/workspace/etf-agent/logs/run_$(date +%Y%m%d)*.log

# 查看最近20行
tail -20 ~/.qclaw/workspace/etf-agent/logs/run_*.log

# 查看所有日志文件
ls -lt ~/.qclaw/workspace/etf-agent/logs/
```

### 5.3 日志级别

日志包含:
- `[INFO]` 正常流程信息
- `[WARNING]` 警告（不影响执行）
- `[ERROR]` 错误（可能导致步骤失败）

---

## 六、查看最终简报

### 6.1 简报文件位置

```
~/.qclaw/workspace/etf-agent/output/dialog_brief_latest.txt
```

### 6.2 查看方式

```bash
# 查看今日简报
cat ~/.qclaw/workspace/etf-agent/output/dialog_brief_latest.txt

# 实时监控（每次运行后）
tail -f ~/.qclaw/workspace/etf-agent/output/dialog_brief_latest.txt

# 美化显示
cat ~/.qclaw/workspace/etf-agent/output/dialog_brief_latest.txt | head -60
```

### 6.3 简报内容预览

简报包含以下部分:

```
==================================================
  📊 ETF每日简报 · 2026年04月18日
==================================================

【市场概览】
今日共有 382 只ETF交易
上涨 201 只（52.6%）
下跌 176 只
...

【低估候选ETF】（共 3 只）
1. 嘉实原油LOF（sz160723）
   评分: 78.5 | 今日涨跌: +1.23%
   PE分位12.3% | PB分位5.1% | PEG: 0.68
   ...

【今日变化】
🆕 新入选 1 只:
  + 华夏科创板50ETF
🛑 退出 2 只:
  - 易方达消费ETF
...

—————————————————————
数据采集时间: 2026-04-18 09:20:31
⚠️ 风险提示: 仅供参考，不构成投资建议
```

---

## 七、首次运行说明

### 7.1 前置检查

```bash
# 1. 确认Python环境
python3 --version  # 建议 3.8+

# 2. 确认项目目录
ls ~/.qclaw/workspace/etf-agent/scripts/

# 3. 确认脚本可执行
chmod +x ~/.qclaw/workspace/etf-agent/scripts/run_etf_full_pipeline.sh
```

### 7.2 首次运行测试

```bash
# 1. 先手动运行一次完整流程
cd ~/.qclaw/workspace/etf-agent
./scripts/run_etf_full_pipeline.sh --force

# 2. 检查输出文件
ls -la output/
cat output/dialog_brief_latest.txt

# 3. 检查日志
ls -lt logs/
cat logs/run_*.log | tail -50
```

### 7.3 设置定时任务

首次运行成功后，按"四、定时调度配置"设置cron。

---

## 八、数据说明

### 8.1 当前数据状态

| 阶段 | 数据来源 | 说明 |
|------|----------|------|
| 行情采集 | 东方财富/新浪/腾讯 | ✅ 真实数据 |
| 估值补全 | Mock哈希生成 | ⚠️ 模拟数据 |
| 低估筛选 | 基于Mock数据 | ⚠️ 结果仅供参考 |
| 简报生成 | 综合上述 | ⚠️ 需接入真实估值 |

### 8.2 为什么估值是Mock？

PE/PB等估值数据需要Tushare Pro等付费数据源。
当前使用哈希算法生成稳定的模拟数据，用于:
- 验证全流程能跑通
- 测试筛选逻辑正确性
- 后续替换真实数据源

### 8.3 Mock数据的表现

- 382条ETF中，约1-3条会通过三条件筛选（PE/PB分位≤30% 且 PEG<1 且 成交额≥1亿）
- 这是正常现象，不代表筛选逻辑有问题
- 简报中会明确标注"⚠️ 当前数据为模拟数据"

---

## 九、后续扩展指南

### 9.1 当前状态

```
dialog_brief_latest.txt（本地文件）← 当前仅生成此文件
```

### 9.2 扩展方案（按优先级）

#### 方案一：微信推送（推荐）

```python
# 读取简报内容
with open("output/dialog_brief_latest.txt", "r") as f:
    brief = f.read()

# 调用微信推送接口（示例）
# message.send(channel="wechat", to="张翔豪", text=brief)
```

#### 方案二：企业微信机器人

```python
# 企业微信群机器人webhook
webhook_url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=XXX"
requests.post(webhook_url, json={"msgtype": "text", "text": {"content": brief}})
```

#### 方案三：微信消息服务

```python
# 调用微信消息服务API
# wechat.send_text(to_user="zhangxianghao", content=brief)
```

### 9.3 扩展建议

> 📌 **扩展时，只需修改 `generate_dialog_brief.py`** 或在总控脚本中新增推送步骤，读取 `output/dialog_brief_latest.txt` 即可。

---

## 十、故障排查

### 10.1 常见问题

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| cron没执行 | cron服务未开启 | `sudo launchctl start com.vix.cron` |
| 权限不足 | 脚本无执行权限 | `chmod +x *.sh` |
| Python找不到 | 环境变量问题 | 使用绝对路径 `python3 /path/to/script.py` |
| 数据采集失败 | 网络问题/数据源变动 | 查看当日日志重试 |
| 简报为空 | 前置数据未生成 | 先单独运行各步骤检查 |

### 10.2 调试命令

```bash
# 1. 检查Python环境
which python3
python3 -c "import sys; print(sys.version)"

# 2. 检查项目依赖
cd ~/.qclaw/workspace/etf-agent
python3 scripts/etf_data_collector.py  # 测试采集
python3 scripts/etf_valuation_enricher.py  # 测试补全

# 3. 检查文件权限
ls -la scripts/*.sh scripts/*.py

# 4. 检查cron状态
sudo launchctl list | grep -i cron

# 5. 查看最近日志
ls -lt logs/
tail -100 logs/run_*.log
```

### 10.3 联系与支持

如有问题，请查看日志文件并提供:
1. 错误信息
2. 日志文件路径
3. 执行时间和环境

---

## 十一、配置修改

### 11.1 修改筛选阈值

编辑 `config/agent2_rules.json`:

```json
{
  "filters": {
    "valuation": {
      "pe_percentile_max": 30.0,   // 修改这里
      "pb_percentile_max": 30.0
    },
    "growth": {
      "peg_max": 1.0               // 修改这里
    },
    "liquidity": {
      "avg_amount_20d_min": 100000000  // 修改这里
    }
  }
}
```

### 11.2 修改Mock模式

编辑 `scripts/etf_valuation_enricher.py`:

```python
USE_MOCK_MODE = False  # 改为 False 启用真实数据源
```

### 11.3 修改采集时间

编辑crontab:

```bash
crontab -e
# 将 "20 9" 改为其他时间
# 例如: "0 18" 表示每天18:00
```

---

*文档更新时间: 2026-04-18*
