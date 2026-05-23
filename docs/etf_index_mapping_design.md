# ETF 指数映射层设计方案

> 文档版本: v1.0 | 日期: 2026-04-18
> 目标：为 `etf_valuation_enricher.py` 提供 ETF → 跟踪指数映射能力，支持后续接入真实指数 PE/PB 数据。

---

## 一、为什么 ETF 估值应基于跟踪指数

### 1.1 ETF 的本质

ETF（Exchange Traded Fund）是**一揽子证券的打包份额**，本身没有独立的利润和净资产：

| 维度 | 个股 | ETF/LOF |
|------|------|---------|
| 净利润 | 自己赚的 | 成分股加权汇总 |
| 每股净资产 | 自己账面 | 净资产/份额 |
| PE(TTM) | `股价/EPS` | **跟踪指数 PE** |
| PB | `股价/每股净资产` | **跟踪指数 PB** |
| 主体 | 上市公司 | 基金管理人（主动）/ 指数（被动） |

### 1.2 为什么不能直接用 fund_daily 的价格数据算 PE/PB

`fund_daily` 返回的是 ETF 的**交易价格**（市价），包含：
```
日期, 开盘, 最高, 最低, 收盘, 成交量, 成交额, 振幅
```

这和股票的日线数据完全一致。用 ETF 市价套入 PE/PB 公式：

```
PE = ETF市价 / EPS  ← EPS 是什么？ETF 没有独立的 EPS！
```

ETF 的价格围绕净值（NAV）波动，NAV 由跟踪指数的成分股决定。因此：

> **正确的做法：`ETF估值 = 跟踪指数的PE/PB`**（对于被动型ETF）
> 对于主动管理型 LOF：无法精确映射，建议使用行业/风格相近的宽基指数或保留 mock。

### 1.3 各类 ETF 的估值来源

| ETF 类型 | 跟踪指数 | PE/PB 来源 | 可行性 |
|---------|---------|-----------|--------|
| 宽基指数 ETF | 沪深300/中证500/上证50等 | 中证指数官网、乐咕乐股 | ✅ 高 |
| 行业 ETF（证券/医药/军工） | 对应行业指数 | 行业指数 PE | ✅ 中（需确认指数代码） |
| QDII ETF（纳指/标普500/黄金） | 对应海外/商品指数 | 海外数据源或无 PE 概念 | ⚠️ 复杂 |
| 主动管理型 LOF | 无固定跟踪指数 | 无法精确映射 | ❌ 困难 |
| 商品 ETF（黄金/原油） | 商品价格 | 无传统 PE/PB | ⚠️ 用商品价格代替 |

---

## 二、映射字段说明

每条映射记录包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `etf_code` | string | ETF 代码（如 `sh510050`） |
| `etf_name` | string | ETF 全称（如 `华夏上证50ETF`） |
| `index_code` | string | 跟踪指数代码（如 `000016`，境外/商品用标准代码如 `IXIC`） |
| `index_name` | string | 跟踪指数名称（如 `上证50`） |
| `source` | string | 映射来源（如 `精确映射表`、`名称关键词`） |
| `confidence` | string | 置信度：`exact` / `high` / `medium` / `low` |
| `mapping_status` | string | 状态：`resolved` / `unresolved` |
| `mapping_method` | string | 方法：`exact_code_match` / `keyword_match` / `null` |

### confidence 语义

| 值 | 含义 | 建议 |
|----|------|------|
| `exact` | 代码精确匹配（如 `sh510050→000016`） | ✅ 可直接使用 |
| `high` | 关键词精确匹配，无歧义（如 `沪深300LOF→000300`） | ✅ 可直接使用 |
| `medium` | 关键词匹配，有一定通用性（如 `证券LOF→399975`） | ⚠️ 可使用，建议人工复核 |
| `low` | 模糊匹配（如 `一带一路→000001`，泛指性高） | ⚠️ 建议人工审核 |
| `null` (unresolved) | 无法自动匹配 | ❌ 需人工标注 |

