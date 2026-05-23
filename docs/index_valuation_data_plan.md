# 指数估值数据接入补充方案

> 目标：逐步将 `etf_valuation_enricher.py` 中 mock 的 PE/PB 字段替换为真实数据，
> 最小化对下游 Agent2/Agent3 的侵入。

---

## 一、为什么 ETF 的 PE/PB 应基于跟踪指数

### 1.1 根本原因：ETF 本身没有"独立"估值

ETF（Exchange Traded Fund）是**一揽子股票/资产的打包份额**，其价格围绕净值（NAV）围绕跟踪指数波动。

- ETF 发行方每天公布一次净值（通常 T+1）
-盘中实时估算净值（IOPV）由交易所每 15 秒计算一次
- ETF **市价**由市场供需决定，可能高于或低于 NAV（溢价/折价）

**ETF 没有自己的利润和净资产**，因此无法像个股一样直接计算 PE/PB。

### 1.2 实际做法：ETF 估值 = 跟踪指数的估值

| 品种 | 估值来源 | 合理性 |
|------|----------|--------|
| 宽基 ETF（上证50、沪深300等） | 直接取对应指数 PE/PB | ✅ 高：指数本身是成分股的市值加权，PE/PB 定义清晰 |
| 行业/主题 ETF | 取对应行业指数 PE/PB | ✅ 高：逻辑一致 |
| 商品 ETF（黄金、原油） | 取对应商品价格/期货指数 | ✅ 可行：黄金→金价，原油→油价 |
| LOF（主动管理型） | 无法精确映射，建议用 mock 或行业均值 | ⚠️ 困难：无明确跟踪指数 |

### 1.3 直接从 Tushare fund_daily 取 PE/PB 不可行

`fund_daily` 接口返回的是 ETF 的**交易价格数据**（OHLCV），并非 PE/PB。

PE（TTM）的定义：`Price / EPS(TTM)`，需要成分股的盈利数据；
PB 的定义：`Price / Book Value Per Share`，需要基金净资产数据。

这两个指标只能从**指数层面**计算，无法从单只 ETF 的日线数据中得出。

---

## 二、当前系统 ETF → 指数映射

### 2.1 映射策略

从现有 `etf_spot_latest.json` 的 382 只 ETF 中：

```
ETF 名称关键词 → 跟踪指数
```

| 关键词 | 跟踪指数 | 指数代码 | 主要 ETF 示例 |
|--------|----------|----------|--------------|
| 上证50 / 50ETF | 上证 50 | 000016 | 510050(SH), 510800(SH) |
| 沪深300 / 300ETF | 沪深 300 | 000300 | 510300(SH), 159919(SZ) |
| 中证500 / 500ETF | 中证 500 | 000905 | 510500(SH), 159922(SZ) |
| 创业板 / 创成长 | 创业板指 | 399006 | 159915(SZ), 159949(SZ) |
| 科创50 / 科创50ETF | 科创50 | 000688 | 588000(SH), 588080(SH) |
| 纳指 / NASDAQ | 纳斯达克 100 | IXIC | 513100(SH), 159941(SZ) |
| 标普500 / SP500 | 标普 500 | SPX | 513500(SH), 165525(SZ) |
| 恒生 / 恒指 | 恒生指数 | HSI | 159920(SZ), 513660(SH) |
| 黄金 / 金ETF | 现货黄金 | XAUUSD | 518880(SH), 159834(SZ) |
| 原油 / 能源 | WTI原油/南华商品 | CL | 160723(SZ), 162411(SZ) |
| 中概 / 恒生科技 | 恒生科技指数 | HSTECH | 513180(SH), 159741(SZ) |
| 红利 / 中证红利 | 中证红利 | 000922 | 515080(SH), 100032(SZ) |
| 消费 / 中证消费 | 中证消费 | 000932 | 159928(SZ), 512600(SH) |
| 医药 / 中证医药 | 中证医药 | 399933 | 512010(SH), 159938(SZ) |
| 军工 / 中证军工 | 中证军工 | 399967 | 512660(SH), 512680(SH) |
| 半导体 / 芯片 | 中华半导体芯片 | 990001 | 512760(SZ), 159995(SZ) |
| 新能源 / 光伏 | 中证光伏产业 | 931798 | 515790(SH), 159857(SZ) |

**覆盖率估算**：以上关键词可覆盖约 150~200 只宽基/行业 ETF。
其余为细分行业、SmartBeta、主动管理 LOF（无法精确映射）。

### 2.2 映射表数据结构（建议）

