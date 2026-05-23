# PE/PB 历史分位过渡计划

## 背景

当前系统中 `pe_percentile` 和 `pb_percentile` 由 `MockDataGenerator` 的 hash 算法生成，
是**伪随机数**，与真实历史分位无关。这些值被用于：
- 筛选条件（模拟池：PE或PB分位 ≤ 30%）
- 评分权重（30% PE分位 + 20% PB分位）
- 简报文案（"PE低分位(12.3%)"等标签）
- 推荐语（"当前估值低位"等判断）

## 过渡方案（v2.1 → v3.0）

### 阶段一：停用伪分位（v2.1，2026-04-19 ✅ 已完成）

| 变更项 | 变更内容 |
|--------|----------|
| ScoringEngine | 停用 pe/pb_percentile 评分，权重重分配：PE绝对值30% + PEG35% + 流动性35% |
| ReasonTagGenerator | 移除 "PE低分位" 等标签，改为 "PE绝对值较低" 等基于真实值的标签 |
| RecommendationGenerator | 移除 "低估" 判断，仅输出观察性结论 |
| _passes_mock_pool | 直接返回 False，模拟池暂时停用 |
| _enrich_etf | pe/pb_percentile 输出 None，原伪值存入 unavailable_mock_percentile |
| generate_markdown_report | 移除 PE分位/PB分位列，添加过渡说明 |
| generate_dialog_brief | 移除分位引用，模拟池改为停用说明 |
| etf_valuation_enricher | 不再生成 mock pe_percentile/pb_percentile，一律设为 None |
| agent2_rules.json | 更新版本为 2.1，评分权重调整 |

### 阶段二：积累真实快照（进行中）

- 每日 pipeline step6 调用 `archive_index_snapshot.py` 归档
- 需积累约 **250 个交易日**（约 1 年）
- 进度查看：`ls archive/index_valuation_history/*.json | wc -l`

### 阶段三：启用真实分位（v3.0，待触发）

触发条件：至少有一个主流指数积累 ≥ 250 个交易日快照

| 变更项 | 预期变更 |
|--------|----------|
| calc_index_percentiles.py | 每日计算真实分位 → data/index_percentiles_latest.json |
| etf_valuation_enricher.py | 读取 index_percentiles_latest.json 回填真实分位 |
| ScoringEngine | 重新引入分位评分维度（如权重20%） |
| _passes_mock_pool | 重新启用，使用真实分位筛选 |
| agent2_rules.json | 版本升至 3.0 |

### 关键文件

```
scripts/
  archive_index_snapshot.py   # 每日归档（已在pipeline中）
  calc_index_percentiles.py   # 分位计算器（已创建骨架）
  etf_valuation_enricher.py   # 估值补全（待v3.0接入分位回填）
  agent2_etf_screener.py      # 筛选器（v2.1过渡版）
  generate_dialog_brief.py    # 简报生成（v2.1过渡版）

config/
  agent2_rules.json           # 筛选规则（v2.1）

data/
  index_percentiles_latest.json  # 待生成

archive/
  index_valuation_history/       # 每日快照（逐步积累）
```
