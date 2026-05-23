#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查sz159905的状态"""

import json
from pathlib import Path

OUTPUT_FILE = Path("/Users/zhangxianghao/.qclaw/workspace/etf-agent/output/low_valuation_candidates_latest.json")

with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

records = data.get("data", [])

# 查找sz159905
target = None
for etf in records:
    if etf.get("code") == "sz159905":
        target = etf
        break

if not target:
    print("❌ 未找到sz159905")
    exit(1)

print(f"ETF: {target['code']} {target['name']}")
print(f"  pool: {target.get('pool')}")
print(f"  percentile_real_flag: {target.get('percentile_real_flag')}")
print(f"  pe_percentile: {target.get('pe_percentile')}")
print(f"  pb_percentile: {target.get('pb_percentile')}")
print(f"  peg: {target.get('peg')}")
print(f"  avg_amount_20d: {target.get('avg_amount_20d')}")
print(f"  data_quality_flag: {target.get('data_quality_flag')}")
print(f"  pe_pb_source: {target.get('pe_pb_source')}")

# 检查是否满足正式池条件
pe_pct = target.get("pe_percentile")
pb_pct = target.get("pb_percentile")
peg = target.get("peg")
avg_amt = target.get("avg_amount_20d") or target.get("amount")

print("\n正式池条件检查：")
print(f"  1. PE分位 ≤ 30%: {pe_pct} → {'✅' if pe_pct and pe_pct <= 30 else '❌'}")
print(f"  2. PB分位 ≤ 30%: {pb_pct} → {'✅' if pb_pct and pb_pct <= 30 else '❌'}")
print(f"  3. PEG < 1: {peg} → {'✅' if peg and peg < 1 else '❌'}")
print(f"  4. 日均成交额 ≥ 1亿: {avg_amt} → {'✅' if avg_amt and avg_amt >= 1e8 else '❌'}")

# 检查是否满足关注池条件
WATCH_LIQ_MIN = 3_000_000  # 300万
print(f"\n关注池条件检查：")
print(f"  1. PE分位 ≤ 30% 或 PB分位 ≤ 30%: {'✅' if (pe_pct and pe_pct <= 30) or (pb_pct and pb_pct <= 30) else '❌'}")
print(f"  2. 日均成交额 ≥ 300万: {avg_amt} → {'✅' if avg_amt and avg_amt >= WATCH_LIQ_MIN else '❌'}")