```python
# 后续可在 scripts/ 目录下新建 etf_index_mapping.py
ETF_INDEX_MAP = {
    # code (新浪格式) : (index_code, index_name, data_source)
    "sh510050": ("000016", "上证50",   "csindex"),
    "sz159919": ("000300", "沪深300",  "csindex"),
    "sh510300": ("000300", "沪深300",  "csindex"),
    "sh515000": ("000689", "中证医疗", "csindex"),  # 科技ETF华宝 → 中证医疗
    "sh518880": ("XAUUSD","现货黄金",  "macro"),
    # ...
}
```

---

## 三、指数估值数据候选来源

### 3.1 来源汇总

| # | 来源 | 接口/方式 | 指数覆盖 | 数据类型 | 成本 | 可行性 |
|---|------|-----------|---------|---------|------|--------|
| 1 | **Tushare 指数接口** | `index_daily` + `index_basic` | 主要指数 | 指数 OHLCV | 需积分 | ✅ 高 |
| 2 | **中证指数官网 API** | `csindex.com.cn` JSON 接口 | 中证系列 | PE/PB 官方值 | 免费 | ⚠️ 待验证 |
| 3 | **乐咕乐股** | `legulegu.com` | 全市场/宽基 | PE/PB 百分位 | 免费 | ✅ 可用 |
| 4 | **AKShare `stock_zh_index_value_csindex`** | 中证官网 | 中证系列 | PE/PB 历史 | 免费 | ❌ SSL 证书问题 |
| 5 | **AKShare `stock_index_pe_lg`** | 乐咕乐股 | 全市场均值 | 滚动/静态 PE | 免费 | ✅ 可用（见注） |
| 6 | **腾讯证券指数 API** | `proxy.finance.qq.com` | 宽基/行业 | PE/PB 实时 | 免费 | ⚠️ 待验证 |
| 7 | **东方财富指数接口** | `push2.eastmoney.com` | 部分指数 | PE/PB 实时 | 免费 | ⚠️ 待验证 |
| 8 | **Tushare fund_daily（PE/PB 列）** | `fund_daily` | ETF/LOF | PE/PB | 5000积分 | ⚠️ 仅主动管理 LOF 需要 |
| 9 | **TuShare 指数估值** | `index_valuation` | 主要指数 | 实时 PE/PB | 需积分 | ✅ 高（积分足够时） |

> **注**：`stock_index_pe_lg` 目前返回全市场 PE 均值（单一时间序列），
> 不是按指数分类的数据。需进一步验证是否有按指数分组的接口。

### 3.2 可行性详情

#### 来源 1：Tushare `index_daily` + 指数点位（✅ 推荐）

```
积分需求：基础权限（当前已有）即可
覆盖：沪深300、上证50、中证500、创业板等主要指数
数据：指数日线 OHLCV（无 PE/PB 列）

PE/PB 获取思路：
1. 用 `index_daily` 获取指数历史点位
2. PE/PB 需另行计算（盈利/净资产数据 Tushare 需更多权限）
3. 替代方案：与乐咕乐股 PE 数据交叉使用
```

#### 来源 3：乐咕乐股（✅ 当前可用）

```
URL 基础: https://legulegu.com
覆盖: 主要宽基指数（沪深300、创业板指等）
数据: PE/PB 历史时间序列（可计算百分位）
成本: 完全免费

限制:
- 不含主动管理型 LOF 的估值
- 实时性：通常 T+1 更新（收盘后）
- 接口可能存在访问频率限制
```

#### 来源 5：AKShare `stock_index_pe_lg`（✅ 当前可用，限制使用）

```
覆盖: 全市场 A 股 PE 均值（单一时间序列）
数据: 每日市场整体 PE/PB
限制: 不是按指数分类的数据，只能反映全市场估值水平
用法: 作为"全市场温度计"，辅助判断整体水位
```

---

## 四、最小改动接入方案

### 4.1 整体架构

```
scripts/etf_valuation_enricher.py（已存在，改动最小）
    │
    ├── TushareClient 新增方法:
    │     ├── fetch_avg_amount_20d()     ✅ 已完成（本次 Step 1）
    │     └── fetch_index_pe_pb()        📌 新增（本次 Step 2 设计）
    │
    ├── MockValuationGenerator
    │     └── generate_avg_amount_20d()  ✅ 已完成（本次 Step 1）
    │
    └── ETFIndexMapper（新增）
          └── get_tracking_index(etf_code) → index_code

scripts/etf_index_mapping.py（新增）
    └── ETF → 指数映射表 + 关键词匹配器
```

### 4.2 新增文件：scripts/etf_index_mapping.py

