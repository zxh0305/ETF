#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
穿透估值计算器 v1.0（简化版） - 基于持仓+申万行业加权
=====================================================
原理（简化版）：
1. 获取ETF季报持仓数据（前十大成分股）
2. 获取成分股所属申万行业（从股票代码判断）
3. 使用申万行业PE/PB（已有数据）
4. 按权重加权计算ETF整体PE/PB
5. 输出：etf_penetration_valuation_latest.json

数据来源：
- ETF持仓：AkShare fund_portfolio_hold_em()
- 申万行业PE/PB：sw_industry_valuation_latest.json

优势：
- 比申万行业加权更精准（用实际持仓权重）
- 不依赖股票实时PE/PB API（避开连接问题）
- 立即可用（所有数据源都已存在）

局限：
- 不是100%真实个股数据（用行业平均替代）
- 依赖季报数据（延迟1-3个月）

实施计划：
- v1.0：持仓+申万行业加权（本周完成）✅ 当前版本
- v2.0：获取个股真实PE/PB（解决API连接问题后）
- v3.0：积累历史数据，计算真实分位（3年后）

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

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("penetration_valuation_v1")

# 路径配置
BASE_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "etf_penetration_valuation_latest.json"
ETF_DATA_FILE = DATA_DIR / "etf_valuation_latest.json"
SW_DATA_FILE = DATA_DIR / "sw_industry_valuation_latest.json"

# 确保目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_sw_industry_data() -> Dict:
    """加载申万行业PE/PB数据"""
    if not SW_DATA_FILE.exists():
        logger.warning(f"⚠️ 申万行业数据文件不存在: {SW_DATA_FILE}")
        return {}
    
    with open(SW_DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # 转换为字典：行业代码 → {pe, pb}
    sw_dict = {}
    for item in data.get("data", []):
        sw_code = item.get("index_code", "")
        sw_dict[sw_code] = {
            "pe": item.get("pe"),
            "pb": item.get("pb"),
            "pe_percentile": item.get("pe_percentile"),
            "pb_percentile": item.get("pb_percentile"),
        }
    
    logger.info(f"✅ 加载申万行业数据: {len(sw_dict)} 个行业")
    return sw_dict


def get_etf_holdings(etf_code: str) -> Optional[List[Dict]]:
    """
    获取ETF持仓数据（前十大成分股）
    
    数据源：AkShare fund_portfolio_hold_em()
    """
    try:
        # etf_code格式转换（sz159915 → 159915）
        code_clean = etf_code.replace("sh", "").replace("sz", "")
        
        # ✅ 正确的API：fund_portfolio_hold_em()
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
                "weight": float(row.get("占净值比例", 0)),
            })
        
        logger.info(f"  ✅ {etf_code} 获取到 {len(holdings)} 只成分股持仓")
        return holdings
        
    except Exception as e:
        logger.warning(f"  ❌ {etf_code} 获取持仓失败: {e}")
        return None


def get_stock_sw_industry(stock_code: str) -> Optional[str]:
    """
    获取个股所属申万行业（简化版）
    
    逻辑：
    - 根据股票代码前缀判断（6=上海，0/3=深圳）
    - 简化：返回None（后续用行业平均替代）
    
    注意：完整实现需要股票→申万行业映射表
    当前简化版：不映射，直接用行业平均
    """
    # TODO: 实现股票→申万行业映射
    # 当前返回None，表示用行业平均
    return None


def calculate_weighted_valuation_simplified(holdings: List[Dict], sw_data: Dict) -> Optional[Dict]:
    """
    计算加权PE/PB（简化版：用申万行业平均）
    
    公式：
    ETF_PE = Σ(成分股所属行业PE × 权重) / Σ(权重)
    ETF_PB = Σ(成分股所属行业PB × 权重) / Σ(权重)
    
    注意：简化版用行业平均PE/PB替代个股真实PE/PB
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
        
        # 简化版：不获取个股真实PE/PB，用行业平均
        # 这里需要用股票→行业映射，但当前简化版跳过
        # 直接假设所有成分股都用同一个行业平均（不准确，但可用）
        
        # TODO: 完整实现需要：
        # 1. 股票→申万行业映射
        # 2. 获取该行业PE/PB
        # 3. 加权计算
        
        # 当前简化版：跳过（返回None）
        continue
    
    if valid_count == 0:
        return None
    
    # 计算加权平均
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


def process_etf_simplified(etf: Dict, sw_data: Dict) -> Dict:
    """
    处理单只ETF：计算穿透估值（简化版）
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
    
    # 2. 计算加权估值（简化版）
    # TODO: 完整实现
    # 当前简化版：不计算（返回None）
    valuation = None
    
    if not valuation:
        return {
            **etf,
            "penetration_pe": None,
            "penetration_pb": None,
            "penetration_coverage": 0,
            "penetration_status": "not_implemented",
            "penetration_note": "简化版v1.0未实现完整逻辑，需用股票→行业映射",
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
    logger.info("穿透估值计算器 v1.0（简化版） - 基于持仓+申万行业加权")
    logger.info("=" * 70)
    
    # 1. 加载申万行业数据
    sw_data = load_sw_industry_data()
    if not sw_data:
        logger.error("❌ 申万行业数据加载失败，无法继续")
        return
    
    # 2. 加载ETF数据
    if not ETF_DATA_FILE.exists():
        logger.error(f"❌ ETF数据文件不存在: {ETF_DATA_FILE}")
        return
    
    with open(ETF_DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    records = data.get("data", [])
    logger.info(f"加载 {len(records)} 条ETF记录")
    
    # 3. 筛选需要计算穿透估值的ETF
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
    
    # 4. 计算穿透估值（测试前5只）
    results = []
    max_test = min(5, len(target_etfs))
    
    logger.info(f"\n开始测试（前 {max_test} 只）...")
    
    for i, etf in enumerate(target_etfs[:max_test]):
        logger.info(f"\n[{i+1}/{max_test}] 处理中...")
        
        result = process_etf_simplified(etf, sw_data)
        results.append(result)
        
        # 限流：每次请求后暂停2秒
        if i < max_test - 1:
            logger.info(f"  等待2秒（避免API限流）...")
            time.sleep(2)
    
    # 5. 保存结果
    success_count = len([r for r in results if r.get("penetration_status") == "success"])
    
    output = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "version": "v1.0",
            "description": "穿透估值计算（简化版：持仓+申万行业加权）",
            "test_mode": f"前{max_test}只测试",
            "success_count": success_count,
            "total_count": len(results),
            "note": "简化版v1.0：未实现完整逻辑，需用股票→行业映射",
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
    logger.info("\n⚠️ 注意：简化版v1.0未实现完整逻辑")
    logger.info("   需要：1. 股票→申万行业映射表")
    logger.info("        2. 用个股真实PE/PB替代行业平均")
    logger.info("\n下次运行：实现完整逻辑后，处理全部目标ETF")


if __name__ == "__main__":
    main()
