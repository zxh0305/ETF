# 当前系统实际可获取字段清单

> 生成时间：2026-04-19 21:26  
> 数据来源：data/etf_valuation_latest.json（382条）、output/low_valuation_candidates_latest.json（real_pool 40条）

---

## 一、100% 可获取字段（382/382）

| 字段名 | 含义 | 来源类型 | 来源脚本/数据源 |
|--------|------|----------|----------------|
| `code` | ETF代码 | 真实数据 | etf_data_collector.py → akshare/sina |
| `name` | ETF名称 | 真实数据 | etf_data_collector.py → akshare/sina |
| `price` | 最新价格 | 真实数据 | etf_data_collector.py → akshare/sina |
| `change_pct` | 涨跌幅% | 真实数据 | etf_data_collector.py → akshare/sina |
| `amount` | 今日成交额 | 真实数据 | etf_data_collector.py → akshare/sina |
| `avg_amount_20d` | 20日均价成交额 | 估算/mock | etf_valuation_enricher.py（sina_spot估算347条，mock 35条） |
| `avg_amount_20d_flag` | 流动性数据标记 | 标记字段 | etf_valuation_enricher.py |
| `avg_amount_source` | 流动性数据来源 | 标记字段 | etf_valuation_enricher.py |
| `liquidity_level` | 流动性等级（高/中/低） | 计算字段 | etf_valuation_enricher.py |
| `liquidity_signal` | 流动性信号文字 | 计算字段 | etf_valuation_enricher.py |
| `pe_ttm` | 市盈率TTM | mock/真实 | etf_valuation_enricher.py（mock 342条，真实 40条） |
| `pe_percentile` | PE历史分位 | **hash伪随机** | MockDataGenerator（已停用，值不可信） |
| `pb` | 市净率 | mock/真实 | etf_valuation_enricher.py（342条有值，40条为空） |
| `pb_percentile` | PB历史分位 | **hash伪随机** | MockDataGenerator（已停用，值不可信） |
| `peg` | PEG比率 | 计算字段 | etf_valuation_enricher.py（pe_ttm / 100） |
| `growth_signal` | 成长性信号文字 | 计算字段 | etf_valuation_enricher.py |
| `valuation_signal` | 估值信号文字 | 计算字段 | etf_valuation_enricher.py |
| `pe_pb_real_flag` | PE/PB是否来自真实数据 | 标记字段 | etf_valuation_enricher.py |
| `pe_pb_source` | PE/PB数据来源标记 | 标记字段 | etf_valuation_enricher.py |
| `percentile_real_flag` | 分位数据是否真实 | 标记字段 | etf_valuation_enricher.py（当前全为False） |
| `data_quality_flag` | 数据质量标记 | 标记字段 | etf_valuation_enricher.py（当前全为mock） |
| `updated_at` | 更新时间戳 | 标记字段 | etf_valuation_enricher.py |

---

## 二、部分可获取字段

| 字段名 | 覆盖率 | 含义 | 来源类型 | 说明 |
|--------|--------|------|----------|------|
| `tracking_index` | 151/382 (39.5%) | 跟踪指数信息 | 真实数据（关键词匹配） | 从ETF名称推断跟踪指数，置信度分布：exact 47, medium 63, low 22, high 19 |
| `pb` | 342/382 (89.5%) | 市净率 | mock为主 | 342条来自mock，40条为None（另有40条真实PE但无PB） |

---

## 三、当前不可获取字段

| 字段名 | 覆盖率 | 含义 | 原因 |
|--------|--------|------|------|
| `pe_lar` | 0/382 | PE（率益法） | 无数据源，全为None |
| `pe_percentile`（真实） | 0/382 | PE历史分位（真实） | 需积累≥250交易日快照，当前hash伪值已停用 |
| `pb_percentile`（真实） | 0/382 | PB历史分位（真实） | 需积累≥250交易日快照，当前hash伪值已停用 |

---

## 四、数据来源统计

### 4.1 PE/PB数据来源

| 来源 | 数量 | 占比 |
|------|------|------|
| mock | 342 | 89.5% |
| em_value_market（东财指数估值） | 40 | 10.5% |

### 4.2 流动性（20日均成交额）数据来源

| 来源 | 数量 | 占比 |
|------|------|------|
| sina_spot（估算） | 347 | 90.8% |
| mock | 35 | 9.2% |
| real_history（真实K线历史） | 0 | 0% |

### 4.3 跟踪指数识别覆盖率

| 置信度 | 数量 | 说明 |
|--------|------|------|
| exact | 47 | 名称完全匹配 |
| high | 19 | 名称高度匹配 |
| medium | 63 | 关键词匹配 |
| low | 22 | 弱匹配 |
| 无 | 231 | 未识别 |

---

## 五、字段用途与筛选条件映射

| 用途 | 使用字段 | 当前可用性 |
|------|----------|------------|
| 行情展示 | code, name, price, change_pct, amount | ✅ 100%可用 |
| 流动性筛选 | avg_amount_20d, liquidity_level | ⚠️ 估算为主 |
| 估值筛选 | pe_ttm, pb, peg | ⚠️ mock为主（真实仅40条） |
| 分位筛选 | pe_percentile, pb_percentile | ❌ 已停用（伪值不可信） |
| 指数归属 | tracking_index | ⚠️ 39.5%有值 |
| 真实数据标记 | pe_pb_real_flag | ✅ 标记可用 |

---

## 六、过渡期建议

| 阶段 | 时间 | 可启用字段 |
|------|------|------------|
| v2.1（当前） | 2026-04-19 起 | PE绝对值、PEG、流动性（估算）、真实数据标记 |
| v3.0 | 约250交易日后 | PE/PB历史分位（真实）、分位筛选、分位评分 |

---

## 七、结论

**100%可获取（数据可信）：**
- 行情基础字段：code, name, price, change_pct, amount
- 标记字段：pe_pb_real_flag, pe_pb_source, avg_amount_20d_flag
- 计算字段：peg, liquidity_level, liquidity_signal, growth_signal, valuation_signal

**部分可获取（需谨慎使用）：**
- avg_amount_20d（90.8%估算，无真实历史）
- pe_ttm（10.5%真实，89.5% mock）
- pb（89.5%有值但主要来自mock）
- tracking_index（39.5%覆盖，关键词推断）

**当前不可获取（已停用或无数据）：**
- pe_percentile / pb_percentile（hash伪随机值，已停用）
- pe_lar（无数据源）
- 真实历史分位（需积累数据）