---

## 三、当前自动映射策略

### 3.1 两层匹配机制

```
输入：etf_spot_latest.json (382只ETF)

Step 1: 精确映射表匹配（EXACT_MAP）
  ├── 覆盖：主要宽基 ETF + QDII ETF + 行业ETF
  └── confidence: exact

Step 2: 关键词规则匹配（KEYWORD_RULES）
  ├── 优先级：按规则列表顺序（宽基 > QDII > 商品 > 行业）
  ├── 是否精确匹配单词：True（避免"中证500"被"中证"误匹配）
  └── confidence: high / medium / low

Step 3: unresolved
  └── 保留记录，mapping_status=unresolved，留待人工标注
```

### 3.2 精确映射表（EXACT_MAP）

覆盖约 70 只高频 ETF，包含：
- 主要宽基 ETF（上证50、沪深300、中证500、创业板指、科创50）
- QDII ETF（纳斯达克100、标普500、恒生指数、黄金ETF、原油LOF）
- 行业 ETF 头部品种（证券ETF、医药ETF、银行ETF、军工ETF、芯片ETF、光伏ETF）

### 3.3 关键词规则（KEYWORD_RULES）

约 130 条规则，按以下顺序组织（匹配到即返回）：

```
宽基指数（最高优先级）
  沪深300 → 000300
  上证50  → 000016
  中证500 → 000905
  创业板指→ 399006
  科创50  → 000688
  ...

QDII / 跨境
  纳斯达克100 → IXIC
  标普500     → SPX
  恒生指数    → HSI
  黄金       → XAUUSD
  原油       → CL
  ...

行业
  中证医药  → 399933
  中证军工  → 399967
  半导体芯片→ 990001
  中证光伏  → 931798
  ...
```

---

## 四、当前映射统计

运行 `scripts/build_etf_index_mapping.py` 后的结果：

| 指标 | 数量 | 占比 |
|------|------|------|
| 总 ETF 数 | 382 | 100% |
| resolved（成功映射）| 151 | 39.5% |
| ├─ exact（精确）| 47 | 12.3% |
| ├─ high（高置信度）| 19 | 5.0% |
| ├─ medium（中）| 63 | 16.5% |
| └─ low（低）| 22 | 5.8% |
| unresolved（未匹配）| 231 | 60.5% |
| **高置信度合计（exact+high）** | **66** | **17.3%** |

### 4.1 容易匹配的类型（resolved）

| 类型 | 示例 | 置信度 |
|------|------|--------|
| 宽基 ETF/LOF | `华夏沪深300ETF(sh510300)` `银华沪深300LOF(160706)` | exact / high |
| QDII ETF/LOF | `纳指ETF(513100)` `标普500LOF(161125)` | exact / high |
| 黄金/原油 LOF | `黄金ETF(518880)` `嘉实原油LOF(160723)` | exact / high |
| 行业 ETF 名称精确 | `证券ETF华宝(512000)` `中证军工(512400)` | exact / high |
| 科创板 LOF | `万家科创板LOF(506001)` | exact |

### 4.2 难以匹配的类型（unresolved）

**主要原因**：主动管理型 LOF 没有明确的跟踪指数，基金管理人为追求超额收益会主动选股。

| 类型 | 特征 | 示例 |
|------|------|------|
| 主动管理型 LOF | 无固定跟踪指数，靠基金经理选股 | `浙商鼎盈LOF` `东方红睿丰LOF` |
| 定期开放混合基金 | 封闭期设计，名称无法映射指数 | `东方红创优定开` `安信价值发现定开` |
| 科创主题/战略配售 | 持仓以科创板为主，但非严格跟踪 | `科创主题投资基金LOF` |
| FOF（基金中基金）| 投资其他基金，无法映射单一指数 | `如意招享FOF` `行业配置FOF` |
| SmartBeta 风格模糊 | 有风格标签但不确定精确指数 | 部分 `ESGLOF` |