```python
# scripts/etf_index_mapping.py
"""ETF → 跟踪指数映射表"""

ETF_INDEX_MAP = {
    "sh510050": {"index_code": "000016", "index_name": "上证50",  "source": "csindex"},
    "sz159919": {"index_code": "000300", "index_name": "沪深300", "source": "csindex"},
    # ... 扩展映射表
}

# 关键词匹配规则（用于未精确映射的ETF）
KEYWORD_RULES = [
    ("sh510050", "50ETF",  "000016", "上证50"),
    ("sh510300", "300ETF", "000300", "沪深300"),
    # ...
]

def get_tracking_index(etf_code: str, etf_name: str) -> dict | None:
    """获取ETF对应的跟踪指数信息"""
    # 1. 精确匹配
    if etf_code in ETF_INDEX_MAP:
        return ETF_INDEX_MAP[etf_code]
    # 2. 关键词匹配
    for pattern, keyword, index_code, index_name in KEYWORD_RULES:
        if keyword in etf_name:
            return {"index_code": index_code, "index_name": index_name, "source": "keyword"}
    return None
```

### 4.3 TushareClient 新增方法

```python
def fetch_index_pe_pb(self, index_code: str, trade_date: str) -> dict:
    """
    获取指数的 PE/PB 数据

    数据来源优先级:
    1. 乐咕乐股 API（免费，已验证）
    2. Tushare 指数接口（有积分时）
    3. Mock 兜底

    Returns:
        {
            "pe_ttm": float,
            "pb": float,
            "pe_percentile": float,  # 历史分位（从乐咕乐股历史数据计算）
            "pb_percentile": float,
            "source": "legulegu" | "tushare" | "mock",
        }
    """
    # TODO: 实现乐咕乐股 API 调用
    # TODO: 实现 Tushare index_daily + 历史 PE 百分位计算
    pass
```

---

## 五、字段接入优先级

### 5.1 可立即替换 mock 的字段

| 字段 | 替换来源 | 依赖 | 实施难度 |
|------|----------|------|----------|
| `avg_amount_20d` | Tushare `fund_daily` | Token + fund_daily 权限 | ✅ 已完成 |
| `pe_ttm`（宽基 ETF） | 乐咕乐股 / 中证指数官网 | 需验证接口稳定性 | ⚠️ 中等 |
| `pb`（宽基 ETF） | 同上 | 同上 | ⚠️ 中等 |
| `pe_percentile` | 乐咕乐股历史 PE + 百分位计算 | 已有历史数据 | ⚠️ 中等 |
| `pb_percentile` | 同上 | 同上 | ⚠️ 中等 |

### 5.2 短期内仍建议保留 mock 的字段

| 字段 | 原因 | 建议 |
|------|------|------|
| `peg` | 需要盈利增长率数据，目前无免费来源 | 保留 mock |
| `pe_ttm` / `pb`（主动管理 LOF） | 无跟踪指数，无法精确映射 | 保留 mock |
| `pe_ttm` / `pb`（细分行业 ETF） | 指数 PE 数据源不覆盖 | 保留 mock |

### 5.3 优先级排序

```
第1批（已完成）:
  ✅ avg_amount_20d → Tushare fund_daily

第2批（本次方案）:
  📌 pe_ttm / pb（宽基ETF）→ 乐咕乐股 + 中证指数官网
  📌 pe_percentile / pb_percentile → 乐咕乐股历史数据

第3批（待后续）:
  ⏳ 接入 Tushare 指数接口，计算真实百分位
  ⏳ 扩充 ETF→指数映射表覆盖更多ETF
  ⏳ peg 真实化（需基本面数据）
```

---

## 六、实施检查清单

- [ ] **Step 1** avg_amount_20d 真实化（`etf_valuation_enricher.py`，✅ 已完成）
- [ ] **Step 2** 指数 PE/PB 接入（本文档方案，📌 进行中）
  - [ ] 创建 `scripts/etf_index_mapping.py`（ETF→指数映射表）
  - [ ] 在 `TushareClient` 添加 `fetch_index_pe_pb()` 方法
  - [ ] 在 `etf_valuation_enricher.py` 调用指数 PE/PB 替代 mock
  - [ ] 测试乐咕乐股接口获取宽基指数 PE
  - [ ] 实现百分位计算逻辑
- [ ] **Step 3** 扩大映射表覆盖率
- [ ] **Step 4** PEG 真实化方案调研

---

## 附录：Tushare 5000 积分获取路径

如果未来需要更完整的 ETF/指数数据，可通过以下方式获取积分：

| 方式 | 积分 | 说明 |
|------|------|------|
| 充值 | 1元=10积分 | 最快 |
| 每日签到 | +5积分/天 | 长期积累 |
| 完成数据任务 | +100~1000积分 | tushare.pro/task |
| 邀请用户注册 | +200积分/人 | 需被邀请人完成任务 |
| 积分要求查看 | fund_daily需5000积分 | 当前缺口约4500积分 |

> **建议**：当前 Token 已有 `fund_daily` 接口访问权限测试结果（失败），
> 登录 tushare.pro → 我的积分 → 查看当前积分和可用接口。
