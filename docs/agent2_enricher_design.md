# ETF估值补全器设计文档

**文档版本**: v1.0  
**创建时间**: 2026-04-17 23:31  
**脚本路径**: `scripts/etf_valuation_enricher.py`  
**当前模式**: MOCK（用于测试，后续替换真实数据源）

---

## 一、输入输出说明

### 1.1 输入文件

| 项目 | 说明 |
|------|------|
| **文件路径** | `data/etf_spot_latest.json` |
| **格式** | JSON |
| **来源** | Agent1 (`etf_data_collector.py`) 的采集输出 |
| **记录数** | 当前382条 |

### 1.2 输出文件

| 项目 | 说明 |
|------|------|
| **文件路径** | `data/etf_valuation_latest.json` |
| **格式** | JSON |
| **内容** | 补全后的ETF数据（行情 + 估值字段） |
| **下游** | Agent2 筛选器 / Agent3 提醒推送 |

### 1.3 输入数据结构

```json
{
  "meta": {
    "data_type": "etf_spot",
    "collect_time": "2026-04-17 20:23:31",
    "trade_date": "2026-04-17",
    "total_count": 382
  },
  "data": [
    {
      "code": "sz169201",
      "name": "浙商鼎盈LOF",
      "price": 1.621,
      "change_pct": 2.79,
      "amount": 111710,
      "category": "其他",
      "liquidity_level": "中",
      ...
    }
  ]
}
```

### 1.4 输出数据结构

```json
{
  "meta": {
    "data_type": "etf_valuation",
    "collect_time": "2026-04-17 23:31:00",
    "source": "etf_spot_latest.json",
    "total_count": 382,
    "success_count": 382,
    "failed_count": 0,
    "mock_used_count": 382,
    "quality_m_count": 382,
    "quality_a_count": 0,
    "mode": "MOCK",
    "enricher_version": "1.0"
  },
  "fields": [
    "code", "name", "category", "price", "amount",
    "change_pct", "liquidity_level",
    "pe_ttm", "pb", "pe_percentile", "pb_percentile",
    "peg", "avg_amount_20d", "avg_amount_20d_flag",
    "valuation_signal", "growth_signal", "liquidity_signal",
    "updated_at", "data_quality_flag"
  ],
  "data": [
    {
      "code": "sz169201",
      "name": "浙商鼎盈LOF",
      "category": "其他",
      "price": 1.621,
      "amount": 111710,
      "change_pct": 2.79,
      "liquidity_level": "中",
      "pe_ttm": 25.97,
      "pb": 1.69,
      "pe_percentile": 48.85,
      "pb_percentile": 44.5,
      "peg": 1.94,
      "avg_amount_20d": 111710.0,
      "avg_amount_20d_flag": "estimated_from_today",
      "valuation_signal": "适中",
      "growth_signal": "成长透支",
      "liquidity_signal": "低",
      "updated_at": "2026-04-17 23:31:00",
      "data_quality_flag": "M"
    }
  ]
}
```

---

## 二、字段说明

### 2.1 继承自原始行情数据

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `code` | string | ETF代码 | `sz169201` |
| `name` | string | ETF名称 | `浙商鼎盈LOF` |
| `category` | string | 自动分类 | `其他` |
| `price` | float | 最新价 | `1.621` |
| `amount` | int | 成交额(元) | `111710` |
| `change_pct` | float | 涨跌幅(%) | `2.79` |
| `liquidity_level` | string | 流动性分级 | `中` |

### 2.2 新增估值字段

| 字段 | 类型 | 说明 | 来源 |
|------|------|------|------|
| `pe_ttm` | float | 市盈率(TTM) | Mock生成 / 真实API |
| `pb` | float | 市净率 | Mock生成 / 真实API |
| `pe_percentile` | float | PE历史分位数(%) | Mock生成 / 真实API |
| `pb_percentile` | float | PB历史分位数(%) | Mock生成 / 真实API |
| `peg` | float | 市盈率相对盈利增长比率 | Mock生成 / 计算 |
| `avg_amount_20d` | float | 20日日均成交额(元) | 估算(当前成交额) |
| `avg_amount_20d_flag` | string | 估算标记 | `estimated_from_today` |

### 2.3 信号字段

| 字段 | 类型 | 可选值 | 说明 |
|------|------|--------|------|
| `valuation_signal` | string | `低估`/`适中`/`高估`/`无法判断` | 估值信号 |
| `growth_signal` | string | `成长空间大`/`成长合理`/`成长透支`/`无法判断` | 成长信号 |
| `liquidity_signal` | string | `高`/`中`/`低`/`无法判断` | 流动性信号 |

### 2.4 元数据字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `updated_at` | string | 数据更新时间 (YYYY-MM-DD HH:MM:SS) |
| `data_quality_flag` | string | 数据质量等级 |

### 2.5 数据质量等级

