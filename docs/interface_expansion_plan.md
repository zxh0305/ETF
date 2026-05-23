# 接口扩充方案 - 保证数据够用

## 一、核心发现

### 1. 历史数据可以从接口获得！

**乐咕乐股接口提供20年历史数据：**

| 接口 | 数据量 | 覆盖指数 |
|------|--------|----------|
| `ak.stock_index_pe_lg("沪深300")` | 5108条 | 沪深300 |
| `ak.stock_index_pe_lg("上证50")` | 5168条 | 上证50 |
| `ak.stock_index_pe_lg("中证500")` | 4679条 | 中证500 |
| `ak.stock_index_pe_lg("中证1000")` | 2796条 | 中证1000 |

**这些数据可以直接计算历史分位！**

### 2. A股整体估值直接提供历史分位

```python
df = ak.stock_a_all_pb()
# 返回字段包含：
# - middlePB: PB中位数
# - quantileInAllHistoryMiddlePB: 历史分位
# - quantileInRecent10YearsMiddlePB: 近10年分位
```

---

## 二、当前数据覆盖缺口

| 数据类型 | 覆盖率 | 缺口 |
|----------|--------|------|
| 主流宽基指数PE/PB | 100%（4只） | ✅ 已解决 |
| 行业指数PE/PB | 0% | ❌ 需扩充 |
| ETF本身PE/PB | 10.5% | ⚠️ 可改进 |
| 历史分位数据 | 0% → 100% | ✅ 可解决 |

---

## 三、接口扩充方案

### 方案A：立即生效（推荐）

**利用现有可用接口，获取历史分位数据**

```python
# scripts/calc_index_percentile_v2.py

import akshare as ak
import pandas as pd

def calc_index_percentile_v2():
    """
    从乐咕乐股获取历史PE/PB，计算分位
    """
    indices = {
        "沪深300": "000300",
        "上证50": "000016",
        "中证500": "000905",
        "中证1000": "000852",
    }
    
    results = {}
    
    for name, code in indices.items():
        # 获取历史PE（20年数据）
        pe_df = ak.stock_index_pe_lg(symbol=name)
        pb_df = ak.stock_index_pb_lg(symbol=name)
        
        # 计算分位
        latest_pe = pe_df["滚动市盈率"].iloc[-1]
        latest_pb = pb_df.iloc[-1, 2]  # PB列
        
        # 历史分位计算
        pe_percentile = (pe_df["滚动市盈率"] <= latest_pe).mean() * 100
        pb_percentile = (pb_df.iloc[:, 2] <= latest_pb).mean() * 100
        
        results[code] = {
            "pe": latest_pe,
            "pb": latest_pb,
            "pe_percentile": pe_percentile,
            "pb_percentile": pb_percentile,
            "data_points": len(pe_df),
            "source": "乐咕乐股",
            "is_real": True
        }
    
    return results
```

**效果：**
- ✅ 4个主流指数有真实历史分位
- ✅ 覆盖约100只ETF（跟踪这4个指数的）
- ✅ 数据可追溯到2004年

---

### 方案B：扩充行业指数（1周内）

**接入东财行业估值接口**

当前系统已有 `RPT_VALUEINDUSTRY_DET` 接口，可覆盖128个行业指数。

```python
# 在 etf_valuation_enricher.py 中添加

def fetch_industry_valuation(self):
    """
    获取128个行业指数估值
    """
    params = {
        "reportName": "RPT_VALUEINDUSTRY_DET",
        "columns": "ALL"
    }
    # 返回字段：行业代码, 行业名称, PE, PB, 市值等
```

**效果：**
- ✅ 覆盖128个行业指数
- ✅ PE/PB覆盖率提升到50-70%
- ⚠️ 需要建立ETF→行业指数映射

---

### 方案C：ETF持仓映射（长期）

**通过ETF持仓计算估值**

```
ETF持仓 → 持仓股票PE/PB加权 → ETF估值
```

**步骤：**
1. 获取ETF持仓明细（东财基金持仓接口）
2. 获取个股PE/PB（`ak.stock_value_em()`）
3. 按市值加权计算

