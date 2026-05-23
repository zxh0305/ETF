# Pipeline 健康检查设计文档

## 目标

确保 ETF-Agent 能够长期稳定积累历史数据，及时发现和预警问题。

## 检查项

| # | 检查项 | 说明 | 失败后果 |
|---|--------|------|----------|
| 1 | 关键文件存在 | etf_spot_latest.json、etf_valuation_latest.json、dialog_brief_latest.txt | 无法生成简报 |
| 2 | 今日快照存在 | archive/index_valuation_history/YYYY-MM-DD.json | 数据中断，影响分位积累 |
| 3 | 快照条数 | 当日快照包含的指数数量 | 数据覆盖不全 |
| 4 | 最近7天快照 | 检查连续性，跳过周末 | 发现历史缺失 |
| 5 | 数据新鲜度 | 估值数据是否为当日 | 数据过期 |

## 状态等级

```
healthy  → 一切正常
warning  → 非致命问题（历史快照缺失、数据略旧）
error    → 关键问题（文件缺失、今日 pipeline 未执行）
```

## 输出文件

`output/pipeline_health_latest.json`

```json
{
  "date": "2026-04-19",
  "check_time": "2026-04-19 20:15:00",
  "status": "healthy",
  "pipeline_status": "executed",
  "files_ok": true,
  "files": {
    "etf_spot_latest.json": {"exists": true, "mtime": "2026-04-19 09:25:00", "size": 123456},
    "etf_valuation_latest.json": {"exists": true, "mtime": "2026-04-19 09:26:00", "size": 234567},
    "dialog_brief_latest.txt": {"exists": true, "mtime": "2026-04-19 09:27:00", "size": 3456}
  },
  "today_snapshot": {
    "exists": true,
    "index_count": 44,
    "date": "2026-04-19"
  },
  "recent_7d": {
    "existing_count": 5,
    "missing_count": 0,
    "missing_dates": []
  },
  "total_snapshots": 2,
  "data_freshness": {
    "valuation_collect_time": "2026-04-19 09:25:00",
    "valuation_mode": "MOCK"
  },
  "warning_messages": []
}
```

## 运行方式

### 手动运行
```bash
cd /Users/zhangxianghao/.qclaw/workspace/etf-agent
python3 scripts/check_pipeline_health.py
```

### 接入每日 Pipeline
可在 `run_etf_full_pipeline.py` 末尾添加 step8，或作为独立 cron 任务在每日 09:30 执行。

### 接入每日简报
在 `generate_dialog_brief.py` 中读取 `pipeline_health_latest.json`，在简报开头添加健康状态摘要：

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏥 系统健康状态: ✅ 正常
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• 今日 pipeline 已执行
• 指数快照: 44 个
• 历史数据: 已积累 2 天
```

或警告时：
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏥 系统健康状态: ⚠️ 警告
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• 最近7天缺失 2 个快照（2026-04-15, 2026-04-16）
```

## 后续扩展

1. **告警推送**：status=error 时发送微信/邮件通知
2. **数据完整性**：检查 ETF 数量是否异常减少
3. **趋势监控**：记录每日健康状态，绘制趋势图
