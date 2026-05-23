# 真实估值数据替换方案

> 文档版本: 1.0  
> 创建时间: 2026-04-18  
> 目标: 在最小改动前提下，将 Mock 估值数据替换为真实数据源

---

## 一、当前 Mock 字段清单

以下字段在 `etf_valuation_enricher.py` 中通过 **hash 算法生成**，需要替换为真实数据：

| 字段名 | 当前来源 | 说明 |
|--------|----------|------|
| `pe` | Mock | 市盈率 |
| `pb` | Mock | 市净率 |
| `peg` | Mock | 市盈增长比率 |
| `pe_percentile` | Mock | PE 历史分位 |
| `pb_percentile` | Mock | PB 历史分位 |
| `data_quality_flag` | 固定值 `"mock"` | 数据质量标记 |

**已有真实数据字段**（无需改动）：
- `code`, `name`, `category` - ETF 基础信息
- `price`, `change_pct`, `volume`, `turnover` - 实时行情（来自 akshare）

---

## 二、必须获取的真实数据字段

接入真实数据源后，需要获取以下字段：

```json
{
  "pe": 15.5,                    // 市盈率（TTM）
  "pb": 1.8,                     // 市净率（LF）
  "peg": 0.85,                   // PEG = PE / 盈利增长率
  "pe_percentile": 25.5,         // PE 近5年分位（%）
  "pb_percentile": 30.2,         // PB 近5年分位（%）
  "data_quality_flag": "real",   // 标记为真实数据
  "data_source": "tushare",      // 数据来源标识
  "update_time": "2026-04-18"    // 数据更新时间
}
```

---

## 三、推荐数据源候选

### 方案 A: Tushare（推荐）

| 项目 | 说明 |
|------|------|
| **优点** | 数据完整、文档清晰、Python SDK 成熟 |
| **缺点** | 需要注册账号，部分高级数据需积分 |
| **接入成本** | 低 |
| **数据覆盖** | A股ETF全覆盖，含历史估值分位 |

**关键接口**:
- `fund_daily` - ETF日线行情（含PE/PB）
- `fund_nav` - ETF净值数据
- `index_daily` - 指数行情（用于计算分位）

**代码示例**:
```python
import tushare as ts

pro = ts.pro_api('your_token')

# 获取ETF估值数据
df = pro.fund_daily(ts_code='510050.SH', 
                    fields='ts_code,trade_date,pe,pb')
```

### 方案 B: AKShare（免费）

| 项目 | 说明 |
|------|------|
| **优点** | 完全免费，无需注册 |
| **缺点** | 部分数据不稳定，文档较分散 |
| **接入成本** | 低 |
| **数据覆盖** | 基础估值数据覆盖 |

**关键接口**:
- `ak.fund_etf_hist_em()` - ETF历史行情
- `ak.index_value_hist_funddb()` - 指数估值数据

### 方案 C: 东方财富/同花顺爬虫

| 项目 | 说明 |
|------|------|
| **优点** | 数据实时、免费 |
| **缺点** | 需要维护爬虫，有反爬风险 |
| **接入成本** | 中 |
| **稳定性** | 低（接口可能变动） |

---

## 四、最小改动接入方案

### 改动点 1: 修改 `etf_valuation_enricher.py`

**当前逻辑**（Mock）:
```python
def _generate_mock_valuation(self, code: str, name: str, trade_date: str) -> Dict:
    # hash 生成 mock 数据
    ...
```

