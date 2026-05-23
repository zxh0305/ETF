#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查红利ETF的数据来源"""

import json
from pathlib import Path

DATA_FILE = Path("/Users/zhangxianghao/.qclaw/workspace/etf-agent/data/etf_valuation_latest.json")

with open(DATA_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

records = data.get("data", [])

# 查找红利ETF
dividend_etfs = [e for e in records if "红利" in e.get("name", "")]

print(f"找到 {len(dividend_etfs)} 只红利ETF")
print()

for etf in divident_etfs[:10]:
    code = etf.get("code", "")
    name = etf.get("name", "")
    real_flag = etf.get("percentile_real_flag", False)
    source = etf.get("pe_pb_source", "")
    pe_pct = etf.get("pe_percentile", "N/A")
    pb_pct = etf.get("pb_percentile", "N/A")
    
    print(f"{code} {name}")
    print(f"  percentile_real_flag: {real_flag}")
    print(f"  pe_pb_source: {source}")
    print(f"  PE%: {pe_pct}, PB%: {pb_pct}")
    print()
