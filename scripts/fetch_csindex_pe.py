#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_csindex_pe.py - 中证指数官方历史PE + 真实分位计算
从 csindex.com 获取6年+日K数据(含滚动市盈率)，计算真实PE分位
写入 index_percentiles_latest.json 的 indices 字段
"""
import akshare as ak
import json
import ssl
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

ssl._create_default_https_context = ssl._create_unverified_context

BASE_DIR = Path(__file__).parent.parent.resolve()
PERCENTILE_FILE = BASE_DIR / "data" / "index_percentiles_latest.json"

CSINDEX_BROAD = {
    "000300": "沪深300", "000905": "中证500", "000016": "上证50",
    "000852": "中证1000", "000906": "中证800", "000010": "上证180",
    "000903": "中证100", "000015": "上证红利", "000688": "科创50",
}


def calc_real_percentile(history_values, current_value):
    if history_values is None or len(history_values) == 0:
        return None
    if current_value is None:
        return None
    valid = history_values.dropna()
    if len(valid) == 0:
        return None
    count = (valid <= float(current_value)).sum()
    return round(float(count) / len(valid) * 100, 2)


def fetch_csindex_pe(code: str, name: str) -> Optional[Dict]:
    try:
        print(f"  获取 {code} {name}...", end=" ", flush=True)
        df = ak.stock_zh_index_hist_csindex(
            symbol=code,
            start_date="20200101",
            end_date=datetime.now().strftime("%Y%m%d")
        )
        if df is None or len(df) == 0:
            print("❌ 无数据"); return None

        pe_col = None
        for col in df.columns:
            if '市盈率' in str(col) or 'PE' in str(col).upper():
                pe_col = col; break
        if pe_col is None:
            print(f"❌ 无PE列"); return None

        pe_series = df[pe_col].astype(float)
        latest_pe = pe_series.iloc[-1]
        latest_date = str(df['日期'].iloc[-1])[:10]
        pe_pct = calc_real_percentile(pe_series, latest_pe)

        result = {
            "code": code, "name": name,
            "pe": round(float(latest_pe), 2),
            "pe_percentile": pe_pct,
            "pe_count": len(df),
            "pe_data_start": str(df['日期'].iloc[0])[:10],
            "pe_data_end": latest_date,
            "is_real_pe": True,
            "source": "中证指数官方(csindex)",
        }
        print(f"✅ PE={latest_pe:.2f} 分位={pe_pct}% ({len(df)}条)")
        return result
    except Exception as e:
        print(f"❌ {str(e)[:60]}"); return None


def main():
    print("=" * 60)
    print("📊 中证指数官方PE - 真实分位计算")
    print("=" * 60)

    indices_data = {}
    for code, name in CSINDEX_BROAD.items():
        result = fetch_csindex_pe(code, name)
        if result:
            indices_data[code] = result
        time.sleep(0.5)

    print(f"\n✅ 成功 {len(indices_data)}/{len(CSINDEX_BROAD)}")

    if not PERCENTILE_FILE.exists():
        existing = {"meta": {}, "indices": {}, "sw_industries": {}, "etf_mapping": {}, "stats": {}}
    else:
        with open(PERCENTILE_FILE, 'r', encoding='utf-8') as f:
            existing = json.load(f)

    existing["indices"] = indices_data
    existing["meta"]["csindex_update_time"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with open(PERCENTILE_FILE, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"✅ 已写入 {PERCENTILE_FILE}")
    return indices_data

if __name__ == "__main__":
    main()