**替换为**（真实数据）:
```python
def _fetch_real_valuation(self, code: str, name: str, trade_date: str) -> Dict:
    """从Tushare获取真实估值数据"""
    try:
        # 转换代码格式 (sz160723 -> 160723.SZ)
        ts_code = self._convert_code_format(code)
        
        # 获取估值数据
        df = self.pro.fund_daily(ts_code=ts_code, 
                                 trade_date=trade_date,
                                 fields='ts_code,pe,pb')
        
        if df.empty:
            # 无数据时回退到mock
            return self._generate_mock_valuation(code, name, trade_date)
        
        pe = float(df['pe'].iloc[0]) if pd.notna(df['pe'].iloc[0]) else None
        pb = float(df['pb'].iloc[0]) if pd.notna(df['pb'].iloc[0]) else None
        
        # 计算PEG（需要获取盈利增长率）
        peg = self._calculate_peg(ts_code, pe)
        
        # 计算历史分位
        pe_pct, pb_pct = self._calculate_percentile(ts_code, pe, pb)
        
        return {
            "pe": pe,
            "pb": pb,
            "peg": peg,
            "pe_percentile": pe_pct,
            "pb_percentile": pb_pct,
            "data_quality_flag": "real" if all([pe, pb]) else "partial",
            "data_source": "tushare",
            "update_time": trade_date
        }
    except Exception as e:
        logger.warning(f"获取真实数据失败 {code}: {e}")
        # 失败时回退到mock
        return self._generate_mock_valuation(code, name, trade_date)
```

### 改动点 2: 配置文件新增数据源配置

在 `config/agent_config.json` 中添加：
```json
{
  "valuation": {
    "data_source": "tushare",
    "tushare_token": "${TUSHARE_TOKEN}",
    "fallback_to_mock": true,
    "percentile_period": "5y"
  }
}
```

### 改动点 3: 环境变量配置

```bash
# ~/.bashrc 或 ~/.zshrc
export TUSHARE_TOKEN="your_token_here"
```

---

## 五、Agent2/Agent3 是否需要改动

### Agent2（低估筛选）

**不需要改动。**

Agent2 的筛选逻辑基于以下字段：
- `pe_percentile` - 无论mock/real，都是数值
- `pb_percentile` - 无论mock/real，都是数值  
- `peg` - 无论mock/real，都是数值
- `turnover` - 已有真实数据

只要 `etf_valuation_enricher.py` 输出的 JSON 结构保持一致，Agent2 无需任何修改。

### Agent3（对比分析）

**不需要改动。**

Agent3 只对比候选列表的变化（新增/退出/排名变化），不依赖估值数据的真实性。

### 唯一需要关注的点

当从 Mock 切换到 Real 数据时，**历史归档数据的数据质量标记**需要处理：

```python
# 在对比时识别数据质量变化
if yesterday["data_quality_flag"] == "mock" and today["data_quality_flag"] == "real":
    # 添加提示：数据质量已提升，历史对比可能不准确
    report["note"] = "数据质量已从模拟切换为真实，历史对比仅供参考"
```

---

## 六、实施步骤

```
Step 1: 注册 Tushare 账号，获取 token
        ↓
Step 2: 安装依赖: pip install tushare
        ↓
Step 3: 配置环境变量 TUSHARE_TOKEN
        ↓
Step 4: 修改 etf_valuation_enricher.py，添加真实数据获取逻辑
        ↓
Step 5: 测试运行，验证数据质量
        ↓
Step 6: 观察 3-5 天，确认稳定后删除 mock 回退逻辑（可选）
```

---

## 七、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| Tushare API 限流 | 中 | 数据采集失败 | 保留 mock 回退逻辑 |
| 数据字段缺失 | 低 | 部分ETF无估值 | 使用 mock 填充缺失字段 |
| 代码格式不兼容 | 低 | 无法查询 | 添加代码格式转换函数 |
| 历史分位计算复杂 | 中 | 开发时间增加 | 先接入PE/PB，分位二期实现 |

---

## 八、预期效果

接入真实数据后：
- ✅ 估值数据真实可靠
- ✅ 筛选结果更具参考价值
- ✅ 可移除 "⚠️ 当前数据为模拟数据" 提示
- ✅ 为后续量化策略提供数据基础

---

## 附录：代码改动统计

| 文件 | 改动类型 | 改动行数（预估） |
|------|----------|------------------|
| `etf_valuation_enricher.py` | 新增真实数据获取方法 | +80 行 |
| `config/agent_config.json` | 新增配置项 | +10 行 |
| `requirements.txt` | 新增依赖 | +1 行 |
| Agent2/Agent3 | 无需改动 | 0 行 |

**总计：约 90 行代码，2 个文件改动**