| 等级 | 说明 | 触发条件 |
|------|------|----------|
| **A** | 真实完整 | 使用真实API获取到完整数据 |
| **B** | 真实部分 | 真实API部分字段缺失 |
| **C** | 真实基础 | 只有真实PE/PB，无分位数 |
| **M** | Mock | 当前模式使用Mock数据 |
| **F** | 失败 | 处理异常，保留原始记录 |

---

## 三、Mock模式说明

### 3.1 为什么需要Mock模式

当前数据缺口：
- `etf_spot_latest.json` 只有行情数据
- 没有 PE/PB/PEG 等估值字段
- 真实估值数据需要 Tushare Pro 等付费/积分数据源

Mock模式的作用：
- 在没有真实数据源时，提供可用的测试数据
- 保证流程完整性，方便后续调试筛选器
- 代码结构与真实数据源完全兼容

### 3.2 Mock数据生成原理

```
ETF code + salt → hash_to_int → 稳定随机数 → 映射到合理范围
```

特点：
- **稳定性**: 相同ETF code每次运行产生完全相同的数据
- **确定性**: 不依赖时间、随机种子
- **分布合理**: PE/PB/分位数在合理范围内

### 3.3 Mock数据取值范围

| 字段 | 范围 | 说明 |
|------|------|------|
| `pe_ttm` | 5.0 ~ 50.0 | 宽基ETF常见范围 |
| `pb` | 0.5 ~ 5.0 | 市净率常见范围 |
| `pe_percentile` | 5% ~ 95% | 历史分位范围 |
| `pb_percentile` | 5% ~ 95% | 历史分位范围 |
| `peg` | 0.2 ~ 3.0 | 约10%概率返回None |
| `avg_amount_20d` | = 当前amount | 估算标记为estimated |

### 3.4 Mock开关配置

```python
# scripts/etf_valuation_enricher.py

USE_MOCK_MODE = True  # True=Mock模式, False=真实数据源
```

---

## 四、后续替换真实数据源

### 4.1 替换策略

**步骤1**: 实现 `_fetch_valuation_data()` 方法

当前代码（第150-170行）：
```python
def _fetch_valuation_data(self, etf_code: str) -> Dict[str, Any]:
    if self.use_mock:
        # 使用Mock生成器
        ...
```

替换为：
```python
def _fetch_valuation_data(self, etf_code: str) -> Dict[str, Any]:
    # 1. 尝试真实数据源
    real_data = self._fetch_real_pe_pb(etf_code)
    if real_data:
        return {**real_data, "is_mock": False}
    
    # 2. 降级到Mock
    mock_data = self.mock_gen.generate_valuation_data(etf_code)
    return {**mock_data, "is_mock": True}
```

**步骤2**: 实现 `_fetch_real_pe_pb()` 方法

```python
def _fetch_real_pe_pb(self, etf_code: str) -> Optional[Dict[str, Any]]:
    """
    从真实数据源获取PE/PB
    推荐数据源: Tushare Pro / JoinQuant / 指数公司官网
    """
    # TODO: 实现真实API调用
    pass
```

### 4.2 推荐数据源

| 数据源 | 费用 | 接口 | 推荐指数 |
|--------|------|------|----------|
| **Tushare Pro** | 积分制 | `index_dailybasic` | ⭐⭐⭐⭐⭐ |
| **JoinQuant** | 免费额度 | `get_index_daily` | ⭐⭐⭐⭐ |
| **指数公司官网** | 免费 | 网页爬虫 | ⭐⭐⭐ |

### 4.3 Tushare Pro 接入示例

```python
# 1. 安装
pip install tushare

# 2. 设置Token
export TUSHARE_TOKEN="your_token"

# 3. 实现
def _fetch_real_pe_pb(self, etf_code: str) -> Optional[Dict[str, Any]]:
    import os
    import tushare as ts
    
    token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        return None
    
    pro = ts.pro_api(token)
    
    # 指数代码映射 (需额外实现ETF->指数映射表)
    index_code = self._get_index_code(etf_code)
    if not index_code:
        return None
    
    today = datetime.now().strftime("%Y%m%d")
    df = pro.index_dailybasic(
        ts_code=index_code,
        trade_date=today,
        fields='ts_code,pe_ttm,pb,pe_percentile,pb_percentile'
    )
    
    if df is not None and len(df) > 0:
        row = df.iloc[0]
        return {
            "pe_ttm": row.get('pe_ttm'),
            "pb": row.get('pb'),
            "pe_percentile": row.get('pe_percentile'),
            "pb_percentile": row.get('pb_percentile'),
            "peg": self._calc_peg(row.get('pe_ttm'), growth_rate),
        }
    
    return None
```

---

## 五、异常处理策略

### 5.1 异常类型与处理

