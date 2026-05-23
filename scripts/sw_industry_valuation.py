#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
申万行业估值计算器 v3.0 - 直接调用官方API
=========================================
数据源：akshare.sw_index_first_info() — 申万官方估值
一次性返回全部31个申万一级行业的PE/PB/股息率，无需手工计算

与v2.0对比：
- v2.0: index_component_sw(成分) + stock_value_em(个股估值) 手工加权
  → 问题：akshare的index_component_sw行业代码与标准申万不一致，银行含建材股
- v3.0: sw_index_first_info() 直接申万官方估值数据，31个行业全覆盖
"""

import json, logging, os
from datetime import datetime
from pathlib import Path

for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    os.environ.pop(var, None)

import akshare as ak

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", force=True)
logger = logging.getLogger("sw_val_v3")

BASE_DIR = Path(__file__).parent.parent.resolve()
OUT_FILE = BASE_DIR / "data" / "sw_industry_valuation_latest.json"


# ============================================================================
# 申万行业关键词映射（ETF名称 → 申万行业代码）
# 用于etf_valuation_enricher.py
# ============================================================================
SW_KEYWORD_MAP = {
    # 官方31个行业及常用别名
    "农林牧渔": "801010",
    "基础化工": "801030",
    "钢铁": "801040",
    "有色金属": "801050",
    "电子": "801080",
    "汽车": "801880",
    "家用电器": "801110",
    "食品饮料": "801120",
    "纺织服饰": "801130",
    "轻工制造": "801140",
    "医药生物": "801150",
    "公用事业": "801160",
    "交通运输": "801170",
    "房地产": "801180",
    "商贸零售": "801200",
    "社会服务": "801210",
    "银行": "801780",
    "非银金融": "801790",
    "综合": "801230",
    "建筑材料": "801710",
    "建筑装饰": "801720",
    "电力设备": "801730",
    "机械设备": "801890",
    "国防军工": "801740",
    "计算机": "801750",
    "传媒": "801760",
    "通信": "801770",
    "煤炭": "801950",
    "石油石化": "801960",
    "环保": "801970",
    "美容护理": "801980",

    # 常用别名（ETF名称中可能出现的关键词）
    "军工": "801740",
    "国防": "801740",
    "证券": "801790",
    "券商": "801790",
    "保险": "801790",
    "地产": "801180",
    "银行ETF": "801780",
    "有色": "801050",
    "新能源": "801730",
    "光伏": "801730",
    "储能": "801730",
    "电力": "801160",
    "公用": "801160",
    "煤炭": "801950",
    "钢铁": "801040",
    "化工": "801030",
    "农业": "801010",
    "畜牧": "801010",
    "酒": "801120",
    "白酒": "801120",
    "食品": "801120",
    "饮料": "801120",
    "消费": "801120",  # 泛消费归食品饮料
    "医药": "801150",
    "中药": "801150",
    "医疗": "801150",
    "科技": "801750",  # 泛科技归计算机
    "TMT": "801750",
    "半导体": "801080",
    "芯片": "801080",
    "通信": "801770",
    "传媒": "801760",
    "互联网": "801760",
    "软件": "801750",
    "计算机": "801750",
    "环保": "801970",
    "新能源汽车": "801880",
    "汽车制造": "801880",
    "家电": "801110",
    "轻工": "801140",
    "纺织": "801130",
    "商贸": "801200",
    "零售": "801200",
    "旅游": "801210",
    "休闲": "801210",
    "教育": "801210",
    "美容": "801980",
    "化妆品": "801980",
}


# ============================================================================
# 核心：获取申万行业官方估值
# ============================================================================
def fetch_sw_industry_valuation() -> dict:
    """调用sw_index_first_info()，返回申万官方行业估值"""
    logger.info("正在获取申万行业官方估值...")
    df = ak.sw_index_first_info()

    industries = {}
    for _, row in df.iterrows():
        code = row['行业代码'].replace('.SI', '')
        name = row['行业名称']
        pe_static = row['静态市盈率']
        pe_ttm = row['TTM(滚动)市盈率']
        pb = row['市净率']
        div_yield = row['静态股息率']
        count = row['成份个数']

        industries[code] = {
            "code": code,
            "name": name,
            "static_pe": round(float(pe_static), 2) if pe_static and pe_static == pe_static else None,  # NaN check
            "pe_ttm": round(float(pe_ttm), 2) if pe_ttm and pe_ttm == pe_ttm else None,
            "pb": round(float(pb), 2) if pb and pb == pb else None,
            "dividend_yield": round(float(div_yield), 2) if div_yield and div_yield == div_yield else None,
            "component_count": int(count) if count else 0,
            "data_source": "申万官方估值(sw_index_first_info)",
        }

        logger.info(f"  {code} {name}: PE_TTM={pe_ttm:.2f} PB={pb:.2f} 成分数={count}")

    return industries


# ============================================================================
# 构建索引（快速查询用）
# ============================================================================
def build_sw_index(industries: dict) -> dict:
    """构建多维度索引：代码→行业、名称→行业"""
    by_code = {code: ind for code, ind in industries.items()}
    by_name = {ind['name']: ind for ind in industries.values()}
    by_pe = {code: ind['pe_ttm'] for code, ind in industries.items() if ind.get('pe_ttm')}
    return {
        "by_code": by_code,
        "by_name": by_name,
        "by_pe": by_pe,
    }


# ============================================================================
# 主流程
# ============================================================================
def run() -> dict:
    logger.info("=" * 70)
    logger.info("申万行业估值计算 v3.0（直接官方API）")
    logger.info("=" * 70)

    t_start = datetime.now()

    try:
        industries = fetch_sw_industry_valuation()
    except Exception as e:
        logger.error(f"获取申万行业数据失败: {e}")
        raise

    t_end = datetime.now()
    duration = (t_end - t_start).total_seconds()

    # 统计
    valid = {code: ind for code, ind in industries.items() if ind.get('pe_ttm')}
    pe_vals = [ind['pe_ttm'] for ind in valid.values()]

    meta = {
        "version": "3.0",
        "generated_at": t_end.isoformat(),
        "duration_seconds": round(duration, 1),
        "total_industries": len(industries),
        "valid_industries": len(valid),
        "data_source": "akshare.sw_index_first_info() — 申万官方估值",
        "note": "v3.0弃用index_component_sw（行业代码错误），改用官方估值API",
    }
    if pe_vals:
        import numpy as np
        meta.update({
            "avg_pe": round(np.mean(pe_vals), 2),
            "min_pe": round(min(pe_vals), 2),
            "max_pe": round(max(pe_vals), 2),
            "median_pe": round(np.median(pe_vals), 2),
        })

    output = {
        "meta": meta,
        "industries": industries,
        "index": build_sw_index(industries),
    }

    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, ensure_ascii=False, indent=2, fp=f)

    logger.info("=" * 70)
    logger.info(f"✅ 完成！耗时: {duration:.1f}秒")
    logger.info(f"   有效行业: {len(valid)}/{len(industries)}")
    if pe_vals:
        logger.info(f"   PE范围: {meta['min_pe']:.2f} ~ {meta['max_pe']:.2f}，中位数: {meta['median_pe']:.2f}")
    logger.info(f"   输出: {OUT_FILE}")

    # 打印排序结果
    valid_sorted = sorted(valid.values(), key=lambda x: x.get('pe_ttm') or 999)
    print("\n" + "=" * 60)
    print("申万行业估值（按PE_TTM升序）")
    print("=" * 60)
    print(f"{'代码':<8} {'行业':<10} {'PE(TTM)':>9} {'PB':>7} {'股息率':>8} {'成分数':>7}")
    print("-" * 60)
    for ind in valid_sorted:
        pe = f"{ind['pe_ttm']:.2f}" if ind.get('pe_ttm') else "N/A"
        pb = f"{ind['pb']:.2f}" if ind.get('pb') else "N/A"
        dy = f"{ind['dividend_yield']:.2f}%" if ind.get('dividend_yield') else "N/A"
        cnt = ind.get('component_count', '-')
        trust = "✅" if (ind.get('pe_ttm') or 999) < 50 else "⚠️"
        print(f"{trust}{ind['code']:<7} {ind['name']:<10} {pe:>9} {pb:>7} {dy:>8} {cnt:>7}")
    print("=" * 60)

    return output


if __name__ == "__main__":
    run()