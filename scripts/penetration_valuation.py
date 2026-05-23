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
- ETF持仓：AkShare fund_etf_holding_em()
- 成分股PE/PB：AkShare stock_zh_a_spot_em()

优势：
- 比申万行业加权更精准（直接用ETF实际持仓）
- 可追溯（每只成分股权重明确）
- 可计算真实分位（积累3年+历史数据后）

局限：
- 依赖季报数据（延迟1-3个月）
- 只覆盖前十大成分股（约60-80%权重）
- 需要每日计算（计算量较大）

实施计划：
- v1.0：计算前十大成分股加权PE/PB（本周完成）
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
    
    数据源：AkShare fund_portfolio_hold_em()
    
    返回：
    [
        {"stock_code": "sh600519", "stock_name": "贵州茅台", "weight": 15.2},
        ...
    ]
    """
    try:
        # etf_code格式转换（sz159915 → 159915）
        code_clean = etf_code.replace("sh", "").replace("sz", "")
        
        # ✅ 修正：使用正确的API fund_portfolio_hold_em()
        df = ak.fund_portfolio_hold_em(symbol=code_clean)
        
        if df is None or df.empty:
            logger.warning(f"  ⚠️ {etf_code} 无持仓数据")
            return None
        
        # 取前十大成分股
        top10 = df.head(10)
        
        holdings = []
        for _, row in top10.iterrows():
            # 股票代码格式统一（加sh/sz前缀）
            stock_code_raw = str(row.get("股票代码", ""))
            if stock_code_raw.startswith("6"):
                stock_code = "sh" + stock_code_raw
            elif stock_code_raw.startswith("0") or stock_code_raw.startswith("3"):
                stock_code = "sz" + stock_code_raw
            else:
                stock_code = stock_code_raw
            
            holdings.append({
                "stock_code": stock_code,
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
    {"pe": 25.3, "pb": 3.2}
    """
    try:
        # 获取A股实时行情
        df = ak.stock_zh_a_spot_em()
        
        # 代码格式转换（sh600519 → 600519）
        code_clean = stock_code.replace("sh", "").replace("sz", "")
        
        # 查找目标股票
        stock = df[df["代码"] == code_clean]
        
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
            weighted_pe += stock_data["pe"] * (weight / 100)  # 权重是百分比
            weighted_pb += stock_data["pb"] * (weight / 100)
            valid_count += 1
    
    if valid_count == 0:
        return None
    
    # 计算加权平均
    etf_pe = weighted_pe
    etf_pb = weighted_pb
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
        "penetration_holdings": holdings[:5],  # 只保存前5只（节省空间）
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
    max_test = min(5, len(target_etfs))  # 先测试5只
    
    logger.info(f"\n开始测试（前 {max_test} 只）...")
    
    for i, etf in enumerate(target_etfs[:max_test]):
        logger.info(f"\n[{i+1}/{max_test}] 处理中...")
        
        result = process_etf(etf)
        results.append(result)
        
        # 限流：每次请求后暂停2秒
        if i < max_test - 1:
            logger.info(f"  等待2秒（避免API限流）...")
            time.sleep(2)
    
    # 4. 保存结果
    success_count = len([r for r in results if r.get("penetration_status") == "success"])
    
    output = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "version": "v1.0",
            "description": "穿透估值计算结果（基于持仓加权）",
            "test_mode": f"前{max_test}只测试",
            "success_count": success_count,
            "total_count": len(results),
        },
        "data": results,
    }
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    logger.info("=" * 70)
    logger.info(f"✅ 穿透估值测试完成！")
    logger.info(f"   输出: {OUTPUT_FILE}")
    logger.info(f"   成功: {success_count}/{len(results)} 只")
    logger.info(f"   失败: {len(results) - success_count}/{len(results)} 只")
    logger.info("=" * 70)
    logger.info("\n下次运行：移除测试限制，处理全部目标ETF")
    logger.info("预计时间：~{}分钟（{}只ETF × 2秒/只）".format(
        len(target_etfs) * 2 // 60,
        len(target_etfs)
    ))


if __name__ == "__main__":
    main()