| 异常场景 | 处理方式 | 结果 |
|----------|----------|------|
| 输入文件不存在 | 打印错误，退出 | `sys.exit(1)` |
| JSON解析失败 | 打印错误，退出 | `sys.exit(1)` |
| 单条ETF处理失败 | 记录错误，保留原始数据 | `data_quality_flag = "F"` |
| 字段缺失 | 返回None，不中断 | 字段置None |
| 估值API超时 | 降级到Mock | 标记为Mock |

### 5.2 日志级别

| 级别 | 内容 |
|------|------|
| `INFO` | 开始/完成/统计 |
| `WARNING` | 数据源不可用/降级 |
| `ERROR` | 处理失败 |
| `DEBUG` | 详细调试（单条ETF结果） |

### 5.3 失败恢复

```python
# 单条ETF处理失败时，保留原始记录
etf_copy = dict(etf)
etf_copy["data_quality_flag"] = "F"
etf_copy["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
etf_copy["error_message"] = str(e)
enriched_list.append(etf_copy)
```

### 5.4 质量标记规则

```python
def calc_quality_flag(self, is_mock: bool, has_real_data: bool) -> str:
    if is_mock:
        return "M"      # Mock模式
    if has_real_data:
        return "A"      # 真实完整
    return "C"          # 真实基础
```

---

## 六、筛选阈值配置

### 6.1 阈值常量

```python
# scripts/etf_valuation_enricher.py 第25-35行

LIQUIDITY_HIGH = 500_000_000       # 5亿 = 高流动性
LIQUIDITY_MEDIUM = 100_000_000    # 1亿 = 中流动性

PE_LOW_THRESHOLD = 30.0           # PE分位 ≤ 30% 视为低估
PE_HIGH_THRESHOLD = 70.0          # PE分位 ≥ 70% 视为高估

PB_LOW_THRESHOLD = 30.0           # PB分位 ≤ 30% 视为低估
PB_HIGH_THRESHOLD = 70.0          # PB分位 ≥ 70% 视为高估

PEG_THRESHOLD = 1.0               # PEG < 1 视为成长空间大
```

### 6.2 信号计算逻辑

**valuation_signal**:
```
if pe/pb 分位数 ≤ 30% → "低估"
if pe/pb 分位数 ≥ 70% → "高估"
else → "适中"
```

**growth_signal**:
```
if PEG < 0.5 → "成长空间大"
if PEG < 1.0 → "成长合理"
else → "成长透支"
```

**liquidity_signal**:
```
if 成交额 ≥ 5亿 → "高"
if 成交额 ≥ 1亿 → "中"
else → "低"
```

---

## 七、使用方法

### 7.1 命令行运行

```bash
cd ~/.qclaw/workspace/etf-agent
python scripts/etf_valuation_enricher.py
```

### 7.2 输出示例

```
2026-04-17 23:31:00 [INFO] ============================================================
2026-04-17 23:31:00 [INFO] 🚀 ETF估值补全脚本启动
2026-04-17 23:31:00 [INFO] ============================================================
2026-04-17 23:31:00 [INFO] 📖 读取输入文件: .../data/etf_spot_latest.json
2026-04-17 23:31:00 [INFO]   ✓ 成功读取 382 条记录
2026-04-17 23:31:00 [INFO] 开始补全 382 只ETF的估值数据...
2026-04-17 23:31:00 [INFO] 💾 写入输出文件: .../data/etf_valuation_latest.json
2026-04-17 23:31:00 [INFO]   ✓ 成功写入 382 条记录
2026-04-17 23:31:00 [INFO] ============================================================
2026-04-17 23:31:00 [INFO] 📊 ETF估值补全统计
2026-04-17 23:31:00 [INFO]   总记录数:   382
2026-04-17 23:31:00 [INFO]   成功补全:   382
2026-04-17 23:31:00 [INFO]   Mock数据:   382
2026-04-17 23:31:00 [INFO]   数据质量M级(Mock): 382
2026-04-17 23:31:00 [INFO] ============================================================
2026-04-17 23:31:00 [INFO] ✅ ETF估值补全完成！
```

---

## 八、文件结构

```
etf-agent/
├── scripts/
│   ├── etf_data_collector.py        # Agent1: 行情采集
│   └── etf_valuation_enricher.py    # Agent2: 估值补全 ← 本脚本
├── data/
│   ├── etf_spot_latest.json          # 输入: 行情数据
│   └── etf_valuation_latest.json     # 输出: 补全后数据
└── docs/
    ├── agent2_enricher_design.md    # 本文档
    └── agent2_data_gap_analysis.md   # 数据缺口分析
```

---

## 九、后续计划

| 阶段 | 任务 | 状态 |
|------|------|------|
| 1 | Mock估值补全器 | ✅ 完成 |
| 2 | Agent2低估筛选器 | ⏳ 待实现 |
| 3 | Agent3结果对比与推送 | ⏳ 待实现 |
| 4 | 接入Tushare Pro真实数据 | 📋 规划中 |

---

*文档更新时间: 2026-04-17 23:31*
