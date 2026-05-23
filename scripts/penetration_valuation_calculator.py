#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
穿透估值计算器 v1.0 - 基于持仓加权计算ETF真实估值
===================================================
原理：
1. 获取ETF季报持仓数据（前十大成分股）
2. 获取成分股当前PE/PB
3. 按权重加权计算ETF整体PE/PB
4. 输出：etf_penetration_valuation_latest.json

数据来源：
- ETF持仓：巨潮资讯/天天基金网（季报数据）
- 成分股PE/PB：AkShare实时行情

优势：
- 比申万行业加权更精准（直接用ETF实际持仓）
- 可追溯（每只成分股权重明确）
- 可计算真实分位（积累3年+历史数据后）

局限：
- 依赖季报数据（延迟1-3个月）
- 只覆盖前十大成分股（约60-80%权重）
- 需要每日计算（计算量较大）

实施计划：
- v1.0：计算前十大成分股加权PE/PB（本月完成）
- v2.0：积累历史数据，计算真实分位（3年后）
- v3.0：全覆盖（所有成分股，不仅前十大）

作者：QClaw AI
日期：2026-05-22
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import akshare as ak
import pandas as pd

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("penetration_valuation")

# 路径配置
BASE_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "etf_penetration_valuation_latest.json"
ETF_DATA_FILE = DATA_DIR / "etf_valuation_latest.json"  # 输入：已有估值数据

# 确保目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_etf_holdings(etf_code: str) -> Optional[List[Dict]]:
    """
    获取ETF持仓数据（前十大成分股）
    
    数据源：
    1. 优先：AkShare fund_etf_holding() API
    2. 备用：网页爬虫（基金季报）
    
    返回：
    [
        {"stock_code": "sh600519", "stock_name": "贵州茅台", "weight": 15.2},
        ...
    ]
    """
    try:
        # 尝试AkShare API
        # 注意：etf_code格式需要转换（sz159915 → 159915）
        code_clean = etf_code.replace("sh", "").replace("sz", "")
        
        # AkShare函数：fund_etf_holding_em(emt="持有股票")
        df = ak.fund_etf_holding_em(symbol=code_clean, emt="持有股票")
        
        if df is None or df.empty:
            logger.warning(f"  ⚠️ {etf_code} 无持仓数据")
            return None
        
        # 取前十大成分股
        top10 = df.head(10)
        
        holdings = []
        for _, row in top10.iterrows():
            holdings.append({
                "stock_code": row.get("股票代码", ""),
                "stock_name": row.get("股票名称", ""),
                "weight": float(row.get("持仓权重", 0)),
            })
        
        logger.info(f"  ✅ {etf_code} 获取到 {len(holdings)} 只成分股持仓")
        return holdings
        
    except Exception as e:
        logger.warning(f"  ❌ {etf_code} 获取持仓失败: {e}")
        return None


def get_stock_pe_pb(stock_code: str) -> Optional[Dict]:
    """
    获取个股当前PE/PB
    
    数据源：AkShare stock_zh_a_spot_em()
    
    返回：
    {"pe": 25.3, "pb": 3.2, "pe_percentile": None}
    """
    try:
        # 获取A股实时行情
        df = ak.stock_zh_a_spot_em()
        
        # 查找目标股票
        stock = df[df["代码"] == stock_code]
        
        if stock.empty:
            logger.warning(f"    ⚠️ 股票 {stock_code} 未找到")
            return None
        
        row = stock.iloc[0]
        
        return {
            "pe": float(row.get("市盈率-动态", 0)),
            "pb": float(row.get("市净率", 0)),
        }
        
    except Exception as e:
        logger.warning(f"    ❌ 获取股票 {stock_code} PE/PB失败: {e}")
        return None