**效果：**
- ✅ 理论覆盖率90%+
- ⚠️ 开发成本高
- ⚠️ 需要每日更新持仓

---

## 四、立即可执行的改进

### Step 1：启用乐咕乐股接口（今天）

```bash
# 创建新的分位计算脚本
cat > scripts/calc_index_percentile_v2.py << 'EOF'
import akshare as ak
import json
from pathlib import Path

def main():
    indices = {
        "沪深300": "000300",
        "上证50": "000016",
        "中证500": "000905",
        "中证1000": "000852",
    }
    
    results = {}
    for name, code in indices.items():
        pe_df = ak.stock_index_pe_lg(symbol=name)
        pb_df = ak.stock_index_pb_lg(symbol=name)
        
        latest_pe = pe_df["滚动市盈率"].iloc[-1]
        latest_pb = pb_df.iloc[-1, 2]
        
        pe_pct = (pe_df["滚动市盈率"] <= latest_pe).mean() * 100
        pb_pct = (pb_df.iloc[:, 2] <= latest_pb).mean() * 100
        
        results[code] = {
            "pe": round(latest_pe, 2),
            "pb": round(latest_pb, 2),
            "pe_percentile": round(pe_pct, 1),
            "pb_percentile": round(pb_pct, 1),
            "data_years": round(len(pe_df) / 252, 1),
            "source": "乐咕乐股",
            "is_real": True
        }
    
    output = {
        "meta": {
            "source": "lg_eastmoney",
            "generated_at": str(pd.Timestamp.now()),
            "total_indices": len(results)
        },
        "data": results
    }
    
    Path("data/index_percentiles_v2.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2)
    )
    print(f"✅ 生成 {len(results)} 个指数的历史分位数据")

if __name__ == "__main__":
    main()
EOF

python3 scripts/calc_index_percentile_v2.py
```

### Step 2：更新估值enricher（今天）

```python
# 在 etf_valuation_enricher.py 中添加

def load_real_percentiles(self):
    """
    加载乐咕乐股真实分位数据
    """
    path = Path("data/index_percentiles_v2.json")
    if path.exists():
        data = json.loads(path.read_text())
        return data.get("data", {})
    return {}

def enrich_with_real_percentiles(self, record):
    """
    使用真实分位数据
    """
    real_pct = self.load_real_percentiles()
    
    # 检查ETF跟踪的指数
    tracking_index = record.get("tracking_index", {}).get("code")
    if tracking_index and tracking_index in real_pct:
        pct_data = real_pct[tracking_index]
        record.update({
            "pe_percentile": pct_data["pe_percentile"],
            "pb_percentile": pct_data["pb_percentile"],
            "percentile_real_flag": True,
            "percentile_source": "乐咕乐股历史数据"
        })
```

---

## 五、数据覆盖预期

| 阶段 | 时间 | PE/PB覆盖率 | 历史分位覆盖率 |
|------|------|-------------|---------------|
| 当前 | - | 10.5% | 0% |
| Step 1完成 | 今天 | 10.5% | **26%**（100只ETF） |
| Step 2完成 | 1周 | 50-70% | **50%** |
| Step 3完成 | 1月 | 90%+ | **90%** |

---

## 六、关键结论

### 历史数据可以从接口获得吗？

**可以！**

- 乐咕乐股提供20年历史PE/PB数据（5108条）
- A股整体估值接口直接提供历史分位
- 不需要自己积累，现在就可以用

### 如何扩充接口？

| 优先级 | 接口 | 效果 |
|--------|------|------|
| 🔴 高 | 乐咕乐股历史数据 | 立即解决4个主流指数 |
| 🟡 中 | 东财行业估值接口 | 扩展到128个行业 |
| 🟢 低 | ETF持仓映射 | 理论全覆盖 |

### 如何保证数据够用？

**短期（今天）：**
- 启用乐咕乐股历史分位
- 覆盖100只主流ETF
- 满足基本投资决策需求

**中期（1周）：**
- 接入行业估值接口
- 覆盖50%以上的ETF
- 提供行业轮动参考

**长期（1月）：**
- ETF持仓映射方案
- 覆盖90%+ETF
- 满足专业投资需求
