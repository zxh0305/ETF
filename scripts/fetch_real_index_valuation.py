#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
真实指数估值数据获取器
====================
从乐咕乐股获取历史PE/PB数据，计算真实历史分位

数据源：
- 乐咕乐股（lg.eastmoney.com）- 提供20年历史数据
- A股整体估值 - 直接提供历史分位

支持的指数：
- 沪深300 (000300)
- 上证50 (000016)
- 中证500 (000905)
- 中证1000 (000852)
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# 清除代理
for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    os.environ.pop(var, None)

import akshare as ak
import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

# ============================================================================
# 指数配置
# ============================================================================

SUPPORTED_INDICES = {
    "沪深300": {"code": "000300", "name": "沪深300", "type": "宽基"},
    "上证50": {"code": "000016", "name": "上证50", "type": "宽基"},
    "中证500": {"code": "000905", "name": "中证500", "type": "宽基"},
    "中证1000": {"code": "000852", "name": "中证1000", "type": "宽基"},
}


class RealIndexValuationFetcher:
    """真实指数估值数据获取器"""
    
    def __init__(self):
        self.results = {}
        self.errors = []
        
    def fetch_index_history(self, index_name: str) -> Dict[str, Any]:
        """
        获取单个指数的历史估值数据
        
        Returns:
            {
                "pe": 当前PE,
                "pb": 当前PB,
                "pe_percentile": PE历史分位,
                "pb_percentile": PB历史分位,
                "pe_history_count": 历史数据条数,
                "pb_history_count": 历史数据条数,
                "data_start_date": 数据起始日期,
                "data_end_date": 数据结束日期,
                "source": "乐咕乐股",
                "is_real": True
            }
        """
        logger.info(f"获取 {index_name} 历史估值数据...")
        
        result = {
            "index_name": index_name,
            "code": SUPPORTED_INDICES.get(index_name, {}).get("code", ""),
            "source": "乐咕乐股",
            "is_real": True,
            "fetch_time": datetime.now().isoformat(),
            "errors": []
        }
        
        try:
            # 获取历史PE
            pe_df = ak.stock_index_pe_lg(symbol=index_name)
            logger.info(f"  PE数据: {len(pe_df)} 条")
            
            # 获取历史PB
            pb_df = ak.stock_index_pb_lg(symbol=index_name)
            logger.info(f"  PB数据: {len(pb_df)} 条")
            
            # 提取当前值
            latest_pe = float(pe_df["滚动市盈率"].iloc[-1])
            latest_pb = float(pb_df.iloc[-1, 2])  # PB在第3列
            
            # 计算历史分位
            pe_values = pe_df["滚动市盈率"].dropna()
            pb_values = pb_df.iloc[:, 2].dropna()
            
            pe_percentile = float((pe_values <= latest_pe).mean() * 100)
            pb_percentile = float((pb_values <= latest_pb).mean() * 100)
            
            # 记录日期范围
            pe_dates = pe_df["日期"]
            data_start = str(pe_dates.iloc[0])
            data_end = str(pe_dates.iloc[-1])
            
            result.update({
                "pe": round(latest_pe, 4),
                "pb": round(latest_pb, 4),
                "pe_percentile": round(pe_percentile, 2),
                "pb_percentile": round(pb_percentile, 2),
                "pe_history_count": len(pe_df),
                "pb_history_count": len(pb_df),
                "data_start_date": data_start,
                "data_end_date": data_end,
                "pe_min": round(float(pe_values.min()), 4),
                "pe_max": round(float(pe_values.max()), 4),
                "pe_mean": round(float(pe_values.mean()), 4),
                "pe_std": round(float(pe_values.std()), 4),
                "pb_min": round(float(pb_values.min()), 4),
                "pb_max": round(float(pb_values.max()), 4),
                "pb_mean": round(float(pb_values.mean()), 4),
                "pb_std": round(float(pb_values.std()), 4),
            })
            
            logger.info(f"  ✅ PE={latest_pe:.2f}, 分位={pe_percentile:.1f}%")
            logger.info(f"  ✅ PB={latest_pb:.2f}, 分位={pb_percentile:.1f}%")
            
        except Exception as e:
            logger.error(f"  ❌ 获取失败: {e}")
            result["errors"].append(str(e))
            result["is_real"] = False
            
        return result
    
    def fetch_market_overall(self) -> Dict[str, Any]:
        """
        获取A股整体估值（直接包含历史分位）
        """
        logger.info("获取A股整体估值...")
        
        try:
            df = ak.stock_a_all_pb()
            latest = df.iloc[-1]
            
            result = {
                "index_name": "A股整体",
                "code": "ALL",
                "source": "乐咕乐股-A股整体",
                "is_real": True,
                "fetch_time": datetime.now().isoformat(),
                "pb_median": float(latest["middlePB"]),
                "pb_equal_weight": float(latest["equalWeightAveragePB"]),
                "pb_percentile_all_history": float(latest["quantileInAllHistoryMiddlePB"] * 100),
                "pb_percentile_10y": float(latest["quantileInRecent10YearsMiddlePB"] * 100),
                "close": float(latest["close"]),
                "date": str(latest["date"]),
                "data_points": len(df)
            }
            
            logger.info(f"  ✅ PB中位数={result['pb_median']:.2f}")
            logger.info(f"  ✅ 历史分位={result['pb_percentile_all_history']:.1f}%")
            
            return result
            
        except Exception as e:
            logger.error(f"  ❌ 获取A股整体估值失败: {e}")
            return {"error": str(e), "is_real": False}
    
    def run(self) -> Dict[str, Any]:
        """运行完整获取流程"""
        logger.info("=" * 70)
        logger.info("开始获取真实指数估值数据")
        logger.info("=" * 70)
        
        start_time = datetime.now()
        
        # 1. 获取各指数历史估值
        for index_name in SUPPORTED_INDICES.keys():
            self.results[index_name] = self.fetch_index_history(index_name)
        
        # 2. 获取A股整体估值
        market_data = self.fetch_market_overall()
        self.results["A股整体"] = market_data
        
        # 3. 汇总统计
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        success_count = sum(1 for r in self.results.values() if r.get("is_real"))
        total_count = len(self.results)
        
        output = {
            "meta": {
                "generated_at": end_time.isoformat(),
                "duration_seconds": round(duration, 2),
                "source": "乐咕乐股",
                "success_rate": f"{success_count}/{total_count}",
                "is_all_real": success_count == total_count,
                "version": "v3.0-real"
            },
            "indices": self.results,
            "etf_mapping": self._build_etf_mapping()
        }
        
        # 4. 保存结果
        output_path = DATA_DIR / "index_valuation_real.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, ensure_ascii=False, indent=2, fp=f)
        
        logger.info("=" * 70)
        logger.info(f"✅ 完成！成功率: {success_count}/{total_count}")
        logger.info(f"   输出文件: {output_path}")
        logger.info("=" * 70)
        
        return output
    
    def _build_etf_mapping(self) -> Dict[str, str]:
        """
        构建ETF到指数的映射
        
        将ETF代码映射到其跟踪的指数代码
        """
        mapping = {
            # 沪深300
            "510300": "000300", "159919": "000300", "510310": "000300",
            "160706": "000300", "159912": "000300",
            # 上证50
            "510050": "000016", "510800": "000016", "510850": "000016",
            # 中证500
            "510500": "000905", "159922": "000905", "510510": "000905",
            # 中证1000
            "512100": "000852", "159845": "000852", "560010": "000852",
        }
        return mapping


def main():
    fetcher = RealIndexValuationFetcher()
    result = fetcher.run()
    
    # 打印摘要
    print("\n" + "=" * 70)
    print("数据获取摘要")
    print("=" * 70)
    
    for name, data in result.get("indices", {}).items():
        if data.get("is_real"):
            pe = data.get("pe", 0)
            pe_pct = data.get("pe_percentile", 0)
            print(f"{name:12s}: PE={pe:6.2f}  分位={pe_pct:5.1f}%  ✅")
        else:
            print(f"{name:12s}: 数据获取失败  ❌")


if __name__ == "__main__":
    main()
