# ETF 指数智能投资顾问

A股量化数据分析工具，基于 AkShare 库获取 A股行情、财务数据、板块信息等，用于回答关于 A股 ETF 查询、行情数据、估值分析、低估筛选、组合配置建议等。

## 项目结构

```
etf-agent/
├── scripts/              # 核心脚本
│   ├── run_etf_full_pipeline.py   # 全流程流水线（step0~step8）
│   ├── agent2_etf_screener.py     # 低估筛选器
│   ├── agent3_daily_report.py     # 日报生成器
│   ├── portfolio_engine/          # Portfolio Engine 模块
│   └── ...
├── portfolio_engine/     # 组合优化引擎
│   ├── engine.py         # 主引擎
│   ├── models.py         # 数据模型与风险配置
│   ├── risk_profiler.py  # 风险画像
│   ├── data_quality.py   # 数据质量过滤
│   ├── correlation.py    # 相关性分析
│   ├── optimizer.py      # 组合优化器
│   ├── risk_controller.py # 风控执行
│   └── output.py         # 输出生成
├── data/                 # 数据文件（由流水线生成）
├── output/               # 产出文件
│   ├── portfolio_latest.json       # 最新组合配置
│   └── low_valuation_candidates_latest.json  # 最新低估池
├── archive/              # 每日快照存档
└── logs/                # 运行日志
```

## 核心功能

### 1. 数据采集（全流程流水线 step0~step8）
- **Step0** 申万行业估值刷新（31个申万一级行业官方PE/PB）
- **Step1** 行情数据采集（全市场1400+只ETF）
- **Step2** 估值补全（四数据源合并）
- **Step2a** 穿透估值计算（ETF持仓×申万行业PE/PB加权）
- **Step3** 低估筛选
- **Step4** 变化对比
- **Step5** 日报生成
- **Step6** 指数快照存档
- **Step7** 历史分位积累
- **Step8** Portfolio Engine 组合优化

### 2. 低估筛选规则

| 池子 | PE% | PB% | PEG | 日均成交额 |
|------|-----|-----|-----|-----------|
| 正式池 | ≤30% | ≤30% | <1 | ≥1亿元 |
| 关注池 | ≤30% | ≤30% | — | ≥300万 |
| 宽基指数 | ≤50% | ≤50% | <1 | ≥1亿元 |

### 3. Portfolio Engine 组合优化
- 相关性分析（60天历史收益率矩阵）
- 风险控制（单ETF上限、总仓位、数据质量限制）
- 仓位优化（基于PE%/PB%综合评分）

## 数据来源

| 数据源 | 覆盖范围 | 可信度 | 用途 |
|--------|---------|--------|------|
| 乐咕乐股 | 9个宽基指数（20年历史） | ⭐⭐⭐⭐⭐ | 宽基ETF真实历史分位 |
| 申万行业 | 31个一级行业 | ⭐⭐⭐⭐ | 行业ETF穿透估值 |
| 巨潮资讯 | ETF成分股数据 | ⭐⭐⭐ | 穿透估值计算 |
| 新浪财经 | 全市场ETF | ⭐⭐⭐⭐⭐ | 实时行情与流动性 |

## 使用方法

```bash
# 全流程流水线（交易日09:20自动运行）
python3 scripts/run_etf_full_pipeline.py

# 单独运行Portfolio Engine
python3 scripts/run_portfolio_engine.py

# 生成日报
python3 scripts/agent3_daily_report.py
```

## 定时任务

| 任务 | 时间 | 功能 |
|------|------|------|
| ETF流水线 | 交易日09:20 | 全流程数据采集+筛选+日报 |
| 日报推送 | 交易日09:40 | 微信推送日报 |
| 数据健康检查 | 交易日10:00 | 异常告警 |
| 流水线健康检查 | 交易日10:05 | 文件+快照检查 |
| 微信Session检查 | 每日07/11/15/19点 | Session有效性 |

## 风险提示

⚠️ 本系统仅提供量化数据参考，不构成任何投资建议。数据存在以下局限：
- 申万行业估算分位存在±20%误差
- 同一行业所有ETF分位相同，无法区分行业内优劣
- 宽基指数当前普遍偏贵，满足PE%≤30%的极少

---
Author: 张翔豪 | QClaw Agent
