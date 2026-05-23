#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF穿透估值合并脚本 v1.0
将行业穿透估值数据合并到主估值文件中

逻辑：
1. 读取 etf_valuation_latest.json（主估值数据）
2. 读取 etf_holding_industry_valuation.json（穿透估值数据）
3. 对无分位的ETF，用穿透估值补充
4. 保存合并后的数据

流水线中在step2（估值补全）之后运行
"""

import json
import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = BASE_DIR / 'data'
OUTPUT_DIR = BASE_DIR / 'output'

VALUATION_JSON = DATA_DIR / 'etf_valuation_latest.json'
HOLDINGS_JSON = OUTPUT_DIR / 'etf_holding_industry_valuation.json'


def main():
    print("=" * 50)
    print("ETF穿透估值合并")
    print("=" * 50)
    
    # 检查输入文件
    if not VALUATION_JSON.exists():
        print(f"❌ 主估值文件不存在: {VALUATION_JSON}")
        sys.exit(1)
    
    if not HOLDINGS_JSON.exists():
        print(f"⚠️ 穿透估值文件不存在: {HOLDINGS_JSON}")
        print("跳过合并（首次运行或穿透估值未执行）")
        sys.exit(0)  # 不阻塞流水线
    
    # 读取数据
    with open(VALUATION_JSON) as f:
        main_data = json.load(f)
    
    with open(HOLDINGS_JSON) as f:
        holdings_data = json.load(f)
    
    # 构建穿透估值查找表
    holdings_map = {}
    for e in holdings_data.get('data', []):
        v = e.get('valuation', {})
        if v.get('status') == 'success':
            holdings_map[e['code']] = {
                'pe_ttm': v.get('estimated_pe'),
                'pb': v.get('estimated_pb'),
                'pe_percentile': v.get('estimated_pe_percentile'),
                'pb_percentile': v.get('estimated_pb_percentile'),
                'pe_pb_source': f"穿透-{','.join(list(v.get('industry_weights', {}).keys())[:3])}",
                'holdings_count': e.get('holdings_count'),
                'mapped_weight_pct': v.get('mapped_weight_pct'),
            }
    
    print(f"穿透估值可用: {len(holdings_map)}只ETF")
    
    # 合并
    merged_pe = 0
    merged_pct = 0
    for etf in main_data.get('data', []):
        code = etf.get('code', '')
        if code in holdings_map:
            hv = holdings_map[code]
            # 补充PE/PB（仅当原数据无PE时）
            if etf.get('pe_ttm') is None and hv.get('pe_ttm') is not None:
                etf['pe_ttm'] = hv['pe_ttm']
                etf['pb'] = hv.get('pb')
                merged_pe += 1
            # 补充分位（仅当原数据无分位时）
            if etf.get('pe_percentile') is None and hv.get('pe_percentile') is not None:
                etf['pe_percentile'] = hv['pe_percentile']
                etf['pb_percentile'] = hv.get('pb_percentile')
                etf['pe_pb_source'] = hv['pe_pb_source']
                merged_pct += 1
    
    # 统计
    total = len(main_data.get('data', []))
    has_pct = sum(1 for e in main_data['data'] if e.get('pe_percentile') is not None)
    
    print(f"新增PE/PB: {merged_pe}只")
    print(f"新增分位: {merged_pct}只")
    print(f"分位覆盖率: {has_pct}/{total} = {has_pct/total*100:.1f}%")
    
    # 保存
    with open(VALUATION_JSON, 'w') as f:
        json.dump(main_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 已保存合并后数据到 {VALUATION_JSON.name}")
    
    # 输出统计供流水线记录
    stats = {
        'total_etfs': total,
        'has_pe_percentile': has_pct,
        'coverage_pct': round(has_pct / total * 100, 1),
        'merged_pe': merged_pe,
        'merged_pct': merged_pct,
    }
    print(f"STATS: {json.dumps(stats, ensure_ascii=False)}")


if __name__ == '__main__':
    main()