**unresolved 处理建议**：
1. 主动管理 LOF（~180只）：保留 mock PE/PB，无需强制映射
2. 定期开放/FOF：同上
3. 部分可补充映射（如科创主题 → 科创50）

---

## 五、如何接入 etf_valuation_enricher.py

### 5.1 架构图

```
etf_valuation_enricher.py
│
├── 新增导入
│   └── from etf_index_mapping import ETFIndexMapper
│
├── ETFIndexMapper（新增模块）
│   ├── load()              加载 data/etf_index_mapping.json
│   ├── get_index(etf_code)  返回跟踪指数信息
│   └── get_tracking_index(etf_code, etf_name) → {index_code, index_name, confidence}
│
├── 新增方法
│   └── fetch_index_pe_pb(index_code)  获取指数真实 PE/PB
│       ├── 乐咕乐股（免费）
│       ├── 中证指数官网（免费）
│       └── mock 兜底
│
└── 修改 _fetch_valuation_data()
    ├── 读取 ETF → 指数映射
    ├── 获取指数 PE/PB（fetch_index_pe_pb）
    ├── PE/PB 替代 mock 值（confidence=exact/high/medium 时）
    └── PE/PB 保留 mock（confidence=low 或 unresolved 时）
```

### 5.2 接口设计（新增）

```python
class ETFIndexMapper:
    """ETF → 跟踪指数映射查询器"""

    def __init__(self, mapping_file: str):
        with open(mapping_file) as f:
            self._data = json.load(f)["data"]
        self._lookup = {m["etf_code"]: m for m in self._data}

    def get_tracking_index(self, etf_code: str) -> dict | None:
        """
        Returns: {
            "index_code": "000300",
            "index_name": "沪深300",
            "confidence": "exact",
            "mapping_status": "resolved"
        }
        """
        return self._lookup.get(etf_code)

    @property
    def high_confidence_codes(self) -> List[str]:
        """置信度 >= high 的 ETF 代码列表（用于优先获取真实 PE/PB）"""
        return [
            m["etf_code"] for m in self._data
            if m["mapping_status"] == "resolved"
            and m["confidence"] in ("exact", "high")
        ]
```

```python
class IndexPEPBClient:
    """指数 PE/PB 数据客户端"""

    def fetch(self, index_code: str, trade_date: str) -> dict:
        """
        获取指数 PE/PB
        数据源：乐咕乐股 > 中证指数官网 > mock
        """
        # TODO: 实现乐咕乐股接口调用
        # TODO: 实现中证指数官网接口调用
        # 返回 mock（后续接入真实数据）
        return {
            "pe_ttm": None,
            "pb": None,
            "pe_percentile": None,
            "pb_percentile": None,
            "source": "mock",
            "updated_at": datetime.now().isoformat()
        }
```

### 5.3 修改 _fetch_valuation_data() 的伪代码

```python
def _fetch_valuation_data(self, etf: dict) -> dict:
    result = {}

    # 1. 原有逻辑：avg_amount_20d
    avg_amount_20d, avg_flag = self._get_avg_amount_20d(etf["code"], etf["amount"])
    result["avg_amount_20d"] = avg_amount_20d
    result["avg_amount_20d_flag"] = avg_flag

    # 2. 新增：指数 PE/PB
    index_info = self.mapper.get_tracking_index(etf["code"])

    if index_info and index_info["mapping_status"] == "resolved":
        # 有跟踪指数，尝试获取真实指数 PE/PB
        pe_pb_data = self.index_pe_client.fetch(
            index_info["index_code"], trade_date
        )
        if pe_pb_data["source"] != "mock":
            result["pe_ttm"] = pe_pb_data["pe_ttm"]
            result["pb"] = pe_pb_data["pb"]
            result["pe_percentile"] = pe_pb_data["pe_percentile"]
            result["pb_percentile"] = pe_pb_data["pb_percentile"]
            result["valuation_source"] = f"index:{index_info['index_name']}"
        else:
            # 真实数据获取失败，用 mock
            result.update(self.mock_gen.generate(etf["code"], etf["name"]))
            result["valuation_source"] = "mock"
    else:
        # unresolved，主动管理型 LOF，保留 mock
        result.update(self.mock_gen.generate(etf["code"], etf["name"]))
        result["valuation_source"] = "mock_unresolved"

    # 3. PEG 仍保留 mock（无免费来源）
    result["peg"] = self.mock_gen.generate_peg(result["pe_ttm"], etf["code"])

    # 4. data_quality_flag 综合判断
    result["data_quality_flag"] = self._judge_quality_flag(
        avg_flag, result.get("valuation_source", "")
    )

    return result
```