def calculate_weighted_valuation(holdings: List[Dict]) -> Optional[Dict]:
    """
    计算加权PE/PB
    
    公式：
    ETF_PE = Σ(成分股PE × 权重) / Σ(权重)
    ETF_PB = Σ(成分股PB × 权重) / Σ(权重)
    
    返回：
    {"pe": 18.5, "pb": 2.3, "coverage": 0.75}
    """
    if not holdings:
        return None
    
    total_weight = sum(h["weight"] for h in holdings)
    if total_weight == 0:
        return None
    
    weighted_pe = 0
    weighted_pb = 0
    valid_count = 0
    
    for holding in holdings:
        stock_code = holding["stock_code"]
        weight = holding["weight"]
        
        # 获取个股PE/PB
        stock_data = get_stock_pe_pb(stock_code)
        
        if stock_data and stock_data["pe"] > 0 and stock_data["pb"] > 0:
            weighted_pe += stock_data["pe"] * weight
            weighted_pb += stock_data["pb"] * weight
            valid_count += 1
    
    if valid_count == 0:
        return None
    
    # 归一化
    etf_pe = weighted_pe / total_weight
    etf_pb = weighted_pb / total_weight
    coverage = valid_count / len(holdings)
    
    return {
        "pe": round(etf_pe, 2),
        "pb": round(etf_pb, 2),
        "coverage": round(coverage, 2),
        "valid_count": valid_count,
        "total_count": len(holdings),
    }


def process_etf(etf: Dict) -> Dict:
    """
    处理单只ETF：计算穿透估值
    """
    code = etf.get("code", "")
    name = etf.get("name", "")
    
    logger.info(f"处理 {code} {name}...")
    
    # 1. 获取持仓
    holdings = get_etf_holdings(code)
    
    if not holdings:
        return {
            **etf,
            "penetration_pe": None,
            "penetration_pb": None,
            "penetration_coverage": 0,
            "penetration_status": "no_holdings",
        }
    
    # 2. 计算加权估值
    valuation = calculate_weighted_valuation(holdings)
    
    if not valuation:
        return {
            **etf,
            "penetration_pe": None,
            "penetration_pb": None,
            "penetration_coverage": 0,
            "penetration_status": "calc_failed",
        }
    
    # 3. 返回结果
    return {
        **etf,
        "penetration_pe": valuation["pe"],
        "penetration_pb": valuation["pb"],
        "penetration_coverage": valuation["coverage"],
        "penetration_valid_count": valuation["valid_count"],
        "penetration_total_count": valuation["total_count"],
        "penetration_status": "success",
        "penetration_holdings": holdings,  # 保存持仓明细
    }


def main():
    """主函数"""
    logger.info("=" * 70)
    logger.info("穿透估值计算器 v1.0 - 基于持仓加权计算ETF真实估值")
    logger.info("=" * 70)
    
    # 1. 加载ETF数据
    if not ETF_DATA_FILE.exists():
        logger.error(f"❌ ETF数据文件不存在: {ETF_DATA_FILE}")
        return
    
    with open(ETF_DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    records = data.get("data", [])
    logger.info(f"加载 {len(records)} 条ETF记录")
    
    # 2. 筛选需要计算穿透估值的ETF
    # 优先处理：行业/主题ETF（宽基ETF已有乐咕乐股真实数据）
    target_etfs = []
    for etf in records:
        # 跳过已有真实数据的宽基ETF
        if etf.get("percentile_real_flag"):
            continue
        
        # 只处理行业/主题ETF（排除货币、债券ETF）
        name = etf.get("name", "")
        if any(x in name for x in ["货币", "债券", "国债", "企业债"]):
            continue
        
        target_etfs.append(etf)
    
    logger.info(f"目标ETF: {len(target_etfs)} 只（行业/主题ETF，无真实数据）")
    
    # 3. 计算穿透估值（分批处理，避免API限流）
    results = []
    for i, etf in enumerate(target_etfs[:10]):  # 先处理前10只（测试）
        logger.info(f"\n[{i+1}/{min(10, len(target_etfs))}] 处理中...")
        
        result = process_etf(etf)
        results.append(result)
        
        # 限流：每次请求后暂停1秒
        time.sleep(1)
    
    # 4. 保存结果
    output = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "version": "v1.0",
            "description": "穿透估值计算结果（基于持仓加权）",
            "coverage": f"{len([r for r in results if r.get('penetration_status')=='success'])}/{len(results)} 成功",
        },
        "data": results,
    }
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    logger.info("=" * 70)
    logger.info(f"✅ 穿透估值计算完成！")
    logger.info(f"   输出: {OUTPUT_FILE}")
    logger.info(f"   成功: {len([r for r in results if r.get('penetration_status')=='success'])} 只")
    logger.info(f"   失败: {len([r for r in results if r.get('penetration_status')!='success'])} 只")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