---

## 六、指数 PE/PB 数据来源优先级

| 优先级 | 来源 | URL | 覆盖 | 数据类型 | 成本 |
|--------|------|-----|------|---------|------|
| 1 | 乐咕乐股 | legulegu.com | 宽基/行业 | PE/PB + 百分位历史 | 免费 |
| 2 | 中证指数官网 | csindex.com.cn | 中证系列 | 官方 PE/PB | 免费 |
| 3 | AKShare `stock_index_pe_lg` | — | 全市场均值 | PE/PB 时间序列 | 免费（⚠️网络问题）|
| 4 | mock 兜底 | — | 全部 | hash稳定估算 | 免费 |

> **已知限制**：AKShare 东方财富接口在国内网络环境下有连接问题（MacBook Air 在海外/受限网络）。乐咕乐股接口目前稳定。

---

## 七、置信度使用建议

```
exact   → 直接替换 mock，置信度最高
high    → 直接替换 mock
medium  → 可替换，但建议在简报中标注"估值来源：行业指数"或"估算"
low     → 保留 mock，或人工确认后再替换
unresolved → 保留 mock（主动管理型LOF不适合映射）
```

---

## 八、文件结构

```
etf-agent/
├── data/
│   ├── etf_spot_latest.json            ← 输入：ETF实时行情
│   ├── etf_valuation_latest.json       ← 输出：估值富化数据
│   ├── etf_index_mapping.json          ← 新增：ETF→指数映射表
│   └── ...
├── scripts/
│   ├── etf_data_collector.py           ← Agent1
│   ├── etf_valuation_enricher.py       ← Agent2（待升级接入指数PE/PB）
│   ├── agent3_etf_comparator.py         ← Agent3（不改动）
│   ├── build_etf_index_mapping.py     ← 新增：映射构建脚本
│   └── ...
└── docs/
    ├── etf_index_mapping_design.md    ← 本文档
    └── ...
```

---

## 九、人工补充 unresolved 的路径

对于 `mapping_status=unresolved` 的 231 只 ETF，建议按以下方式处理：

| 类型 | 建议 | 优先级 |
|------|------|--------|
| 主动管理型 LOF（~180只）| 保留 unresolved，不强制映射 | 低 |
| 定期开放混合基金 | 保留 unresolved | 低 |
| FOF | 保留 unresolved | 低 |
| 名称含明确行业词的 unresolved | 人工匹配行业指数 | 中 |
| 名称含泛投资风格词的 unresolved | 匹配宽基指数（如000300） | 低 |

### 人工标注格式（data/etf_index_mapping_manual.json）

```json
{
  "manual_overrides": {
    "sz169201": {"index_code": "000300", "index_name": "沪深300", "note": "浙商鼎盈主要配置A股大盘股"},
    "sz168701": {"index_code": "399699", "index_name": "中证金融科技", "note": "金融科技主题"}
  }
}
```

---

## 十、待办事项

- [ ] 创建 `scripts/etf_index_mapping.py` 模块（ETFIndexMapper 类）
- [ ] 实现 `IndexPEPBClient`（乐咕乐股接口）
- [ ] 修改 `etf_valuation_enricher.py` 接入映射层
- [ ] 运行完整 pipeline 验证
- [ ] 人工补充高价值 unresolved（行业主题 LOF）
- [ ] 评估 unresolved 中主动管理 LOF 的 mock 替代方案
